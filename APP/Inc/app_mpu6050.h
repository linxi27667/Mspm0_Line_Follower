/**
 * @file    app_mpu6050.h
 * @brief   MPU6050应用层声明（硬件绑定 + 业务逻辑入口）
 */
#ifndef APP_MPU6050_H
#define APP_MPU6050_H

#include "bsp_mpu6050.h"

/* ============ MPU6050硬件配置 ============ */
#define MPU6050_DEV_ADDR           0x68

/* ============ 业务接口声明 ============ */
extern bsp_mpu_t App_MPU;

void App_MPU6050_System_Init(void);
void App_MPU6050_Read_Data(void);

#endif /* APP_MPU6050_H */
