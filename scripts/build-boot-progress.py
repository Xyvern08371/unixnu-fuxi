#!/usr/bin/env python3
"""Build the fuxi boot-progress backend and the Sheng launchd watchdog policy.

The real BootProgress.c supplies the scanout/prepare/cancel hooks the legacy
display backend calls, and BootWatchdogPolicy.c supplies the Sheng
launchd-isolation policy.
"""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/boot-progress'
OUT.mkdir(parents=True, exist_ok=True)

policy_record = json.loads((ROOT / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/bsd/DEVELOPMENT/kern_exec.o.json')
                           .read_text().strip().rstrip(','))
shim_record = json.loads((ROOT / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/osfmk/DEVELOPMENT/startup.o.json')
                         .read_text().strip().rstrip(','))


def compile_like(record, source, destination, extra):
    command, index = [], 0
    arguments = record['arguments']
    while index < len(arguments):
        value = arguments[index]
        if value == record['file']:
            command.append(str(source))
        elif value == '-o':
            command += ['-o', str(destination)]
            index += 1
        elif value in ('-MF', '-MT', '-MJ'):
            index += 1
        elif value == '-Xclang' and arguments[index + 1].startswith('-W'):
            index += 1
        elif value == '-D' and arguments[index + 1].startswith('XNU_BOOT_PROGRESS='):
            index += 1
        elif value.startswith('-DXNU_BOOT_PROGRESS='):
            pass
        elif not value.startswith('-W'):
            command.append(value)
        index += 1
    # The driver builds the archive before the pass that force-loads it, so the records replayed
    # here come from the bootstrap pass, which is pinned to XNU_BOOT_PROGRESS=0. Only the enabled
    # pass links this archive, so the hooks must be compiled as the real implementations.
    command += ['-DXNU_BOOT_PROGRESS=1']
    command += extra
    subprocess.run(command, cwd=record['directory'], check=True, timeout=90)
    return destination


policy_source = ROOT / 'kits/fuxi/BootWatchdogPolicy.c'
policy_obj = compile_like(policy_record, policy_source, OUT / 'BootWatchdogPolicy.o',
                          ['-mgeneral-regs-only', '-Wall', '-Wextra', '-Werror'])
progress_source = ROOT / 'kits/fuxi/BootProgress.c'
progress_obj = compile_like(shim_record, progress_source, OUT / 'BootProgress.o',
                            ['-mgeneral-regs-only', '-Wall', '-Wextra', '-Werror',
                             '-I', str(ROOT / '.cache/xnu-work/osfmk')])
fault_source = ROOT / 'kits/fuxi/BootFaultProbe.c'
fault_obj = compile_like(shim_record, fault_source, OUT / 'BootFaultProbe.o',
                          ['-mgeneral-regs-only', '-Wall', '-Wextra', '-Werror',
                           '-I', str(ROOT / '.cache/xnu-work/osfmk')])
stubs_source = ROOT / 'kits/fuxi/BootProgressStubs.c'
stubs_obj = compile_like(shim_record, stubs_source, OUT / 'BootProgressStubs.o',
                          ['-mgeneral-regs-only', '-Wall', '-Wextra', '-Werror',
                           '-I', str(ROOT / '.cache/xnu-work/osfmk')])

archive = OUT / 'libBootProgress.a'
archive.unlink(missing_ok=True)
subprocess.run(['xcrun', 'ar', 'rcs', str(archive), str(policy_obj), str(progress_obj), str(fault_obj),
                str(stubs_obj)],
               check=True, timeout=30)
(OUT / 'build-report.json').write_text(json.dumps({
    'watchdog_policy_sha256': hashlib.sha256(policy_source.read_bytes()).hexdigest(),
    'progress_sha256': hashlib.sha256(progress_source.read_bytes()).hexdigest(),
    'fault_sha256': hashlib.sha256(fault_source.read_bytes()).hexdigest(),
    'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
    'hardware_execution': False,
}, indent=2) + '\n')
print('PASS: fuxi boot-progress backend and Sheng launchd watchdog policy build')
