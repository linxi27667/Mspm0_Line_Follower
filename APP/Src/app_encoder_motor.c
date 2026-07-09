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
#include <elog.h>

/* ================= 右编码器中断计数 ================= */
volatile int32_t g_right_enc_count = 0;
static int32_t   s_right_enc_last  = 0;

/* ================= 速度PID ================= */
static bsp_pid_t s_left_speed_pid;
static bsp_pid_t s_right_speed_pid;
/* 国一方案: 左右编码器分辨率不同 (左 QEI 4x / 右 GPIO 2x), 必须分别标定 scale */
static float     s_speed_scale_left  = MOTOR_SPEED_SCALE_LEFT_DEFAULT;
static float     s_speed_scale_right = MOTOR_SPEED_SCALE_RIGHT_DEFAULT;

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

/* 左电机编码器读取 — 硬件QEI
 * 实测: 正转时 QEI 计数递减 (delta<0), 反转时递增 (delta>0)。
 * 取反 delta 使正转=正数, 反转=负数, 与右编码器方向一致。 */
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

    int16_t delta = (int16_t)(current_count - last_count);
    last_count = current_count;
    return -(int32_t)delta;  /* 取反: QEI 方向与电机正转相反 */
}

/* 右电机编码器读取 — GPIO中断计数差值
 * 修复: 增加 first_read 保护，避免首次调用返回累计大值导致 PID 误差尖峰 */
