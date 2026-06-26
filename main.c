/**
 * @file    main.c
 * @brief   MSPM0G3507 主程序（参考 f407zet6 架构：模块化初始化 + elog + 调试开关）
 * @note    架构:
 *            System_Init()  — RTT/SysConfig/SysTick/elog/外设模块统一初始化
 *            SelfTest 阶段  — 由 SELFTEST_MODE 宏控制，上电自检各设备
 *            Track 阶段     — 循迹主循环
 *          调试:
 *            SELFTEST_MODE=1 启动后跑一遍自检并打印诊断
 *            SELFTEST_MODE=0 跳过自检直接进入循迹模式
 */

/* ==================================================================
 * ====== 用户调参区 (所有可调参数集中于此,方便手动调试) ======
 * 说明: 此处定义优先于 track.h / app_encoder_motor.h 中的默认值
 *       修改后重新编译烧录即可生效
 * ================================================================== */

/* ---------- 1. 循迹线PID (主循迹,输入灰度误差,输出转向量) ----------
 * 调参方法:
 *   1. 先只调KP: 从小值(2.0)开始,车能跟线但反应慢→加大KP
 *   2. 车甩出弯道→KP太大,减小
 *   3. 车左右震荡→加KD(从0.5开始),KD约为KP的1/5~1/3
 *   4. 直线有静差→加KI(从0.1开始),但通常循迹KI=0
 *   5. 转向量过大→减小OLIMIT */
#define USER_LINE_PID_KP           8.0f    /* 比例增益(建议2~15) */
#define USER_LINE_PID_KI           0.0f    /* 积分增益(循迹通常为0) */
#define USER_LINE_PID_KD           1.5f    /* 微分增益(建议KP的1/5~1/3) */
#define USER_LINE_PID_ILIMIT       50.0f   /* 积分限幅 */
#define USER_LINE_PID_OLIMIT       40.0f   /* 输出限幅(转向量最大值) */
#define USER_LINE_PID_DERIV_ALPHA  0.6f    /* 不完全微分系数(0~1,越大滤波越弱) */

/* ---------- 2. 陀螺仪PID (丢线/直角弯时用,输入航向角偏差) ----------
 * 调参方法:
 *   1. 直角弯转不过去→加大KP
 *   2. 转过头→加KD或减小KP
 *   3. 丢线时车跑偏→加大KP */
#define USER_GYRO_PID_KP           3.0f    /* 比例增益 */
#define USER_GYRO_PID_KI           0.0f    /* 积分增益 */
#define USER_GYRO_PID_KD           0.5f    /* 微分增益 */
#define USER_GYRO_PID_ILIMIT       30.0f   /* 积分限幅 */
#define USER_GYRO_PID_OLIMIT       40.0f   /* 输出限幅 */

/* ---------- 3. 速度PID (电机闭环,输入目标速度,反馈编码器,输出PWM) ----------
 * 调参方法:
 *   1. 空转时PWM很高(如90)是正常的(编码器读数≈0,PID拼命加PWM)
 *   2. 接轮子后车不动→加大KP
 *   3. 车速震荡→加KD或减小KP
 *   4. 速度跟不上→加大OLIMIT或减小INTEGRAL_SEP
 * 速度比例尺(SPEED_SCALE): 需实车校准
 *   方法: 设PWM=50,测encoder_speed,SPEED_SCALE = encoder_speed / 50 */
#define USER_MOTOR_SPEED_PID_KP    0.8f    /* 速度PID比例增益 */
#define USER_MOTOR_SPEED_PID_KI    0.2f    /* 速度PID积分增益 */
#define USER_MOTOR_SPEED_PID_KD    0.0f    /* 速度PID微分增益 */
#define USER_MOTOR_SPEED_PID_ILIMIT 30.0f  /* 速度PID积分限幅 */
#define USER_MOTOR_SPEED_PID_OLIMIT 30.0f  /* 速度PID输出限幅(前馈+修正≤100) */
#define USER_MOTOR_SPEED_PID_INTEGRAL_SEP 15.0f /* 积分分离阈值(误差>此值不累加I) */
#define USER_MOTOR_SPEED_SCALE     1.0f    /* 编码器速度→速度单位比例尺(需实车校准) */

/* ---------- 4. 循迹策略参数 ----------
 * 调参方法:
 *   1. 车速太快冲出弯道→减小BASE_SPEED或SPEED_STRAIGHT
 *   2. 直道不够快→加大SPEED_STRAIGHT
 *   3. 弯道转不过→减小SPEED_CURVE或加大MOTOR_INNER_MIN
 *   4. 急转时内侧轮停转→减小MOTOR_INNER_MIN(最低15) */
