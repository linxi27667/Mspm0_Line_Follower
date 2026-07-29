/**
 * @file    final_xy_point_test.h
 * @brief   Gated final-parameter five-point XY endpoint diagnostic.
 */
#ifndef FINAL_XY_POINT_TEST_H
#define FINAL_XY_POINT_TEST_H

#include <stdbool.h>
#include <stdint.h>

#define FINAL_XY_POINT_TEST_BUILD_ID \
    "AUTHOR_TEXT_Y1095_5POINT_DOTS_L205_L203_GATED_V34"

#define FINAL_XY_POINT_TEST_TARGET_COUNT       (9u)
#define FINAL_XY_POINT_TEST_MARK_COUNT         (9u)
#define FINAL_XY_POINT_TEST_UNIQUE_POINT_COUNT (5u)
#define FINAL_XY_POINT_TEST_CENTER_STAMP_COUNT (5u)
#define FINAL_XY_POINT_TEST_START_SETTLE_MS    (300u)
#define FINAL_XY_POINT_TEST_DOWN_HOLD_MS       (700u)
#define FINAL_XY_POINT_TEST_UP_SETTLE_MS       (700u)
#define FINAL_XY_POINT_TEST_POSITION_EPS_MM    (0.08f)
#define FINAL_XY_POINT_TEST_ALIGN_FEED_MM_MIN  (600.0f)
#define FINAL_XY_POINT_TEST_MOVE_FEED_MM_MIN   (240.0f)

typedef enum {
    FINAL_XY_POINT_TEST_STATE_IDLE = 0,
    FINAL_XY_POINT_TEST_STATE_WAIT_ALIGN,
    FINAL_XY_POINT_TEST_STATE_RUNNING_ALIGN,
    FINAL_XY_POINT_TEST_STATE_WAIT_DOTS,
    FINAL_XY_POINT_TEST_STATE_MOVE,
    FINAL_XY_POINT_TEST_STATE_WAIT_MOVE,
    FINAL_XY_POINT_TEST_STATE_START_SETTLE,
    FINAL_XY_POINT_TEST_STATE_DOWN_HOLD,
    FINAL_XY_POINT_TEST_STATE_UP_SETTLE,
    FINAL_XY_POINT_TEST_STATE_DONE,
    FINAL_XY_POINT_TEST_STATE_STOPPED,
    FINAL_XY_POINT_TEST_STATE_ERROR
} final_xy_point_test_state_t;

void FinalXYPointTest_Start(void);
void FinalXYPointTest_Update(void);
bool FinalXYPointTest_Process_Frame(const uint8_t *frame, uint16_t len);
bool FinalXYPointTest_Is_Done(void);
final_xy_point_test_state_t FinalXYPointTest_Get_State(void);

#endif /* FINAL_XY_POINT_TEST_H */
