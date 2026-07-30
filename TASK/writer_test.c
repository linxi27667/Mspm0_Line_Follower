/**
 * @file    writer_test.c
 * @brief   Writer robot task selector for the retained execution paths.
 */
#include "writer_test.h"
#include "author_text_demo.h"
#include "final_xy_point_test.h"
#include "fixed_layout_axis_mark.h"
#include "fixed_layout_probe.h"
#include "puzzle_area_probe.h"
#include "center_reference_mark.h"
#include "gcode_serial.h"
#include "app_servo.h"
#include "app_stepper.h"
#include "app_puzzle_frame.h"
#include "app_writer_motion.h"
#include "app_writer_paper_map.h"
#include "comm_vision_uart.h"
#include "elog.h"
#include <ctype.h>
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

static writer_test_state_t s_writer_test_state = WRITER_TEST_STATE_IDLE;

#if WRITER_TEST_MODE == WRITER_TEST_MODE_PUZZLE_AREA_PROBE
typedef enum {
    WRITER_PANEL_ACTION_IDLE = 0,
    WRITER_PANEL_ACTION_RECTANGLE,
    WRITER_PANEL_ACTION_ORIGIN
} writer_panel_action_t;

static writer_panel_action_t s_writer_panel_action =
    WRITER_PANEL_ACTION_IDLE;
#endif

#if (WRITER_TEST_MODE == WRITER_TEST_MODE_GCODE_SERIAL) && \
    WRITER_TEST_BOOT_PATROL_4DOT_ENABLE
#define WRITER_BOOT_POINT_COUNT              (4u)
#define WRITER_BOOT_START_DELAY_MS           (3000u)
#define WRITER_BOOT_MOVE_FEED_MM_MIN         (180.0f)
#define WRITER_BOOT_MOVE_LEG_MAX_MM          (140.0f)
#define WRITER_BOOT_POSITION_EPS_MM          (0.20f)
#define WRITER_BOOT_ANGLE_EPS_DEG            (0.20f)
#define WRITER_BOOT_PRE_DOWN_SETTLE_MS       (300u)
#define WRITER_BOOT_DOWN_HOLD_MS             (700u)
#define WRITER_BOOT_UP_SETTLE_MS             (700u)
#define WRITER_BOOT_REPLY_MAX                (256u)
#define WRITER_BOOT_COMMAND_MAX              (16u)

typedef enum {
    WRITER_BOOT_STATE_IDLE = 0,
    WRITER_BOOT_STATE_WAIT_START,
    WRITER_BOOT_STATE_SAFE_MOVE,
    WRITER_BOOT_STATE_SAFE_WAIT,
    WRITER_BOOT_STATE_PATROL_MOVE,
    WRITER_BOOT_STATE_PATROL_WAIT,
    WRITER_BOOT_STATE_MARK_MOVE,
    WRITER_BOOT_STATE_MARK_WAIT,
    WRITER_BOOT_STATE_PRE_DOWN_SETTLE,
    WRITER_BOOT_STATE_DOWN_HOLD,
    WRITER_BOOT_STATE_UP_SETTLE,
    WRITER_BOOT_STATE_DONE,
    WRITER_BOOT_STATE_STOPPED,
    WRITER_BOOT_STATE_ERROR
} writer_boot_state_t;

typedef struct {
    const char *name;
    float paper_x_mm;
    float paper_y_mm;
} writer_boot_point_t;

static const writer_boot_point_t s_writer_boot_points[WRITER_BOOT_POINT_COUNT] = {
    {"LOWER_LEFT",  35.0f,  55.0f},
    {"LOWER_RIGHT", 175.0f, 55.0f},
    {"UPPER_RIGHT", 175.0f, 255.0f},
    {"UPPER_LEFT",  35.0f, 255.0f},
};

extern volatile uint32_t s_sys_tick;

static writer_boot_state_t s_writer_boot_state = WRITER_BOOT_STATE_IDLE;
static uint32_t s_writer_boot_point_index = 0u;
static uint32_t s_writer_boot_mark_count = 0u;
static uint32_t s_writer_boot_state_start_ms = 0u;
static bool s_writer_boot_pen_down = false;
static float s_writer_boot_final_user_x_mm = 0.0f;
static float s_writer_boot_final_user_y_mm = 0.0f;

static int32_t WriterBoot_Scale_100(float value)
{
    return (int32_t)((value >= 0.0f) ?
                     (value * 100.0f + 0.5f) :
                     (value * 100.0f - 0.5f));
}

