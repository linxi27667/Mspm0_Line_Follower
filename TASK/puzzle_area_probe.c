/**
 * @file    puzzle_area_probe.c
 * @brief   Calibrated puzzle-area marking and serial coordinate simulation.
 *
 * KEY2 marks only the four corners during safe-trapezoid calibration.
 * UART1 also accepts MOVE/DOT coordinates in the explicit paper frame:
 * former P4 is (0,0), X+ points right and Y+ points down. Mechanical joint
 * home remains a separate frame.
 */
#include "puzzle_area_probe.h"
#include "app_puzzle_frame.h"
#include "app_servo.h"
#include "app_stepper.h"
#include "app_writer_motion.h"
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
#define PUZZLE_AREA_SERIAL_FEED_DEFAULT_MM_MIN (1800.0f)
#define PUZZLE_AREA_SERIAL_FEED_MIN_MM_MIN     (100.0f)
#define PUZZLE_AREA_SERIAL_FEED_MAX_MM_MIN     (6000.0f)
#define PUZZLE_AREA_SERIAL_RAPID_MIN_FREQ_HZ   (80u)
#define PUZZLE_AREA_SERIAL_RAPID_MAX_FREQ_HZ   (600u)
#define PUZZLE_AREA_MOVE_LEG_MAX_MM           (120.0f)
#define PUZZLE_AREA_POSITION_EPS_MM           (0.20f)
#define PUZZLE_AREA_REPLY_MAX                 (512u)
#define PUZZLE_AREA_COMMAND_MAX               (64u)
#define PUZZLE_AREA_CORNER_ONLY_CALIBRATION   (1u)
#define PUZZLE_AREA_WIDTH_MM                  \
    APP_PUZZLE_PAPER_WIDTH_MM
#define PUZZLE_AREA_HEIGHT_MM                 \
    APP_PUZZLE_PAPER_HEIGHT_MM
#define PUZZLE_AREA_DIVIDER_PAPER_Y_MM        (153.5f)

