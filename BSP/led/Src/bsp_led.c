/**
 * @file    bsp_led.c
 * @brief   LED 核心逻辑实现
 */
#include "bsp_led.h"
#include "bsp_common.h"

led_t bsp_leds[BSP_LED_NUM];

void BSP_Led_Init(led_t *led)
{
    for (uint8_t i = 0; i < BSP_LED_NUM; i++) {
        GPIO_WritePin(led[i].port, led[i].pin, led[i].state);
    }
}

void BSP_Led_On(led_t *led)
{
    GPIO_WritePin(led->port, led->pin, LED_ON);
    led->state = LED_ON;
}

void BSP_Led_Off(led_t *led)
{
    GPIO_WritePin(led->port, led->pin, LED_OFF);
    led->state = LED_OFF;
}
