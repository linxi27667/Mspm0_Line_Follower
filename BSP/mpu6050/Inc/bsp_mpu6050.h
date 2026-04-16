/**
 * @file    bsp_mpu6050.h
 * @brief   MPU6050 传感器驱动层（BSP — 纯逻辑，跨平台）
 */
#ifndef __BSP_MPU6050_H__
#define __BSP_MPU6050_H__

#include <stdint.h>
#include "bsp_sw_i2c.h"

#define BSP_MPU_SMPLRT_DIV_REG   0x19
#define BSP_MPU_CONFIG_REG       0x1A
#define BSP_MPU_GYRO_CONFIG_REG  0x1B
#define BSP_MPU_ACCEL_CONFIG_REG 0x1C
#define BSP_MPU_ACCEL_XOUT_H_REG 0x3B
#define BSP_MPU_PWR_MGMT_1_REG   0x6B
#define BSP_MPU_WHO_AM_I_REG     0x75

typedef struct {
    bsp_sw_i2c_t *bus;
    uint8_t dev_addr;

    float accel_x, accel_y, accel_z;
    float gyro_x, gyro_y, gyro_z;
    float temp;

    void (*Delay_ms)(uint32_t ms);
} bsp_mpu_t;

uint8_t BSP_MPU6050_Init_Device(bsp_mpu_t *mpu);
void    BSP_MPU6050_Read_Data(bsp_mpu_t *mpu);

#endif /* __BSP_MPU6050_H__ */
