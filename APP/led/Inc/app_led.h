/**
 * @file    app_led.h
 * @brief   LED 硬件绑定层声明
 */
#ifndef APP_LED_H
#define APP_LED_H

#include "bsp_led.h"

extern led_t app_leds[BSP_LED_NUM];

void App_LED_System_Init(void);

#endif /* APP_LED_H */
