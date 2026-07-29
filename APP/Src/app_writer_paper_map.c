/**
 * @file    app_writer_paper_map.c
 * @brief   Shared paper-coordinate mapping for standard G0/G1 execution.
 */
#include "app_writer_paper_map.h"

#define PAPER_MAP_BOUND_EPS_MM (0.001f)
#define PAPER_MAP_VERTICAL_KNOT_COUNT   (5u)
#define PAPER_MAP_HORIZONTAL_KNOT_COUNT (4u)

/*
 * Stable global paper-to-user baseline fitted from the previous 36 measured
 * paper vertices. Inputs are normalized as:
 *   nx = (paper_x - 105) / 100
 *   ny = (paper_y - 130) / 100
 * and evaluated with [1, nx, ny, nx^2, nx*ny, ny^2].
 *
 * The 4x7 table is a user-coordinate residual correction on top of this
 * global baseline. V5 directly inverts each measured V24 physical cell into
 * the corresponding V24 user-command cell.
 */
static const float s_base_x[6] = {
    290.945962f, 62.273998f, -78.732064f,
    -3.922490f, -2.442049f, 5.239680f,
};
static const float s_base_y[6] = {
    30.887338f, 84.802037f, 52.883179f,
    -7.669222f, 3.617273f, 3.846007f,
};

#if APP_WRITER_PAPER_S_BOW_CORRECTION_ENABLE
/*
 * V60 measured residuals in nominal physical A4 coordinates.
 *
 * Vertical strokes run from physical Y=235 down to Y=75:
 *   distance down [mm] : 0, 7, 55, 125, 160
 *   observed X error   : 0, 0, -2,   0,  +4
 *
 * Horizontal strokes run from physical X=25 to X=185:
 *   distance right [mm]: 0, 40, 92.5, 160
 *   observed Y error   : 0, -2,    0,  +4
 *
 * Negative errors are left/below the reference.  The map applies the
 * opposite pre-warp before evaluating the stable base quadratic.
 *
 * The vertical X-error samples came from the right-side calibration stroke.
 * V7 therefore keeps the paper's left half on the stable baseline and
 * smoothly blends the vertical correction from zero at X=105 to full
 * strength at X=185.  Horizontal Y-error compensation remains global.
 */
static const float s_vertical_distance_down_mm[
    PAPER_MAP_VERTICAL_KNOT_COUNT] = {
    0.0f, 7.0f, 55.0f, 125.0f, 160.0f,
};
static const float s_vertical_x_error_mm[
    PAPER_MAP_VERTICAL_KNOT_COUNT] = {
    0.0f, 0.0f, -2.0f, 0.0f, 4.0f,
};
static const float s_vertical_x_slope[
    PAPER_MAP_VERTICAL_KNOT_COUNT] = {
    0.0f, 0.0f, 0.0f, 0.048979592f, 0.142857143f,
};
static const float s_horizontal_distance_right_mm[
    PAPER_MAP_HORIZONTAL_KNOT_COUNT] = {
    0.0f, 40.0f, 92.5f, 160.0f,
};
static const float s_horizontal_y_error_mm[
    PAPER_MAP_HORIZONTAL_KNOT_COUNT] = {
    0.0f, -2.0f, 0.0f, 4.0f,
};
static const float s_horizontal_y_slope[
    PAPER_MAP_HORIZONTAL_KNOT_COUNT] = {
    -0.088095238f, 0.0f, 0.045960503f, 0.071164021f,
};

static float WriterPaperMap_Clamp(float value, float lower, float upper)
{
    if (value < lower) {
        return lower;
    }
    if (value > upper) {
        return upper;
    }
    return value;
}

static float WriterPaperMap_Pchip(const float *knots,
                                  const float *values,
                                  const float *slopes,
                                  uint32_t count,
                                  float input)
{
    uint32_t index;
    float width;
    float t;
    float t2;
    float t3;
    float h00;
    float h10;
    float h01;
    float h11;

    input = WriterPaperMap_Clamp(
        input, knots[0], knots[count - 1u]);
    index = count - 2u;
    for (uint32_t candidate = 0u;
         candidate + 1u < count;
         candidate++) {
        if (input <= knots[candidate + 1u]) {
            index = candidate;
            break;
        }
    }
    width = knots[index + 1u] - knots[index];
    t = (input - knots[index]) / width;
    t2 = t * t;
    t3 = t2 * t;
    h00 = 2.0f * t3 - 3.0f * t2 + 1.0f;
    h10 = t3 - 2.0f * t2 + t;
    h01 = -2.0f * t3 + 3.0f * t2;
    h11 = t3 - t2;
    return h00 * values[index] +
           h10 * width * slopes[index] +
           h01 * values[index + 1u] +
           h11 * width * slopes[index + 1u];
}

