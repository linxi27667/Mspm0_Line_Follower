/**
 * @file    app_puzzle_frame.h
 * @brief   Explicit paper-frame to calibrated motion-frame conversion.
 *
 * Coordinate layers:
 *   1. Mechanical home: two joint/step counters zeroed by limit switches.
 *   2. Legacy calibration frame: the measured four-point projective model.
 *   3. Paper frame: origin at the former P4 corner, X+ right, Y+ down.
 *
 * Mechanical home and paper zero are intentionally independent.
 */
#ifndef APP_PUZZLE_FRAME_H
#define APP_PUZZLE_FRAME_H

#include <stdbool.h>

#define APP_PUZZLE_FRAME_BUILD_ID \
    "PAPER_TRAPEZOID199_120_H243_TRI_MESH_4ROW_ALIGN_V12"

#define APP_PUZZLE_PAPER_WIDTH_MM             (199.0f)
#define APP_PUZZLE_PAPER_HEIGHT_MM            (243.0f)
#define APP_PUZZLE_TRAPEZOID_SHOULDER_Y_MM    (180.0f)
#define APP_PUZZLE_TRAPEZOID_BOTTOM_LEFT_X_MM (40.0f)
#define APP_PUZZLE_TRAPEZOID_BOTTOM_RIGHT_X_MM (160.0f)
#define APP_PUZZLE_PAPER_ZERO_CORNER_NUMBER   (4u)
#define APP_PUZZLE_PAPER_FRAME_TEXT \
    "P4_ZERO_X_RIGHT_Y_DOWN_TRAPEZOID_TRI_MESH_4ROW_ALIGN"
#define APP_PUZZLE_MACHINE_HOME_TEXT \
    "JOINT_LIMIT_SWITCH_ZERO"

typedef struct {
    float paper_x_mm;
    float paper_y_mm;
    float calibration_input_x_mm;
    float calibration_input_y_mm;
    float mapped_paper_x_mm;
    float mapped_paper_y_mm;
    float legacy_work_x_mm;
    float legacy_work_y_mm;
    float calibrated_physical_x_mm;
    float calibrated_physical_y_mm;
    float user_x_mm;
    float user_y_mm;
} app_puzzle_frame_map_t;

bool App_PuzzleFrame_Is_In_Bounds(float paper_x_mm, float paper_y_mm);
bool App_PuzzleFrame_To_User(float paper_x_mm, float paper_y_mm,
                             app_puzzle_frame_map_t *map);

#endif /* APP_PUZZLE_FRAME_H */
