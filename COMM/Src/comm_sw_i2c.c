/**
 * @file    comm_sw_i2c.c
 * @brief   软件I2C通讯层实现（MSPM0G3507）
 */
#include "comm_sw_i2c.h"
#include "bsp_common.h"
#include "ti_msp_dl_config.h"

/* ================= 1. 硬件底层函数 (HW_ 前缀) ================= */

static void HW_I2C_Init(void)
{
    (void)I2C_BUS1_SCL_PORT;
    (void)I2C_BUS1_SCL_PIN;
    (void)I2C_BUS1_SDA_PORT;
    (void)I2C_BUS1_SDA_PIN;
}

static void HW_Pin_Write(void *port, uint32_t pin, uint8_t level)
{
    if (port) {
        GPIO_WritePin((GPIO_Regs *)port, pin, level);
    }
}

static uint8_t HW_Pin_Read(void *port, uint32_t pin)
{
    if (port) return (uint8_t)GPIO_ReadPin((GPIO_Regs *)port, pin);
    return 0;
}

static void HW_Delay_us(uint32_t us)
{
    delay_cycles(us * (CPUCLK_FREQ / 1000000u));
}

/* ================= 2. 对象实例化与引脚拼装 ================= */

bsp_sw_i2c_t App_I2C_Bus_1 = {
    .scl       = {I2C_BUS1_SCL_PORT, I2C_BUS1_SCL_PIN},
    .sda       = {I2C_BUS1_SDA_PORT, I2C_BUS1_SDA_PIN},

    .Init      = HW_I2C_Init,
    .Pin_Write = HW_Pin_Write,
    .Pin_Read  = HW_Pin_Read,
    .Delay_us  = HW_Delay_us
};

/* ================= 3. 对外业务切入点 ================= */

void App_I2C_System_Init(void)
{
    HW_I2C_Init();
}
