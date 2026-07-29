/**
 * @file    author_text_demo.c
 * @brief   UART-triggered V44 one-file A4 3x3 local draw calibration.
 */
#include "author_text_demo.h"
#include "author_text_demo_path.h"
#include "app_servo.h"
#include "app_stepper.h"
#include "app_writer_motion.h"
#include "comm_vision_uart.h"
#include "elog.h"
#include <ctype.h>
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#define AUTHOR_TEXT_DEMO_REPLY_MAX       (384u)
#define AUTHOR_TEXT_DEMO_COMMAND_MAX     (32u)
#define AUTHOR_TEXT_DEMO_SETUP_G21       (1u << 0)
#define AUTHOR_TEXT_DEMO_SETUP_G90       (1u << 1)
#define AUTHOR_TEXT_DEMO_SETUP_G94       (1u << 2)
#define AUTHOR_TEXT_DEMO_SETUP_M5        (1u << 3)
#define AUTHOR_TEXT_DEMO_SETUP_ALL       (0x0Fu)
#define AUTHOR_TEXT_DEMO_ALIGN_X_X10     (1500)
#define AUTHOR_TEXT_DEMO_ALIGN_Y_X10     (200)

#if !APP_WRITER_AUTHOR_BASELINE_ENABLE || !APP_WRITER_AUTHOR_CORE_ENABLE
#error "The V44 one-file A4 calibration requires the active author frame"
#endif

#if !APP_WRITER_A4_ENVELOPE_PROBE_ENABLE
#error "The V44 one-file A4 calibration requires measured-envelope limits"
#endif

#if APP_WRITER_DIRECTION_COMP_ENABLE || \
    APP_WRITER_DIRECTION_COMP_PRELOAD_ENABLE
#error "The V44 one-file A4 calibration requires direction compensation disabled"
#endif

#if APP_WRITER_AUTHOR_LINE_EXECUTION_ENABLE
#error "The V44 one-file A4 calibration requires 1 mm Cartesian IK segmentation"
#endif

#if (AUTHOR_TEXT_DEMO_PATH_X_MIN_X10 != 1500) || \
    (AUTHOR_TEXT_DEMO_PATH_X_MAX_X10 != 4160) || \
    (AUTHOR_TEXT_DEMO_PATH_Y_MIN_X10 != -80) || \
    (AUTHOR_TEXT_DEMO_PATH_Y_MAX_X10 != 1420)
#error "The generated V44 calibration left its offline-checked command bounds"
#endif

#if (AUTHOR_TEXT_DEMO_AUX_TOGGLE_MIN_X_X10 != 1500) || \
    (AUTHOR_TEXT_DEMO_PATH_X_MIN_X10 < AUTHOR_TEXT_DEMO_AUX_TOGGLE_MIN_X_X10) || \
    (AUTHOR_TEXT_DEMO_ALIGN_X_X10 < AUTHOR_TEXT_DEMO_AUX_TOGGLE_MIN_X_X10)
#error "The V44 path violated the empirical auxiliary-toggle X guard"
#endif

#if (AUTHOR_TEXT_DEMO_PATH_DRAW_COUNT != 54u) || \
    (AUTHOR_TEXT_DEMO_PATH_MOVE_COUNT != 34u) || \
    ((AUTHOR_TEXT_DEMO_PATH_DRAW_COUNT + AUTHOR_TEXT_DEMO_PATH_MOVE_COUNT) != \
     AUTHOR_TEXT_DEMO_PATH_POINT_COUNT) || \
    (AUTHOR_TEXT_DEMO_ZONE_COUNT != 9u) || \
    (AUTHOR_TEXT_DEMO_STROKE_COUNT != 27u) || \
    (AUTHOR_TEXT_DEMO_MARKER_SIZE_X10 != 200) || \
    (AUTHOR_TEXT_DEMO_RIGHT_BOTTOM_INSET_X10 != 300)
#error "The V44 3x3 square-and-cross path contract changed"
#endif

