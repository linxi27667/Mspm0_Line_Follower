/**
 * @file    app_puzzle_frame.c
 * @brief   New paper coordinates composed with the established calibration.
 */
#include "app_puzzle_frame.h"

#include <math.h>
#include <stddef.h>
#include <stdint.h>

#define PUZZLE_FRAME_BOUND_EPS_MM                 (0.001f)
#define PUZZLE_CALIBRATION_WIDTH_MM                (199.0f)
#define PUZZLE_CALIBRATION_HEIGHT_MM               (243.0f)
#define PUZZLE_MESH_NODE_COUNT                     (24u)
#define PUZZLE_MESH_TRIANGLE_COUNT                 (31u)
#define PUZZLE_MESH_BARYCENTRIC_MIN                (-0.55f)
#define PUZZLE_MESH_BARYCENTRIC_MAX                (1.55f)
#define PUZZLE_MESH_INSIDE_EPS                     (0.0001f)
#define PUZZLE_MESH_DETERMINANT_MIN                (0.0001f)
#define PUZZLE_RIGHT_EDGE_CORRECTION_NODE_COUNT    (5u)

/* Corrected quadrilateral corner coordinates in the calibration plane. */
#define LEGACY_BOTTOM_LEFT_X_MM                   (-9.0f)
#define LEGACY_BOTTOM_RIGHT_X_MM                  (191.5f)
#define LEGACY_TOP_RIGHT_X_MM                     (191.5f)
#define LEGACY_TOP_LEFT_X_MM                      (0.0f)
#define LEGACY_BOTTOM_LEFT_Y_MM                   (-10.0f)
#define LEGACY_BOTTOM_RIGHT_Y_MM                  (-24.0f)
#define LEGACY_TOP_RIGHT_Y_MM                     (231.0f)
#define LEGACY_TOP_LEFT_Y_MM                      (230.0f)

/* Inverse of the measured legacy four-point projective map. */
#define LEGACY_MAP_I00                            (0.612747360342f)
#define LEGACY_MAP_I01                            (-0.780222332711f)
#define LEGACY_MAP_I02                            (333.928440000f)
#define LEGACY_MAP_I10                            (0.763264696327f)
#define LEGACY_MAP_I11                            (0.586876702962f)
#define LEGACY_MAP_I12                            (-87.111624000f)
#define LEGACY_MAP_I20                            (-0.0000919330667873f)
#define LEGACY_MAP_I21                            (-0.000162807549841f)
#define LEGACY_MAP_I22                            (1.0f)
#define LEGACY_MAP_DENOMINATOR_MIN                (0.001f)

typedef struct {
    float command_x_mm;
    float command_y_mm;
    float actual_x_mm;
    float actual_y_mm;
} puzzle_mesh_node_t;

typedef struct {
    uint8_t node0;
    uint8_t node1;
    uint8_t node2;
} puzzle_mesh_triangle_t;

/*
 * V32 measured output mesh, recovered from the uncut A4 photograph after
 * perspective rectification. Coordinates are relative to the P4 dot, with
 * X+ right and Y+ down.
 *
 * The 24th measured node at command (0, 243) landed outside the paper, but it
 * is retained only as a calibration observation. The missing command
 * (199, 243) is never invented. The public boundary below Y=180 therefore
 * narrows to a 120 mm bottom edge, X=40..160 at Y=243.
 */
