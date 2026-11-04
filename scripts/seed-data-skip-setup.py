#!/usr/bin/env python3
"""Make a Data seed that boots to SpringBoard instead of Setup: the preference changes github.com/dipa-studio/ios-sweet
(tools/sweet-root-tweaks.py) established on hardware, applied to a copy of an existing packed Data seed.

  seed-data-skip-setup.py BASE.dbr OUTPUT.dbr

BASE is a DBRDISK1 packed APFS container (drivers/DarwinBoot/Test/packed_ramdisk.py format). It is expanded to a raw image, attached
read-write on this Mac, the preference files below are merged into /private/var/mobile/Library/Preferences, and the result is packed
again. The volume UUID is unchanged. Nothing is written to Git or to the OS inputs; BASE is not modified.
  com.apple.purplebuddy            SetupDone, SetupFinishedAllSteps, SetupVersion 11, daemonizeNeedsToRun false   (skips Setup)
  com.apple.purplebuddy.notbackedup  the mini-buddy flags false
  com.apple.managedconfiguration.notbackedup  LockdownActivationIndicatesCloudConfigurationAvailable false
  com.apple.springboard            BKNoWatchdogs, FBLaunchWatchdogExceptions{com.apple.purplebuddy: 100}, MCForceShowCloudConfigurationUI false
  com.apple.migration              LastSystemVersion (no data migration on every boot)
and the container directories under /private/var/containers that on a device live on the data volume.
"""
import hashlib, json, os, plistlib, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'drivers/DarwinBoot/Test'))
import packed_ramdisk

BUILD, VERSION = '21H461', '17.7.11'
MOBILE = 501

def merge_pref(var, name, values):
    path = var / 'mobile/Library/Preferences' / (name + '.plist')
    path.parent.mkdir(parents=True, exist_ok=True)
    data = plistlib.loads(path.read_bytes()) if path.exists() else {}
    data.update(values)
    path.write_bytes(plistlib.dumps(data, fmt=plistlib.FMT_BINARY))
    os.chmod(path, 0o600)
    print('pref', name, sorted(values))

def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    base, output = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    if output.exists():
        sys.exit('Refuse to overwrite ' + str(output))
    blob = base.read_bytes()
    logical, extents = packed_ramdisk.regions(blob)
    with tempfile.TemporaryDirectory(prefix='data-seed-', dir=str(ROOT / 'build')) as td:
        raw = Path(td) / 'seed.raw'
        with raw.open('wb') as f:
            f.truncate(logical)
            for offset, data in extents:
                f.seek(offset)
                f.write(data)
        mount = Path(td) / 'mount'
        mount.mkdir()
        attached = plistlib.loads(subprocess.check_output(
            ['hdiutil', 'attach', '-imagekey', 'diskimage-class=CRawDiskImage', '-nobrowse', '-owners', 'off',
             '-mountpoint', str(mount), '-plist', str(raw)]))
        device = attached['system-entities'][0]['dev-entry']
        try:
            if not (mount / 'mobile').is_dir():
                sys.exit('The Data seed has no /mobile; wrong base image?')
            # 不写 LastSystemVersion：让 SystemAppMigrator 正常跑首启数据迁移，
            # 从而把内核 staged-apps（sheng-staged-apps=1）拷贝进 Data 卷的可删除系统应用
            # 安装到 /Applications。只保留 SyntheticDidUpgrade=False（不合成升级）。
            merge_pref(mount, 'com.apple.migration', {
                'DMUserDataDisposition': {'SyntheticDidUpgrade': False, 'buildVersion': BUILD}})
            merge_pref(mount, 'com.apple.springboard', {
                'BKNoWatchdogs': True,
                'FBLaunchWatchdogExceptions': {'com.apple.purplebuddy': 100.0},
                'MCForceShowCloudConfigurationUI': False})
            merge_pref(mount, 'com.apple.purplebuddy', {
                'SetupDone': True, 'SetupFinishedAllSteps': True, 'SetupVersion': 11, 'daemonizeNeedsToRun': False})
            merge_pref(mount, 'com.apple.purplebuddy.notbackedup', {
                k: False for k in ('ShouldRunDiagnosticsMiniBuddy', 'ShouldRunHSA2MiniBuddy', 'ShouldRunKeychainSyncMiniBuddy',
                                   'ShouldRunMesaMiniBuddy', 'ShouldRunPaymentMiniBuddy', 'ShouldRunStandardMiniBuddy',
                                   'SilentICDPUpgrade')})
            merge_pref(mount, 'com.apple.managedconfiguration.notbackedup', {
                'LockdownActivationIndicatesCloudConfigurationAvailable': False})
            for sub in ('Bundle', 'Data/System', 'Shared/SystemGroup', 'Temp'):
                d = mount / 'containers' / sub
                if not d.is_dir():
                    d.mkdir(parents=True)
                    os.chmod(d, 0o755)
                    print('mkdir', d.relative_to(mount))
        finally:
            subprocess.run(['hdiutil', 'detach', device], check=True)
        if raw.read_bytes()[32:36] != b'NXSB':
            sys.exit('The edited image is no APFS container any more')
        metadata = packed_ramdisk.pack(raw, output)
    report = dict(base_sha256=packed_ramdisk.inspect(base)[0]['sha256'], output=metadata,
                  preferences=['com.apple.migration', 'com.apple.springboard', 'com.apple.purplebuddy',
                               'com.apple.purplebuddy.notbackedup', 'com.apple.managedconfiguration.notbackedup'],
                  build=BUILD, source='github.com/dipa-studio/ios-sweet tools/sweet-root-tweaks.py')
    output.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
