/**
 * @file    app_imu.c
 * @brief   MSPM0 SPI1 binding for the ICM42688-P.
 */
#include "app_imu.h"

#include "app_common.h"
#include "app_log.h"
#include "bsp_common.h"
#include "ti_msp_dl_config.h"

#define IMU_SPI_TRANSACTION_TIMEOUT_MS 1u

static uint32_t s_transaction_started_at;

static bool HW_Spi_Timed_Out(void)
{
    return (uint32_t)(Bsp_GetTick() - s_transaction_started_at) >=
           IMU_SPI_TRANSACTION_TIMEOUT_MS;
}

static void HW_Spi_Flush_Rx(void)
{
    while (!DL_SPI_isRXFIFOEmpty(ICM_SPI_INST)) {
        (void)DL_SPI_receiveData8(ICM_SPI_INST);
    }
}

static void HW_Imu_Cs_Write(bool high)
{
    if (high) {
        DL_GPIO_setPins(ICM_CS_PORT, ICM_CS_CS_PIN);
    } else {
        HW_Spi_Flush_Rx();
        s_transaction_started_at = Bsp_GetTick();
        DL_GPIO_clearPins(ICM_CS_PORT, ICM_CS_CS_PIN);
    }
}

static bool HW_Imu_Spi_Transfer(uint8_t tx, uint8_t *rx)
{
    if (rx == NULL) {
        return false;
    }
    while (DL_SPI_isTXFIFOFull(ICM_SPI_INST)) {
        if (HW_Spi_Timed_Out()) {
            return false;
        }
    }
    DL_SPI_transmitData8(ICM_SPI_INST, tx);
    while (DL_SPI_isRXFIFOEmpty(ICM_SPI_INST)) {
        if (HW_Spi_Timed_Out()) {
            return false;
        }
    }
    *rx = DL_SPI_receiveData8(ICM_SPI_INST);
    while (DL_SPI_isBusy(ICM_SPI_INST)) {
        if (HW_Spi_Timed_Out()) {
            return false;
        }
    }
    return true;
}

static void HW_Imu_Delay_ms(uint32_t ms)
{
    Bsp_Delay_ms(ms);
}

imu_sensor_t Imu_Sensor = {
    .Spi_Transfer = HW_Imu_Spi_Transfer,
    .Cs_Write = HW_Imu_Cs_Write,
    .Delay_ms = HW_Imu_Delay_ms,
    .initialized = false,
    .data_valid = false,
    .calibration_state = IMU_CAL_IDLE,
};

bool App_Imu_Init(void)
{
    bool ok;

    HW_Imu_Cs_Write(true);
    HW_Spi_Flush_Rx();
    ok = Bsp_Icm42688_Init_Device(&Imu_Sensor);
    if (ok) {
        APP_IMU_LOG_I("IMU", "[IMU] ICM42688-P init OK: SPI1 mode3 1MHz, gyro=+-500dps ODR=500Hz");
    } else {
        APP_IMU_LOG_E("IMU", "[IMU] ICM42688-P init failed: WHO/config/SPI error");
    }
    return ok;
}

bool Imu_Read_Data(void)
{
    return Bsp_Icm42688_Read_Data(&Imu_Sensor);
}

void Imu_Calibration_Start(void)
{
    Bsp_Icm42688_Calibration_Start(&Imu_Sensor);
    APP_IMU_LOG_I("IMU", "[IMU] gyro calibration start: keep car still, samples=%u",
                  ICM42688_CALIB_SAMPLES);
}

imu_cal_state_t Imu_Calibration_Update(void)
{
    imu_cal_state_t previous = Imu_Sensor.calibration_state;
    imu_cal_state_t current =
        Bsp_Icm42688_Calibration_Update(&Imu_Sensor);

    if (previous != current && current == IMU_CAL_DONE) {
        APP_IMU_LOG_I("IMU", "[IMU] gyro calibration done: bias=%.3f dps",
                      (double)Imu_Sensor.gyro_z_offset);
    } else if (previous != current && current == IMU_CAL_FAILED) {
        APP_IMU_LOG_E("IMU", "[IMU] gyro calibration failed");
    }
    return current;
}

bool Imu_Update_Heading(float dt)
{
    return Bsp_Icm42688_Update_Heading(&Imu_Sensor, dt);
}