typedef enum {
    AUTHOR_TEXT_DEMO_EXEC_IDLE = 0,
    AUTHOR_TEXT_DEMO_EXEC_SELECT_POINT,
    AUTHOR_TEXT_DEMO_EXEC_WAIT_PEN_UP,
    AUTHOR_TEXT_DEMO_EXEC_WAIT_PEN_DOWN,
    AUTHOR_TEXT_DEMO_EXEC_WAIT_MOTION,
    AUTHOR_TEXT_DEMO_EXEC_WAIT_ALIGN_PAUSE,
    AUTHOR_TEXT_DEMO_EXEC_WAIT_FINAL_PEN_UP
} author_text_demo_exec_state_t;

typedef enum {
    AUTHOR_TEXT_DEMO_STAGE_NONE = 0,
    AUTHOR_TEXT_DEMO_STAGE_ALIGN,
    AUTHOR_TEXT_DEMO_STAGE_CALIBRATION
} author_text_demo_stage_t;

static author_text_demo_state_t s_state = AUTHOR_TEXT_DEMO_STATE_IDLE;
static author_text_demo_exec_state_t s_exec_state = AUTHOR_TEXT_DEMO_EXEC_IDLE;
static author_text_demo_stage_t s_stage = AUTHOR_TEXT_DEMO_STAGE_NONE;
static const author_text_demo_path_point_t *s_path = 0;
static uint32_t s_path_count = 0u;
static uint32_t s_path_index = 0u;
static uint32_t s_state_start_ms = 0u;
static uint32_t s_setup_mask = 0u;
static uint32_t s_next_probe_index = 0u;
static bool s_pen_is_down = false;

extern volatile uint32_t s_sys_tick;

static int32_t AuthorTextDemo_Scale_100(float value)
{
    return (int32_t)((value >= 0.0f) ?
                     (value * 100.0f + 0.5f) :
                     (value * 100.0f - 0.5f));
}

static const char *AuthorTextDemo_State_Name(void)
{
    switch (s_state) {
        case AUTHOR_TEXT_DEMO_STATE_IDLE:
            return "IDLE";
        case AUTHOR_TEXT_DEMO_STATE_WAIT_ALIGN:
            return "WAIT_ALIGN";
        case AUTHOR_TEXT_DEMO_STATE_RUNNING_ALIGN:
            return "RUNNING_ALIGN";
        case AUTHOR_TEXT_DEMO_STATE_WAIT_CALIBRATION:
            return "WAIT_CALIBRATION";
        case AUTHOR_TEXT_DEMO_STATE_RUNNING_CALIBRATION:
            return "RUNNING_CALIBRATION";
        case AUTHOR_TEXT_DEMO_STATE_DONE:
            return "DONE";
        case AUTHOR_TEXT_DEMO_STATE_STOPPED:
            return "STOPPED";
        case AUTHOR_TEXT_DEMO_STATE_ERROR:
            return "ERROR";
        default:
            return "UNKNOWN";
    }
}

static const char *AuthorTextDemo_Probe_Gate_Name(uint32_t probe_index)
{
    static const char *const gates[AUTHOR_TEXT_DEMO_STAGE_COUNT] = {
        "M891",
    };

    if (probe_index >= AUTHOR_TEXT_DEMO_STAGE_COUNT) {
        return "NONE";
    }
    return gates[probe_index];
}

static bool AuthorTextDemo_Is_Probe_Gate(const char *command)
{
    uint32_t index;

    for (index = 0u; index < AUTHOR_TEXT_DEMO_STAGE_COUNT; index++) {
        if (strcmp(command, AuthorTextDemo_Probe_Gate_Name(index)) == 0) {
            return true;
        }
    }
    return false;
}

static const char *AuthorTextDemo_Action_Name(void)
{
    switch (s_state) {
        case AUTHOR_TEXT_DEMO_STATE_WAIT_ALIGN:
            return "M891";
        case AUTHOR_TEXT_DEMO_STATE_WAIT_CALIBRATION:
            return AuthorTextDemo_Probe_Gate_Name(s_next_probe_index);
        case AUTHOR_TEXT_DEMO_STATE_RUNNING_ALIGN:
        case AUTHOR_TEXT_DEMO_STATE_RUNNING_CALIBRATION:
            return "STOP";
        case AUTHOR_TEXT_DEMO_STATE_IDLE:
        case AUTHOR_TEXT_DEMO_STATE_DONE:
        case AUTHOR_TEXT_DEMO_STATE_STOPPED:
        case AUTHOR_TEXT_DEMO_STATE_ERROR:
            return "NONE";
        default:
            return "NONE";
    }
}

