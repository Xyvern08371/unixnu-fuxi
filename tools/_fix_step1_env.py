import io
import yaml

p = r"E:\ios-on-fuxi\.github\workflows\build-xnu-macos.yml"
t = io.open(p, encoding="utf-8").read()

old = """          XNU_SOURCE_CORECRYPTO14: "0"
          XNU_SOURCE_PTHREAD: "0"
          XNU_ARM_DT_PLATFORM: "0"
          XNU_ARMVIRT_PLATFORM: "0"
          XNU_ARMCPU: "0"
          XNU_NATIVE_UFS: "0"
          XNU_NATIVE_AES: "0"
          XNU_NATIVE_VIRTIO_BLOCK: "0"
          XNU_NATIVE_RAM_BLOCK: "0"
          XNU_NATIVE_VIRTIO_CONSOLE: "0"
          XNU_NATIVE_MOBILE_DISPLAY: "0"
          XNU_NATIVE_LEGACY_DISPLAY: "0"
          XNU_NATIVE_ADRENO: "0"
          XNU_NATIVE_OFFLINE_GPU: "0"
          XNU_VERIFIED_ROOT_PROBE: "0"
          XNU_OWNER_ROOT_AUDIT: "0"
          XNU_OWNER_ROOT_TRUST: "0"
          XNU_SHENG_PMGR: "0"
          XNU_SOURCE_MOCKFS: "0"
          XNU_BOOT_PROGRESS: "0"
          XNU_SMMU4K_PROBE: "0"
          XNU_ADRENO_FIRMWARE_PROBE: "0"
          XNU_ADRENO_PM4_PROBE: "0"
          XNU_CONSTANT_UPLOADS_PROBE: "0"
          XNU_NATIVE_CS_HASH_CACHE: "1"
          XNU_NATIVE_ARCH_TIMER: "1"
          XNU_NATIVE_PAN: "1"
          XNU_DT_PANIC_REGION: "1"
          XNU_TRUST_CACHE_RUNTIME: "1"
          XNU_ZONE_PGZ_ALIGNMENT_PROBE: "1"
          XNU_CRYPTO_BOOTSTRAP: "prelinked"
          XNU_BUILD_WERROR: "0\""""

new = """          # 对齐 hanzi123-bilp/unixnu-fuxi 的 configs/fuxi_defconfig。
          # 第 1 步只要自洽就行（NATIVE_ARCH_TIMER=1 必须配 ARMCPU=1，
          # 否则 build-xnu-4k-baseline.sh L509 直接 exit 1），
          # 但 fuxi_defconfig 里 CONFIG_XNU_ARMCPU=y 且 CONFIG_XNU_NATIVE_UFS=y，
          # 所以下面按 defconfig 全开。
          XNU_SOURCE_CORECRYPTO14: "1"
          XNU_SOURCE_PTHREAD: "1"
          XNU_ARM_DT_PLATFORM: "1"
          XNU_ARMVIRT_PLATFORM: "0"
          XNU_ARMCPU: "1"
          XNU_NATIVE_UFS: "1"
          XNU_NATIVE_AES: "1"
          XNU_NATIVE_VIRTIO_BLOCK: "0"
          XNU_NATIVE_RAM_BLOCK: "0"
          XNU_NATIVE_VIRTIO_CONSOLE: "0"
          XNU_NATIVE_MOBILE_DISPLAY: "0"
          XNU_NATIVE_LEGACY_DISPLAY: "0"
          XNU_NATIVE_ADRENO: "0"
          XNU_NATIVE_OFFLINE_GPU: "0"
          XNU_VERIFIED_ROOT_PROBE: "0"
          XNU_OWNER_ROOT_AUDIT: "0"
          XNU_OWNER_ROOT_TRUST: "0"
          XNU_SHENG_PMGR: "0"
          XNU_SOURCE_MOCKFS: "0"
          XNU_BOOT_PROGRESS: "1"
          XNU_SMMU4K_PROBE: "0"
          XNU_ADRENO_FIRMWARE_PROBE: "0"
          XNU_ADRENO_PM4_PROBE: "0"
          XNU_CONSTANT_UPLOADS_PROBE: "0"
          XNU_NATIVE_CS_HASH_CACHE: "1"
          XNU_NATIVE_ARCH_TIMER: "1"
          XNU_NATIVE_PAN: "1"
          XNU_DT_PANIC_REGION: "1"
          XNU_TRUST_CACHE_RUNTIME: "1"
          XNU_ZONE_PGZ_ALIGNMENT_PROBE: "1"
          XNU_CRYPTO_BOOTSTRAP: "prelinked"
          XNU_BUILD_WERROR: "0\""""

if old in t:
    t = t.replace(old, new, 1)
    io.open(p, "w", encoding="utf-8", newline="\n").write(t)
    print("第 1 步 env 已对齐 fuxi_defconfig")
else:
    print("锚点没找到")

d = yaml.safe_load(io.open(p, encoding="utf-8"))
print("\nYAML 有效")

# 打印新的 env
for step in d["jobs"]["build"]["steps"]:
    if "第 1 步" in step.get("name", ""):
        print("\n第 1 步 env:")
        for k, v in (step.get("env") or {}).items():
            print("  %-32s %s" % (k, v))
