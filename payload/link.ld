/*
 * 链接脚本：把内核链接到地址 0，并且让 _start 落在最前面。
 *
 * 为什么要链到 0：
 *   内核是以"位置无关"的方式编译的（-fpie -pie），所有地址都是相对 PC 的。
 *   引导器可以把它复制到任意地址，然后跳到"那块地址 + 0"，就能正确执行。
 *   链到 0 保证了文件的第一字节就是 _start。
 */

ENTRY(_start)

SECTIONS
{
    . = 0;

    .text : {
        *(.text.start)
        *(.text*)
    }

    .rodata : {
        *(.rodata*)
    }

    .data : {
        *(.data*)
    }

    .bss : {
        *(.bss*)
        *(COMMON)
    }

    /DISCARD/ : {
        *(.comment)
        *(.note*)
        *(.eh_frame*)
    }
}