static int32_t HW_Enc_Read_Right(void *enc_timer)
{
    (void)enc_timer;  /* 右编码器不使用定时器 */
    static bool first_read = true;

    int32_t current = g_right_enc_count;
    if (first_read) {
        s_right_enc_last = current;
        first_read = false;
        return 0;
    }

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
    /* 原子读取 PHA+PHB (单次 DIN 寄存器读取), 避免两次 readPins 间编码器
     * 位置变化导致方向误判。实测: 分两次读取时反转方向计数异常。 */
    uint32_t din = RIGHT_ENC_PHA_PORT->DIN31_0;
    uint8_t pha = (din & RIGHT_ENC_PHA_PIN) ? 1 : 0;
    uint8_t phb = (din & RIGHT_ENC_PHB_PIN) ? 1 : 0;

    /* PHA与PHB异相=正转(递增)，同相=反转(递减) */
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
 *          scale: 左右独立的速度比例尺 (国一方案: 编码器分辨率不同)
 */
static void Speed_PID_Update_Single(bsp_motor_t *motor, bsp_pid_t *pid, float scale)
{
    if (motor == NULL || pid == NULL) return;
    if (!motor->use_speed_pid) return;

    /* 读取编码器速度 */
    Bsp_Motor_Update_Status(motor);

    /* 编码器速度转换为0-100速度单位 (左右独立 scale) */
    float actual_speed = 0;
    if (scale > 0.001f) {
        actual_speed = (float)motor->encoder_speed / scale;
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
    Speed_PID_Update_Single(&Motor_Left,  &s_left_speed_pid,  s_speed_scale_left);
    Speed_PID_Update_Single(&Motor_Right, &s_right_speed_pid, s_speed_scale_right);
}

void App_Motor_Enable_Speed_PID(bool enable)
{
    Motor_Left.use_speed_pid  = enable;
    Motor_Right.use_speed_pid = enable;

    if (enable) {
        /* 切换到闭环时，复位PID防止积分突跳 */
        Pid_Reset(&s_left_speed_pid);
        Pid_Reset(&s_right_speed_pid);
        /* 修复: 同步编码器基准，避免首次读取产生大 delta 导致 PID 误差尖峰。
         * 调用 Bsp_Motor_Update_Status 更新 last_count 为当前值，
         * 然后清零 encoder_speed 丢弃这次读取。 */
        Bsp_Motor_Update_Status(&Motor_Left);
        Bsp_Motor_Update_Status(&Motor_Right);
        Motor_Left.encoder_speed  = 0;
        Motor_Right.encoder_speed = 0;
    } else {
        /* 切换回开环时，同步current_pwm = target_speed */
        Bsp_Motor_Write_Pwm(&Motor_Left,  Motor_Left.target_speed);
        Bsp_Motor_Write_Pwm(&Motor_Right, Motor_Right.target_speed);
    }
}

void App_Motor_Set_Speed_Scale(float scale)
{
    /* 兼容旧调用: 同时设置左右 scale */
    if (scale > 0.001f) {
        s_speed_scale_left  = scale;
        s_speed_scale_right = scale;
    }
}

void App_Motor_Set_Speed_Scale_Left(float scale)
{
    if (scale > 0.001f) {
        s_speed_scale_left = scale;
    }
}

void App_Motor_Set_Speed_Scale_Right(float scale)
{
    if (scale > 0.001f) {
        s_speed_scale_right = scale;
    }
}

/* 速度比例尺自动标定 (国一方案核心)
 * 流程: 切开环 → PWM=50 跑1秒 → 测左右 encoder_speed → scale=enc/50 → RTT打印
 * 使用前必须悬空车轮! */
#define MOTOR_CALIB_PWM         50
#define MOTOR_CALIB_SETTLE_MS   200     /* 加速稳定时间 */
#define MOTOR_CALIB_SAMPLE_MS   5       /* 采样周期(与速度PID一致) */
#define MOTOR_CALIB_SAMPLES     200     /* 200*5ms=1s */
void App_Motor_Calibrate_Scale(void)
{
    elog_i("CALIB", "==== Speed Scale Calibration ====");
    elog_i("CALIB", "Lift wheels! Running PWM=%d for %dms...",
           MOTOR_CALIB_PWM, MOTOR_CALIB_SAMPLES * MOTOR_CALIB_SAMPLE_MS);

    /* 切开环, 直写 PWM (避免闭环干扰测量) */
    App_Motor_Enable_Speed_PID(false);
    Bsp_Motor_Set_Speed(&Motor_Left,  MOTOR_CALIB_PWM);
    Bsp_Motor_Set_Speed(&Motor_Right, MOTOR_CALIB_PWM);

    /* 加速稳定 */
    Bsp_Delay_ms(MOTOR_CALIB_SETTLE_MS);

    /* 同步编码器基准, 丢弃首次读取 */
    Bsp_Motor_Update_Status(&Motor_Left);
    Bsp_Motor_Update_Status(&Motor_Right);
    Motor_Left.encoder_speed  = 0;
    Motor_Right.encoder_speed = 0;

    /* 采样 1 秒 */
    int32_t left_sum = 0, right_sum = 0;
    for (uint16_t i = 0; i < MOTOR_CALIB_SAMPLES; i++) {
        Bsp_Motor_Update_Status(&Motor_Left);
        Bsp_Motor_Update_Status(&Motor_Right);
        left_sum  += Motor_Left.encoder_speed;
        right_sum += Motor_Right.encoder_speed;
        Bsp_Delay_ms(MOTOR_CALIB_SAMPLE_MS);
    }

    /* 停车 */
    Bsp_Motor_Set_Speed(&Motor_Left,  0);
    Bsp_Motor_Set_Speed(&Motor_Right, 0);
    Bsp_Delay_ms(100);

    /* 计算平均 encoder_speed 和 scale */
    float left_avg  = (float)left_sum  / MOTOR_CALIB_SAMPLES;
    float right_avg = (float)right_sum / MOTOR_CALIB_SAMPLES;

    if (left_avg  > 1.0f) s_speed_scale_left  = left_avg  / (float)MOTOR_CALIB_PWM;
    if (right_avg > 1.0f) s_speed_scale_right = right_avg / (float)MOTOR_CALIB_PWM;

    elog_i("CALIB", "LeftEncAvg:%ld RightEncAvg:%ld", (long)left_avg, (long)right_avg);
    elog_i("CALIB", "Scale Left:%ld/1000 Right:%ld/1000",
           (long)(s_speed_scale_left  * 1000),
           (long)(s_speed_scale_right * 1000));
    elog_i("CALIB", "Write to main.c:");
    elog_i("CALIB", "  #define USER_MOTOR_SPEED_SCALE_LEFT   %d/1000", (long)(s_speed_scale_left  * 1000));
    elog_i("CALIB", "  #define USER_MOTOR_SPEED_SCALE_RIGHT  %d/1000", (long)(s_speed_scale_right * 1000));
    elog_i("CALIB", "==== Calibration Done ====");
}

/* ================= 5. 对外业务切入点 ================= */

void App_Motor_Init(void)
{
    /* 修复: Bsp_Motor_Init_Device 内部已调用 motor->Init (即 HW_Motor_Init)，
     * 原代码重复调用导致时钟使能/启动计数器执行两次。删除显式调用。 */
    Bsp_Motor_Init_Device(&Motor_Left);
    Bsp_Motor_Init_Device(&Motor_Right);

    /* 使能右编码器GPIO中断 NVIC
     * 注: SysConfig 生成的 SYSCFG_DL_GPIO_init 已调用
     * DL_GPIO_setLowerPinsPolarity + enableInterrupt，此处仅需 NVIC 使能 */
    NVIC_EnableIRQ(GPIOB_INT_IRQn);

    /* 初始化速度PID */
    Pid_Init(&s_left_speed_pid,
             MOTOR_SPEED_PID_KP, MOTOR_SPEED_PID_KI, MOTOR_SPEED_PID_KD,
             MOTOR_SPEED_PID_ILIMIT, MOTOR_SPEED_PID_OLIMIT);
    Pid_Init(&s_right_speed_pid,
             MOTOR_SPEED_PID_KP, MOTOR_SPEED_PID_KI, MOTOR_SPEED_PID_KD,
             MOTOR_SPEED_PID_ILIMIT, MOTOR_SPEED_PID_OLIMIT);

    /* 修复: 启用积分分离，避免启动/急停时积分饱和导致超调
     * 误差超过阈值时不累加积分，PID 仍正常计算 P/D */
    s_left_speed_pid.integral_sep_threshold  = MOTOR_SPEED_PID_INTEGRAL_SEP;
    s_right_speed_pid.integral_sep_threshold = MOTOR_SPEED_PID_INTEGRAL_SEP;
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
