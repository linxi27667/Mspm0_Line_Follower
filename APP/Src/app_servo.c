/**
 * @file    app_servo.c
 * @brief   PA12/TIMG0 50 Hz PWM implementation for the pen servo.
 */
#include "app_servo.h"
#include "ti_msp_dl_config.h"
#include <stdbool.h>

#define SERVO_PWM_TIMER                 (TIMG0)
#define SERVO_PWM_CHANNEL               (DL_TIMER_CC_0_INDEX)
#define SERVO_PWM_IOMUX                 (IOMUX_PINCM34)
#define SERVO_PWM_IOMUX_FUNC            (IOMUX_PINCM34_PF_TIMG0_CCP0)
#define SERVO_PWM_GPIO_PORT             (GPIOA)
#define SERVO_PWM_GPIO_PIN              (DL_GPIO_PIN_12)
#define SERVO_PWM_CLOCK_PRESCALE        (31u)
#define SERVO_PWM_PERIOD_US             (20000u)

static bool s_servo_initialized = false;

static void HW_Gpio_Config(void)
{
    DL_GPIO_initPeripheralOutputFunction(SERVO_PWM_IOMUX,
                                         SERVO_PWM_IOMUX_FUNC);
    DL_GPIO_enableOutput(SERVO_PWM_GPIO_PORT, SERVO_PWM_GPIO_PIN);
}

static void HW_Tim_Config(void)
{
    static const DL_TimerG_ClockConfig clock_config = {
        .clockSel = DL_TIMER_CLOCK_BUSCLK,
        .divideRatio = DL_TIMER_CLOCK_DIVIDE_1,
        .prescale = SERVO_PWM_CLOCK_PRESCALE
    };
    static const DL_TimerG_PWMConfig pwm_config = {
        .pwmMode = DL_TIMER_PWM_MODE_EDGE_ALIGN,
        .period = SERVO_PWM_PERIOD_US,
        .startTimer = DL_TIMER_STOP
    };

    DL_TimerG_reset(SERVO_PWM_TIMER);
    DL_TimerG_enablePower(SERVO_PWM_TIMER);
    delay_cycles(POWER_STARTUP_DELAY);

    DL_TimerG_setClockConfig(SERVO_PWM_TIMER,
                             (DL_TimerG_ClockConfig *)&clock_config);
    DL_TimerG_initPWMMode(SERVO_PWM_TIMER,
                          (DL_TimerG_PWMConfig *)&pwm_config);
    DL_TimerG_setCaptureCompareValue(SERVO_PWM_TIMER,
                                     SERVO_PWM_PERIOD_US -
                                         BSP_SERVO_MIN_PULSE_US,
                                     SERVO_PWM_CHANNEL);
    DL_TimerG_setCaptureCompareOutCtl(SERVO_PWM_TIMER,
                                      DL_TIMER_CC_OCTL_INIT_VAL_LOW,
                                      DL_TIMER_CC_OCTL_INV_OUT_DISABLED,
                                      DL_TIMER_CC_OCTL_SRC_FUNCVAL,
                                      SERVO_PWM_CHANNEL);
    DL_TimerG_setCaptCompUpdateMethod(SERVO_PWM_TIMER,
                                      DL_TIMER_CC_UPDATE_METHOD_IMMEDIATE,
                                      SERVO_PWM_CHANNEL);
    DL_TimerG_setCCPDirection(SERVO_PWM_TIMER, DL_TIMER_CC0_OUTPUT);
}

static int8_t HW_Servo_Init(void *timer, uint32_t channel)
{
    GPTIMER_Regs *timer_regs = (GPTIMER_Regs *)timer;

    (void)channel;
    if (timer_regs == NULL) {
        return -1;
    }

    DL_TimerG_enableClock(timer_regs);
    DL_TimerG_startCounter(timer_regs);
    return 0;
}

static void HW_Servo_Set_Pulse(void *timer, uint32_t channel,
                               uint16_t pulse_us)
{
    GPTIMER_Regs *timer_regs = (GPTIMER_Regs *)timer;

    if (timer_regs == NULL) {
        return;
    }

    DL_TimerG_setCaptureCompareValue(timer_regs,
                                     SERVO_PWM_PERIOD_US - pulse_us,
                                     (DL_TIMER_CC_INDEX)channel);
}

bsp_servo_t App_Servo_1 = {
    .pwm_pin = {SERVO_PWM_TIMER, SERVO_PWM_CHANNEL},
    .angle_deg = 0.0f,
    .Gpio_Config = HW_Gpio_Config,
    .Tim_Config = HW_Tim_Config,
    .Init = HW_Servo_Init,
    .Set_Pulse = HW_Servo_Set_Pulse
};

int8_t App_Servo_System_Init(void)
{
    int8_t result;

    if (s_servo_initialized) {
        App_Servo_Pen_Up();
        return 0;
    }

    result = BSP_Servo_Init_Device(&App_Servo_1);

    if (result == 0) {
        s_servo_initialized = true;
        App_Servo_Pen_Up();
    }
    return result;
}

void App_Servo_Set_Angle(float angle_deg)
{
    BSP_Servo_Set_Angle(&App_Servo_1, angle_deg);
}

void App_Servo_Pen_Up(void)
{
    App_Servo_Set_Angle(APP_SERVO_PEN_UP_ANGLE_DEG);
}

void App_Servo_Pen_Down(void)
{
    App_Servo_Set_Angle(APP_SERVO_PEN_DOWN_ANGLE_DEG);
}

float App_Servo_Get_Angle(void)
{
    return App_Servo_1.angle_deg;
}
