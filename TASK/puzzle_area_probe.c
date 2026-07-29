/**
 * @file    puzzle_area_probe.c
 * @brief   Calibrated puzzle-area marking and serial coordinate simulation.
 *
 * KEY2 retains the four-corner and divider test. UART1 also accepts MOVE/DOT
 * coordinates in a clean 181.5 x 240 mm work frame. The same line protocol is
 * used by a serial assistant now and by the K230 vision program later.
 */
#include "puzzle_area_probe.h"
#include "app_servo.h"
#include "app_stepper.h"
#include "app_writer_motion.h"
#include "app_writer_paper_map.h"
#include "comm_vision_uart.h"
#include "gcode_serial.h"
#include "elog.h"
#include <ctype.h>
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PUZZLE_AREA_UNIQUE_CORNER_COUNT       (4u)
#define PUZZLE_AREA_VISIT_COUNT               (5u)
#define PUZZLE_AREA_DWELL_MS                  (500u)
#define PUZZLE_AREA_MARK_DOWN_HOLD_MS         (700u)
#define PUZZLE_AREA_MARK_UP_SETTLE_MS         (700u)
#define PUZZLE_AREA_LINE_DOWN_HOLD_MS         (700u)
#define PUZZLE_AREA_LINE_UP_SETTLE_MS         (700u)
#define PUZZLE_AREA_APPROACH_FEED_MM_MIN      (300.0f)
#define PUZZLE_AREA_MOVE_FEED_MM_MIN          (900.0f)
#define PUZZLE_AREA_LINE_DRAW_FEED_MM_MIN     (300.0f)
#define PUZZLE_AREA_SERIAL_MOVE_FEED_MM_MIN   (900.0f)
#define PUZZLE_AREA_MOVE_LEG_MAX_MM           (120.0f)
#define PUZZLE_AREA_POSITION_EPS_MM           (0.20f)
#define PUZZLE_AREA_REPLY_MAX                 (320u)
#define PUZZLE_AREA_COMMAND_MAX               (64u)
#define PUZZLE_AREA_WIDTH_MM                  (181.5f)
#define PUZZLE_AREA_HEIGHT_MM                 (240.0f)
#define PUZZLE_AREA_BOTTOM_LOCAL_Y_MM         (-10.0f)
#define PUZZLE_AREA_RIGHT_BOTTOM_LOCAL_Y_MM   (-14.0f)
#define PUZZLE_AREA_POINT3_TOP_LOCAL_Y_MM     (233.0f)
#define PUZZLE_AREA_POINT4_TOP_LOCAL_Y_MM     (230.0f)
#define PUZZLE_AREA_LINE_LOCAL_Y_MM           (76.5f)
#define PUZZLE_AREA_LINE_FROM_P4_TOP_MM       (153.5f)
#define PUZZLE_AREA_RIGHT_PAPER_X_MM          \
    (APP_WRITER_LANDSCAPE_MAP_ORIGIN_X_MM + PUZZLE_AREA_WIDTH_MM)
#define PUZZLE_AREA_BOTTOM_PAPER_Y_MM         \
    (APP_WRITER_LANDSCAPE_MAP_ORIGIN_Y_MM + \
     PUZZLE_AREA_BOTTOM_LOCAL_Y_MM)
#define PUZZLE_AREA_RIGHT_BOTTOM_PAPER_Y_MM   \
    (APP_WRITER_LANDSCAPE_MAP_ORIGIN_Y_MM + \
     PUZZLE_AREA_RIGHT_BOTTOM_LOCAL_Y_MM)
#define PUZZLE_AREA_POINT3_TOP_PAPER_Y_MM     \
    (APP_WRITER_LANDSCAPE_MAP_ORIGIN_Y_MM + \
     PUZZLE_AREA_POINT3_TOP_LOCAL_Y_MM)
#define PUZZLE_AREA_POINT4_TOP_PAPER_Y_MM     \
    (APP_WRITER_LANDSCAPE_MAP_ORIGIN_Y_MM + \
     PUZZLE_AREA_POINT4_TOP_LOCAL_Y_MM)
#define PUZZLE_AREA_LINE_PAPER_Y_MM           \
    (APP_WRITER_LANDSCAPE_MAP_ORIGIN_Y_MM + \
     PUZZLE_AREA_LINE_LOCAL_Y_MM)

/*
 * Inverse of the measured four-point projective map.
 * Input: corrected local physical coordinate. Output: motion user coordinate.
 */
#define PUZZLE_MAP_I00                         (0.612747360342f)
#define PUZZLE_MAP_I01                         (-0.780222332711f)
#define PUZZLE_MAP_I02                         (333.928440000f)
#define PUZZLE_MAP_I10                         (0.763264696327f)
#define PUZZLE_MAP_I11                         (0.586876702962f)
#define PUZZLE_MAP_I12                         (-87.111624000f)
#define PUZZLE_MAP_I20                         (-0.0000919330667873f)
#define PUZZLE_MAP_I21                         (-0.000162807549841f)
#define PUZZLE_MAP_I22                         (1.0f)
#define PUZZLE_MAP_DENOMINATOR_MIN             (0.001f)

typedef struct {
    const char *name;
    float paper_x_mm;
    float paper_y_mm;
    float user_x_mm;
    float user_y_mm;
} puzzle_area_point_t;

/*
 * Four-point local projective correction, 2026-07-29.
 *
 * The pre-key kinematic baseline commanded a local 160 x 160 mm square and
 * produced these measured points relative to the first point:
 *   P1=(0,0), P2=(156,3), P3=(141,161), P4=(-11,157.5) mm.
 *
 * A projective map was fitted from the four original user targets to those
 * measured positions. After the 210 mm side-length trial, the four physical
 * points were measured relative to P1 as:
 *   P1=(0,0), P2=(178,11.3), P3=(185,218), P4=(0,205) mm.
 *
 * A new projective map is fitted from the V15 direct user targets to those
 * measurements and inverted at the strict rectangle:
 *   P1=(0,0), P2=(181.5,0), P3=(181.5,210), P4=(0,210) mm.
 *
 * The lower P1/P2 points remain at the V17 Y=-10 mm edge. This trial moves
 * the aligned upper P3/P4 points another 20 mm up:
 *   P1=(0,-10), P2=(181.5,-10),
 *   P3=(181.5,230), P4=(0,230) mm.
 *
 * V18 measurement found P2 3.3 mm above P1 and the P2/P3 side about 4 mm
 * short. Move only P2 another 4 mm down:
 *   P1=(0,-10), P2=(181.5,-14),
 *   P3=(181.5,230), P4=(0,230) mm.
 *
 * The next measured correction moves only P3 another 3 mm up:
 *   P3=(181.5,233) mm.
 *
 * P1/P2/P4 remain unchanged. KEY3 remains at the previous reference origin.
 *
 * The fifth visit repeats P1 so the pen-up patrol closes the rectangle.
 */
static const puzzle_area_point_t s_points[PUZZLE_AREA_VISIT_COUNT] = {
    {"LOWER_LEFT",  APP_WRITER_PAPER_X_MIN_MM,
                    PUZZLE_AREA_BOTTOM_PAPER_Y_MM,
                    341.175204f, -92.829258f},
    {"LOWER_RIGHT", PUZZLE_AREA_RIGHT_PAPER_X_MM,
                    PUZZLE_AREA_RIGHT_BOTTOM_PAPER_Y_MM,
                    462.731562f, 43.836172f},
    {"UPPER_RIGHT", PUZZLE_AREA_RIGHT_PAPER_X_MM,
                    PUZZLE_AREA_POINT3_TOP_PAPER_Y_MM,
                    278.565535f, 199.034454f},
    {"UPPER_LEFT",  APP_WRITER_PAPER_X_MIN_MM,
                    PUZZLE_AREA_POINT4_TOP_PAPER_Y_MM,
                    160.486852f, 49.732280f},
    {"CLOSE_LOWER_LEFT", APP_WRITER_PAPER_X_MIN_MM,
                         PUZZLE_AREA_BOTTOM_PAPER_Y_MM,
                         341.175204f, -92.829258f},
};

