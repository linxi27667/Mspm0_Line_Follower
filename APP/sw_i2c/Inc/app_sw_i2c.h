/**
 * @file    app_sw_i2c.h
 * @brief   软件 I2C 应用层声明
 */
#ifndef APP_SW_I2C_H
#define APP_SW_I2C_H

#include "bsp_sw_i2c.h"

extern bsp_sw_i2c_t App_I2C_Bus_1;

void App_I2C_System_Init(void);

#endif /* APP_SW_I2C_H */
