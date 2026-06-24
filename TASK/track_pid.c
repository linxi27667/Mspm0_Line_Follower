/**
 * @file    track_pid.c
 * @brief   循迹PID控制器实现 — 含不完全微分
 */
#include "track_pid.h"

void Track_PID_Init(Track_PID_t *pid, float kp, float ki, float kd,
                    float integral_limit, float output_limit)
{
    if (pid == NULL) return;
    pid->kp = kp;
    pid->ki = ki;
    pid->kd = kd;
    pid->integral_limit   = integral_limit;
    pid->output_limit     = output_limit;
    pid->integral_sep_threshold = 0;
    pid->error           = 0;
    pid->last_error      = 0;
    pid->integral        = 0;
    pid->derivative      = 0;
    pid->last_derivative = 0;
    pid->output          = 0;
}

void Track_PID_Set_Params(Track_PID_t *pid, float kp, float ki, float kd)
{
    if (pid == NULL) return;
    pid->kp = kp;
    pid->ki = ki;
    pid->kd = kd;
}

float Track_PID_Calculate(Track_PID_t *pid, float target, float feedback)
{
    if (pid == NULL) return 0;

    pid->error = target - feedback;

    /* 积分分离：偏差过大时不累加积分 */
    if (pid->integral_sep_threshold > 0 &&
        (pid->error > pid->integral_sep_threshold ||
         pid->error < -pid->integral_sep_threshold)) {
        /* 跳过积分累加 */
    } else {
        pid->integral += pid->error;
        if (pid->integral >  pid->integral_limit) pid->integral =  pid->integral_limit;
        if (pid->integral < -pid->integral_limit) pid->integral = -pid->integral_limit;
    }

    /* 不完全微分：一阶低通滤波，抑制噪声尖峰
     * derivative = alpha * last_derivative + (1-alpha) * (error - last_error) */
    float raw_derivative = pid->error - pid->last_error;
    pid->derivative = TRACK_PID_DERIV_ALPHA * pid->last_derivative
                    + (1.0f - TRACK_PID_DERIV_ALPHA) * raw_derivative;

    pid->output = pid->kp * pid->error
                + pid->ki * pid->integral
                + pid->kd * pid->derivative;

    if (pid->output >  pid->output_limit) pid->output =  pid->output_limit;
    if (pid->output < -pid->output_limit) pid->output = -pid->output_limit;

    pid->last_error      = pid->error;
    pid->last_derivative = pid->derivative;
    return pid->output;
}

void Track_PID_Reset(Track_PID_t *pid)
{
    if (pid == NULL) return;
    pid->error           = 0;
    pid->last_error      = 0;
    pid->integral        = 0;
    pid->derivative      = 0;
    pid->last_derivative = 0;
    pid->output          = 0;
}
