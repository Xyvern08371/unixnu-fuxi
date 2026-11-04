// SPDX-License-Identifier: BSD-2-Clause-Patent
// Starts the touch digitizer of ShengHidInput (NativeHidInput.cpp, an unchanged copy of UniXNU ShengHidInput 71a40e7) for the
// fuxi touch probe and provides the three board functions it calls. It follows UniXNU-sheng package/HidInputProbe.cpp
// (native_hid_input_probe, native_hid_live_checkpoint) without sheng's display hooks and Home-button automation: fuxi has
// no button driver, so only the touch-only device (native_hid_touch_allocate) is created. FuxiTouchProbe.cpp calls
// fuxi_hid_start once sensing runs, with the boot argument fuxi-touch-hid=1; the device then turns every contact set the
// probe publishes into a digitizer report (native_touch_hid_reports, the hid counter of the touch report).
#include <IOKit/IOService.h>
#include <IOKit/IOLib.h>
#include <libkern/libkern.h>
#include <libkern/c++/OSMetaClass.h>
#include <libkern/c++/OSSymbol.h>
#include <libkern/c++/OSIterator.h>
#include <libkern/c++/OSKext.h>
#include <kern/thread.h>
#include <pexpert/pexpert.h>
#include <mach/kmod.h>

extern kmod_info_t g_kernel_kmod_info;
// NativeHidInput's static initializer. scripts/build-fuxi-hid-input.py takes it out of __mod_init_func: the metaclass it
// registers derives from IOHIDDevice, which exists only once IOHIDFamily is loaded.
extern "C" void native_hid_static_init(void) __asm__("__GLOBAL__sub_I_NativeHidInput.cpp");
extern "C" IOService *native_hid_touch_allocate(void);
extern "C" {
extern kern_return_t OSKextLoadKextWithIdentifier(const char *);
// [0] step reached (1 IOHIDFamily, 2 IOHIDEventDriver, 3 IOHIDResource, 4 metaclass, 5 device, 6 started), [1] IOHIDFamily
// load result, [2] IOHIDEventDriver load result, [3] IOHIDDevice instance size (208 expected), [4] IOHIDResource found,
// [5] postModLoad result, [6] device (1 allocated, 2 initialized, 3 attached, 4 started), [7] step that failed (0 none).
volatile int fuxi_hid_state[8] = {0, -1, -1, 0, 0, -1, 0, 0};
// native_hid_input_observed: how often each event happened and its last result (2 device started, 6 touch report).
volatile uint32_t native_hid_input_events[8];
volatile int native_hid_input_results[8] = {-1, -1, -1, -1, -1, -1, -1, -1};
volatile uint32_t fuxi_hid_driver;   // 1 once an IOHIDEventDriver is attached below the device
extern volatile uint32_t native_touch_edge_stats[4];   // NativeHidInput: [0] edge wrapper installed
}

extern "C" bool native_hid_input_requested(void) {return false;}   // no Home presses: the combined device is not created

// The combined device would register here for the hardware buttons. fuxi has no button driver and creates only the touch-only
// device, but the kernel is linked statically, so NativeHidInput's weak import still needs a definition (run 41437861526
// stopped at the link without it). The sink is accepted and never called.
extern "C" void native_buttons_set_sink(void (*)(void *, uint32_t), void *) {}

extern "C" void native_hid_input_observed(unsigned event, int result) {
    if (event < 8) {native_hid_input_events[event] = native_hid_input_events[event] + 1; native_hid_input_results[event] = result;}
}

static IORegistryEntry *findEventDriver(IORegistryEntry *parent, unsigned depth) {
    if (!depth) return nullptr;
    OSIterator *it = parent->getChildIterator(gIOServicePlane);
    if (!it) return nullptr;
    IORegistryEntry *found = nullptr;
    while (OSObject *child = it->getNextObject()) {
        IORegistryEntry *entry = OSDynamicCast(IORegistryEntry, child);
        if (!entry) continue;
        if (entry->metaCast("IOHIDEventDriver")) {found = entry; break;}
        if ((found = findEventDriver(entry, depth - 1))) break;
    }
    it->release();
    return found;
}

// Called by the device's timer once a second. As on sheng, backboardd classifies a digitizer by Built-In, DisplayIntegrated
// and the primary usage (Digitizer, Touch Screen) of the event service it opened, so they are published on the event driver
// and its interface once, after the driver has matched (on the device they would change the matching).
extern "C" __attribute__((noinline)) void native_hid_live_checkpoint(IOService *device) {
    IORegistryEntry *driver = findEventDriver(device, 4);
    if (!driver) return;
    fuxi_hid_driver = 1;
    static IORegistryEntry *publishedFor;
    if (!device->getProperty("Built-In") || publishedFor == driver) return;
    publishedFor = driver;
    IORegistryEntry *entries[2] = {driver, driver->getParentEntry(gIOServicePlane)};
    for (IORegistryEntry *entry : entries) {
        if (!entry) continue;
        entry->setProperty("Built-In", kOSBooleanTrue);
        entry->setProperty("DisplayIntegrated", kOSBooleanTrue);
        entry->setProperty("PrimaryUsagePage", 0x0dULL, 32);
        entry->setProperty("PrimaryUsage", 4ULL, 32);
    }
}

