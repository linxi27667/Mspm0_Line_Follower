/**
 * @file    comm_vision_uart.h
 * @brief   视觉通信串口声明 (UART1: PB4=TX, PB5=RX)
 *          与视觉模块(OpenMV/K210等)全时双工通信，避免与步进电机共用UART0
 */
#ifndef COMM_VISION_UART_H
#define COMM_VISION_UART_H

#include <stdbool.h>
#include <stdint.h>

/* ============ 视觉 UART 硬件配置 ============ */
/* PB4 → IOMUX_PINCM17 → UART1_TX */
/* PB5 → IOMUX_PINCM18 → UART1_RX */
#define VISION_UART_INST            UART1
#define VISION_UART_TX_IOMUX        IOMUX_PINCM17
#define VISION_UART_TX_IOMUX_FUNC   IOMUX_PINCM17_PF_UART1_TX
#define VISION_UART_RX_IOMUX        IOMUX_PINCM18
#define VISION_UART_RX_IOMUX_FUNC   IOMUX_PINCM18_PF_UART1_RX
#define VISION_UART_BAUDRATE        115200
#define VISION_UART_RX_RING_SIZE    (1024u)
#define VISION_UART_TX_RING_SIZE    (256u)

/* ============ 业务接口声明 ============ */

void App_Vision_UART_Init(void);
void App_Vision_UART_Send(const uint8_t *data, uint16_t len);
bool App_Vision_UART_Try_Send(const uint8_t *data, uint16_t len);
uint16_t App_Vision_UART_Read(uint8_t *data, uint16_t capacity);
void App_Vision_UART_Service(void);
void App_Vision_UART_Task(void);
uint32_t App_Vision_UART_Get_Rx_Dropped(void);
uint32_t App_Vision_UART_Get_Tx_Rejected(void);

#endif /* COMM_VISION_UART_H */
