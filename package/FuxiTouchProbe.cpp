// SPDX-License-Identifier: BSD-2-Clause-Patent
// Default-off staged bring-up of the fuxi (Xiaomi 13) ST FingerTip FTM5 touch controller. `fuxi-touch=<n>`:
//   1  read-only snapshot: GCC branches, S4 DFS levels, the touch pins, the two touch rails in the command database
//   2  vote the touch rails through RPMh, the QUP clocks, configure the pins, read the GENI engine identity
//   3  GENI SPI init and clock, reset the controller, wait for its ready event, read the chip id (36 40)
//   4  start sensing, take the interrupt, drain the event FIFO and publish contacts to the HID source
// Every stage reports on the diagnostic page (native_touch_rows); the first failure stops the sequence. Nothing here is
// validated on the device until a boot has shown it.
//
// The QUP1 SE4 engine, its clocks, pins 44..47, the stream id and the interrupt pin 25 are the same as on sheng, so the
// clock, pin, DMA and SMMU code follows UniXNU-sheng package/TouchProbe.cpp and uses its TouchBoard.h. fuxi facts
// (rails, reset pin, pulls, SPI rate, coordinates) are in FuxiTouchBoard.h; the protocol is FtsProtocol.c.
//
// Other boot arguments: fuxi-touch-hz (SPI rate, default 12 MHz from the DT), fuxi-touch-power=0 (skip the rail votes),
// fuxi-touch-tcs (active TCS of the apps RSC used for the votes, default 2), fuxi-touch-poll=1 (no interrupt),
// fuxi-touch-map (FTS_MAP_* bits applied before publishing: 1 swap, 2 mirror x, 4 mirror y),
// fuxi-touch-panic (1: when the requested stage ends or fails, panic with the four diagnostic rows as the message, so the
// result can be read from the panic screen while no display driver runs; 2: in stage 4, also after the first lift).
// With sheng-smp=1 the panic message has two more rows: the secondary-core state ArmCpu records (smpText).
// fuxi-touch-hid=1: once sensing runs, start ShengHidInput's touch digitizer (FuxiHidProbe.cpp), which sends every published
// contact set as a HID report (the hid counter); the panic message then has a HID row (fuxi_hid_row).
// The probe starts from bsd_init (patches/xnu/fuxi-touch-probe.patch); every stage result is also printed to the kernel log.
#include <IOKit/IOService.h>
#include <IOKit/IOLib.h>
#include <IOKit/IOMemoryDescriptor.h>
#include <IOKit/IOBufferMemoryDescriptor.h>
#include <string.h>
#include <libkern/libkern.h>
#include <libkern/c++/OSSharedPtr.h>
#include <kern/debug.h>
#include <kern/thread.h>
#include <kern/clock.h>
#include <pexpert/pexpert.h>
extern "C" {
#include "GeniSpi.h"
#include "FtsProtocol.h"
#include "FtsTouchCore.h"
#include "TouchBoard.h"
#include "FuxiTouchBoard.h"
#include "QcomRpmh.h"
#include "SmmuBypass.h"
}

// The HID source (ShengHidInput NativeHidInput.cpp) reads 12 slots and scales x from 0..30480 and y from 0..20320 to its
// logical range; contacts are mapped into those ranges before they are published.
constexpr unsigned kPublishSlots = 12;
constexpr int kHidXMax = 30480, kHidYMax = 20320;

extern "C" {
char native_touch_rows[4][120];
char native_touch_trace[8][120];
volatile uint32_t native_touch_loop_step;
volatile uint32_t native_touch_stage_req, native_touch_stage_done, native_touch_step, native_touch_frames,
    native_touch_valid, native_touch_contacts, native_touch_hid_reports;
volatile int native_touch_error;
volatile int native_touch_last_x = -1, native_touch_last_y = -1;
// Latest finger set for the HID digitizer source; the sequence is odd while it is written.
volatile uint32_t native_touch_seq;
volatile uint32_t native_touch_count;
volatile int native_touch_xs[kPublishSlots], native_touch_ys[kPublishSlots], native_touch_ids[kPublishSlots];
// [0] 0 not armed, 1 armed, 2 attach failed, [1] interrupts, [2] spurious, [3] attach status
volatile uint32_t native_touch_irq_stats[4];
}

