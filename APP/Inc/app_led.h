/**
 * @file    app_led.h
 * @brief   LED应用层声明（硬件绑定 + 业务逻辑入口）
 */
#ifndef APP_LED_H
#define APP_LED_H

#include "bsp_led.h"
#include "ti_msp_dl_config.h"

/* ============ LED硬件配置（由SysConfig生成） ============ */
#define LED1_PORT       Led_Group_PORT
#define LED1_PIN        Led_Group_LED1_PIN
#define LED2_PORT       Led_Group_PORT
#define LED2_PIN        Led_Group_LED2_PIN
#define LED3_PORT       Led_Group_PORT
#define LED3_PIN        Led_Group_LED3_PIN
#define LED4_PORT       Led_Group_PORT
#define LED4_PIN        Led_Group_LED4_PIN

/* ============ 业务接口声明 ============ */
extern led_t Led_Devices[BSP_LED_NUM];

void App_Led_Init(void);
void Led_On(uint8_t index);
void Led_Off(uint8_t index);
void Led_Toggle(uint8_t index);

#endif /* APP_LED_H */
