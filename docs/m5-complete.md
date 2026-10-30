## M5 完成：启动了一个独立编译的内核（2026-10-18）

真机屏幕显示：

```
KERNEL
RUNNING
DTB
0X00000000XXXXXXXX
MAGIC
0XD00DFEED
DT OK
FB
0X0000B0000000
```

### 这件事为什么重要

这个 `KERNEL` 不是"在 UEFI 驱动里调了个函数"，而是**一份独立编译的裸机程序**：

```
payload/entry.S + payload/kernel.c
    ↓ aarch64-linux-gnu-gcc 编译（-nostdlib -ffreestanding，链接到地址 0）
kernel.bin  （独立二进制，几 KB）
    ↓ tools/gen_blob.py 转成 C 数组
编进 UEFI 固件（LZMA 压缩的固件卷里）
    ↓ 引导器：退出 Boot Services → 分配页 → 复制内核到缓冲区
    ↓ 关中断 → 换栈 → x0=DTB x1=FB x2=pitch x3=height → br 入口
内核执行 → 用自己的点阵字体在屏幕上打印
```

也就是说，**引导器和内核是两份完全独立的程序，只通过寄存器约定通信**。
这正是真实内核的启动方式，后续换成任何内核（Linux 等）流程完全一样。

### 踩到的两个链接坑

| 报错 | 原因 | 解决 |
|---|---|---|
| `PHDR segment not covered by LOAD segment` | `-pie` + 自定义链接脚本 | 去掉 `-pie`（AArch64 寻址本身 PC 相对） |
| 同上，仍复现 | `-T link.ld -Wl,-N` 的段布局问题 | 不用自定义脚本，改 `-Wl,-Ttext=0` |
| 入口可能不在文件开头 | `.text.start` 会被排在 `.text` 之后 | 入口段改回 `.text`，并把 `entry.S` 放在编译命令最前 |

### 当前完整能力链

```
固件启动 → 显示初始化 → 帧缓冲 → 退出 Boot Services
        → 裸机自绘文字 → 关中断/换栈/传设备树 → 跳转
        → 独立内核运行
```

## 下一步的方向（诚实评估）

| 目标 | 可行性 | 说明 |
|---|---|---|
| 自己的内核继续长（中断、定时器、串口） | 🟢 循序渐进 | 每一步都可验证 |
| **启动 Linux 内核** | 🟢 现实目标 | Linux 原生支持设备树与高通平台，驱动都在内核里 |
| **XNU 在 fuxi 上** | 🔴 不可达 | 需要 Apple 私有驱动（display/PMIC/存储/USB 都在 iBoot 侧）+ 未加密 kernelcache |

XNU 的阻碍不是工程量，而是**根本不存在的高通版驱动**，以及加密固件（这部分我们不做）。