static const char *WriterBoot_State_Name(void)
{
    switch (s_writer_boot_state) {
        case WRITER_BOOT_STATE_IDLE: return "IDLE";
        case WRITER_BOOT_STATE_WAIT_START: return "WAIT_START";
        case WRITER_BOOT_STATE_SAFE_MOVE: return "SAFE_MOVE";
        case WRITER_BOOT_STATE_SAFE_WAIT: return "SAFE_WAIT";
        case WRITER_BOOT_STATE_PATROL_MOVE: return "PATROL_MOVE";
        case WRITER_BOOT_STATE_PATROL_WAIT: return "PATROL_WAIT";
        case WRITER_BOOT_STATE_MARK_MOVE: return "MARK_MOVE";
        case WRITER_BOOT_STATE_MARK_WAIT: return "MARK_WAIT";
        case WRITER_BOOT_STATE_PRE_DOWN_SETTLE: return "PRE_DOWN_SETTLE";
        case WRITER_BOOT_STATE_DOWN_HOLD: return "DOWN_HOLD";
        case WRITER_BOOT_STATE_UP_SETTLE: return "UP_SETTLE";
        case WRITER_BOOT_STATE_DONE: return "DONE";
        case WRITER_BOOT_STATE_STOPPED: return "STOPPED";
        case WRITER_BOOT_STATE_ERROR: return "ERROR";
        default: return "UNKNOWN";
    }
}

static bool WriterBoot_Is_Terminal(void)
{
    return (s_writer_boot_state == WRITER_BOOT_STATE_DONE) ||
           (s_writer_boot_state == WRITER_BOOT_STATE_STOPPED) ||
           (s_writer_boot_state == WRITER_BOOT_STATE_ERROR);
}

static bool WriterBoot_Limits_Clear(void)
{
    return !App_Stepper_Stage1_IsLimitHit() &&
           !App_Stepper_Stage2_IsLimitHit();
}

static bool WriterBoot_Point_To_User(const writer_boot_point_t *point,
                                     float *user_x_mm,
                                     float *user_y_mm)
{
    if ((point == NULL) || (user_x_mm == NULL) || (user_y_mm == NULL) ||
        !WriterPaperMap_To_User(point->paper_x_mm, point->paper_y_mm,
                               user_x_mm, user_y_mm)) {
        return false;
    }
    *user_x_mm += GCODE_SERIAL_WORKSPACE_SHIFT_X_MM;
    *user_y_mm += GCODE_SERIAL_WORKSPACE_SHIFT_Y_MM;
    return true;
}

