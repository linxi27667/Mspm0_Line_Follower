/**
 * @file    app_servo.h
 * @brief   舵机应用层声明（硬件绑定 + 业务逻辑入口）
 */
#ifndef APP_SERVO_H
#define APP_SERVO_H

#include "bsp_servo.h"

/* ============ 舵机1硬件配置 ============ */
/* 舵机PWM由APP层手动配置（SysConfig不支持prescale）
 * TIMG12, PB20, 50Hz: BUSCLK/8/(3+1)=1MHz, period=20000 */
#define SERVO_1_PWM_TIMER           TIMG12
#define SERVO_1_PWM_CHANNEL         DL_TIMER_CC_0_INDEX
#define SERVO_1_PWM_PINCM           IOMUX_PINCM48  /* PB20 = TIMG12_CCP0 */

/* ============ 业务接口声明 ============ */
extern bsp_servo_t Servo_1;

void App_Servo_Init(void);
void Servo_Set_Angle(float angle);

#endif /* APP_SERVO_H */
