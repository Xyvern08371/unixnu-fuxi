/*
 * fuxi 用的 firehose 替身头文件（第 2 版）
 *
 * 背景:
 *   XNU 的 libkern/os/log.c 与 bsd/kern/subr_log.c 依赖 Apple 内部头:
 *       <firehose/tracepoint_private.h>
 *       <firehose/chunk_private.h>
 *       <firehose/ioctl_private.h>
 *       <os/firehose_buffer_private.h>
 *   这些不在开源树里，也不在公开 SDK 里。
 *
 * 从编译错误得知: 树内已有 libkern/firehose/firehose_types_private.h，
 * 它已经定义了 firehose_stream_t / tracepoint_code_t / namespace /
 * firehose_tracepoint_id_u(含 ftid_value) 等。**不能重复定义**。
 *
 * 本文件只补真正缺失的部分:
 *   - struct firehose_chunk_s 与 firehose_chunk_t（真实类型是指针）
 *   - firehose_buffer_t / map_info / push_reply
 *   - FIREHOSE_CHUNK_SIZE 等常量
 *   - 若干函数（空实现，只为让内核能编过、能链接）
 */

#ifndef __FUXI_FIREHOSE_STUB_H__
#define __FUXI_FIREHOSE_STUB_H__

#include <mach/mach_types.h>
#include <mach/std_types.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

/* 复用树内已有的类型定义（枚举、tracepoint id 等） */
#include <firehose/firehose_types_private.h>

__BEGIN_DECLS

/* ---------------- 常量（树内没有的） ---------------- */

#ifndef FIREHOSE_CHUNK_SIZE
#define FIREHOSE_CHUNK_SIZE                          0x40000     /* 256KB */
#endif

#ifndef FIREHOSE_BUFFER_KERNEL_DEFAULT_CHUNK_COUNT
#define FIREHOSE_BUFFER_KERNEL_DEFAULT_CHUNK_COUNT   16
#endif

#ifndef FIREHOSE_BUFFER_KERNEL_DEFAULT_IO_PAGES
#define FIREHOSE_BUFFER_KERNEL_DEFAULT_IO_PAGES      16
#endif

#ifndef FIREHOSE_BUFFER_KERNEL_CHUNK_COUNT
#define FIREHOSE_BUFFER_KERNEL_CHUNK_COUNT           16
#endif

/* ---------------- chunk（chunk_private.h 里的内容） ---------------- */

struct firehose_chunk_pos_s {
	uint32_t          fcp_next_entry_offs;
	uint32_t          fcp_private_offs;
	uint32_t          fcp_refcnt;
	firehose_stream_t fcp_stream;
	uint32_t          fcp_flag_io;
};

struct firehose_chunk_s {
	struct firehose_chunk_pos_s  fc_pos;
	uint8_t                      fc_data[FIREHOSE_CHUNK_SIZE];
};

/* 真实类型是指针（subr_log.c 里: firehose_chunk_t firehose_boot_chunk = &oslog_boot_buf） */
typedef struct firehose_chunk_s *firehose_chunk_t;

/* ---------------- 缓冲区（firehose_buffer_private.h 里的内容） ---------------- */

typedef struct firehose_buffer_s *firehose_buffer_t;

typedef struct {
	mach_vm_address_t  addr;
	mach_vm_size_t     size;
} firehose_buffer_map_info_t;

typedef struct {
	uint32_t  fpr_status;
	uint32_t  fpr_padding;
} firehose_push_reply_t;

typedef struct {
	uint64_t  flags;
} firehose_trace_metadata_t;

typedef struct {
	uint8_t   flags[16];
} firehose_trace_uuid_info_s;

/* ---------------- 函数（空实现） ---------------- */

static inline uint64_t
firehose_tracepoint_time(firehose_tracepoint_flags_t flags __unused)
{
	return 0;
}

static inline firehose_chunk_t
firehose_chunk_tracepoint_try_reserve(firehose_buffer_t fb __unused,
    firehose_stream_t stream __unused, uint16_t flags __unused, uint8_t size __unused)
{
	return (firehose_chunk_t)0;
}

static inline void
firehose_chunk_tracepoint_begin(firehose_buffer_t fb __unused,
    firehose_tracepoint_id_u ftid __unused, uint64_t ts __unused)
{
}

static inline void
firehose_chunk_tracepoint_end(firehose_buffer_t fb __unused,
    firehose_chunk_t chunk __unused, firehose_tracepoint_id_u ftid __unused,
    uint64_t ts __unused, const void *buf __unused, size_t sz __unused)
{
}

static inline void
__firehose_allocate(vm_offset_t *addr __unused, vm_size_t size __unused)
{
}

static inline void
__firehose_critical_region_enter(void)
{
}

static inline void
__firehose_critical_region_leave(void)
{
}

static inline void
__firehose_buffer_push_to_logd(firehose_buffer_t fb __unused, bool for_io __unused)
{
}

static inline firehose_buffer_t
__firehose_buffer_create(size_t *size __unused)
{
	return (firehose_buffer_t)0;
}

static inline bool
__firehose_merge_updates(firehose_push_reply_t reply __unused)
{
	return false;
}

static inline bool
__firehose_kernel_configuration_valid(uint8_t chunks __unused, uint8_t pages __unused)
{
	return true;
}

__END_DECLS

#endif /* __FUXI_FIREHOSE_STUB_H__ */
