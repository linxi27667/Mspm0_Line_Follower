/**
 * @file    app_stepper.c
 * @brief   步进电机硬件绑定实现（MSPM0G3507）
 */
#include "app_stepper.h"
#include "main.h"
#include "bsp_common.h"

/* ================= 1. 硬件底层函数 (HW_ 前缀) ================= */

static void HW_GPIO_Config(void)
{
    DL_GPIO_initDigitalOutputFeatures(GPIOA,
        DL_GPIO_PIN_1 | DL_GPIO_PIN_2,
        DL_GPIO_PIN_NO_PULL);
}

static void HW_Stepper_Init(void)
{
    HW_GPIO_Config();
}

static void HW_Gpio_Write(void *port, uint32_t pin, uint8_t level)
{
    if (port == NULL) return;
    GPIO_WritePin((GPIO_Regs *)port, pin, level);
}

static void HW_Delay_us(uint32_t us)
{
    BSP_Delay_us(us);
}

/* ================= 2. 对象实例化与引脚拼装 ================= */

bsp_stepper_t App_Stepper_X = {
    .dir_pin    = {GPIOA, DL_GPIO_PIN_1},
    .step_pin   = {GPIOA, DL_GPIO_PIN_2},

    .Init       = HW_Stepper_Init,
    .Gpio_Write = HW_Gpio_Write,
    .Delay_us   = HW_Delay_us
};

/* ================= 3. 对外业务切入点 ================= */

void App_Stepper_System_Init(void)
{
    BSP_Stepper_Init_Device(&App_Stepper_X);
}