static const puzzle_mesh_node_t s_mesh_nodes[PUZZLE_MESH_NODE_COUNT] = {
    {0.0f,   0.0f,   0.000f,    0.000f},
    {50.0f,  0.0f,  48.361f,    6.730f},
    {100.0f, 0.0f,  98.388f,    8.970f},
    {150.0f, 0.0f, 147.517f,    9.205f},
    {199.0f, 0.0f, 197.075f,    4.025f},

    {0.0f,   60.0f,   2.814f,  52.362f},
    {50.0f,  60.0f,  48.173f,  59.421f},
    {100.0f, 60.0f,  96.720f,  63.069f},
    {150.0f, 60.0f, 146.275f,  64.213f},
    {199.0f, 60.0f, 196.560f,  62.579f},

    {0.0f,   120.0f,   2.566f, 110.983f},
    {50.0f,  120.0f,  44.760f, 116.528f},
    {100.0f, 120.0f,  93.230f, 121.145f},
    {150.0f, 120.0f, 142.691f, 124.223f},
    {199.0f, 120.0f, 194.116f, 124.161f},

    {0.0f,   180.0f,  -5.656f, 170.857f},
    {50.0f,  180.0f,  36.755f, 175.947f},
    {100.0f, 180.0f,  86.070f, 182.739f},
    {150.0f, 180.0f, 135.674f, 187.974f},
    {199.0f, 180.0f, 188.095f, 189.613f},

    {0.0f,   243.0f, -17.091f, 237.255f},
    {50.0f,  243.0f,  28.387f, 242.901f},
    {100.0f, 243.0f,  79.285f, 251.397f},
    {150.0f, 243.0f, 130.882f, 257.306f}
};

static const puzzle_mesh_triangle_t
    s_mesh_triangles[PUZZLE_MESH_TRIANGLE_COUNT] = {
    {0u, 1u, 5u},   {1u, 6u, 5u},
    {1u, 2u, 6u},   {2u, 7u, 6u},
    {2u, 3u, 7u},   {3u, 8u, 7u},
    {3u, 4u, 8u},   {4u, 9u, 8u},

    {5u, 6u, 10u},  {6u, 11u, 10u},
    {6u, 7u, 11u},  {7u, 12u, 11u},
    {7u, 8u, 12u},  {8u, 13u, 12u},
    {8u, 9u, 13u},  {9u, 14u, 13u},

    {10u, 11u, 15u}, {11u, 16u, 15u},
    {11u, 12u, 16u}, {12u, 17u, 16u},
    {12u, 13u, 17u}, {13u, 18u, 17u},
    {13u, 14u, 18u}, {14u, 19u, 18u},

    {15u, 16u, 20u}, {16u, 21u, 20u},
    {16u, 17u, 21u}, {17u, 22u, 21u},
    {17u, 18u, 22u}, {18u, 23u, 22u},
    {18u, 19u, 23u}
};

static bool App_PuzzleFrame_Barycentric(
    float point_x_mm,
    float point_y_mm,
    float node0_x_mm,
    float node0_y_mm,
    float node1_x_mm,
    float node1_y_mm,
    float node2_x_mm,
    float node2_y_mm,
    float *weight0,
    float *weight1,
    float *weight2)
{
    float determinant;

    if ((weight0 == NULL) || (weight1 == NULL) || (weight2 == NULL)) {
        return false;
    }

    determinant =
        (node1_y_mm - node2_y_mm) * (node0_x_mm - node2_x_mm) +
        (node2_x_mm - node1_x_mm) * (node0_y_mm - node2_y_mm);
    if (fabsf(determinant) < PUZZLE_MESH_DETERMINANT_MIN) {
        return false;
    }

    *weight0 =
        ((node1_y_mm - node2_y_mm) * (point_x_mm - node2_x_mm) +
         (node2_x_mm - node1_x_mm) * (point_y_mm - node2_y_mm)) /
        determinant;
    *weight1 =
        ((node2_y_mm - node0_y_mm) * (point_x_mm - node2_x_mm) +
         (node0_x_mm - node2_x_mm) * (point_y_mm - node2_y_mm)) /
        determinant;
    *weight2 = 1.0f - *weight0 - *weight1;

    return isfinite(*weight0) && isfinite(*weight1) &&
           isfinite(*weight2);
}

