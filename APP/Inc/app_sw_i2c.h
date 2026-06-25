/**
 * @file    app_sw_i2c.h
 * @brief   软件I2C应用层声明（硬件绑定 + 业务逻辑入口）
 */
#ifndef APP_SW_I2C_H
#define APP_SW_I2C_H

#include "bsp_sw_i2c.h"

/* ============ I2C总线1硬件配置 ============ */
#define I2C_BUS1_SCL_PORT          GPIOB
#define I2C_BUS1_SCL_PIN           DL_GPIO_PIN_8
#define I2C_BUS1_SDA_PORT          GPIOB
#define I2C_BUS1_SDA_PIN           DL_GPIO_PIN_9

/* ============ 业务接口声明 ============ */
extern bsp_sw_i2c_t I2C_Bus_1;

void App_I2C_Init(void);

#endif /* APP_SW_I2C_H */
