/**
 * @file    author_text_demo.h
 * @brief   UART-triggered V44 one-file A4 3x3 local calibration.
 */
#ifndef AUTHOR_TEXT_DEMO_H
#define AUTHOR_TEXT_DEMO_H

#include <stdbool.h>
#include <stdint.h>

#define AUTHOR_TEXT_DEMO_BUILD_ID \
    "AUTHOR_A4_3X3_20MM_SQUARE_CROSS_DRAW_L205_L203_ONEFILE_V44"
#define AUTHOR_TEXT_DEMO_POSITION_EPS_MM       (0.15f)
#define AUTHOR_TEXT_DEMO_MOVE_FEED_MM_MIN      (300.0f)
#define AUTHOR_TEXT_DEMO_DRAW_FEED_MM_MIN      (240.0f)
#define AUTHOR_TEXT_DEMO_PEN_SETTLE_MS         (500u)
#define AUTHOR_TEXT_DEMO_ALIGN_PAUSE_MS        (3000u)

typedef enum {
    AUTHOR_TEXT_DEMO_STATE_IDLE = 0,
    AUTHOR_TEXT_DEMO_STATE_WAIT_ALIGN,
    AUTHOR_TEXT_DEMO_STATE_RUNNING_ALIGN,
    AUTHOR_TEXT_DEMO_STATE_WAIT_CALIBRATION,
    AUTHOR_TEXT_DEMO_STATE_RUNNING_CALIBRATION,
    AUTHOR_TEXT_DEMO_STATE_DONE,
    AUTHOR_TEXT_DEMO_STATE_STOPPED,
    AUTHOR_TEXT_DEMO_STATE_ERROR
} author_text_demo_state_t;

void AuthorTextDemo_Start(void);
void AuthorTextDemo_Update(void);
bool AuthorTextDemo_Process_Frame(const uint8_t *frame, uint16_t len);
bool AuthorTextDemo_Is_Done(void);
author_text_demo_state_t AuthorTextDemo_Get_State(void);

#endif /* AUTHOR_TEXT_DEMO_H */
