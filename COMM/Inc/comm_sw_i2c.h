/**
 * @file    comm_sw_i2c.h
 * @brief   软件I2C通讯层声明（协议解析 + 收发适配）
 */
#ifndef COMM_SW_I2C_H
#define COMM_SW_I2C_H

#include "bsp_sw_i2c.h"

/* ============ I2C总线1硬件配置 ============ */
#define I2C_BUS1_SCL_PORT          GPIOB
#define I2C_BUS1_SCL_PIN           DL_GPIO_PIN_8
#define I2C_BUS1_SDA_PORT          GPIOB
#define I2C_BUS1_SDA_PIN           DL_GPIO_PIN_9

/* ============ 业务接口声明 ============ */
extern bsp_sw_i2c_t App_I2C_Bus_1;

void App_I2C_System_Init(void);

#endif /* COMM_SW_I2C_H */
