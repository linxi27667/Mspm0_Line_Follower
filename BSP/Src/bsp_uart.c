/**
 * @file    bsp_uart.c
 * @brief   UART 核心逻辑实现（BSP — 纯逻辑，跨平台）
 */
#include "bsp_uart.h"

/* ================= 1. 核心初始化 ================= */
void BSP_UART_Init(bsp_uart_t *uart)
{
    if (uart == NULL || uart->Init == NULL) return;
    uart->Init();
}

/* ================= 2. 发送接口 ================= */
void BSP_UART_Send(bsp_uart_t *uart, const uint8_t *data, uint16_t len)
{
    if (uart == NULL || uart->Send == NULL) return;
    uart->Send(data, len);
}

/* ================= 3. 接收钩子函数 ================= */
void BSP_UART_RxCallback(bsp_uart_t *uart, uint8_t data)
{
    if (uart && uart->Rx_Callback) {
        uart->Rx_Callback(data);
    }
}

/* ================= 4. 超时判定 ================= */
void BSP_UART_Timeout_Tick(bsp_uart_t *uart)
{
    /* 超时判定逻辑由APP层实现 */
    (void)uart;
}

/* ================= 5. APP 拉取接口 ================= */
bool BSP_UART_Get_Frame(bsp_uart_t *uart, uint8_t *out_buf, uint16_t *out_len)
{
    /* 帧获取逻辑由APP层实现 */
    (void)uart;
    (void)out_buf;
    (void)out_len;
    return false;
}
