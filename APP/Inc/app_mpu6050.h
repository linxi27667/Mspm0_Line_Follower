/**
 * @file    app_mpu6050.h
 * @brief   MPU6050 应用层声明
 */
#ifndef APP_MPU6050_H
#define APP_MPU6050_H

#include "bsp_mpu6050.h"

extern bsp_mpu_t App_MPU;

void App_MPU6050_System_Init(void);

#endif /* APP_MPU6050_H */