typedef struct {
    const char *name;
    float paper_x_mm;
    float paper_y_mm;
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
 * V28 extends the full right edge 10 mm, moves P3 down 2 mm, and temporarily
 * disables the divider so strict corner alignment can be completed first:
 *   P2=(191.5,-14), P3=(191.5,231) mm.
 *
 * V29 keeps P3/P4 and the right-edge X target fixed, then corrects the
 * measured bottom corners:
 *   P1 X: 9 mm right -> calibration X moves 9 mm left.
 *   P2 Y: about 233 mm -> calibration Y moves 10 mm down.
 * The paper-local Y range is recorded as 243 mm.
 *
 * V34 replaces the accumulated one-dimensional correction as the public
 * calibration model with a 24-node, 31-triangle measured mesh recovered
 * from the uncut A4 photograph. The missing (199,243) sample is not
 * invented. To retain the height needed by the puzzle task while avoiding
 * the two failed bottom extremes, the public safe region is:
 *
 *   paper (0,0)       = P4 / safe top-left
 *   paper (199,0)     = safe top-right
 *   paper (160,243)   = safe bottom-right trial
 *   paper (40,243)    = safe bottom-left
 *
 * The 120 mm bottom edge preserves space for the largest 12 cm target
 * rectangle in the contest statement. X+ points right and Y+ points down.
 * The fifth visit repeats paper zero to close the trapezoid.
 *
 * V37 keeps that frame unchanged and aligns the four measured scan rows.
 * Their right endpoints were respectively 2.0/3.5/1.5/4.2 mm higher than
 * their left endpoints at paper Y=0/50/100/145. The right-edge correction
 * is piecewise linear in Y, scales linearly from zero at X=0, and returns
 * continuously to zero at Y=180.
 */
static const puzzle_area_point_t s_points[PUZZLE_AREA_VISIT_COUNT] = {
    {"PAPER_ZERO_P4", 0.0f, 0.0f},
    {"X_MAX_P3", PUZZLE_AREA_WIDTH_MM, 0.0f},
    {"SAFE_BOTTOM_RIGHT",
     APP_PUZZLE_TRAPEZOID_BOTTOM_RIGHT_X_MM,
     PUZZLE_AREA_HEIGHT_MM},
    {"SAFE_BOTTOM_LEFT",
     APP_PUZZLE_TRAPEZOID_BOTTOM_LEFT_X_MM,
     PUZZLE_AREA_HEIGHT_MM},
    {"CLOSE_PAPER_ZERO_P4", 0.0f, 0.0f},
};

/*
 * The existing divider was 153.5 mm below the former P4 top reference.
 * It is now expressed directly in the new top-down paper frame. Both
 * endpoints pass through the same frame/calibration pipeline as serial XY.
 */
static const puzzle_area_point_t s_line_start = {
    "DIVIDER_X0",
    0.0f,
    PUZZLE_AREA_DIVIDER_PAPER_Y_MM
};

static const puzzle_area_point_t s_line_end = {
    "DIVIDER_X_MAX",
    PUZZLE_AREA_WIDTH_MM,
    PUZZLE_AREA_DIVIDER_PAPER_Y_MM
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
static float s_serial_paper_x_mm = 0.0f;
static float s_serial_paper_y_mm = 0.0f;
static float s_serial_grid_input_x_mm = 0.0f;
static float s_serial_grid_input_y_mm = 0.0f;
static float s_serial_mapped_x_mm = 0.0f;
static float s_serial_mapped_y_mm = 0.0f;
static float s_serial_calibrated_x_mm = 0.0f;
static float s_serial_calibrated_y_mm = 0.0f;
static float s_serial_move_feed_mm_min =
    PUZZLE_AREA_SERIAL_FEED_DEFAULT_MM_MIN;
static uint32_t s_serial_last_master_freq_hz = 0u;

static int32_t PuzzleAreaProbe_Scale_100(float value)
{
    return (int32_t)((value >= 0.0f) ?
                     (value * 100.0f + 0.5f) :
                     (value * 100.0f - 0.5f));
}

static float PuzzleAreaProbe_Paper_X(
    const puzzle_area_point_t *point)
{
    return point->paper_x_mm;
}

static float PuzzleAreaProbe_Paper_Y(
    const puzzle_area_point_t *point)
{
    return point->paper_y_mm;
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
    app_puzzle_frame_map_t frame_map;

    if ((point == NULL) || (user_x_mm == NULL) || (user_y_mm == NULL)) {
        return false;
    }

    if (!App_PuzzleFrame_To_User(
            point->paper_x_mm, point->paper_y_mm, &frame_map)) {
        return false;
    }
    *user_x_mm = frame_map.user_x_mm;
    *user_y_mm = frame_map.user_y_mm;
    return true;
}

/*
 * Paper coordinates remain rectangular for the serial assistant and K230.
 * The shared frame module keeps the new paper zero independent of mechanical
 * home and composes the established measured projective calibration.
 */
static bool PuzzleAreaProbe_Paper_To_User(
    float paper_x_mm,
    float paper_y_mm,
    app_puzzle_frame_map_t *frame_map)
{
    return App_PuzzleFrame_To_User(
        paper_x_mm, paper_y_mm, frame_map);
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
               PuzzleAreaProbe_Paper_X(point)),
           PuzzleAreaProbe_Scale_100(
               PuzzleAreaProbe_Paper_Y(point)),
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
               PuzzleAreaProbe_Paper_X(point)),
           PuzzleAreaProbe_Scale_100(
               PuzzleAreaProbe_Paper_Y(point)),
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
    if (!WriterMotion_Start_To_At_Feed_Limited(
            leg_x,
            leg_y,
            s_serial_move_feed_mm_min,
            PUZZLE_AREA_SERIAL_RAPID_MIN_FREQ_HZ,
            PUZZLE_AREA_SERIAL_RAPID_MAX_FREQ_HZ)) {
        return false;
    }
    s_serial_last_master_freq_hz =
        WriterMotion_Get_Last_Cmd()->master_freq_hz;
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
           "paper_frame=%s paper_x100=%d paper_y100=%d "
           "grid_in_x100=%d grid_in_y100=%d "
           "mapped_x100=%d mapped_y100=%d "
           "cal_x100=%d cal_y100=%d "
           "user_x100=%d user_y100=%d tool=UP",
           s_serial_dot ? "DOT" : "MOVE",
           APP_PUZZLE_PAPER_FRAME_TEXT,
           PuzzleAreaProbe_Scale_100(s_serial_paper_x_mm),
           PuzzleAreaProbe_Scale_100(s_serial_paper_y_mm),
           PuzzleAreaProbe_Scale_100(s_serial_grid_input_x_mm),
           PuzzleAreaProbe_Scale_100(s_serial_grid_input_y_mm),
           PuzzleAreaProbe_Scale_100(s_serial_mapped_x_mm),
           PuzzleAreaProbe_Scale_100(s_serial_mapped_y_mm),
           PuzzleAreaProbe_Scale_100(s_serial_calibrated_x_mm),
           PuzzleAreaProbe_Scale_100(s_serial_calibrated_y_mm),
           PuzzleAreaProbe_Scale_100(pose->user_point.x_mm),
           PuzzleAreaProbe_Scale_100(pose->user_point.y_mm));
    PuzzleAreaProbe_Sendf(
        "ok DONE command=%s frame=%s "
        "paper_x100=%d paper_y100=%d "
        "grid_in_x100=%d grid_in_y100=%d "
        "mapped_x100=%d mapped_y100=%d "
        "cal_x100=%d cal_y100=%d "
        "user_x100=%d user_y100=%d tool=UP\r\n",
        s_serial_dot ? "DOT" : "MOVE",
        APP_PUZZLE_PAPER_FRAME_TEXT,
        PuzzleAreaProbe_Scale_100(s_serial_paper_x_mm),
        PuzzleAreaProbe_Scale_100(s_serial_paper_y_mm),
        PuzzleAreaProbe_Scale_100(s_serial_grid_input_x_mm),
        PuzzleAreaProbe_Scale_100(s_serial_grid_input_y_mm),
        PuzzleAreaProbe_Scale_100(s_serial_mapped_x_mm),
        PuzzleAreaProbe_Scale_100(s_serial_mapped_y_mm),
        PuzzleAreaProbe_Scale_100(s_serial_calibrated_x_mm),
        PuzzleAreaProbe_Scale_100(s_serial_calibrated_y_mm),
        PuzzleAreaProbe_Scale_100(pose->user_point.x_mm),
        PuzzleAreaProbe_Scale_100(pose->user_point.y_mm));
}

