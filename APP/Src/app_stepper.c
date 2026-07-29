/**
 * @file    app_stepper.c
 * @brief   步进电机硬件绑定实现（MSPM0G3507）
 */
#include "app_stepper.h"
#include "ti_msp_dl_config.h"
#include "bsp_common.h"

/* ================= 1. 硬件底层函数 (HW_ 前缀) ================= */

static void HW_GPIO_Config(void)
{
    DL_GPIO_initDigitalOutputFeatures(STEPPER_X_DIR_PORT,
        STEPPER_X_DIR_PIN | STEPPER_X_STEP_PIN,
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

/* ================= 2. 对象实例化与引脚拼装 ================= */

bsp_stepper_t App_Stepper_X = {
    .dir_pin    = {STEPPER_X_DIR_PORT, STEPPER_X_DIR_PIN},
    .step_pin   = {STEPPER_X_STEP_PORT, STEPPER_X_STEP_PIN},

    .state      = STEPPER_STATE_IDLE,
    .steps_remaining = 0,
    .delay_counter = 0,

    .Init       = HW_Stepper_Init,
    .Gpio_Write = HW_Gpio_Write
};

/* ================= 3. 对外业务切入点 ================= */

void App_Stepper_System_Init(void)
{
    BSP_Stepper_Init_Device(&App_Stepper_X);
}

void App_Stepper_Start(uint8_t dir, uint32_t steps, uint32_t delay_ticks)
{
    BSP_Stepper_Start(&App_Stepper_X, dir, steps, delay_ticks);
}

void App_Stepper_Task(void)
{
    BSP_Stepper_Task(&App_Stepper_X);
}
