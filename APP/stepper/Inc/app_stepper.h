/**
 * @file    app_stepper.h
 * @brief   步进电机应用层声明
 */
#ifndef APP_STEPPER_H
#define APP_STEPPER_H

#include "bsp_stepper.h"

extern bsp_stepper_t App_Stepper_X;

void App_Stepper_System_Init(void);

#endif /* APP_STEPPER_H */
