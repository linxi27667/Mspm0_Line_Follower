/**
 * @file    bsp_common.c
 * @brief   SysTick 延时实现（MSPM0G3507，32MHz）
 */
#include "bsp_common.h"

void BSP_Delay_ms(uint32_t ms)
{
    uint32_t start = systick_ms;
    while ((systick_ms - start) < ms) { }
}

void BSP_Delay_us(uint32_t us)
{
    /* 32MHz → 每微秒 32 个周期，while 约 4 周期/迭代 */
    uint32_t ticks = us * 8;
    while (ticks--) {
        __asm("nop");
    }
}

uint32_t BSP_GetTick(void)
{
    return systick_ms;
}