static const char *AuthorTextDemo_Stage_Name(void)
{
    switch (s_stage) {
        case AUTHOR_TEXT_DEMO_STAGE_NONE:
            return "NONE";
        case AUTHOR_TEXT_DEMO_STAGE_ALIGN:
            return "ALIGN";
        case AUTHOR_TEXT_DEMO_STAGE_CALIBRATION:
            return "CALIBRATION";
        default:
            return "NONE";
    }
}

static bool AuthorTextDemo_Is_Running(void)
{
    return (s_state == AUTHOR_TEXT_DEMO_STATE_RUNNING_ALIGN) ||
           (s_state == AUTHOR_TEXT_DEMO_STATE_RUNNING_CALIBRATION);
}

static bool AuthorTextDemo_Limits_Clear(void)
{
    return !App_Stepper_Stage1_IsLimitHit() &&
           !App_Stepper_Stage2_IsLimitHit();
}

static bool AuthorTextDemo_Config_Matches(void)
{
    return (fabsf(APP_WRITER_L1_MM - 205.0f) < 0.0001f) &&
           (fabsf(APP_WRITER_L2_MM - 203.0f) < 0.0001f) &&
           (fabsf(APP_WRITER_MACHINE_OFFSET_X_MM - (-129.0f)) < 0.0001f) &&
           (fabsf(APP_WRITER_MACHINE_OFFSET_Y_MM - 128.0f) < 0.0001f) &&
           (fabsf(APP_WRITER_THETA_LIMIT_DEG - (-0.773082f)) < 0.0001f) &&
           (fabsf(APP_WRITER_PSI_LIMIT_DEG - 134.177381f) < 0.0001f) &&
           (fabsf(APP_WRITER_STAGE1_STEPS_PER_DEG - 40.099216f) <
            0.000001f) &&
           (fabsf(APP_WRITER_STAGE2_STEPS_PER_DEG - 40.115790f) <
            0.000001f) &&
           (fabsf(APP_WRITER_PLAN_SEGMENT_MM - 1.0f) < 0.0001f) &&
           (fabsf(APP_SERVO_PEN_DOWN_ANGLE_DEG - 0.0f) < 0.0001f) &&
           (fabsf(APP_SERVO_PEN_UP_ANGLE_DEG - 90.0f) < 0.0001f) &&
           (APP_WRITER_DIRECTION_COMP_ENABLE == 0u) &&
           (APP_WRITER_DIRECTION_COMP_PRELOAD_ENABLE == 0u) &&
           (APP_WRITER_AUTHOR_LINE_EXECUTION_ENABLE == 0u) &&
           (APP_WRITER_A4_ENVELOPE_PROBE_ENABLE == 1u) &&
           (AUTHOR_TEXT_DEMO_PATH_CRC32 == 0x058FBC5Cu) &&
           (AUTHOR_TEXT_DEMO_PATH_POINT_COUNT == 88u) &&
           (AUTHOR_TEXT_DEMO_PATH_MOVE_COUNT == 34u) &&
           (AUTHOR_TEXT_DEMO_PATH_DRAW_COUNT == 54u) &&
           (AUTHOR_TEXT_DEMO_STAGE_COUNT == 1u) &&
           (AUTHOR_TEXT_DEMO_ZONE_COUNT == 9u) &&
           (AUTHOR_TEXT_DEMO_STROKE_COUNT == 27u) &&
           (AUTHOR_TEXT_DEMO_MARKER_SIZE_X10 == 200) &&
           (AUTHOR_TEXT_DEMO_PAPER_SHIFT_X_X10 == 1360) &&
           (AUTHOR_TEXT_DEMO_PAPER_SHIFT_Y_X10 == -380) &&
           (AUTHOR_TEXT_DEMO_ALIGN_PAPER_X_X10 == 140) &&
           (AUTHOR_TEXT_DEMO_ALIGN_PAPER_Y_X10 == 580) &&
           (AUTHOR_TEXT_DEMO_DRAW_PAPER_X_MIN_X10 == 300) &&
           (AUTHOR_TEXT_DEMO_DRAW_PAPER_X_MAX_X10 == 2800) &&
           (AUTHOR_TEXT_DEMO_DRAW_PAPER_Y_MIN_X10 == 300) &&
           (AUTHOR_TEXT_DEMO_DRAW_PAPER_Y_MAX_X10 == 1800) &&
           (AUTHOR_TEXT_DEMO_RIGHT_BOTTOM_INSET_X10 == 300) &&
           (AUTHOR_TEXT_DEMO_AUX_TOGGLE_MIN_X_X10 == 1500) &&
           (AUTHOR_TEXT_DEMO_CONTOUR_MARGIN_MDEG == 15000) &&
           (AUTHOR_TEXT_DEMO_PATH_MAX_SPAN_X10 == 1403) &&
           (AUTHOR_TEXT_DEMO_MOVE_FEED_MM_MIN == 300.0f) &&
           (AUTHOR_TEXT_DEMO_DRAW_FEED_MM_MIN == 240.0f) &&
           (AUTHOR_TEXT_DEMO_ALIGN_PAUSE_MS == 3000u);
}

