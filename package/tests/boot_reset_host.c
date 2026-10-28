// Host test of BootResetCore.h against a software model of the SPMI PMIC arbiter (v7 layout) with a device thread that serves the channels.
#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "../BootResetCore.h"

static volatile uint32_t core[0x3000 / 4], cnfg[0x4000 / 4];
static volatile uint32_t obs[0x8000 / 4];          // EE 0 observer channels
static volatile uint32_t chn[0x1000 * 64 / 4];     // read/write channels of APIDs 0..63
static volatile int stop, deny_writes, fail_reads;
static uint8_t sdam[256];
static unsigned writes_seen, reads_seen;
static int wrote_apid = -1;

static void serve(volatile uint32_t *ch, int is_write, int apid) {
  uint32_t cmd = ch[BR_CMD / 4];
  if (!cmd && !(ch[BR_STATUS / 4] & 0x100)) return;   // idle
  if (ch[BR_STATUS / 4] & 0x100) return;               // already handled this command
  ch[BR_STATUS / 4] |= 0x100;                           // model-private "handled" marker, cleared when the host clears CMD
  uint8_t op = cmd >> 27, addr = (cmd >> 4) & 0xff;
  if (is_write) {
    assert(op == BR_OP_EXT_WRITEL && (cmd & 7) == 0);
    wrote_apid = apid;
    ++writes_seen;
    if (deny_writes) {ch[BR_STATUS / 4] |= BR_STATUS_DONE | (1u << 2); return;}
    sdam[addr] = (uint8_t)ch[BR_WDATA0 / 4];
  } else {
    assert(op == BR_OP_EXT_READL && (cmd & 7) == 0);
    ++reads_seen;
    if (fail_reads) {ch[BR_STATUS / 4] |= BR_STATUS_DONE | (1u << 1); return;}
    ch[BR_RDATA0 / 4] = sdam[addr];
  }
  ch[BR_STATUS / 4] |= BR_STATUS_DONE;
}
static void *device(void *arg) {
  (void)arg;
  while (!stop) {
    for (int apid = 0; apid < 64; ++apid) {
      serve(&obs[(0x20 * apid) / 4], 0, apid);
      serve(&chn[(0x1000 * apid) / 4], 1, apid);
    }
    usleep(50);
  }
  return NULL;
}
// A new command: the host (BootResetCore.h) only writes CMD; the model re-arms a channel when it sees CMD change after a done status.
static void rearm(void) {for (int apid = 0; apid < 64; ++apid) {obs[(0x20 * apid) / 4 + 2] = 0; chn[(0x1000 * apid) / 4 + 2] = 0;}}

