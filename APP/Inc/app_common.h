/**
 * @file    app_common.h
 * @brief   APP层公共基础设施 — 硬件抽象 + 电平约定
 * @note    APP层是唯一可包含硬件头文件的层
 */
#ifndef APP_COMMON_H
#define APP_COMMON_H

#include <ti/devices/msp/msp.h>
#include <ti/driverlib/driverlib.h>
#include "bsp_common.h"

/* ============================================================
 * GPIO 端口类型别名
 * ============================================================ */
typedef GPIO_Regs *gpio_port_t;
typedef uint32_t    gpio_pin_t;

/* ============================================================
 * GPIO 读写抽象（MSPM0 DriverLib 映射）
 * ============================================================ */
#define GPIO_SetBits(port, pins)       DL_GPIO_setPins((port), (pins))
#define GPIO_ClearBits(port, pins)     DL_GPIO_clearPins((port), (pins))
#define GPIO_ToggleBits(port, pins)    DL_GPIO_togglePins((port), (pins))
#define GPIO_ReadPin(port, pin)        ((DL_GPIO_readPins((port), (pin)) != 0) ? 1 : 0)
#define GPIO_WritePin(port, pin, lvl)  do { \
    if (lvl) DL_GPIO_setPins((port), (pin)); \
    else     DL_GPIO_clearPins((port), (pin)); \
} while (0)

/* ============================================================
 * 电平约定
 * ============================================================ */
// 低电平点亮 LED
#define LED_ON      0
#define LED_OFF     1

#endif /* APP_COMMON_H */
