/**
 * @file    bsp_common.h
 * @brief   BSP 公共基础设施 — 纯逻辑，零硬件依赖
 * @note    所有 BSP 模块共享的基础设施
 *          严禁包含任何硬件头文件
 */
#ifndef __BSP_COMMON_H__
#define __BSP_COMMON_H__

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

/* ============================================================
 * 全局时标（定义在 bsp_common.c，由 SysTick_Handler 递增）
 * ============================================================ */
extern volatile uint32_t systick_ms;

/* ============================================================
 * 延时服务（基于 systick_ms，纯软件实现）
 * ============================================================ */
void Bsp_Delay_ms(uint32_t ms);
void Bsp_Delay_us(uint32_t us);
uint32_t Bsp_GetTick(void);

#endif /* __BSP_COMMON_H__ */
