/**
 * @file    track_gyro.h
 * @brief   MPU6050陀螺仪驱动（TASK层 — 软件I2C直驱）
 * @note    硬件连接:
 *          - SCL: PB8 (PINCM25)
 *          - SDA: PB9 (PINCM26)
 */
#ifndef __TRACK_GYRO_H__
#define __TRACK_GYRO_H__

#include <stdint.h>
#include <stdbool.h>

/* ============================================================
 * 陀螺仪宏定义
 * ============================================================ */

/* 编译期开关：是否使用 MPU6050 */
#define TRACK_USE_MPU6050       1

/* I2C 引脚定义 */
#define TRACK_I2C_SCL_PORT      GPIOB
#define TRACK_I2C_SCL_PIN       DL_GPIO_PIN_8
#define TRACK_I2C_SCL_IOMUX     IOMUX_PINCM25
#define TRACK_I2C_SDA_PORT      GPIOB
#define TRACK_I2C_SDA_PIN       DL_GPIO_PIN_9
#define TRACK_I2C_SDA_IOMUX     IOMUX_PINCM26

/* MPU6050 设备地址和寄存器 */
#define TRACK_MPU6050_ADDR      0x68
#define TRACK_MPU_WHO_AM_I      0x75
#define TRACK_MPU_PWR_MGMT_1    0x6B
#define TRACK_MPU_SMPLRT_DIV    0x19
#define TRACK_MPU_CONFIG        0x1A
#define TRACK_MPU_ACCEL_CONFIG  0x1C
#define TRACK_MPU_GYRO_CONFIG   0x1B
#define TRACK_MPU_ACCEL_XOUT_H  0x3B

/* 陀螺仪量程灵敏度: ±2000deg/s → 16.4 LSB/(deg/s) */
#define TRACK_MPU_GYRO_SENS     16.4f

/* I2C 时序延时(us) */
#define TRACK_I2C_DELAY_US      2

/* 零偏校准采样次数（上电静态采集） */
#define TRACK_GYRO_CALIB_SAMPLES    500

/* 零偏校准阈值：采样标准差超过此值说明有运动，校准失败 */
#define TRACK_GYRO_CALIB_MAX_STD    5.0f

/* ============================================================
 * 陀螺仪数据结构
 * ============================================================ */
typedef struct {
    float    gyro_z;                /* Z轴角速度(deg/s)，已减零偏 */
    float    heading;               /* 累计航向角(deg) */
    float    gyro_z_offset;         /* Z轴零偏(deg/s)，校准得到 */
    uint8_t  gyro_ok;               /* 初始化成功标志 */
    uint8_t  calibrated;            /* 零偏校准完成标志 */
} Track_Gyro_t;

/* ============================================================
 * 陀螺仪接口
 * ============================================================ */

/* 外部全局对象 */
extern Track_Gyro_t Track_Gyro;

/* 初始化 MPU6050（含 I2C 引脚配置 + 零偏校准） */
void Track_Gyro_Init(void);

/* 读取陀螺仪Z轴数据并积分航向角（5ms周期调用） */
void Track_Gyro_Read(void);

#endif /* __TRACK_GYRO_H__ */
