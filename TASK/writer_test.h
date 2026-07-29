/**
 * @file    writer_test.h
 * @brief   Writer robot task selector for the retained execution paths.
 */
#ifndef WRITER_TEST_H
#define WRITER_TEST_H

#include <stdbool.h>
#include <stdint.h>

#define WRITER_TEST_MODE_GCODE_SERIAL     (12u)
#define WRITER_TEST_MODE_AUTHOR_TEXT_DEMO (25u)
#define WRITER_TEST_MODE_FINAL_XY_POINT_DOTS (26u)
#define WRITER_TEST_MODE_FIXED_LAYOUT_PROBE (27u)
#define WRITER_TEST_MODE_FIXED_LAYOUT_AXIS_MARK (28u)
#define WRITER_TEST_MODE_PUZZLE_AREA_PROBE (29u)

/* Retain the patrol implementation, but bypass it for cloud G-code mode. */
#define WRITER_TEST_BOOT_PATROL_4DOT_ENABLE (0u)
#define WRITER_TEST_BOOT_PATROL_4DOT_BUILD_ID \
    "PAPER_A4_CLOUD_GCODE_DIRECT_V36"

/* Gated pen-up patrol of the currently calibrated puzzle work rectangle. */
#define WRITER_TEST_MODE             WRITER_TEST_MODE_PUZZLE_AREA_PROBE

/*
 * UART1 is the temporary vision link in puzzle mode. This deliberately
 * overrides an enabled local cloud configuration so PB4/PB5 can be connected
 * to a serial assistant now and to the K230 later.
 */
#define WRITER_TEST_LOCAL_UART_CONTROL_ENABLE \
    ((WRITER_TEST_MODE == WRITER_TEST_MODE_PUZZLE_AREA_PROBE) ? 1u : 0u)

#if (WRITER_TEST_MODE != WRITER_TEST_MODE_GCODE_SERIAL) && \
    (WRITER_TEST_MODE != WRITER_TEST_MODE_AUTHOR_TEXT_DEMO) && \
    (WRITER_TEST_MODE != WRITER_TEST_MODE_FINAL_XY_POINT_DOTS) && \
    (WRITER_TEST_MODE != WRITER_TEST_MODE_FIXED_LAYOUT_PROBE) && \
    (WRITER_TEST_MODE != WRITER_TEST_MODE_FIXED_LAYOUT_AXIS_MARK) && \
    (WRITER_TEST_MODE != WRITER_TEST_MODE_PUZZLE_AREA_PROBE)
#error "Unsupported retained writer task"
#endif

typedef enum {
    WRITER_TEST_STATE_IDLE = 0,
    WRITER_TEST_STATE_RUNNING,
    WRITER_TEST_STATE_DONE
} writer_test_state_t;

void WriterTest_Start(void);
void WriterTest_Update(void);
bool WriterTest_Trigger_Puzzle_Area_Marks(void);
bool WriterTest_Trigger_Paper_Origin_Mark(void);
void WriterTest_Abort_For_Rehome(void);
bool WriterTest_Process_Serial_Frame(const uint8_t *frame, uint16_t len);
bool WriterTest_Is_Done(void);
writer_test_state_t WriterTest_Get_State(void);
bool WriterTest_Startup_Is_Complete(void);
bool WriterTest_Startup_Succeeded(void);

#endif /* WRITER_TEST_H */
