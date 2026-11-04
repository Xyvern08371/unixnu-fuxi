// SPDX-License-Identifier: BSD-2-Clause-Patent
// Zero-initialised dashboard placeholders BootProgress.c draws but which the
// stage-2 fuxi kernel does not build (no legacy display transfer, no offline
// GPU, no process trace, no cpufreq probe). Zero means "not present"; when a
// subsystem is really built, its archive takes the symbol over and this file
// must drop it. Types mirror the weak_import declarations in BootProgress.c.
#include <stddef.h>
#include <stdint.h>

// Boot process trace.
volatile unsigned boot_process_attempts;
volatile unsigned boot_process_busy;
volatile unsigned boot_process_passes;
char boot_process_rows[10][120];
volatile unsigned boot_process_seen;

// Boot UI trace.
volatile unsigned boot_ui_trace_index;
char boot_ui_trace_label[120];
volatile unsigned boot_ui_trace_phase;
unsigned boot_ui_trace_ready;
char boot_ui_trace_rows[14][120];

// Adreno counters BootProgress reads directly.
volatile uint32_t native_adreno_audit_attr;
volatile uint64_t native_adreno_audit_ticks;
volatile uint32_t native_adreno_coherence[8];
volatile uint32_t native_adreno_wc_distrusted;

// cpufreq / GOP counters.
volatile uint32_t native_cpufreq_stage;
volatile uint64_t native_gop_gpu_abandoned;
volatile uint64_t native_gop_gpu_completions;
volatile uint64_t native_gop_gpu_failures;
volatile uint64_t native_gop_gpu_offers;

// fuxi touch GPIO overlay (weak_import in BootProgress.c; zero keeps it off).
volatile int native_fuxi_touch_pad;
volatile uint32_t native_fuxi_touch_pins[6];
volatile int native_fuxi_touch_pins_n;
volatile uint32_t native_fuxi_touch_dbg[24];

// Legacy display transfer counters.
volatile uint32_t native_legacy_client_calls;
char native_legacy_client_class[64];
volatile int native_legacy_client_pid;
volatile int native_legacy_client_status;
volatile uint32_t native_legacy_client_type;
volatile uint64_t native_legacy_copy_bytes_last;
volatile uint64_t native_legacy_copy_bytes_sum;
volatile uint64_t native_legacy_copy_last;
volatile uint64_t native_legacy_copy_max;
volatile uint64_t native_legacy_copy_n;
volatile uint64_t native_legacy_copy_sum;
volatile uint64_t native_legacy_frame_color_counts[8][4];
volatile uint64_t native_legacy_frame_color_other[8];
volatile uint32_t native_legacy_frame_colors[8][4];
volatile uint32_t native_legacy_frame_count;
volatile uint32_t native_legacy_frame_kind[32];
volatile uint64_t native_legacy_frame_stats[32][5];
volatile uint32_t native_legacy_frame_time[32];
volatile uint64_t native_legacy_gop_bytes;
volatile uint64_t native_legacy_gop_physical;
volatile uint64_t native_legacy_gop_virtual;
volatile uint32_t native_legacy_gpu_fallbacks;
volatile uint32_t native_legacy_gpu_last_status;
volatile uint32_t native_legacy_guard_slot;
volatile uint32_t native_legacy_pm_callbacks;
volatile uint32_t native_legacy_pm_calls;
volatile uint32_t native_legacy_pm_stage;
volatile uint32_t native_legacy_prepare_attempts;
volatile uint32_t native_legacy_prepare_calls;
volatile uint32_t native_legacy_prepare_reason;
char native_legacy_rej_class[32];
volatile uint32_t native_legacy_rej_reason;
volatile uint32_t native_legacy_rej_size[2];
volatile uint32_t native_legacy_rej_state[3];
volatile uint64_t native_legacy_rej_surface[7];
volatile uint64_t native_legacy_rej_surfaces[4];
volatile uint32_t native_legacy_retirement_calls;
volatile uint32_t native_legacy_stage;
volatile uint32_t native_legacy_swap_accepted_count;
volatile uint32_t native_legacy_swap_rejected_count;
volatile uint32_t native_legacy_swap_validation_calls;
volatile uint32_t native_legacy_swap_validation_reason;
volatile uint32_t native_legacy_swap_validation_result;
volatile uint64_t native_legacy_transfer_bytes;
volatile uint32_t native_legacy_transfer_calls;
volatile int native_legacy_transfer_status;

// Probe entry points: nothing to capture and nothing to draw.
void boot_ui_trace_snapshot(unsigned phase) { (void)phase; }
void boot_process_capture(void) {}
void boot_process_snapshot(void) {}
void sheng_cpufreq_poll(void) {}