#define USER_TRACK_BASE_SPEED      40      /* 基础速度(启动时) */
#define USER_TRACK_SPEED_STRAIGHT  60      /* 直道速度 */
#define USER_TRACK_SPEED_CURVE     35      /* 弯道速度 */
#define USER_TRACK_SPEED_RAMP_STEP 2       /* 速度渐变步进(避免突变抖动) */
#define USER_TRACK_MOTOR_INNER_MIN 15      /* 内侧电机最低速度(防急转停转) */
#define USER_TRACK_CIRCLES         1       /* 目标圈数 */

/* ---------- 5. 丢线/直角弯参数 ----------
 * 调参方法:
 *   1. 丢线后车立即停车→加大LINE_LOST_TIMEOUT
 *   2. 直角弯检测不到→减小RIGHT_ANGLE_THRESHOLD
 *   3. 普通弯道被误判为直角弯→加大RIGHT_ANGLE_THRESHOLD或CONFIRM_FRAMES */
#define USER_LINE_LOST_TIMEOUT     500     /* 丢线超时停车(ms) */
#define USER_LINE_LOST_GAIN        2.0f    /* 丢线时转向增益(无陀螺仪时用) */
#define USER_RIGHT_ANGLE_THRESHOLD 2.5f    /* 直角弯检测误差阈值 */
#define USER_RIGHT_ANGLE_CONFIRM_FRAMES 3  /* 直角弯连续确认帧数 */
#define USER_RIGHT_ANGLE_TIMEOUT   1000    /* 直角弯超时(ms) */
#define USER_RIGHT_ANGLE_DONE_ERR  5.0f    /* 直角弯完成角度误差(度) */

/* ---------- 6. 起点线/十字路口参数 ---------- */
#define USER_START_LINE_MIN_BLACK  6       /* 起点线最少黑色通道数 */
#define USER_CROSS_MIN_BLACK       4       /* 十字路口中间黑色通道数 */

/* ==================================================================
 * ====== 用户调参区结束 (以下不要修改) ======
 * ================================================================== */

#include "ti_msp_dl_config.h"
#include <elog.h>
#include "SEGGER_RTT.h"
#include "bsp_uart.h"
#include "app_all.h"
#include "track.h"
#include <stdio.h>

/* ================= 调试开关 ================= */
/* SELFTEST_MODE=1: 上电后自动跑一次自检（电机/编码器/MPU/灰度） */
/* SELFTEST_MODE=0: 跳过自检，直接进入循迹模式 */
#ifndef SELFTEST_MODE
#define SELFTEST_MODE  0
#endif

/* ================= 全局时标 ================= */
extern volatile uint32_t systick_ms;  /* 定义在 bsp_common.c */

/* ================= 中断处理函数（全部集中于此） ================= */

void SysTick_Handler(void)
{
    systick_ms++;
}

/* ================= HardFault 诊断 ================= */
/* Cortex-M0+ 仅有 SHCSR, 没有 CFSR/HFSR/DFSR */
__attribute__((naked)) void HardFault_Handler(void)
{
    __asm volatile(
        "mov r0, sp\n"
        "ldr r1, =HardFault_Diag\n"
        "bx r1\n"
    );
}

void HardFault_Diag(uint32_t *sp)
{
    uint32_t r0  = sp[0];
    uint32_t r1  = sp[1];
    uint32_t r2  = sp[2];
    uint32_t r3  = sp[3];
    uint32_t r12 = sp[4];
    uint32_t lr  = sp[5];
    uint32_t pc  = sp[6];
    uint32_t xpsr = sp[7];

    SEGGER_RTT_Write(0, "*** HARDFAULT ***\r\n", 20);
    elog_e("FAULT", "PC=0x%08lX LR=0x%08lX XPSR=0x%08lX",
           (unsigned long)pc, (unsigned long)lr, (unsigned long)xpsr);
    elog_e("FAULT", "R0=0x%08lX R1=0x%08lX R2=0x%08lX R3=0x%08lX R12=0x%08lX",
           (unsigned long)r0, (unsigned long)r1, (unsigned long)r2,
           (unsigned long)r3, (unsigned long)r12);
    elog_e("FAULT", "SHCSR=0x%04lX", (unsigned long)(SCB->SHCSR & 0xFFFF));

    while (1) { /* 死循环等待调试器 */ }
}

/* ================= GPIO 输入回读使能 ================= */
/* SysConfig 的 DL_GPIO_initDigitalOutput 不启用 INE (bit18),
 * 导致 GPIO_ReadPin(读DIN) 始终返回0。此处对所有输出引脚 OR 上 INE。 */
