/**
 * @file    app_sw_i2c.c
 * @brief   软件I2C硬件绑定实现（MSPM0G3507）
 */
#include "app_sw_i2c.h"
#include "bsp_common.h"
#include "ti_msp_dl_config.h"

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
    if (level) {
        DL_GPIO_setPins((GPIO_Regs *)port, pin);
    } else {
        DL_GPIO_clearPins((GPIO_Regs *)port, pin);
    }
}

static uint8_t HW_Pin_Read(void *port, uint32_t pin)
{
    if (port == NULL) return 0;
    return (DL_GPIO_readPins((GPIO_Regs *)port, pin) != 0) ? 1 : 0;
}

static void HW_Delay_us(uint32_t us)
{
    BSP_Delay_us(us);
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
    BSP_I2C_Init_Device(&App_I2C_Bus_1);
}
