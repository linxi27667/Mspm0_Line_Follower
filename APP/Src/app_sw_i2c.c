/**
 * @file    app_sw_i2c.c
 * @brief   软件I2C硬件绑定实现（MSPM0G3507）
 */
#include "app_sw_i2c.h"
#include "app_common.h"

/* ================= 1. 硬件底层函数 (HW_ 前缀) ================= */

static void HW_I2C_Init(void)
{
    /* PB8=PINCM25, PB9=PINCM26 — 配置为开漏输出（软件I2C） */
    DL_GPIO_initDigitalOutput(IOMUX_PINCM25);
    DL_GPIO_initDigitalOutput(IOMUX_PINCM26);
}

static void HW_Pin_Write(void *port, uint32_t pin, uint8_t level)
{
    if (port == NULL) return;
    GPIO_WritePin((GPIO_Regs *)port, pin, level);
}

static uint8_t HW_Pin_Read(void *port, uint32_t pin)
{
    if (port == NULL) return 0;
    return GPIO_ReadPin((GPIO_Regs *)port, pin);
}

static void HW_Delay_us(uint32_t us)
{
    Bsp_Delay_us(us);
}

/* ================= 2. 对象实例化与引脚拼装 ================= */

bsp_sw_i2c_t I2C_Bus_1 = {
    .scl       = {I2C_BUS1_SCL_PORT, I2C_BUS1_SCL_PIN},
    .sda       = {I2C_BUS1_SDA_PORT, I2C_BUS1_SDA_PIN},

    .Init      = HW_I2C_Init,
    .Pin_Write = HW_Pin_Write,
    .Pin_Read  = HW_Pin_Read,
    .Delay_us  = HW_Delay_us
};

/* ================= 3. 对外业务切入点 ================= */

void App_I2C_Init(void)
{
    Bsp_I2C_Init_Device(&I2C_Bus_1);
}
