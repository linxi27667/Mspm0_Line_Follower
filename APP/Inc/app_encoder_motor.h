/**
 * @file    app_encoder_motor.h
 * @brief   霍尔编码器电机应用层声明（硬件绑定 + 业务逻辑入口）
 */
#ifndef APP_ENCODER_MOTOR_H
#define APP_ENCODER_MOTOR_H

#include "bsp_encoder_motor.h"
#include "ti_msp_dl_config.h"

/* ============ 左电机硬件配置 ============ */
#define MOTOR_LEFT_PWM_TIMER        TIMG7
#define MOTOR_LEFT_PWM_CHANNEL      0
#define MOTOR_LEFT_ENC_TIMER        TIMG8
#define MOTOR_LEFT_DIR1_PORT        Monitor_Dir_PORT
#define MOTOR_LEFT_DIR1_PIN         Monitor_Dir_Monitor_AIN1_PIN
#define MOTOR_LEFT_DIR2_PORT        Monitor_Dir_PORT
#define MOTOR_LEFT_DIR2_PIN         Monitor_Dir_Monitor_AIN2_PIN

/* ============ 右电机硬件配置 ============ */
#define MOTOR_RIGHT_PWM_TIMER       TIMG6
#define MOTOR_RIGHT_PWM_CHANNEL     0
#define MOTOR_RIGHT_DIR1_PORT       Right_Motor_Dir_PORT
#define MOTOR_RIGHT_DIR1_PIN        Right_Motor_Dir_AIN1_PIN
#define MOTOR_RIGHT_DIR2_PORT       Right_Motor_Dir_PORT
#define MOTOR_RIGHT_DIR2_PIN        Right_Motor_Dir_AIN2_PIN

/* ============ 右编码器硬件配置（GPIO中断方式） ============
 * MSPM0G3507仅有一个硬件QEI(TIMG8)，已被左编码器占用
 * 右编码器使用GPIO中断计数: PB14=PHA(双沿中断), PB15=PHB
 */
#define RIGHT_ENC_PHA_PORT          Right_Encoder_PORT
#define RIGHT_ENC_PHA_PIN           Right_Encoder_PHA_PIN
#define RIGHT_ENC_PHB_PORT          Right_Encoder_PORT
#define RIGHT_ENC_PHB_PIN           Right_Encoder_PHB_PIN

/* ============ 速度PID参数 ============
 * 级联控制: 位置PID(循迹) → 目标速度 → 速度PID → PWM
 *
 * speed_scale: 编码器计数/周期 对应 1% PWM 的系数
 *   计算式: actual_speed = encoder_speed / speed_scale
 *   校准方法: 设 PWM=50, 测 encoder_speed, scale = encoder_speed / 50
 *   注意: 未校准时 scale=1.0, encoder_speed 被直接当作速度单位,
 *         闭环性能不可靠。需实车标定后调用 App_Motor_Set_Speed_Scale()。
 *   左编码器(QEI 4x)与右编码器(GPIO 2x)分辨率不同,
 *         若发现左右轮增益不一致, 需分别为左右设置不同 scale。
 *
 * integral_sep: 积分分离阈值, 误差超过此值时不累加积分
 *   作用: 启动/急停时避免积分饱和导致超调
 */
#define MOTOR_SPEED_PID_KP          0.8f
#define MOTOR_SPEED_PID_KI          0.2f
#define MOTOR_SPEED_PID_KD          0.0f
#define MOTOR_SPEED_PID_ILIMIT      30.0f
#define MOTOR_SPEED_PID_OLIMIT      30.0f   /* PID修正量限幅(前馈+修正≤100) */
#define MOTOR_SPEED_PID_INTEGRAL_SEP 15.0f  /* 积分分离阈值(误差>15%时不累加I) */
#define MOTOR_SPEED_SCALE_DEFAULT   1.0f    /* 默认值, 需实车校准 */

/* ============ 业务接口声明 ============ */
extern bsp_motor_t Motor_Left;
extern bsp_motor_t Motor_Right;

/* 右编码器计数器（由GPIO中断维护） */
extern volatile int32_t g_right_enc_count;

void App_Motor_Init(void);
void Motor_Set_Speed(int32_t speed);
void Motor_Right_Set_Speed(int32_t speed);
void Motor_Forward(int32_t speed);
void Motor_Backward(int32_t speed);
void Motor_Stop(void);
void Motor_Update_Status(void);
void App_Motor_Speed_PID_Update(void);
void App_Motor_Enable_Speed_PID(bool enable);
void App_Motor_Set_Speed_Scale(float scale);

/* 右编码器GPIO中断回调（在main.c的GROUP1 ISR中调用） */
void Right_Encoder_IRQHandler(void);

#endif /* APP_ENCODER_MOTOR_H */
