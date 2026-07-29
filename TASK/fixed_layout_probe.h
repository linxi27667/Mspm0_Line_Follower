/**
 * @file    fixed_layout_probe.h
 * @brief   Pen-up commissioning task for the fixed paper/machine placement.
 */
#ifndef FIXED_LAYOUT_PROBE_H
#define FIXED_LAYOUT_PROBE_H

#include <stdbool.h>
#include <stdint.h>

#define FIXED_LAYOUT_PROBE_BUILD_ID "FIXED_LAYOUT_AUTHOR_AXIS_PROBE_V2"

typedef enum {
    FIXED_LAYOUT_PROBE_STATE_IDLE = 0,
    FIXED_LAYOUT_PROBE_STATE_WAIT_GATE,
    FIXED_LAYOUT_PROBE_STATE_RUNNING,
    FIXED_LAYOUT_PROBE_STATE_DONE,
    FIXED_LAYOUT_PROBE_STATE_STOPPED,
    FIXED_LAYOUT_PROBE_STATE_ERROR
} fixed_layout_probe_state_t;

void FixedLayoutProbe_Start(void);
void FixedLayoutProbe_Update(void);
bool FixedLayoutProbe_Process_Frame(const uint8_t *frame, uint16_t len);
bool FixedLayoutProbe_Is_Done(void);
fixed_layout_probe_state_t FixedLayoutProbe_Get_State(void);

#endif /* FIXED_LAYOUT_PROBE_H */
