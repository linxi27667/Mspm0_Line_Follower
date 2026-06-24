/**
 * @file    track_gyro.c
 * @brief   MPU6050陀螺仪驱动实现 — 软件I2C直驱 + 零偏校准
 */
#include "track_gyro.h"

#if TRACK_USE_MPU6050

#include "ti_msp_dl_config.h"
#include <math.h>

/* systick_ms 定义在 main.c */
extern volatile uint32_t systick_ms;

/* ============================================================
 * 全局对象
 * ============================================================ */
Track_Gyro_t Track_Gyro = {0};

/* ============================================================
 * 时标工具
 * ============================================================ */
static void Track_Delay_ms(uint32_t ms)
{
    uint32_t start = systick_ms;
    while ((systick_ms - start) < ms) { }
}

static void Track_Delay_us(uint32_t us)
{
    uint32_t ticks = us * 8;
    while (ticks--) {
        __asm("nop");
    }
}

/* ============================================================
 * I2C 基础操作宏
 * ============================================================ */
#define I2C_SCL_H()   DL_GPIO_setPins  (TRACK_I2C_SCL_PORT, TRACK_I2C_SCL_PIN)
#define I2C_SCL_L()   DL_GPIO_clearPins(TRACK_I2C_SCL_PORT, TRACK_I2C_SCL_PIN)
#define I2C_SDA_H()   DL_GPIO_setPins  (TRACK_I2C_SDA_PORT, TRACK_I2C_SDA_PIN)
#define I2C_SDA_L()   DL_GPIO_clearPins(TRACK_I2C_SDA_PORT, TRACK_I2C_SDA_PIN)
#define I2C_SDA_READ() ((DL_GPIO_readPins(TRACK_I2C_SDA_PORT, TRACK_I2C_SDA_PIN) != 0) ? 1 : 0)
#define I2C_DELAY()   Track_Delay_us(TRACK_I2C_DELAY_US)

/* ============================================================
 * I2C 时序函数
 * ============================================================ */

static void Track_I2C_Start(void)
{
    I2C_SDA_H(); I2C_SCL_H(); I2C_DELAY();
    I2C_SDA_L(); I2C_DELAY();
    I2C_SCL_L(); I2C_DELAY();
}

static void Track_I2C_Stop(void)
{
    I2C_SDA_L(); I2C_SCL_L(); I2C_DELAY();
    I2C_SCL_H(); I2C_DELAY();
    I2C_SDA_H(); I2C_DELAY();
}

static uint8_t Track_I2C_WaitAck(void)
{
    uint8_t timeout = 0;
    I2C_SDA_H(); I2C_DELAY();
    I2C_SCL_H(); I2C_DELAY();
    while (I2C_SDA_READ()) {
        timeout++;
        if (timeout > 250) { Track_I2C_Stop(); return 1; }
    }
    I2C_SCL_L(); I2C_DELAY();
    return 0;
}

static void Track_I2C_SendByte(uint8_t data)
{
    for (uint8_t i = 0; i < 8; i++) {
        if (data & 0x80) I2C_SDA_H(); else I2C_SDA_L();
        I2C_DELAY(); I2C_SCL_H(); I2C_DELAY();
        I2C_SCL_L(); I2C_DELAY();
        data <<= 1;
    }
}

static uint8_t Track_I2C_ReadByte(uint8_t ack)
{
    uint8_t data = 0;
    I2C_SDA_H();
    for (uint8_t i = 0; i < 8; i++) {
        data <<= 1; I2C_SCL_H(); I2C_DELAY();
        if (I2C_SDA_READ()) data++;
        I2C_SCL_L(); I2C_DELAY();
    }
    if (ack) I2C_SDA_L(); else I2C_SDA_H();
    I2C_DELAY(); I2C_SCL_H(); I2C_DELAY();
    I2C_SCL_L(); I2C_DELAY();
    return data;
}

/* ============================================================
 * I2C 寄存器读写
 * ============================================================ */

static uint8_t Track_I2C_WriteReg(uint8_t dev_addr, uint8_t reg, const uint8_t *data, uint16_t len)
{
    Track_I2C_Start();
    Track_I2C_SendByte(dev_addr << 1);
    if (Track_I2C_WaitAck()) { Track_I2C_Stop(); return 1; }
    Track_I2C_SendByte(reg);
    if (Track_I2C_WaitAck()) { Track_I2C_Stop(); return 1; }
    for (uint16_t i = 0; i < len; i++) {
        Track_I2C_SendByte(data[i]);
        if (Track_I2C_WaitAck()) { Track_I2C_Stop(); return 1; }
    }
    Track_I2C_Stop();
    return 0;
}

static uint8_t Track_I2C_ReadReg(uint8_t dev_addr, uint8_t reg, uint8_t *data, uint16_t len)
{
    Track_I2C_Start();
    Track_I2C_SendByte(dev_addr << 1);
    if (Track_I2C_WaitAck()) { Track_I2C_Stop(); return 1; }
    Track_I2C_SendByte(reg);
    if (Track_I2C_WaitAck()) { Track_I2C_Stop(); return 1; }
    Track_I2C_Start();
    Track_I2C_SendByte((dev_addr << 1) | 1);
    if (Track_I2C_WaitAck()) { Track_I2C_Stop(); return 1; }
    for (uint16_t i = 0; i < len; i++) {
        data[i] = Track_I2C_ReadByte((i == (len - 1)) ? 0 : 1);
    }
    Track_I2C_Stop();
    return 0;
}