/*
 * The divider was first placed at Y=31.5 mm, then moved 15 mm up to
 * Y=46.5 mm. This revision moves it another 30 mm up:
 * physical line Y=76.5 mm, X=0..181.5 mm.
 *
 * These direct user targets are the inverse of the same measured projective
 * map used for the four calibrated corners.
 */
static const puzzle_area_point_t s_line_start = {
    "LINE_LEFT",
    APP_WRITER_PAPER_X_MIN_MM,
    PUZZLE_AREA_LINE_PAPER_Y_MM,
    277.700125f,
    -42.747973f
};

static const puzzle_area_point_t s_line_end = {
    "LINE_RIGHT",
    PUZZLE_AREA_RIGHT_PAPER_X_MM,
    PUZZLE_AREA_LINE_PAPER_Y_MM,
    397.024625f,
    99.207969f
};

extern volatile uint32_t s_sys_tick;

static puzzle_area_probe_state_t s_state =
    PUZZLE_AREA_PROBE_STATE_IDLE;
static uint32_t s_point_index = 0u;
static uint32_t s_mark_count = 0u;
static uint32_t s_dwell_start_ms = 0u;
static uint32_t s_mark_state_start_ms = 0u;
static float s_target_user_x_mm = 0.0f;
static float s_target_user_y_mm = 0.0f;
static bool s_tool_down = false;
static bool s_line_active = false;
static bool s_line_drawing = false;
static bool s_serial_dot = false;
static float s_serial_work_x_mm = 0.0f;
static float s_serial_work_y_mm = 0.0f;
static float s_serial_physical_x_mm = 0.0f;
static float s_serial_physical_y_mm = 0.0f;

static int32_t PuzzleAreaProbe_Scale_100(float value)
{
    return (int32_t)((value >= 0.0f) ?
                     (value * 100.0f + 0.5f) :
                     (value * 100.0f - 0.5f));
}

static float PuzzleAreaProbe_Landscape_X(
    const puzzle_area_point_t *point)
{
    return point->paper_x_mm -
           APP_WRITER_LANDSCAPE_MAP_ORIGIN_X_MM;
}

static float PuzzleAreaProbe_Landscape_Y(
    const puzzle_area_point_t *point)
{
    return point->paper_y_mm -
           APP_WRITER_LANDSCAPE_MAP_ORIGIN_Y_MM;
}

static const char *PuzzleAreaProbe_State_Name(void)
{
    switch (s_state) {
        case PUZZLE_AREA_PROBE_STATE_IDLE:
            return "IDLE";
        case PUZZLE_AREA_PROBE_STATE_WAIT_TRIGGER:
            return "WAIT_TRIGGER";
        case PUZZLE_AREA_PROBE_STATE_MOVING:
            return "MOVING";
        case PUZZLE_AREA_PROBE_STATE_MARK_DOWN_HOLD:
            return "MARK_DOWN_HOLD";
        case PUZZLE_AREA_PROBE_STATE_MARK_UP_SETTLE:
            return "MARK_UP_SETTLE";
        case PUZZLE_AREA_PROBE_STATE_DWELL:
            return "DWELL";
        case PUZZLE_AREA_PROBE_STATE_LINE_DOWN_HOLD:
            return "LINE_DOWN_HOLD";
        case PUZZLE_AREA_PROBE_STATE_LINE_UP_SETTLE:
            return "LINE_UP_SETTLE";
        case PUZZLE_AREA_PROBE_STATE_SERIAL_MOVING:
            return "SERIAL_MOVING";
        case PUZZLE_AREA_PROBE_STATE_SERIAL_DOT_DOWN_HOLD:
            return "SERIAL_DOT_DOWN_HOLD";
        case PUZZLE_AREA_PROBE_STATE_SERIAL_DOT_UP_SETTLE:
            return "SERIAL_DOT_UP_SETTLE";
        case PUZZLE_AREA_PROBE_STATE_DONE:
            return "DONE";
        case PUZZLE_AREA_PROBE_STATE_STOPPED:
            return "STOPPED";
        case PUZZLE_AREA_PROBE_STATE_ERROR:
            return "ERROR";
        default:
            return "UNKNOWN";
    }
}

static bool PuzzleAreaProbe_Limits_Clear(void)
{
    return !App_Stepper_Stage1_IsLimitHit() &&
           !App_Stepper_Stage2_IsLimitHit();
}

static void PuzzleAreaProbe_Sendf(const char *format, ...)
{
    char reply[PUZZLE_AREA_REPLY_MAX];
    va_list args;
    int count;

    va_start(args, format);
    count = vsnprintf(reply, sizeof(reply), format, args);
    va_end(args);
    if (count <= 0) {
        return;
    }
    if ((uint32_t)count >= sizeof(reply)) {
        count = (int)(sizeof(reply) - 1u);
    }
    App_Vision_UART_Send((const uint8_t *)reply, (uint16_t)count);
}

static bool PuzzleAreaProbe_Point_To_User(
    const puzzle_area_point_t *point,
    float *user_x_mm,
    float *user_y_mm)
{
    if ((point == NULL) || (user_x_mm == NULL) || (user_y_mm == NULL)) {
        return false;
    }

    *user_x_mm = point->user_x_mm;
    *user_y_mm = point->user_y_mm;
    return true;
}

/*
 * Work coordinates deliberately remain rectangular for the serial assistant
 * and K230: (0,0) is P1 and (181.5,240) is P3. The measured P2-down/P3-up
 * corrections are blended into the physical Y coordinate before applying the
 * projective inverse, so the sender does not need to know about them.
 */
static bool PuzzleAreaProbe_Work_To_User(
    float work_x_mm,
    float work_y_mm,
    float *physical_x_mm,
    float *physical_y_mm,
    float *user_x_mm,
    float *user_y_mm)
{
    float x_ratio;
    float bottom_y_mm;
    float top_y_mm;
    float physical_y;
    float denominator;

    if ((physical_x_mm == NULL) || (physical_y_mm == NULL) ||
        (user_x_mm == NULL) || (user_y_mm == NULL) ||
        !isfinite(work_x_mm) || !isfinite(work_y_mm) ||
        (work_x_mm < 0.0f) || (work_x_mm > PUZZLE_AREA_WIDTH_MM) ||
        (work_y_mm < 0.0f) || (work_y_mm > PUZZLE_AREA_HEIGHT_MM)) {
        return false;
    }

    x_ratio = work_x_mm / PUZZLE_AREA_WIDTH_MM;
    bottom_y_mm = PUZZLE_AREA_BOTTOM_LOCAL_Y_MM +
                  (PUZZLE_AREA_RIGHT_BOTTOM_LOCAL_Y_MM -
                   PUZZLE_AREA_BOTTOM_LOCAL_Y_MM) * x_ratio;
    top_y_mm = PUZZLE_AREA_POINT4_TOP_LOCAL_Y_MM +
               (PUZZLE_AREA_POINT3_TOP_LOCAL_Y_MM -
                PUZZLE_AREA_POINT4_TOP_LOCAL_Y_MM) * x_ratio;
    physical_y = bottom_y_mm +
                 (top_y_mm - bottom_y_mm) *
                 (work_y_mm / PUZZLE_AREA_HEIGHT_MM);
    denominator = PUZZLE_MAP_I20 * work_x_mm +
                  PUZZLE_MAP_I21 * physical_y +
                  PUZZLE_MAP_I22;
    if (fabsf(denominator) < PUZZLE_MAP_DENOMINATOR_MIN) {
        return false;
    }

    *physical_x_mm = work_x_mm;
    *physical_y_mm = physical_y;
    *user_x_mm = (PUZZLE_MAP_I00 * work_x_mm +
                  PUZZLE_MAP_I01 * physical_y +
                  PUZZLE_MAP_I02) / denominator;
    *user_y_mm = (PUZZLE_MAP_I10 * work_x_mm +
                  PUZZLE_MAP_I11 * physical_y +
                  PUZZLE_MAP_I12) / denominator;
    return isfinite(*user_x_mm) && isfinite(*user_y_mm);
}