static bool App_PuzzleFrame_Triangle_Weights(
    uint32_t triangle_index,
    float point_x_mm,
    float point_y_mm,
    bool use_actual_coordinates,
    float *weight0,
    float *weight1,
    float *weight2)
{
    const puzzle_mesh_triangle_t *triangle;
    const puzzle_mesh_node_t *node0;
    const puzzle_mesh_node_t *node1;
    const puzzle_mesh_node_t *node2;

    if (triangle_index >= PUZZLE_MESH_TRIANGLE_COUNT) {
        return false;
    }

    triangle = &s_mesh_triangles[triangle_index];
    node0 = &s_mesh_nodes[triangle->node0];
    node1 = &s_mesh_nodes[triangle->node1];
    node2 = &s_mesh_nodes[triangle->node2];

    return App_PuzzleFrame_Barycentric(
        point_x_mm,
        point_y_mm,
        use_actual_coordinates ? node0->actual_x_mm :
                                 node0->command_x_mm,
        use_actual_coordinates ? node0->actual_y_mm :
                                 node0->command_y_mm,
        use_actual_coordinates ? node1->actual_x_mm :
                                 node1->command_x_mm,
        use_actual_coordinates ? node1->actual_y_mm :
                                 node1->command_y_mm,
        use_actual_coordinates ? node2->actual_x_mm :
                                 node2->command_x_mm,
        use_actual_coordinates ? node2->actual_y_mm :
                                 node2->command_y_mm,
        weight0,
        weight1,
        weight2);
}

/*
 * V37 four-row physical alignment.
 *
 * With V36, the right endpoint was higher than the left endpoint by:
 *   Y=0:   2.0 mm
 *   Y=50:  3.5 mm
 *   Y=100: 1.5 mm
 *   Y=145: 4.2 mm
 *
 * V35/V36 established the empirical software sign: reducing mesh-Y
 * precompensation moves the physical right endpoint downward. Therefore the
 * V37 right-edge values equal V36's values minus those measured residuals:
 *   V36 at Y=0/50/100/145: +6.000/+3.931/+1.862/0.000 mm
 *   V37 at Y=0/50/100/145: +4.000/+0.431/+0.362/-4.200 mm
 *
 * The correction is zero at X=0 and reaches the tabulated value at X=199.
 * It is piecewise linear in Y. A final node at Y=180 returns it continuously
 * to zero before the lower trapezoid region.
 */
static const float
    s_right_edge_correction_y_mm[PUZZLE_RIGHT_EDGE_CORRECTION_NODE_COUNT] = {
    0.0f, 50.0f, 100.0f, 145.0f, 180.0f
};

static const float
    s_right_edge_correction_mm[PUZZLE_RIGHT_EDGE_CORRECTION_NODE_COUNT] = {
    4.0f,
    0.43103448f,
    0.36206897f,
    -4.2f,
    0.0f
};

static float App_PuzzleFrame_Right_Edge_Y_Precompensation(
    float paper_x_mm,
    float paper_y_mm)
{
    uint32_t index;
    float x_blend;
    float right_edge_correction_mm;

    x_blend = paper_x_mm / APP_PUZZLE_PAPER_WIDTH_MM;
    if (x_blend < 0.0f) {
        x_blend = 0.0f;
    } else if (x_blend > 1.0f) {
        x_blend = 1.0f;
    }

    if (paper_y_mm <= s_right_edge_correction_y_mm[0]) {
        right_edge_correction_mm = s_right_edge_correction_mm[0];
    } else if (paper_y_mm >=
               s_right_edge_correction_y_mm[
                   PUZZLE_RIGHT_EDGE_CORRECTION_NODE_COUNT - 1u]) {
        right_edge_correction_mm = 0.0f;
    } else {
        right_edge_correction_mm = 0.0f;
        for (index = 0u;
             index + 1u < PUZZLE_RIGHT_EDGE_CORRECTION_NODE_COUNT;
             index++) {
            float y0 = s_right_edge_correction_y_mm[index];
            float y1 = s_right_edge_correction_y_mm[index + 1u];

            if (paper_y_mm <= y1) {
                float ratio = (paper_y_mm - y0) / (y1 - y0);
                right_edge_correction_mm =
                    s_right_edge_correction_mm[index] +
                    (s_right_edge_correction_mm[index + 1u] -
                     s_right_edge_correction_mm[index]) * ratio;
                break;
            }
        }
    }

    return right_edge_correction_mm * x_blend;
}

