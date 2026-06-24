/**
 * @file    app_key.h
 * @brief   按键应用层声明（硬件绑定 + 业务逻辑入口）
 */
#ifndef APP_KEY_H
#define APP_KEY_H

#include "bsp_key.h"

/* ============ 按键硬件配置 ============ */
#define KEY1_PORT       GPIOB
#define KEY1_PIN        DL_GPIO_PIN_0
#define KEY2_PORT       GPIOB
#define KEY2_PIN        DL_GPIO_PIN_1
#define KEY3_PORT       GPIOB
#define KEY3_PIN        DL_GPIO_PIN_2
#define KEY4_PORT       GPIOA
#define KEY4_PIN        DL_GPIO_PIN_0

/* ============ 业务接口声明 ============ */
extern bsp_key_t app_keys[BSP_KEY_NUM];

void App_Key_System_Init(void);
void App_Key_Scan_Task(void);
bsp_key_event_t App_Key_GetEvent(uint8_t index);

#endif /* APP_KEY_H */
