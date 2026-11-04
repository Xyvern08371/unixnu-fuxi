#!/usr/bin/env python3
"""Build the fuxi UFS diagnostic log writer archive (package/BootLog.c).

The patched kernel (patches/xnu/zzzc-boot-log.patch) calls boot_log_tick() once
after the clock service is created. boot_log_tick parses sheng-log=1 and starts
the writer thread, which then waits for NativeUfs to publish the root layout and
writes the kernel message buffer plus the boot-progress text into the last 32 MiB
of userdata (read back with package/linux-log + scripts/read-sheng-log.py).

BootLog.c is compiled like the osfmk startup object. BootCrashExport.c walks
the Data volume's CrashReporter directory, so it is compiled like
bsd/kern_exec.c and archived next to the writer.
"""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/boot-log'
OUT.mkdir(parents=True, exist_ok=True)

record = json.loads((ROOT / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/osfmk/DEVELOPMENT/startup.o.json')
                    .read_text().strip().rstrip(','))
crash_record = json.loads((ROOT / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/bsd/DEVELOPMENT/kern_exec.o.json')
                          .read_text().strip().rstrip(','))

def compile_like(record, source, obj, extra=()):
    command = []
    args = record['arguments']
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == record['file']:
            command.append(str(source))
        elif arg in ('-o', '-MF', '-MT', '-MJ'):
            if arg == '-o':
                command += ['-o', str(obj)]
            i += 1
        elif arg == '-Xclang' and args[i + 1].startswith('-W'):
            i += 1
        elif not arg.startswith('-W'):
            command.append(arg)
        i += 1
    command += ['-Wall', '-Wextra', '-Werror', '-mgeneral-regs-only']
    command += list(extra)
    subprocess.run(command, cwd=record['directory'], check=True, timeout=120)
    return obj

log_obj = compile_like(record, ROOT / 'kits/fuxi/BootLog.c', OUT / 'BootLog.o',
                       ['-I', str(ROOT / '.cache/xnu-work/osfmk'),
                        '-I', str(ROOT / 'kits/fuxi')])
crash_obj = compile_like(crash_record, ROOT / 'kits/fuxi/BootCrashExport.c', OUT / 'BootCrashExport.o',
                         ['-I', str(ROOT / 'kits/fuxi')])
touch_stats_obj = compile_like(record, ROOT / 'kits/fuxi/BootLogTouchStats.c', OUT / 'BootLogTouchStats.o',
                               [])
fence_stub_obj = compile_like(record, ROOT / 'kits/fuxi/BootLogFenceStubs.c', OUT / 'BootLogFenceStubs.o',
                              [])
# BootLogStubs provides placeholder definitions for every diagnostic-page
# global BootLog.c composes (boot_progress_*, native_adreno_*, native_dpu_*,
# native_touch_*, native_data_persist_*, boot_reset_*, ...) until the real
# drivers are linked. Without it the stage-1 kernel cannot link BootLog.
stubs_obj = compile_like(record, ROOT / 'kits/fuxi/BootLogStubs.c', OUT / 'BootLogStubs.o',
                         ['-I', str(ROOT / 'kits/fuxi')])
# BootLogExtraStubs supplies fuxi_buttons_stats, native_process_wait_port and
# native_data_persist_* until those real sources are linked.
extra_stubs_obj = compile_like(record, ROOT / 'kits/fuxi/BootLogExtraStubs.c', OUT / 'BootLogExtraStubs.o',
                               ['-I', str(ROOT / 'kits/fuxi')])

archive = OUT / 'libBootLog.a'
archive.unlink(missing_ok=True)
subprocess.run(['xcrun', 'ar', 'rcs', str(archive), str(log_obj), str(crash_obj), str(touch_stats_obj),
                str(fence_stub_obj), str(stubs_obj), str(extra_stubs_obj)],
               check=True, timeout=30)
print(f'boot log archive: {archive}')
