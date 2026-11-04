// Shared interface between the UFS boot-log writer (BootLog.c) and the
// CrashReporter directory walker (BootCrashExport.c). The walker is compiled
// in the BSD source context because it uses vnode/uio APIs; the writer stays
// in the osfmk context where it has NativeUfs and IOKit.
#ifndef BOOT_CRASH_EXPORT_H
#define BOOT_CRASH_EXPORT_H

#include <stdint.h>

int boot_log_crash_store(const char *name, const uint8_t *data, uint32_t bytes);
const char *boot_log_crash_current_name(void);
uint32_t boot_log_crash_current_bytes(void);
void boot_log_crash_collect(void);

#endif
