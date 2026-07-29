/**
 * @file    comm_uart.h
 * @brief   UART通讯层声明（协议解析 + 收发适配）
 */
#ifndef COMM_UART_H
#define COMM_UART_H

#include <stdint.h>

/* ============ 业务接口声明 ============ */
void App_UART_System_Init(void);
void App_UART_Send(const uint8_t *data, uint16_t len);
void App_UART_Task_Run(void);

#endif /* COMM_UART_H */