static bool PuzzleAreaProbe_Start_Current_Point(void)
{
    if (!PuzzleAreaProbe_Load_Target()) {
        return false;
    }
    /*
     * A repeated KEY2 run may already be at paper zero P4. Do not submit a
     * zero-length motion; enter MOVING so Update() performs the first mark.
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
        "ok STATUS id=%s state=%s frame=%s "
        "machine_home=%s paper_zero=P4 axes=X_RIGHT_Y_DOWN "
        "visit=%u/%u marks=%u/%u target=%s "
        "target_x100=%d target_y100=%d "
        "serial_x100=%d serial_y100=%d "
        "range_x100=0..19900 range_y100=0..24300 "
        "polygon=0_0__199_0__160_243__40_243 "
        "serial_up_feed_x100=%d serial_master_hz=%u "
        "serial_rapid_cap_hz=%u "
        "user_x100=%d user_y100=%d busy=%u lim1=%d lim2=%d "
        "tool=%s\r\n",
        PUZZLE_AREA_PROBE_BUILD_ID,
        PuzzleAreaProbe_State_Name(),
        APP_PUZZLE_PAPER_FRAME_TEXT,
        APP_PUZZLE_MACHINE_HOME_TEXT,
        (s_point_index < PUZZLE_AREA_VISIT_COUNT) ?
            (s_point_index + 1u) : PUZZLE_AREA_VISIT_COUNT,
        PUZZLE_AREA_VISIT_COUNT,
        s_mark_count,
        PUZZLE_AREA_UNIQUE_CORNER_COUNT,
        point->name,
        PuzzleAreaProbe_Scale_100(
            PuzzleAreaProbe_Paper_X(point)),
        PuzzleAreaProbe_Scale_100(
            PuzzleAreaProbe_Paper_Y(point)),
        PuzzleAreaProbe_Scale_100(s_serial_paper_x_mm),
        PuzzleAreaProbe_Scale_100(s_serial_paper_y_mm),
        PuzzleAreaProbe_Scale_100(s_serial_move_feed_mm_min),
        s_serial_last_master_freq_hz,
        PUZZLE_AREA_SERIAL_RAPID_MAX_FREQ_HZ,
        PuzzleAreaProbe_Scale_100(pose->user_point.x_mm),
        PuzzleAreaProbe_Scale_100(pose->user_point.y_mm),
        WriterMotion_Is_Busy() ? 1u : 0u,
        App_Stepper_Stage1_IsLimitHit(),
        App_Stepper_Stage2_IsLimitHit(),
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
    s_serial_paper_x_mm = 0.0f;
    s_serial_paper_y_mm = 0.0f;
    s_serial_grid_input_x_mm = 0.0f;
    s_serial_grid_input_y_mm = 0.0f;
    s_serial_mapped_x_mm = 0.0f;
    s_serial_mapped_y_mm = 0.0f;
    s_serial_calibrated_x_mm = 0.0f;
    s_serial_calibrated_y_mm = 0.0f;
    s_serial_move_feed_mm_min =
        PUZZLE_AREA_SERIAL_FEED_DEFAULT_MM_MIN;
    s_serial_last_master_freq_hz = 0u;
    s_state = PUZZLE_AREA_PROBE_STATE_WAIT_TRIGGER;

    elog_i("PUZ_AREA",
           "[PUZ_AREA] id=%s state=WAIT_TRIGGER "
           "machine_home=%s paper_zero=P4 paper_frame=%s "
           "axes=X_RIGHT_Y_DOWN range_x100=0..19900 "
           "range_y100=0..24300 "
           "polygon=0_0__199_0__160_243__40_243 "
           "legacy_corners=P1_-9_-10_P2_191p5_-24_"
           "P3_191p5_231_P4_0_230 "
           "calibration=PHOTO_TRI_MESH_24NODE_31TRI_4ROW_ALIGN "
           "mesh_rows_y=0_60_120_180_243 "
           "unique_corners=%u visits=%u "
           "route=P4_P3_SAFE_BR_SAFE_BL_P4 "
           "marks=%u divider=DISABLED_CORNER_CAL "
           "mark_down_ms=%u mark_up_ms=%u dwell_ms=%u "
           "approach_feed=%d edge_feed=%d line_feed=%d "
           "serial_up_feed=%d serial_feed_range=%d..%d "
           "serial_rapid_cap_hz=%u "
           "uart1=LOCAL_115200 protocol=MOVE_DOT_SPEED_PAPER_XY "
           "tool=UP magnet=NOT_CONTROLLED",
           PUZZLE_AREA_PROBE_BUILD_ID,
           APP_PUZZLE_MACHINE_HOME_TEXT,
           APP_PUZZLE_PAPER_FRAME_TEXT,
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
               PUZZLE_AREA_LINE_DRAW_FEED_MM_MIN),
           PuzzleAreaProbe_Scale_100(
               s_serial_move_feed_mm_min),
           PuzzleAreaProbe_Scale_100(
               PUZZLE_AREA_SERIAL_FEED_MIN_MM_MIN),
           PuzzleAreaProbe_Scale_100(
               PUZZLE_AREA_SERIAL_FEED_MAX_MM_MIN),
           PUZZLE_AREA_SERIAL_RAPID_MAX_FREQ_HZ);
    PuzzleAreaProbe_Sendf(
        "ok PUZZLE_AREA READY id=%s state=WAIT_TRIGGER "
        "machine_home=%s paper_zero=P4 frame=%s "
        "axes=X_RIGHT_Y_DOWN range_x100=0..19900 "
        "range_y100=0..24300 "
        "polygon=0_0__199_0__160_243__40_243 "
        "route=P4_P3_SAFE_BR_SAFE_BL_P4 "
        "divider=DISABLED_CORNER_CAL marks=%u "
        "commands=MOVE_XY_DOT_XY_SPEED_F_STATUS_STOP "
        "serial_up_feed_x100=%d serial_rapid_cap_hz=%u "
        "tool=UP status=STATUS emergency=STOP\r\n",
        PUZZLE_AREA_PROBE_BUILD_ID,
        APP_PUZZLE_MACHINE_HOME_TEXT,
        APP_PUZZLE_PAPER_FRAME_TEXT,
        PUZZLE_AREA_UNIQUE_CORNER_COUNT,
        PuzzleAreaProbe_Scale_100(s_serial_move_feed_mm_min),
        PUZZLE_AREA_SERIAL_RAPID_MAX_FREQ_HZ);
}

bool PuzzleAreaProbe_Trigger(void)
{
    if (s_state == PUZZLE_AREA_PROBE_STATE_DONE) {
        /*
         * The completed corner-only path ends back at paper zero P4, so the
         * tracked pose is still valid. Rearm without resetting it to home.
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
           "route=P4_P3_SAFE_BR_SAFE_BL_P4 "
           "paper_zero=P4 axes=X_RIGHT_Y_DOWN "
           "marks=4 lines=0 divider=DISABLED_CORNER_CAL tool=UP");
    PuzzleAreaProbe_Sendf(
        "ok START accepted id=%s source=KEY2_OR_M850 "
        "frame=%s route=P4_P3_SAFE_BR_SAFE_BL_P4 "
        "marks=4 lines=0 divider=DISABLED_CORNER_CAL "
        "tool=UP stop=STOP\r\n",
        PUZZLE_AREA_PROBE_BUILD_ID,
        APP_PUZZLE_PAPER_FRAME_TEXT);
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
               "frame=%s paper_x100=%d paper_y100=%d hold_ms=%u",
               APP_PUZZLE_PAPER_FRAME_TEXT,
               PuzzleAreaProbe_Scale_100(s_serial_paper_x_mm),
               PuzzleAreaProbe_Scale_100(s_serial_paper_y_mm),
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
                       "frame=%s paper_y100=%d "
                       "tool=UP settle_ms=%u",
                       APP_PUZZLE_PAPER_FRAME_TEXT,
                       PuzzleAreaProbe_Scale_100(
                           PUZZLE_AREA_DIVIDER_PAPER_Y_MM),
                       PUZZLE_AREA_LINE_UP_SETTLE_MS);
                PuzzleAreaProbe_Sendf(
                    "ok LINE_END id=%s frame=%s paper_y100=%d "
                    "tool=UP settle_ms=%u\r\n",
                    PUZZLE_AREA_PROBE_BUILD_ID,
                    APP_PUZZLE_PAPER_FRAME_TEXT,
                    PuzzleAreaProbe_Scale_100(
                        PUZZLE_AREA_DIVIDER_PAPER_Y_MM),
                    PUZZLE_AREA_LINE_UP_SETTLE_MS);
            } else {
                App_Servo_Pen_Down();
                s_tool_down = true;
                s_mark_state_start_ms = s_sys_tick;
                s_state = PUZZLE_AREA_PROBE_STATE_LINE_DOWN_HOLD;
                elog_i("PUZ_AREA",
                       "[PUZ_AREA] action=LINE_START_REACHED "
                       "frame=%s paper_y100=%d "
                       "tool=DOWN hold_ms=%u",
                       APP_PUZZLE_PAPER_FRAME_TEXT,
                       PuzzleAreaProbe_Scale_100(
                           PUZZLE_AREA_DIVIDER_PAPER_Y_MM),
                       PUZZLE_AREA_LINE_DOWN_HOLD_MS);
                PuzzleAreaProbe_Sendf(
                    "ok LINE_START id=%s frame=%s paper_y100=%d "
                    "tool=DOWN hold_ms=%u\r\n",
                    PUZZLE_AREA_PROBE_BUILD_ID,
                    APP_PUZZLE_PAPER_FRAME_TEXT,
                    PuzzleAreaProbe_Scale_100(
                        PUZZLE_AREA_DIVIDER_PAPER_Y_MM),
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
                   PuzzleAreaProbe_Paper_X(
                       &s_points[s_point_index])),
               PuzzleAreaProbe_Scale_100(
                   PuzzleAreaProbe_Paper_Y(
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
               "frame=%s paper_x100=0..19900 paper_y100=%d "
               "feed_x100=%d tool=DOWN",
               APP_PUZZLE_PAPER_FRAME_TEXT,
               PuzzleAreaProbe_Scale_100(
                   PUZZLE_AREA_DIVIDER_PAPER_Y_MM),
               PuzzleAreaProbe_Scale_100(
                   PUZZLE_AREA_LINE_DRAW_FEED_MM_MIN));
        PuzzleAreaProbe_Sendf(
            "ok LINE_DRAW_START id=%s frame=%s "
            "paper_x100=0..19900 paper_y100=%d "
            "feed_x100=%d tool=DOWN\r\n",
            PUZZLE_AREA_PROBE_BUILD_ID,
            APP_PUZZLE_PAPER_FRAME_TEXT,
            PuzzleAreaProbe_Scale_100(
                PUZZLE_AREA_DIVIDER_PAPER_Y_MM),
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
               "visits=%u lines=1 frame=%s "
               "paper_points_mm=0_0__199_0__"
               "160_243__40_243 "
               "divider_y100=%d tool=UP magnet=NOT_CONTROLLED",
               PUZZLE_AREA_UNIQUE_CORNER_COUNT,
               s_mark_count,
               PUZZLE_AREA_VISIT_COUNT,
               APP_PUZZLE_PAPER_FRAME_TEXT,
               PuzzleAreaProbe_Scale_100(
                   PUZZLE_AREA_DIVIDER_PAPER_Y_MM));
        PuzzleAreaProbe_Sendf(
            "ok DONE id=%s unique_corners=%u marks=%u visits=%u "
            "lines=1 frame=%s paper_points_mm=0_0__199_0__"
            "160_243__40_243 divider_y100=%d "
            "tool=UP magnet=NOT_CONTROLLED\r\n",
            PUZZLE_AREA_PROBE_BUILD_ID,
            PUZZLE_AREA_UNIQUE_CORNER_COUNT,
            s_mark_count,
            PUZZLE_AREA_VISIT_COUNT,
            APP_PUZZLE_PAPER_FRAME_TEXT,
            PuzzleAreaProbe_Scale_100(
                PUZZLE_AREA_DIVIDER_PAPER_Y_MM));
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
#if PUZZLE_AREA_CORNER_ONLY_CALIBRATION
        s_line_active = false;
        s_line_drawing = false;
        s_state = PUZZLE_AREA_PROBE_STATE_DONE;
        elog_i("PUZ_AREA",
               "[PUZ_AREA] result=DONE unique_corners=%u marks=%u "
               "visits=%u lines=0 frame=%s "
               "paper_points_mm=0_0__199_0__"
               "160_243__40_243 "
               "divider=DISABLED_CORNER_CAL "
               "tool=UP magnet=NOT_CONTROLLED",
               PUZZLE_AREA_UNIQUE_CORNER_COUNT,
               s_mark_count,
               PUZZLE_AREA_VISIT_COUNT,
               APP_PUZZLE_PAPER_FRAME_TEXT);
        PuzzleAreaProbe_Sendf(
            "ok DONE id=%s unique_corners=%u marks=%u visits=%u "
            "lines=0 frame=%s paper_points_mm=0_0__199_0__"
            "160_243__40_243 divider=DISABLED_CORNER_CAL "
            "tool=UP magnet=NOT_CONTROLLED\r\n",
            PUZZLE_AREA_PROBE_BUILD_ID,
            PUZZLE_AREA_UNIQUE_CORNER_COUNT,
            s_mark_count,
            PUZZLE_AREA_VISIT_COUNT,
            APP_PUZZLE_PAPER_FRAME_TEXT);
        return;
#else
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
               "target=X0 frame=%s paper_x100=0 paper_y100=%d "
               "tool=UP",
               APP_PUZZLE_PAPER_FRAME_TEXT,
               PuzzleAreaProbe_Scale_100(
                   PUZZLE_AREA_DIVIDER_PAPER_Y_MM));
        PuzzleAreaProbe_Sendf(
            "ok LINE_APPROACH id=%s target=X0 frame=%s "
            "paper_x100=0 paper_y100=%d tool=UP\r\n",
            PUZZLE_AREA_PROBE_BUILD_ID,
            APP_PUZZLE_PAPER_FRAME_TEXT,
            PuzzleAreaProbe_Scale_100(
                PUZZLE_AREA_DIVIDER_PAPER_Y_MM));
        return;
#endif
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

static bool PuzzleAreaProbe_Parse_Speed(
    const char *command,
    float *feed_mm_min)
{
    static const char verb[] = "SPEED";
    const char *cursor;
    char *end;
    float value;

    if ((command == NULL) || (feed_mm_min == NULL) ||
        (strncmp(command, verb, sizeof(verb) - 1u) != 0)) {
        return false;
    }

    cursor = command + sizeof(verb) - 1u;
    if ((*cursor != '\0') && (*cursor != '=') &&
        (*cursor != ',') && !isspace((unsigned char)*cursor)) {
        return false;
    }
    while ((*cursor != '\0') &&
           (isspace((unsigned char)*cursor) ||
            (*cursor == ',') || (*cursor == '='))) {
        cursor++;
    }

    /* Accept both SPEED 1800 and the explicit SPEED UP F1800 form. */
    if ((cursor[0] == 'U') && (cursor[1] == 'P') &&
        ((cursor[2] == '\0') || (cursor[2] == '=') ||
         (cursor[2] == ',') ||
         isspace((unsigned char)cursor[2]))) {
        cursor += 2;
        while ((*cursor != '\0') &&
               (isspace((unsigned char)*cursor) ||
                (*cursor == ',') || (*cursor == '='))) {
            cursor++;
        }
    }
    if (*cursor == 'F') {
        cursor++;
        while ((*cursor == ' ') || (*cursor == '\t') ||
               (*cursor == '=')) {
            cursor++;
        }
    }

    value = strtof(cursor, &end);
    if ((end == cursor) || !isfinite(value)) {
        return false;
    }
    cursor = PuzzleAreaProbe_Skip_Separators(end);
    if (*cursor != '\0') {
        return false;
    }

    *feed_mm_min = value;
    return true;
}

