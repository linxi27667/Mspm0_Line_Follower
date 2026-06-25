/**
 * @file    main.c
 * @brief   MSPM0G3507 裸机调度入口 — 四层架构调度层
 * @note    所有中断处理函数 + 时标轮询 + 组合逻辑集中于此
 *          UART RX: DMA CH0 + IDLE/Timeout 帧检测 + 字节FIFO + 帧长队列（多帧缓冲）
 *          UART TX: DMA CH1 零拷贝（DMA 直接读 TX FIFO）+ 完成中断自动链接
 */
#include "ti_msp_dl_config.h"
#include "my_easylog.h"
#include "bsp_uart.h"
#include "app_all.h"
#include "track.h"
#include <stdio.h>

/* ================= 全局时标 ================= */

extern volatile uint32_t systick_ms;  /* 定义在 bsp_common.c */

/* ================= 中断处理函数（全部集中于此） ================= */

/* SysTick 1ms 中断 */
void SysTick_Handler(void)
{
    systick_ms++;
}

/* UART0 中断 — IDLE/Timeout 帧检测（DMA 已自动接收数据到 s_rx_dma_buf）
 * 流程：停 DMA → 读已收字节数 → 排空硬件 FIFO 残余 → 推入软件 FIFO + 重启 DMA */
extern uint8_t s_rx_dma_buf[];

void UART0_IRQHandler(void)
{
    uint32_t irq = DL_UART_getPendingInterrupt(UART0);

    switch (irq) {
        case DL_UART_IIDX_RX_TIMEOUT_ERROR:
        {
            /* 1. 停止 DMA（冻结传输计数） */
            DL_DMA_disableChannel(DMA, DMA_CH0_RX);

            /* 2. 计算 DMA 已接收字节数 */
            uint16_t rx_len = BSP_UART_RX_BUF_SIZE -
                              DL_DMA_getTransferSize(DMA, DMA_CH0_RX);

            /* 3. 清空 UART 硬件 FIFO 残余数据（追加到 DMA 缓冲尾部） */
            while (!DL_UART_isRXFIFOEmpty(UART0)) {
                if (rx_len < BSP_UART_RX_BUF_SIZE) {
                    s_rx_dma_buf[rx_len++] = (uint8_t)DL_UART_receiveData(UART0);
                } else {
                    (void)DL_UART_receiveData(UART0);
                }
            }

            /* 4. 推入软件 FIFO + 记录帧长 + 自动重启 DMA RX */
            Uart_RX_IRQHandler(rx_len);
            break;
        }

        default:
            break;
    }
}

/* DMA 中断 — TX DMA 完成通知（自动链接下一块 / 停止触发） */
void DMA_IRQHandler(void)
{
    switch (DL_DMA_getPendingInterrupt(DMA)) {
        case DL_DMA_EVENT_IIDX_DMACH1:
            /* TX DMA 完成一块 → 推进 FIFO tail + 链接下一块 */
            Uart_Tx_DMA_Done_IRQHandler();
            break;

        default:
            break;
    }
}

/* GPIO GROUP1 中断 — 右编码器PHA双沿触发 */
void GROUP1_IRQHandler(void)
{
    /* 检查PB14(PHA)是否产生中断
     * 注意: DL_GPIO_getPendingInterrupt 返回 IIDX 枚举(非位掩码)，
     *       与 RIGHT_ENC_PHA_PIN(位掩码)按位与恒为0，导致右编码器中断
     *       永不触发。必须用 getEnabledInterruptStatus 按位掩码判断。 */
    if (DL_GPIO_getEnabledInterruptStatus(RIGHT_ENC_PHA_PORT,
                                          RIGHT_ENC_PHA_PIN)) {
        DL_GPIO_clearInterruptStatus(RIGHT_ENC_PHA_PORT, RIGHT_ENC_PHA_PIN);
        Right_Encoder_IRQHandler();
    }
}

/* ================= 组合逻辑函数（main 上方定义） ================= */

static void System_Init(void)
{
    /* ① RTT 最早初始化，确保后续日志都能输出 */
    SEGGER_RTT_Init();
    SEGGER_RTT_Write(0, "\r\n===== MSPM0G3507 SmartCar Boot =====\r\n", 38);

    /* ② 硬件外设初始化（GPIO/UART/DMA/ADC/I2C/Timer 全部由 SysConfig 生成） */
    SYSCFG_DL_init();

    /* ③ 日志系统初始化（设置默认级别与颜色） */
    my_log_init();

    /* ④ 启动 1ms SysTick 中断（必须在任何 Bsp_Delay_ms 调用前完成） */
    SysTick_Config(CPUCLK_FREQ / 1000);

    /* ⑤ 非循迹模块初始化 */
    App_Led_Init();
    App_Key_Init();
    App_Uart_Init();

    /* ⑥ 循迹任务初始化 */
    Track_Init();

    elog_i("[SYS]", "System initialized - ready");
}