static bool PuzzleAreaProbe_Is_At_Target(void)
{
    const app_writer_pose_t *pose = WriterMotion_Get_Pose();

    return (fabsf(pose->user_point.x_mm - s_target_user_x_mm) <=
            PUZZLE_AREA_POSITION_EPS_MM) &&
           (fabsf(pose->user_point.y_mm - s_target_user_y_mm) <=
            PUZZLE_AREA_POSITION_EPS_MM);
}

static void PuzzleAreaProbe_Fail(const char *reason)
{
    App_Servo_Pen_Up();
    s_tool_down = false;
    s_line_active = false;
    s_line_drawing = false;
    WriterMotion_Emergency_Stop();
    s_state = PUZZLE_AREA_PROBE_STATE_ERROR;
    elog_e("PUZ_AREA",
           "[PUZ_AREA] result=ERROR reason=%s visit=%u/%u "
           "lim1=%d lim2=%d tool=UP magnet=NOT_CONTROLLED rehome=1",
           reason,
           (s_point_index < PUZZLE_AREA_VISIT_COUNT) ?
               (s_point_index + 1u) : PUZZLE_AREA_VISIT_COUNT,
           PUZZLE_AREA_VISIT_COUNT,
           App_Stepper_Stage1_IsLimitHit(),
           App_Stepper_Stage2_IsLimitHit());
    PuzzleAreaProbe_Sendf(
        "error:%s id=%s state=ERROR visit=%u/%u "
        "tool=UP magnet=NOT_CONTROLLED rehome=1\r\n",
        reason,
        PUZZLE_AREA_PROBE_BUILD_ID,
        (s_point_index < PUZZLE_AREA_VISIT_COUNT) ?
            (s_point_index + 1u) : PUZZLE_AREA_VISIT_COUNT,
        PUZZLE_AREA_VISIT_COUNT);
}

static void PuzzleAreaProbe_Stop(void)
{
    App_Servo_Pen_Up();
    s_tool_down = false;
    s_line_active = false;
    s_line_drawing = false;
    WriterMotion_Emergency_Stop();
    s_state = PUZZLE_AREA_PROBE_STATE_STOPPED;
    elog_w("PUZ_AREA",
           "[PUZ_AREA] result=STOPPED visit=%u/%u "
           "tool=UP magnet=NOT_CONTROLLED rehome=1",
           (s_point_index < PUZZLE_AREA_VISIT_COUNT) ?
               (s_point_index + 1u) : PUZZLE_AREA_VISIT_COUNT,
           PUZZLE_AREA_VISIT_COUNT);
    PuzzleAreaProbe_Sendf(
        "ok STOPPED id=%s visit=%u/%u "
        "tool=UP magnet=NOT_CONTROLLED rehome=1\r\n",
        PUZZLE_AREA_PROBE_BUILD_ID,
        (s_point_index < PUZZLE_AREA_VISIT_COUNT) ?
            (s_point_index + 1u) : PUZZLE_AREA_VISIT_COUNT,
        PUZZLE_AREA_VISIT_COUNT);
}

static bool PuzzleAreaProbe_Load_Target(void)
{
    const puzzle_area_point_t *point;

    if (s_point_index >= PUZZLE_AREA_VISIT_COUNT) {
        return false;
    }
    point = &s_points[s_point_index];
    if (!PuzzleAreaProbe_Point_To_User(
            point, &s_target_user_x_mm, &s_target_user_y_mm)) {
        return false;
    }

    elog_i("PUZ_AREA",
           "[PUZ_AREA] action=TARGET visit=%u/%u unique_corner=%u/%u "
           "name=%s paper_x100=%d paper_y100=%d "
           "user_x100=%d user_y100=%d quality=CALIBRATED "
           "tool=UP magnet=NOT_CONTROLLED",
           s_point_index + 1u,
           PUZZLE_AREA_VISIT_COUNT,
           (s_point_index < PUZZLE_AREA_UNIQUE_CORNER_COUNT) ?
               (s_point_index + 1u) : 1u,
           PUZZLE_AREA_UNIQUE_CORNER_COUNT,
           point->name,
           PuzzleAreaProbe_Scale_100(
               PuzzleAreaProbe_Landscape_X(point)),
           PuzzleAreaProbe_Scale_100(
               PuzzleAreaProbe_Landscape_Y(point)),
           PuzzleAreaProbe_Scale_100(s_target_user_x_mm),
           PuzzleAreaProbe_Scale_100(s_target_user_y_mm));
    return true;
}

static bool PuzzleAreaProbe_Load_Line_Target(bool line_end)
{
    const puzzle_area_point_t *point =
        line_end ? &s_line_end : &s_line_start;

    if (!PuzzleAreaProbe_Point_To_User(
            point, &s_target_user_x_mm, &s_target_user_y_mm)) {
        return false;
    }

    elog_i("PUZ_AREA",
           "[PUZ_AREA] action=LINE_TARGET phase=%s name=%s "
           "paper_x100=%d paper_y100=%d "
           "user_x100=%d user_y100=%d tool=%s",
           line_end ? "END" : "START",
           point->name,
           PuzzleAreaProbe_Scale_100(
               PuzzleAreaProbe_Landscape_X(point)),
           PuzzleAreaProbe_Scale_100(
               PuzzleAreaProbe_Landscape_Y(point)),
           PuzzleAreaProbe_Scale_100(s_target_user_x_mm),
           PuzzleAreaProbe_Scale_100(s_target_user_y_mm),
           s_tool_down ? "DOWN" : "UP");
    return true;
}

static bool PuzzleAreaProbe_Start_Move_Leg(void)
{
    const app_writer_pose_t *pose = WriterMotion_Get_Pose();
    float feed_mm_min = (s_line_active && s_line_drawing) ?
        PUZZLE_AREA_LINE_DRAW_FEED_MM_MIN :
        ((s_point_index == 0u) ?
            PUZZLE_AREA_APPROACH_FEED_MM_MIN :
            PUZZLE_AREA_MOVE_FEED_MM_MIN);
    float delta_x = s_target_user_x_mm - pose->user_point.x_mm;
    float delta_y = s_target_user_y_mm - pose->user_point.y_mm;
    float span = fmaxf(fabsf(delta_x), fabsf(delta_y));
    float ratio = (span > PUZZLE_AREA_MOVE_LEG_MAX_MM) ?
                  (PUZZLE_AREA_MOVE_LEG_MAX_MM / span) : 1.0f;
    float leg_x = pose->user_point.x_mm + delta_x * ratio;
    float leg_y = pose->user_point.y_mm + delta_y * ratio;

    if (s_line_active && s_line_drawing) {
        App_Servo_Pen_Down();
        s_tool_down = true;
    } else {
        App_Servo_Pen_Up();
        s_tool_down = false;
    }
    if (!WriterMotion_Start_To_At_Feed(
            leg_x, leg_y, feed_mm_min)) {
        return false;
    }
    s_state = PUZZLE_AREA_PROBE_STATE_MOVING;
    return true;
}