static void AuthorTextDemo_Sendf(const char *fmt, ...)
{
    char reply[AUTHOR_TEXT_DEMO_REPLY_MAX];
    va_list args;
    int count;

    va_start(args, fmt);
    count = vsnprintf(reply, sizeof(reply), fmt, args);
    va_end(args);
    if (count <= 0) {
        return;
    }
    if ((uint32_t)count >= sizeof(reply)) {
        count = (int)(sizeof(reply) - 1u);
    }
    App_Vision_UART_Send((const uint8_t *)reply, (uint16_t)count);
}

static bool AuthorTextDemo_Is_At(const author_text_demo_path_point_t *point)
{
    const app_writer_pose_t *pose = WriterMotion_Get_Pose();
    float target_x;
    float target_y;

    if (point == 0) {
        return false;
    }
    target_x = (float)point->x_x10 / 10.0f;
    target_y = (float)point->y_x10 / 10.0f;
    return (fabsf(pose->user_point.x_mm - target_x) <=
            AUTHOR_TEXT_DEMO_POSITION_EPS_MM) &&
           (fabsf(pose->user_point.y_mm - target_y) <=
            AUTHOR_TEXT_DEMO_POSITION_EPS_MM);
}

static void AuthorTextDemo_Fail(const char *reason)
{
    const app_writer_pose_t *pose = WriterMotion_Get_Pose();

    App_Servo_Pen_Up();
    s_pen_is_down = false;
    WriterMotion_Emergency_Stop();
    s_exec_state = AUTHOR_TEXT_DEMO_EXEC_IDLE;
    s_state = AUTHOR_TEXT_DEMO_STATE_ERROR;
    elog_e("TEXTDEMO", "[TEXTDEMO] error=%s stage=%s point=%u/%u user_x=%d user_y=%d lim1=%d lim2=%d pen=UP rehome=1",
           reason,
           AuthorTextDemo_Stage_Name(),
           s_path_index,
           s_path_count,
           AuthorTextDemo_Scale_100(pose->user_point.x_mm),
           AuthorTextDemo_Scale_100(pose->user_point.y_mm),
           App_Stepper_Stage1_IsLimitHit(),
           App_Stepper_Stage2_IsLimitHit());
    AuthorTextDemo_Sendf(
        "error:%s id=%s stage=%s point=%u/%u pen=UP rehome=1\r\n",
        reason,
        AUTHOR_TEXT_DEMO_BUILD_ID,
        AuthorTextDemo_Stage_Name(),
        s_path_index,
        s_path_count);
}

static void AuthorTextDemo_Stop(void)
{
    App_Servo_Pen_Up();
    s_pen_is_down = false;
    WriterMotion_Emergency_Stop();
    s_exec_state = AUTHOR_TEXT_DEMO_EXEC_IDLE;
    s_state = AUTHOR_TEXT_DEMO_STATE_STOPPED;
    AuthorTextDemo_Sendf(
        "ok STOPPED id=%s stage=%s point=%u/%u pen=UP rehome=1\r\n",
        AUTHOR_TEXT_DEMO_BUILD_ID,
        AuthorTextDemo_Stage_Name(),
        s_path_index,
        s_path_count);
}

