/**
 * @file    bsp_key.c
 * @brief   按键扫描状态机实现
 */
#include "bsp_key.h"
#include "bsp_common.h"

void BSP_Key_Init(bsp_key_t *keys, uint8_t num)
{
    for (uint8_t i = 0; i < num; i++) {
        keys[i].judge = BSP_KEY_JUDGE_IDLE;
        keys[i].state = KEY_RELEASE;
        keys[i].f_push = 0;
        keys[i].f_longpush = 0;
        keys[i].f_doubleclick = 0;
        keys[i].longpush_time = 0;
        keys[i].doubleclick_time = 0;
    }
}

void BSP_Key_Scan(bsp_key_t *keys, uint8_t num)
{
    for (uint8_t i = 0; i < num; i++) {
        keys[i].state = GPIO_ReadPin(keys[i].port, keys[i].pin);

        switch (keys[i].judge) {
        case BSP_KEY_JUDGE_IDLE:
            if (keys[i].state == KEY_PRESS) {
                keys[i].judge = BSP_KEY_JUDGE_PRESS;
            }
            break;

        case BSP_KEY_JUDGE_PRESS:
            if (keys[i].state == KEY_PRESS) {
                keys[i].judge = BSP_KEY_JUDGE_LONGPUSH;
                keys[i].longpush_time = 0;
            } else {
                keys[i].judge = BSP_KEY_JUDGE_IDLE;
            }
            break;

        case BSP_KEY_JUDGE_LONGPUSH:
            if (keys[i].state == KEY_PRESS) {
                keys[i].longpush_time++;
                if (keys[i].longpush_time >= BSP_KEY_LONGPUSH_MIN_TIME) {
                    keys[i].longpush_time = 0;
                    keys[i].judge = BSP_KEY_JUDGE_RELEASE;
                    keys[i].f_longpush = BSP_KEY_EVENT_LONGPUSH;
                }
            } else {
                keys[i].longpush_time = 0;
                keys[i].doubleclick_time = 0;
                keys[i].judge = BSP_KEY_JUDGE_DOUBLECLICK;
            }
            break;

        case BSP_KEY_JUDGE_DOUBLECLICK:
            keys[i].doubleclick_time++;
            if (keys[i].state == KEY_PRESS && keys[i].doubleclick_time <= BSP_KEY_DOUBLE_TIMEOUT) {
                keys[i].judge = BSP_KEY_JUDGE_RELEASE;
                keys[i].doubleclick_time = 0;
                keys[i].f_doubleclick = BSP_KEY_EVENT_DOUBLECLICK;
            } else if (keys[i].state == KEY_RELEASE && keys[i].doubleclick_time > BSP_KEY_DOUBLE_TIMEOUT) {
                keys[i].judge = BSP_KEY_JUDGE_IDLE;
                keys[i].doubleclick_time = 0;
                keys[i].f_push = BSP_KEY_EVENT_PUSH;
            }
            break;

        case BSP_KEY_JUDGE_RELEASE:
            if (keys[i].state == KEY_RELEASE) {
                keys[i].judge = BSP_KEY_JUDGE_IDLE;
            }
            break;
        }
    }
}

void BSP_Key_EasyScan(bsp_key_t *keys, uint8_t num)
{
    for (uint8_t i = 0; i < num; i++) {
        keys[i].state = GPIO_ReadPin(keys[i].port, keys[i].pin);
    }

    for (uint8_t i = 0; i < num; i++) {
        switch (keys[i].judge) {
        case BSP_KEY_JUDGE_IDLE:
            if (keys[i].state == KEY_PRESS) keys[i].judge = BSP_KEY_JUDGE_PRESS;
            break;
        case BSP_KEY_JUDGE_PRESS:
            if (keys[i].state == KEY_PRESS) keys[i].judge = BSP_KEY_JUDGE_LONGPUSH;
            else keys[i].judge = BSP_KEY_JUDGE_IDLE;
            break;
        case BSP_KEY_JUDGE_LONGPUSH:
            if (keys[i].state == KEY_RELEASE) {
                keys[i].f_push = 1;
                keys[i].judge = BSP_KEY_JUDGE_IDLE;
            }
            break;
        default:
            keys[i].judge = BSP_KEY_JUDGE_IDLE;
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
