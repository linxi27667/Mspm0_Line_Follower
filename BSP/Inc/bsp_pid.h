/**
 * @file    bsp_pid.h
 * @brief   通用PID控制器（BSP — 纯逻辑，跨平台）
 * @note    特性：积分分离 + 输出限幅 + 微分滤波
 */
#ifndef __BSP_PID_H__
#define __BSP_PID_H__

#include <stdint.h>

typedef struct {
    /* --- PID参数 --- */
    float kp;
    float ki;
    float kd;

    /* --- 限幅参数 --- */
    float integral_limit;   /* 积分限幅 */
    float output_limit;     /* 输出限幅 */

    /* --- 积分分离阈值 --- */
    float integral_sep_threshold;  /* 偏差大于此值时关闭积分，0=始终启用 */

    /* --- 内部状态 --- */
    float error;
    float last_error;
    float integral;
    float derivative;
    float output;
} bsp_pid_t;

/* --- API --- */
void  BSP_PID_Init(bsp_pid_t *pid, float kp, float ki, float kd,
                   float integral_limit, float output_limit);
void  BSP_PID_Set_Params(bsp_pid_t *pid, float kp, float ki, float kd);
float BSP_PID_Calculate(bsp_pid_t *pid, float target, float feedback);
void  BSP_PID_Reset(bsp_pid_t *pid);

#endif /* __BSP_PID_H__ */
