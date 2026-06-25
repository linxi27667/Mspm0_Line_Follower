/**
 * @file    bsp_common.c
 * @brief   BSP 公共基础设施实现
 */
#include "bsp_common.h"
#include <ti/devices/msp/msp.h>

/* 全局时标 — 唯一定义点（从 main.c 迁入） */
volatile uint32_t systick_ms = 0;

void Bsp_Delay_ms(uint32_t ms)
{
    uint32_t start = systick_ms;
    while ((systick_ms - start) < ms) {}
}

void Bsp_Delay_us(uint32_t us)
{
    /* MSPM0G3507 忙等近似延时，需根据 CPUCLK_FREQ 调整 */
    volatile uint32_t count = us * 8;
    while (count--) {
        __NOP();
    }
}

uint32_t Bsp_GetTick(void)
{
    return systick_ms;
}