static bool PuzzleAreaProbe_Start_Serial_Move_Leg(void)
{
    const app_writer_pose_t *pose = WriterMotion_Get_Pose();
    float delta_x = s_target_user_x_mm - pose->user_point.x_mm;
    float delta_y = s_target_user_y_mm - pose->user_point.y_mm;
    float span = fmaxf(fabsf(delta_x), fabsf(delta_y));
    float ratio = (span > PUZZLE_AREA_MOVE_LEG_MAX_MM) ?
                  (PUZZLE_AREA_MOVE_LEG_MAX_MM / span) : 1.0f;
    float leg_x = pose->user_point.x_mm + delta_x * ratio;
    float leg_y = pose->user_point.y_mm + delta_y * ratio;

    App_Servo_Pen_Up();
    s_tool_down = false;
    if (!WriterMotion_Start_To_At_Feed(
            leg_x, leg_y, PUZZLE_AREA_SERIAL_MOVE_FEED_MM_MIN)) {
        return false;
    }
    s_state = PUZZLE_AREA_PROBE_STATE_SERIAL_MOVING;
    return true;
}

static void PuzzleAreaProbe_Complete_Serial_Command(void)
{
    const app_writer_pose_t *pose = WriterMotion_Get_Pose();

    App_Servo_Pen_Up();
    s_tool_down = false;
    s_state = PUZZLE_AREA_PROBE_STATE_WAIT_TRIGGER;
    elog_i("PUZ_UART",
           "[PUZ_UART] result=DONE command=%s "
           "work_x100=%d work_y100=%d physical_x100=%d physical_y100=%d "
           "user_x100=%d user_y100=%d tool=UP",
           s_serial_dot ? "DOT" : "MOVE",
           PuzzleAreaProbe_Scale_100(s_serial_work_x_mm),
           PuzzleAreaProbe_Scale_100(s_serial_work_y_mm),
           PuzzleAreaProbe_Scale_100(s_serial_physical_x_mm),
           PuzzleAreaProbe_Scale_100(s_serial_physical_y_mm),
           PuzzleAreaProbe_Scale_100(pose->user_point.x_mm),
           PuzzleAreaProbe_Scale_100(pose->user_point.y_mm));
    PuzzleAreaProbe_Sendf(
        "ok DONE command=%s work_x100=%d work_y100=%d "
        "physical_x100=%d physical_y100=%d "
        "user_x100=%d user_y100=%d tool=UP\r\n",
        s_serial_dot ? "DOT" : "MOVE",
        PuzzleAreaProbe_Scale_100(s_serial_work_x_mm),
        PuzzleAreaProbe_Scale_100(s_serial_work_y_mm),
        PuzzleAreaProbe_Scale_100(s_serial_physical_x_mm),
        PuzzleAreaProbe_Scale_100(s_serial_physical_y_mm),
        PuzzleAreaProbe_Scale_100(pose->user_point.x_mm),
        PuzzleAreaProbe_Scale_100(pose->user_point.y_mm));
}

static bool PuzzleAreaProbe_Start_Current_Point(void)
{
    if (!PuzzleAreaProbe_Load_Target()) {
        return false;
    }
    /*
     * A repeated KEY2 run begins where the previous run ended: the lower-left
     * corner. Do not submit a zero-length motion; enter MOVING so Update()
     * immediately performs the first mark.
     */
    if (PuzzleAreaProbe_Is_At_Target()) {
        s_state = PUZZLE_AREA_PROBE_STATE_MOVING;
        return true;
    }
    return PuzzleAreaProbe_Start_Move_Leg();
}

static void PuzzleAreaProbe_Send_Status(void)
{
    const app_writer_pose_t *pose = WriterMotion_Get_Pose();
    const puzzle_area_point_t *point =
        &s_points[(s_point_index < PUZZLE_AREA_VISIT_COUNT) ?
                  s_point_index : (PUZZLE_AREA_VISIT_COUNT - 1u)];

    PuzzleAreaProbe_Sendf(
        "ok STATUS id=%s state=%s action=%s visit=%u/%u "
        "unique_corners=%u marks=%u/%u name=%s "
        "paper_x100=%d paper_y100=%d "
        "user_x100=%d user_y100=%d busy=%u lim1=%d lim2=%d "
        "serial_work_x100=%d serial_work_y100=%d "
        "serial_range_x100=0..18150 serial_range_y100=0..24000 "
        "tool=%s magnet=NOT_CONTROLLED\r\n",
        PUZZLE_AREA_PROBE_BUILD_ID,
        PuzzleAreaProbe_State_Name(),
        (s_state == PUZZLE_AREA_PROBE_STATE_WAIT_TRIGGER) ?
            "KEY2_OR_M850" :
        ((s_state == PUZZLE_AREA_PROBE_STATE_MOVING) ||
         (s_state == PUZZLE_AREA_PROBE_STATE_MARK_DOWN_HOLD) ||
         (s_state == PUZZLE_AREA_PROBE_STATE_MARK_UP_SETTLE) ||
         (s_state == PUZZLE_AREA_PROBE_STATE_LINE_DOWN_HOLD) ||
         (s_state == PUZZLE_AREA_PROBE_STATE_LINE_UP_SETTLE) ||
         (s_state == PUZZLE_AREA_PROBE_STATE_SERIAL_MOVING) ||
         (s_state == PUZZLE_AREA_PROBE_STATE_SERIAL_DOT_DOWN_HOLD) ||
         (s_state == PUZZLE_AREA_PROBE_STATE_SERIAL_DOT_UP_SETTLE) ?
            "STOP" : "NONE"),
        (s_point_index < PUZZLE_AREA_VISIT_COUNT) ?
            (s_point_index + 1u) : PUZZLE_AREA_VISIT_COUNT,
        PUZZLE_AREA_VISIT_COUNT,
        PUZZLE_AREA_UNIQUE_CORNER_COUNT,
        s_mark_count,
        PUZZLE_AREA_UNIQUE_CORNER_COUNT,
        point->name,
        PuzzleAreaProbe_Scale_100(
            PuzzleAreaProbe_Landscape_X(point)),
        PuzzleAreaProbe_Scale_100(
            PuzzleAreaProbe_Landscape_Y(point)),
        PuzzleAreaProbe_Scale_100(pose->user_point.x_mm),
        PuzzleAreaProbe_Scale_100(pose->user_point.y_mm),
        WriterMotion_Is_Busy() ? 1u : 0u,
        App_Stepper_Stage1_IsLimitHit(),
        App_Stepper_Stage2_IsLimitHit(),
        PuzzleAreaProbe_Scale_100(s_serial_work_x_mm),
        PuzzleAreaProbe_Scale_100(s_serial_work_y_mm),
        s_tool_down ? "DOWN" : "UP");
}