static void WriterBoot_Sendf(const char *format, ...)
{
    char reply[WRITER_BOOT_REPLY_MAX];
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

static void WriterBoot_Fail(const char *reason)
{
    App_Servo_Pen_Up();
    s_writer_boot_pen_down = false;
    WriterMotion_Emergency_Stop();
    s_writer_boot_state = WRITER_BOOT_STATE_ERROR;
    elog_e("BOOT_DOT", "[BOOT_DOT] result=ERROR reason=%s point=%u/%u marks=%u/%u lim1=%d lim2=%d pen=UP needs_rehome=1",
           reason,
           s_writer_boot_point_index + 1u,
           WRITER_BOOT_POINT_COUNT,
           s_writer_boot_mark_count,
           WRITER_BOOT_POINT_COUNT,
           App_Stepper_Stage1_IsLimitHit(),
           App_Stepper_Stage2_IsLimitHit());
    WriterBoot_Sendf(
        "error:%s id=%s state=ERROR point=%u/%u marks=%u/%u pen=UP needs_rehome=1\r\n",
        reason,
        WRITER_TEST_BOOT_PATROL_4DOT_BUILD_ID,
        s_writer_boot_point_index + 1u,
        WRITER_BOOT_POINT_COUNT,
        s_writer_boot_mark_count,
        WRITER_BOOT_POINT_COUNT);
}

static void WriterBoot_Stop(void)
{
    App_Servo_Pen_Up();
    s_writer_boot_pen_down = false;
    WriterMotion_Emergency_Stop();
    s_writer_boot_state = WRITER_BOOT_STATE_STOPPED;
    elog_w("BOOT_DOT", "[BOOT_DOT] result=STOPPED point=%u/%u marks=%u/%u pen=UP needs_rehome=1",
           s_writer_boot_point_index + 1u,
           WRITER_BOOT_POINT_COUNT,
           s_writer_boot_mark_count,
           WRITER_BOOT_POINT_COUNT);
    WriterBoot_Sendf(
        "ok STOPPED id=%s point=%u/%u marks=%u/%u pen=UP needs_rehome=1\r\n",
        WRITER_TEST_BOOT_PATROL_4DOT_BUILD_ID,
        s_writer_boot_point_index + 1u,
        WRITER_BOOT_POINT_COUNT,
        s_writer_boot_mark_count,
        WRITER_BOOT_POINT_COUNT);
}

static void WriterBoot_Send_Status(void)
{
    const writer_boot_point_t *point =
        &s_writer_boot_points[s_writer_boot_point_index];

    WriterBoot_Sendf(
        "ok STATUS id=%s state=%s point=%u/%u name=%s paper_x100=%d paper_y100=%d marks=%u/%u busy=%u lim1=%d lim2=%d pen=%s\r\n",
        WRITER_TEST_BOOT_PATROL_4DOT_BUILD_ID,
        WriterBoot_State_Name(),
        s_writer_boot_point_index + 1u,
        WRITER_BOOT_POINT_COUNT,
        point->name,
        WriterBoot_Scale_100(point->paper_x_mm),
        WriterBoot_Scale_100(point->paper_y_mm),
        s_writer_boot_mark_count,
        WRITER_BOOT_POINT_COUNT,
        WriterMotion_Is_Busy() ? 1u : 0u,
        App_Stepper_Stage1_IsLimitHit(),
        App_Stepper_Stage2_IsLimitHit(),
        s_writer_boot_pen_down ? "DOWN" : "UP");
}

static bool WriterBoot_Is_At(const writer_boot_point_t *point)
{
    const app_writer_pose_t *pose = WriterMotion_Get_Pose();
    float user_x_mm;
    float user_y_mm;

    return WriterBoot_Point_To_User(point, &user_x_mm, &user_y_mm) &&
           (fabsf(pose->user_point.x_mm - user_x_mm) <=
            WRITER_BOOT_POSITION_EPS_MM) &&
           (fabsf(pose->user_point.y_mm - user_y_mm) <=
            WRITER_BOOT_POSITION_EPS_MM);
}

static bool WriterBoot_Start_Move_Leg(writer_boot_state_t wait_state)
{
    const app_writer_pose_t *pose = WriterMotion_Get_Pose();
    float delta_x = s_writer_boot_final_user_x_mm - pose->user_point.x_mm;
    float delta_y = s_writer_boot_final_user_y_mm - pose->user_point.y_mm;
    float span = fmaxf(fabsf(delta_x), fabsf(delta_y));
    float ratio = (span > WRITER_BOOT_MOVE_LEG_MAX_MM) ?
                  (WRITER_BOOT_MOVE_LEG_MAX_MM / span) : 1.0f;
    float leg_x = pose->user_point.x_mm + delta_x * ratio;
    float leg_y = pose->user_point.y_mm + delta_y * ratio;

    elog_i("BOOT_DOT", "[BOOT_DOT] action=MOVE_LEG from_x=%d from_y=%d leg_x=%d leg_y=%d final_x=%d final_y=%d span=%d pen=UP",
           WriterBoot_Scale_100(pose->user_point.x_mm),
           WriterBoot_Scale_100(pose->user_point.y_mm),
           WriterBoot_Scale_100(leg_x),
           WriterBoot_Scale_100(leg_y),
           WriterBoot_Scale_100(s_writer_boot_final_user_x_mm),
           WriterBoot_Scale_100(s_writer_boot_final_user_y_mm),
           WriterBoot_Scale_100(span));
    if (!WriterMotion_Start_To_At_Feed(
            leg_x, leg_y, WRITER_BOOT_MOVE_FEED_MM_MIN)) {
        WriterBoot_Fail("move_leg_rejected");
        return false;
    }
    s_writer_boot_state = wait_state;
    return true;
}

static bool WriterBoot_Start_Move(const char *phase,
                                  writer_boot_state_t wait_state)
{
    const writer_boot_point_t *point =
        &s_writer_boot_points[s_writer_boot_point_index];
    float user_x_mm;
    float user_y_mm;

    if (!WriterBoot_Point_To_User(point, &user_x_mm, &user_y_mm)) {
        WriterBoot_Fail("paper_map_rejected");
        return false;
    }
    elog_i("BOOT_DOT", "[BOOT_DOT] phase=%s point=%u/%u name=%s paper_x=%d paper_y=%d map=EXTRAPOLATED user_x=%d user_y=%d pen=UP",
           phase,
           s_writer_boot_point_index + 1u,
           WRITER_BOOT_POINT_COUNT,
           point->name,
           WriterBoot_Scale_100(point->paper_x_mm),
           WriterBoot_Scale_100(point->paper_y_mm),
           WriterBoot_Scale_100(user_x_mm),
           WriterBoot_Scale_100(user_y_mm));
    s_writer_boot_final_user_x_mm = user_x_mm;
    s_writer_boot_final_user_y_mm = user_y_mm;
    s_writer_boot_state = wait_state;
    return WriterBoot_Start_Move_Leg(wait_state);
}

static void WriterBoot_Start(void)
{
    uint32_t index;
    float user_x_mm;
    float user_y_mm;

    App_Servo_Pen_Up();
    s_writer_boot_pen_down = false;
    s_writer_boot_point_index = 0u;
    s_writer_boot_mark_count = 0u;
    s_writer_boot_state_start_ms = s_sys_tick;
    s_writer_boot_final_user_x_mm = 0.0f;
    s_writer_boot_final_user_y_mm = 0.0f;
    for (index = 0u; index < WRITER_BOOT_POINT_COUNT; index++) {
        if (!WriterBoot_Point_To_User(
                &s_writer_boot_points[index], &user_x_mm, &user_y_mm)) {
            WriterBoot_Fail("configuration_point_rejected");
            return;
        }
    }
    if (!WriterBoot_Limits_Clear()) {
        WriterBoot_Fail("startup_limit_active");
        return;
    }
    s_writer_boot_state = WRITER_BOOT_STATE_WAIT_START;
    elog_w("BOOT_DOT", "[BOOT_DOT] id=%s autonomous=1 start_delay_ms=%u sequence=PATROL_UP_THEN_4DOT points=(35,55),(175,55),(175,255),(35,255) feed=%d stop=STOP pen=UP cloud_locked=1",
           WRITER_TEST_BOOT_PATROL_4DOT_BUILD_ID,
           WRITER_BOOT_START_DELAY_MS,
           WriterBoot_Scale_100(WRITER_BOOT_MOVE_FEED_MM_MIN));
    WriterBoot_Sendf(
        "ok BOOT_DOT READY id=%s delay_ms=%u sequence=PATROL_UP_THEN_4DOT status=STATUS emergency=STOP pen=UP cloud_locked=1\r\n",
        WRITER_TEST_BOOT_PATROL_4DOT_BUILD_ID,
        WRITER_BOOT_START_DELAY_MS);
}

static void WriterBoot_Update(void)
{
    const writer_boot_point_t *point;

    if (WriterBoot_Is_Terminal() ||
        (s_writer_boot_state == WRITER_BOOT_STATE_IDLE)) {
        return;
    }
    if (!WriterBoot_Limits_Clear()) {
        WriterBoot_Fail("runtime_limit_active");
        return;
    }
    point = &s_writer_boot_points[s_writer_boot_point_index];
    switch (s_writer_boot_state) {
        case WRITER_BOOT_STATE_WAIT_START:
            if ((uint32_t)(s_sys_tick - s_writer_boot_state_start_ms) <
                WRITER_BOOT_START_DELAY_MS) {
                return;
            }
            s_writer_boot_state = WRITER_BOOT_STATE_SAFE_MOVE;
            return;

        case WRITER_BOOT_STATE_SAFE_MOVE:
            elog_i("BOOT_DOT", "[BOOT_DOT] phase=SAFE_WAYPOINT theta=%d psi=%d pen=UP",
                   WriterBoot_Scale_100(
                       APP_WRITER_SAFE_WAYPOINT_THETA_DEG),
                   WriterBoot_Scale_100(
                       APP_WRITER_SAFE_WAYPOINT_PSI_DEG));
            if (!WriterMotion_Start_Joints(
                    APP_WRITER_SAFE_WAYPOINT_THETA_DEG,
                    APP_WRITER_SAFE_WAYPOINT_PSI_DEG)) {
                WriterBoot_Fail("safe_waypoint_rejected");
                return;
            }
            s_writer_boot_state = WRITER_BOOT_STATE_SAFE_WAIT;
            return;

        case WRITER_BOOT_STATE_SAFE_WAIT:
            WriterMotion_Task();
            if (WriterMotion_Is_Busy()) {
                return;
            }
            {
                const app_writer_pose_t *pose = WriterMotion_Get_Pose();

                if ((fabsf(pose->angles.theta_deg -
                           APP_WRITER_SAFE_WAYPOINT_THETA_DEG) >
                     WRITER_BOOT_ANGLE_EPS_DEG) ||
                    (fabsf(pose->angles.psi_deg -
                           APP_WRITER_SAFE_WAYPOINT_PSI_DEG) >
                     WRITER_BOOT_ANGLE_EPS_DEG)) {
                    WriterBoot_Fail("safe_waypoint_incomplete");
                    return;
                }
            }
            s_writer_boot_state = WRITER_BOOT_STATE_PATROL_MOVE;
            return;

        case WRITER_BOOT_STATE_PATROL_MOVE:
            (void)WriterBoot_Start_Move(
                "PATROL", WRITER_BOOT_STATE_PATROL_WAIT);
            return;

        case WRITER_BOOT_STATE_PATROL_WAIT:
            WriterMotion_Task();
            if (WriterMotion_Is_Busy()) {
                return;
            }
            if (!WriterBoot_Is_At(point)) {
                (void)WriterBoot_Start_Move_Leg(
                    WRITER_BOOT_STATE_PATROL_WAIT);
                return;
            }
            if ((s_writer_boot_point_index + 1u) <
                WRITER_BOOT_POINT_COUNT) {
                s_writer_boot_point_index++;
                s_writer_boot_state = WRITER_BOOT_STATE_PATROL_MOVE;
            } else {
                s_writer_boot_point_index = 0u;
                s_writer_boot_state = WRITER_BOOT_STATE_MARK_MOVE;
                elog_i("BOOT_DOT", "[BOOT_DOT] phase=PATROL result=COMPLETED points=4 pen=UP next=4DOT");
            }
            return;

        case WRITER_BOOT_STATE_MARK_MOVE:
            (void)WriterBoot_Start_Move(
                "MARK_APPROACH", WRITER_BOOT_STATE_MARK_WAIT);
            return;

        case WRITER_BOOT_STATE_MARK_WAIT:
            WriterMotion_Task();
            if (WriterMotion_Is_Busy()) {
                return;
            }
            if (!WriterBoot_Is_At(point)) {
                (void)WriterBoot_Start_Move_Leg(
                    WRITER_BOOT_STATE_MARK_WAIT);
                return;
            }
            s_writer_boot_state_start_ms = s_sys_tick;
            s_writer_boot_state = WRITER_BOOT_STATE_PRE_DOWN_SETTLE;
            return;

        case WRITER_BOOT_STATE_PRE_DOWN_SETTLE:
            if ((uint32_t)(s_sys_tick - s_writer_boot_state_start_ms) <
                WRITER_BOOT_PRE_DOWN_SETTLE_MS) {
                return;
            }
            App_Servo_Pen_Down();
            s_writer_boot_pen_down = true;
            s_writer_boot_state_start_ms = s_sys_tick;
            s_writer_boot_state = WRITER_BOOT_STATE_DOWN_HOLD;
            elog_i("BOOT_DOT", "[BOOT_DOT] action=PEN_DOWN point=%u/%u name=%s paper_x=%d paper_y=%d hold_ms=%u",
                   s_writer_boot_point_index + 1u,
                   WRITER_BOOT_POINT_COUNT,
                   point->name,
                   WriterBoot_Scale_100(point->paper_x_mm),
                   WriterBoot_Scale_100(point->paper_y_mm),
                   WRITER_BOOT_DOWN_HOLD_MS);
            return;

        case WRITER_BOOT_STATE_DOWN_HOLD:
            if ((uint32_t)(s_sys_tick - s_writer_boot_state_start_ms) <
                WRITER_BOOT_DOWN_HOLD_MS) {
                return;
            }
            App_Servo_Pen_Up();
            s_writer_boot_pen_down = false;
            s_writer_boot_mark_count++;
            s_writer_boot_state_start_ms = s_sys_tick;
            s_writer_boot_state = WRITER_BOOT_STATE_UP_SETTLE;
            elog_i("BOOT_DOT", "[BOOT_DOT] action=PEN_UP point=%u/%u marks=%u/%u settle_ms=%u",
                   s_writer_boot_point_index + 1u,
                   WRITER_BOOT_POINT_COUNT,
                   s_writer_boot_mark_count,
                   WRITER_BOOT_POINT_COUNT,
                   WRITER_BOOT_UP_SETTLE_MS);
            return;

        case WRITER_BOOT_STATE_UP_SETTLE:
            if ((uint32_t)(s_sys_tick - s_writer_boot_state_start_ms) <
                WRITER_BOOT_UP_SETTLE_MS) {
                return;
            }
            if ((s_writer_boot_point_index + 1u) <
                WRITER_BOOT_POINT_COUNT) {
                s_writer_boot_point_index++;
                s_writer_boot_state = WRITER_BOOT_STATE_MARK_MOVE;
            } else if (s_writer_boot_mark_count == WRITER_BOOT_POINT_COUNT) {
                s_writer_boot_state = WRITER_BOOT_STATE_DONE;
                elog_i("BOOT_DOT", "[BOOT_DOT] result=COMPLETED patrol_points=4 marks=4 pen=UP cloud_locked=0 gcode_ready=1");
                WriterBoot_Sendf(
                    "ok BOOT_DOT DONE id=%s patrol_points=4 marks=4 pen=UP cloud_locked=0 gcode_ready=1\r\n",
                    WRITER_TEST_BOOT_PATROL_4DOT_BUILD_ID);
            } else {
                WriterBoot_Fail("mark_count_mismatch");
            }
            return;

        case WRITER_BOOT_STATE_IDLE:
        case WRITER_BOOT_STATE_DONE:
        case WRITER_BOOT_STATE_STOPPED:
        case WRITER_BOOT_STATE_ERROR:
        default:
            return;
    }
}

static bool WriterBoot_Process_Frame(const uint8_t *frame, uint16_t len)
{
    char command[WRITER_BOOT_COMMAND_MAX];
    uint16_t start = 0u;
    uint16_t end = len;
    uint16_t index;

    if ((frame == NULL) || (len == 0u)) {
        return false;
    }
    while ((start < end) && isspace((unsigned char)frame[start])) {
        start++;
    }
    while ((end > start) && isspace((unsigned char)frame[end - 1u])) {
        end--;
    }
    if ((end - start) >= sizeof(command)) {
        WriterBoot_Sendf("error:command_too_long id=%s\r\n",
                         WRITER_TEST_BOOT_PATROL_4DOT_BUILD_ID);
        return true;
    }
    for (index = 0u; index < (uint16_t)(end - start); index++) {
        command[index] = (char)toupper((unsigned char)frame[start + index]);
    }
    command[end - start] = '\0';
    if ((strcmp(command, "STATUS") == 0) || (strcmp(command, "?") == 0)) {
        WriterBoot_Send_Status();
        return true;
    }
    if (strcmp(command, "STOP") == 0) {
        if (!WriterBoot_Is_Terminal()) {
            WriterBoot_Stop();
        } else {
            WriterBoot_Send_Status();
        }
        return true;
    }
    WriterBoot_Sendf(
        "error:startup_test_busy id=%s state=%s allowed=STATUS_STOP pen=%s\r\n",
        WRITER_TEST_BOOT_PATROL_4DOT_BUILD_ID,
        WriterBoot_State_Name(),
        s_writer_boot_pen_down ? "DOWN" : "UP");
    return true;
}
#endif

#if APP_WRITER_A4_ENVELOPE_PROBE_ENABLE && \
    (WRITER_TEST_MODE != WRITER_TEST_MODE_AUTHOR_TEXT_DEMO) && \
    (WRITER_TEST_MODE != WRITER_TEST_MODE_FINAL_XY_POINT_DOTS) && \
    (WRITER_TEST_MODE != WRITER_TEST_MODE_FIXED_LAYOUT_PROBE) && \
    (WRITER_TEST_MODE != WRITER_TEST_MODE_FIXED_LAYOUT_AXIS_MARK) && \
    (WRITER_TEST_MODE != WRITER_TEST_MODE_PUZZLE_AREA_PROBE) && \
    !((WRITER_TEST_MODE == WRITER_TEST_MODE_GCODE_SERIAL) && \
      (GCODE_SERIAL_RESTRICTED_RECT_ENABLE || \
       GCODE_SERIAL_PAPER_CALIBRATION_ENABLE))
#error "Measured envelope requires a gated, offline-checked task"
#endif

void WriterTest_Start(void)
{
    s_writer_test_state = WRITER_TEST_STATE_RUNNING;

#if WRITER_TEST_MODE == WRITER_TEST_MODE_FINAL_XY_POINT_DOTS
    elog_i("TEST", "[TEST] mode=%s source=UART_GATED stages=ALIGN_DOTS unique_points=5 marks=9 gcode=DISABLED dircomp=0 single_pass=1",
           FINAL_XY_POINT_TEST_BUILD_ID);
    FinalXYPointTest_Start();
#elif WRITER_TEST_MODE == WRITER_TEST_MODE_AUTHOR_TEXT_DEMO
    elog_i("TEST", "[TEST] mode=%s source=UART_ONEFILE trigger=M891 stages=AUTO_ALIGN_3X3_CALIBRATION_RETURN path=A4_3X3_20MM_SQUARE_CROSS_DRAW gcode=DISABLED dircomp=0 preload=0 single_pass=1",
           AUTHOR_TEXT_DEMO_BUILD_ID);
    AuthorTextDemo_Start();
#elif WRITER_TEST_MODE == WRITER_TEST_MODE_FIXED_LAYOUT_PROBE
    elog_i("TEST", "[TEST] mode=%s source=UART_GATED stages=ALIGN_XY10 "
           "paper_frame=UNSET gcode=DISABLED pen=UP single_pass=1",
           FIXED_LAYOUT_PROBE_BUILD_ID);
    FixedLayoutProbe_Start();
#elif WRITER_TEST_MODE == WRITER_TEST_MODE_FIXED_LAYOUT_AXIS_MARK
    elog_i("TEST", "[TEST] mode=%s source=UART_GATED "
           "paper=A4_210X297 test=Y_RANGE_3RECT square_mm=(20,20) "
           "stages=ONEFILE_AUTO_MOVE_DRAW_3RECT "
           "calibration=V17_MEASURED_LOCAL_AFFINE_V18 x_unchanged=1 "
           "first_waypoint=(22000,0) "
           "paper_y_limit_mm=20_130 "
           "trigger=M801 gcode=DISABLED regions=3 single_pass=1",
           FIXED_LAYOUT_AXIS_MARK_BUILD_ID);
    FixedLayoutAxisMark_Start();
#elif WRITER_TEST_MODE == WRITER_TEST_MODE_PUZZLE_AREA_PROBE
    s_writer_panel_action = WRITER_PANEL_ACTION_IDLE;
    elog_i("TEST", "[TEST] mode=%s source=KEY2_OR_M850 "
           "machine_home=%s paper_zero=P4 paper_frame=%s "
           "axes=X_RIGHT_Y_DOWN "
           "paper_points_mm=0_0__199_0__160_243__40_243 "
           "legacy_cal=P1_-9_-10_P2_191p5_-24_"
           "P3_191p5_231_P4_0_230 "
           "calibration=PHOTO_TRI_MESH_24NODE_31TRI_4ROW_ALIGN "
           "route=P4_P3_SAFE_BR_SAFE_BL_P4 marks=4 lines=0 "
           "divider=DISABLED_CORNER_CAL "
           "tool=UP_AFTER_EACH_MARK gcode=DISABLED single_pass=1",
           PUZZLE_AREA_PROBE_BUILD_ID,
           APP_PUZZLE_MACHINE_HOME_TEXT,
           APP_PUZZLE_PAPER_FRAME_TEXT);
    PuzzleAreaProbe_Start();
#elif WRITER_TEST_MODE == WRITER_TEST_MODE_GCODE_SERIAL
    elog_i("TEST", "[TEST] mode=%s host=STANDARD_GCODE "
           "paper_calibration=%u restricted_rect=%u boot_patrol_4dot=%u single_pass=1",
           GCODE_SERIAL_BUILD_ID,
           GCODE_SERIAL_PAPER_CALIBRATION_ENABLE,
           GCODE_SERIAL_RESTRICTED_RECT_ENABLE,
           WRITER_TEST_BOOT_PATROL_4DOT_ENABLE);
    GCodeSerial_Start();
#if WRITER_TEST_BOOT_PATROL_4DOT_ENABLE
    WriterBoot_Start();
#endif
#endif
}

bool WriterTest_Trigger_Puzzle_Area_Marks(void)
{
#if WRITER_TEST_MODE == WRITER_TEST_MODE_PUZZLE_AREA_PROBE
    if ((s_writer_panel_action == WRITER_PANEL_ACTION_ORIGIN) &&
        !CenterReferenceMark_Is_Done()) {
        return false;
    }
    if (!PuzzleAreaProbe_Trigger()) {
        return false;
    }
    s_writer_panel_action = WRITER_PANEL_ACTION_RECTANGLE;
    s_writer_test_state = WRITER_TEST_STATE_RUNNING;
    return true;
#else
    return false;
#endif
}

bool WriterTest_Trigger_Paper_Origin_Mark(void)
{
#if WRITER_TEST_MODE == WRITER_TEST_MODE_PUZZLE_AREA_PROBE
    puzzle_area_probe_state_t area_state =
        PuzzleAreaProbe_Get_State();

    if ((area_state != PUZZLE_AREA_PROBE_STATE_WAIT_TRIGGER) &&
        (area_state != PUZZLE_AREA_PROBE_STATE_DONE)) {
        return false;
    }
    if (!CenterReferenceMark_Start()) {
        return false;
    }
    s_writer_panel_action = WRITER_PANEL_ACTION_ORIGIN;
    s_writer_test_state = WRITER_TEST_STATE_RUNNING;
    return true;
#else
    return false;
#endif
}

void WriterTest_Abort_For_Rehome(void)
{
    App_Servo_Pen_Up();
    WriterMotion_Emergency_Stop();
#if WRITER_TEST_MODE == WRITER_TEST_MODE_PUZZLE_AREA_PROBE
    PuzzleAreaProbe_Abort_For_Rehome();
    CenterReferenceMark_Abort_For_Rehome();
    s_writer_panel_action = WRITER_PANEL_ACTION_IDLE;
#endif
    s_writer_test_state = WRITER_TEST_STATE_IDLE;
}

void WriterTest_Update(void)
{
    if (s_writer_test_state != WRITER_TEST_STATE_RUNNING) {
        return;
    }

#if WRITER_TEST_MODE == WRITER_TEST_MODE_FINAL_XY_POINT_DOTS
    FinalXYPointTest_Update();
    if (FinalXYPointTest_Is_Done()) {
        final_xy_point_test_state_t point_state =
            FinalXYPointTest_Get_State();
        s_writer_test_state = WRITER_TEST_STATE_DONE;
        if (point_state == FINAL_XY_POINT_TEST_STATE_DONE) {
            elog_i("TEST", "[TEST] mode=%s done rehome=1",
                   FINAL_XY_POINT_TEST_BUILD_ID);
        } else {
            elog_e("TEST", "[TEST] mode=%s stopped state=%u rehome=1",
                   FINAL_XY_POINT_TEST_BUILD_ID,
                   (uint32_t)point_state);
        }
    }
#elif WRITER_TEST_MODE == WRITER_TEST_MODE_AUTHOR_TEXT_DEMO
    AuthorTextDemo_Update();
    if (AuthorTextDemo_Is_Done()) {
        author_text_demo_state_t demo_state = AuthorTextDemo_Get_State();
        s_writer_test_state = WRITER_TEST_STATE_DONE;
        if (demo_state == AUTHOR_TEXT_DEMO_STATE_DONE) {
            elog_i("TEST", "[TEST] mode=%s done rehome=1",
                   AUTHOR_TEXT_DEMO_BUILD_ID);
        } else {
            elog_e("TEST", "[TEST] mode=%s stopped state=%u rehome=1",
                   AUTHOR_TEXT_DEMO_BUILD_ID,
                   (uint32_t)demo_state);
        }
    }
#elif WRITER_TEST_MODE == WRITER_TEST_MODE_FIXED_LAYOUT_PROBE
    FixedLayoutProbe_Update();
    if (FixedLayoutProbe_Is_Done()) {
        fixed_layout_probe_state_t probe_state =
            FixedLayoutProbe_Get_State();
        s_writer_test_state = WRITER_TEST_STATE_DONE;
        if (probe_state == FIXED_LAYOUT_PROBE_STATE_DONE) {
            elog_i("TEST", "[TEST] mode=%s done rehome=1",
                   FIXED_LAYOUT_PROBE_BUILD_ID);
        } else {
            elog_e("TEST", "[TEST] mode=%s stopped state=%u rehome=1",
                   FIXED_LAYOUT_PROBE_BUILD_ID,
                   (uint32_t)probe_state);
        }
    }
#elif WRITER_TEST_MODE == WRITER_TEST_MODE_FIXED_LAYOUT_AXIS_MARK
    FixedLayoutAxisMark_Update();
    if (FixedLayoutAxisMark_Is_Done()) {
        fixed_layout_axis_mark_state_t mark_state =
            FixedLayoutAxisMark_Get_State();
        s_writer_test_state = WRITER_TEST_STATE_DONE;
        if (mark_state == FIXED_LAYOUT_AXIS_MARK_STATE_DONE) {
            elog_i("TEST", "[TEST] mode=%s done rehome=1",
                   FIXED_LAYOUT_AXIS_MARK_BUILD_ID);
        } else {
            elog_e("TEST", "[TEST] mode=%s stopped state=%u rehome=1",
                   FIXED_LAYOUT_AXIS_MARK_BUILD_ID,
                   (uint32_t)mark_state);
        }
    }
#elif WRITER_TEST_MODE == WRITER_TEST_MODE_PUZZLE_AREA_PROBE
    if (s_writer_panel_action == WRITER_PANEL_ACTION_ORIGIN) {
        CenterReferenceMark_Update();
        if (CenterReferenceMark_Is_Done()) {
            center_reference_mark_state_t origin_state =
                CenterReferenceMark_Get_State();

            s_writer_test_state = WRITER_TEST_STATE_DONE;
            if (origin_state == CENTER_REFERENCE_MARK_STATE_DONE) {
                elog_i("TEST",
                       "[TEST] mode=%s origin_mark_done rehome=0",
                       CENTER_REFERENCE_MARK_BUILD_ID);
            } else {
                elog_e("TEST",
                       "[TEST] mode=%s origin_mark_stopped state=%u "
                       "rehome=1",
                       CENTER_REFERENCE_MARK_BUILD_ID,
                       (uint32_t)origin_state);
            }
        }
        return;
    }
    PuzzleAreaProbe_Update();
    if (PuzzleAreaProbe_Is_Done()) {
        puzzle_area_probe_state_t area_state =
            PuzzleAreaProbe_Get_State();
        s_writer_test_state = WRITER_TEST_STATE_DONE;
        if (area_state == PUZZLE_AREA_PROBE_STATE_DONE) {
            elog_i("TEST", "[TEST] mode=%s done rehome=1",
                   PUZZLE_AREA_PROBE_BUILD_ID);
        } else {
            elog_e("TEST", "[TEST] mode=%s stopped state=%u rehome=1",
                   PUZZLE_AREA_PROBE_BUILD_ID,
                   (uint32_t)area_state);
        }
    }
#elif WRITER_TEST_MODE == WRITER_TEST_MODE_GCODE_SERIAL
#if WRITER_TEST_BOOT_PATROL_4DOT_ENABLE
    if (!WriterBoot_Is_Terminal()) {
        WriterBoot_Update();
        return;
    }
#endif
    GCodeSerial_Update();
#endif
}

bool WriterTest_Process_Serial_Frame(const uint8_t *frame, uint16_t len)
{
#if WRITER_TEST_MODE == WRITER_TEST_MODE_FINAL_XY_POINT_DOTS
    /* Keep STATUS and STOP available after the point test terminates. */
    return FinalXYPointTest_Process_Frame(frame, len);
#elif WRITER_TEST_MODE == WRITER_TEST_MODE_AUTHOR_TEXT_DEMO
    /* Keep STATUS and STOP available after the staged demo terminates. */
    return AuthorTextDemo_Process_Frame(frame, len);
#elif WRITER_TEST_MODE == WRITER_TEST_MODE_FIXED_LAYOUT_PROBE
    /* Keep STATUS and STOP available after the probe terminates. */
    return FixedLayoutProbe_Process_Frame(frame, len);
#elif WRITER_TEST_MODE == WRITER_TEST_MODE_FIXED_LAYOUT_AXIS_MARK
    /* Keep STATUS and STOP available after the mark task terminates. */
    return FixedLayoutAxisMark_Process_Frame(frame, len);
#elif WRITER_TEST_MODE == WRITER_TEST_MODE_PUZZLE_AREA_PROBE
    bool handled = PuzzleAreaProbe_Process_Frame(frame, len);

    /*
     * A serial MOVE/DOT may rearm the puzzle task after a completed KEY2 run.
     * Restore the top-level updater as soon as the puzzle state is nonterminal.
     */
    if (handled && !PuzzleAreaProbe_Is_Done()) {
        s_writer_panel_action = WRITER_PANEL_ACTION_RECTANGLE;
        s_writer_test_state = WRITER_TEST_STATE_RUNNING;
    }
    return handled;
#elif WRITER_TEST_MODE == WRITER_TEST_MODE_GCODE_SERIAL
    if (s_writer_test_state != WRITER_TEST_STATE_RUNNING) {
        elog_w("TEST", "[TEST] serial frame ignored before writer test start len=%u", len);
        return false;
    }
#if WRITER_TEST_BOOT_PATROL_4DOT_ENABLE
    if (s_writer_boot_state != WRITER_BOOT_STATE_DONE) {
        return WriterBoot_Process_Frame(frame, len);
    }
#endif
    return GCodeSerial_ProcessFrame(frame, len);
#endif
}

bool WriterTest_Is_Done(void)
{
    return s_writer_test_state == WRITER_TEST_STATE_DONE;
}

writer_test_state_t WriterTest_Get_State(void)
{
    return s_writer_test_state;
}

bool WriterTest_Startup_Is_Complete(void)
{
#if (WRITER_TEST_MODE == WRITER_TEST_MODE_GCODE_SERIAL) && \
    WRITER_TEST_BOOT_PATROL_4DOT_ENABLE
    return WriterBoot_Is_Terminal();
#else
    return s_writer_test_state != WRITER_TEST_STATE_IDLE;
#endif
}

bool WriterTest_Startup_Succeeded(void)
{
#if (WRITER_TEST_MODE == WRITER_TEST_MODE_GCODE_SERIAL) && \
    WRITER_TEST_BOOT_PATROL_4DOT_ENABLE
    return s_writer_boot_state == WRITER_BOOT_STATE_DONE;
#else
    return s_writer_test_state != WRITER_TEST_STATE_IDLE;
#endif
}
