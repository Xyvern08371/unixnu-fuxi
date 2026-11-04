// SPDX-License-Identifier: MIT
// Best-effort CrashReporter snapshot for the UFS log. Runs on the boot-log
// thread every few rounds and copies the newest .ips from the Data volume
// into the tail of the export region, where UEFI's UFS Log reads SHCRASH01.
//
// Compiled in the BSD source context because directory walking needs
// vnode/uio; BootLog.c stays in the osfmk context and only owns the storage
// window.
#include "BootCrashExport.h"

#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <sys/dirent.h>
#include <sys/errno.h>
#include <sys/fcntl.h>
#include <sys/uio.h>
#include <sys/vnode.h>
#include <sys/vnode_internal.h>
#include <IOKit/IOLib.h>

#define BOOT_CRASH_DIRECTORY "/private/var/mobile/Library/Logs/CrashReporter"
#define BOOT_CRASH_ENTRIES_SIZE (64u * 1024u)
#define BOOT_CRASH_MAX_FILE_BYTES (4u * 1024u * 1024u)

void boot_log_crash_collect(void) {
  vfs_context_t ctx = vfs_context_current();
  vnode_t dir = NULLVP;
  int error = vnode_lookup(BOOT_CRASH_DIRECTORY, VNODE_LOOKUP_NOFOLLOW, &dir, ctx);
  if (error) return;
  if (vnode_vtype(dir) != VDIR) {vnode_put(dir); return;}
  error = VNOP_OPEN(dir, FREAD, ctx);
  if (error) {vnode_put(dir); return;}

  uint8_t *entries = (uint8_t *)IOMallocAligned(BOOT_CRASH_ENTRIES_SIZE, 4096);
  uint8_t *payload = (uint8_t *)IOMallocAligned(BOOT_CRASH_MAX_FILE_BYTES, 4096);
  char selected[256]; selected[0] = 0;
  uint64_t selected_time = 0, selected_size = 0;
  int found = 0;
  if (entries && payload) {
    off_t offset = 0;
    for (int eof = 0; !error && !eof;) {
      uio_t uio = uio_create(1, offset, UIO_SYSSPACE, UIO_READ);
      if (!uio) {error = ENOMEM; break;}
      uio_addiov(uio, CAST_USER_ADDR_T(entries), BOOT_CRASH_ENTRIES_SIZE);
      int count = 0;
      error = vnode_readdir64(dir, uio, VNODE_READDIR_EXTENDED, &eof, &count, ctx);
      const uint32_t filled = BOOT_CRASH_ENTRIES_SIZE - (uint32_t)uio_resid(uio);
      offset = uio_offset(uio);
      uio_free(uio);
      if (error || !filled) break;
      for (uint32_t at = 0; at + offsetof(struct direntry, d_name) < filled;) {
        struct direntry *entry = (struct direntry *)(entries + at);
        if (!entry->d_reclen || at + entry->d_reclen > filled) {error = EINVAL; break;}
        at += entry->d_reclen;
        const char *name = entry->d_name;
        if (!entry->d_ino || !strcmp(name, ".") || !strcmp(name, "..")) continue;
        const size_t n = strlen(name);
        if (n < 5 || strcmp(name + n - 4, ".ips")) continue;
        vnode_t child = NULLVP;
        int child_error = vnode_lookupat(name, VNODE_LOOKUP_NOFOLLOW | VNODE_LOOKUP_NOCROSSMOUNT, &child, ctx, dir);
        if (child_error) continue;
        if (vnode_vtype(child) == VREG) {
          struct vnode_attr va;
          VATTR_INIT(&va);
          VATTR_WANTED(&va, va_data_size);
          VATTR_WANTED(&va, va_modify_time);
          child_error = vnode_getattr(child, &va, ctx);
          if (!child_error && va.va_data_size) {
            const uint64_t t = (uint64_t)va.va_modify_time.tv_sec * 1000000000ull + (uint64_t)va.va_modify_time.tv_nsec;
            if (!found || t > selected_time) {
              strlcpy(selected, name, sizeof selected);
              selected_time = t; selected_size = (uint64_t)va.va_data_size; found = 1;
            }
          }
        }
        vnode_put(child);
      }
    }
  }

  const char *stored_name = boot_log_crash_current_name();
  uint32_t stored_bytes = boot_log_crash_current_bytes();
  if (found && (strcmp(selected, stored_name) || selected_size != stored_bytes)) {
    if (selected_size > BOOT_CRASH_MAX_FILE_BYTES) selected_size = BOOT_CRASH_MAX_FILE_BYTES;
    vnode_t child = NULLVP;
    error = vnode_lookupat(selected, VNODE_LOOKUP_NOFOLLOW | VNODE_LOOKUP_NOCROSSMOUNT, &child, ctx, dir);
    if (!error && vnode_vtype(child) == VREG) {
      error = VNOP_OPEN(child, FREAD, ctx);
      if (!error) {
        memset(payload, 0, BOOT_CRASH_MAX_FILE_BYTES);
        int resid = 0;
        error = vn_rdwr(UIO_READ, child, (caddr_t)payload, (int)selected_size, 0, UIO_SYSSPACE, IO_NOAUTH,
                        vfs_context_ucred(ctx), &resid, vfs_context_proc(ctx));
        VNOP_CLOSE(child, FREAD, ctx);
        if (!error && resid >= 0 && (uint64_t)resid < selected_size) {
          boot_log_crash_store(selected, payload, (uint32_t)(selected_size - (uint64_t)resid));
        }
      }
    }
    if (child != NULLVP) vnode_put(child);
  }

  if (entries) IOFreeAligned(entries, BOOT_CRASH_ENTRIES_SIZE);
  if (payload) IOFreeAligned(payload, BOOT_CRASH_MAX_FILE_BYTES);
  VNOP_CLOSE(dir, FREAD, ctx);
  vnode_put(dir);
}