static void Enable_GPIO_InputReadback(void)
{
    const uint32_t INE_BIT = IOMUX_PINCM_INENA_ENABLE;

    /* 灰度 AD0/AD1/AD2 */
    IOMUX->SECCFG.PINCM[Grayscale_ADDR_A_AD0_IOMUX] |= INE_BIT;
    IOMUX->SECCFG.PINCM[Grayscale_ADDR_A_AD1_IOMUX] |= INE_BIT;
    IOMUX->SECCFG.PINCM[Grayscale_ADDR_B_AD2_IOMUX] |= INE_BIT;

    /* 电机方向引脚 */
    IOMUX->SECCFG.PINCM[Monitor_Dir_Monitor_AIN1_IOMUX] |= INE_BIT;
    IOMUX->SECCFG.PINCM[Monitor_Dir_Monitor_AIN2_IOMUX] |= INE_BIT;
    IOMUX->SECCFG.PINCM[Right_Motor_Dir_AIN1_IOMUX] |= INE_BIT;
    IOMUX->SECCFG.PINCM[Right_Motor_Dir_AIN2_IOMUX] |= INE_BIT;

    /* 右编码器 PHA/PHB (PB12/PB13) — 确保 INE 使能, ISR 中读 DIN 判断方向 */
    IOMUX->SECCFG.PINCM[Right_Encoder_PHA_IOMUX] |= INE_BIT;
    IOMUX->SECCFG.PINCM[Right_Encoder_PHB_IOMUX] |= INE_BIT;

    /* LED 引脚 */
    IOMUX->SECCFG.PINCM[Led_Group_LED1_IOMUX] |= INE_BIT;
    IOMUX->SECCFG.PINCM[Led_Group_LED2_IOMUX] |= INE_BIT;
    IOMUX->SECCFG.PINCM[Led_Group_LED3_IOMUX] |= INE_BIT;
    IOMUX->SECCFG.PINCM[Led_Group_LED4_IOMUX] |= INE_BIT;
}

/* ================= 外设中断 ISR ================= */

extern uint8_t s_rx_dma_buf[];

void UART0_IRQHandler(void)
{
    uint32_t irq = DL_UART_getPendingInterrupt(UART0);
    switch (irq) {
        case DL_UART_IIDX_RX_TIMEOUT_ERROR: {
            DL_DMA_disableChannel(DMA, DMA_CH0_RX);
            uint16_t rx_len = BSP_UART_RX_BUF_SIZE -
                              DL_DMA_getTransferSize(DMA, DMA_CH0_RX);
            while (!DL_UART_isRXFIFOEmpty(UART0)) {
                if (rx_len < BSP_UART_RX_BUF_SIZE) {
                    s_rx_dma_buf[rx_len++] = (uint8_t)DL_UART_receiveData(UART0);
                } else {
                    (void)DL_UART_receiveData(UART0);
                }
            }
            Uart_RX_IRQHandler(rx_len);
            break;
        }
        default: break;
    }
}

void DMA_IRQHandler(void)
{
    switch (DL_DMA_getPendingInterrupt(DMA)) {
        case DL_DMA_EVENT_IIDX_DMACH1:
            Uart_Tx_DMA_Done_IRQHandler();
            break;
        default: break;
    }
}

/* GPIO GROUP1 中断 — 右编码器PHA双沿触发 */
void GROUP1_IRQHandler(void)
{
    if (DL_GPIO_getEnabledInterruptStatus(RIGHT_ENC_PHA_PORT,
                                          RIGHT_ENC_PHA_PIN)) {
        DL_GPIO_clearInterruptStatus(RIGHT_ENC_PHA_PORT, RIGHT_ENC_PHA_PIN);
        Right_Encoder_IRQHandler();
    }
}

/* =================================================================
 * 系统初始化 — 参考 f407zet6 main.c 的初始化顺序
 * ================================================================= */
static void System_Init(void)
{
    /* 1. RTT 优先（最早的日志通道） */
    SEGGER_RTT_Init();

    /* 2. SysConfig 生成的外设初始化 */
    SYSCFG_DL_init();

    /* 3. SysTick 1ms */
    SysTick_Config(CPUCLK_FREQ / 1000);

    /* 4. elog 日志框架 */
    elog_init();
    elog_set_fmt(ELOG_LVL_ASSERT, ELOG_FMT_LVL | ELOG_FMT_TAG | ELOG_FMT_TIME);
    elog_set_fmt(ELOG_LVL_ERROR,  ELOG_FMT_LVL | ELOG_FMT_TAG | ELOG_FMT_TIME);
    elog_set_fmt(ELOG_LVL_WARN,   ELOG_FMT_LVL | ELOG_FMT_TAG | ELOG_FMT_TIME);
    elog_set_fmt(ELOG_LVL_INFO,   ELOG_FMT_LVL | ELOG_FMT_TAG | ELOG_FMT_TIME);
    elog_set_fmt(ELOG_LVL_DEBUG,  ELOG_FMT_LVL | ELOG_FMT_TAG | ELOG_FMT_TIME | ELOG_FMT_LINE);
    elog_start();

    /* 5. 启用 GPIO 输入回读（诊断用） */
    Enable_GPIO_InputReadback();

    /* 6. 应用层模块初始化（顺序参考 f407zet6: Motor/Safety/Key/Encoder） */
    App_Led_Init();
    App_Key_Init();
    App_Uart_Init();

    elog_i("SYS", "System initialized - CPU=%luHz", (unsigned long)CPUCLK_FREQ);
}

