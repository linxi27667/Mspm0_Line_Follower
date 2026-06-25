/**
 * @file    app_uart.h
 * @brief   UART 应用层声明（DMA TX 零拷贝 + DMA RX + IDLE/Timeout + FIFO）
 *          对接 bsp_uart_t 通用驱动，绑定 MSPM0G3507 UART0 + DMA CH0/CH1
 */
#ifndef APP_UART_H
#define APP_UART_H

#include "bsp_uart.h"

/* ============ DMA 通道分配（与 SysConfig 一致） ============ */
#define DMA_CH0_RX  0   /* UART0 RX → DMA CH0 */
#define DMA_CH1_TX  1   /* UART0 TX ← DMA CH1 */

/* ============ 业务接口声明 ============ */
extern bsp_uart_t Uart_Dev;
extern uint8_t    s_rx_dma_buf[];   /* DMA RX 暂存，main.c ISR 访问 */

/* 初始化（在 main 中调用一次） */
void App_Uart_Init(void);

/* ---- TX ---- */
/* 非阻塞发送（FIFO 满则丢字节，查 Uart_Dev.tx_overflow） */
void Uart_Send(const uint8_t *data, uint16_t len);
/* 阻塞发送（等待 FIFO 有空间，不丢数据） */
void Uart_Send_Block(const uint8_t *data, uint16_t len);
/* 阻塞发送字符串 */
void Uart_SendString(const char *s);
/* 阻塞等待全部发送完成 */
void Uart_Flush(void);
/* 待发送字节数 */
uint16_t Uart_TxPending(void);

/* ---- RX ---- */
/* 弹出一帧（返回 false 表示无完整帧） */
bool Uart_Get_Frame(uint8_t *out_buf, uint16_t *out_len);
/* 可读字节数 */
uint16_t Uart_Available(void);
/* 弹出一个字节 */
bool Uart_ReadByte(uint8_t *out_byte);
/* 待处理帧数 */
uint16_t Uart_Frame_Count(void);

/* ---- 中断回调（main.c ISR 中调用） ---- */
void Uart_Tx_DMA_Done_IRQHandler(void);   /* DMA CH1 完成 */
void Uart_RX_IRQHandler(uint16_t rx_len); /* UART0 IDLE/Timeout，已收 rx_len 字节 */

#endif /* APP_UART_H */
