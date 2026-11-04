# 会话交接记录（2026-10-20 深夜）

> 给下一个上下文用的完整状态快照。读这份就够接着干。

---

## 一、当前结论（最重要）

**路线已确定：放弃裸机 shim，改用 UniXNU 方案。**

裸机 shim 路线走到尽头的原因（有屏幕证据）：
- 内核能在真机启动并给出 `FUXI EARLY PANIC` 寄存器转储
- 但稳定死在 `pc = _current_percpu_base+0xc`，`far = 0x220`，`esr = 0x96000006`
- 该函数是 `return current_thread()->machine.pcpu_data_base;`，`current_thread()` 读 `TPIDR_EL1`
- TPIDR_EL1 原值实测 `0xA76E3718`（ABL 脏值）；清零后仍崩；改成合法地址后仍崩
- 结论：内核在 `start.s` 到 `cpu_data_startup_init` 之间某一环初始化失败，
  且异常处理链自身不可用（`check_exception_stack` 里再崩）

---

## 二、UniXNU 方案现状

### 已克隆到 E 盘
```
E:\download\UniXNU          框架（build driver / DarwinBoot / NativePrelink）
E:\download\UniXNU-sheng    板级配置（board.toml / sheng_defconfig / 驱动 / 脚本）
E:\download\uefi-sheng      Mu-Silicium 的 SM8550 UEFI 端口（含 shengPkg）
E:\download\xnu-src         XNU 源码（打补丁验证用）
```

### sheng（同 SM8550）的关键参数，可直接复用
```
splash_region:  0xb8000000 / 0x2b00000   ← 与我们实测的 fuxi 帧缓冲完全一致
GICD: 0x17100000 (+0x10000)
GICR: 0x17180000 (+0x200000)，PE_SIZE 0x40000
vtimer INTID: 19
chip_id: 207
dram_size: 0x80000000
owned_memory_size: 0x130000000
root_match_volume_uuid: 04769D26-2CA0-4825-B443-E2E5F88300F2
cpu_regs: 0,0x100,0x200,0x300,0x400,0x500,0x600,0x700
```

### sheng 用的内核配置（fuxi 应照抄）
```
kernel = build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped.noctf
slide = -0x1000000
early_security_init = com.apple.driver.AppleMobileFileIntegrity=0xfffffff005ab4ae0
IPSW = iPad7,1 / iPadOS 17.7.11 (21H461)
prelink roots = 32 个（apfs、AppleARMPlatform、AppleMobileFileIntegrity、sandbox、IOHIDFamily…）
```

### shengPkg 里解决过、我们踩过的坑（PORTING.md）
```
① splash_region 节点必须加，否则 ABL 关屏
② SEC 必须选 SP_ELx —— 上一级用 SPSel=0 进来，否则每个异常跑在
   过期的 SP_EL1 上（紧邻不可写的向量页）
③ GIC spurious 中断（INTID 0x105 的 IPCC）必须屏蔽，否则无限循环
   → Resources/MuPatches/Gic-Spurious.patch
④ SHENG_VENDOR_HW=0（默认）时用 SimpleFbDxe 在帧缓冲上发布 GOP，面板保持常亮
   SHENG_VENDOR_HW=1 加厂商驱动会黑屏
```

---

## 三、fuxi 移植要改的东西

| 项 | sheng | fuxi 需要 |
|---|---|---|
| UEFI 平台包 | `Platforms/Xiaomi/shengPkg` | 复制成 `fuxiPkg`（uefi-sheng 里没有 fuxiPkg） |
| board.toml | name=sheng | name=fuxi，其余结构照抄 |
| userdata LBA | 0x2f3840..0x3d0abfa | **从 fuxi 的 GPT 读**（工具已有：`tools/ufs.c` 的 GPT 列表） |
| chip_id | 207 | 需查 fuxi 实际值 |
| 面板 | 3048×2032 | 1080×2400 |
| defconfig | sheng_defconfig | 照抄，去掉 sheng 专用（SHENG_PMGR） |
| GIC / splash | 见上 | **完全相同** |

---

## 四、未完成的动作

1. **`build-uefi-sheng.yml` 已推送（f5913f4）但没有任何构建记录** ——
   用户说"sheng 根本就没在编译"。需要在 Actions 页面确认这个 workflow 是否被识别。
2. **`fuxi-uefi-205.zip` 已测试** —— 那是我们仓库自己的 `edk2-msm` fuxi UEFI，
   `fastboot boot` 返回 OK，但屏幕表现未确认。
3. **用户反馈"我们的 uefi 好像改不了什么东西"** —— 待用户说明具体现象。

---

## 五、关键教训（避免重蹈）

```
· QEMU 用 qemu.adt，真机用 fuxi.adt —— 之前所有"virt_base 导致 panic"的结论
  都是因为 QEMU 测试用了 fuxi.adt（GICR 唤醒超时）
· phys_base 必须与 ADT 的 dram-base 一致
· IC/DC 必须在跳转前刷清，SCTLR_EL1 的 M/C/I 必须清零
· Video.v_baseAddr 最低位=1 表示物理地址（XNU video_console 约定）
· GIC 地址：arm-io.ranges[1] 是 soc_base（真机是 0x100000000，不是 0x1000000），
  gic/reg 要给绝对地址并把 ranges 归零
· 内核窗口要避开 payload 自身区间，且 size 要比 need 留余量
```

---

## 六、仓库状态

```
E:\ios-on-fuxi  分支 main，远程 github.com/Xyvern08371/ios-on-fuxi

补丁：0004（板级+GIC）、0010（早期帧缓冲）、0012（TTBR0 后保留控制台）、
      0027（AppleKeyStore）、0028/0031/0032/0033（各类打点）、0029（vfs 兼容）
      （0030 已回退）

workflows：build-xnu / build-fuxi-shim / build-fuxi-uefi（edk2-msm）/ build-loader
           build-uefi-sheng（新增，未跑）

工具：tools/prelink_payload5.py  预链接主入口
      tools/adt_fix_fuxi.py      ADT 修正（GIC 绝对地址 + ranges 归零）
      tools/qemu_fuxi.py         QEMU 跑 payload + 截屏
      tools/dump_panic2.py       从内存读 panic 字符串
      tools/panic_backtrace.py   帧指针回溯
```

---

## 七、手机恢复

```powershell
cd E:\ios-on-fuxi
$fb = "scripts\adb-platform-tools-latest-windows\platform-tools\fastboot.exe"
& $fb flash boot_a E:\fuxi\boot.img
& $fb flash boot_b E:\fuxi\boot.img
& $fb reboot
```
