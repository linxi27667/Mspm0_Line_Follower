/**
 * @file    app_servo.h
 * @brief   Pen lift servo on PA12/TIMG0_CCP0.
 */
#ifndef APP_SERVO_H
#define APP_SERVO_H

#include "bsp_servo.h"

#define APP_SERVO_PEN_DOWN_ANGLE_DEG     (0.0f)
#define APP_SERVO_PEN_UP_ANGLE_DEG       (90.0f)

extern bsp_servo_t App_Servo_1;

int8_t App_Servo_System_Init(void);
void App_Servo_Set_Angle(float angle_deg);
void App_Servo_Pen_Up(void);
void App_Servo_Pen_Down(void);
float App_Servo_Get_Angle(void);

#endif /* APP_SERVO_H */
