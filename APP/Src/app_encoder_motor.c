/**
 * @file    app_encoder_motor.c
 * @brief   霍尔编码器电机硬件绑定实现（MSPM0G3507）
 * @note    左编码器: 硬件QEI (TIMG8)
 *          右编码器: GPIO中断计数 (PB14=PHA, PB15=PHB)
 *          速度PID: 前馈(目标速度) + PID修正，级联位置PID
 */
#include "app_encoder_motor.h"
#include "app_common.h"
#include "app_pid.h"
#include "my_easylog.h"

/* ================= 右编码器中断计数 ================= */
volatile int32_t g_right_enc_count = 0;
static int32_t   s_right_enc_last  = 0;

/* ================= 速度PID ================= */
static bsp_pid_t s_left_speed_pid;
static bsp_pid_t s_right_speed_pid;
static float     s_speed_scale = MOTOR_SPEED_SCALE_DEFAULT;

/* ================= 1. 硬件底层函数 (HW_ 前缀) ================= */

static void HW_GPIO_Config(void)
{
    /* 方向引脚由 SysConfig 配置为输出 */
}

static void HW_Motor_Init(bsp_motor_t *motor)
{
    if (motor == NULL) return;

    DL_TimerG_enableClock(motor->pwm_timer);
    DL_TimerG_startCounter(motor->pwm_timer);

    /* 编码器定时器可能为NULL(右电机使用GPIO中断) */
    if (motor->enc_timer != NULL) {
        DL_TimerG_enableClock(motor->enc_timer);
        DL_TimerG_startCounter(motor->enc_timer);
    }

    motor->Gpio_Config();
}

static void HW_Gpio_Write(void *port, uint32_t pin, uint8_t level)
{
    if (port == NULL) return;
    GPIO_WritePin((GPIO_Regs *)port, pin, level);
}

static void HW_Pwm_Write(void *timer, uint32_t channel, uint32_t duty)
{
    if (timer == NULL) return;
    DL_TimerG_setCaptureCompareValue((GPTIMER_Regs *)timer, duty, (DL_TIMER_CC_INDEX)channel);
}

/* 左电机编码器读取 — 硬件QEI */
static int32_t HW_Enc_Read_Left(void *enc_timer)
{
    static uint32_t last_count = 0;
    static bool first_read = true;

    uint32_t current_count = DL_Timer_getTimerCount((GPTIMER_Regs *)enc_timer) & 0xFFFF;

    if (first_read) {
        last_count = current_count;
        first_read = false;
        return 0;
    }

    int16_t delta = (int16_t)(last_count - current_count);
    last_count = current_count;
    return (int32_t)delta;
}

/* 右电机编码器读取 — GPIO中断计数差值 */
static int32_t HW_Enc_Read_Right(void *enc_timer)
{
    (void)enc_timer;  /* 右编码器不使用定时器 */
    int32_t current = g_right_enc_count;
    int32_t delta = current - s_right_enc_last;
    s_right_enc_last = current;
    return delta;
}

/* ================= 2. 对象实例化与引脚拼装 ================= */

bsp_motor_t Motor_Left = {
    .dir_pin1   = {MOTOR_LEFT_DIR1_PORT, MOTOR_LEFT_DIR1_PIN},
    .dir_pin2   = {MOTOR_LEFT_DIR2_PORT, MOTOR_LEFT_DIR2_PIN},
    .pwm_timer  = MOTOR_LEFT_PWM_TIMER,
    .pwm_channel = MOTOR_LEFT_PWM_CHANNEL,
    .enc_timer  = MOTOR_LEFT_ENC_TIMER,
    .use_speed_pid = false,

    .Gpio_Config = HW_GPIO_Config,
    .Init        = HW_Motor_Init,
    .Gpio_Write  = HW_Gpio_Write,
    .Pwm_Write   = HW_Pwm_Write,
    .Enc_Read    = HW_Enc_Read_Left
};

bsp_motor_t Motor_Right = {
    .dir_pin1   = {MOTOR_RIGHT_DIR1_PORT, MOTOR_RIGHT_DIR1_PIN},
    .dir_pin2   = {MOTOR_RIGHT_DIR2_PORT, MOTOR_RIGHT_DIR2_PIN},
    .pwm_timer  = MOTOR_RIGHT_PWM_TIMER,
    .pwm_channel = MOTOR_RIGHT_PWM_CHANNEL,
    .enc_timer  = NULL,  /* 右编码器使用GPIO中断，不使用定时器 */
    .use_speed_pid = false,

    .Gpio_Config = HW_GPIO_Config,
    .Init        = HW_Motor_Init,
    .Gpio_Write  = HW_Gpio_Write,
    .Pwm_Write   = HW_Pwm_Write,
    .Enc_Read    = HW_Enc_Read_Right
};

/* ================= 3. 右编码器GPIO中断处理 ================= */

