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

/* ================= 全局时标 ================= */

volatile uint32_t systick_ms = 0;  /* 唯一时标源，供 bsp_common.c 使用 */

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
            App_UART_RX_IRQHandler(rx_len);
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
            App_UART_Tx_DMA_Done_IRQHandler();
            break;

        default:
            break;
    }
}

/* ================= 组合逻辑函数（main 上方定义） ================= */

static void System_Init(void)
{
    SYSCFG_DL_init();
    my_log_init();

    /* 配置 SysTick 为 1ms 中断 */
    SysTick_Config(CPUCLK_FREQ / 1000);

    /* 非循迹模块初始化（按键/LED/UART 仍走 APP 层） */
    App_LED_System_Init();
    App_Key_System_Init();
    App_UART_System_Init();

    /* 循迹任务初始化（自包含：灰度+电机+陀螺仪 全部在 TASK 层直驱） */
    Track_Init();
}

/* ================= 主函数 ================= */

int main(void)
{
    System_Init();

    elog_i("SYS", "System ready - waiting for keys");

    /* 循迹小车: 设置3圈，基础速度40 */
    Track_Set_Circles(3);
    Track_Set_Speed(40);

    /* 时标调度变量 */
    uint32_t last_10ms = 0, last_50ms = 0, last_100ms = 0;

    while (1)
    {
        uint32_t now = systick_ms;

        /* ===================== 循迹任务（自包含，全由 Track_Update 调度） ===================== */
        /* 内部完成: 灰度扫描 → 陀螺仪读取 → 偏差计算 → PID → 电机输出 */
        Track_Update();

        /* ===================== 时标轮询任务（非循迹） ===================== */

        /* ---- 10ms: 按键扫描（无阻塞状态机） ---- */
        if ((now - last_10ms) >= 10) {
            last_10ms = now;
            App_Key_Scan_Task();
        }

        /* ---- 50ms: 日志输出 ---- */
        if ((now - last_50ms) >= 50) {
            last_50ms = now;
            elog_i("TRACK", "St:%d Cir:%d Err:%.1f L:%d R:%d BC:%d",
                   Track.state, Track.current_circle,
                   Track.error, Track.left_speed, Track.right_speed,
                   Track_Gray.black_count);
        }

        /* ---- 100ms: 按键事件处理 ---- */
        if ((now - last_100ms) >= 100) {
            last_100ms = now;
            bsp_key_event_t evt;
            for (uint8_t i = 0; i < BSP_KEY_NUM; i++) {
                evt = App_Key_GetEvent(i);
                if (evt == BSP_KEY_EVENT_PUSH) {
                    App_LED_Toggle(i);
                    elog_i("KEY", "Key%u pressed", i);
                    /* KEY1: 启动循迹 */
                    if (i == 0) {
                        Track_Start();
                        elog_i("TRACK", "Tracking started!");
                    }
                    /* KEY2: 停止 */
                    if (i == 1) {
                        Track_Stop();
                        elog_i("TRACK", "Tracking stopped!");
                    }
                    /* KEY3: 白纸校准 */
                    if (i == 2) {
                        Track_Calibrate_White();
                        elog_i("TRACK", "White calibrated");
                    }
                    /* KEY4: 黑纸校准 */
                    if (i == 3) {
                        Track_Calibrate_Black();
                        elog_i("TRACK", "Black calibrated");
                    }
                }
            }
        }

        /* ---- UART 帧处理（事件驱动，非周期，多帧一次排空） ---- */
        {
            uint8_t frame[BSP_UART_RX_BUF_SIZE];
            uint16_t len = 0;
            while (App_UART_Get_Frame(frame, &len)) {
                frame[len] = '\0';
                elog_i("UART", "RX(%u): %s", len, frame);
            }
        }
    }
}
