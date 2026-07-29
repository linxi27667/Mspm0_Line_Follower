/**
 * @file    app_servo.c
 * @brief   舵机硬件绑定实现（MSPM0G3507）
 *          PA12 → TIMG0_C0, 50Hz PWM, 0~180° → 0.5~2.5ms 脉宽
 *          定时器时钟 32MHz, 周期 20000 → 20ms, 0°=500, 180°=2500
 */
#include "app_servo.h"
#include "main.h"
#include "bsp_common.h"

/* ================= 1. 硬件底层函数 (HW_ 前缀) ================= */

static void HW_Gpio_Config(void)
{
    DL_GPIO_initPeripheralOutputFunction(SERVO_PWM_IOMUX, SERVO_PWM_IOMUX_FUNC);
}

static void HW_Tim_Config(void)
{
    DL_TimerG_setPeriod(SERVO_PWM_TIMER, 20000u);
    DL_TimerG_setLoadValue(SERVO_PWM_TIMER, 20000u);
    DL_TimerG_setCaptureCompareCC0Value(SERVO_PWM_TIMER, 1500u, DL_TIMER_CC0_VALUE);
    DL_TimerG_setCaptureCompareControl(SERVO_PWM_TIMER,
        DL_TIMER_CC_UPDATE_METHOD_SOFTWARE, SERVO_PWM_CHANNEL);
}

static int8_t HW_Servo_Init(void *timer, uint32_t channel)
{
    if (timer == NULL) return -1;
    TimerG_Regs *t = (TimerG_Regs *)timer;

    DL_TimerG_enableClock(t);
    DL_TimerG_startCounter(t, DL_TIMER_COUNTER_RUN);

    return 0;
}

static void HW_Servo_Set_Pulse(void *timer, uint32_t channel, uint16_t pulse)
{
    if (timer == NULL) return;
    TimerG_Regs *t = (TimerG_Regs *)timer;
    DL_TimerG_setCaptureCompareCC0Value(t, pulse, DL_TIMER_CC0_VALUE);
}

/* ================= 2. 对象实例化与引脚拼装 ================= */

bsp_servo_t App_Servo_1 = {
    .pwm_pin    = {SERVO_PWM_TIMER, SERVO_PWM_CHANNEL},
    .Gpio_Config = HW_Gpio_Config,
    .Tim_Config  = HW_Tim_Config,
    .Init        = HW_Servo_Init,
    .Set_Pulse   = HW_Servo_Set_Pulse
};

/* ================= 3. 对外业务切入点 ================= */

void App_Servo_System_Init(void)
{
    App_Servo_1.Gpio_Config();
    App_Servo_1.Tim_Config();
    BSP_Servo_Init_Device(&App_Servo_1);
    BSP_Servo_Set_Angle(&App_Servo_1, 0.0f);
}