static void AuthorTextDemo_Send_Status(void)
{
    const app_writer_pose_t *pose = WriterMotion_Get_Pose();

    AuthorTextDemo_Sendf(
        "ok STATUS id=%s state=%s action=%s stage=%s point=%u/%u setup=%u/15 user_x100=%d user_y100=%d lim1=%d lim2=%d pen=%s\r\n",
        AUTHOR_TEXT_DEMO_BUILD_ID,
        AuthorTextDemo_State_Name(),
        AuthorTextDemo_Action_Name(),
        AuthorTextDemo_Stage_Name(),
        s_path_index,
        s_path_count,
        s_setup_mask,
        AuthorTextDemo_Scale_100(pose->user_point.x_mm),
        AuthorTextDemo_Scale_100(pose->user_point.y_mm),
        App_Stepper_Stage1_IsLimitHit(),
        App_Stepper_Stage2_IsLimitHit(),
        s_pen_is_down ? "DOWN" : "UP");
}

static void AuthorTextDemo_Finish_Stage(void)
{
    author_text_demo_stage_t completed = s_stage;
    uint32_t completed_probe_index = s_next_probe_index;

    s_exec_state = AUTHOR_TEXT_DEMO_EXEC_IDLE;
    s_path = 0;
    s_path_count = 0u;
    s_path_index = 0u;
    s_stage = AUTHOR_TEXT_DEMO_STAGE_NONE;
    s_setup_mask = 0u;

    if (completed == AUTHOR_TEXT_DEMO_STAGE_ALIGN) {
        s_next_probe_index = 0u;
        s_state = AUTHOR_TEXT_DEMO_STATE_WAIT_CALIBRATION;
    } else if (completed == AUTHOR_TEXT_DEMO_STAGE_CALIBRATION) {
        s_next_probe_index++;
        s_state = (s_next_probe_index < AUTHOR_TEXT_DEMO_STAGE_COUNT) ?
            AUTHOR_TEXT_DEMO_STATE_WAIT_CALIBRATION :
            AUTHOR_TEXT_DEMO_STATE_DONE;
    } else {
        AuthorTextDemo_Fail("invalid_completed_stage");
        return;
    }

    elog_i("TEXTDEMO", "[TEXTDEMO] stage_done=%s probe=%u/%u next=%s pen=UP%s",
           (completed == AUTHOR_TEXT_DEMO_STAGE_ALIGN) ? "ALIGN" : "CALIBRATION",
           (completed == AUTHOR_TEXT_DEMO_STAGE_ALIGN) ? 0u :
               (completed_probe_index + 1u),
           AUTHOR_TEXT_DEMO_STAGE_COUNT,
           AuthorTextDemo_Action_Name(),
           (s_state == AUTHOR_TEXT_DEMO_STATE_DONE) ? " rehome=1" : "");
    AuthorTextDemo_Sendf(
        "ok STAGE_DONE id=%s completed=%s run=%u/%u state=%s action=%s pen=UP%s\r\n",
        AUTHOR_TEXT_DEMO_BUILD_ID,
        (completed == AUTHOR_TEXT_DEMO_STAGE_ALIGN) ? "ALIGN" : "CALIBRATION",
        (completed == AUTHOR_TEXT_DEMO_STAGE_ALIGN) ? 0u :
            (completed_probe_index + 1u),
        AUTHOR_TEXT_DEMO_STAGE_COUNT,
        AuthorTextDemo_State_Name(),
        AuthorTextDemo_Action_Name(),
        (s_state == AUTHOR_TEXT_DEMO_STATE_DONE) ? " rehome=1" : "");
}

static bool AuthorTextDemo_Start_Stage(
    author_text_demo_stage_t stage,
    author_text_demo_state_t running_state,
    const author_text_demo_path_point_t *path,
    uint32_t point_count)
{
    if ((path == 0) || (point_count == 0u) ||
        !AuthorTextDemo_Limits_Clear() || s_pen_is_down) {
        return false;
    }
    s_stage = stage;
    s_state = running_state;
    s_path = path;
    s_path_count = point_count;
    s_path_index = 0u;
    s_exec_state = AUTHOR_TEXT_DEMO_EXEC_SELECT_POINT;
    s_setup_mask = 0u;
    return true;
}

