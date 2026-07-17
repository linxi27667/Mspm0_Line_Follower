/**
 * @file    bsp_icm42688.c
 * @brief   ICM42688-P register access, conversion, calibration and yaw integration.
 */
#include "bsp_icm42688.h"

#include <math.h>
#include <stddef.h>

#define ICM42688_ACCEL_G_PER_LSB  (4.0f / 32768.0f)
#define ICM42688_GYRO_DPS_PER_LSB (500.0f / 32768.0f)

static void Bsp_Icm42688_End_Transaction(imu_sensor_t *imu)
{
    imu->Cs_Write(true);
}

static bool Bsp_Icm42688_Read_Registers(imu_sensor_t *imu, uint8_t reg,
                                        uint8_t *data, uint16_t len)
{
    uint8_t rx = 0u;
    uint16_t i;

    if (imu == NULL || data == NULL || len == 0u ||
        imu->Spi_Transfer == NULL || imu->Cs_Write == NULL) {
        return false;
    }

    imu->Cs_Write(false);
    if (!imu->Spi_Transfer((uint8_t)(reg | 0x80u), &rx)) {
        Bsp_Icm42688_End_Transaction(imu);
        return false;
    }
    for (i = 0u; i < len; i++) {
        if (!imu->Spi_Transfer(0u, &data[i])) {
            Bsp_Icm42688_End_Transaction(imu);
            return false;
        }
    }
    Bsp_Icm42688_End_Transaction(imu);
    return true;
}

static bool Bsp_Icm42688_Write_Register(imu_sensor_t *imu, uint8_t reg,
                                        uint8_t value)
{
    uint8_t rx = 0u;

    if (imu == NULL || imu->Spi_Transfer == NULL || imu->Cs_Write == NULL) {
        return false;
    }

    imu->Cs_Write(false);
    if (!imu->Spi_Transfer((uint8_t)(reg & 0x7Fu), &rx) ||
        !imu->Spi_Transfer(value, &rx)) {
        Bsp_Icm42688_End_Transaction(imu);
        return false;
    }
    Bsp_Icm42688_End_Transaction(imu);
    return true;
}

static bool Bsp_Icm42688_Read_Register(imu_sensor_t *imu, uint8_t reg,
                                       uint8_t *value)
{
    return Bsp_Icm42688_Read_Registers(imu, reg, value, 1u);
}

static int16_t Bsp_Icm42688_Make_Int16(uint8_t high, uint8_t low)
{
    return (int16_t)(((uint16_t)high << 8) | (uint16_t)low);
}

const char *Bsp_Icm42688_Init_Result_Name(icm42688_init_result_t result)
{
    switch (result) {
    case ICM42688_INIT_OK: return "ok";
    case ICM42688_INIT_INVALID_ARGUMENT: return "invalid_argument";
    case ICM42688_INIT_WHO_READ_FAILED: return "who_read_failed";
    case ICM42688_INIT_WHO_MISMATCH: return "who_mismatch";
    case ICM42688_INIT_RESET_WRITE_FAILED: return "reset_write_failed";
    case ICM42688_INIT_RESET_TIMEOUT: return "reset_timeout";
    case ICM42688_INIT_WHO_AFTER_RESET_READ_FAILED: return "who_after_reset_read_failed";
    case ICM42688_INIT_WHO_AFTER_RESET_MISMATCH: return "who_after_reset_mismatch";
    case ICM42688_INIT_CONFIG_WRITE_FAILED: return "config_write_failed";
    case ICM42688_INIT_CONFIG_READ_FAILED: return "config_read_failed";
    case ICM42688_INIT_CONFIG_MISMATCH: return "config_mismatch";
    default: return "unknown";
    }
}

