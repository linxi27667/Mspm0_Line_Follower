/**
 * @file    bsp_common.h
 * @brief   MSPM0 BSP 公共工具定义
 * @note    所有 BSP 模块共享的基础设施
 */
#ifndef __BSP_COMMON_H__
#define __BSP_COMMON_H__

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <ti/devices/msp/msp.h>
#include <ti/driverlib/driverlib.h>

/* ============================================================
 * MSPM0 驱动层 API 映射宏（统一 STM32 → MSPM0 调用习惯）
 * ============================================================ */

/* GPIO 读写抽象 */
#define GPIO_SetBits(port, pins)       DL_GPIO_setPins((port), (pins))
#define GPIO_ClearBits(port, pins)     DL_GPIO_clearPins((port), (pins))
#define GPIO_ToggleBits(port, pins)    DL_GPIO_togglePins((port), (pins))
#define GPIO_ReadPin(port, pin)        ((DL_GPIO_readPins((port), (pin)) != 0) ? 1 : 0)
#define GPIO_WritePin(port, pin, lvl)  do { \
    if (lvl) DL_GPIO_setPins((port), (pin)); \
    else     DL_GPIO_clearPins((port), (pin)); \
} while (0)

/* 电平约定（低电平点亮 LED） */
#define LED_ON      0
#define LED_OFF     1

/* 按键约定（上拉输入，按下为低） */
#define KEY_PRESS   0
#define KEY_RELEASE 1

/* ============================================================
 * SysTick 延时服务
 * ============================================================ */

extern volatile uint32_t systick_ms;  /* 定义在 main.c，由 SysTick_Handler 递增 */

void BSP_Delay_ms(uint32_t ms);
void BSP_Delay_us(uint32_t us);
uint32_t BSP_GetTick(void);

/* ============================================================
 * GPIO 端口类型别名
 * ============================================================ */

typedef GPIO_Regs * gpio_port_t;
typedef uint32_t     gpio_pin_t;

#endif /* __BSP_COMMON_H__ */