static void AuthorTextDemo_Update_Path(void)
{
    const author_text_demo_path_point_t *point;
    float feed_mm_min;

    if (!AuthorTextDemo_Is_Running()) {
        return;
    }
    if (!AuthorTextDemo_Limits_Clear()) {
        AuthorTextDemo_Fail("unexpected_limit_active");
        return;
    }

    if (s_exec_state == AUTHOR_TEXT_DEMO_EXEC_WAIT_PEN_UP) {
        if ((uint32_t)(s_sys_tick - s_state_start_ms) <
            AUTHOR_TEXT_DEMO_PEN_SETTLE_MS) {
            return;
        }
        s_pen_is_down = false;
        s_exec_state = AUTHOR_TEXT_DEMO_EXEC_SELECT_POINT;
        return;
    }

    if (s_exec_state == AUTHOR_TEXT_DEMO_EXEC_WAIT_PEN_DOWN) {
        if ((uint32_t)(s_sys_tick - s_state_start_ms) <
            AUTHOR_TEXT_DEMO_PEN_SETTLE_MS) {
            return;
        }
        s_pen_is_down = true;
        s_exec_state = AUTHOR_TEXT_DEMO_EXEC_SELECT_POINT;
        return;
    }

    if (s_exec_state == AUTHOR_TEXT_DEMO_EXEC_WAIT_FINAL_PEN_UP) {
        if ((uint32_t)(s_sys_tick - s_state_start_ms) <
            AUTHOR_TEXT_DEMO_PEN_SETTLE_MS) {
            return;
        }
        s_pen_is_down = false;
        AuthorTextDemo_Finish_Stage();
        return;
    }

    if (s_exec_state == AUTHOR_TEXT_DEMO_EXEC_WAIT_ALIGN_PAUSE) {
        if ((uint32_t)(s_sys_tick - s_state_start_ms) <
            AUTHOR_TEXT_DEMO_ALIGN_PAUSE_MS) {
            return;
        }
        s_exec_state = AUTHOR_TEXT_DEMO_EXEC_SELECT_POINT;
        return;
    }

    if (s_exec_state == AUTHOR_TEXT_DEMO_EXEC_WAIT_MOTION) {
        WriterMotion_Task();
        if (WriterMotion_Is_Busy()) {
            return;
        }
        point = &s_path[s_path_index];
        if (!AuthorTextDemo_Is_At(point)) {
            AuthorTextDemo_Fail("motion_incomplete");
            return;
        }
        s_path_index++;
        if (s_path_index == 1u) {
            s_state_start_ms = s_sys_tick;
            s_exec_state = AUTHOR_TEXT_DEMO_EXEC_WAIT_ALIGN_PAUSE;
        } else {
            s_exec_state = AUTHOR_TEXT_DEMO_EXEC_SELECT_POINT;
        }
        return;
    }

    if (s_exec_state != AUTHOR_TEXT_DEMO_EXEC_SELECT_POINT) {
        AuthorTextDemo_Fail("invalid_executor_state");
        return;
    }

    if (s_path_index >= s_path_count) {
        if (s_pen_is_down) {
            App_Servo_Pen_Up();
            s_state_start_ms = s_sys_tick;
            s_exec_state = AUTHOR_TEXT_DEMO_EXEC_WAIT_FINAL_PEN_UP;
        } else {
            AuthorTextDemo_Finish_Stage();
        }
        return;
    }

    point = &s_path[s_path_index];
    if (point->x_x10 < AUTHOR_TEXT_DEMO_AUX_TOGGLE_MIN_X_X10) {
        AuthorTextDemo_Fail("aux_toggle_x_guard");
        return;
    }

    if ((point->draw != 0u) != s_pen_is_down) {
        if (point->draw != 0u) {
            App_Servo_Pen_Down();
            s_state_start_ms = s_sys_tick;
            s_exec_state = AUTHOR_TEXT_DEMO_EXEC_WAIT_PEN_DOWN;
        } else {
            App_Servo_Pen_Up();
            s_state_start_ms = s_sys_tick;
            s_exec_state = AUTHOR_TEXT_DEMO_EXEC_WAIT_PEN_UP;
        }
        return;
    }

    if (AuthorTextDemo_Is_At(point)) {
        s_path_index++;
        if (s_path_index == 1u) {
            s_state_start_ms = s_sys_tick;
            s_exec_state = AUTHOR_TEXT_DEMO_EXEC_WAIT_ALIGN_PAUSE;
        }
        return;
    }

    feed_mm_min = (point->draw != 0u) ?
        AUTHOR_TEXT_DEMO_DRAW_FEED_MM_MIN :
        AUTHOR_TEXT_DEMO_MOVE_FEED_MM_MIN;
    if (!WriterMotion_Start_To_At_Feed(
            (float)point->x_x10 / 10.0f,
            (float)point->y_x10 / 10.0f,
            feed_mm_min)) {
        AuthorTextDemo_Fail("motion_rejected");
        return;
    }
    s_exec_state = AUTHOR_TEXT_DEMO_EXEC_WAIT_MOTION;
}