namespace {
struct Region {OSSharedPtr<IOMemoryMap> keep; uintptr_t va = 0;};

bool mapRegion(uint64_t phys, uint64_t length, Region &region) {
    IODeviceMemory *memory = IODeviceMemory::withRange(phys, length);
    if (!memory) return false;
    region.keep = OSSharedPtr<IOMemoryMap>(memory->map(kIOMapAnywhere | kIOMapInhibitCache), OSNoRetain);
    memory->release();
    region.va = region.keep ? static_cast<uintptr_t>(region.keep->getVirtualAddress()) : 0;
    return region.va != 0;
}
uint32_t rd32(uintptr_t base, uint32_t reg) {return *reinterpret_cast<volatile uint32_t *>(base + reg);}
void wr32(uintptr_t base, uint32_t reg, uint32_t value) {
    *reinterpret_cast<volatile uint32_t *>(base + reg) = value;
    __asm__ volatile("dsb sy" ::: "memory");
}

// The serial engine's DMA master reads and writes two 64 KiB buffers through a pass-through stream of the apps SMMU,
// with explicit cache maintenance (as on sheng).
constexpr size_t kDmaBytes = 64 * 1024;
void cacheRange(void *p, size_t len, int op) {   // 0 clean, 1 clean+invalidate, 2 invalidate
    uint64_t ctr;
    __asm__ volatile("mrs %0, ctr_el0" : "=r"(ctr));
    size_t line = 4u << ((ctr >> 16) & 15);
    uintptr_t a = reinterpret_cast<uintptr_t>(p) & ~(line - 1), end = reinterpret_cast<uintptr_t>(p) + len;
    for (; a < end; a += line) {
        if (op == 0) __asm__ volatile("dc cvac, %0" :: "r"(a) : "memory");
        else if (op == 1) __asm__ volatile("dc civac, %0" :: "r"(a) : "memory");
        else __asm__ volatile("dc ivac, %0" :: "r"(a) : "memory");
    }
    __asm__ volatile("dsb sy" ::: "memory");
}
void dmaClean(void *, void *p, size_t len) {cacheRange(p, len, 0);}
void dmaCleanInval(void *, void *p, size_t len) {cacheRange(p, len, 1);}
void dmaInval(void *, void *p, size_t len) {cacheRange(p, len, 2);}
uint32_t smmuRd(void *ctx, unsigned o) {return rd32(reinterpret_cast<uintptr_t>(ctx), o);}
void smmuWr(void *ctx, unsigned o, uint32_t v) {wr32(reinterpret_cast<uintptr_t>(ctx), o, v);}

uint32_t ioRd(void *ctx, uint32_t reg) {return rd32(reinterpret_cast<uintptr_t>(ctx), reg);}
void ioWr(void *ctx, uint32_t reg, uint32_t value) {wr32(reinterpret_cast<uintptr_t>(ctx), reg, value);}
// Waits of the SPI status polls are about a microsecond: spin on the counter instead of blocking the thread.
void ioDelayUs(void *, unsigned us) {
    if (us > 50) {IODelay(us); return;}
    uint64_t frequency = 0, start = 0, now = 0;
    __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(frequency));
    __asm__ volatile("isb\n\tmrs %0, cntpct_el0" : "=r"(start));
    const uint64_t ticks = (frequency ? frequency : 19200000) * us / 1000000 + 1;
    do {__asm__ volatile("isb\n\tmrs %0, cntpct_el0" : "=r"(now));} while (now - start < ticks);
}

// TLMM pin control: bits 1:0 pull (1 down, 3 up), bits 5:2 function, bits 8:6 drive ((mA / 2) - 1), bit 9 output enable;
// IN_OUT (+0x4) bit 0 the input level, bit 1 the output level (pinctrl-msm.c, pinctrl-sm8550.c).
constexpr uint32_t kPullDown = 1, kPullUp = 3, kOutputEnable = 1u << 9, kOutHigh = 1u << 1;
constexpr uint32_t pinCfg(unsigned func, unsigned ma, uint32_t pull) {return pull | (func & 15u) << 2 | ((ma / 2 - 1) & 7u) << 6;}

constexpr uint64_t kCmdDbBase = 0x81c60000ULL, kCmdDbSize = 0x20000;   // DT reserved-memory aop_cmd_db_region@81c60000
constexpr uint64_t kAppsRscDrv2 = 0x17a20000ULL;                        // DT apps_rsc@17a00000 reg "drv-2"
constexpr uint32_t kTcsOffset = 0xd00;                                  // DT drv@2 qcom,tcs-offset
// DT drv@2 qcom,tcs-config: ACTIVE 3, SLEEP 2, WAKE 2, CONTROL 0, FAST_PATH 1, so TCS 0..2 are the active ones.
constexpr unsigned kActiveTcs = 3;

struct Session {
    Region gccLow, gccS4, gccHalt, gccVote, tlmmIrq, tlmmReset, tlmmSpi, wrapper, se, smmu, rsc;
    IOBufferMemoryDescriptor *dmaMem;
    uint64_t dmaPhys;
    int smmuSlot, smmuBank, smmuErr;
    struct geni_spi spi;
    uint8_t *tx, *rx, *events;
    struct fts_bus bus;
    struct fts_chip chip;
    struct fts_touch_core core;
    struct fts_map map;
    uint32_t vals[32];
    uint32_t vddAddr, avddAddr;       // from the command database (0: not found)
    int rpmhRc, rpmhWait;
    unsigned tcs;
    int lastRc, idRc, resetRc, senseRc;   // the last three are 99 until they run
    uint32_t lastLen, xIrq, xGeni;
    uint64_t levelHz[TB_DFS_LEVELS];
    unsigned level, div;
    uint64_t actualHz;
    uint32_t reads, drained, idleWakes, rearms;
};

int busXfer(void *ctx, const uint8_t *tx, uint8_t *rx, size_t len) {
    Session *s = static_cast<Session *>(ctx);
    int rc = geni_spi_transfer(&s->spi, tx, rx, len, 0);
    if (rc && !s->lastRc) {s->lastRc = rc; s->lastLen = static_cast<uint32_t>(len); s->xIrq = s->spi.snap_irq; s->xGeni = s->spi.snap_status;}
    return rc;
}
void busDelay(void *, unsigned ms) {IOSleep(ms);}
void busReset(void *ctx, int level) {
    Session *s = static_cast<Session *>(ctx);
    wr32(s->tlmmReset.va, 4, level ? kOutHigh : 0);
}