static void PuzzleAreaProbe_Send_Speed(void)
{
    PuzzleAreaProbe_Sendf(
        "ok SPEED mode=PEN_UP_XY feed_x100=%d "
        "range_x100=%d..%d rapid_cap_hz=%u "
        "examples=SPEED_1800__SPEED_UP_F1800\r\n",
        PuzzleAreaProbe_Scale_100(s_serial_move_feed_mm_min),
        PuzzleAreaProbe_Scale_100(
            PUZZLE_AREA_SERIAL_FEED_MIN_MM_MIN),
        PuzzleAreaProbe_Scale_100(
            PUZZLE_AREA_SERIAL_FEED_MAX_MM_MIN),
        PUZZLE_AREA_SERIAL_RAPID_MAX_FREQ_HZ);
}

static bool PuzzleAreaProbe_Set_Speed(float feed_mm_min)
{
    if (WriterMotion_Is_Busy() ||
        (s_state == PUZZLE_AREA_PROBE_STATE_MOVING) ||
        (s_state == PUZZLE_AREA_PROBE_STATE_SERIAL_MOVING) ||
        (s_state == PUZZLE_AREA_PROBE_STATE_SERIAL_DOT_DOWN_HOLD) ||
        (s_state == PUZZLE_AREA_PROBE_STATE_SERIAL_DOT_UP_SETTLE)) {
        PuzzleAreaProbe_Sendf(
            "error:busy command=SPEED state=%s "
            "use=STOP_OR_WAIT_DONE\r\n",
            PuzzleAreaProbe_State_Name());
        return true;
    }
    if ((feed_mm_min < PUZZLE_AREA_SERIAL_FEED_MIN_MM_MIN) ||
        (feed_mm_min > PUZZLE_AREA_SERIAL_FEED_MAX_MM_MIN)) {
        PuzzleAreaProbe_Sendf(
            "error:speed_out_of_range feed_x100=%d "
            "range_x100=%d..%d\r\n",
            PuzzleAreaProbe_Scale_100(feed_mm_min),
            PuzzleAreaProbe_Scale_100(
                PUZZLE_AREA_SERIAL_FEED_MIN_MM_MIN),
            PuzzleAreaProbe_Scale_100(
                PUZZLE_AREA_SERIAL_FEED_MAX_MM_MIN));
        return true;
    }

    s_serial_move_feed_mm_min = feed_mm_min;
    elog_i("PUZ_UART",
           "[PUZ_UART] action=SPEED_SET mode=PEN_UP_XY "
           "feed_x100=%d rapid_cap_hz=%u",
           PuzzleAreaProbe_Scale_100(s_serial_move_feed_mm_min),
           PUZZLE_AREA_SERIAL_RAPID_MAX_FREQ_HZ);
    PuzzleAreaProbe_Send_Speed();
    return true;
}