static bool App_PuzzleFrame_Invert_Measured_Mesh(
    float desired_x_mm,
    float desired_y_mm,
    float *calibration_input_x_mm,
    float *calibration_input_y_mm)
{
    uint32_t triangle_index;
    uint32_t selected_triangle = PUZZLE_MESH_TRIANGLE_COUNT;
    float weight0 = 0.0f;
    float weight1 = 0.0f;
    float weight2 = 0.0f;
    const puzzle_mesh_triangle_t *triangle;
    const puzzle_mesh_node_t *node0;
    const puzzle_mesh_node_t *node1;
    const puzzle_mesh_node_t *node2;

    if ((calibration_input_x_mm == NULL) ||
        (calibration_input_y_mm == NULL)) {
        return false;
    }

    /*
     * Prefer a triangle containing the desired point in measured space.
     * This is the true inverse of the photographed forward map and keeps
     * adjacent triangle boundaries continuous.
     */
    for (triangle_index = 0u;
         triangle_index < PUZZLE_MESH_TRIANGLE_COUNT;
         triangle_index++) {
        if (App_PuzzleFrame_Triangle_Weights(
                triangle_index,
                desired_x_mm,
                desired_y_mm,
                true,
                &weight0,
                &weight1,
                &weight2) &&
            (weight0 >= -PUZZLE_MESH_INSIDE_EPS) &&
            (weight1 >= -PUZZLE_MESH_INSIDE_EPS) &&
            (weight2 >= -PUZZLE_MESH_INSIDE_EPS)) {
            selected_triangle = triangle_index;
            break;
        }
    }

    /*
     * Paper-edge targets can lie just outside the photographed measured
     * hull. Fall back to the command-space triangle for bounded
     * extrapolation. The only public point beyond the measured bottom mesh
     * is the right taper X=150..160, which uses the last measured triangle.
     */
    if (selected_triangle == PUZZLE_MESH_TRIANGLE_COUNT) {
        for (triangle_index = 0u;
             triangle_index < PUZZLE_MESH_TRIANGLE_COUNT;
             triangle_index++) {
            if (App_PuzzleFrame_Triangle_Weights(
                    triangle_index,
                    desired_x_mm,
                    desired_y_mm,
                    false,
                    &weight0,
                    &weight1,
                    &weight2) &&
                (weight0 >= -PUZZLE_MESH_INSIDE_EPS) &&
                (weight1 >= -PUZZLE_MESH_INSIDE_EPS) &&
                (weight2 >= -PUZZLE_MESH_INSIDE_EPS)) {
                selected_triangle = triangle_index;
                break;
            }
        }
    }

    if ((selected_triangle == PUZZLE_MESH_TRIANGLE_COUNT) &&
        (desired_y_mm > APP_PUZZLE_TRAPEZOID_SHOULDER_Y_MM) &&
        (desired_x_mm >= 150.0f)) {
        selected_triangle = PUZZLE_MESH_TRIANGLE_COUNT - 1u;
    }
    if (selected_triangle == PUZZLE_MESH_TRIANGLE_COUNT) {
        return false;
    }

    if (!App_PuzzleFrame_Triangle_Weights(
            selected_triangle,
            desired_x_mm,
            desired_y_mm,
            true,
            &weight0,
            &weight1,
            &weight2) ||
        (weight0 < PUZZLE_MESH_BARYCENTRIC_MIN) ||
        (weight0 > PUZZLE_MESH_BARYCENTRIC_MAX) ||
        (weight1 < PUZZLE_MESH_BARYCENTRIC_MIN) ||
        (weight1 > PUZZLE_MESH_BARYCENTRIC_MAX) ||
        (weight2 < PUZZLE_MESH_BARYCENTRIC_MIN) ||
        (weight2 > PUZZLE_MESH_BARYCENTRIC_MAX)) {
        return false;
    }

    triangle = &s_mesh_triangles[selected_triangle];
    node0 = &s_mesh_nodes[triangle->node0];
    node1 = &s_mesh_nodes[triangle->node1];
    node2 = &s_mesh_nodes[triangle->node2];
    *calibration_input_x_mm =
        weight0 * node0->command_x_mm +
        weight1 * node1->command_x_mm +
        weight2 * node2->command_x_mm;
    *calibration_input_y_mm =
        weight0 * node0->command_y_mm +
        weight1 * node1->command_y_mm +
        weight2 * node2->command_y_mm;

    return isfinite(*calibration_input_x_mm) &&
           isfinite(*calibration_input_y_mm);
}

