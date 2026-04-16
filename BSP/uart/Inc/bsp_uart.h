/**
 * @file    bsp_uart.h
 * @brief   UART 抽象驱动层（BSP — 纯逻辑，硬件无关）
 */
#ifndef __BSP_UART_H__
#define __BSP_UART_H__

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#define BSP_UART_RX_BUF_SIZE 256

typedef struct {
    uint8_t  data[BSP_UART_RX_BUF_SIZE];
    uint16_t len;
} bsp_uart_rx_msg_t;

void    BSP_UART_Init(void);
void    BSP_UART_Send(const uint8_t *data, uint16_t len);
bool    BSP_UART_Get_Frame(uint8_t *out_buf, uint16_t *out_len);
void    BSP_UART_RxCallback(uint8_t data);
void    BSP_UART_Timeout_Tick(void);

#endif /* __BSP_UART_H__ */
