// Link fallback for the Adreno740 fence-event ring.
//
// package/BootLog.c (upstream diagnostic) reads native_adreno_fence_events,
// which the pinned Adreno740 submodule does not define yet. BootLog gates the
// [fence] rows on the count, so weak zero definitions keep the kernel link and
// leave those rows empty; a newer Adreno740 overrides them.
#include <stdint.h>

volatile uint32_t native_adreno_fence_events[32][4] __attribute__((weak));
volatile uint32_t native_adreno_fence_events_count __attribute__((weak));