void AuthorTextDemo_Start(void)
{
    App_Servo_Pen_Up();
    s_pen_is_down = false;
    s_stage = AUTHOR_TEXT_DEMO_STAGE_NONE;
    s_path = 0;
    s_path_count = 0u;
    s_path_index = 0u;
    s_state_start_ms = 0u;
    s_setup_mask = 0u;
    s_next_probe_index = 0u;
    s_exec_state = AUTHOR_TEXT_DEMO_EXEC_IDLE;

    if (!AuthorTextDemo_Config_Matches()) {
        s_state = AUTHOR_TEXT_DEMO_STATE_ERROR;
        elog_e("TEXTDEMO", "[TEXTDEMO] configuration mismatch motion_locked=1 pen=UP");
        AuthorTextDemo_Sendf(
            "error:configuration_mismatch id=%s motion_locked=1 pen=UP\r\n",
            AUTHOR_TEXT_DEMO_BUILD_ID);
        return;
    }

    WriterMotion_Init_From_Home();
    s_state = AUTHOR_TEXT_DEMO_STATE_WAIT_ALIGN;
    elog_i("TEXTDEMO", "[TEXTDEMO] mode=%s ready trigger=M891_ONEFILE_AUTO_ALIGN_3X3_CALIBRATION_RETURN zones=9 marker=20x20mm strokes=27 move_feed=300 draw_feed=240 align_pause_ms=3000 single_pass=1 gcode=DISABLED dircomp=0 preload=0 pen=UP",
           AUTHOR_TEXT_DEMO_BUILD_ID);
    elog_i("TEXTDEMO", "[TEXTDEMO] A4_photo_axes=XP_UP,YP_LEFT align_machine=(15000,2000) align_paper=(1400,5800) command_from_paper=(+13600,-3800) safe_polygon=(1500,1500),(28100,1500),(28100,16200),(25700,19300),(8200,19300),(1700,14500) draw_paper_bounds=(3000,3000)..(28000,18000) photo_bottom_right_inset=3000 aux_toggle_guard_x_min=15000 points=%u moves=34 draws=54 crc32=058FBC5C",
           AUTHOR_TEXT_DEMO_PATH_POINT_COUNT);
    AuthorTextDemo_Sendf(
        "ok TEXTDEMO READY id=%s state=WAIT_ALIGN action=M891 mode=ONEFILE_AUTO_ALIGN_3X3_CALIBRATION_RETURN zones=9 marker=20x20mm draw_feed=240 status=STATUS emergency=STOP pen=UP\r\n",
        AUTHOR_TEXT_DEMO_BUILD_ID);
}

void AuthorTextDemo_Update(void)
{
    AuthorTextDemo_Update_Path();
}

static bool AuthorTextDemo_Accept_Gate(const char *command)
{
    bool started = false;

    if (s_setup_mask != AUTHOR_TEXT_DEMO_SETUP_ALL) {
        AuthorTextDemo_Sendf(
            "error:setup_incomplete mask=%u required=G21_G90_G94_M5 state=%s pen=UP\r\n",
            s_setup_mask,
            AuthorTextDemo_State_Name());
        return true;
    }
    if (!AuthorTextDemo_Limits_Clear() || s_pen_is_down) {
        AuthorTextDemo_Fail("gate_precondition_failed");
        return true;
    }

    if ((strcmp(command, "M891") == 0) &&
        (s_state == AUTHOR_TEXT_DEMO_STATE_WAIT_ALIGN)) {
        started = AuthorTextDemo_Start_Stage(
            AUTHOR_TEXT_DEMO_STAGE_CALIBRATION,
            AUTHOR_TEXT_DEMO_STATE_RUNNING_CALIBRATION,
            s_author_text_demo_path,
            AUTHOR_TEXT_DEMO_PATH_POINT_COUNT);
    } else {
        AuthorTextDemo_Sendf(
            "error:wrong_gate command=%s state=%s expected=%s pen=UP\r\n",
            command,
            AuthorTextDemo_State_Name(),
            AuthorTextDemo_Action_Name());
        return true;
    }

    if (!started) {
        AuthorTextDemo_Fail("stage_start_rejected");
        return true;
    }
    AuthorTextDemo_Sendf(
        "ok %s accepted id=%s stage=%s points=%u stop=STOP pen=UP\r\n",
        command,
        AUTHOR_TEXT_DEMO_BUILD_ID,
        AuthorTextDemo_Stage_Name(),
        s_path_count);
    return true;
}

