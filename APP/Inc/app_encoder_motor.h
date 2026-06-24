/**
 * @file    app_encoder_motor.h
 * @brief   霍尔编码器电机应用层声明（硬件绑定 + 业务逻辑入口）
 */
#ifndef APP_ENCODER_MOTOR_H
#define APP_ENCODER_MOTOR_H

#include "bsp_encoder_motor.h"

/* ============ 左电机硬件配置 ============ */
#define MOTOR_LEFT_PWM_TIMER        TIMG7
#define MOTOR_LEFT_PWM_CHANNEL      0
#define MOTOR_LEFT_ENC_TIMER        TIMG8
#define MOTOR_LEFT_DIR1_PORT        GPIOA
#define MOTOR_LEFT_DIR1_PIN         DL_GPIO_PIN_14
#define MOTOR_LEFT_DIR2_PORT        GPIOA
#define MOTOR_LEFT_DIR2_PIN         DL_GPIO_PIN_15

/* ============ 右电机硬件配置 ============ */
/* PB10 = TIMG6-C0 (PINCM27), PA18=纯GPIO, PA13=GPIO */
/* 右编码器暂未实现: MSPM0G3507的QEI仅支持TIMG8(已被左电机占用)
 * 当前循迹不依赖右编码器，灰度+陀螺仪足够 */
#define MOTOR_RIGHT_PWM_TIMER       TIMG6
#define MOTOR_RIGHT_PWM_CHANNEL     0
#define MOTOR_RIGHT_ENC_TIMER       NULL
#define MOTOR_RIGHT_DIR1_PORT       GPIOA
#define MOTOR_RIGHT_DIR1_PIN        DL_GPIO_PIN_13
#define MOTOR_RIGHT_DIR2_PORT       GPIOA
#define MOTOR_RIGHT_DIR2_PIN        DL_GPIO_PIN_18

/* ============ 业务接口声明 ============ */
extern bsp_motor_t App_Motor_Left;
extern bsp_motor_t App_Motor_Right;

void App_Motor_System_Init(void);
void App_Motor_Set_Speed(int32_t speed);
void App_Motor_Right_Set_Speed(int32_t speed);
void App_Motor_Forward(int32_t speed);
void App_Motor_Backward(int32_t speed);
void App_Motor_Stop(void);
void App_Motor_Update_Status(void);

#endif /* APP_ENCODER_MOTOR_H */
