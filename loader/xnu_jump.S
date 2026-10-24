// xnu_jump.S —— 关 MMU / 清缓存 / 跳进 XNU，以及"跳转自测"桩
//
// AsmXnuDcacheCleanRange(x0 = start, x1 = end)   按 VA 清 D-cache
// AsmXnuJump(x0 = entry_pa, x1 = boot_args_pa)   关 MMU/缓存后跳转，x0 = boot_args
// AsmXnuSelfTest(x0 = fb, x1 = bytes, x2 = color)
//     关 MMU/缓存后把帧缓冲刷成指定颜色并停住 —— 用来验证"跳转+关 MMU"这套动作本身

.text

// ---------------------------------------------------------------------------
// void AsmXnuDcacheCleanRange(UINTN start, UINTN end)
// ---------------------------------------------------------------------------
.global AsmXnuDcacheCleanRange
.type   AsmXnuDcacheCleanRange, %function
AsmXnuDcacheCleanRange:
    mrs     x2, ctr_el0
    ubfx    x3, x2, #16, #4
    mov     x4, #4
    lsl     x4, x4, x3
    sub     x5, x4, #1
    bic     x0, x0, x5
1:
    dc      cvac, x0
    add     x0, x0, x4
    cmp     x0, x1
    b.lo    1b
    dsb     sy
    ret
.size   AsmXnuDcacheCleanRange, . - AsmXnuDcacheCleanRange

// ---------------------------------------------------------------------------
// void AsmXnuDcacheInvalidateRange(UINTN start, UINTN end)
// 作废 D-cache 行（不写回）：用来强制后续读取走内存，验证清缓存是否有效
// ---------------------------------------------------------------------------
.global AsmXnuDcacheInvalidateRange
.type   AsmXnuDcacheInvalidateRange, %function
AsmXnuDcacheInvalidateRange:
    mrs     x2, ctr_el0
    ubfx    x3, x2, #16, #4
    mov     x4, #4
    lsl     x4, x4, x3
    sub     x5, x4, #1
    bic     x0, x0, x5
4:
    dc      ivac, x0
    add     x0, x0, x4
    cmp     x0, x1
    b.lo    4b
    dsb     sy
    ret
.size   AsmXnuDcacheInvalidateRange, . - AsmXnuDcacheInvalidateRange

// ---------------------------------------------------------------------------
// void AsmXnuTryMmuOff(UINT64 out[2])
//   out[0] = 清 M 之前的 SCTLR_EL1
//   out[1] = 清 M 之后立刻读回的 SCTLR_EL1
// 结束时恢复原值（MMU 保持开启），所以对调用者安全。
// ---------------------------------------------------------------------------
.global AsmXnuTryMmuOff
.type   AsmXnuTryMmuOff, %function
AsmXnuTryMmuOff:
    mrs     x2, sctlr_el1
    str     x2, [x0]
    bic     x3, x2, #0x1
    msr     sctlr_el1, x3
    isb
    mrs     x4, sctlr_el1
    str     x4, [x0, #8]
    msr     sctlr_el1, x2
    isb
    ret
.size   AsmXnuTryMmuOff, . - AsmXnuTryMmuOff

// ---------------------------------------------------------------------------
// void AsmXnuJump(UINTN entry_pa, UINTN boot_args_pa)
// ---------------------------------------------------------------------------
.global AsmXnuJump
.type   AsmXnuJump, %function
AsmXnuJump:
    msr     daifset, #0xf
    mov     x3, x0
    mov     x4, x1

    ic      iallu
    dsb     sy
    isb

    mrs     x2, sctlr_el1
    bic     x2, x2, #0x1
    bic     x2, x2, #0x2
    bic     x2, x2, #0x4
    bic     x2, x2, #0x1000
    msr     sctlr_el1, x2
    isb
    dsb     sy

    // ---------------- MARKER_AFTER_MMU_OFF ----------------
    // MMU 已关，先往帧缓冲左上角画一块 64x64 的绿色方块。
    // 看到绿色 = 关 MMU 之后的写显存正常 -> 问题只剩 br 指令。
    movz    x5, #0xB000, lsl #16
    movz    x6, #0x1C00
    movk    x6, #0x2, lsl #16          // 128 行 * 1080
    mov     w7, #0x0000FF00
3:
    str     w7, [x5], #4
    subs    x6, x6, #1
    b.ne    3b
    dsb     sy

    // fuxi probe: do not jump yet, spin here to isolate the MMU-off write test
5:
    wfi
    b       5b

    mov     x0, x4
    br      x3
.size   AsmXnuJump, . - AsmXnuJump

// ---------------------------------------------------------------------------
// void AsmXnuSelfTest(UINTN fb, UINTN bytes, UINT32 color)
//
// 关 MMU 和缓存之后，直接把整块帧缓冲写成 color，然后停住。
// 能看到颜色 = 跳转前的这段状态切换（关 MMU/缓存）是好的。
// ---------------------------------------------------------------------------
.global AsmXnuSelfTest
.type   AsmXnuSelfTest, %function
AsmXnuSelfTest:
    msr     daifset, #0xf
    mov     x5, x0                  // fb
    mov     x6, x1                  // bytes
    mov     x7, x2                  // color

    ic      iallu
    dsb     sy
    isb

    mrs     x2, sctlr_el1
    bic     x2, x2, #0x1            // M
    bic     x2, x2, #0x2            // A
    bic     x2, x2, #0x4            // C
    bic     x2, x2, #0x1000         // I
    msr     sctlr_el1, x2
    isb
    dsb     sy

    // 按 4 字节写整块显存（MMU 关了，全是 Device，写直通）
2:
    str     w7, [x5], #4
    subs    x6, x6, #4
    b.ne    2b

    dsb     sy
3:
    wfi
    b       3b
.size   AsmXnuSelfTest, . - AsmXnuSelfTest