void fail(unsigned step, int code) {
    if (!native_touch_error) {native_touch_step = step; native_touch_error = code ? code : -1;}
}

void rows(const Session &s) {
    const uint32_t *v = s.vals;
    snprintf(native_touch_rows[0], sizeof native_touch_rows[0],
        "FTS s%u/%u st%u e%d vote%08x h%08x %08x %08x %08x %08x gp%08x",
        native_touch_stage_done, native_touch_stage_req, native_touch_step, native_touch_error,
        v[0], v[1], v[2], v[3], v[4], v[5], v[6]);
    snprintf(native_touch_rows[1], sizeof native_touch_rows[1],
        "FTS p%08x %08x %08x %08x rst%08x irq%08x hw%08x L%u/%u %uHz",
        v[9], v[10], v[11], v[12], v[13], v[14], v[17], s.level, s.div, (unsigned)s.actualHz);
    snprintf(native_touch_rows[2], sizeof native_touch_rows[2],
        "FTS pwr vdd%05x avdd%05x tcs%u rc%d w%d id%02x%02x rc%d rst%d/%u sp4%d ev%02x%02x%02x sense%d",
        s.vddAddr, s.avddAddr, s.tcs, s.rpmhRc, s.rpmhWait, s.chip.id[0], s.chip.id[1], s.idRc, s.resetRc,
        s.chip.reset_attempts, s.chip.spi4_fallback, s.chip.last_event[0], s.chip.last_event[1], s.chip.last_event[2], s.senseRc);
    snprintf(native_touch_rows[3], sizeof native_touch_rows[3],
        "FTS rd%u ev%u in%u mv%u up%u er%u/%02x rdy%u rearm%u c%u %d,%d hid%u irq%u/%u xf%d",
        s.reads, s.drained, s.core.enters, s.core.motions, s.core.leaves, s.core.errors, s.core.last_error[0],
        s.core.readies, s.rearms, native_touch_contacts, native_touch_last_x, native_touch_last_y, native_touch_hid_reports,
        native_touch_irq_stats[1], native_touch_irq_stats[2], s.lastRc);
}
void mark(const Session &s, unsigned step) {native_touch_step = step; rows(s);}

static void (*gTouchSink)(void *);
static void *gTouchSinkContext;

void publish(const Session &s, unsigned count, const fts_point *p) {
    native_touch_seq = native_touch_seq + 1;
    __asm__ volatile("dmb ish" ::: "memory");
    native_touch_count = count;
    for (unsigned i = 0; i < count && i < kPublishSlots; ++i) {
        int x, y;
        fts_map_point(&s.map, p[i].x, p[i].y, &x, &y);
        native_touch_xs[i] = x;
        native_touch_ys[i] = y;
        native_touch_ids[i] = p[i].id;   // the controller's tracking id, 0..9; NativeHidInput sends it as the contact identifier
    }
    __asm__ volatile("dmb ish" ::: "memory");
    native_touch_seq = native_touch_seq + 1;
    if (void (*sink)(void *) = __atomic_load_n(&gTouchSink, __ATOMIC_ACQUIRE)) sink(gTouchSinkContext);
}

bool snapshot(Session &s) {
    mark(s, 1);
    if (!mapRegion(TB_GCC_BASE + 0x0000, 0x1000, s.gccLow) || !mapRegion(TB_GCC_BASE + 0x18000, 0x1000, s.gccS4) ||
        !mapRegion(TB_GCC_BASE + 0x23000, 0x1000, s.gccHalt) || !mapRegion(TB_GCC_BASE + 0x52000, 0x1000, s.gccVote) ||
        !mapRegion(ftb_tlmm_ctl(FTB_GPIO_IRQ), 0x1000, s.tlmmIrq) || !mapRegion(ftb_tlmm_ctl(FTB_GPIO_RESET), 0x1000, s.tlmmReset) ||
        !mapRegion(ftb_tlmm_ctl(FTB_GPIO_SPI_MISO), 4 * FTB_GPIO_STRIDE, s.tlmmSpi)) {
        fail(1, -12);
        return false;
    }
    uint32_t *v = s.vals;
    v[0] = rd32(s.gccVote.va, TB_GCC_VOTE_ENABLE & 0xfff);
    v[1] = rd32(s.gccHalt.va, TB_HALT_M_AHB & 0xfff);
    v[2] = rd32(s.gccHalt.va, TB_HALT_S_AHB & 0xfff);
    v[3] = rd32(s.gccHalt.va, TB_HALT_CORE & 0xfff);
    v[4] = rd32(s.gccHalt.va, TB_HALT_CORE_2X & 0xfff);
    v[5] = rd32(s.gccS4.va, TB_HALT_S4 & 0xfff);
    v[6] = rd32(s.gccLow.va, TB_GCC_GPLL0_MODE);
    for (unsigned l = 0; l < TB_DFS_LEVELS; ++l) {
        uint32_t cfg = rd32(s.gccS4.va, (TB_S4_RCG + TB_RCG_PERF_CFG(l)) & 0xfff);
        uint32_t m = rd32(s.gccS4.va, (TB_S4_RCG + TB_RCG_PERF_M(l)) & 0xfff);
        uint32_t n = rd32(s.gccS4.va, (TB_S4_RCG + TB_RCG_PERF_N(l)) & 0xfff);
        s.levelHz[l] = tb_dfs_level_hz(cfg, m, n);
    }
    for (unsigned i = 0; i < 4; ++i) v[9 + i] = rd32(s.tlmmSpi.va, i * FTB_GPIO_STRIDE);
    v[13] = rd32(s.tlmmReset.va, 0) | rd32(s.tlmmReset.va, 4) << 16;
    v[14] = rd32(s.tlmmIrq.va, 0) | rd32(s.tlmmIrq.va, 4) << 16;
    // The rails by name in the AOP command database; the board constants are the fallback (measured on Android).
    static uint8_t db[kCmdDbSize];
    Region dbw;
    s.vddAddr = s.avddAddr = 0;
    if (mapRegion(kCmdDbBase, kCmdDbSize, dbw)) {
        for (size_t i = 0; i < sizeof db; i += 4) {const uint32_t w = rd32(dbw.va, static_cast<uint32_t>(i)); memcpy(db + i, &w, 4);}
        QcomRpmhResource res;
        if (!qcom_cmd_db_find(db, sizeof db, FTB_VDD_RPMH_RESOURCE, &res)) s.vddAddr = res.address;
        if (!qcom_cmd_db_find(db, sizeof db, FTB_AVDD_RPMH_RESOURCE, &res)) s.avddAddr = res.address;
    }
    return true;
}