static bool PuzzleAreaProbe_Start_Serial_Command(
    float paper_x_mm,
    float paper_y_mm,
    bool dot)
{
    app_puzzle_frame_map_t frame_map;

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
    if (!PuzzleAreaProbe_Paper_To_User(
            paper_x_mm, paper_y_mm, &frame_map)) {
        PuzzleAreaProbe_Sendf(
            "error:coordinate_out_of_range command=%s "
            "frame=%s range_x100=0..19900 range_y100=0..24300 "
            "polygon=0_0__199_0__160_243__40_243\r\n",
            dot ? "DOT" : "MOVE",
            APP_PUZZLE_PAPER_FRAME_TEXT);
        return true;
    }

    s_serial_dot = dot;
    s_serial_paper_x_mm = paper_x_mm;
    s_serial_paper_y_mm = paper_y_mm;
    s_serial_grid_input_x_mm = frame_map.calibration_input_x_mm;
    s_serial_grid_input_y_mm = frame_map.calibration_input_y_mm;
    s_serial_mapped_x_mm = frame_map.mapped_paper_x_mm;
    s_serial_mapped_y_mm = frame_map.mapped_paper_y_mm;
    s_serial_calibrated_x_mm =
        frame_map.calibrated_physical_x_mm;
    s_serial_calibrated_y_mm =
        frame_map.calibrated_physical_y_mm;
    s_target_user_x_mm = frame_map.user_x_mm;
    s_target_user_y_mm = frame_map.user_y_mm;
    s_line_active = false;
    s_line_drawing = false;
    App_Servo_Pen_Up();
    s_tool_down = false;
    s_serial_last_master_freq_hz = 0u;

    if (PuzzleAreaProbe_Is_At_Target()) {
        s_state = PUZZLE_AREA_PROBE_STATE_SERIAL_MOVING;
    } else if (!PuzzleAreaProbe_Start_Serial_Move_Leg()) {
        PuzzleAreaProbe_Fail("serial_first_leg_rejected");
        return true;
    }

    elog_i("PUZ_UART",
           "[PUZ_UART] action=ACCEPT command=%s "
           "paper_frame=%s paper_x100=%d paper_y100=%d "
           "grid_in_x100=%d grid_in_y100=%d "
           "mapped_x100=%d mapped_y100=%d "
           "legacy_x100=%d legacy_y100=%d "
           "cal_x100=%d cal_y100=%d "
           "user_x100=%d user_y100=%d feed_x100=%d "
           "master_hz=%u rapid_cap_hz=%u tool=UP",
           dot ? "DOT" : "MOVE",
           APP_PUZZLE_PAPER_FRAME_TEXT,
           PuzzleAreaProbe_Scale_100(paper_x_mm),
           PuzzleAreaProbe_Scale_100(paper_y_mm),
           PuzzleAreaProbe_Scale_100(
               frame_map.calibration_input_x_mm),
           PuzzleAreaProbe_Scale_100(
               frame_map.calibration_input_y_mm),
           PuzzleAreaProbe_Scale_100(frame_map.mapped_paper_x_mm),
           PuzzleAreaProbe_Scale_100(frame_map.mapped_paper_y_mm),
           PuzzleAreaProbe_Scale_100(frame_map.legacy_work_x_mm),
           PuzzleAreaProbe_Scale_100(frame_map.legacy_work_y_mm),
           PuzzleAreaProbe_Scale_100(
               frame_map.calibrated_physical_x_mm),
           PuzzleAreaProbe_Scale_100(
               frame_map.calibrated_physical_y_mm),
           PuzzleAreaProbe_Scale_100(frame_map.user_x_mm),
           PuzzleAreaProbe_Scale_100(frame_map.user_y_mm),
           PuzzleAreaProbe_Scale_100(
               s_serial_move_feed_mm_min),
           s_serial_last_master_freq_hz,
           PUZZLE_AREA_SERIAL_RAPID_MAX_FREQ_HZ);
    PuzzleAreaProbe_Sendf(
        "ok ACCEPT command=%s frame=%s "
        "paper_x100=%d paper_y100=%d "
        "grid_in_x100=%d grid_in_y100=%d "
        "mapped_x100=%d mapped_y100=%d "
        "legacy_x100=%d legacy_y100=%d "
        "feed_x100=%d master_hz=%u rapid_cap_hz=%u tool=UP\r\n",
        dot ? "DOT" : "MOVE",
        APP_PUZZLE_PAPER_FRAME_TEXT,
        PuzzleAreaProbe_Scale_100(paper_x_mm),
        PuzzleAreaProbe_Scale_100(paper_y_mm),
        PuzzleAreaProbe_Scale_100(
            frame_map.calibration_input_x_mm),
        PuzzleAreaProbe_Scale_100(
            frame_map.calibration_input_y_mm),
        PuzzleAreaProbe_Scale_100(frame_map.mapped_paper_x_mm),
        PuzzleAreaProbe_Scale_100(frame_map.mapped_paper_y_mm),
        PuzzleAreaProbe_Scale_100(frame_map.legacy_work_x_mm),
        PuzzleAreaProbe_Scale_100(frame_map.legacy_work_y_mm),
        PuzzleAreaProbe_Scale_100(
            s_serial_move_feed_mm_min),
        s_serial_last_master_freq_hz,
        PUZZLE_AREA_SERIAL_RAPID_MAX_FREQ_HZ);
    return true;
}

