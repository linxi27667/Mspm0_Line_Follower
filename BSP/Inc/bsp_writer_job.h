/**
 * @file    bsp_writer_job.h
 * @brief   Static writer job sequence, deduplication, and CRC state.
 */
#ifndef BSP_WRITER_JOB_H
#define BSP_WRITER_JOB_H

#include <stdbool.h>
#include <stdint.h>

#include "bsp_writer_protocol.h"

typedef enum {
    BSP_WRITER_JOB_ACCEPTED = 0,
    BSP_WRITER_JOB_DUPLICATE_BEGIN,
    BSP_WRITER_JOB_DUPLICATE_ACTIVE,
    BSP_WRITER_JOB_DUPLICATE_COMPLETED,
    BSP_WRITER_JOB_DUPLICATE_END,
    BSP_WRITER_JOB_OUT_OF_ORDER,
    BSP_WRITER_JOB_BUSY,
    BSP_WRITER_JOB_NO_ACTIVE,
    BSP_WRITER_JOB_BAD_ID,
    BSP_WRITER_JOB_TOTAL_MISMATCH,
    BSP_WRITER_JOB_CRC_MISMATCH
} bsp_writer_job_result_t;

typedef struct {
    char job_id[BSP_WRITER_ID_MAX + 1u];
    uint32_t total;
    uint32_t expected_crc32;
    uint32_t running_crc32;
    uint32_t expected_seq;
    uint32_t active_seq;
    uint32_t last_completed_seq;
    char last_ended_job_id[BSP_WRITER_ID_MAX + 1u];
    uint32_t last_ended_total;
    uint32_t last_ended_crc32;
    bool active;
    bool line_active;
    bool line_started;
    bool has_completed;
    bool has_ended;
} bsp_writer_job_t;

void Bsp_WriterJob_Init(bsp_writer_job_t *job);
bsp_writer_job_result_t Bsp_WriterJob_Begin(
    bsp_writer_job_t *job,
    const char *job_id,
    uint32_t total,
    uint32_t expected_crc32);
bsp_writer_job_result_t Bsp_WriterJob_Accept_Line(
    bsp_writer_job_t *job,
    const char *job_id,
    uint32_t seq);
bool Bsp_WriterJob_Line_Needs_Start(const bsp_writer_job_t *job);
bool Bsp_WriterJob_Mark_Line_Started(bsp_writer_job_t *job);
bool Bsp_WriterJob_Complete_Line(bsp_writer_job_t *job,
                                 const uint8_t *line,
                                 uint16_t line_len);
bsp_writer_job_result_t Bsp_WriterJob_End(
    const bsp_writer_job_t *job,
    const char *job_id,
    uint32_t total,
    uint32_t expected_crc32);
bool Bsp_WriterJob_Finish(bsp_writer_job_t *job);
void Bsp_WriterJob_Abort(bsp_writer_job_t *job);

#endif /* BSP_WRITER_JOB_H */