bool Bsp_Icm42688_Init_Device(imu_sensor_t *imu)
{
    uint8_t who = 0u;
    uint8_t int_status = 0u;
    uint8_t accel_config = 0u;
    uint8_t gyro_config = 0u;
    uint8_t power_config = 0u;
    uint8_t attempt;
    bool reset_done = false;
    bool who_read = false;

    if (imu == NULL) {
        return false;
    }

    imu->initialized = false;
    imu->data_valid = false;
    imu->calibration_state = IMU_CAL_IDLE;
    imu->init_result = ICM42688_INIT_INVALID_ARGUMENT;
    imu->init_who_am_i = 0u;
    imu->init_accel_config = 0u;
    imu->init_gyro_config = 0u;
    imu->init_power_config = 0u;
    imu->gyro_z_offset = 0.0f;
    imu->heading = 0.0f;

    if (imu->Spi_Transfer == NULL || imu->Cs_Write == NULL) {
        return false;
    }
    imu->Cs_Write(true);

    if (!Bsp_Icm42688_Read_Register(imu, ICM42688_WHO_AM_I, &who)) {
        imu->init_result = ICM42688_INIT_WHO_READ_FAILED;
        return false;
    }
    imu->init_who_am_i = who;
    if (who != ICM42688_WHO_AM_I_VALUE) {
        imu->init_result = ICM42688_INIT_WHO_MISMATCH;
        return false;
    }
    if (!Bsp_Icm42688_Write_Register(imu, ICM42688_REG_BANK_SEL, 0u) ||
        !Bsp_Icm42688_Write_Register(imu, ICM42688_DEVICE_CONFIG, 0x01u)) {
        imu->init_result = ICM42688_INIT_RESET_WRITE_FAILED;
        return false;
    }
    for (attempt = 0u; attempt < ICM42688_RESET_POLL_ATTEMPTS; attempt++) {
        if (imu->Delay_ms != NULL) {
            imu->Delay_ms(ICM42688_RESET_POLL_MS);
        }
        if (Bsp_Icm42688_Read_Register(imu, ICM42688_INT_STATUS,
                                       &int_status) &&
            (int_status & ICM42688_RESET_DONE_MASK) != 0u) {
            reset_done = true;
        }
        if (Bsp_Icm42688_Read_Register(imu, ICM42688_WHO_AM_I, &who)) {
            who_read = true;
            imu->init_who_am_i = who;
            if (reset_done && who == ICM42688_WHO_AM_I_VALUE) {
                break;
            }
        }
    }
    if (!reset_done) {
        imu->init_result = ICM42688_INIT_RESET_TIMEOUT;
        return false;
    }
    if (!who_read) {
        imu->init_result = ICM42688_INIT_WHO_AFTER_RESET_READ_FAILED;
        return false;
    }
    if (who != ICM42688_WHO_AM_I_VALUE) {
        imu->init_result = ICM42688_INIT_WHO_AFTER_RESET_MISMATCH;
        return false;
    }
    if (!Bsp_Icm42688_Write_Register(imu, ICM42688_REG_BANK_SEL, 0u) ||
        !Bsp_Icm42688_Write_Register(imu, ICM42688_ACCEL_CONFIG0,
                                     ICM42688_ACCEL_CONFIG_VALUE) ||
        !Bsp_Icm42688_Write_Register(imu, ICM42688_GYRO_CONFIG0,
                                     ICM42688_GYRO_CONFIG_VALUE) ||
        !Bsp_Icm42688_Write_Register(imu, ICM42688_PWR_MGMT0,
                                     ICM42688_PWR_MGMT0_VALUE)) {
        imu->init_result = ICM42688_INIT_CONFIG_WRITE_FAILED;
        return false;
    }
    if (imu->Delay_ms != NULL) {
        imu->Delay_ms(1u);
    }
    if (!Bsp_Icm42688_Read_Register(imu, ICM42688_ACCEL_CONFIG0,
                                    &accel_config)) {
        imu->init_result = ICM42688_INIT_CONFIG_READ_FAILED;
        return false;
    }
    imu->init_accel_config = accel_config;
    if (!Bsp_Icm42688_Read_Register(imu, ICM42688_GYRO_CONFIG0,
                                    &gyro_config)) {
        imu->init_result = ICM42688_INIT_CONFIG_READ_FAILED;
        return false;
    }
    imu->init_gyro_config = gyro_config;
    if (!Bsp_Icm42688_Read_Register(imu, ICM42688_PWR_MGMT0,
                                    &power_config)) {
        imu->init_result = ICM42688_INIT_CONFIG_READ_FAILED;
        return false;
    }
    imu->init_power_config = power_config;
    if (accel_config != ICM42688_ACCEL_CONFIG_VALUE ||
        gyro_config != ICM42688_GYRO_CONFIG_VALUE ||
        (power_config & 0x0Fu) != ICM42688_PWR_MGMT0_VALUE) {
        imu->init_result = ICM42688_INIT_CONFIG_MISMATCH;
        return false;
    }

    imu->initialized = true;
    imu->data_valid = true;
    imu->init_result = ICM42688_INIT_OK;
    return true;
}