bool AuthorTextDemo_Process_Frame(const uint8_t *frame, uint16_t len)
{
    char command[AUTHOR_TEXT_DEMO_COMMAND_MAX];
    uint16_t copy_len;

    if ((frame == 0) || (len == 0u)) {
        return false;
    }
    copy_len = len;
    if (copy_len >= sizeof(command)) {
        copy_len = (uint16_t)(sizeof(command) - 1u);
    }
    memcpy(command, frame, copy_len);
    command[copy_len] = '\0';
    for (uint16_t i = 0u; i < copy_len; i++) {
        if ((command[i] == '\r') || (command[i] == '\n')) {
            command[i] = '\0';
            break;
        }
        command[i] = (char)toupper((unsigned char)command[i]);
    }

    if ((strcmp(command, "STATUS") == 0) ||
        (strcmp(command, "?") == 0)) {
        AuthorTextDemo_Send_Status();
        return true;
    }
    if (strcmp(command, "STOP") == 0) {
        AuthorTextDemo_Stop();
        return true;
    }
    if (AuthorTextDemo_Is_Running()) {
        AuthorTextDemo_Fail("unexpected_uart_while_running");
        return true;
    }
    if ((s_state == AUTHOR_TEXT_DEMO_STATE_DONE) ||
        (s_state == AUTHOR_TEXT_DEMO_STATE_STOPPED) ||
        (s_state == AUTHOR_TEXT_DEMO_STATE_ERROR)) {
        AuthorTextDemo_Sendf(
            "error:reset_required state=%s pen=UP rehome=1\r\n",
            AuthorTextDemo_State_Name());
        return true;
    }

    if (strcmp(command, "G21") == 0) {
        s_setup_mask |= AUTHOR_TEXT_DEMO_SETUP_G21;
        AuthorTextDemo_Sendf("ok G21 setup=%u/15 pen=UP\r\n", s_setup_mask);
        return true;
    }
    if (strcmp(command, "G90") == 0) {
        s_setup_mask |= AUTHOR_TEXT_DEMO_SETUP_G90;
        AuthorTextDemo_Sendf("ok G90 setup=%u/15 pen=UP\r\n", s_setup_mask);
        return true;
    }
    if (strcmp(command, "G94") == 0) {
        s_setup_mask |= AUTHOR_TEXT_DEMO_SETUP_G94;
        AuthorTextDemo_Sendf("ok G94 setup=%u/15 pen=UP\r\n", s_setup_mask);
        return true;
    }
    if (strcmp(command, "M5") == 0) {
        App_Servo_Pen_Up();
        s_pen_is_down = false;
        s_setup_mask |= AUTHOR_TEXT_DEMO_SETUP_M5;
        AuthorTextDemo_Sendf("ok M5 setup=%u/15 pen=UP\r\n", s_setup_mask);
        return true;
    }
    if (AuthorTextDemo_Is_Probe_Gate(command)) {
        return AuthorTextDemo_Accept_Gate(command);
    }

    AuthorTextDemo_Sendf(
        "error:unsupported allowed=G21_G90_G94_M5_%s_STATUS_STOP gcode=DISABLED pen=%s\r\n",
        AuthorTextDemo_Action_Name(),
        s_pen_is_down ? "DOWN" : "UP");
    return true;
}

bool AuthorTextDemo_Is_Done(void)
{
    return (s_state == AUTHOR_TEXT_DEMO_STATE_DONE) ||
           (s_state == AUTHOR_TEXT_DEMO_STATE_STOPPED) ||
           (s_state == AUTHOR_TEXT_DEMO_STATE_ERROR);
}

author_text_demo_state_t AuthorTextDemo_Get_State(void)
{
    return s_state;
}
