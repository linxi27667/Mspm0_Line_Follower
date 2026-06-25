/**
 * @file    app_key.h
 * @brief   按键应用层声明（硬件绑定 + 业务逻辑入口）
 */
#ifndef APP_KEY_H
#define APP_KEY_H

#include "bsp_key.h"
#include "ti_msp_dl_config.h"

/* ============ 按键硬件配置（由SysConfig生成） ============ */
#define KEY1_PORT       Key_Group_PORT
#define KEY1_PIN        Key_Group_KEY1_PIN
#define KEY2_PORT       Key_Group_PORT
#define KEY2_PIN        Key_Group_KEY2_PIN
#define KEY3_PORT       Key_Group_PORT
#define KEY3_PIN        Key_Group_KEY3_PIN
#define KEY4_PORT       Key_PA30_PORT
#define KEY4_PIN        Key_PA30_KEY4_PIN

/* ============ 业务接口声明 ============ */
extern bsp_key_t Key_Devices[BSP_KEY_NUM];

void App_Key_Init(void);
void Key_Scan_Task(void);
bsp_key_event_t Key_GetEvent(uint8_t index);

#endif /* APP_KEY_H */
