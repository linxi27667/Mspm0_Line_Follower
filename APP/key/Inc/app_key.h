/**
 * @file    app_key.h
 * @brief   按键应用层声明
 */
#ifndef APP_KEY_H
#define APP_KEY_H

#include "bsp_key.h"

void App_Key_System_Init(void);
void App_Key_Scan_Task(void);

#endif /* APP_KEY_H */
