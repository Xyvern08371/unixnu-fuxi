/*
 * fuxi 最小内核 —— 入口
 *
 * 引导器（UEFI 里的 FuxiProbe）跳过来时的约定：
 *   x0 = 设备树物理地址
 *   x1 = 帧缓冲物理地址
 *   x2 = 每行像素数（pitch）
 *   x3 = 屏幕高度（像素行数）
 *   sp = 已经由引导器设好（64KB 栈顶）
 *
 * 这个文件只做一件事：直接跳到 C 的 kernel_main，保持 x0..x3 不变。
 */

    .section .text, "ax"
    .global _start
    .type _start, %function
_start:
    /* 中断已由引导器关闭；这里再关一次，防御性动作 */
    msr  daifset, #0xf
    b    kernel_main
    .size _start, . - _start
