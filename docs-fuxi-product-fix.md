# 关键突破：ADT 缺 /product 导致 SpringBoard 崩溃

日期：2026-10-24
设备：Xiaomi 13 (fuxi, SM8550)
镜像：ios-fuxi 社区移植 + 他们的内核（2026-10-21_working，sha256 829e3e3a…）

## 现象

启动到用户态后，SpringBoard 反复崩溃重启，屏幕永远停在苹果 logo。
控制台里能看到：

```
[SpringBoard] *** Assertion failure in
  -[_UIScreenComplexBoundingPathUtilities _loadBitmapForScreen:type:],
  _UIScreenComplexBoundingPathUtilities.m:326
[SpringBoard] *** Terminating app due to uncaught exception
  'NSInternalInconsistencyException', reason:
  'Failed to load bounding path bitmap data from the asset manager
   for asset name: BoundingPathBitmap-1125x2436-375x812-3.00x'
CRASH SpringBoard sig 6 ...        (sig 6 = abort)
```

## 排查过程（走过的弯路，供以后参考）

以下**都不管用**：

- 确认 `BoundingPathData.bundle/Assets.car` 存在、里面有那个资产名字符串
- 把 `Assets.car` 复制成 `UIKit_BoundingPathData.car` 放在 6 个候选路径
  （bundle 内、framework 根、framework/Resources、以 catalog 名命名的 bundle、CoreUI.framework）
- 用 launchd plist 的 `DYLD_INSERT_LIBRARIES` 注入 dylib，把
  `+[_UIScreenComplexBoundingPathUtilities isScreenSupported:]` 改成返回 NO
  → **SpringBoard 直接不启动了**：iOS 的 launchd 对平台二进制会忽略 DYLD_*
- 给 SpringBoard 的 Mach-O 加 `LC_LOAD_DYLIB`（改 load command）
  → **内核 panic**：`unexpected exec of non-platform binary`
  （签名失效后不再是平台二进制，且没有 boot-arg 能关这条检查）
- `sweetfb_native=1`（1080x2400）、`ufscache`、`debug=0x0`、GPU 固件补齐等

## 根因

`tools/mkadt.py` 的注释里写着：

> copies `/product` from the real iPhone X device tree, **which MobileGestalt needs**

**MobileGestalt 从 IORegistry 的 `/device-tree/product` 读设备身份**（product-name、
设备族、能力位……）。UIKit 计算资源 key 时依赖这套身份。我们的 ADT 是从
`XNU Kernel.zip` 里那份直接改的，**没有 `/product` 节点**，于是资产 key 对不上，
`_loadBitmapForScreen:type:` 拿到 nil → NSAssert → abort。

## 修复

从 iPhone X（iPhone10,3 / D22AP, iOS 16.7.16）的 `DeviceTree.d22ap.im4p` 里
把 `/product` 合进我们的 ADT。

注意两个坑：

1. `DeviceTree.d22ap.im4p` 是 **DER 包裹的 IM4P，payload 还是 lzfse 压缩**；
   用 `tools/adt.py` 的 `load()`，需要 `lzfse` 命令行工具。
2. `/product` 有 5 个子节点，其中 `syscfg` 里装的是**设备树绝对指针**；
   原样拷过去内核会 panic：

   ```
   panic: Device tree pointer outside of device tree region
   ```

   照 `mkadt.py` 的做法：**只取属性，丢弃全部子节点**，并跳过 placeholder
   （flag 位非 0）、`name`、`AAPL,phandle`，再补一个新的 `AAPL,phandle`。

最终 `/product` = 61 个属性（`product-name = "iPhone X"` 等），ADT 11,988 字节。

## 结果

```
ABL → loader → XNU → UFS → HFS+ → launchd → backboardd → SpringBoard
→ 锁屏界面正常绘制
```

## 相关文件

- 修复脚本：`E:\download\uefi-build\_graft4.py`
- 产出的 ADT：`E:\download\uefi-build\working\fuxi-root3.adt`
- 可用镜像：`E:\download\fuxi-loader-work\fuxi-lock.img`（控制台关）
            `E:\download\fuxi-loader-work\fuxi-product-con.img`（控制台开，可看日志）
- 根卷：`E:\wsl\ios16-root-v9.simg`

## 触控

现状：**已可用**（锁屏可触摸）。

根因：`bsd/dev/fuxi_touch.c`（补丁 0091-fuxi-touch-fts-spi）的头部注释写明：

```
FUXI touch: ST FTS (FTM5) on QUP1 SE4, SPI through QUP1 GPI DMA (polled).
...
The loader votes the RPMh rails (ldob12 vdd 1.8 V, ldom6 avdd 3.2 V)
before the XNU handoff; this driver does not talk to RPMh.
```

**触控 IC 的供电必须由 loader 在跳转前投 RPMh 票，内核驱动自己不做。**
而这段代码在 `probe.c` 的 `touch_power()` 里，正常启动时不会被调用
（只由 USB 监控命令 `'TP'` 0x5450 触发）。我们跳过 `probe_main` 后，
触控就一直没电。

修复：给 `probe.c` 加 `fuxi_touch_power()`，把 `touch_power()` 的前半段
（复位保持、四条 RPMh 投票、延时、放开 IRQ 与复位、SPI 引脚配置）
单独暴露出来，由 `loader_patched.c` 在 `loader_boot()` 前调用：

```c
ts_gpio(24,0,3,8,0); ts_gpio(25,0,3,8,0);        /* 复位保持、IRQ 低 */
{0x40900,1800},{0x40904,1}                       /* vdd 1.8 V + enable */
{0x41b00,3200},{0x41b04,1}                       /* avdd 3.2 V + enable */
delay(3000);
ts_gpio(25,0,3,8,-1); ts_gpio(24,0,3,8,1);       /* 放 IRQ、释放复位 */
ts_gpio(44..47, ...);                            /* SPI 引脚 */
```

内核随后自己做时钟、SE/SPI 初始化、复位时序、多点扫描和事件轮询。

排查中顺带确认：fuxi 的触控是 **ST FTS (FTM5)**，走 QUP1 SE4 的 SPI；
像素上有 Goodix GT9916 的节点（`goodix,gt9916`），但那是别的配置，
与本机实际控制器无关。

## GPU

`FUXI GPU: disabled permanently: bring-up/self-test (0x10), zap=0xf04`
—— GPU 固件自检失败，UI 目前纯 CPU 渲染（这也是启动/绘制慢的原因）。
他们 pin 的 `a740_sqe.fw` 是 7538 B 版本，我们用的是设备 vendor 里的 76724 B 版本。
