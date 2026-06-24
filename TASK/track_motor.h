/**
 * @file    track_motor.h
 * @brief   双电机驱动（TASK层 — 直接操作PWM定时器+GPIO方向）
 * @note    硬件连接（由 SysConfig 生成 ti_msp_dl_config.h）:
 *          - 左电机PWM: TIMG7-CCP0 (PA17), 方向: PA14(AIN1)/PA15(AIN2)
 *          - 右电机PWM: TIMG6-CCP0 (PB10), 方向: PA13(AIN1)/PA18(AIN2)
 */
#ifndef __TRACK_MOTOR_H__
#define __TRACK_MOTOR_H__

#include <stdint.h>

/* ============================================================
 * 电机宏定义
 * ============================================================ */

/* PWM 周期值（SysConfig 配置的 timerCount = 100） */
#define TRACK_MOTOR_PWM_PERIOD   100

/* 速度限幅 */
#define TRACK_MOTOR_SPEED_MAX    100
#define TRACK_MOTOR_SPEED_MIN   (-100)

/* ============================================================
 * 电机接口
 * ============================================================ */

/* 设置左电机速度 (-100~100, 正=前进, 负=后退) */
void Track_Motor_SetLeft(int32_t speed);

/* 设置右电机速度 (-100~100) */
void Track_Motor_SetRight(int32_t speed);

#endif /* __TRACK_MOTOR_H__ */