/* ============================================================
 * 零偏校准（上电时静态采集，计算均值和标准差）
 * ============================================================ */
static void Track_Gyro_Calibrate(void)
{
    float sum = 0, sum_sq = 0;
    float samples[TRACK_GYRO_CALIB_SAMPLES];

    /* 采集 N 个样本 */
    for (uint16_t i = 0; i < TRACK_GYRO_CALIB_SAMPLES; i++) {
        uint8_t raw[14];
        if (Track_I2C_ReadReg(TRACK_MPU6050_ADDR, TRACK_MPU_ACCEL_XOUT_H, raw, 14) != 0) {
            Track_Gyro.calibrated = 0;
            return;
        }
        int16_t gz = (int16_t)((raw[12] << 8) | raw[13]);
        samples[i] = (float)gz / TRACK_MPU_GYRO_SENS;
        sum += samples[i];
        Track_Delay_ms(1);   /* 1ms 间隔，约 0.5 秒完成 */
    }

    /* 计算均值 */
    float mean = sum / TRACK_GYRO_CALIB_SAMPLES;

    /* 计算标准差（判断是否有运动） */
    for (uint16_t i = 0; i < TRACK_GYRO_CALIB_SAMPLES; i++) {
        float diff = samples[i] - mean;
        sum_sq += diff * diff;
    }
    float std_dev = sqrtf(sum_sq / TRACK_GYRO_CALIB_SAMPLES);

    /* 标准差过大说明校准期间有运动，放弃校准 */
    if (std_dev > TRACK_GYRO_CALIB_MAX_STD) {
        Track_Gyro.calibrated = 0;
        return;
    }

    Track_Gyro.gyro_z_offset = mean;
    Track_Gyro.calibrated = 1;
}

/* ============================================================
 * 对外接口
 * ============================================================ */

void Track_Gyro_Init(void)
{
    /* 配置 I2C 引脚为开漏输出 */
    DL_GPIO_initDigitalOutput(TRACK_I2C_SCL_IOMUX);
    DL_GPIO_initDigitalOutput(TRACK_I2C_SDA_IOMUX);

    Track_Gyro.gyro_ok      = 0;
    Track_Gyro.calibrated   = 0;
    Track_Gyro.gyro_z       = 0;
    Track_Gyro.heading      = 0;
    Track_Gyro.gyro_z_offset = 0;

    /* 检查 WHO_AM_I */
    uint8_t id = 0;
    if (Track_I2C_ReadReg(TRACK_MPU6050_ADDR, TRACK_MPU_WHO_AM_I, &id, 1) != 0) return;
    if (id != 0x68 && id != 0x71) return;

    /* 唤醒 */
    uint8_t w = 0x00;
    Track_I2C_WriteReg(TRACK_MPU6050_ADDR, TRACK_MPU_PWR_MGMT_1, &w, 1);
    Track_Delay_ms(50);

    /* 采样率分频器: 1kHz / (1+7) = 125Hz */
    w = 0x07;
    Track_I2C_WriteReg(TRACK_MPU6050_ADDR, TRACK_MPU_SMPLRT_DIV, &w, 1);

    /* 低通滤波: 44Hz (CONFIG=0x03)，延迟约 5ms，适合循迹响应 */
    w = 0x03;
    Track_I2C_WriteReg(TRACK_MPU6050_ADDR, TRACK_MPU_CONFIG, &w, 1);

    /* 加速度量程: ±2g */
    w = 0x00;
    Track_I2C_WriteReg(TRACK_MPU6050_ADDR, TRACK_MPU_ACCEL_CONFIG, &w, 1);

    /* 陀螺仪量程: ±2000deg/s */
    w = 0x18;
    Track_I2C_WriteReg(TRACK_MPU6050_ADDR, TRACK_MPU_GYRO_CONFIG, &w, 1);

    Track_Gyro.gyro_ok = 1;

    /* 零偏校准：上电静态采集 500 次 */
    Track_Gyro_Calibrate();
}

void Track_Gyro_Read(void)
{
    if (!Track_Gyro.gyro_ok) return;

    uint8_t raw[14];
    if (Track_I2C_ReadReg(TRACK_MPU6050_ADDR, TRACK_MPU_ACCEL_XOUT_H, raw, 14) != 0) return;

    int16_t gz = (int16_t)((raw[12] << 8) | raw[13]);
    Track_Gyro.gyro_z = (float)gz / TRACK_MPU_GYRO_SENS;

    /* 减去零偏 */
    if (Track_Gyro.calibrated) {
        Track_Gyro.gyro_z -= Track_Gyro.gyro_z_offset;
    }

    /* 死区：极小角速度视为零（进一步抑制静态漂移） */
    if (Track_Gyro.gyro_z > -0.3f && Track_Gyro.gyro_z < 0.3f) {
        Track_Gyro.gyro_z = 0;
    }

    /* 积分得到航向角（5ms周期） */
    Track_Gyro.heading += Track_Gyro.gyro_z * 0.005f;
}

#endif /* TRACK_USE_MPU6050 */
