/**
 * @file    bsp_sw_i2c.h
 * @brief   软件 I2C 总线抽象层（BSP — 纯逻辑，跨平台）
 */
#ifndef __BSP_SW_I2C_H__
#define __BSP_SW_I2C_H__

#include <stdint.h>
#include <stddef.h>

typedef struct {
    void     *port;
    uint32_t  pin;
} bsp_i2c_gpio_t;

typedef struct {
    bsp_i2c_gpio_t scl;
    bsp_i2c_gpio_t sda;

    void    (*Init)(void);
    void    (*Pin_Write)(void *port, uint32_t pin, uint8_t level);
    uint8_t (*Pin_Read)(void *port, uint32_t pin);
    void    (*Delay_us)(uint32_t us);
} bsp_sw_i2c_t;

void    BSP_I2C_Init_Device(bsp_sw_i2c_t *bus);
uint8_t BSP_I2C_Write_Reg(bsp_sw_i2c_t *bus, uint8_t dev_addr, uint8_t reg_addr, const uint8_t *data, uint16_t len);
uint8_t BSP_I2C_Read_Reg(bsp_sw_i2c_t *bus, uint8_t dev_addr, uint8_t reg_addr, uint8_t *data, uint16_t len);

#endif /* __BSP_SW_I2C_H__ */
