/**
 * @file    app_mpu6050.c
 * @brief   MPU6050应用层 — 硬件绑定 + 一次业务函数
 * @note    通过 MPU6050_USE_HW_I2C 宏选择软件/硬件I2C
 */
#include "app_mpu6050.h"
#include "app_log.h"
#include "bsp_common.h"
#include <elog.h>

/* ================================================================
 *  I2C 总线包装函数（APP层绑定硬件，BSP层通过函数指针调用）
 * ================================================================ */

#if MPU6050_USE_HW_I2C
/* ---------- 硬件 I2C 实现 ---------- */
#include "app_common.h"
#include "ti_msp_dl_config.h"

/* I2C 操作超时阈值（循环计数）— 避免外设未启用 / 设备未应答时永久阻塞 */
#define I2C_TIMEOUT_MS          2u

/**
 * @brief   硬件I2C写寄存器（阻塞式 + 超时保护）
 * @note    MSPM0G3507 I2C Controller 模式流程:
 *          1. 等待总线空闲
 *          2. 填充TX FIFO（寄存器地址 + 数据）
 *          3. 启动写传输（含START+STOP）
 *          4. 等待TX完成中断标志
 * @return  0=成功, 1=NACK, 2=超时
 */
static uint8_t HW_I2C_Write_Reg(uint8_t dev_addr, uint8_t reg_addr,
                                 const uint8_t *data, uint16_t len)
{
    I2C_Regs *i2c = MPU6050_HW_I2C_INST;
    uint32_t start;

    /* 等待总线空闲（带超时） */
    start = Bsp_GetTick();
    while (DL_I2C_getControllerStatus(i2c) & DL_I2C_CONTROLLER_STATUS_BUSY) {
        if ((Bsp_GetTick() - start) >= I2C_TIMEOUT_MS) return 2;
    }

    /* 清除可能残留的中断标志 */
    DL_I2C_clearInterruptStatus(i2c,
        DL_I2C_INTERRUPT_CONTROLLER_TX_DONE |
        DL_I2C_INTERRUPT_CONTROLLER_RX_DONE |
        DL_I2C_INTERRUPT_CONTROLLER_NACK);

    /* 填充TX FIFO: 先写寄存器地址，再写数据 */
    DL_I2C_fillControllerTXFIFO(i2c, (uint8_t *)&reg_addr, 1);
    DL_I2C_fillControllerTXFIFO(i2c, (uint8_t *)data, len);

    /* 启动写传输: 目标地址 + 方向TX + 长度(1字节地址+len字节数据) */
    DL_I2C_startControllerTransfer(i2c, dev_addr,
        DL_I2C_CONTROLLER_DIRECTION_TX, 1 + len);

    /* 等待传输完成（带超时） */
    start = Bsp_GetTick();
    while (!(DL_I2C_getRawInterruptStatus(i2c,
                DL_I2C_INTERRUPT_CONTROLLER_TX_DONE))) {
        if ((Bsp_GetTick() - start) >= I2C_TIMEOUT_MS) return 2;
    }
    DL_I2C_clearInterruptStatus(i2c, DL_I2C_INTERRUPT_CONTROLLER_TX_DONE);

    /* 检查NACK */
    if (DL_I2C_getRawInterruptStatus(i2c, DL_I2C_INTERRUPT_CONTROLLER_NACK)) {
        DL_I2C_clearInterruptStatus(i2c, DL_I2C_INTERRUPT_CONTROLLER_NACK);
        return 1;
    }

    return 0;
}

/**
 * @brief   硬件I2C读寄存器（阻塞式 + 超时保护）
 * @note    流程: 写寄存器地址(无STOP) → 重新START → 读数据(含STOP)
 *          MSPM0的startControllerTransfer自带START+STOP，
 *          所以分两步: 先写地址(1字节TX)，再读数据(len字节RX)
 * @return  0=成功, 1=NACK, 2=超时
 */
