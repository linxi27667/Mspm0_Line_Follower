/**
 * @file    bsp_icm42688.h
 * @brief   ICM42688-P sensor logic with an abstract SPI transport.
 */
#ifndef BSP_ICM42688_H
#define BSP_ICM42688_H

#include <stdbool.h>
#include <stdint.h>

#define ICM42688_DEVICE_CONFIG       0x11u
#define ICM42688_TEMP_DATA1          0x1Du
#define ICM42688_ACCEL_DATA_X1       0x1Fu
#define ICM42688_ACCEL_DATA_Y1       0x21u
#define ICM42688_ACCEL_DATA_Z1       0x23u
#define ICM42688_GYRO_DATA_X1        0x25u
#define ICM42688_GYRO_DATA_Y1        0x27u
#define ICM42688_GYRO_DATA_Z1        0x29u
#define ICM42688_PWR_MGMT0           0x4Eu
#define ICM42688_GYRO_CONFIG0        0x4Fu
#define ICM42688_ACCEL_CONFIG0       0x50u
#define ICM42688_WHO_AM_I            0x75u
#define ICM42688_REG_BANK_SEL        0x76u
#define ICM42688_WHO_AM_I_VALUE      0x47u

#define ICM42688_ACCEL_CONFIG_VALUE  0x4Fu
#define ICM42688_GYRO_CONFIG_VALUE   0x4Fu
#define ICM42688_PWR_MGMT0_VALUE     0x0Fu

#define ICM42688_CALIB_SAMPLES       200u
#define ICM42688_CALIB_MAX_STD_DPS   5.0f
#define ICM42688_GYRO_DEADZONE_DPS   0.05f
#define ICM42688_GYRO_Z_SIGN         1.0f

typedef enum {
    IMU_CAL_IDLE = 0,
    IMU_CAL_RUNNING,
    IMU_CAL_DONE,
    IMU_CAL_FAILED
} imu_cal_state_t;

typedef struct {
    bool (*Spi_Transfer)(uint8_t tx, uint8_t *rx);
    void (*Cs_Write)(bool high);
    void (*Delay_ms)(uint32_t ms);

    float accel_x;
    float accel_y;
    float accel_z;
    float gyro_x;
    float gyro_y;
    float gyro_z;
    float temp;
    float gyro_z_offset;
    float heading;

    bool initialized;
    bool data_valid;
    imu_cal_state_t calibration_state;

    uint16_t calibration_sample_count;
    float calibration_mean;
    float calibration_m2;
} imu_sensor_t;

bool Bsp_Icm42688_Init_Device(imu_sensor_t *imu);
bool Bsp_Icm42688_Read_Data(imu_sensor_t *imu);
void Bsp_Icm42688_Calibration_Start(imu_sensor_t *imu);
imu_cal_state_t Bsp_Icm42688_Calibration_Update(imu_sensor_t *imu);
bool Bsp_Icm42688_Update_Heading(imu_sensor_t *imu, float dt);

#endif /* BSP_ICM42688_H */