void PuzzleAreaProbe_Start(void)
{
    App_Servo_Pen_Up();
    WriterMotion_Init_From_Home();
    s_point_index = 0u;
    s_mark_count = 0u;
    s_dwell_start_ms = 0u;
    s_mark_state_start_ms = 0u;
    s_target_user_x_mm = 0.0f;
    s_target_user_y_mm = 0.0f;
    s_tool_down = false;
    s_line_active = false;
    s_line_drawing = false;
    s_serial_dot = false;
    s_serial_work_x_mm = 0.0f;
    s_serial_work_y_mm = 0.0f;
    s_serial_physical_x_mm = 0.0f;
    s_serial_physical_y_mm = 0.0f;
    s_state = PUZZLE_AREA_PROBE_STATE_WAIT_TRIGGER;

    elog_i("PUZ_AREA",
           "[PUZ_AREA] id=%s state=WAIT_TRIGGER "
           "action=KEY2_OR_M850 "
           "paper=A4_LANDSCAPE target_x100=0..18150 "
           "target_y100=p1_-1000_p2_-1400_p3_23300_p4_23000 "
           "p2_down_x100=400 p3_up_x100=300 "
           "map_anchor_x100=%d "
           "map_anchor_y100=%d shift_x100=%d shift_y100=%d "
           "unique_corners=%u visits=%u "
           "route=LL_LR_UR_UL_LL marks=%u "
           "line_x100=0..18150 line_y100=7650 "
           "line_from_p4_top_x100=15350 line_more_up_x100=3000 "
           "mark_down_ms=%u mark_up_ms=%u dwell_ms=%u "
           "approach_feed=%d edge_feed=%d line_feed=%d "
           "uart1=LOCAL_115200 protocol=MOVE_DOT_XY "
           "serial_range_x100=0..18150 serial_range_y100=0..24000 "
           "tool=UP magnet=NOT_CONTROLLED",
           PUZZLE_AREA_PROBE_BUILD_ID,
           PuzzleAreaProbe_Scale_100(
               APP_WRITER_LANDSCAPE_MAP_ORIGIN_X_MM),
           PuzzleAreaProbe_Scale_100(
               APP_WRITER_LANDSCAPE_MAP_ORIGIN_Y_MM),
           PuzzleAreaProbe_Scale_100(
               APP_WRITER_LANDSCAPE_SHIFT_X_MM),
           PuzzleAreaProbe_Scale_100(
               APP_WRITER_LANDSCAPE_SHIFT_Y_MM),
           PUZZLE_AREA_UNIQUE_CORNER_COUNT,
           PUZZLE_AREA_VISIT_COUNT,
           PUZZLE_AREA_UNIQUE_CORNER_COUNT,
           PUZZLE_AREA_MARK_DOWN_HOLD_MS,
           PUZZLE_AREA_MARK_UP_SETTLE_MS,
           PUZZLE_AREA_DWELL_MS,
           PuzzleAreaProbe_Scale_100(
               PUZZLE_AREA_APPROACH_FEED_MM_MIN),
           PuzzleAreaProbe_Scale_100(
               PUZZLE_AREA_MOVE_FEED_MM_MIN),
           PuzzleAreaProbe_Scale_100(
               PUZZLE_AREA_LINE_DRAW_FEED_MM_MIN));
    PuzzleAreaProbe_Sendf(
        "ok PUZZLE_AREA READY id=%s state=WAIT_TRIGGER "
        "action=KEY2_OR_M850 "
        "paper_points_mm=0_-10__181p5_-14__181p5_233__0_230 "
        "correction=P2_DOWN4_P3_UP3 route=LL_LR_UR_UL_LL "
        "line_mm=0_76p5__181p5_76p5 line_more_up_mm=30 "
        "marks=%u mark_down_ms=%u mark_up_ms=%u dwell_ms=%u "
        "serial=115200_8N1 commands=MOVE_XY_DOT_XY_STATUS_STOP "
        "serial_frame_mm=LL_ORIGIN_X0_181p5_Y0_240 "
        "tool=UP magnet=NOT_CONTROLLED "
        "status=STATUS emergency=STOP\r\n",
        PUZZLE_AREA_PROBE_BUILD_ID,
        PUZZLE_AREA_UNIQUE_CORNER_COUNT,
        PUZZLE_AREA_MARK_DOWN_HOLD_MS,
        PUZZLE_AREA_MARK_UP_SETTLE_MS,
        PUZZLE_AREA_DWELL_MS);
}

bool PuzzleAreaProbe_Trigger(void)
{
    if (s_state == PUZZLE_AREA_PROBE_STATE_DONE) {
        /*
         * The completed path ends at the horizontal line's right endpoint,
         * so the tracked pose is still valid. Rearm without resetting the
         * motion pose to home.
         */
        App_Servo_Pen_Up();
        s_point_index = 0u;
        s_mark_count = 0u;
        s_dwell_start_ms = 0u;
        s_mark_state_start_ms = 0u;
        s_target_user_x_mm = 0.0f;
        s_target_user_y_mm = 0.0f;
        s_tool_down = false;
        s_line_active = false;
        s_line_drawing = false;
        s_serial_dot = false;
        s_state = PUZZLE_AREA_PROBE_STATE_WAIT_TRIGGER;
    }
    if (s_state != PUZZLE_AREA_PROBE_STATE_WAIT_TRIGGER) {
        return false;
    }
    if (!PuzzleAreaProbe_Limits_Clear()) {
        PuzzleAreaProbe_Fail("start_limit_active");
        return false;
    }
    if (!PuzzleAreaProbe_Start_Current_Point()) {
        PuzzleAreaProbe_Fail("first_point_rejected");
        return false;
    }
    elog_i("PUZ_AREA",
           "[PUZ_AREA] action=TRIGGER_ACCEPTED source=KEY2_OR_M850 "
           "route=LL_LR_UR_UL_LL_LINE marks=4 lines=1 tool=UP");
    PuzzleAreaProbe_Sendf(
        "ok START accepted id=%s source=KEY2_OR_M850 "
        "route=LL_LR_UR_UL_LL_LINE marks=4 lines=1 "
        "tool=UP stop=STOP\r\n",
        PUZZLE_AREA_PROBE_BUILD_ID);
    return true;
}

void PuzzleAreaProbe_Abort_For_Rehome(void)
{
    App_Servo_Pen_Up();
    s_tool_down = false;
    s_line_active = false;
    s_line_drawing = false;
    WriterMotion_Emergency_Stop();
    s_state = PUZZLE_AREA_PROBE_STATE_STOPPED;
    elog_w("PUZ_AREA",
           "[PUZ_AREA] action=ABORT_FOR_REHOME tool=UP");
}

