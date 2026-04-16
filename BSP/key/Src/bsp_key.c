/**
 * @file    bsp_key.c
 * @brief   按键扫描状态机实现
 */
#include "bsp_key.h"
#include "bsp_common.h"

bsp_key_t bsp_keys[BSP_KEY_NUM];

void BSP_Key_Init(void)
{
    for (uint8_t i = 0; i < BSP_KEY_NUM; i++) {
        bsp_keys[i].judge = BSP_KEY_JUDGE_IDLE;
        bsp_keys[i].state = KEY_RELEASE;
        bsp_keys[i].f_push = 0;
        bsp_keys[i].f_longpush = 0;
        bsp_keys[i].f_doubleclick = 0;
        bsp_keys[i].longpush_time = 0;
        bsp_keys[i].doubleclick_time = 0;
    }
}

void BSP_Key_Scan(bsp_key_t *key)
{
    for (uint8_t i = 0; i < BSP_KEY_NUM; i++) {
        key[i].state = GPIO_ReadPin(key[i].port, key[i].pin);

        switch (key[i].judge) {
        case BSP_KEY_JUDGE_IDLE:
            if (key[i].state == KEY_PRESS) {
                key[i].judge = BSP_KEY_JUDGE_PRESS;
            }
            break;

        case BSP_KEY_JUDGE_PRESS:
            if (key[i].state == KEY_PRESS) {
                key[i].judge = BSP_KEY_JUDGE_LONGPUSH;
                key[i].longpush_time = 0;
            } else {
                key[i].judge = BSP_KEY_JUDGE_IDLE;
            }
            break;

        case BSP_KEY_JUDGE_LONGPUSH:
            if (key[i].state == KEY_PRESS) {
                key[i].longpush_time++;
                if (key[i].longpush_time >= BSP_KEY_LONGPUSH_MIN_TIME) {
                    key[i].longpush_time = 0;
                    key[i].judge = BSP_KEY_JUDGE_RELEASE;
                    key[i].f_longpush = BSP_KEY_EVENT_LONGPUSH;
                }
            } else {
                key[i].longpush_time = 0;
                key[i].doubleclick_time = 0;
                key[i].judge = BSP_KEY_JUDGE_DOUBLECLICK;
            }
            break;

        case BSP_KEY_JUDGE_DOUBLECLICK:
            key[i].doubleclick_time++;
            if (key[i].state == KEY_PRESS && key[i].doubleclick_time <= BSP_KEY_DOUBLE_TIMEOUT) {
                key[i].judge = BSP_KEY_JUDGE_RELEASE;
                key[i].doubleclick_time = 0;
                key[i].f_doubleclick = BSP_KEY_EVENT_DOUBLECLICK;
            } else if (key[i].state == KEY_RELEASE && key[i].doubleclick_time > BSP_KEY_DOUBLE_TIMEOUT) {
                key[i].judge = BSP_KEY_JUDGE_IDLE;
                key[i].doubleclick_time = 0;
                key[i].f_push = BSP_KEY_EVENT_PUSH;
            }
            break;

        case BSP_KEY_JUDGE_RELEASE:
            if (key[i].state == KEY_RELEASE) {
                key[i].judge = BSP_KEY_JUDGE_IDLE;
            }
            break;
        }
    }
}

void BSP_Key_EasyScan(bsp_key_t *key)
{
    for (uint8_t i = 0; i < BSP_KEY_NUM; i++) {
        key[i].state = GPIO_ReadPin(key[i].port, key[i].pin);
    }

    for (uint8_t i = 0; i < BSP_KEY_NUM; i++) {
        switch (key[i].judge) {
        case BSP_KEY_JUDGE_IDLE:
            if (key[i].state == KEY_PRESS) key[i].judge = BSP_KEY_JUDGE_PRESS;
            break;
        case BSP_KEY_JUDGE_PRESS:
            if (key[i].state == KEY_PRESS) key[i].judge = BSP_KEY_JUDGE_LONGPUSH;
            else key[i].judge = BSP_KEY_JUDGE_IDLE;
            break;
        case BSP_KEY_JUDGE_LONGPUSH:
            if (key[i].state == KEY_RELEASE) {
                key[i].f_push = 1;
                key[i].judge = BSP_KEY_JUDGE_IDLE;
            }
            break;
        default:
            key[i].judge = BSP_KEY_JUDGE_IDLE;
            break;
        }
    }
}

bsp_key_event_t BSP_Key_GetEvent(bsp_key_t *key)
{
    if (key->f_push)       { key->f_push = 0; return BSP_KEY_EVENT_PUSH; }
    if (key->f_longpush)   { key->f_longpush = 0; return BSP_KEY_EVENT_LONGPUSH; }
    if (key->f_doubleclick){ key->f_doubleclick = 0; return BSP_KEY_EVENT_DOUBLECLICK; }
    return BSP_KEY_EVENT_IDLE;
}