// One active-only request of up to four commands in TCS s.tcs of the apps RSC. Waits for the TCS to be idle before
// and for its done bit after; whether the done bit latches without the TCS interrupt enabled is not known, so a missing
// bit only waits the full 10 ms (sheng's microphone rail sleeps 2 ms instead) and is recorded as rpmhWait -1.
int rpmhSend(Session &s, const QcomRscLayout &layout, const uint32_t *addresses, const uint32_t *values, unsigned count) {
    QcomRpmhWrite writes[24];
    const uint32_t base = layout.tcs_stride * s.tcs;
    unsigned i = 0;
    for (; i < 1000 && rd32(s.rsc.va, kTcsOffset + base + layout.status) == 0; ++i) IODelay(10);   // non-zero: the TCS is idle
    if (i == 1000) return -16;
    const unsigned n = qcom_rpmh_active_request(&layout, s.tcs, addresses, values, count, writes, 24);
    if (!n) return -22;
    for (unsigned k = 0; k < n; ++k) wr32(s.rsc.va, kTcsOffset + writes[k].offset, writes[k].value);
    for (i = 0; i < 1000 && !(rd32(s.rsc.va, kTcsOffset + layout.irq_status) & (1u << s.tcs)); ++i) IODelay(10);
    if (i == 1000) s.rpmhWait = -1;
    else if (s.rpmhWait >= 0 && s.rpmhWait < static_cast<int>(i)) s.rpmhWait = static_cast<int>(i);
    const unsigned m = qcom_rpmh_finish(&layout, s.tcs, writes, 24);
    for (unsigned k = 0; k < m; ++k) wr32(s.rsc.va, kTcsOffset + writes[k].offset, writes[k].value);
    return 0;
}

bool powerOn(Session &s) {
    mark(s, 20);
    const uint32_t vdd = s.vddAddr ? s.vddAddr : FTB_VDD_RPMH_ADDR, avdd = s.avddAddr ? s.avddAddr : FTB_AVDD_RPMH_ADDR;
    if (!mapRegion(kAppsRscDrv2, 0x10000, s.rsc)) {fail(20, -12); return false;}
    const QcomRscLayout layout = qcom_rsc_layout(rd32(s.rsc.va, 0));
    // ftb_power_on_cmds in order (vdd, then avdd, as fts_enable_reg), one request per rail, against the addresses found
    // above: each command is a rail's resource address plus a VRM register offset.
    constexpr unsigned kCmds = sizeof ftb_power_on_cmds / sizeof ftb_power_on_cmds[0];
    for (unsigned first = 0; first < kCmds && !s.rpmhRc;) {
        const uint32_t rail = ftb_power_on_cmds[first].addr & ~0xffu;
        uint32_t addresses[4], values[4];
        unsigned n = 0;
        for (; first < kCmds && n < 4 && (ftb_power_on_cmds[first].addr & ~0xffu) == rail; ++first, ++n) {
            const uint32_t base = rail == FTB_VDD_RPMH_ADDR ? vdd : rail == FTB_AVDD_RPMH_ADDR ? avdd : rail;
            addresses[n] = base + (ftb_power_on_cmds[first].addr & 0xffu);
            values[n] = ftb_power_on_cmds[first].data;
        }
        s.rpmhRc = rpmhSend(s, layout, addresses, values, n);
    }
    if (s.rpmhRc) {fail(21, s.rpmhRc); return false;}
    IOSleep(FTB_POWER_SETTLE_MS);
    return true;
}