/* =================================================================
 * 自检模块（SELFTEST_MODE=1 时执行）
 * ================================================================= */
#if SELFTEST_MODE

static void Diag_PINCM(void)
{
    elog_i("IOMUX", "=== PINCM Dump (expect 0x00040081 with INE) ===");
    elog_i("IOMUX", "PA26(AD0, PINCM59)=0x%08lX",
           (unsigned long)IOMUX->SECCFG.PINCM[Grayscale_ADDR_A_AD0_IOMUX]);
    elog_i("IOMUX", "PA24(AD1, PINCM54)=0x%08lX",
           (unsigned long)IOMUX->SECCFG.PINCM[Grayscale_ADDR_A_AD1_IOMUX]);
    elog_i("IOMUX", "PB24(AD2, PINCM52)=0x%08lX",
           (unsigned long)IOMUX->SECCFG.PINCM[Grayscale_ADDR_B_AD2_IOMUX]);
    elog_i("IOMUX", "PA22(LDir1, PINCM47)=0x%08lX",
           (unsigned long)IOMUX->SECCFG.PINCM[Monitor_Dir_Monitor_AIN1_IOMUX]);
    elog_i("IOMUX", "PA15(LDir2, PINCM37)=0x%08lX",
           (unsigned long)IOMUX->SECCFG.PINCM[Monitor_Dir_Monitor_AIN2_IOMUX]);
    elog_i("IOMUX", "PB0(RDir1, PINCM12)=0x%08lX",
           (unsigned long)IOMUX->SECCFG.PINCM[Right_Motor_Dir_AIN1_IOMUX]);
    elog_i("IOMUX", "PB11(RDir2, PINCM28)=0x%08lX",
           (unsigned long)IOMUX->SECCFG.PINCM[Right_Motor_Dir_AIN2_IOMUX]);
    elog_i("IOMUX", "PB4(LED1, PINCM17)=0x%08lX [ref]",
           (unsigned long)IOMUX->SECCFG.PINCM[Led_Group_LED1_IOMUX]);

    /* PWM 引脚 PINCM (应为外设功能) */
    elog_i("IOMUX", "PA17(LPWM, PINCM39)=0x%08lX [expect PF=TIMG7]",
           (unsigned long)IOMUX->SECCFG.PINCM[IOMUX_PINCM39]);
    elog_i("IOMUX", "PB10(RPWM, PINCM27)=0x%08lX [expect PF=TIMG6]",
           (unsigned long)IOMUX->SECCFG.PINCM[IOMUX_PINCM27]);

    /* GPIO 寄存器 */
    elog_i("GPIO", "A: DOE=0x%08lX DOUT=0x%08lX DIN=0x%08lX",
           (unsigned long)GPIOA->DOE31_0, (unsigned long)GPIOA->DOUT31_0,
           (unsigned long)GPIOA->DIN31_0);
    elog_i("GPIO", "B: DOE=0x%08lX DOUT=0x%08lX DIN=0x%08lX",
           (unsigned long)GPIOB->DOE31_0, (unsigned long)GPIOB->DOUT31_0,
           (unsigned long)GPIOB->DIN31_0);

    /* PA27 ADC 引脚状态 (PA27 = IOMUX_PINCM60) */
    elog_i("IOMUX", "PA27(ADC, PINCM60)=0x%08lX [expect 0x00 analog]",
           (unsigned long)IOMUX->SECCFG.PINCM[IOMUX_PINCM60]);
}

static void SelfTest_MPU6050(void)
{
    elog_i("TEST", "==== MPU6050 Test ====");
    App_Mpu_Init();
    Bsp_Delay_ms(100);

    if (Mpu_Sensor.gyro_ok) {
        Mpu_Read_Data();
        elog_i("TEST", "MPU OK: ax=%.2f ay=%.2f az=%.2f",
               Mpu_Sensor.accel_x, Mpu_Sensor.accel_y, Mpu_Sensor.accel_z);
        elog_i("TEST", "MPU OK: gx=%.2f gy=%.2f gz=%.2f",
               Mpu_Sensor.gyro_x, Mpu_Sensor.gyro_y, Mpu_Sensor.gyro_z);
        elog_i("TEST", "MPU OK: temp=%.1fC", Mpu_Sensor.temp);
    } else {
        elog_e("TEST", "MPU FAIL: gyro_ok=0");
    }
    elog_i("TEST", "==== MPU6050 Done ====");
}

