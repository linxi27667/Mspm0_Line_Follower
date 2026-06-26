/**
 * @file    bsp_mpu6050.c
 * @brief   MPU6050 驱动实现（BSP — 纯逻辑，跨平台）
 * @note    含零偏校准 + Z轴航向积分 + 死区抑制
 *          I2C操作通过函数指针调用，不依赖具体总线实现
 */
#include "bsp_mpu6050.h"
#include <elog.h>
#include <stddef.h>
#include <math.h>

/* ================= 1. 设备初始化 ================= */
uint8_t Bsp_MPU6050_Init_Device(bsp_mpu_t *mpu)
{
    if (mpu == NULL || mpu->I2C_Write_Reg == NULL || mpu->I2C_Read_Reg == NULL) return 1;

    mpu->gyro_ok       = false;
    mpu->calibrated    = false;
    mpu->gyro_z_offset = 0;
    mpu->heading       = 0;

    /* 检查 WHO_AM_I — 接受 MPU6050(0x68)/MPU9250(0x71)/MPU6500(0x70) */
    uint8_t check_id = 0;
    uint8_t ret = mpu->I2C_Read_Reg(mpu->dev_addr, BSP_MPU_WHO_AM_I_REG, &check_id, 1);
    if (check_id != 0x68 && check_id != 0x70 && check_id != 0x71) {
        elog_e("MPU", "WHO_AM_I fail: ret=%d id=0x%02X addr=0x%02X",
               ret, check_id, mpu->dev_addr);
        return 1;
    }
    elog_i("MPU", "WHO_AM_I OK: id=0x%02X addr=0x%02X", check_id, mpu->dev_addr);

    /* 唤醒 */
    uint8_t w = 0x00;
    mpu->I2C_Write_Reg(mpu->dev_addr, BSP_MPU_PWR_MGMT_1_REG, &w, 1);
    if (mpu->Delay_ms) mpu->Delay_ms(50);

    /* 采样率分频器: 1kHz / (1+7) = 125Hz */
    w = 0x07;
    mpu->I2C_Write_Reg(mpu->dev_addr, BSP_MPU_SMPLRT_DIV_REG, &w, 1);

    /* 低通滤波: 44Hz (CONFIG=0x03) */
    w = 0x03;
    mpu->I2C_Write_Reg(mpu->dev_addr, BSP_MPU_CONFIG_REG, &w, 1);

    /* 加速度量程: ±2g */
    w = 0x00;
    mpu->I2C_Write_Reg(mpu->dev_addr, BSP_MPU_ACCEL_CONFIG_REG, &w, 1);

    /* 陀螺仪量程: ±2000deg/s */
    w = 0x18;
    mpu->I2C_Write_Reg(mpu->dev_addr, BSP_MPU_GYRO_CONFIG_REG, &w, 1);

    mpu->gyro_ok = true;
    return 0;
}

/* ================= 2. 读取传感器数据 ================= */
void Bsp_MPU6050_Read_Data(bsp_mpu_t *mpu)
{
    if (mpu == NULL || mpu->I2C_Read_Reg == NULL) return;

    uint8_t raw[14];
    if (mpu->I2C_Read_Reg(mpu->dev_addr, BSP_MPU_ACCEL_XOUT_H_REG, raw, 14) != 0) return;

    int16_t ax = (int16_t)((raw[0] << 8) | raw[1]);
    int16_t ay = (int16_t)((raw[2] << 8) | raw[3]);
    int16_t az = (int16_t)((raw[4] << 8) | raw[5]);
    int16_t tp = (int16_t)((raw[6] << 8) | raw[7]);
    int16_t gx = (int16_t)((raw[8] << 8) | raw[9]);
    int16_t gy = (int16_t)((raw[10] << 8) | raw[11]);
    int16_t gz = (int16_t)((raw[12] << 8) | raw[13]);

    mpu->accel_x = (float)ax / 16384.0f;
    mpu->accel_y = (float)ay / 16384.0f;
    mpu->accel_z = (float)az / 16384.0f;
    mpu->temp    = 36.53f + ((float)tp / 340.0f);
    mpu->gyro_x  = (float)gx / BSP_MPU_GYRO_SENS;
    mpu->gyro_y  = (float)gy / BSP_MPU_GYRO_SENS;
    mpu->gyro_z  = (float)gz / BSP_MPU_GYRO_SENS;
}

/* ================= 3. 零偏校准 ================= */
void Bsp_MPU6050_Calibrate(bsp_mpu_t *mpu)
{
    if (mpu == NULL || mpu->I2C_Read_Reg == NULL || !mpu->gyro_ok) {
        mpu->calibrated = false;
        return;
    }

    float sum = 0, sum_sq = 0;
    float samples[BSP_MPU_CALIB_SAMPLES];

    /* 采集 N 个样本 */
    for (uint16_t i = 0; i < BSP_MPU_CALIB_SAMPLES; i++) {
        uint8_t raw[14];
        if (mpu->I2C_Read_Reg(mpu->dev_addr, BSP_MPU_ACCEL_XOUT_H_REG, raw, 14) != 0) {
            mpu->calibrated = false;
            return;
        }
        int16_t gz = (int16_t)((raw[12] << 8) | raw[13]);
        samples[i] = (float)gz / BSP_MPU_GYRO_SENS;
        sum += samples[i];
        if (mpu->Delay_ms) mpu->Delay_ms(1);
    }

    /* 计算均值 */
    float mean = sum / BSP_MPU_CALIB_SAMPLES;

    /* 计算标准差（判断是否有运动） */
    for (uint16_t i = 0; i < BSP_MPU_CALIB_SAMPLES; i++) {
        float diff = samples[i] - mean;
        sum_sq += diff * diff;
    }
    float std_dev = sqrtf(sum_sq / BSP_MPU_CALIB_SAMPLES);

    /* 标准差过大说明校准期间有运动，放弃校准 */
    if (std_dev > BSP_MPU_CALIB_MAX_STD) {
        mpu->calibrated = false;
        return;
    }

    mpu->gyro_z_offset = mean;
    mpu->calibrated = true;
}

/* ================= 4. 航向角更新 ================= */
void Bsp_MPU6050_Update_Heading(bsp_mpu_t *mpu, float dt)
{
    if (mpu == NULL || !mpu->gyro_ok) return;

    /* 读取最新数据 */
    Bsp_MPU6050_Read_Data(mpu);

    /* 减去零偏 */
    if (mpu->calibrated) {
        mpu->gyro_z -= mpu->gyro_z_offset;
    }

    /* 死区：极小角速度视为零（抑制静态漂移） */
    if (mpu->gyro_z > -BSP_MPU_GYRO_DEADZONE &&
        mpu->gyro_z <  BSP_MPU_GYRO_DEADZONE) {
        mpu->gyro_z = 0;
    }

    /* 积分得到航向角 */
    mpu->heading += mpu->gyro_z * dt;
}
