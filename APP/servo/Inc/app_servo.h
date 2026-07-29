/**
 * @file    app_servo.h
 * @brief   舵机应用层声明
 */
#ifndef APP_SERVO_H
#define APP_SERVO_H

#include "bsp_servo.h"

/* ============ 舵机硬件配置 ============ */
/* PA12 → TIMG0_C0 (50Hz PWM, J4_24, IOMUX_PINCM34) */
#define SERVO_PWM_TIMER         TIMG0
#define SERVO_PWM_CHANNEL       0
#define SERVO_PWM_IOMUX         IOMUX_PINCM34
#define SERVO_PWM_IOMUX_FUNC    IOMUX_PINCM34_PF_TIMG0_CCP0

extern bsp_servo_t App_Servo_1;

void App_Servo_System_Init(void);

#endif /* APP_SERVO_H */
