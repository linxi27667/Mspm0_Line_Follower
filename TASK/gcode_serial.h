/**
 * @file    gcode_serial.h
 * @brief   Official DrawBot host compatible serial G-code executor.
 */
#ifndef GCODE_SERIAL_H
#define GCODE_SERIAL_H

#include <stdbool.h>
#include <stdint.h>

#define GCODE_SERIAL_BUILD_ID                \
    "PAPER_A4_CLOUD_GCODE_DIRECT_V36"

/* Standard G-code source coordinates are fixed A4 paper millimetres. */
#define GCODE_SERIAL_USE_FIXED_SOURCE_ORIGIN  (1u)
#define GCODE_SERIAL_SOURCE_ORIGIN_X_MM       (0.0f)
#define GCODE_SERIAL_SOURCE_ORIGIN_Y_MM       (0.0f)
/*
 * Global post-map workspace translation.  Keep the physical limit-switch
 * angles and homing pull-off unchanged; every accepted G0/G1 target is moved
 * together in Cartesian user space after any paper mapping.
 */
#define GCODE_SERIAL_WORKSPACE_SHIFT_X_MM     (0.0f)
#define GCODE_SERIAL_WORKSPACE_SHIFT_Y_MM     (15.0f)
#define GCODE_SERIAL_PAPER_CALIBRATION_ENABLE (1u)
#define GCODE_SERIAL_PAPER_MAP_ENABLE         (1u)
#define GCODE_SERIAL_PAPER_DRAW_SEGMENT_MM    (1.0f)
#define GCODE_SERIAL_RAPID_SEGMENT_MM         (20.0f)

#define GCODE_SERIAL_RESTRICTED_RECT_ENABLE   (0u)
#define GCODE_SERIAL_RECT_CCW_ENABLE          (1u)
#define GCODE_SERIAL_RECT_X0_MM               (120.0f)
#define GCODE_SERIAL_RECT_Y0_MM               (5.0f)
#define GCODE_SERIAL_RECT_X1_MM               (290.0f)
#define GCODE_SERIAL_RECT_Y1_MM               (125.0f)
#define GCODE_SERIAL_RECT_POINT_STEP_MAX_MM   (1.01f)

typedef void (*gcode_serial_result_callback_t)(bool ok,
                                                const char *detail,
                                                void *context);

void GCodeSerial_Start(void);
void GCodeSerial_Update(void);
bool GCodeSerial_ProcessFrame(const uint8_t *frame, uint16_t len);
void GCodeSerial_Set_Result_Callback(
    gcode_serial_result_callback_t callback,
    void *context);
bool GCodeSerial_Is_Idle(void);
bool GCodeSerial_Is_Pen_Down(void);
void GCodeSerial_Abort(void);

#endif /* GCODE_SERIAL_H */
