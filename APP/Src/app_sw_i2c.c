/**
 * @file    app_sw_i2c.c
 * @brief   软件 I2C 硬件绑定实现（MSPM0G3507）
 */
#include "app_sw_i2c.h"
#include "main.h"
#include "bsp_common.h"

/* ================= 1. 硬件底层函数 (HW_ 前缀) ================= */

static void HW_I2C_Init(void)
{
    DL_GPIO_initDigitalOutputFeatures(GPIOB,
        DL_GPIO_PIN_8 | DL_GPIO_PIN_9,
        DL_GPIO_PIN_OUTPUT_DRIVE_STRENGTH_4MA);
}

static void HW_Pin_Write(void *port, uint32_t pin, uint8_t level)
{
    if (port) GPIO_WritePin((GPIO_Regs *)port, pin, level);
}

static uint8_t HW_Pin_Read(void *port, uint32_t pin)
{
    if (port) return (uint8_t)GPIO_ReadPin((GPIO_Regs *)port, pin);
    return 0;
}

static void HW_Delay_us(uint32_t us)
{
    BSP_Delay_us(us);
}

/* ================= 2. 实例化总线对象 ================= */

bsp_sw_i2c_t App_I2C_Bus_1 = {
    .scl       = {GPIOB, DL_GPIO_PIN_8},
    .sda       = {GPIOB, DL_GPIO_PIN_9},

    .Init      = HW_I2C_Init,
    .Pin_Write = HW_Pin_Write,
    .Pin_Read  = HW_Pin_Read,
    .Delay_us  = HW_Delay_us
};

void App_I2C_System_Init(void)
{
    BSP_I2C_Init_Device(&App_I2C_Bus_1);
}
