/**
 * @file    app_pid.h
 * @brief   通用PID控制器（纯算法，零硬件依赖）
 * @note    特性：积分分离 + 输出限幅 + 微分滤波
 */
#ifndef APP_PID_H
#define APP_PID_H

#include <stdint.h>

typedef struct {
    // PID参数
    float kp;
    float ki;
    float kd;

    // 限幅参数
    float integral_limit;
    float output_limit;

    // 积分分离阈值
    float integral_sep_threshold;

    // 不完全微分系数 (0~1)
    float deriv_alpha;

    // 内部状态
    float error;
    float last_error;
    float integral;
    float derivative;
    float last_derivative;
    float output;
} bsp_pid_t;

//=====PID一次业务函数=====
void  Pid_Init(bsp_pid_t *pid, float kp, float ki, float kd,
               float integral_limit, float output_limit);
void  Pid_Set_Params(bsp_pid_t *pid, float kp, float ki, float kd);
float Pid_Compute(bsp_pid_t *pid, float target, float feedback);
void  Pid_Reset(bsp_pid_t *pid);

#endif /* APP_PID_H */