static void startThread(void *, wait_result_t) {
    thread_set_thread_name(current_thread(), "fuxi-hid");
    volatile int *st = fuxi_hid_state;
    st[0] = 1;
    st[1] = OSKextLoadKextWithIdentifier("com.apple.iokit.IOHIDFamily");
    if (st[1]) {st[7] = 1; return;}
    st[0] = 2;
    st[2] = OSKext::loadKextWithIdentifier("com.apple.iokit.IOHIDEventDriver", true, false, kOSKextExcludeNone,
                                           kOSKextExcludeNone, nullptr);
    // The generated OriginalHidDeviceABI.h describes an IOHIDDevice of 208 bytes; any other family is left alone.
    const OSSymbol *name = OSSymbol::withCString("IOHIDDevice");
    const OSMetaClass *meta = name ? OSMetaClass::getMetaClassWithName(name) : nullptr;
    st[3] = meta ? static_cast<int>(meta->getClassSize()) : 0;
    OSSafeReleaseNULL(name);
    if (st[3] != 208) {st[7] = 2; return;}
    st[0] = 3;
    OSDictionary *match = IOService::serviceMatching("IOHIDResource");
    IOService *resource = match ? IOService::waitForMatchingService(match, 5000000000ULL) : nullptr;
    OSSafeReleaseNULL(match);
    st[4] = resource != nullptr;
    if (!resource) {st[7] = 3; return;}
    st[0] = 4;
    void *handle = OSMetaClass::preModLoad(g_kernel_kmod_info.name);
    if (handle) {native_hid_static_init(); st[5] = OSMetaClass::postModLoad(handle);}
    if (!handle || st[5]) {st[7] = 4; resource->release(); return;}
    st[0] = 5;
    IOService *device = native_hid_touch_allocate();
    bool ok = device && device->metaCast("IOHIDDevice");
    if (ok) {st[6] = 1; ok = device->init();}
    if (ok) {st[6] = 2; ok = device->attach(resource);}
    if (ok) {
        st[6] = 3;
        if (device->start(resource)) {st[6] = 4; st[0] = 6;}
        else {device->detach(resource); ok = false;}
    }
    if (!ok) {st[7] = 5; OSSafeReleaseNULL(device);}
    // As on sheng, a started device keeps this reference for the rest of the boot.
    resource->release();
}

static uint64_t counter(void) {uint64_t v; __asm__ volatile("isb\n\tmrs %0, cntvct_el0" : "=r"(v)); return v;}
static uint64_t gStartCount;   // the counter when fuxi_hid_start ran

extern "C" void fuxi_hid_start(void) {
    static bool started;
    if (__atomic_exchange_n(&started, true, __ATOMIC_ACQ_REL)) return;
    gStartCount = counter();
    thread_t thread = nullptr;
    if (kernel_thread_start(startThread, nullptr, &thread) == KERN_SUCCESS) thread_deallocate(thread);
    else fuxi_hid_state[7] = 9;
}

// The start has come to an end: the device runs and an event driver has attached, a step failed, or 20 s have passed. The
// touch probe ends its run only at a lift after this, so that the touch it reports went through the HID device.
extern "C" bool fuxi_hid_settled(void) {
    if (fuxi_hid_state[7] || (fuxi_hid_state[0] == 6 && fuxi_hid_driver)) return true;
    uint64_t frequency;
    __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(frequency));
    return gStartCount && counter() - gStartCount > 20 * frequency;
}

// One report row: step and failed step, the two load results, the IOHIDDevice size, the resource, the metaclass registration,
// the device's progress, whether an event driver attached, the device's start count, the reports sent with the last result,
// and whether the edge wrapper was installed on the event driver.
extern "C" const char *fuxi_hid_row(char *out, size_t size) {
    const volatile int *st = fuxi_hid_state;
    snprintf(out, size, "\nHID st%d f%d fam%x evd%x sz%d res%d meta%x dev%d drv%u up%u rep%u/%x edge%u",
             st[0], st[7], static_cast<unsigned>(st[1]), static_cast<unsigned>(st[2]), st[3], st[4], static_cast<unsigned>(st[5]),
             st[6], fuxi_hid_driver, native_hid_input_events[2], native_hid_input_events[6],
             static_cast<unsigned>(native_hid_input_results[6]), native_touch_edge_stats[0]);
    return out;
}