bool enable(Session &s, bool power) {
    mark(s, 2);
    if (power && !powerOn(s)) return false;
    // GPLL0 feeds the DFS levels; vote for it (shared) and wait for lock.
    wr32(s.gccVote.va, TB_GCC_GPLL0_ENABLE & 0xfff, rd32(s.gccVote.va, TB_GCC_GPLL0_ENABLE & 0xfff) | 1u);
    for (unsigned i = 0; i < 10000 && !(rd32(s.gccLow.va, TB_GCC_GPLL0_MODE) & (1u << 31)); ++i) IODelay(10);
    s.vals[6] = rd32(s.gccLow.va, TB_GCC_GPLL0_MODE);
    wr32(s.gccVote.va, TB_GCC_VOTE_ENABLE & 0xfff, rd32(s.gccVote.va, TB_GCC_VOTE_ENABLE & 0xfff) | TB_VOTE_ALL);
    auto running = [](uint32_t cbcr) {return !(cbcr & TB_CBCR_CLK_OFF) || (cbcr & 2u);};
    bool ok = false;
    for (unsigned i = 0; i < 2000 && !ok; ++i) {
        ok = running(rd32(s.gccHalt.va, TB_HALT_M_AHB & 0xfff)) && running(rd32(s.gccHalt.va, TB_HALT_S_AHB & 0xfff)) &&
             !(rd32(s.gccHalt.va, TB_HALT_CORE & 0xfff) & TB_CBCR_CLK_OFF) &&
             !(rd32(s.gccHalt.va, TB_HALT_CORE_2X & 0xfff) & TB_CBCR_CLK_OFF) &&
             !(rd32(s.gccS4.va, TB_HALT_S4 & 0xfff) & TB_CBCR_CLK_OFF);
        if (!ok) IODelay(10);
    }
    s.vals[0] = rd32(s.gccVote.va, TB_GCC_VOTE_ENABLE & 0xfff);
    s.vals[1] = rd32(s.gccHalt.va, TB_HALT_M_AHB & 0xfff);
    s.vals[2] = rd32(s.gccHalt.va, TB_HALT_S_AHB & 0xfff);
    s.vals[3] = rd32(s.gccHalt.va, TB_HALT_CORE & 0xfff);
    s.vals[4] = rd32(s.gccHalt.va, TB_HALT_CORE_2X & 0xfff);
    s.vals[5] = rd32(s.gccS4.va, TB_HALT_S4 & 0xfff);
    if (!ok) {fail(2, -110); return false;}   // never touch the engine without running clocks
    // DT qupv3_se4_spi_*_active and mi_ts_cs_active: function qup1_se4, 6 mA, data and clock pulled down, CS pulled up.
    for (unsigned i = 0; i < 3; ++i) wr32(s.tlmmSpi.va, i * FTB_GPIO_STRIDE, pinCfg(TB_FUNC_QUP1_SE4, 6, kPullDown));
    wr32(s.tlmmSpi.va, 3 * FTB_GPIO_STRIDE, pinCfg(TB_FUNC_QUP1_SE4, 6, kPullUp));
    // DT mi_ts_active: reset (GPIO 24) and interrupt (GPIO 25) as GPIO, 8 mA, pulled up; reset driven high (released).
    wr32(s.tlmmReset.va, 4, kOutHigh);
    wr32(s.tlmmReset.va, 0, pinCfg(0, 8, kPullUp) | kOutputEnable);
    wr32(s.tlmmIrq.va, 0, pinCfg(0, 8, kPullUp));
    for (unsigned i = 0; i < 4; ++i) s.vals[9 + i] = rd32(s.tlmmSpi.va, i * FTB_GPIO_STRIDE);
    s.vals[13] = rd32(s.tlmmReset.va, 0) | rd32(s.tlmmReset.va, 4) << 16;
    s.vals[14] = rd32(s.tlmmIrq.va, 0) | rd32(s.tlmmIrq.va, 4) << 16;
    mark(s, 3);   // the next accesses touch the engine: if the page freezes here, the engine access hung
    if (!mapRegion(TB_QUP_WRAPPER_BASE, 0x2000, s.wrapper) || !mapRegion(FTB_SE_BASE, FTB_SE_SIZE, s.se)) {fail(3, -12); return false;}
    s.spi.se = (struct geni_io){reinterpret_cast<void *>(s.se.va), ioRd, ioWr, ioDelayUs};
    s.spi.wrapper = (struct geni_io){reinterpret_cast<void *>(s.wrapper.va), ioRd, ioWr, ioDelayUs};
    int r = geni_spi_read_info(&s.spi);
    s.vals[17] = s.spi.info.qup_hw_version;
    if (r) {fail(3, r); return false;}
    return true;
}

