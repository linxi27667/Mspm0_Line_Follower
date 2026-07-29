/**
 * @file    fixed_layout_axis_mark.h
 * @brief   Gated origin and author-axis calibration mark for the fixed layout.
 */
#ifndef FIXED_LAYOUT_AXIS_MARK_H
#define FIXED_LAYOUT_AXIS_MARK_H

#include <stdbool.h>
#include <stdint.h>

#define FIXED_LAYOUT_AXIS_MARK_BUILD_ID "FIXED_LAYOUT_3RECT_X95_Y20_130_LOCALCAL_V18"

typedef enum {
    FIXED_LAYOUT_AXIS_MARK_STATE_IDLE = 0,
    FIXED_LAYOUT_AXIS_MARK_STATE_WAIT_ALIGN,
    FIXED_LAYOUT_AXIS_MARK_STATE_RUNNING_ALIGN,
    FIXED_LAYOUT_AXIS_MARK_STATE_WAIT_DRAW,
    FIXED_LAYOUT_AXIS_MARK_STATE_RUNNING_DRAW,
    FIXED_LAYOUT_AXIS_MARK_STATE_DONE,
    FIXED_LAYOUT_AXIS_MARK_STATE_STOPPED,
    FIXED_LAYOUT_AXIS_MARK_STATE_ERROR
} fixed_layout_axis_mark_state_t;

void FixedLayoutAxisMark_Start(void);
void FixedLayoutAxisMark_Update(void);
bool FixedLayoutAxisMark_Process_Frame(const uint8_t *frame, uint16_t len);
bool FixedLayoutAxisMark_Is_Done(void);
fixed_layout_axis_mark_state_t FixedLayoutAxisMark_Get_State(void);

#endif /* FIXED_LAYOUT_AXIS_MARK_H */
