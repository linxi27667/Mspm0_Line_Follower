/**
 * @file    app_stepper.c
 * @brief   步进电机硬件绑定实现（MSPM0G3507）
 */
#include "app_stepper.h"
#include "app_common.h"

/* PINCM 索引定义（MSPM0G3507 引脚映射） */
#define STEPPER_DIR_PINCM    7   /* PA2 */
#define STEPPER_STEP_PINCM   8   /* PA3 */

/* ================= 1. 硬件底层函数 (HW_ 前缀) ================= */

static void HW_GPIO_Config(void)
{
    /* 步进电机引脚配置为推挽输出 */
    DL_GPIO_initDigitalOutput(STEPPER_DIR_PINCM);
    DL_GPIO_initDigitalOutput(STEPPER_STEP_PINCM);
    DL_GPIO_clearPins(GPIOA, STEPPER_X_DIR_PIN | STEPPER_X_STEP_PIN);
    DL_GPIO_enableOutput(GPIOA, STEPPER_X_DIR_PIN | STEPPER_X_STEP_PIN);
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

bsp_stepper_t Stepper_X = {
    .dir_pin    = {STEPPER_X_DIR_PORT, STEPPER_X_DIR_PIN},
    .step_pin   = {STEPPER_X_STEP_PORT, STEPPER_X_STEP_PIN},

    .state      = STEPPER_STATE_IDLE,
    .steps_remaining = 0,
    .delay_counter = 0,

    .Init       = HW_Stepper_Init,
    .Gpio_Write = HW_Gpio_Write
};

/* ================= 3. 对外业务切入点 ================= */

void App_Stepper_Init(void)
{
    Bsp_Stepper_Init_Device(&Stepper_X);
}

void Stepper_Start(uint8_t dir, uint32_t steps, uint32_t delay_ticks)
{
    Bsp_Stepper_Start(&Stepper_X, dir, steps, delay_ticks);
}

void Stepper_Task(void)
{
    Bsp_Stepper_Task(&Stepper_X);
}