/*
 * Measured V31 forward X error:
 *   command 100 -> actual about 98
 *
 * Invert the two measured spans and retain both established boundaries:
 *   actual 0..98   came from command 0..100
 *   actual 98..199 came from command 100..199
 */
static float App_PuzzleFrame_Map_Paper_X(float paper_x_mm)
{
    if (paper_x_mm <= 98.0f) {
        return paper_x_mm * (100.0f / 98.0f);
    }
    return 100.0f +
           (paper_x_mm - 98.0f) * (99.0f / 101.0f);
}

/*
 * Measured V30 forward error:
 *   command 50 -> actual 57
 *   command 70 -> actual about 80
 *   command 140 -> actual 150
 *
 * This is the inverse, piecewise-linear command map. Paper Y=0 and Y=243
 * remain fixed so the already aligned top and bottom corners are preserved.
 */
static float App_PuzzleFrame_Map_Paper_Y(float paper_y_mm)
{
    if (paper_y_mm <= 57.0f) {
        return paper_y_mm * (50.0f / 57.0f);
    }
    if (paper_y_mm <= 80.0f) {
        return 50.0f +
               (paper_y_mm - 57.0f) * (20.0f / 23.0f);
    }
    if (paper_y_mm <= 150.0f) {
        return 70.0f + (paper_y_mm - 80.0f);
    }
    return 140.0f +
           (paper_y_mm - 150.0f) * (103.0f / 93.0f);
}

bool App_PuzzleFrame_Is_In_Bounds(float paper_x_mm, float paper_y_mm)
{
    float minimum_x_mm = 0.0f;
    float maximum_x_mm = APP_PUZZLE_PAPER_WIDTH_MM;

    if (!isfinite(paper_x_mm) || !isfinite(paper_y_mm) ||
        (paper_y_mm < -PUZZLE_FRAME_BOUND_EPS_MM) ||
        (paper_y_mm >
         APP_PUZZLE_PAPER_HEIGHT_MM + PUZZLE_FRAME_BOUND_EPS_MM)) {
        return false;
    }

    if (paper_y_mm > APP_PUZZLE_TRAPEZOID_SHOULDER_Y_MM) {
        float taper =
            (paper_y_mm - APP_PUZZLE_TRAPEZOID_SHOULDER_Y_MM) /
            (APP_PUZZLE_PAPER_HEIGHT_MM -
             APP_PUZZLE_TRAPEZOID_SHOULDER_Y_MM);
        minimum_x_mm =
            taper * APP_PUZZLE_TRAPEZOID_BOTTOM_LEFT_X_MM;
        maximum_x_mm =
            APP_PUZZLE_PAPER_WIDTH_MM +
            taper *
            (APP_PUZZLE_TRAPEZOID_BOTTOM_RIGHT_X_MM -
             APP_PUZZLE_PAPER_WIDTH_MM);
    }

    return (paper_x_mm >=
            minimum_x_mm - PUZZLE_FRAME_BOUND_EPS_MM) &&
           (paper_x_mm <=
            maximum_x_mm + PUZZLE_FRAME_BOUND_EPS_MM);
}

