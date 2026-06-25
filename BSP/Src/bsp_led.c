/**
 * @file    bsp_led.c
 * @brief   LED 核心逻辑实现（BSP — 纯逻辑，跨平台）
 */
#include "bsp_led.h"

/* ================= 1. 设备初始化 ================= */
void Bsp_Led_Init(led_t *led)
{
    /* 初始化状态，具体GPIO配置由APP层完成 */
    (void)led;
}

/* ================= 2. LED 控制 ================= */
void Bsp_Led_On(led_t *led)
{
    if (led == NULL || led->Gpio_Write == NULL) return;
    led->Gpio_Write(led->port, led->pin, 1);
    led->state = 1;
}

void Bsp_Led_Off(led_t *led)
{
    if (led == NULL || led->Gpio_Write == NULL) return;
    led->Gpio_Write(led->port, led->pin, 0);
    led->state = 0;
}