void PuzzleAreaProbe_Update(void)
{
    if (s_state == PUZZLE_AREA_PROBE_STATE_WAIT_TRIGGER) {
        App_Servo_Pen_Up();
        return;
    }

    if ((s_state != PUZZLE_AREA_PROBE_STATE_MOVING) &&
        (s_state != PUZZLE_AREA_PROBE_STATE_MARK_DOWN_HOLD) &&
        (s_state != PUZZLE_AREA_PROBE_STATE_MARK_UP_SETTLE) &&
        (s_state != PUZZLE_AREA_PROBE_STATE_DWELL) &&
        (s_state != PUZZLE_AREA_PROBE_STATE_LINE_DOWN_HOLD) &&
        (s_state != PUZZLE_AREA_PROBE_STATE_LINE_UP_SETTLE) &&
        (s_state != PUZZLE_AREA_PROBE_STATE_SERIAL_MOVING) &&
        (s_state != PUZZLE_AREA_PROBE_STATE_SERIAL_DOT_DOWN_HOLD) &&
        (s_state != PUZZLE_AREA_PROBE_STATE_SERIAL_DOT_UP_SETTLE)) {
        return;
    }
    if (!PuzzleAreaProbe_Limits_Clear()) {
        PuzzleAreaProbe_Fail("runtime_limit_active");
        return;
    }

    if (s_state == PUZZLE_AREA_PROBE_STATE_SERIAL_MOVING) {
        App_Servo_Pen_Up();
        s_tool_down = false;
        WriterMotion_Task();
        if (WriterMotion_Is_Busy()) {
            return;
        }
        if (!PuzzleAreaProbe_Is_At_Target()) {
            if (!PuzzleAreaProbe_Start_Serial_Move_Leg()) {
                PuzzleAreaProbe_Fail("serial_move_leg_rejected");
            }
            return;
        }
        if (!s_serial_dot) {
            PuzzleAreaProbe_Complete_Serial_Command();
            return;
        }
        App_Servo_Pen_Down();
        s_tool_down = true;
        s_mark_state_start_ms = s_sys_tick;
        s_state = PUZZLE_AREA_PROBE_STATE_SERIAL_DOT_DOWN_HOLD;
        elog_i("PUZ_UART",
               "[PUZ_UART] action=DOT_DOWN "
               "work_x100=%d work_y100=%d hold_ms=%u",
               PuzzleAreaProbe_Scale_100(s_serial_work_x_mm),
               PuzzleAreaProbe_Scale_100(s_serial_work_y_mm),
               PUZZLE_AREA_MARK_DOWN_HOLD_MS);
        return;
    }

    if (s_state == PUZZLE_AREA_PROBE_STATE_SERIAL_DOT_DOWN_HOLD) {
        App_Servo_Pen_Down();
        s_tool_down = true;
        if ((uint32_t)(s_sys_tick - s_mark_state_start_ms) <
            PUZZLE_AREA_MARK_DOWN_HOLD_MS) {
            return;
        }
        App_Servo_Pen_Up();
        s_tool_down = false;
        s_mark_state_start_ms = s_sys_tick;
        s_state = PUZZLE_AREA_PROBE_STATE_SERIAL_DOT_UP_SETTLE;
        return;
    }

    if (s_state == PUZZLE_AREA_PROBE_STATE_SERIAL_DOT_UP_SETTLE) {
        App_Servo_Pen_Up();
        s_tool_down = false;
        if ((uint32_t)(s_sys_tick - s_mark_state_start_ms) <
            PUZZLE_AREA_MARK_UP_SETTLE_MS) {
            return;
        }
        PuzzleAreaProbe_Complete_Serial_Command();
        return;
    }

    if (s_state == PUZZLE_AREA_PROBE_STATE_MOVING) {
        if (s_line_active && s_line_drawing) {
            App_Servo_Pen_Down();
            s_tool_down = true;
        } else {
            App_Servo_Pen_Up();
            s_tool_down = false;
        }
        WriterMotion_Task();
        if (WriterMotion_Is_Busy()) {
            return;
        }
        if (!PuzzleAreaProbe_Is_At_Target()) {
            if (!PuzzleAreaProbe_Start_Move_Leg()) {
                PuzzleAreaProbe_Fail("move_leg_rejected");
            }
            return;
        }

        if (s_line_active) {
            if (s_line_drawing) {
                App_Servo_Pen_Up();
                s_tool_down = false;
                s_mark_state_start_ms = s_sys_tick;
                s_state = PUZZLE_AREA_PROBE_STATE_LINE_UP_SETTLE;
                elog_i("PUZ_AREA",
                       "[PUZ_AREA] action=LINE_END_REACHED "
                       "line_y100=7650 from_p4_top_x100=15350 "
                       "tool=UP settle_ms=%u",
                       PUZZLE_AREA_LINE_UP_SETTLE_MS);
                PuzzleAreaProbe_Sendf(
                    "ok LINE_END id=%s line_y100=7650 "
                    "from_p4_top_x100=15350 "
                    "tool=UP settle_ms=%u\r\n",
                    PUZZLE_AREA_PROBE_BUILD_ID,
                    PUZZLE_AREA_LINE_UP_SETTLE_MS);
            } else {
                App_Servo_Pen_Down();
                s_tool_down = true;
                s_mark_state_start_ms = s_sys_tick;
                s_state = PUZZLE_AREA_PROBE_STATE_LINE_DOWN_HOLD;
                elog_i("PUZ_AREA",
                       "[PUZ_AREA] action=LINE_START_REACHED "
                       "line_y100=7650 from_p4_top_x100=15350 "
                       "tool=DOWN hold_ms=%u",
                       PUZZLE_AREA_LINE_DOWN_HOLD_MS);
                PuzzleAreaProbe_Sendf(
                    "ok LINE_START id=%s line_y100=7650 "
                    "from_p4_top_x100=15350 "
                    "tool=DOWN hold_ms=%u\r\n",
                    PUZZLE_AREA_PROBE_BUILD_ID,
                    PUZZLE_AREA_LINE_DOWN_HOLD_MS);
            }
            return;
        }

        if (s_point_index < PUZZLE_AREA_UNIQUE_CORNER_COUNT) {
            App_Servo_Pen_Down();
            s_tool_down = true;
            s_mark_state_start_ms = s_sys_tick;
            s_state = PUZZLE_AREA_PROBE_STATE_MARK_DOWN_HOLD;
        } else {
            s_dwell_start_ms = s_sys_tick;
            s_state = PUZZLE_AREA_PROBE_STATE_DWELL;
        }
        elog_i("PUZ_AREA",
               "[PUZ_AREA] action=CORNER_REACHED visit=%u/%u "
               "name=%s mark=%u tool=%s magnet=NOT_CONTROLLED",
               s_point_index + 1u,
               PUZZLE_AREA_VISIT_COUNT,
               s_points[s_point_index].name,
               (s_point_index < PUZZLE_AREA_UNIQUE_CORNER_COUNT) ?
                   1u : 0u,
               s_tool_down ? "DOWN" : "UP");
        PuzzleAreaProbe_Sendf(
            "ok CORNER_REACHED id=%s visit=%u/%u name=%s "
            "paper_x100=%d paper_y100=%d mark=%u tool=%s "
            "magnet=NOT_CONTROLLED\r\n",
            PUZZLE_AREA_PROBE_BUILD_ID,
            s_point_index + 1u,
            PUZZLE_AREA_VISIT_COUNT,
            s_points[s_point_index].name,
               PuzzleAreaProbe_Scale_100(
                   PuzzleAreaProbe_Landscape_X(
                       &s_points[s_point_index])),
               PuzzleAreaProbe_Scale_100(
                   PuzzleAreaProbe_Landscape_Y(
                       &s_points[s_point_index])),
            (s_point_index < PUZZLE_AREA_UNIQUE_CORNER_COUNT) ?
                1u : 0u,
            s_tool_down ? "DOWN" : "UP");
        return;
    }

    if (s_state == PUZZLE_AREA_PROBE_STATE_LINE_DOWN_HOLD) {
        App_Servo_Pen_Down();
        s_tool_down = true;
        if ((uint32_t)(s_sys_tick - s_mark_state_start_ms) <
            PUZZLE_AREA_LINE_DOWN_HOLD_MS) {
            return;
        }
        s_line_drawing = true;
        if (!PuzzleAreaProbe_Load_Line_Target(true)) {
            PuzzleAreaProbe_Fail("line_end_load_failed");
            return;
        }
        if (PuzzleAreaProbe_Is_At_Target()) {
            s_state = PUZZLE_AREA_PROBE_STATE_MOVING;
        } else if (!PuzzleAreaProbe_Start_Move_Leg()) {
            PuzzleAreaProbe_Fail("line_draw_start_rejected");
            return;
        }
        elog_i("PUZ_AREA",
               "[PUZ_AREA] action=LINE_DRAW_START "
               "x100=0..18150 y100=7650 "
               "from_p4_top_x100=15350 "
               "feed_x100=%d tool=DOWN",
               PuzzleAreaProbe_Scale_100(
                   PUZZLE_AREA_LINE_DRAW_FEED_MM_MIN));
        PuzzleAreaProbe_Sendf(
            "ok LINE_DRAW_START id=%s x100=0..18150 y100=7650 "
            "from_p4_top_x100=15350 feed_x100=%d tool=DOWN\r\n",
            PUZZLE_AREA_PROBE_BUILD_ID,
            PuzzleAreaProbe_Scale_100(
                PUZZLE_AREA_LINE_DRAW_FEED_MM_MIN));
        return;
    }

    if (s_state == PUZZLE_AREA_PROBE_STATE_LINE_UP_SETTLE) {
        App_Servo_Pen_Up();
        s_tool_down = false;
        if ((uint32_t)(s_sys_tick - s_mark_state_start_ms) <
            PUZZLE_AREA_LINE_UP_SETTLE_MS) {
            return;
        }
        if (s_mark_count != PUZZLE_AREA_UNIQUE_CORNER_COUNT) {
            PuzzleAreaProbe_Fail("mark_count_mismatch");
            return;
        }
        s_line_active = false;
        s_line_drawing = false;
        s_state = PUZZLE_AREA_PROBE_STATE_DONE;
        elog_i("PUZ_AREA",
               "[PUZ_AREA] result=DONE unique_corners=%u marks=%u "
               "visits=%u lines=1 "
               "paper_points_mm=0_-10__181p5_-14__181p5_233__0_230 "
               "line_mm=0_76p5__181p5_76p5 "
               "line_more_up_mm=30 tool=UP magnet=NOT_CONTROLLED",
               PUZZLE_AREA_UNIQUE_CORNER_COUNT,
               s_mark_count,
               PUZZLE_AREA_VISIT_COUNT);
        PuzzleAreaProbe_Sendf(
            "ok DONE id=%s unique_corners=%u marks=%u visits=%u "
            "lines=1 line_mm=0_76p5__181p5_76p5 "
            "line_more_up_mm=30 tool=UP magnet=NOT_CONTROLLED\r\n",
            PUZZLE_AREA_PROBE_BUILD_ID,
            PUZZLE_AREA_UNIQUE_CORNER_COUNT,
            s_mark_count,
            PUZZLE_AREA_VISIT_COUNT);
        return;
    }

    if (s_state == PUZZLE_AREA_PROBE_STATE_MARK_DOWN_HOLD) {
        if ((uint32_t)(s_sys_tick - s_mark_state_start_ms) <
            PUZZLE_AREA_MARK_DOWN_HOLD_MS) {
            return;
        }
        App_Servo_Pen_Up();
        s_tool_down = false;
        s_mark_count++;
        s_mark_state_start_ms = s_sys_tick;
        s_state = PUZZLE_AREA_PROBE_STATE_MARK_UP_SETTLE;
        elog_i("PUZ_AREA",
               "[PUZ_AREA] action=MARK_DONE mark=%u/%u visit=%u/%u "
               "name=%s tool=UP magnet=NOT_CONTROLLED",
               s_mark_count,
               PUZZLE_AREA_UNIQUE_CORNER_COUNT,
               s_point_index + 1u,
               PUZZLE_AREA_VISIT_COUNT,
               s_points[s_point_index].name);
        PuzzleAreaProbe_Sendf(
            "ok MARK_DONE id=%s mark=%u/%u visit=%u/%u name=%s "
            "tool=UP magnet=NOT_CONTROLLED\r\n",
            PUZZLE_AREA_PROBE_BUILD_ID,
            s_mark_count,
            PUZZLE_AREA_UNIQUE_CORNER_COUNT,
            s_point_index + 1u,
            PUZZLE_AREA_VISIT_COUNT,
            s_points[s_point_index].name);
        return;
    }

    if (s_state == PUZZLE_AREA_PROBE_STATE_MARK_UP_SETTLE) {
        App_Servo_Pen_Up();
        s_tool_down = false;
        if ((uint32_t)(s_sys_tick - s_mark_state_start_ms) <
            PUZZLE_AREA_MARK_UP_SETTLE_MS) {
            return;
        }
        s_dwell_start_ms = s_sys_tick;
        s_state = PUZZLE_AREA_PROBE_STATE_DWELL;
        return;
    }

    App_Servo_Pen_Up();
    s_tool_down = false;
    if ((uint32_t)(s_sys_tick - s_dwell_start_ms) <
        PUZZLE_AREA_DWELL_MS) {
        return;
    }
    s_point_index++;
    if (s_point_index >= PUZZLE_AREA_VISIT_COUNT) {
        if (s_mark_count != PUZZLE_AREA_UNIQUE_CORNER_COUNT) {
            PuzzleAreaProbe_Fail("mark_count_mismatch");
            return;
        }
        s_line_active = true;
        s_line_drawing = false;
        if (!PuzzleAreaProbe_Load_Line_Target(false)) {
            PuzzleAreaProbe_Fail("line_start_load_failed");
            return;
        }
        if (PuzzleAreaProbe_Is_At_Target()) {
            s_state = PUZZLE_AREA_PROBE_STATE_MOVING;
        } else if (!PuzzleAreaProbe_Start_Move_Leg()) {
            PuzzleAreaProbe_Fail("line_start_move_rejected");
            return;
        }
        elog_i("PUZ_AREA",
               "[PUZ_AREA] action=LINE_APPROACH "
               "target=LEFT x100=0 y100=7650 "
               "from_p4_top_x100=15350 tool=UP");
        PuzzleAreaProbe_Sendf(
            "ok LINE_APPROACH id=%s target=LEFT x100=0 y100=7650 "
            "from_p4_top_x100=15350 tool=UP\r\n",
            PUZZLE_AREA_PROBE_BUILD_ID);
        return;
    }
    if (!PuzzleAreaProbe_Start_Current_Point()) {
        PuzzleAreaProbe_Fail("next_point_rejected");
    }
}