static uint8_t HW_I2C_Read_Reg(uint8_t dev_addr, uint8_t reg_addr,
                                uint8_t *data, uint16_t len)
{
    I2C_Regs *i2c = MPU6050_HW_I2C_INST;
    uint32_t start;

    /* 等待总线空闲（带超时） */
    start = Bsp_GetTick();
    while (DL_I2C_getControllerStatus(i2c) & DL_I2C_CONTROLLER_STATUS_BUSY) {
        if ((Bsp_GetTick() - start) >= I2C_TIMEOUT_MS) return 2;
    }

    /* 清除残留中断标志 */
    DL_I2C_clearInterruptStatus(i2c,
        DL_I2C_INTERRUPT_CONTROLLER_TX_DONE |
        DL_I2C_INTERRUPT_CONTROLLER_RX_DONE |
        DL_I2C_INTERRUPT_CONTROLLER_NACK);

    /* 第1步: 写寄存器地址 */
    DL_I2C_fillControllerTXFIFO(i2c, (uint8_t *)&reg_addr, 1);
    DL_I2C_startControllerTransfer(i2c, dev_addr,
        DL_I2C_CONTROLLER_DIRECTION_TX, 1);

    /* 等待写完成（带超时） */
    start = Bsp_GetTick();
    while (!(DL_I2C_getRawInterruptStatus(i2c,
                DL_I2C_INTERRUPT_CONTROLLER_TX_DONE))) {
        if ((Bsp_GetTick() - start) >= I2C_TIMEOUT_MS) return 2;
    }
    DL_I2C_clearInterruptStatus(i2c, DL_I2C_INTERRUPT_CONTROLLER_TX_DONE);

    /* 检查NACK */
    if (DL_I2C_getRawInterruptStatus(i2c, DL_I2C_INTERRUPT_CONTROLLER_NACK)) {
        DL_I2C_clearInterruptStatus(i2c, DL_I2C_INTERRUPT_CONTROLLER_NACK);
        return 1;
    }

    /* 第2步: 读数据 — MSPM0 I2C RX FIFO仅4字节，必须边传输边读取 */
    DL_I2C_flushControllerRXFIFO(i2c);

    DL_I2C_startControllerTransfer(i2c, dev_addr,
        DL_I2C_CONTROLLER_DIRECTION_RX, len);

    /* 边传输边从RX FIFO取数据，防止FIFO溢出丢字节 */
    uint16_t received = 0;
    start = Bsp_GetTick();
    while (received < len) {
        uint32_t avail = DL_I2C_getControllerRXFIFOCounter(i2c);
        while (avail > 0 && received < len) {
            data[received++] = DL_I2C_receiveControllerData(i2c);
            avail--;
        }
        if ((Bsp_GetTick() - start) >= I2C_TIMEOUT_MS) return 2;
    }

    /* 等待RX_DONE并清除 */
    start = Bsp_GetTick();
    while (!(DL_I2C_getRawInterruptStatus(i2c,
                DL_I2C_INTERRUPT_CONTROLLER_RX_DONE))) {
        if ((Bsp_GetTick() - start) >= I2C_TIMEOUT_MS) break;
    }
    DL_I2C_clearInterruptStatus(i2c,
        DL_I2C_INTERRUPT_CONTROLLER_RX_DONE |
        DL_I2C_INTERRUPT_CONTROLLER_NACK);

    /* 检查NACK（设备不应答） */
    if (DL_I2C_getRawInterruptStatus(i2c, DL_I2C_INTERRUPT_CONTROLLER_NACK)) {
        DL_I2C_clearInterruptStatus(i2c, DL_I2C_INTERRUPT_CONTROLLER_NACK);
        return 1;
    }

    return 0;
}

#else
/* ---------- 软件 I2C 实现 ---------- */
#include "app_sw_i2c.h"

static uint8_t HW_I2C_Write_Reg(uint8_t dev_addr, uint8_t reg_addr,
                                 const uint8_t *data, uint16_t len)
{
    return Bsp_I2C_Write_Reg(&I2C_Bus_1, dev_addr, reg_addr, data, len);
}

static uint8_t HW_I2C_Read_Reg(uint8_t dev_addr, uint8_t reg_addr,
                                uint8_t *data, uint16_t len)
{
    return Bsp_I2C_Read_Reg(&I2C_Bus_1, dev_addr, reg_addr, data, len);
}

#endif /* MPU6050_USE_HW_I2C */

/* ================================================================
 *  延时包装
 * ================================================================ */
static void HW_Delay_ms(uint32_t ms)
{
    Bsp_Delay_ms(ms);
}

/* ================================================================
 *  对象实例化
 * ================================================================ */
bsp_mpu_t Mpu_Sensor = {
    .dev_addr      = MPU6050_DEV_ADDR,
    .I2C_Write_Reg = HW_I2C_Write_Reg,
    .I2C_Read_Reg  = HW_I2C_Read_Reg,
    .Delay_ms      = HW_Delay_ms,
    .gyro_ok       = false,
    .calibrated    = false,
    .gyro_z_offset = 0,
    .heading       = 0,
};

/* ================================================================
 *  一次业务函数
 * ================================================================ */

void App_Mpu_Init(void)
{
#if MPU6050_USE_HW_I2C
    /* 硬件 I2C: SysConfig 生成的 SYSCFG_DL_MPU6050_I2C_init() 只调用
     * setClockConfig(BUSCLK/1) + glitch filter，缺失 enableController →
     * 启动后 I2C 完全无 SDA/SCL 输出，startControllerTransfer 后
     * TX_DONE 永远不会置位。这里补上 controller 使能。
     *
     * 注: driverlib 1.30 未提供 SCL 频率设置 API（DL_I2C_setBitTime 不存在）。
     * SCL 频率由 I2C 控制器内部基于 BUSCLK=32MHz 自动分频，默认约 100kHz。
     * MPU6050 支持 100kHz-400kHz，能正常通信。 */
    DL_I2C_enableController(MPU6050_HW_I2C_INST);

    /* 给 I2C 一些稳定时间（外设使能后 SCL/SDA 才进入空闲态） */
    if (Mpu_Sensor.Delay_ms) Mpu_Sensor.Delay_ms(2);
#else
    /* 软件 I2C 需要先初始化 GPIO */
    App_I2C_Init();
#endif

    uint8_t ret = Bsp_MPU6050_Init_Device(&Mpu_Sensor);

    if (ret == 0 && Mpu_Sensor.gyro_ok) {
        APP_MPU_LOG_I("MPU", "Init OK (gyro ready)");
    } else {
        /* 失败也不阻塞主流程：gyro_ok=false 时航向角积分自动跳过 */
        APP_MPU_LOG_W("MPU", "Init FAIL ret=%d gyro_ok=%d (continuing without gyro)",
               ret, Mpu_Sensor.gyro_ok ? 1 : 0);
    }
}

void Mpu_Read_Data(void)
{
    Bsp_MPU6050_Read_Data(&Mpu_Sensor);
}

void Mpu_Calibrate(void)
{
    Bsp_MPU6050_Calibrate(&Mpu_Sensor);
}

void Mpu_Update_Heading(float dt)
{
    Bsp_MPU6050_Update_Heading(&Mpu_Sensor, dt);
}
