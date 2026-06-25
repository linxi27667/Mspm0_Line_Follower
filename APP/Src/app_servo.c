/**
 * @file    app_servo.c
 * @brief   舵机硬件绑定实现（MSPM0G3507）
 * @note    舵机PWM定时器(TIMG12)由APP层手动初始化，
 *          因为SysConfig不支持prescale属性，无法生成50Hz周期
 */
#include "app_servo.h"
#include "app_common.h"

/* ================= 1. 硬件底层函数 (HW_ 前缀) ================= */

static void HW_Gpio_Config(void)
{
    /* PB20 = TIMG12_CCP0, 配置为外设输出 */
    DL_GPIO_initPeripheralOutputFunction(SERVO_1_PWM_PINCM,
                                         IOMUX_PINCM48_PF_TIMG12_CCP0);
    DL_GPIO_enableOutput(GPIOB, DL_GPIO_PIN_20);
}

static void HW_Tim_Config(void)
{
    GPTIMER_Regs *timer = (GPTIMER_Regs *)SERVO_1_PWM_TIMER;

    /* 使能时钟 + 复位 */
    DL_TimerG_reset(timer);
    DL_TimerG_enablePower(timer);
    delay_cycles(16);

    /* 时钟配置: BUSCLK / 8 / (3+1) = 1MHz */
    static const DL_TimerG_ClockConfig clkCfg = {
        .clockSel    = DL_TIMER_CLOCK_BUSCLK,
        .divideRatio = DL_TIMER_CLOCK_DIVIDE_8,
        .prescale    = 3U
    };
    DL_TimerG_setClockConfig(timer, (DL_TimerG_ClockConfig *)&clkCfg);

    /* PWM模式: 边沿对齐, 周期20000=20ms(50Hz), 不自动启动 */
    static const DL_TimerG_PWMConfig pwmCfg = {
        .pwmMode    = DL_TIMER_PWM_MODE_EDGE_ALIGN,
        .period     = 20000,
        .startTimer = DL_TIMER_STOP,
    };
    DL_TimerG_initPWMMode(timer, (DL_TimerG_PWMConfig *)&pwmCfg);

    /* CC0: 初始脉宽1500us(中立位) */
    DL_TimerG_setCaptureCompareValue(timer, 1500, DL_TIMER_CC_0_INDEX);
    DL_TimerG_setCaptureCompareOutCtl(timer,
        DL_TIMER_CC_OCTL_INIT_VAL_LOW,
        DL_TIMER_CC_OCTL_INV_OUT_DISABLED,
        DL_TIMER_CC_OCTL_SRC_FUNCVAL,
        DL_TIMERG_CAPTURE_COMPARE_0_INDEX);
    DL_TimerG_setCaptCompUpdateMethod(timer,
        DL_TIMER_CC_UPDATE_METHOD_IMMEDIATE,
        DL_TIMERG_CAPTURE_COMPARE_0_INDEX);

    DL_TimerG_enableClock(timer);
    DL_TimerG_setCCPDirection(timer, DL_TIMER_CC0_OUTPUT);
}

static int8_t HW_Servo_Init(void *timer, uint32_t channel)
{
    if (timer == NULL) return -1;
    HW_Tim_Config();
    DL_TimerG_startCounter((GPTIMER_Regs *)timer);
    return 0;
}

static void HW_Servo_Set_Pulse(void *timer, uint32_t channel, uint16_t pulse)
{
    if (timer == NULL) return;
    DL_Timer_setCaptureCompareValue((GPTIMER_Regs *)timer, pulse, DL_TIMER_CC_0_INDEX);
}

/* ================= 2. 对象实例化与引脚拼装 ================= */

bsp_servo_t Servo_1 = {
    .pwm_pin     = {SERVO_1_PWM_TIMER, SERVO_1_PWM_CHANNEL},
    .Gpio_Config = HW_Gpio_Config,
    .Tim_Config  = HW_Tim_Config,
    .Init        = HW_Servo_Init,
    .Set_Pulse   = HW_Servo_Set_Pulse
};

/* ================= 3. 对外业务切入点 ================= */

void App_Servo_Init(void)
{
    Bsp_Servo_Init_Device(&Servo_1);
    Bsp_Servo_Set_Angle(&Servo_1, 90.0f);
}

void Servo_Set_Angle(float angle)
{
    Bsp_Servo_Set_Angle(&Servo_1, angle);
}