static bool PuzzleAreaProbe_Normalize_Command(
    const uint8_t *frame,
    uint16_t len,
    char *command,
    uint16_t command_size)
{
    uint16_t copy_len = 0u;
    uint16_t start = 0u;
    uint16_t end;

    if ((frame == NULL) || (len == 0u) ||
        (command == NULL) || (command_size < 2u)) {
        return false;
    }
    while ((copy_len < len) &&
           (copy_len < (uint16_t)(command_size - 1u)) &&
           (frame[copy_len] != '\r') && (frame[copy_len] != '\n')) {
        command[copy_len] =
            (char)toupper((unsigned char)frame[copy_len]);
        copy_len++;
    }
    command[copy_len] = '\0';
    while ((start < copy_len) &&
           isspace((unsigned char)command[start])) {
        start++;
    }
    end = copy_len;
    while ((end > start) &&
           isspace((unsigned char)command[end - 1u])) {
        end--;
    }
    if (start > 0u) {
        memmove(command, &command[start], (size_t)(end - start));
    }
    command[end - start] = '\0';
    return command[0] != '\0';
}

static const char *PuzzleAreaProbe_Skip_Separators(const char *cursor)
{
    while ((*cursor != '\0') &&
           (isspace((unsigned char)*cursor) || (*cursor == ','))) {
        cursor++;
    }
    return cursor;
}

