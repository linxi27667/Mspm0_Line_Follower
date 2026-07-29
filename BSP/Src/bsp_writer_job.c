/**
 * @file    bsp_writer_job.c
 * @brief   Static writer job sequence, deduplication, and CRC state.
 */
#include "bsp_writer_job.h"

#include <stddef.h>
#include <string.h>

void Bsp_WriterJob_Init(bsp_writer_job_t *job)
{
    if (job == NULL) {
        return;
    }
    memset(job, 0, sizeof(*job));
    job->running_crc32 = Bsp_Writer_Crc32_Init();
}

bsp_writer_job_result_t Bsp_WriterJob_Begin(
    bsp_writer_job_t *job,
    const char *job_id,
    uint32_t total,
    uint32_t expected_crc32)
{
    if ((job == NULL) || !Bsp_Writer_Id_Is_Valid(job_id) ||
        (total == 0u)) {
        return BSP_WRITER_JOB_BAD_ID;
    }
    if (job->active) {
        if ((strcmp(job->job_id, job_id) == 0) &&
            (job->total == total) &&
            (job->expected_crc32 == expected_crc32)) {
            return BSP_WRITER_JOB_DUPLICATE_BEGIN;
        }
        return BSP_WRITER_JOB_BUSY;
    }

    Bsp_WriterJob_Init(job);
    memcpy(job->job_id, job_id, strlen(job_id) + 1u);
    job->total = total;
    job->expected_crc32 = expected_crc32;
    job->active = true;
    return BSP_WRITER_JOB_ACCEPTED;
}

bsp_writer_job_result_t Bsp_WriterJob_Accept_Line(
    bsp_writer_job_t *job,
    const char *job_id,
    uint32_t seq)
{
    if ((job == NULL) || !job->active) {
        return BSP_WRITER_JOB_NO_ACTIVE;
    }
    if ((job_id == NULL) || (strcmp(job->job_id, job_id) != 0)) {
        return BSP_WRITER_JOB_BAD_ID;
    }
    if (job->line_active) {
        if (seq == job->active_seq) {
            return BSP_WRITER_JOB_DUPLICATE_ACTIVE;
        }
        return BSP_WRITER_JOB_OUT_OF_ORDER;
    }
    if (job->has_completed && (seq == job->last_completed_seq)) {
        return BSP_WRITER_JOB_DUPLICATE_COMPLETED;
    }
    if ((seq != job->expected_seq) || (seq >= job->total)) {
        return BSP_WRITER_JOB_OUT_OF_ORDER;
    }

    job->active_seq = seq;
    job->line_active = true;
    job->line_started = false;
    return BSP_WRITER_JOB_ACCEPTED;
}

bool Bsp_WriterJob_Line_Needs_Start(const bsp_writer_job_t *job)
{
    return (job != NULL) && job->active && job->line_active &&
           !job->line_started;
}

bool Bsp_WriterJob_Mark_Line_Started(bsp_writer_job_t *job)
{
    if (!Bsp_WriterJob_Line_Needs_Start(job)) {
        return false;
    }
    job->line_started = true;
    return true;
}

bool Bsp_WriterJob_Complete_Line(bsp_writer_job_t *job,
                                 const uint8_t *line,
                                 uint16_t line_len)
{
    static const uint8_t newline = '\n';

    if ((job == NULL) || !job->active || !job->line_active ||
        !job->line_started ||
        (line == NULL) || (line_len == 0u)) {
        return false;
    }

    job->running_crc32 =
        Bsp_Writer_Crc32_Update(job->running_crc32, line, line_len);
    job->running_crc32 =
        Bsp_Writer_Crc32_Update(job->running_crc32, &newline, 1u);
    job->last_completed_seq = job->active_seq;
    job->has_completed = true;
    job->line_active = false;
    job->line_started = false;
    job->expected_seq++;
    return true;
}

bsp_writer_job_result_t Bsp_WriterJob_End(
    const bsp_writer_job_t *job,
    const char *job_id,
    uint32_t total,
    uint32_t expected_crc32)
{
    if (job == NULL) {
        return BSP_WRITER_JOB_NO_ACTIVE;
    }
    if (!job->active) {
        if (job->has_ended && (job_id != NULL) &&
            (strcmp(job->last_ended_job_id, job_id) == 0) &&
            (job->last_ended_total == total) &&
            (job->last_ended_crc32 == expected_crc32)) {
            return BSP_WRITER_JOB_DUPLICATE_END;
        }
        return BSP_WRITER_JOB_NO_ACTIVE;
    }
    if ((job_id == NULL) || (strcmp(job->job_id, job_id) != 0)) {
        return BSP_WRITER_JOB_BAD_ID;
    }
    if (job->line_active || (total != job->total) ||
        (job->expected_seq != job->total)) {
        return BSP_WRITER_JOB_TOTAL_MISMATCH;
    }
    if ((expected_crc32 != job->expected_crc32) ||
        (Bsp_Writer_Crc32_Final(job->running_crc32) !=
         job->expected_crc32)) {
        return BSP_WRITER_JOB_CRC_MISMATCH;
    }
    return BSP_WRITER_JOB_ACCEPTED;
}

bool Bsp_WriterJob_Finish(bsp_writer_job_t *job)
{
    char ended_job_id[BSP_WRITER_ID_MAX + 1u];
    uint32_t ended_total;
    uint32_t ended_crc32;

    if ((job == NULL) || !job->active || job->line_active ||
        (job->expected_seq != job->total) ||
        (Bsp_Writer_Crc32_Final(job->running_crc32) !=
         job->expected_crc32)) {
        return false;
    }

    memcpy(ended_job_id, job->job_id, strlen(job->job_id) + 1u);
    ended_total = job->total;
    ended_crc32 = job->expected_crc32;
    Bsp_WriterJob_Init(job);
    memcpy(job->last_ended_job_id, ended_job_id,
           strlen(ended_job_id) + 1u);
    job->last_ended_total = ended_total;
    job->last_ended_crc32 = ended_crc32;
    job->has_ended = true;
    return true;
}

void Bsp_WriterJob_Abort(bsp_writer_job_t *job)
{
    Bsp_WriterJob_Init(job);
}
