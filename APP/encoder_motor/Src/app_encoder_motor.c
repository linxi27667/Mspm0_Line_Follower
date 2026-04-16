/**
 * @file    app_encoder_motor.c
 * @brief   霍尔电机硬件绑定实现（MSPM0G3507）
 */
#include "app_encoder_motor.h"
#include "main.h"
#include "bsp_common.h"

/* ================= 1. 硬件底层函数 (HW_ 前缀) ================= */

static void HW_GPIO_Config(void)
{
    /* 方向引脚由 SysConfig 配置为输出 */
}

static void HW_Timer_Init(void)
{
    /* 启动 PWM Timer 和编码器 Timer */
    DL_TimerG_enableClock(TIMER_G0);
    DL_TimerG_startCounter(TIMER_G0, DL_TIMER_COUNTER_RUN);
}

static void HW_Gpio_Write(void *port, uint32_t pin, uint8_t level)
{
    if (port == NULL) return;
    GPIO_WritePin((GPIO_Regs *)port, pin, level);
}

static void HW_Pwm_Write(void *timer, uint32_t channel, uint32_t duty)
{
    if (timer == NULL) return;
    TimerG_Regs *t = (TimerG_Regs *)timer;
    DL_TimerG_setCaptureCompareCC0Value(t, duty, DL_TIMER_CC0_VALUE);
}

static int32_t HW_Enc_Read(void)
{
    /* MSPM0 用 Timer 做编码器时，读取 CC 捕获值后清零 */
    int32_t count = (int32_t)DL_TimerG_getCaptureCompareCC0Value(TIMER_G1);
    DL_TimerG_setCaptureCompareCC0Value(TIMER_G1, 0, DL_TIMER_CC0_VALUE);
    return count;
}

/* ================= 2. 对象实例化与引脚拼装 ================= */

bsp_motor_t App_Motor_Left = {
    .dir_pin1   = {GPIOB, DL_GPIO_PIN_12},
    .dir_pin2   = {GPIOB, DL_GPIO_PIN_13},
    .pwm_timer  = TIMER_G0,
    .pwm_channel = 0,

    .Gpio_Config = HW_GPIO_Config,
    .Init        = HW_Timer_Init,
    .Gpio_Write  = HW_Gpio_Write,
    .Pwm_Write   = HW_Pwm_Write,
    .Enc_Read    = HW_Enc_Read
};

/* ================= 3. 对外业务切入点 ================= */

void App_Motor_System_Init(void)
{
    BSP_Motor_Init_Device(&App_Motor_Left);
}