static bool PuzzleAreaProbe_Parse_XY(
    const char *command,
    const char *verb,
    float *x_mm,
    float *y_mm)
{
    const char *cursor;
    size_t verb_len;
    bool has_x = false;
    bool has_y = false;

    if ((command == NULL) || (verb == NULL) ||
        (x_mm == NULL) || (y_mm == NULL)) {
        return false;
    }
    verb_len = strlen(verb);
    if ((strncmp(command, verb, verb_len) != 0) ||
        ((command[verb_len] != '\0') &&
         !isspace((unsigned char)command[verb_len]) &&
         (command[verb_len] != ','))) {
        return false;
    }

    cursor = command + verb_len;
    while (true) {
        char axis;
        char *end;
        float value;

        cursor = PuzzleAreaProbe_Skip_Separators(cursor);
        if (*cursor == '\0') {
            break;
        }
        axis = *cursor++;
        if ((axis != 'X') && (axis != 'Y')) {
            return false;
        }
        while ((*cursor == ' ') || (*cursor == '\t') ||
               (*cursor == '=')) {
            cursor++;
        }
        value = strtof(cursor, &end);
        if ((end == cursor) || !isfinite(value)) {
            return false;
        }
        if (axis == 'X') {
            if (has_x) {
                return false;
            }
            *x_mm = value;
            has_x = true;
        } else {
            if (has_y) {
                return false;
            }
            *y_mm = value;
            has_y = true;
        }
        cursor = end;
    }
    return has_x && has_y;
}

static bool PuzzleAreaProbe_Start_Serial_Command(
    float work_x_mm,
    float work_y_mm,
    bool dot)
{
    float physical_x_mm;
    float physical_y_mm;
    float user_x_mm;
    float user_y_mm;

    if (s_state == PUZZLE_AREA_PROBE_STATE_DONE) {
        /*
         * A completed KEY2 test has a valid tracked pose. Rearm the serial
         * task without falsely resetting that pose to the home position.
         */
        App_Servo_Pen_Up();
        s_point_index = 0u;
        s_mark_count = 0u;
        s_dwell_start_ms = 0u;
        s_mark_state_start_ms = 0u;
        s_tool_down = false;
        s_line_active = false;
        s_line_drawing = false;
        s_state = PUZZLE_AREA_PROBE_STATE_WAIT_TRIGGER;
    }
    if (s_state != PUZZLE_AREA_PROBE_STATE_WAIT_TRIGGER) {
        PuzzleAreaProbe_Sendf(
            "error:busy command=%s state=%s use=STATUS_OR_STOP\r\n",
            dot ? "DOT" : "MOVE",
            PuzzleAreaProbe_State_Name());
        return true;
    }
    if (!PuzzleAreaProbe_Limits_Clear()) {
        PuzzleAreaProbe_Sendf(
            "error:limit_active command=%s lim1=%d lim2=%d rehome=1\r\n",
            dot ? "DOT" : "MOVE",
            App_Stepper_Stage1_IsLimitHit(),
            App_Stepper_Stage2_IsLimitHit());
        return true;
    }
    if (!PuzzleAreaProbe_Work_To_User(
            work_x_mm,
            work_y_mm,
            &physical_x_mm,
            &physical_y_mm,
            &user_x_mm,
            &user_y_mm)) {
        PuzzleAreaProbe_Sendf(
            "error:coordinate_out_of_range command=%s "
            "range_x100=0..18150 range_y100=0..24000\r\n",
            dot ? "DOT" : "MOVE");
        return true;
    }

    s_serial_dot = dot;
    s_serial_work_x_mm = work_x_mm;
    s_serial_work_y_mm = work_y_mm;
    s_serial_physical_x_mm = physical_x_mm;
    s_serial_physical_y_mm = physical_y_mm;
    s_target_user_x_mm = user_x_mm;
    s_target_user_y_mm = user_y_mm;
    s_line_active = false;
    s_line_drawing = false;
    App_Servo_Pen_Up();
    s_tool_down = false;

    if (PuzzleAreaProbe_Is_At_Target()) {
        s_state = PUZZLE_AREA_PROBE_STATE_SERIAL_MOVING;
    } else if (!PuzzleAreaProbe_Start_Serial_Move_Leg()) {
        PuzzleAreaProbe_Fail("serial_first_leg_rejected");
        return true;
    }

    elog_i("PUZ_UART",
           "[PUZ_UART] action=ACCEPT command=%s "
           "work_x100=%d work_y100=%d physical_x100=%d physical_y100=%d "
           "user_x100=%d user_y100=%d feed_x100=%d tool=UP",
           dot ? "DOT" : "MOVE",
           PuzzleAreaProbe_Scale_100(work_x_mm),
           PuzzleAreaProbe_Scale_100(work_y_mm),
           PuzzleAreaProbe_Scale_100(physical_x_mm),
           PuzzleAreaProbe_Scale_100(physical_y_mm),
           PuzzleAreaProbe_Scale_100(user_x_mm),
           PuzzleAreaProbe_Scale_100(user_y_mm),
           PuzzleAreaProbe_Scale_100(
               PUZZLE_AREA_SERIAL_MOVE_FEED_MM_MIN));
    PuzzleAreaProbe_Sendf(
        "ok ACCEPT command=%s work_x100=%d work_y100=%d "
        "physical_x100=%d physical_y100=%d "
        "feed_x100=%d tool=UP\r\n",
        dot ? "DOT" : "MOVE",
        PuzzleAreaProbe_Scale_100(work_x_mm),
        PuzzleAreaProbe_Scale_100(work_y_mm),
        PuzzleAreaProbe_Scale_100(physical_x_mm),
        PuzzleAreaProbe_Scale_100(physical_y_mm),
        PuzzleAreaProbe_Scale_100(
            PUZZLE_AREA_SERIAL_MOVE_FEED_MM_MIN));
    return true;
}

bool PuzzleAreaProbe_Process_Frame(const uint8_t *frame, uint16_t len)
{
    char command[PUZZLE_AREA_COMMAND_MAX];
    float x_mm = 0.0f;
    float y_mm = 0.0f;

    if (!PuzzleAreaProbe_Normalize_Command(
            frame, len, command, sizeof(command))) {
        return false;
    }
    if ((strcmp(command, "STATUS") == 0) ||
        (strcmp(command, "?") == 0)) {
        PuzzleAreaProbe_Send_Status();
        return true;
    }
    if (strcmp(command, "STOP") == 0) {
        PuzzleAreaProbe_Stop();
        return true;
    }
    if (PuzzleAreaProbe_Parse_XY(
            command, "MOVE", &x_mm, &y_mm)) {
        return PuzzleAreaProbe_Start_Serial_Command(
            x_mm, y_mm, false);
    }
    if (PuzzleAreaProbe_Parse_XY(
            command, "DOT", &x_mm, &y_mm)) {
        return PuzzleAreaProbe_Start_Serial_Command(
            x_mm, y_mm, true);
    }
    if ((strcmp(command, "M850") == 0) ||
        (strcmp(command, "START") == 0)) {
        if (s_state != PUZZLE_AREA_PROBE_STATE_WAIT_TRIGGER) {
            PuzzleAreaProbe_Sendf(
                "error:wrong_state command=%s state=%s "
                "tool=UP magnet=NOT_CONTROLLED\r\n",
                command,
                PuzzleAreaProbe_State_Name());
            return true;
        }
        (void)PuzzleAreaProbe_Trigger();
        return true;
    }

    PuzzleAreaProbe_Sendf(
        "error:unsupported allowed=MOVE_XY_DOT_XY_M850_START_STATUS_STOP "
        "range_x100=0..18150 range_y100=0..24000 "
        "state=%s tool=UP magnet=NOT_CONTROLLED\r\n",
        PuzzleAreaProbe_State_Name());
    return true;
}

bool PuzzleAreaProbe_Is_Done(void)
{
    return (s_state == PUZZLE_AREA_PROBE_STATE_DONE) ||
           (s_state == PUZZLE_AREA_PROBE_STATE_STOPPED) ||
           (s_state == PUZZLE_AREA_PROBE_STATE_ERROR);
}

puzzle_area_probe_state_t PuzzleAreaProbe_Get_State(void)
{
    return s_state;
}
