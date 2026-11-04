// SPDX-License-Identifier: MIT
// Restarts into the bootloader's fastboot mode: sync, then reboot(LINUX_REBOOT_CMD_RESTART2, "bootloader"). The sheng device tree's
// nvmem-reboot-mode node (mode-bootloader = 2 in the PMIC SDAM reboot-reason cell) turns the argument into the boot mode ABL reads, once
// nvmem-reboot-mode.ko is loaded. Static, libc-free aarch64 Linux program, built like linux-ref's tools.
namespace {
long sys(long n, long a = 0, long b = 0, long c = 0, long d = 0) {
    register long x8 asm("x8") = n, x0 asm("x0") = a, x1 asm("x1") = b, x2 asm("x2") = c, x3 asm("x3") = d;
    asm volatile("svc #0" : "+r"(x0) : "r"(x8), "r"(x1), "r"(x2), "r"(x3) : "memory");
    return x0;
}
enum : long {SysWrite = 64, SysExit = 94, SysSync = 81, SysReboot = 142};
}  // namespace

extern "C" [[noreturn]] void start() {
    sys(SysSync);
    const long r = sys(SysReboot, 0xfee1dead, 672274793, 0xa1b2c3d4, (long)"bootloader");
    static const char failed[] = "rebootbl: reboot failed\n";
    sys(SysWrite, 2, (long)failed, sizeof failed - 1);
    sys(SysExit, r < 0 ? -r : 1);
    for (;;) {}
}