void Right_Encoder_IRQHandler(void)
{
    /* 读取PHA和PHB当前电平，判断旋转方向 */
    uint8_t pha = DL_GPIO_readPins(RIGHT_ENC_PHA_PORT, RIGHT_ENC_PHA_PIN) ? 1 : 0;
    uint8_t phb = DL_GPIO_readPins(RIGHT_ENC_PHB_PORT, RIGHT_ENC_PHB_PIN) ? 1 : 0;

    /* PHA与PHB同相=正转，反相=反转 */
    if (pha ^ phb) {
        g_right_enc_count++;
    } else {
        g_right_enc_count--;
    }
}

/* ================= 4. 速度PID ================= */

/**
 * @brief   单电机速度PID更新（前馈 + PID修正）
 * @note    前馈: target_speed 直接作为基础PWM
 *          PID修正: 根据编码器反馈修正PWM，消除左右电机机械差异
 *          最终PWM = target_speed + PID_correction
 */
static void Speed_PID_Update_Single(bsp_motor_t *motor, bsp_pid_t *pid)
{
    if (motor == NULL || pid == NULL) return;
    if (!motor->use_speed_pid) return;

    /* 读取编码器速度 */
    Bsp_Motor_Update_Status(motor);

    /* 编码器速度转换为0-100速度单位 */
    float actual_speed = 0;
    if (s_speed_scale > 0.001f) {
        actual_speed = (float)motor->encoder_speed / s_speed_scale;
    }

    /* PID计算修正量: setpoint=target_speed, feedback=actual_speed */
    float correction = Pid_Compute(pid, (float)motor->target_speed, actual_speed);

    /* 前馈 + 修正 */
    int32_t pwm = motor->target_speed + (int32_t)correction;

    /* 限幅 */
    if (pwm > 100)  pwm = 100;
    if (pwm < -100) pwm = -100;

    /* 写入电机 */
    Bsp_Motor_Write_Pwm(motor, pwm);
}

void App_Motor_Speed_PID_Update(void)
{
    Speed_PID_Update_Single(&Motor_Left,  &s_left_speed_pid);
    Speed_PID_Update_Single(&Motor_Right, &s_right_speed_pid);
}

void App_Motor_Enable_Speed_PID(bool enable)
{
    Motor_Left.use_speed_pid  = enable;
    Motor_Right.use_speed_pid = enable;

    if (enable) {
        /* 切换到闭环时，复位PID防止积分突跳 */
        Pid_Reset(&s_left_speed_pid);
        Pid_Reset(&s_right_speed_pid);
    } else {
        /* 切换回开环时，同步current_pwm = target_speed */
        Bsp_Motor_Write_Pwm(&Motor_Left,  Motor_Left.target_speed);
        Bsp_Motor_Write_Pwm(&Motor_Right, Motor_Right.target_speed);
    }
}

void App_Motor_Set_Speed_Scale(float scale)
{
    if (scale > 0.001f) {
        s_speed_scale = scale;
    }
}

/* ================= 5. 对外业务切入点 ================= */

void App_Motor_Init(void)
{
    HW_Motor_Init(&Motor_Left);
    Bsp_Motor_Init_Device(&Motor_Left);

    HW_Motor_Init(&Motor_Right);
    Bsp_Motor_Init_Device(&Motor_Right);

    /* 使能右编码器GPIO中断 */
    DL_GPIO_enableInterrupt(RIGHT_ENC_PHA_PORT, RIGHT_ENC_PHA_PIN);
    NVIC_EnableIRQ(GPIOB_INT_IRQn);

    /* 初始化速度PID */
    Pid_Init(&s_left_speed_pid,
             MOTOR_SPEED_PID_KP, MOTOR_SPEED_PID_KI, MOTOR_SPEED_PID_KD,
             MOTOR_SPEED_PID_ILIMIT, MOTOR_SPEED_PID_OLIMIT);
    Pid_Init(&s_right_speed_pid,
             MOTOR_SPEED_PID_KP, MOTOR_SPEED_PID_KI, MOTOR_SPEED_PID_KD,
             MOTOR_SPEED_PID_ILIMIT, MOTOR_SPEED_PID_OLIMIT);
}

void Motor_Set_Speed(int32_t speed)
{
    Bsp_Motor_Set_Speed(&Motor_Left, speed);
}

void Motor_Forward(int32_t speed)
{
    Bsp_Motor_Set_Speed(&Motor_Left, speed);
}

void Motor_Backward(int32_t speed)
{
    Bsp_Motor_Set_Speed(&Motor_Left, -speed);
}

void Motor_Stop(void)
{
    Bsp_Motor_Set_Speed(&Motor_Left, 0);
}

void Motor_Update_Status(void)
{
    Bsp_Motor_Update_Status(&Motor_Left);
    Bsp_Motor_Update_Status(&Motor_Right);
}

void Motor_Right_Set_Speed(int32_t speed)
{
    Bsp_Motor_Set_Speed(&Motor_Right, speed);
}
