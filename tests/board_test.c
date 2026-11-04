// SPDX-License-Identifier: BSD-2-Clause-Patent
// 主机侧测试：FuxiTouchBoard.h / FuxiPanelBoard.h 的板级常量与地址换算，并与 drivers/FuxiFtsTouch 的协议常量交叉核对。
// 协议层和触点跟踪自己的测试在 drivers/FuxiFtsTouch/Test/。
// 编译运行（WSL）: gcc -std=c11 -Wall -Wextra -Werror -I../package -I../drivers/FuxiFtsTouch board_test.c
//   ../drivers/FuxiFtsTouch/FtsTouchCore.c -o /tmp/board_test && /tmp/board_test
#include <stdio.h>
#include <string.h>
#include "FtsProtocol.h"
#include "FtsTouchCore.h"
#include "FuxiTouchBoard.h"
#include "FuxiPanelBoard.h"

static int failures;
#define CHECK(cond) do { if (!(cond)) { printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); failures++; } } while (0)

int main(void) {
    // 板级芯片 ID 与协议层一致
    CHECK(FTB_CHIP_ID0 == FTS_CHIP_ID0 && FTB_CHIP_ID1 == FTS_CHIP_ID1);

    // 超分辨率事件解码后换算到像素：x = 6700 → 670 px，y = 20492 → 2049 px
    const uint8_t ev[8] = {0x13, 0x21, 0x2C, 0x1A, 0x0C, 0x50, 0x34, 0x82};
    struct fts_point p;
    fts_decode_point(ev, 1, &p);
    CHECK(p.x == 6700 && p.y == 20492);
    CHECK(ftb_to_pixel_x(p.x) == 670 && ftb_to_pixel_y(p.y) == 2049);

    // 坐标边界正好覆盖屏幕
    CHECK(FTB_X_MAX / FTB_SCALE == FPB_WIDTH && FTB_Y_MAX / FTB_SCALE == FPB_HEIGHT);
    // 屏下指纹中心与安卓侧属性 442,2052 / 196 一致
    CHECK(FTB_FOD_X / FTB_SCALE == 442 && FTB_FOD_Y / FTB_SCALE == 2052 && FTB_FOD_SIZE / FTB_SCALE == 196);

    // TLMM 地址：GPIO25 控制寄存器 0x0F119000，中断状态 0x0F11900C；GPIO44 = 0x0F12C000
    CHECK(ftb_tlmm_ctl(FTB_GPIO_IRQ) == 0x0f119000ULL);
    CHECK(ftb_tlmm_intr_status(FTB_GPIO_IRQ) == 0x0f11900cULL);
    CHECK(ftb_tlmm_ctl(FTB_GPIO_SPI_MISO) == 0x0f12c000ULL);

    // 帧缓冲放得下 1080x2400x32bpp
    CHECK((unsigned long long)FPB_FB_STRIDE_PIXELS * FPB_HEIGHT * (FPB_FB_BPP / 8) <= FPB_SPLASH_SIZE);

    // 触控上电投票：先 vdd（0x40900）后 avdd（0x41b00），最后一条是 avdd 使能
    const size_t ncmd = sizeof ftb_power_on_cmds / sizeof ftb_power_on_cmds[0];
    CHECK(ncmd == 5);
    CHECK(ftb_power_on_cmds[0].addr == 0x40900u && ftb_power_on_cmds[0].data == 1800u);
    CHECK(ftb_power_on_cmds[2].addr == 0x40904u && ftb_power_on_cmds[2].data == 1u);
    CHECK(ftb_power_on_cmds[3].addr == 0x41b00u && ftb_power_on_cmds[3].data == 3200u);
    CHECK(ftb_power_on_cmds[ncmd - 1].addr == 0x41b04u && ftb_power_on_cmds[ncmd - 1].data == 1u);

    printf(failures ? "%d 项失败\n" : "全部通过\n", failures);
    return failures != 0;
}
