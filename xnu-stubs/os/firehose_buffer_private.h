/*
 * os/firehose_buffer_private.h —— fuxi 用最小替身（第 4 版）
 *
 * 背景:
 *   XNU 树里 libkern/firehose/ 下有 firehose_types_private.h、
 *   tracepoint_private.h、chunk_private.h，但缺 os/firehose_buffer_private.h
 *   （Apple 内部头）。libkern/os/log.c 与 bsd/kern/subr_log.c 需要它。
 *
 * 逐步收紧的过程（由编译错误反推）:
 *   1. 不能重复定义 firehose_buffer_t / map_info / push_reply（树里已有）
 *   2. 不能定义 __firehose_buffer_push_to_logd（log.c 自己有实现）
 *   3. 不能用 #include <firehose/private.h>（部分编译单元没有该 include 路径）
 *   4. 需要自己提供 __firehose_buffer_tracepoint_reserve / _flush 的空实现
 *      —— 参数个数不确定，用可变参数最稳（C99 允许 static inline 变参函数）
 *
 * 这里的实现全部是空操作：firehose 追踪功能不可用，但不影响内核主流程。
 */

#ifndef __FIREHOSE_BUFFER_PRIVATE__
#define __FIREHOSE_BUFFER_PRIVATE__

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#include <mach/mach_types.h>
#include <mach/std_types.h>

#include <firehose/firehose_types_private.h>
#include <firehose/tracepoint_private.h>
#include <firehose/chunk_private.h>

__BEGIN_DECLS

/* ---------------- 树内缺失的常量 ---------------- */

#ifndef FIREHOSE_BUFFER_KERNEL_CHUNK_COUNT
#define FIREHOSE_BUFFER_KERNEL_CHUNK_COUNT   16
#endif

#ifndef FIREHOSE_BUFFER_KERNEL_DEFAULT_CHUNK_COUNT
#define FIREHOSE_BUFFER_KERNEL_DEFAULT_CHUNK_COUNT   16
#endif

#ifndef FIREHOSE_BUFFER_KERNEL_DEFAULT_IO_PAGES
#define FIREHOSE_BUFFER_KERNEL_DEFAULT_IO_PAGES      16
#endif

/* ---------------- 空实现（变参，避免参数个数/类型不匹配） ---------------- */

/*
 * 用 K&R 风格 "()" 声明：参数个数与类型都不做检查。
 * 这样无论内核代码怎么调用都能编过（只是空实现，firehose 不可用）。
 * clang 会给 -Wstrict-prototypes 警告，但我们已经去掉了 -Werror。
 */

static inline firehose_tracepoint_t
__firehose_buffer_tracepoint_reserve()
{
	return (firehose_tracepoint_t)0;
}

static inline void
__firehose_buffer_tracepoint_flush()
{
}

static inline firehose_buffer_t
__firehose_buffer_create()
{
	return (firehose_buffer_t)0;
}

static inline bool
__firehose_merge_updates()
{
	return false;
}

static inline bool
__firehose_kernel_configuration_valid()
{
	return true;
}

__END_DECLS

#endif /* __FIREHOSE_BUFFER_PRIVATE__ */
