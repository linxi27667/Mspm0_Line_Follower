/**
 * @file    app_uart.c
 * @brief   UART 应用层业务逻辑
 */
#include "app_uart.h"
#include "bsp_uart.h"
#include "bsp_common.h"

void App_UART_System_Init(void)
{
    BSP_UART_Init();
}

void App_UART_Task_Run(void)
{
    uint8_t frame_buf[256];
    uint16_t frame_len = 0;

    if (BSP_UART_Get_Frame(frame_buf, &frame_len)) {
        frame_buf[frame_len] = '\0';
        /* 在此编写业务判断逻辑 */
    }
}