static void SelfTest_Motor_Encoder(void)
{
    elog_i("TEST", "==== Motor+Encoder Test ====");
    App_Motor_Init();
    Bsp_Delay_ms(50);

    /* 引脚说明 */
    elog_i("MOT", "Left:  PWM=TIMG7_CH0(PA17) DIR1=PA22 DIR2=PA15 Enc=TIMG8(PB21/PB22)");
    elog_i("MOT", "Right: PWM=TIMG6_CH0(PB10) DIR1=PB0  DIR2=PB11 Enc=GPIO(PB12/PB13)");

    /* PWM 定时器运行状态 + 寄存器诊断 */
    uint32_t t7_1 = DL_Timer_getTimerCount(TIMG7);
    uint32_t t6_1 = DL_Timer_getTimerCount(TIMG6);
    Bsp_Delay_ms(10);
    uint32_t t7_2 = DL_Timer_getTimerCount(TIMG7);
    uint32_t t6_2 = DL_Timer_getTimerCount(TIMG6);
    elog_i("MOT", "TIMG7 cnt: %lu->%lu (%s) LOAD=%lu",
           (unsigned long)t7_1, (unsigned long)t7_2,
           (t7_2 != t7_1) ? "RUNNING" : "STOPPED",
           (unsigned long)DL_Timer_getLoadValue(TIMG7));
    elog_i("MOT", "TIMG6 cnt: %lu->%lu (%s) LOAD=%lu",
           (unsigned long)t6_1, (unsigned long)t6_2,
           (t6_2 != t6_1) ? "RUNNING" : "STOPPED",
           (unsigned long)DL_Timer_getLoadValue(TIMG6));

    /* 编码器定时器诊断 */
    elog_i("MOT", "TIMG8(Enc) LOAD=%lu cnt=%lu",
           (unsigned long)DL_Timer_getLoadValue(MOTOR_LEFT_ENC_TIMER),
           (unsigned long)DL_Timer_getTimerCount(MOTOR_LEFT_ENC_TIMER));

    /* 同步编码器基准 (调用 Update_Status 让 last_count = 当前值, 首次返回0) */
    Bsp_Motor_Update_Status(&Motor_Left);
    Bsp_Motor_Update_Status(&Motor_Right);
    Motor_Left.encoder_speed  = 0;
    Motor_Right.encoder_speed = 0;

    /* ---- 正转测试: PWM=50, 每200ms采样一次, 共2秒 ----
     * 使用 Bsp_Motor_Update_Status 获取正确符号的 delta:
     *   左编码器(QEI 16位): int16_t cast 处理短间隔回绕
     *   右编码器(GPIO 32位): int32_t 无回绕 */
    elog_i("TEST", "Forward PWM=50 for 2s (sampled every 200ms)...");
    Bsp_Motor_Set_Speed(&Motor_Left, 50);
    Bsp_Motor_Set_Speed(&Motor_Right, 50);

    uint32_t cc7 = DL_TimerG_getCaptureCompareValue(TIMG7, DL_TIMER_CC_0_INDEX);
    uint32_t cc6 = DL_TimerG_getCaptureCompareValue(TIMG6, DL_TIMER_CC_0_INDEX);
    uint8_t ld1 = (GPIOA->DOUT31_0 & MOTOR_LEFT_DIR1_PIN)  ? 1 : 0;
    uint8_t ld2 = (GPIOA->DOUT31_0 & MOTOR_LEFT_DIR2_PIN)  ? 1 : 0;
    uint8_t rd1 = (GPIOB->DOUT31_0 & MOTOR_RIGHT_DIR1_PIN) ? 1 : 0;
    uint8_t rd2 = (GPIOB->DOUT31_0 & MOTOR_RIGHT_DIR2_PIN) ? 1 : 0;
    elog_i("MOT", "Fwd: CC7=%lu CC6=%lu (LOAD=99)", (unsigned long)cc7, (unsigned long)cc6);
    elog_i("MOT", "Fwd: LDir DOUT=[%d,%d] RDir DOUT=[%d,%d]", ld1, ld2, rd1, rd2);

    int32_t left_fwd = 0, right_fwd = 0;
    for (int i = 0; i < 10; i++) {
        Bsp_Delay_ms(200);
        Bsp_Motor_Update_Status(&Motor_Left);
        Bsp_Motor_Update_Status(&Motor_Right);
        left_fwd  += Motor_Left.encoder_speed;
        right_fwd += Motor_Right.encoder_speed;
    }
    Bsp_Motor_Set_Speed(&Motor_Left, 0);
    Bsp_Motor_Set_Speed(&Motor_Right, 0);
    Bsp_Delay_ms(300);

    elog_i("TEST", "Forward: LeftEnc=%ld RightEnc=%ld", (long)left_fwd, (long)right_fwd);

    if (left_fwd > 10 && right_fwd > 10) {
        elog_i("TEST", "Motor+Enc OK: both wheels rotated forward");
    } else if (left_fwd > 10 || right_fwd > 10) {
        elog_w("TEST", "Partial: L=%ld R=%ld (check wiring)", (long)left_fwd, (long)right_fwd);
    } else {
        elog_e("TEST", "Both FAIL - check: 1)Motor driver EN/STBY pin 2)Motor power supply 3)Wiring");
    }

    /* ---- 反转测试: PWM=-50, 每200ms采样一次, 共2秒 ---- */
    elog_i("TEST", "Backward PWM=-50 for 2s (sampled every 200ms)...");
    Bsp_Motor_Set_Speed(&Motor_Left, -50);
    Bsp_Motor_Set_Speed(&Motor_Right, -50);

    uint8_t ld1r = (GPIOA->DOUT31_0 & MOTOR_LEFT_DIR1_PIN)  ? 1 : 0;
    uint8_t ld2r = (GPIOA->DOUT31_0 & MOTOR_LEFT_DIR2_PIN)  ? 1 : 0;
    uint8_t rd1r = (GPIOB->DOUT31_0 & MOTOR_RIGHT_DIR1_PIN) ? 1 : 0;
    uint8_t rd2r = (GPIOB->DOUT31_0 & MOTOR_RIGHT_DIR2_PIN) ? 1 : 0;
    elog_i("MOT", "Bwd: LDir DOUT=[%d,%d] RDir DOUT=[%d,%d]", ld1r, ld2r, rd1r, rd2r);

    int32_t left_bwd = 0, right_bwd = 0;
    for (int i = 0; i < 10; i++) {
        Bsp_Delay_ms(200);
        Bsp_Motor_Update_Status(&Motor_Left);
        Bsp_Motor_Update_Status(&Motor_Right);
        left_bwd  += Motor_Left.encoder_speed;
        right_bwd += Motor_Right.encoder_speed;
    }
    Bsp_Motor_Set_Speed(&Motor_Left, 0);
    Bsp_Motor_Set_Speed(&Motor_Right, 0);

    elog_i("TEST", "Backward: LeftEnc=%ld RightEnc=%ld", (long)left_bwd, (long)right_bwd);

    /* 方向验证: 正转应>0, 反转应<0 */
    if (left_fwd > 10 && left_bwd < -10) {
        elog_i("TEST", "Left enc direction OK (fwd=%ld bwd=%ld)", (long)left_fwd, (long)left_bwd);
    } else {
        elog_w("TEST", "Left enc direction ISSUE (fwd=%ld bwd=%ld)", (long)left_fwd, (long)left_bwd);
    }
    if (right_fwd > 10 && right_bwd < -10) {
        elog_i("TEST", "Right enc direction OK (fwd=%ld bwd=%ld)", (long)right_fwd, (long)right_bwd);
    } else {
        elog_w("TEST", "Right enc direction ISSUE (fwd=%ld bwd=%ld)", (long)right_fwd, (long)right_bwd);
    }
    elog_i("TEST", "==== Motor+Encoder Done ====");
}

