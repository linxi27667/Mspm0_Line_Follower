/**
 * @file    app_writer_paper_map.h
 * @brief   Standard A4 paper coordinates to writer user coordinates.
 */
#ifndef APP_WRITER_PAPER_MAP_H
#define APP_WRITER_PAPER_MAP_H

#include <stdbool.h>
#include <stdint.h>

#define APP_WRITER_PAPER_MAP_BUILD_ID \
    "A4_BASE_QUADRATIC_XSCALE_NO_SBOW_Y45_265_TRIAL_V9"

#define APP_WRITER_PAPER_X_MIN_MM             (25.0f)
#define APP_WRITER_PAPER_X_MAX_MM             (185.0f)
#define APP_WRITER_PAPER_Y_MIN_MM             (45.0f)
#define APP_WRITER_PAPER_Y_MAX_MM             (265.0f)
#define APP_WRITER_PAPER_CALIBRATED_Y_MIN_MM  (75.0f)
#define APP_WRITER_PAPER_CALIBRATED_Y_MAX_MM  (235.0f)
#define APP_WRITER_PAPER_EXTENDED_Y_TRIAL_ENABLE (1u)
#define APP_WRITER_PAPER_GRID_COLS             (4u)
#define APP_WRITER_PAPER_GRID_ROWS             (7u)

/*
 * The 4x7 residual table includes the second correction derived from all
 * twenty-eight measured V24 verification dots.
 */
#define APP_WRITER_PAPER_GRID_CORRECTION_ENABLE (0u)
#define APP_WRITER_PAPER_S_BOW_CORRECTION_ENABLE (0u)
#define APP_WRITER_PAPER_VERTICAL_SBOW_RIGHT_ONLY_ENABLE (1u)
#define APP_WRITER_PAPER_VERTICAL_SBOW_RIGHT_X0_MM (105.0f)
#define APP_WRITER_PAPER_VERTICAL_SBOW_RIGHT_X1_MM (185.0f)
#define APP_WRITER_PAPER_X_SCALE_OBSERVED      (1.03125f)
#define APP_WRITER_PAPER_LEGACY_Y_SHIFT_MM     (15.0f)

/*
 * Pre-panel-key puzzle-area kinematic baseline:
 * use the established paper map directly.  The later placement-only
 * corrections (+3/-128 and +44/-180) are deliberately removed because they
 * drove the linkage outside the previously verified joint envelope.
 *
 * Keep these symbols so the retained KEY2/KEY3 task code does not change;
 * a zero correction restores the original calibrated rectangle.
 */
#define APP_WRITER_LANDSCAPE_MAP_ORIGIN_X_MM   (25.0f)
#define APP_WRITER_LANDSCAPE_MAP_ORIGIN_Y_MM   (75.0f)
#define APP_WRITER_LANDSCAPE_SHIFT_X_MM        (0.0f)
#define APP_WRITER_LANDSCAPE_SHIFT_Y_MM        (0.0f)

bool WriterPaperMap_Is_In_Bounds(float paper_x_mm, float paper_y_mm);
bool WriterPaperMap_To_User(float paper_x_mm, float paper_y_mm,
                           float *user_x_mm, float *user_y_mm);

#endif /* APP_WRITER_PAPER_MAP_H */