bool prepareDma(Session &s) {
    mark(s, 41);
    s.dmaMem = IOBufferMemoryDescriptor::inTaskWithPhysicalMask(kernel_task, static_cast<IOOptionBits>(kIODirectionInOut) | static_cast<IOOptionBits>(kIOMemoryPhysicallyContiguous),
                                                               2 * kDmaBytes, 0xfffffff000ULL);
    if (!s.dmaMem || s.dmaMem->prepare() != kIOReturnSuccess) {fail(41, -12); return false;}
    addr64_t seg_len = 0;
    s.dmaPhys = s.dmaMem->getPhysicalSegment(0, &seg_len);
    uint8_t *virt = static_cast<uint8_t *>(s.dmaMem->getBytesNoCopy());
    if (!virt || !s.dmaPhys || seg_len < 2 * kDmaBytes) {fail(42, -14); return false;}
    memset(virt, 0, 2 * kDmaBytes);
    cacheRange(virt, 2 * kDmaBytes, 1);
    if (!mapRegion(TB_APPS_SMMU_BASE, TB_APPS_SMMU_SIZE, s.smmu)) {fail(43, -12); return false;}
    struct smmu_io io = {reinterpret_cast<void *>(s.smmu.va), smmuRd, smmuWr};
    struct smmu_plan plan = smmu_plan_bypass(&io, FTB_QUP_SMMU_SID, s.dmaPhys, 2 * kDmaBytes);
    s.smmuSlot = static_cast<int>(plan.slot); s.smmuBank = static_cast<int>(plan.bank);
    if (plan.error) {s.smmuErr = 1; fail(43, -101); return false;}
    if (smmu_configure_bypass(&io, &plan, FTB_QUP_SMMU_SID)) {s.smmuErr = 2; fail(44, -102); return false;}
    s.spi.use_dma = 1;
    s.spi.dma.ctx = nullptr;
    s.spi.dma.clean = dmaClean;
    s.spi.dma.clean_inval = dmaCleanInval;
    s.spi.dma.inval = dmaInval;
    s.spi.dma.tx_virt = virt;
    s.spi.dma.rx_virt = virt + kDmaBytes;
    s.spi.dma.tx_phys = s.dmaPhys;
    s.spi.dma.rx_phys = s.dmaPhys + kDmaBytes;
    s.spi.dma.size = kDmaBytes;
    return true;
}

bool openBus(Session &s, unsigned hz) {
    mark(s, 4);
    s.spi.poll_limit = 400000;
    s.spi.poll_only = 2;
    if (s.spi.info.fifo_disabled && !prepareDma(s)) return false;
    int r = geni_spi_init(&s.spi);
    if (r) {fail(4, r); return false;}
    struct tb_clock_choice choice = {};
    if (tb_choose_clock(s.levelHz, TB_DFS_LEVELS, s.spi.oversampling, hz, &choice)) {fail(5, -22); return false;}
    s.level = choice.level;
    s.div = choice.div;
    s.actualHz = choice.actual_hz;
    r = geni_spi_set_clock(&s.spi, hz, static_cast<unsigned>(choice.sclk_hz), choice.level);
    if (r) {fail(5, r); return false;}
    r = geni_spi_setup(&s.spi, FTB_SPI_MODE, 0);
    if (r) {fail(5, r); return false;}
    return true;
}
}  // namespace

extern "C" void native_touch_set_sink(void (*sink)(void *), void *context) {
    gTouchSinkContext = context;
    __atomic_store_n(&gTouchSink, sink, __ATOMIC_RELEASE);
}

// The touch interrupt: GPIO 25, active low (DT fts,irq-gpio flags 0x2008, IRQF_TRIGGER_LOW | IRQF_ONESHOT). The controller
// holds the line low while its FIFO is not empty. The TLMM detects the falling edge (INTR_CFG detection 2, polarity bit set,
// raw status on, target the application processor) and raises the summary interrupt SPI 208; the handler acknowledges the
// pin and wakes the thread, which drains the FIFO until the line reads high again, so an edge that came while it was
// reading is not lost. A timed wait also checks the line in case an edge is missed.
extern "C" int armcpu_spi_attach(uint32_t, bool, void (*)(void *), void *, uint32_t *, uint64_t *) __attribute__((weak_import));
static volatile uint32_t gTouchIrqEvents;
static volatile uint32_t *gTouchPin;
static void touchIrq(void *) {
    if (!(gTouchPin[0xc / 4] & 1)) {native_touch_irq_stats[2] = native_touch_irq_stats[2] + 1; return;}
    gTouchPin[0xc / 4] = 0;
    native_touch_irq_stats[1] = native_touch_irq_stats[1] + 1;
    __atomic_fetch_add(&gTouchIrqEvents, 1, __ATOMIC_RELEASE);
    thread_wakeup((event_t)&gTouchIrqEvents);
}
static bool armTouchIrq(Session &s) {
    gTouchPin = reinterpret_cast<volatile uint32_t *>(s.tlmmIrq.va);
    uint32_t cfg = gTouchPin[0x8 / 4];
    cfg &= ~((7u << 5) | (3u << 2) | (1u << 1) | 1u);
    cfg |= (3u << 5) | (2u << 2) | (1u << 1) | (1u << 4);
    gTouchPin[0x8 / 4] = cfg;
    gTouchPin[0xc / 4] = 0;
    __asm__ volatile("dsb sy" ::: "memory");
    if (!armcpu_spi_attach) {native_touch_irq_stats[0] = 2; native_touch_irq_stats[3] = 0xffff; return false;}
    const int rc = armcpu_spi_attach(32 + FTB_TLMM_SUMMARY_GIC_SPI, false, touchIrq, nullptr, nullptr, nullptr);
    native_touch_irq_stats[3] = static_cast<uint32_t>(rc);
    if (rc) {native_touch_irq_stats[0] = 2; return false;}
    gTouchPin[0x8 / 4] = cfg | 1u;   // enable last
    native_touch_irq_stats[0] = 1;
    return true;
}
static bool lineLow(const Session &s) {return (rd32(s.tlmmIrq.va, 4) & 1) == 0;}

