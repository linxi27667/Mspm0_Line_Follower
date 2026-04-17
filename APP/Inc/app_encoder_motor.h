/**
 * @file    app_encoder_motor.h
 * @brief   霍尔电机应用层声明
 */
#ifndef APP_ENCODER_MOTOR_H
#define APP_ENCODER_MOTOR_H

#include "bsp_encoder_motor.h"

extern bsp_motor_t App_Motor_Left;

void App_Motor_System_Init(void);

#endif /* APP_ENCODER_MOTOR_H */
