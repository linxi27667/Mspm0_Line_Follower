/**
 * @file    track_pid.h
 * @brief   循迹PID控制器（TASK层 — 自包含，不依赖BSP）
 */
#ifndef __TRACK_PID_H__
#define __TRACK_PID_H__

#include <stdint.h>
#include <stddef.h>

/* ============================================================
 * PID 控制器结构体
 * ============================================================ */
typedef struct {
    float kp, ki, kd;
    float error, last_error;
    float integral, derivative;
    float integral_limit, output_limit;
    float integral_sep_threshold;
    float output;
} Track_PID_t;

/* ============================================================
 * PID 接口
 * ============================================================ */
void Track_PID_Init(Track_PID_t *pid, float kp, float ki, float kd,
                    float integral_limit, float output_limit);
void Track_PID_Set_Params(Track_PID_t *pid, float kp, float ki, float kd);
float Track_PID_Calculate(Track_PID_t *pid, float target, float feedback);
void Track_PID_Reset(Track_PID_t *pid);

#endif /* __TRACK_PID_H__ */