// Secondary-core state of ArmCpu (UniXNU drivers/ArmCpu/ArmCpu.cpp) on a boot with sheng-smp=1. Step of each core 1..7:
// 1 nub started, 2 registered, 3 start thread running, 4 PSCI CPU_ON issued, 5 initCPU entered on the new core,
// 6 redistributor ready, 7 running. A failure code parks the core (1 MPIDR differs, 2 or 3 redistributor, 4 registration);
// psci is the CPU_ON result (0 success; -1000 no start thread, -1001 no PSCI method in the DT). Weak like armcpu_spi_attach:
// a kernel without ArmCpu reports no SMP rows.
extern "C" {
extern volatile uint32_t __attribute__((weak_import)) armcpu_smp_requested, armcpu_smp_running, armcpu_smp_conduit,
    armcpu_boot_mpidr, armcpu_smp_step[8], armcpu_smp_fail[8], armcpu_core_timer[8], armcpu_core_sgi[8];
extern volatile int32_t __attribute__((weak_import)) armcpu_smp_psci_rc[8];
extern volatile uint64_t __attribute__((weak_import)) armcpu_ipi_sent, armcpu_ipi_interrupts;
extern uint32_t processor_avail_count;   // osfmk/kern/processor.h: processors the scheduler runs threads on
int cpu_number(void);
}
// Two report rows: running cores, PSCI conduit (1 smc, 2 hvc), boot MPIDR, the core this thread reports from, the
// scheduler's processor count, then per secondary core its step, failure code and CPU_ON result, IPIs sent and taken;
// the second row has the timer interrupts and IPIs each core took. Empty without sheng-smp, so that report is unchanged.
static char gSmpText[320];
static const char *smpText() {
    if (!&armcpu_smp_requested || !armcpu_smp_requested) return "";
    char st[8], f[8];
    for (unsigned c = 1; c < 8; ++c) {
        st[c - 1] = static_cast<char>('0' + armcpu_smp_step[c] % 10);
        f[c - 1] = static_cast<char>('0' + armcpu_smp_fail[c] % 10);
    }
    st[7] = f[7] = 0;
    const volatile int32_t *rc = armcpu_smp_psci_rc;
    const volatile uint32_t *t = armcpu_core_timer, *i = armcpu_core_sgi;
    snprintf(gSmpText, sizeof gSmpText,
        "\nSMP run%u c%u b%x cpu%d av%u st%s f%s psci%d,%d,%d,%d,%d,%d,%d ipi%llu/%llu"
        "\nSMP tmr%u/%u/%u/%u/%u/%u/%u/%u ipi%u/%u/%u/%u/%u/%u/%u/%u",
        armcpu_smp_running, armcpu_smp_conduit, armcpu_boot_mpidr & 0xffffffu, cpu_number(), processor_avail_count, st, f,
        rc[1], rc[2], rc[3], rc[4], rc[5], rc[6], rc[7],
        static_cast<unsigned long long>(armcpu_ipi_sent), static_cast<unsigned long long>(armcpu_ipi_interrupts),
        t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[7], i[0], i[1], i[2], i[3], i[4], i[5], i[6], i[7]);
    return gSmpText;
}

// The HID digitizer (FuxiHidProbe.cpp, in this archive): started from stage 4 with fuxi-touch-hid=1, reported as one more row.
extern "C" void fuxi_hid_start(void);
extern "C" bool fuxi_hid_settled(void);
extern "C" const char *fuxi_hid_row(char *out, size_t size);
static bool gHidRequested;
static char gHidText[160];
static const char *hidText() {return gHidRequested ? fuxi_hid_row(gHidText, sizeof gHidText) : "";}

// Refreshes the diagnostic rows and prints them to the kernel log.
static void report(const Session &s) {
    rows(s);
    printf("fuxi-touch stage %u/%u\n%s\n%s\n%s\n%s\n", native_touch_stage_done, native_touch_stage_req, native_touch_rows[0],
           native_touch_rows[1], native_touch_rows[2], native_touch_rows[3]);
}

// Reads every queued event, applies it and publishes the contact set when it changed. Returns false on a bus error.
static bool drain(Session &s) {
    for (unsigned round = 0; round < 8; ++round) {
        unsigned count = 0;
        native_touch_loop_step = 2;
        if (fts_read_events(&s.chip, s.events, &count)) {fail(11, FTS_ERR_BUS); return false;}
        ++s.reads;
        if (!count) return true;
        s.drained += count;
        native_touch_valid = native_touch_valid + 1;
        native_touch_loop_step = 3;
        if (fts_touch_apply_events(&s.core, s.events, count)) {
            fts_point pts[FTS_SLOTS];
            const unsigned n = fts_touch_contacts(&s.core, pts, FTS_SLOTS);
            native_touch_contacts = n;
            if (n) {native_touch_last_x = pts[0].x; native_touch_last_y = pts[0].y;}
            native_touch_frames = native_touch_frames + 1;
            publish(s, n, pts);
        }
        if (s.core.reset_needed) {
            // Watchdog, ESD or a reset of its own: reset again and restart sensing, as the driver's error handler does.
            ++s.rearms;
            s.core.reset_needed = 0;
            s.resetRc = fts_reset(&s.chip);
            s.senseRc = fts_start_sensing(&s.chip);
        }
        if (!lineLow(s)) return true;
    }
    return true;
}

