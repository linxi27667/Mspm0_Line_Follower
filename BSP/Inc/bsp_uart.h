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

typedef struct {
    void (*Init)(void);
    void (*Send)(const uint8_t *data, uint16_t len);
    void (*Rx_Callback)(uint8_t data);
} bsp_uart_t;

void    BSP_UART_Init(bsp_uart_t *uart);
void    BSP_UART_Send(bsp_uart_t *uart, const uint8_t *data, uint16_t len);
bool    BSP_UART_Get_Frame(bsp_uart_t *uart, uint8_t *out_buf, uint16_t *out_len);
void    BSP_UART_RxCallback(bsp_uart_t *uart, uint8_t data);
void    BSP_UART_Timeout_Tick(bsp_uart_t *uart);

#endif /* __BSP_UART_H__ */
