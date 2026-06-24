/**
 * @file    app_led.h
 * @brief   LED应用层声明（硬件绑定 + 业务逻辑入口）
 */
#ifndef APP_LED_H
#define APP_LED_H

#include "bsp_led.h"

/* ============ LED硬件配置 ============ */
#define LED1_PORT       GPIOB
#define LED1_PIN        DL_GPIO_PIN_22
#define LED2_PORT       GPIOB
#define LED2_PIN        DL_GPIO_PIN_21
#define LED3_PORT       GPIOB
#define LED3_PIN        DL_GPIO_PIN_27
#define LED4_PORT       GPIOB
#define LED4_PIN        DL_GPIO_PIN_16

/* ============ 业务接口声明 ============ */
extern led_t app_leds[BSP_LED_NUM];

void App_LED_System_Init(void);
void App_LED_On(uint8_t index);
void App_LED_Off(uint8_t index);
void App_LED_Toggle(uint8_t index);

#endif /* APP_LED_H */
