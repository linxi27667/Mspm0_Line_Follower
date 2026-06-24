/**
 * @file    app_servo.h
 * @brief   舵机应用层声明（硬件绑定 + 业务逻辑入口）
 */
#ifndef APP_SERVO_H
#define APP_SERVO_H

#include "bsp_servo.h"

/* ============ 舵机1硬件配置 ============ */
#define SERVO_1_PWM_TIMER           TIMER_G0
#define SERVO_1_PWM_CHANNEL         0

/* ============ 业务接口声明 ============ */
extern bsp_servo_t App_Servo_1;

void App_Servo_System_Init(void);
void App_Servo_Set_Angle(float angle);

#endif /* APP_SERVO_H */