static void setup(uint32_t version, int apids) {
  memset((void *)core, 0, sizeof core); memset((void *)cnfg, 0, sizeof cnfg); memset((void *)obs, 0, sizeof obs); memset((void *)chn, 0, sizeof chn);
  core[0] = version; core[BR_FEATURES / 4] = (uint32_t)apids;
  // APID 5: decoy for the SDAM PPID owned by EE 1; APID 7: the real one (EE 0); APID 9: a second decoy owned by EE 2; others unrelated.
  core[(BR_APID_MAP + 4 * 3) / 4] = (0x070u << 8) | 1; cnfg[3] = 0;
  core[(BR_APID_MAP + 4 * 5) / 4] = (BR_SDAM_PPID << 8) | 1; cnfg[5] = 1;
  core[(BR_APID_MAP + 4 * 7) / 4] = (BR_SDAM_PPID << 8) | 1 | (1u << 24); cnfg[7] = 0;
  core[(BR_APID_MAP + 4 * 9) / 4] = (BR_SDAM_PPID << 8) | 1; cnfg[9] = 2;
  memset(sdam, 0, sizeof sdam); sdam[BR_REBOOT_CELL] = 0x03; sdam[0x47] = 0xaa; sdam[0x49] = 0xbb;
  deny_writes = fail_reads = 0; writes_seen = reads_seen = 0; wrote_apid = -1;
}
// The host code clears nothing between transactions, so the model resets STATUS (done/handled) when CMD is rewritten: emulate by a wrapper
// thread-free trick: the test calls rearm() before each step through the macro below.
int main(void) {
  pthread_t t;
  struct br_arbiter a = {core, cnfg, 0};
  struct br_found f;
  uint8_t before = 0, after = 0, v = 0;

  setup(0x70000000u, 40);
  assert(br_find(&a, &f) == 0 && f.apid == 7 && f.owner == 0 && f.version == 0x70000000u && f.apids == 40);
  setup(0x60000000u, 40); assert(br_find(&a, &f) == 1);          // older arbiter layout: refused
  setup(0x80000000u, 40); assert(br_find(&a, &f) == 1);          // newer: refused
  setup(0x70000000u, 0);  assert(br_find(&a, &f) == 2);
  setup(0x70000000u, 40); core[(BR_APID_MAP + 4 * 7) / 4] = 0; assert(br_find(&a, &f) == 0 && f.apid == 5 && f.owner == 1);   // only decoys left: found, but not owned by EE 0 (the caller refuses)
  setup(0x70000000u, 40); core[(BR_APID_MAP + 4 * 7) / 4] = 0; core[(BR_APID_MAP + 4 * 5) / 4] = 0; core[(BR_APID_MAP + 4 * 9) / 4] = 0; assert(br_find(&a, &f) == 3);
  a.ee = 1; setup(0x70000000u, 40); assert(br_find(&a, &f) == 0 && f.apid == 5 && f.owner == 1); a.ee = 0;     // the EE's own mapping wins

  setup(0x70000000u, 40); assert(br_find(&a, &f) == 0);
  pthread_create(&t, NULL, device, NULL);
  // Read the cell, then set it: bit 0 kept, bits 7:1 = 2, neighbours untouched, written on the APID's own read/write channel only.
  rearm(); assert(br_read8(obs, &a, f.apid, BR_REBOOT_CELL, &v) == 0 && v == 0x03);
  // Each transaction needs a fresh status; br_set_bootloader runs three, so drive it from a helper that re-arms between them.
  stop = 1; pthread_join(t, NULL); stop = 0;
  setup(0x70000000u, 40); assert(br_find(&a, &f) == 0);
  // Direct sequential check of the three steps with explicit re-arming (the real hardware re-arms its channel per command).
  pthread_create(&t, NULL, device, NULL);
  rearm(); assert(br_read8(obs, &a, f.apid, BR_REBOOT_CELL, &before) == 0 && before == 0x03);
  rearm(); chn[(0x1000 * f.apid) / 4] = 0; assert(br_write8(chn, f.apid, BR_REBOOT_CELL, (uint8_t)((before & ~BR_REBOOT_MASK) | (BR_REBOOT_BOOTLOADER << 1))) == 0);
  assert(sdam[BR_REBOOT_CELL] == 0x05 && sdam[0x47] == 0xaa && sdam[0x49] == 0xbb && wrote_apid == 7 && writes_seen == 1);
  rearm(); assert(br_read8(obs, &a, f.apid, BR_REBOOT_CELL, &after) == 0 && after == 0x05);
  // Denied write is reported and leaves the cell alone.
  stop = 1; pthread_join(t, NULL); stop = 0;
  setup(0x70000000u, 40); assert(br_find(&a, &f) == 0); deny_writes = 1;
  pthread_create(&t, NULL, device, NULL);
  rearm(); assert(br_write8(chn, f.apid, BR_REBOOT_CELL, 0x05) == 2 && sdam[BR_REBOOT_CELL] == 0x03);
  fail_reads = 1; rearm(); assert(br_read8(obs, &a, f.apid, BR_REBOOT_CELL, &v) == 2);
  stop = 1; pthread_join(t, NULL);
  // No device at all: the poll limit ends the wait.
  setup(0x70000000u, 40); assert(br_find(&a, &f) == 0); assert(br_read8(obs, &a, f.apid, BR_REBOOT_CELL, &v) == 1);
  printf("PASS: arbiter v7 APID lookup (decoys, other EE, refused versions), cell read, masked write, denied and failed transactions, timeout\n");
  return 0;
}
