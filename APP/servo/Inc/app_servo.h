/**
 * @file    app_servo.h
 * @brief   舵机应用层声明
 */
#ifndef APP_SERVO_H
#define APP_SERVO_H

#include "bsp_servo.h"

extern bsp_servo_t App_Servo_1;

void App_Servo_System_Init(void);

#endif /* APP_SERVO_H */
