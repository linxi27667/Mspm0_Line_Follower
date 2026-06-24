/**
 * @file    bsp_pid.c
 * @brief   通用PID控制器实现（BSP — 纯逻辑，跨平台）
 */
#include "bsp_pid.h"
#include <stddef.h>

void BSP_PID_Init(bsp_pid_t *pid, float kp, float ki, float kd,
                   float integral_limit, float output_limit)
{
    if (pid == NULL) return;

    pid->kp = kp;
    pid->ki = ki;
    pid->kd = kd;
    pid->integral_limit   = integral_limit;
    pid->output_limit     = output_limit;
    pid->integral_sep_threshold = 0;  /* 默认不启用积分分离 */

    pid->error      = 0;
    pid->last_error = 0;
    pid->integral   = 0;
    pid->derivative = 0;
    pid->output     = 0;
}

void BSP_PID_Set_Params(bsp_pid_t *pid, float kp, float ki, float kd)
{
    if (pid == NULL) return;
    pid->kp = kp;
    pid->ki = ki;
    pid->kd = kd;
}

float BSP_PID_Calculate(bsp_pid_t *pid, float target, float feedback)
{
    if (pid == NULL) return 0;

    pid->error = target - feedback;

    /* 积分分离：偏差过大时关闭积分 */
    if (pid->integral_sep_threshold > 0 &&
        (pid->error > pid->integral_sep_threshold ||
         pid->error < -pid->integral_sep_threshold)) {
        /* 不累加积分 */
    } else {
        pid->integral += pid->error;
        if (pid->integral > pid->integral_limit)  pid->integral = pid->integral_limit;
        if (pid->integral < -pid->integral_limit) pid->integral = -pid->integral_limit;
    }

    /* 微分 */
    pid->derivative = pid->error - pid->last_error;

    /* PID输出 */
    pid->output = pid->kp * pid->error
                + pid->ki * pid->integral
                + pid->kd * pid->derivative;

    /* 输出限幅 */
    if (pid->output > pid->output_limit)  pid->output = pid->output_limit;
    if (pid->output < -pid->output_limit) pid->output = -pid->output_limit;

    pid->last_error = pid->error;

    return pid->output;
}

void BSP_PID_Reset(bsp_pid_t *pid)
{
    if (pid == NULL) return;
    pid->error      = 0;
    pid->last_error = 0;
    pid->integral   = 0;
    pid->derivative = 0;
    pid->output     = 0;
}