static float WriterPaperMap_Vertical_Sbow_Weight(float paper_x_mm)
{
#if APP_WRITER_PAPER_VERTICAL_SBOW_RIGHT_ONLY_ENABLE
    float t = (paper_x_mm -
               APP_WRITER_PAPER_VERTICAL_SBOW_RIGHT_X0_MM) /
              (APP_WRITER_PAPER_VERTICAL_SBOW_RIGHT_X1_MM -
               APP_WRITER_PAPER_VERTICAL_SBOW_RIGHT_X0_MM);

    /*
     * Smoothstep keeps both ends continuous with zero slope.  X<=105 is
     * untouched; X=185 receives the complete measured correction.
     */
    t = WriterPaperMap_Clamp(t, 0.0f, 1.0f);
    return t * t * (3.0f - 2.0f * t);
#else
    (void)paper_x_mm;
    return 1.0f;
#endif
}

static void WriterPaperMap_Apply_Measured_Prewarp(
    float paper_x_mm, float paper_y_mm,
    float *corrected_x_mm, float *corrected_y_mm)
{
    float distance_down_mm = 235.0f - paper_y_mm;
    float distance_right_mm = paper_x_mm - 25.0f;
    float x_error_mm = WriterPaperMap_Pchip(
        s_vertical_distance_down_mm,
        s_vertical_x_error_mm,
        s_vertical_x_slope,
        PAPER_MAP_VERTICAL_KNOT_COUNT,
        distance_down_mm);
    float y_error_mm = WriterPaperMap_Pchip(
        s_horizontal_distance_right_mm,
        s_horizontal_y_error_mm,
        s_horizontal_y_slope,
        PAPER_MAP_HORIZONTAL_KNOT_COUNT,
        distance_right_mm);
    float vertical_sbow_weight =
        WriterPaperMap_Vertical_Sbow_Weight(paper_x_mm);

    *corrected_x_mm = 105.0f +
        (paper_x_mm - 105.0f) /
        APP_WRITER_PAPER_X_SCALE_OBSERVED -
        vertical_sbow_weight * x_error_mm;
    *corrected_y_mm = paper_y_mm - y_error_mm -
        APP_WRITER_PAPER_LEGACY_Y_SHIFT_MM;
}
#endif

#if APP_WRITER_PAPER_GRID_CORRECTION_ENABLE
static const float s_grid_x[APP_WRITER_PAPER_GRID_COLS] = {
    25.0f, 78.333333f, 131.666667f, 185.0f,
};
static const float s_grid_y[APP_WRITER_PAPER_GRID_ROWS] = {
    20.0f, 56.666667f, 93.333333f, 130.0f,
    167.0f, 203.666667f, 240.333333f,
};

/*
 * User-coordinate residuals at the twenty-eight paper nodes.
 */
static const float s_grid_dx[APP_WRITER_PAPER_GRID_ROWS]
                            [APP_WRITER_PAPER_GRID_COLS] = {
    {15.374045f, 11.264158f, 8.010076f, 7.482587f},
    {11.971359f, 11.478098f, 9.812184f, 10.295691f},
    {10.857600f, 16.953468f, 15.238151f, 13.522322f},
    {9.097849f, 12.655831f, 12.629562f, 14.224327f},
    {9.415328f, 16.061117f, 13.622487f, 15.102993f},
    {11.297691f, 11.506274f, 12.110170f, 14.702651f},
    {10.914966f, 8.135556f, 9.048756f, 12.367785f},
};
static const float s_grid_dy[APP_WRITER_PAPER_GRID_ROWS]
                            [APP_WRITER_PAPER_GRID_COLS] = {
    {-8.007694f, -13.058400f, -14.102836f, -13.665245f},
    {-6.734813f, -10.434403f, -11.232856f, -9.807597f},
    {-5.488841f, -2.945919f, -4.604275f, -5.962542f},
    {-8.424914f, -8.309162f, -8.901382f, -6.034423f},
    {-9.226505f, -1.609058f, -5.895272f, -4.394807f},
    {-10.213145f, -8.589176f, -8.779323f, -5.775140f},
    {1.421038f, -2.770281f, -5.900727f, -7.896923f},
};

