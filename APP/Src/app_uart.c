/**
 * @file    app_uart.c
 * @brief   UART 应用层 — MSPM0G3507 硬件绑定层
 * @note    基础外设由 SysConfig 生成（ti_msp_dl_config.c），此处仅补充：
 *          - DMA 缓冲区地址 / 传输长度 / 通道使能
 *          - HW 钩子实现：Init / StartTxChunk / StopTx / RestartRx
 *
 *          RX: DMA CH0 单次传输 → s_rx_dma_buf
 *              UART0 RX Timeout（≈IDLE）中断 → Bsp_UART_Rx_OnFrame → 字节FIFO + 帧长队列
 *          TX: 字节FIFO → DMA CH1 零拷贝（DMA 直接读 FIFO）→ 完成中断链接下一块
 */
#include "app_uart.h"
#include "bsp_uart.h"
#include "ti_msp_dl_config.h"
#include "app_common.h"

/* ================= 1. 缓冲区定义 ================= */

/* DMA 接收暂存（非 static，供 main.c ISR 访问） */
uint8_t s_rx_dma_buf[BSP_UART_RX_BUF_SIZE];

/* RX 软件 FIFO（环形） */
static uint8_t s_rx_fifo_buf[BSP_UART_RX_FIFO_SIZE];

/* TX 软件 FIFO（环形）—— DMA 直接从此处读取，零拷贝 */
static uint8_t s_tx_fifo_buf[BSP_UART_TX_FIFO_SIZE];

/* ================= 2. HW 钩子实现 ================= */

/* ---- 初始化：配置 DMA CH0 RX 并启动接收 ---- */
static void HW_UART_Init(void)
{
    /* SysConfig 已完成 UART0 GPIO/波特率/FIFO/RX Timeout/DMA 通道配置
     * 此处仅补充 DMA 缓冲区地址、传输长度，并启动 DMA 接收 */

    DL_DMA_setSrcAddr(DMA, DMA_CH0_RX, (uint32_t)&UART0->RXDATA);
    DL_DMA_setDestAddr(DMA, DMA_CH0_RX, (uint32_t)s_rx_dma_buf);
    DL_DMA_setTransferSize(DMA, DMA_CH0_RX, BSP_UART_RX_BUF_SIZE);
    DL_DMA_enableChannel(DMA, DMA_CH0_RX);
}

/* ---- 重启 DMA RX（帧捕获后调用） ---- */
static void HW_UART_RestartRx(void)
{
    DL_DMA_setDestAddr(DMA, DMA_CH0_RX, (uint32_t)s_rx_dma_buf);
    DL_DMA_setTransferSize(DMA, DMA_CH0_RX, BSP_UART_RX_BUF_SIZE);
    DL_DMA_enableChannel(DMA, DMA_CH0_RX);
}

/* ---- 启动一段 DMA TX（src 指向 TX FIFO 内部，零拷贝） ---- */
static void HW_UART_StartTxChunk(const uint8_t *src, uint16_t len)
{
    if (len == 0) return;

    DL_DMA_setSrcAddr(DMA, DMA_CH1_TX, (uint32_t)src);
    DL_DMA_setDestAddr(DMA, DMA_CH1_TX, (uint32_t)&UART0->TXDATA);
    DL_DMA_setTransferSize(DMA, DMA_CH1_TX, len);

    /* 使能 UART TX DMA 事件 → 触发 DMA 传输 */
    DL_UART_enableDMATransmitEvent(UART0);
    DL_DMA_enableChannel(DMA, DMA_CH1_TX);
}

/* ---- 停止 UART TX DMA 触发（FIFO 排空时） ---- */
static void HW_UART_StopTx(void)
{
    DL_UART_disableDMATransmitEvent(UART0);
}

/* ================= 3. 对象实例化 ================= */

bsp_uart_t Uart_Dev = {
    .Init         = HW_UART_Init,
    .StartTxChunk = HW_UART_StartTxChunk,
    .StopTx       = HW_UART_StopTx,
    .RestartRx    = HW_UART_RestartRx,

    .rx_fifo_buf  = s_rx_fifo_buf,
    .rx_fifo_size = BSP_UART_RX_FIFO_SIZE,
    .rx_fifo_head = 0,
    .rx_fifo_tail = 0,

    .rx_frame_head = 0,
    .rx_frame_tail = 0,

    .tx_fifo_buf  = s_tx_fifo_buf,
    .tx_fifo_size = BSP_UART_TX_FIFO_SIZE,
    .tx_fifo_head = 0,
    .tx_fifo_tail = 0,
    .tx_chunk_len = 0,
    .tx_busy      = false,

    .tx_overflow       = false,
    .rx_overflow       = false,
    .rx_frame_overflow = false,
};

/* ================= 4. 对外业务切入点 ================= */

void App_Uart_Init(void)
{
    Bsp_UART_Init(&Uart_Dev);
}

/* ---- TX 封装 ---- */
void Uart_Send(const uint8_t *data, uint16_t len)
{
    Bsp_UART_Send(&Uart_Dev, data, len);
}

void Uart_Send_Block(const uint8_t *data, uint16_t len)
{
    Bsp_UART_Send_Block(&Uart_Dev, data, len);
}

void Uart_SendString(const char *s)
{
    Bsp_UART_SendString(&Uart_Dev, s);
}

void Uart_Flush(void)
{
    Bsp_UART_Flush(&Uart_Dev);
}

uint16_t Uart_TxPending(void)
{
    return Bsp_UART_TxPending(&Uart_Dev);
}

/* ---- RX 封装 ---- */
bool Uart_Get_Frame(uint8_t *out_buf, uint16_t *out_len)
{
    return Bsp_UART_Get_Frame(&Uart_Dev, out_buf, out_len);
}

uint16_t Uart_Available(void)
{
    return Bsp_UART_Available(&Uart_Dev);
}

bool Uart_ReadByte(uint8_t *out_byte)
{
    return Bsp_UART_ReadByte(&Uart_Dev, out_byte);
}

uint16_t Uart_Frame_Count(void)
{
    return Bsp_UART_Frame_Count(&Uart_Dev);
}

/* ================= 5. 中断回调（main.c ISR 调用） ================= */

/* DMA CH1 完成 —— TX 一块发完 */
void Uart_Tx_DMA_Done_IRQHandler(void)
{
    Bsp_UART_Tx_OnDMAComplete(&Uart_Dev);
}

/* UART0 IDLE/Timeout —— 已收 rx_len 字节（main.c 已停 DMA、读计数、排空 FIFO） */
void Uart_RX_IRQHandler(uint16_t rx_len)
{
    Bsp_UART_Rx_OnFrame(&Uart_Dev, s_rx_dma_buf, rx_len);
}