/* ================= 主函数 ================= */

int main(void)
{
    System_Init();

    elog_i("[SYS]", "Waiting for keys (K1=Start K2=Stop K3=WhiteCal K4=BlackCal)");

    /* 循迹小车: 设置3圈，基础速度40 */
    Track_Set_Circles(3);
    Track_Set_Speed(40);

    /* 时标调度变量 */
    uint32_t last_5ms = 0, last_10ms = 0, last_500ms = 0, last_100ms = 0;
    /* 状态变化检测：避免静止状态下重复打印相同状态 */
    uint8_t  last_state = 0xFF;
    uint8_t  last_circle = 0xFF;
    uint8_t  last_bc = 0xFF;

    while (1)
    {
        uint32_t now = systick_ms;

        /* ===================== 循迹任务（自包含，全由 Track_Update 调度） ===================== */
        Track_Update();

        /* ---- 5ms: 速度PID更新（独立于循迹状态机，保证 IDLE/FINISHED 时也能更新）
         * 修复: 原代码速度PID只在 Track_Update 末尾调用，受 5ms 节流+8ms 数据同步
         * 双重约束，且 FINISHED/IDLE 状态下完全不执行 → 电机保持最后PWM。
         * 独立调用确保 target=0 时能自然减速到停。 */
        if ((now - last_5ms) >= 5) {
            last_5ms = now;
            App_Motor_Speed_PID_Update();
        }

        /* ---- 10ms: 按键扫描（无阻塞状态机） ---- */
        if ((now - last_10ms) >= 10) {
            last_10ms = now;
            Key_Scan_Task();
        }

        /* ---- 500ms: 传感器状态日志（降低频率，避免刷屏） ----
         * 仅在状态/圈数/黑点数变化时打印，或在循迹运行中周期打印 */
        if ((now - last_500ms) >= 500) {
            last_500ms = now;
            uint8_t cur_state  = (uint8_t)Track.state;
            uint8_t cur_circle = (uint8_t)Track.current_circle;
            uint8_t cur_bc     = Grayscale_Sensor.black_count;

            bool state_changed = (cur_state != last_state) ||
                                 (cur_circle != last_circle) ||
                                 (cur_bc != last_bc);

            /* 状态变化时必打印；运行中即使无变化也周期打印
             * 修复: FINISHED 状态不再持续打印，避免浪费 RTT 带宽 */
            if (state_changed ||
                (cur_state != TRACK_STATE_IDLE &&
                 cur_state != TRACK_STATE_FINISHED)) {
                elog_i("[CAR]", "St:%d Cir:%d Err:%d L:%d R:%d BC:%d",
                       Track.state, Track.current_circle,
                       (int)(Track.error * 1000),
                       Track.left_speed, Track.right_speed,
                       cur_bc);
                last_state  = cur_state;
                last_circle = cur_circle;
                last_bc     = cur_bc;
            }
        }

        /* ---- 100ms: 按键事件处理 ---- */
        if ((now - last_100ms) >= 100) {
            last_100ms = now;
            bsp_key_event_t evt;
            for (uint8_t i = 0; i < BSP_KEY_NUM; i++) {
                evt = Key_GetEvent(i);
                if (evt == BSP_KEY_EVENT_PUSH) {
                    Led_Toggle(i);
                    elog_i("[KEY]", "K%d pressed", (int)i);
                    /* KEY1: 启动循迹 */
                    if (i == 0) {
                        Track_Start();
                        elog_i("[CTRL]", "Tracking started");
                    }
                    /* KEY2: 停止 */
                    if (i == 1) {
                        Track_Stop();
                        elog_i("[CTRL]", "Tracking stopped");
                    }
                    /* KEY3: 白纸校准 */
                    if (i == 2) {
                        Track_Calibrate_White();
                        elog_i("[SENSOR]", "White calibrated");
                    }
                    /* KEY4: 黑纸校准 */
                    if (i == 3) {
                        Track_Calibrate_Black();
                        elog_i("[SENSOR]", "Black calibrated");
                    }
                }
            }
        }

        /* ---- UART 帧处理（事件驱动，非周期，多帧一次排空） ---- */
        {
            /* 修复: 缓冲区 +1 留给 '\0'，避免 len==BSP_UART_RX_BUF_SIZE 时越界 */
            uint8_t frame[BSP_UART_RX_BUF_SIZE + 1];
            uint16_t len = 0;
            while (Uart_Get_Frame(frame, &len)) {
                if (len >= BSP_UART_RX_BUF_SIZE) len = BSP_UART_RX_BUF_SIZE - 1;
                frame[len] = '\0';
                elog_i("[COMM]", "RX(%u): %s", (unsigned)len, (char*)frame);
            }
        }
    }
}
