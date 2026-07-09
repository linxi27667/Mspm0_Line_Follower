/**
 * @file    bsp_mpu6050.h
 * @brief   MPU6050 传感器驱动层（BSP — 纯逻辑，跨平台）
 * @note    含零偏校准 + Z轴航向积分 + 死区抑制
 *          I2C总线通过函数指针抽象，不依赖具体软件/硬件I2C实现
 */
#ifndef __Bsp_MPU6050_H__
#define __Bsp_MPU6050_H__

#include <stdint.h>
#include <stdbool.h>

/* --- MPU6050 寄存器地址 --- */
#define BSP_MPU_SMPLRT_DIV_REG   0x19
#define BSP_MPU_CONFIG_REG       0x1A
#define BSP_MPU_GYRO_CONFIG_REG  0x1B
#define BSP_MPU_ACCEL_CONFIG_REG 0x1C
#define BSP_MPU_ACCEL_XOUT_H_REG 0x3B
#define BSP_MPU_PWR_MGMT_1_REG   0x6B
#define BSP_MPU_WHO_AM_I_REG     0x75

/* --- 陀螺仪量程灵敏度: ±2000deg/s → 16.4 LSB/(deg/s) --- */
#define BSP_MPU_GYRO_SENS        16.4f

/* --- 零偏校准默认参数 --- */
#define BSP_MPU_CALIB_SAMPLES    200     /* 校准采样次数: 200*10ms=2s */
#define BSP_MPU_CALIB_INTERVAL_MS 10     /* 校准采样间隔 */
#define BSP_MPU_CALIB_MAX_STD    5.0f    /* 标准差阈值(超过则校准失败) */
#define BSP_MPU_GYRO_DEADZONE    0.05f   /* 积分死区(±deg/s)，遥测仍保留减偏置结果 */

/* --- MPU6050 对象 --- */
typedef struct {
    /* --- 1. 总线配置 --- */
    uint8_t       dev_addr;

    /* --- 2. I2C总线抽象（函数指针，APP层绑定软件/硬件实现） --- */
    uint8_t (*I2C_Write_Reg)(uint8_t dev_addr, uint8_t reg_addr, const uint8_t *data, uint16_t len);
    uint8_t (*I2C_Read_Reg)(uint8_t dev_addr, uint8_t reg_addr, uint8_t *data, uint16_t len);

    /* --- 3. 原始传感器数据 --- */
    float accel_x, accel_y, accel_z;
    float gyro_x, gyro_y, gyro_z;
    float temp;

    /* --- 4. 陀螺仪校准/航向 --- */
    float    gyro_z_offset;      /* Z轴零偏(deg/s)，校准得到 */
    float    heading;            /* 累计航向角(deg)，积分得到 */
    bool     gyro_ok;            /* 初始化成功标志 */
    bool     calibrated;         /* 零偏校准完成标志 */

    /* --- 5. 抽象延时方法 --- */
    void (*Delay_ms)(uint32_t ms);
} bsp_mpu_t;

/* --- API --- */

/* 初始化 MPU6050（I2C通信 + 寄存器配置） */
uint8_t Bsp_MPU6050_Init_Device(bsp_mpu_t *mpu);

/* 读取全部传感器数据（加速度+陀螺仪+温度） */
void Bsp_MPU6050_Read_Data(bsp_mpu_t *mpu);

/* 零偏校准（静态采集N次，计算均值和标准差） */
void Bsp_MPU6050_Calibrate(bsp_mpu_t *mpu);

/* 更新航向角（读取陀螺仪 + 减零偏 + 死区 + 积分）
 * dt: 积分步长(秒)，例如5ms周期传入0.005f */
void Bsp_MPU6050_Update_Heading(bsp_mpu_t *mpu, float dt);

#endif /* __Bsp_MPU6050_H__ */