bool Bsp_Icm42688_Read_Data(imu_sensor_t *imu)
{
    uint8_t raw[14];
    int16_t raw_temp;
    int16_t raw_ax;
    int16_t raw_ay;
    int16_t raw_az;
    int16_t raw_gx;
    int16_t raw_gy;
    int16_t raw_gz;

    if (imu == NULL || !imu->initialized ||
        !Bsp_Icm42688_Read_Registers(imu, ICM42688_TEMP_DATA1,
                                     raw, sizeof(raw))) {
        if (imu != NULL) {
            imu->data_valid = false;
        }
        return false;
    }

    raw_temp = Bsp_Icm42688_Make_Int16(raw[0], raw[1]);
    raw_ax = Bsp_Icm42688_Make_Int16(raw[2], raw[3]);
    raw_ay = Bsp_Icm42688_Make_Int16(raw[4], raw[5]);
    raw_az = Bsp_Icm42688_Make_Int16(raw[6], raw[7]);
    raw_gx = Bsp_Icm42688_Make_Int16(raw[8], raw[9]);
    raw_gy = Bsp_Icm42688_Make_Int16(raw[10], raw[11]);
    raw_gz = Bsp_Icm42688_Make_Int16(raw[12], raw[13]);

    /* ICM42688-P uses 0x8000 as the invalid-data marker. Never expose it
     * as a legitimate full-scale sample or retain the previous frame. */
    if (raw_temp == INT16_MIN || raw_ax == INT16_MIN || raw_ay == INT16_MIN ||
        raw_az == INT16_MIN || raw_gx == INT16_MIN || raw_gy == INT16_MIN ||
        raw_gz == INT16_MIN) {
        imu->data_valid = false;
        return false;
    }

    imu->temp = ((float)raw_temp / 132.48f) + 25.0f;
    imu->accel_x = (float)raw_ax * ICM42688_ACCEL_G_PER_LSB;
    imu->accel_y = (float)raw_ay * ICM42688_ACCEL_G_PER_LSB;
    imu->accel_z = (float)raw_az * ICM42688_ACCEL_G_PER_LSB;
    imu->gyro_x = (float)raw_gx * ICM42688_GYRO_DPS_PER_LSB;
    imu->gyro_y = (float)raw_gy * ICM42688_GYRO_DPS_PER_LSB;
    imu->gyro_z = (float)raw_gz * ICM42688_GYRO_DPS_PER_LSB *
                  ICM42688_GYRO_Z_SIGN;
    imu->data_valid = isfinite(imu->temp) &&
                      isfinite(imu->accel_x) && isfinite(imu->accel_y) &&
                      isfinite(imu->accel_z) && isfinite(imu->gyro_x) &&
                      isfinite(imu->gyro_y) && isfinite(imu->gyro_z);
    return imu->data_valid;
}

void Bsp_Icm42688_Calibration_Start(imu_sensor_t *imu)
{
    if (imu == NULL) {
        return;
    }
    imu->calibration_sample_count = 0u;
    imu->calibration_read_failures = 0u;
    imu->calibration_mean = 0.0f;
    imu->calibration_m2 = 0.0f;
    imu->gyro_z_offset = 0.0f;
    imu->calibration_state = imu->initialized ? IMU_CAL_RUNNING : IMU_CAL_FAILED;
}

imu_cal_state_t Bsp_Icm42688_Calibration_Update(imu_sensor_t *imu)
{
    float delta;
    float delta2;
    float std_dev;

    if (imu == NULL) {
        return IMU_CAL_FAILED;
    }
    if (imu->calibration_state != IMU_CAL_RUNNING) {
        return imu->calibration_state;
    }
    if (!Bsp_Icm42688_Read_Data(imu)) {
        if (imu->calibration_read_failures < UINT8_MAX) {
            imu->calibration_read_failures++;
        }
        if (imu->calibration_read_failures >=
            ICM42688_CALIB_MAX_READ_FAILURES) {
            imu->calibration_state = IMU_CAL_FAILED;
        }
        return imu->calibration_state;
    }

    imu->calibration_read_failures = 0u;
    imu->calibration_sample_count++;
    delta = imu->gyro_z - imu->calibration_mean;
    imu->calibration_mean += delta / (float)imu->calibration_sample_count;
    delta2 = imu->gyro_z - imu->calibration_mean;
    imu->calibration_m2 += delta * delta2;

    if (imu->calibration_sample_count >= ICM42688_CALIB_SAMPLES) {
        std_dev = sqrtf(imu->calibration_m2 /
                        (float)imu->calibration_sample_count);
        if (!isfinite(std_dev) || std_dev > ICM42688_CALIB_MAX_STD_DPS) {
            imu->calibration_state = IMU_CAL_FAILED;
            imu->data_valid = false;
        } else {
            imu->gyro_z_offset = imu->calibration_mean;
            imu->calibration_state = IMU_CAL_DONE;
        }
    }
    return imu->calibration_state;
}

bool Bsp_Icm42688_Update_Heading(imu_sensor_t *imu, float dt)
{
    float gyro_for_heading;

    if (imu == NULL || !imu->initialized ||
        imu->calibration_state != IMU_CAL_DONE || !isfinite(dt) || dt <= 0.0f ||
        !Bsp_Icm42688_Read_Data(imu)) {
        if (imu != NULL) {
            imu->data_valid = false;
        }
        return false;
    }

    imu->gyro_z -= imu->gyro_z_offset;
    gyro_for_heading = imu->gyro_z;
    if (gyro_for_heading > -ICM42688_GYRO_DEADZONE_DPS &&
        gyro_for_heading < ICM42688_GYRO_DEADZONE_DPS) {
        gyro_for_heading = 0.0f;
    }
    imu->heading += gyro_for_heading * dt;
    if (!isfinite(imu->heading)) {
        imu->data_valid = false;
        return false;
    }
    return true;
}
