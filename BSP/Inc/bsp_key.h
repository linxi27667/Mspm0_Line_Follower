/**
 * @file    bsp_key.h
 * @brief   按键抽象驱动层（BSP — 纯逻辑，硬件无关）
 */
#ifndef __BSP_KEY_H__
#define __BSP_KEY_H__

#include <stdint.h>
#include <stddef.h>

#define BSP_KEY_NUM               4
#define BSP_KEY_LONGPUSH_MIN_TIME 80   /* 长按判定周期数 (ms) */
#define BSP_KEY_DOUBLE_TIMEOUT    15   /* 双击判定窗口 (ms) */

typedef enum {
    BSP_KEY_JUDGE_IDLE = 0,
    BSP_KEY_JUDGE_PRESS,
    BSP_KEY_JUDGE_LONGPUSH,
    BSP_KEY_JUDGE_DOUBLECLICK,
    BSP_KEY_JUDGE_RELEASE
} bsp_key_judge_t;

typedef enum {
    BSP_KEY_EVENT_IDLE = 0,
    BSP_KEY_EVENT_PUSH,
    BSP_KEY_EVENT_LONGPUSH,
    BSP_KEY_EVENT_DOUBLECLICK
} bsp_key_event_t;

typedef struct {
    bsp_key_judge_t judge;
    uint8_t  state;
    void    *port;
    uint32_t pin;
    volatile uint8_t f_push;
    volatile uint8_t f_longpush;
    volatile uint8_t f_doubleclick;
    uint8_t  debounce_cnt;
    uint32_t longpush_time;
    uint32_t doubleclick_time;
} bsp_key_t;

void BSP_Key_Init(bsp_key_t *keys, uint8_t num);
void BSP_Key_Scan(bsp_key_t *keys, uint8_t num);
void BSP_Key_EasyScan(bsp_key_t *keys, uint8_t num);
bsp_key_event_t BSP_Key_GetEvent(bsp_key_t *key);

#endif /* __BSP_KEY_H__ */
