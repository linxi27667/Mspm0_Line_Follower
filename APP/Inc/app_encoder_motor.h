/**
 * @file    app_encoder_motor.h
 * @brief   霍尔编码器电机应用层声明（硬件绑定 + 业务逻辑入口）
 */
#ifndef APP_ENCODER_MOTOR_H
#define APP_ENCODER_MOTOR_H

#include "bsp_encoder_motor.h"
#include "ti_msp_dl_config.h"
#include "user_tuning.h"

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
 *         闭环性能不可靠。需实车标定后调用 App_Motor_Calibrate_Scale()。
 *   左编码器(QEI 4x)与右编码器(GPIO 2x)分辨率不同,
 *         必须分别为左右设置不同 scale (典型 scale_right ≈ 2 * scale_left)。
 *
 * integral_sep: 积分分离阈值, 误差超过此值时不累加积分
 *   作用: 启动/急停时避免积分饱和导致超调
 */
#ifndef USER_MOTOR_SPEED_PID_KP
#define USER_MOTOR_SPEED_PID_KP    0.8f
#endif
#ifndef USER_MOTOR_SPEED_PID_KI
#define USER_MOTOR_SPEED_PID_KI    0.2f
#endif
#ifndef USER_MOTOR_SPEED_PID_KD
#define USER_MOTOR_SPEED_PID_KD    0.0f
#endif
#ifndef USER_MOTOR_SPEED_PID_ILIMIT
#define USER_MOTOR_SPEED_PID_ILIMIT 30.0f
#endif
#ifndef USER_MOTOR_SPEED_PID_OLIMIT
#define USER_MOTOR_SPEED_PID_OLIMIT 30.0f
#endif
#ifndef USER_MOTOR_SPEED_PID_INTEGRAL_SEP
#define USER_MOTOR_SPEED_PID_INTEGRAL_SEP 15.0f
#endif

/* 左右独立速度比例尺 (国一方案: 左右编码器分辨率不同必须分别标定)
 * 若只定义了 USER_MOTOR_SPEED_SCALE (兼容旧配置), 左右都用该值 */
#ifdef USER_MOTOR_SPEED_SCALE
#ifndef USER_MOTOR_SPEED_SCALE_LEFT
#define USER_MOTOR_SPEED_SCALE_LEFT   USER_MOTOR_SPEED_SCALE
#endif
#ifndef USER_MOTOR_SPEED_SCALE_RIGHT
#define USER_MOTOR_SPEED_SCALE_RIGHT  USER_MOTOR_SPEED_SCALE
#endif
#else
#ifndef USER_MOTOR_SPEED_SCALE_LEFT
#define USER_MOTOR_SPEED_SCALE_LEFT   1.0f
#endif
#ifndef USER_MOTOR_SPEED_SCALE_RIGHT
#define USER_MOTOR_SPEED_SCALE_RIGHT  1.0f
#endif
#endif

#define MOTOR_SPEED_PID_KP          USER_MOTOR_SPEED_PID_KP
#define MOTOR_SPEED_PID_KI          USER_MOTOR_SPEED_PID_KI
#define MOTOR_SPEED_PID_KD          USER_MOTOR_SPEED_PID_KD
#define MOTOR_SPEED_PID_ILIMIT      USER_MOTOR_SPEED_PID_ILIMIT
#define MOTOR_SPEED_PID_OLIMIT      USER_MOTOR_SPEED_PID_OLIMIT
#define MOTOR_SPEED_PID_INTEGRAL_SEP USER_MOTOR_SPEED_PID_INTEGRAL_SEP
#define MOTOR_SPEED_SCALE_LEFT_DEFAULT   USER_MOTOR_SPEED_SCALE_LEFT
#define MOTOR_SPEED_SCALE_RIGHT_DEFAULT  USER_MOTOR_SPEED_SCALE_RIGHT

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

/* 速度比例尺设置 (国一方案: 左右编码器分辨率不同必须分别标定)
 * - App_Motor_Set_Speed_Scale: 同时设置左右 (兼容旧调用)
 * - App_Motor_Set_Speed_Scale_Left/Right: 左右独立设置 */
void App_Motor_Set_Speed_Scale(float scale);
void App_Motor_Set_Speed_Scale_Left(float scale);
void App_Motor_Set_Speed_Scale_Right(float scale);

/* 速度比例尺自动标定 (国一方案核心: 速度环可信的前提)
 * 使用方法: 悬空车轮 → 调用此函数 → 自动以 PWM=50 跑1秒测编码器速度
 *          → 计算 scale = encoder_speed/50 → 写入左右独立 scale → RTT 打印结果
 * 标定后把打印的 Scale 值写入 main.c 的 USER_MOTOR_SPEED_SCALE_LEFT/RIGHT */
void App_Motor_Calibrate_Scale(void);

/* 右编码器GPIO中断回调（在main.c的GROUP1 ISR中调用） */
void Right_Encoder_IRQHandler(void);

#endif /* APP_ENCODER_MOTOR_H */