static void SelfTest_Grayscale(void)
{
    elog_i("TEST", "==== Grayscale Test ====");
    elog_i("GRAY", "AD0=PA26 AD1=PA24 AD2=PB24 ADC=PA27(CH0)");

    App_Grayscale_Init();
    Bsp_Delay_ms(50);

    /* 逐通道测试: 切换 AD0/AD1/AD2, 读取 ADC */
    for (uint8_t ch = 0; ch < 8; ch++) {
        uint8_t ad0 = ch & 0x01;
        uint8_t ad1 = (ch >> 1) & 0x01;
        uint8_t ad2 = (ch >> 2) & 0x01;
        GPIO_WritePin(GRAY_AD0_PORT, GRAY_AD0_PIN, ad0);
        GPIO_WritePin(GRAY_AD1_PORT, GRAY_AD1_PIN, ad1);
        GPIO_WritePin(GRAY_AD2_PORT, GRAY_AD2_PIN, ad2);
        Bsp_Delay_ms(10);
        Grayscale_Sensor.ADC_Read();  /* 丢弃第一次（建立时间） */
        Bsp_Delay_ms(5);
        uint16_t v = Grayscale_Sensor.ADC_Read();
        uint8_t rd0 = (GPIOA->DOUT31_0 & GRAY_AD0_PIN) ? 1 : 0;
        uint8_t rd1 = (GPIOA->DOUT31_0 & GRAY_AD1_PIN) ? 1 : 0;
        uint8_t rd2 = (GPIOB->DOUT31_0 & GRAY_AD2_PIN) ? 1 : 0;
        elog_i("GRAY", "CH%d AD=[%d%d%d] DOUT=[%d%d%d] adc=%u",
               ch, ad2, ad1, ad0, rd2, rd1, rd0, v);
    }

    /* BSP 框架扫描一轮 */
    for (uint8_t i = 0; i < 8; i++) {
        Grayscale_Update();
        Bsp_Delay_ms(10);
    }
    elog_i("TEST", "Gray BC=%d analog=[%u,%u,%u,%u,%u,%u,%u,%u]",
           Grayscale_Sensor.black_count,
           Grayscale_Sensor.analog[0], Grayscale_Sensor.analog[1],
           Grayscale_Sensor.analog[2], Grayscale_Sensor.analog[3],
           Grayscale_Sensor.analog[4], Grayscale_Sensor.analog[5],
           Grayscale_Sensor.analog[6], Grayscale_Sensor.analog[7]);
    elog_i("TEST", "==== Grayscale Done ====");
}