static void touchThread(void *, wait_result_t) {
    thread_set_thread_name(current_thread(), "fuxi-touch");
    Session *s = static_cast<Session *>(IOMallocType(Session));
    if (!s) {fail(0, -12); return;}
    bzero(static_cast<void *>(s), sizeof *s);   // IOMallocType runs no constructor: every field starts at zero
    s->idRc = s->resetRc = s->senseRc = 99;
    unsigned stage = native_touch_stage_req, hz = FTB_SPI_HZ, power = 1, tcs = 2, mapFlags = 0, panicReport = 0;
    PE_parse_boot_argn("fuxi-touch-hz", &hz, sizeof hz);
    if (hz < 100000 || hz > FTB_SPI_HZ) hz = FTB_SPI_HZ;
    PE_parse_boot_argn("fuxi-touch-power", &power, sizeof power);
    PE_parse_boot_argn("fuxi-touch-tcs", &tcs, sizeof tcs);
    s->tcs = tcs < kActiveTcs ? tcs : 2;
    PE_parse_boot_argn("fuxi-touch-map", &mapFlags, sizeof mapFlags);
    PE_parse_boot_argn("fuxi-touch-panic", &panicReport, sizeof panicReport);
    s->map = (struct fts_map){FTB_X_MAX, FTB_Y_MAX, kHidXMax, kHidYMax, mapFlags & 7u};
    fts_touch_init(&s->core, 1, FTB_X_MAX, FTB_Y_MAX);
    do {
        if (!snapshot(*s)) break;
        native_touch_stage_done = 1;
        report(*s);
        if (stage < 2) break;
        if (!enable(*s, power != 0)) break;
        native_touch_stage_done = 2;
        report(*s);
        if (stage < 3) break;
        if (!openBus(*s, hz)) break;
        s->tx = static_cast<uint8_t *>(IOMalloc(FTS_XFER_MAX));
        s->rx = static_cast<uint8_t *>(IOMalloc(FTS_XFER_MAX));
        s->events = static_cast<uint8_t *>(IOMalloc(FTS_FIFO_DEPTH * FTS_EVENT_SIZE));
        if (!s->tx || !s->rx || !s->events) {fail(6, -12); break;}
        s->bus = (struct fts_bus){s, busXfer, busDelay, busReset};
        s->chip = {};
        s->chip.bus = &s->bus;
        s->chip.tx = s->tx;
        s->chip.rx = s->rx;
        mark(*s, 7);
        s->resetRc = fts_reset(&s->chip);
        s->idRc = fts_read_chip_id(&s->chip);
        rows(*s);
        if (s->resetRc) {fail(7, s->resetRc); break;}
        if (s->idRc) {fail(8, s->idRc); break;}
        native_touch_stage_done = 3;
        report(*s);
        if (stage < 4) break;
        mark(*s, 9);
        s->senseRc = fts_start_sensing(&s->chip);
        if (s->senseRc) {fail(9, s->senseRc); break;}
        native_touch_stage_done = 4;
        report(*s);
        unsigned hid = 0;
        PE_parse_boot_argn("fuxi-touch-hid", &hid, sizeof hid);
        gHidRequested = hid == 1;
        if (gHidRequested) fuxi_hid_start();   // its own thread: loading IOHIDFamily does not delay the touch loop
        mark(*s, 10);
        unsigned pollOnly = 0;
        PE_parse_boot_argn("fuxi-touch-poll", &pollOnly, sizeof pollOnly);
        const bool irqArmed = !pollOnly && armTouchIrq(*s);
        uint32_t seen = gTouchIrqEvents;
        unsigned tick = 0;
        // With the HID digitizer the run ends at the first lift after its start has settled; otherwise at the first lift.
        bool settled = !gHidRequested;
        uint32_t leavesBefore = 0;
        for (;;) {
            native_touch_loop_step = 1;
            if (irqArmed) {
                // Event driven; a 100 ms timeout re-checks the line in case an edge was missed.
                assert_wait_timeout((event_t)&gTouchIrqEvents, THREAD_UNINT, 100, kMillisecondScale);
                if (gTouchIrqEvents != seen || lineLow(*s)) clear_wait(current_thread(), THREAD_AWAKENED);
                else if (thread_block(THREAD_CONTINUE_NULL) == THREAD_TIMED_OUT) ++s->idleWakes;
                seen = gTouchIrqEvents;
                if (!lineLow(*s)) {if ((++tick & 63) == 0) rows(*s); continue;}
            } else {
                IOSleep(pollOnly ? 8 : 10);
            }
            if (!drain(*s)) break;
            if ((++tick & 15) == 0) rows(*s);
            if (!settled && fuxi_hid_settled()) {settled = true; leavesBefore = s->core.leaves;}
            if (panicReport == 2 && settled && s->core.leaves > leavesBefore) break;   // one complete touch seen: report it
        }
    } while (0);
    report(*s);
    if (panicReport) {
        panic("fuxi-touch report (stage %u of %u)\n%s\n%s\n%s\n%s%s%s", native_touch_stage_done, native_touch_stage_req,
              native_touch_rows[0], native_touch_rows[1], native_touch_rows[2], native_touch_rows[3], smpText(), hidText());
    }
}

extern "C" void native_touch_probe(void) {
    unsigned stage = 0;
    if (!PE_parse_boot_argn("fuxi-touch", &stage, sizeof stage) || stage < 1 || native_touch_stage_req) return;
    if (stage > 4) stage = 4;
    native_touch_stage_req = stage;
    thread_t thread = nullptr;
    if (kernel_thread_start(touchThread, nullptr, &thread) == KERN_SUCCESS) thread_deallocate(thread);
    else native_touch_error = -12;
}
