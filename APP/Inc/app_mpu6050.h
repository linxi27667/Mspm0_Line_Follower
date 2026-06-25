/**
 * @file    app_mpu6050.h
 * @brief   MPU6050应用层声明（硬件绑定 + 业务逻辑入口）
 * @note    通过 MPU6050_USE_HW_I2C 宏切换软件/硬件I2C:
 *          0 = 软件I2C (默认，PB8=SCL, PB9=SDA)
 *          1 = 硬件I2C (需在SysConfig中配置I2C实例)
 */
#ifndef APP_MPU6050_H
#define APP_MPU6050_H

#include "bsp_mpu6050.h"

/* ============ I2C模式选择 ============ */
/* 0: 软件I2C (PB8=SCL, PB9=SDA)   1: 硬件I2C (PA0=SDA, PA1=SCL) */
#define MPU6050_USE_HW_I2C      1

/* ============ MPU6050硬件配置 ============ */
#define MPU6050_DEV_ADDR           0x68

#if MPU6050_USE_HW_I2C
/* 硬件I2C实例（SysConfig中 MPU6050_I2C 生成） */
#define MPU6050_HW_I2C_INST       MPU6050_I2C_INST
#else
/* 软件I2C引脚配置 */
#define MPU6050_SW_I2C_SCL_PORT   GPIOB
#define MPU6050_SW_I2C_SCL_PIN    DL_GPIO_PIN_8
#define MPU6050_SW_I2C_SDA_PORT   GPIOB
#define MPU6050_SW_I2C_SDA_PIN    DL_GPIO_PIN_9
#endif

/* ============ 业务接口声明 ============ */
extern bsp_mpu_t Mpu_Sensor;

/* 初始化MPU6050（含I2C总线初始化 + 寄存器配置） */
void App_Mpu_Init(void);

/* 读取全部传感器数据 */
void Mpu_Read_Data(void);

/* 零偏校准（静态采集，阻塞约0.5秒） */
void Mpu_Calibrate(void);

/* 更新航向角（读取 + 减零偏 + 死区 + 积分）
 * dt: 积分步长(秒)，例如5ms周期传入0.005f */
void Mpu_Update_Heading(float dt);

#endif /* APP_MPU6050_H */