bool PuzzleAreaProbe_Process_Frame(const uint8_t *frame, uint16_t len)
{
    char command[PUZZLE_AREA_COMMAND_MAX];
    float x_mm = 0.0f;
    float y_mm = 0.0f;
    float feed_mm_min = 0.0f;

    if (!PuzzleAreaProbe_Normalize_Command(
            frame, len, command, sizeof(command))) {
        return false;
    }
    if ((strcmp(command, "STATUS") == 0) ||
        (strcmp(command, "?") == 0)) {
        PuzzleAreaProbe_Send_Status();
        return true;
    }
    if ((strcmp(command, "SPEED") == 0) ||
        (strcmp(command, "SPEED?") == 0)) {
        PuzzleAreaProbe_Send_Speed();
        return true;
    }
    if (PuzzleAreaProbe_Parse_Speed(command, &feed_mm_min)) {
        return PuzzleAreaProbe_Set_Speed(feed_mm_min);
    }
    if (strncmp(command, "SPEED", 5u) == 0) {
        PuzzleAreaProbe_Sendf(
            "error:speed_syntax examples=SPEED_1800__"
            "SPEED_UP_F1800__SPEED_QUERY\r\n");
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
        "error:unsupported allowed=MOVE_XY_DOT_XY_SPEED_F_"
        "M850_START_STATUS_STOP "
        "frame=%s axes=X_RIGHT_Y_DOWN "
        "range_x100=0..19900 range_y100=0..24300 "
        "polygon=0_0__199_0__160_243__40_243 "
        "state=%s tool=UP magnet=NOT_CONTROLLED\r\n",
        APP_PUZZLE_PAPER_FRAME_TEXT,
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
