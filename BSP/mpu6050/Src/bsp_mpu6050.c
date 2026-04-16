/**
 * @file    bsp_mpu6050.c
 * @brief   MPU6050 驱动实现
 */
#include "bsp_mpu6050.h"
#include "bsp_sw_i2c.h"

uint8_t BSP_MPU6050_Init_Device(bsp_mpu_t *mpu)
{
    if (mpu == NULL || mpu->bus == NULL) return 1;

    uint8_t check_id = 0;
    BSP_I2C_Read_Reg(mpu->bus, mpu->dev_addr, BSP_MPU_WHO_AM_I_REG, &check_id, 1);
    if (check_id != 0x68 && check_id != 0x71) return 1;

    uint8_t w = 0x00;
    BSP_I2C_Write_Reg(mpu->bus, mpu->dev_addr, BSP_MPU_PWR_MGMT_1_REG, &w, 1);
    if (mpu->Delay_ms) mpu->Delay_ms(50);

    w = 0x07;
    BSP_I2C_Write_Reg(mpu->bus, mpu->dev_addr, BSP_MPU_SMPLRT_DIV_REG, &w, 1);

    w = 0x06;
    BSP_I2C_Write_Reg(mpu->bus, mpu->dev_addr, BSP_MPU_CONFIG_REG, &w, 1);

    w = 0x00;
    BSP_I2C_Write_Reg(mpu->bus, mpu->dev_addr, BSP_MPU_ACCEL_CONFIG_REG, &w, 1);

    w = 0x18;
    BSP_I2C_Write_Reg(mpu->bus, mpu->dev_addr, BSP_MPU_GYRO_CONFIG_REG, &w, 1);

    return 0;
}

void BSP_MPU6050_Read_Data(bsp_mpu_t *mpu)
{
    if (mpu == NULL || mpu->bus == NULL) return;

    uint8_t raw[14];
    if (BSP_I2C_Read_Reg(mpu->bus, mpu->dev_addr, BSP_MPU_ACCEL_XOUT_H_REG, raw, 14) != 0) return;

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
    mpu->gyro_x  = (float)gx / 16.4f;
    mpu->gyro_y  = (float)gy / 16.4f;
    mpu->gyro_z  = (float)gz / 16.4f;
}