static uint32_t WriterPaperMap_Cell(const float *nodes, uint32_t count,
                                    float value)
{
    uint32_t index;

    for (index = 0u; index + 1u < count; index++) {
        if (value <= nodes[index + 1u]) {
            return index;
        }
    }
    return count - 2u;
}

static float WriterPaperMap_Bilerp(float q00, float q10,
                                   float q01, float q11,
                                   float tx, float ty)
{
    float lower = q00 + (q10 - q00) * tx;
    float upper = q01 + (q11 - q01) * tx;

    return lower + (upper - lower) * ty;
}
#endif

bool WriterPaperMap_Is_In_Bounds(float paper_x_mm, float paper_y_mm)
{
    return
        (paper_x_mm >=
         APP_WRITER_PAPER_X_MIN_MM - PAPER_MAP_BOUND_EPS_MM) &&
        (paper_x_mm <=
         APP_WRITER_PAPER_X_MAX_MM + PAPER_MAP_BOUND_EPS_MM) &&
        (paper_y_mm >=
         APP_WRITER_PAPER_Y_MIN_MM - PAPER_MAP_BOUND_EPS_MM) &&
        (paper_y_mm <=
         APP_WRITER_PAPER_Y_MAX_MM + PAPER_MAP_BOUND_EPS_MM);
}

bool WriterPaperMap_To_User(float paper_x_mm, float paper_y_mm,
                           float *user_x_mm, float *user_y_mm)
{
    float calibrated_x_mm;
    float calibrated_y_mm;
    float nx;
    float ny;
    float basis[6];
    float mapped_x;
    float mapped_y;
    uint32_t index;

    if ((user_x_mm == 0) || (user_y_mm == 0) ||
        !WriterPaperMap_Is_In_Bounds(paper_x_mm, paper_y_mm)) {
        return false;
    }

#if APP_WRITER_PAPER_S_BOW_CORRECTION_ENABLE
    WriterPaperMap_Apply_Measured_Prewarp(
        paper_x_mm, paper_y_mm,
        &calibrated_x_mm, &calibrated_y_mm);
#else
    /*
     * V31 single-variable diagnostic:
     * keep the established global X scale and legacy/user Y-shift contract,
     * but do not turn the direction-dependent 160 mm line residual into a
     * static short-stroke warp.
     */
    calibrated_x_mm = 105.0f +
        (paper_x_mm - 105.0f) /
        APP_WRITER_PAPER_X_SCALE_OBSERVED;
    calibrated_y_mm = paper_y_mm -
        APP_WRITER_PAPER_LEGACY_Y_SHIFT_MM;
#endif

    nx = (calibrated_x_mm - 105.0f) / 100.0f;
    ny = (calibrated_y_mm - 130.0f) / 100.0f;
    basis[0] = 1.0f;
    basis[1] = nx;
    basis[2] = ny;
    basis[3] = nx * nx;
    basis[4] = nx * ny;
    basis[5] = ny * ny;
    mapped_x = 0.0f;
    mapped_y = 0.0f;
    for (index = 0u; index < 6u; index++) {
        mapped_x += basis[index] * s_base_x[index];
        mapped_y += basis[index] * s_base_y[index];
    }

#if APP_WRITER_PAPER_GRID_CORRECTION_ENABLE
    {
        uint32_t column = WriterPaperMap_Cell(
            s_grid_x, APP_WRITER_PAPER_GRID_COLS, calibrated_x_mm);
        uint32_t row = WriterPaperMap_Cell(
            s_grid_y, APP_WRITER_PAPER_GRID_ROWS, calibrated_y_mm);
        float tx = (calibrated_x_mm - s_grid_x[column]) /
                   (s_grid_x[column + 1u] - s_grid_x[column]);
        float ty = (calibrated_y_mm - s_grid_y[row]) /
                   (s_grid_y[row + 1u] - s_grid_y[row]);

        mapped_x += WriterPaperMap_Bilerp(
            s_grid_dx[row][column],
            s_grid_dx[row][column + 1u],
            s_grid_dx[row + 1u][column],
            s_grid_dx[row + 1u][column + 1u],
            tx, ty);
        mapped_y += WriterPaperMap_Bilerp(
            s_grid_dy[row][column],
            s_grid_dy[row][column + 1u],
            s_grid_dy[row + 1u][column],
            s_grid_dy[row + 1u][column + 1u],
            tx, ty);
    }
#endif

    *user_x_mm = mapped_x;
    *user_y_mm = mapped_y;
    return true;
}