static void SelfTest_KeyLed(void)
{
    elog_i("TEST", "==== Key+LED Test ====");
    for (uint8_t i = 0; i < 4; i++) {
        Led_On(i);
        Bsp_Delay_ms(200);
        Led_Off(i);
    }
    elog_i("TEST", "==== Key+LED Done ====");
}

/* 自检主入口 */
static void Run_SelfTest(void)
{
    elog_i("SYS", "########## SelfTest Start ##########");

    Diag_PINCM();
    Bsp_Delay_ms(100);

    SelfTest_MPU6050();
    Bsp_Delay_ms(200);

    SelfTest_Grayscale();
    Bsp_Delay_ms(200);

    SelfTest_KeyLed();
    Bsp_Delay_ms(200);

    SelfTest_Motor_Encoder();
    Bsp_Delay_ms(200);

    elog_i("SYS", "########## SelfTest Complete ##########");
}

#endif /* SELFTEST_MODE */

/* =================================================================
 * 主函数
 * ================================================================= */
int main(void)
{
    System_Init();

    /* 启动延时: 给 RTT Logger 连接时间 */
    elog_i("SYS", "Boot delay 3s - connect RTT logger now");
    Bsp_Delay_ms(3000);

#if SELFTEST_MODE
    Run_SelfTest();
    elog_i("SYS", "Switching to tracking mode...");
    Bsp_Delay_ms(500);
#endif

    /* ====== 循迹模式 ====== */
    Track_Init();
    Track_Set_Circles(3);
    Track_Set_Speed(40);

    elog_i("SYS", "Ready. K1=Start K2=Stop K3=WhiteCal K4=BlackCal");

    uint32_t last_5ms = 0, last_10ms = 0, last_100ms = 0, last_500ms = 0, last_1000ms = 0;
    uint8_t  last_state = 0xFF, last_circle = 0xFF, last_bc = 0xFF;

    while (1)
    {
        uint32_t now = systick_ms;

        Track_Update();

        if ((now - last_5ms) >= 5) {
            last_5ms = now;
            App_Motor_Speed_PID_Update();
        }

        if ((now - last_10ms) >= 10) {
            last_10ms = now;
            Key_Scan_Task();
        }

        if ((now - last_500ms) >= 500) {
            last_500ms = now;
            uint8_t cur_state  = (uint8_t)Track.state;
            uint8_t cur_circle = (uint8_t)Track.current_circle;
            uint8_t cur_bc     = Grayscale_Sensor.black_count;

            bool changed = (cur_state != last_state) ||
                           (cur_circle != last_circle) ||
                           (cur_bc != last_bc);

            if (changed ||
                (cur_state != TRACK_STATE_IDLE &&
                 cur_state != TRACK_STATE_FINISHED)) {
                /* 诊断: 打印完整电机状态
                 * State/Circle/Error/LeftTarget/RightTarget/BlackCount
                 * LeftPwm/RightPwm/LeftEncoder/RightEncoder
                 * LeftDir1/LeftDir2/RightDir1/RightDir2 (方向引脚DOUT状态)
                 * LeftTotalPos/RightTotalPos (累计位置) */
                uint8_t ld1 = (GPIOA->DOUT31_0 & MOTOR_LEFT_DIR1_PIN)  ? 1 : 0;
                uint8_t ld2 = (GPIOA->DOUT31_0 & MOTOR_LEFT_DIR2_PIN)  ? 1 : 0;
                uint8_t rd1 = (GPIOB->DOUT31_0 & MOTOR_RIGHT_DIR1_PIN) ? 1 : 0;
                uint8_t rd2 = (GPIOB->DOUT31_0 & MOTOR_RIGHT_DIR2_PIN) ? 1 : 0;
                elog_i("CAR", "State:%d Circle:%d Error:%ld LeftTarget:%d RightTarget:%d BlackCount:%d",
                       Track.state, Track.current_circle,
                       (long)(Track.error * 1000),
                       Track.left_speed, Track.right_speed, cur_bc);
                elog_i("MOTOR", "LeftPwm:%ld RightPwm:%ld | LeftEnc:%ld RightEnc:%ld | LeftTotal:%ld RightTotal:%ld",
                       (long)Motor_Left.current_pwm, (long)Motor_Right.current_pwm,
                       (long)Motor_Left.encoder_speed, (long)Motor_Right.encoder_speed,
                       (long)Motor_Left.total_position, (long)Motor_Right.total_position);
                elog_i("MOTOR", "LeftDir1:%d LeftDir2:%d | RightDir1:%d RightDir2:%d",
                       ld1, ld2, rd1, rd2);
                last_state  = cur_state;
                last_circle = cur_circle;
                last_bc     = cur_bc;
            }
        }

        /* ====== 灰度传感器诊断（每1秒打印8通道ADC原始值+数字值+校准基准） ======
         * ADC: 原始ADC值, DIG: 黑白判定(0=白 1=黑), CAL: 校准基准(black/white) */
        if ((now - last_1000ms) >= 1000) {
            last_1000ms = now;
            elog_i("GRAY", "ADC_Ch0:%d ADC_Ch1:%d ADC_Ch2:%d ADC_Ch3:%d ADC_Ch4:%d ADC_Ch5:%d ADC_Ch6:%d ADC_Ch7:%d",
                   Grayscale_Sensor.analog[0], Grayscale_Sensor.analog[1],
                   Grayscale_Sensor.analog[2], Grayscale_Sensor.analog[3],
                   Grayscale_Sensor.analog[4], Grayscale_Sensor.analog[5],
                   Grayscale_Sensor.analog[6], Grayscale_Sensor.analog[7]);
            elog_i("GRAY", "Digital:%d %d %d %d %d %d %d %d | BlackCount:%d",
                   Grayscale_Sensor.digital[0], Grayscale_Sensor.digital[1],
                   Grayscale_Sensor.digital[2], Grayscale_Sensor.digital[3],
                   Grayscale_Sensor.digital[4], Grayscale_Sensor.digital[5],
                   Grayscale_Sensor.digital[6], Grayscale_Sensor.digital[7],
                   Grayscale_Sensor.black_count);
            elog_i("GRAY", "Cal: Black:%d White:%d | HystHigh:%d HystLow:%d",
                   Grayscale_Sensor.black[0], Grayscale_Sensor.white[0],
                   (int)((Grayscale_Sensor.black[0] + Grayscale_Sensor.white[0]) / 2 +
                         (Grayscale_Sensor.white[0] - Grayscale_Sensor.black[0]) / 4),
                   (int)((Grayscale_Sensor.black[0] + Grayscale_Sensor.white[0]) / 2 -
                         (Grayscale_Sensor.white[0] - Grayscale_Sensor.black[0]) / 4));
        }

        if ((now - last_100ms) >= 100) {
            last_100ms = now;
            bsp_key_event_t evt;
            for (uint8_t i = 0; i < BSP_KEY_NUM; i++) {
                evt = Key_GetEvent(i);
                if (evt == BSP_KEY_EVENT_PUSH) {
                    Led_Toggle(i);
                    elog_i("KEY", "K%d pressed", (int)i);
                    if (i == 0) { Track_Start(); elog_i("CTRL", "Tracking started"); }
                    if (i == 1) { Track_Stop();  elog_i("CTRL", "Tracking stopped"); }
                    if (i == 2) { Track_Calibrate_White(); elog_i("SENSOR", "White calibrated"); }
                    if (i == 3) { Track_Calibrate_Black(); elog_i("SENSOR", "Black calibrated"); }
                }
            }
        }

        {
            uint8_t frame[BSP_UART_RX_BUF_SIZE + 1];
            uint16_t len = 0;
            while (Uart_Get_Frame(frame, &len)) {
                if (len >= BSP_UART_RX_BUF_SIZE) len = BSP_UART_RX_BUF_SIZE - 1;
                frame[len] = '\0';
                elog_i("COMM", "RX(%u): %s", (unsigned)len, (char*)frame);
            }
        }
    }
}
