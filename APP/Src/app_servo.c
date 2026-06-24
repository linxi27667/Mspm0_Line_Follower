/**
 * @file    app_servo.c
 * @brief   舵机硬件绑定实现（MSPM0G3507）
 */
#include "app_servo.h"
#include "ti_msp_dl_config.h"

/* ================= 1. 硬件底层函数 (HW_ 前缀) ================= */

static void HW_Gpio_Config(void)
{
    /* PWM 引脚由 SysConfig 配置 */
}

static void HW_Tim_Config(void)
{
    /* 定时器 PWM 配置 */
}

static int8_t HW_Servo_Init(void *timer, uint32_t channel)
{
    if (timer == NULL) return -1;
    DL_TimerG_enableClock((TimerG_Regs *)timer);
    DL_TimerG_startCounter((TimerG_Regs *)timer, DL_TIMER_COUNTER_RUN);
    return 0;
}

static void HW_Servo_Set_Pulse(void *timer, uint32_t channel, uint16_t pulse)
{
    if (timer == NULL) return;
    DL_TimerG_setCaptureCompareCC0Value((TimerG_Regs *)timer, pulse, DL_TIMER_CC0_VALUE);
}

/* ================= 2. 对象实例化与引脚拼装 ================= */

bsp_servo_t App_Servo_1 = {
    .pwm_pin     = {SERVO_1_PWM_TIMER, SERVO_1_PWM_CHANNEL},
    .Gpio_Config = HW_Gpio_Config,
    .Tim_Config  = HW_Tim_Config,
    .Init        = HW_Servo_Init,
    .Set_Pulse   = HW_Servo_Set_Pulse
};

/* ================= 3. 对外业务切入点 ================= */

void App_Servo_System_Init(void)
{
    BSP_Servo_Init_Device(&App_Servo_1);
    BSP_Servo_Set_Angle(&App_Servo_1, 0.0f);
}

void App_Servo_Set_Angle(float angle)
{
    BSP_Servo_Set_Angle(&App_Servo_1, angle);
}
