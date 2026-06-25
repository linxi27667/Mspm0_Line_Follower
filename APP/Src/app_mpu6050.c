/**
 * @file    app_mpu6050.c
 * @brief   MPU6050应用层 — 硬件绑定 + 一次业务函数
 * @note    通过 MPU6050_USE_HW_I2C 宏选择软件/硬件I2C
 */
#include "app_mpu6050.h"
#include "bsp_common.h"
#include "my_easylog.h"

/* ================================================================
 *  I2C 总线包装函数（APP层绑定硬件，BSP层通过函数指针调用）
 * ================================================================ */

#if MPU6050_USE_HW_I2C
/* ---------- 硬件 I2C 实现 ---------- */
#include "app_common.h"
#include "ti_msp_dl_config.h"

/* I2C 操作超时阈值（循环计数）— 避免外设未启用 / 设备未应答时永久阻塞 */
#define I2C_TIMEOUT_LOOP        (200000u)

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
    uint32_t timeout;

    /* 等待总线空闲（带超时） */
    timeout = I2C_TIMEOUT_LOOP;
    while (DL_I2C_getControllerStatus(i2c) & DL_I2C_CONTROLLER_STATUS_BUSY) {
        if (--timeout == 0) return 2;
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
    timeout = I2C_TIMEOUT_LOOP;
    while (!(DL_I2C_getRawInterruptStatus(i2c,
                DL_I2C_INTERRUPT_CONTROLLER_TX_DONE))) {
        if (--timeout == 0) return 2;
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
    uint32_t timeout;

    /* 等待总线空闲（带超时） */
    timeout = I2C_TIMEOUT_LOOP;
    while (DL_I2C_getControllerStatus(i2c) & DL_I2C_CONTROLLER_STATUS_BUSY) {
        if (--timeout == 0) return 2;
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
    timeout = I2C_TIMEOUT_LOOP;
    while (!(DL_I2C_getRawInterruptStatus(i2c,
                DL_I2C_INTERRUPT_CONTROLLER_TX_DONE))) {
        if (--timeout == 0) return 2;
    }
    DL_I2C_clearInterruptStatus(i2c, DL_I2C_INTERRUPT_CONTROLLER_TX_DONE);

    /* 检查NACK */
    if (DL_I2C_getRawInterruptStatus(i2c, DL_I2C_INTERRUPT_CONTROLLER_NACK)) {
        DL_I2C_clearInterruptStatus(i2c, DL_I2C_INTERRUPT_CONTROLLER_NACK);
        return 1;
    }

    /* 第2步: 读数据 */
    DL_I2C_startControllerTransfer(i2c, dev_addr,
        DL_I2C_CONTROLLER_DIRECTION_RX, len);

    /* 等待读完成（带超时） */
    timeout = I2C_TIMEOUT_LOOP;
    while (!(DL_I2C_getRawInterruptStatus(i2c,
                DL_I2C_INTERRUPT_CONTROLLER_RX_DONE))) {
        if (--timeout == 0) return 2;
    }
    DL_I2C_clearInterruptStatus(i2c, DL_I2C_INTERRUPT_CONTROLLER_RX_DONE);

    /* 从RX FIFO读取数据 */
    for (uint16_t i = 0; i < len; i++) {
        data[i] = DL_I2C_receiveControllerData(i2c);
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
    /* 硬件 I2C: SysConfig 只生成了 setClockConfig + glitch filter，
     * 缺失 enableController → 启动后 I2C 完全无 SDA/SCL 输出，
     * startControllerTransfer 后 TX_DONE 永远不会置位。
     * 这里补上 controller 使能 + 设备启用。 */
    DL_I2C_enableController(MPU6050_HW_I2C_INST);

    /* 给 I2C 一些稳定时间（外设使能后 SCL/SDA 才进入空闲态） */
    if (Mpu_Sensor.Delay_ms) Mpu_Sensor.Delay_ms(2);
#else
    /* 软件 I2C 需要先初始化 GPIO */
    App_I2C_Init();
#endif

    uint8_t ret = Bsp_MPU6050_Init_Device(&Mpu_Sensor);

    if (ret == 0 && Mpu_Sensor.gyro_ok) {
        elog_i("[MPU]", "Init OK (gyro ready)");
    } else {
        /* 失败也不阻塞主流程：gyro_ok=false 时航向角积分自动跳过 */
        elog_w("[MPU]", "Init FAIL ret=%d gyro_ok=%d (continuing without gyro)",
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
