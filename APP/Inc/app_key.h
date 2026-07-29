/**
 * @file    app_key.h
 * @brief   Four active-low panel keys with millisecond software debounce.
 */
#ifndef APP_KEY_H
#define APP_KEY_H

#include <stdbool.h>
#include <stdint.h>

#define APP_KEY_COUNT        (4u)
#define APP_KEY_DEBOUNCE_MS  (30u)

typedef enum {
    APP_KEY_1_REHOME = 0,
    APP_KEY_2_AREA_MARK,
    APP_KEY_3_ORIGIN_MARK,
    APP_KEY_4_RESERVED
} app_key_id_t;

/*
 * The inputs and pull-ups are configured by TI_moban.syscfg.
 * Call Update continuously; timing is based on the 1 ms system tick, not on
 * the number of main-loop scans.
 */
void App_Key_Init(uint32_t now_ms);
void App_Key_Update(uint32_t now_ms);
bool App_Key_Take_Press(app_key_id_t key);
bool App_Key_Is_Pressed(app_key_id_t key);
void App_Key_Clear_Events(void);

#endif /* APP_KEY_H */