bool App_PuzzleFrame_To_User(float paper_x_mm, float paper_y_mm,
                             app_puzzle_frame_map_t *map)
{
    float mesh_target_y_mm;
    float x_ratio;
    float y_ratio;
    float left_x_mm;
    float right_x_mm;
    float bottom_y_mm;
    float top_y_mm;
    float denominator;

    if ((map == NULL) ||
        !App_PuzzleFrame_Is_In_Bounds(paper_x_mm, paper_y_mm)) {
        return false;
    }

    map->paper_x_mm = paper_x_mm;
    map->paper_y_mm = paper_y_mm;
    mesh_target_y_mm =
        paper_y_mm +
        App_PuzzleFrame_Right_Edge_Y_Precompensation(
            paper_x_mm, paper_y_mm);
    if (!App_PuzzleFrame_Invert_Measured_Mesh(
            paper_x_mm,
            mesh_target_y_mm,
            &map->calibration_input_x_mm,
            &map->calibration_input_y_mm)) {
        return false;
    }
    map->mapped_paper_x_mm =
        App_PuzzleFrame_Map_Paper_X(
            map->calibration_input_x_mm);
    map->mapped_paper_y_mm =
        App_PuzzleFrame_Map_Paper_Y(
            map->calibration_input_y_mm);
    map->legacy_work_x_mm = map->mapped_paper_x_mm;
    map->legacy_work_y_mm =
        PUZZLE_CALIBRATION_HEIGHT_MM -
        map->mapped_paper_y_mm;

    x_ratio =
        map->legacy_work_x_mm / PUZZLE_CALIBRATION_WIDTH_MM;
    y_ratio =
        map->legacy_work_y_mm / PUZZLE_CALIBRATION_HEIGHT_MM;
    left_x_mm = LEGACY_BOTTOM_LEFT_X_MM +
                (LEGACY_TOP_LEFT_X_MM -
                 LEGACY_BOTTOM_LEFT_X_MM) * y_ratio;
    right_x_mm = LEGACY_BOTTOM_RIGHT_X_MM +
                 (LEGACY_TOP_RIGHT_X_MM -
                  LEGACY_BOTTOM_RIGHT_X_MM) * y_ratio;
    bottom_y_mm = LEGACY_BOTTOM_LEFT_Y_MM +
                  (LEGACY_BOTTOM_RIGHT_Y_MM -
                   LEGACY_BOTTOM_LEFT_Y_MM) * x_ratio;
    top_y_mm = LEGACY_TOP_LEFT_Y_MM +
               (LEGACY_TOP_RIGHT_Y_MM -
                LEGACY_TOP_LEFT_Y_MM) * x_ratio;

    map->calibrated_physical_x_mm =
        left_x_mm + (right_x_mm - left_x_mm) * x_ratio;
    map->calibrated_physical_y_mm =
        bottom_y_mm +
        (top_y_mm - bottom_y_mm) * y_ratio;

    denominator =
        LEGACY_MAP_I20 * map->calibrated_physical_x_mm +
        LEGACY_MAP_I21 * map->calibrated_physical_y_mm +
        LEGACY_MAP_I22;
    if (fabsf(denominator) < LEGACY_MAP_DENOMINATOR_MIN) {
        return false;
    }

    map->user_x_mm =
        (LEGACY_MAP_I00 * map->calibrated_physical_x_mm +
         LEGACY_MAP_I01 * map->calibrated_physical_y_mm +
         LEGACY_MAP_I02) / denominator;
    map->user_y_mm =
        (LEGACY_MAP_I10 * map->calibrated_physical_x_mm +
         LEGACY_MAP_I11 * map->calibrated_physical_y_mm +
         LEGACY_MAP_I12) / denominator;

    return isfinite(map->user_x_mm) && isfinite(map->user_y_mm);
}
