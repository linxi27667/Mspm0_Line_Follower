/**
 * @file    puzzle_area_probe.h
 * @brief   Key-triggered corner marks and calibrated horizontal divider.
 */
#ifndef PUZZLE_AREA_PROBE_H
#define PUZZLE_AREA_PROBE_H

#include <stdbool.h>
#include <stdint.h>

#define PUZZLE_AREA_PROBE_BUILD_ID \
    "PUZZLE_UART_XY_SIM_K230_PROTOCOL_V23"

typedef enum {
    PUZZLE_AREA_PROBE_STATE_IDLE = 0,
    PUZZLE_AREA_PROBE_STATE_WAIT_TRIGGER,
    PUZZLE_AREA_PROBE_STATE_MOVING,
    PUZZLE_AREA_PROBE_STATE_MARK_DOWN_HOLD,
    PUZZLE_AREA_PROBE_STATE_MARK_UP_SETTLE,
    PUZZLE_AREA_PROBE_STATE_DWELL,
    PUZZLE_AREA_PROBE_STATE_LINE_DOWN_HOLD,
    PUZZLE_AREA_PROBE_STATE_LINE_UP_SETTLE,
    PUZZLE_AREA_PROBE_STATE_SERIAL_MOVING,
    PUZZLE_AREA_PROBE_STATE_SERIAL_DOT_DOWN_HOLD,
    PUZZLE_AREA_PROBE_STATE_SERIAL_DOT_UP_SETTLE,
    PUZZLE_AREA_PROBE_STATE_DONE,
    PUZZLE_AREA_PROBE_STATE_STOPPED,
    PUZZLE_AREA_PROBE_STATE_ERROR
} puzzle_area_probe_state_t;

void PuzzleAreaProbe_Start(void);
bool PuzzleAreaProbe_Trigger(void);
void PuzzleAreaProbe_Abort_For_Rehome(void);
void PuzzleAreaProbe_Update(void);
bool PuzzleAreaProbe_Process_Frame(const uint8_t *frame, uint16_t len);
bool PuzzleAreaProbe_Is_Done(void);
puzzle_area_probe_state_t PuzzleAreaProbe_Get_State(void);

#endif /* PUZZLE_AREA_PROBE_H */
