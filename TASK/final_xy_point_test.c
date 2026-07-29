/**
 * @file    final_xy_point_test.c
 * @brief   Mark five isolated XY endpoints after explicit UART gates.
 */
#include "final_xy_point_test.h"
#include "app_servo.h"
#include "app_stepper.h"
#include "app_writer_motion.h"
#include "comm_vision_uart.h"
#include "elog.h"
#include <ctype.h>
#include <math.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define FINAL_XY_POINT_TEST_REPLY_MAX       (256u)
#define FINAL_XY_POINT_TEST_COMMAND_MAX     (32u)
#define FINAL_XY_POINT_TEST_SETUP_G21       (1u << 0)
#define FINAL_XY_POINT_TEST_SETUP_G90       (1u << 1)
#define FINAL_XY_POINT_TEST_SETUP_G94       (1u << 2)
#define FINAL_XY_POINT_TEST_SETUP_M5        (1u << 3)
#define FINAL_XY_POINT_TEST_SETUP_ALL       (0x0Fu)
#define FINAL_XY_POINT_TEST_ALIGN_X_MM      (150.0f)
#define FINAL_XY_POINT_TEST_ALIGN_Y_MM      (20.0f)

typedef struct {
    const char *name;
    float x_mm;
    float y_mm;
} final_xy_point_target_t;

static const final_xy_point_target_t s_targets[] = {
    {"O_BASE",   205.0f, 65.0f},
    {"W",        185.0f, 65.0f},
    {"O_FROM_W", 205.0f, 65.0f},
    {"E",        225.0f, 65.0f},
    {"O_FROM_E", 205.0f, 65.0f},
    {"S",        205.0f, 43.1f},
    {"O_FROM_S", 205.0f, 65.0f},
    {"N",        205.0f, 86.9f},
    {"O_FROM_N", 205.0f, 65.0f},
};

typedef char final_xy_point_target_count_must_match[
    ((sizeof(s_targets) / sizeof(s_targets[0])) ==
     FINAL_XY_POINT_TEST_TARGET_COUNT) ? 1 : -1];

extern volatile uint32_t s_sys_tick;

static final_xy_point_test_state_t s_state =
    FINAL_XY_POINT_TEST_STATE_IDLE;
static uint32_t s_target_index = 0u;
static uint32_t s_mark_count = 0u;
static uint32_t s_state_start_ms = 0u;
static uint8_t s_setup_mask = 0u;
static bool s_pen_is_down = false;

static int32_t FinalXYPointTest_Scale_100(float value)
{
    return (int32_t)((value >= 0.0f) ?
                     (value * 100.0f + 0.5f) :
                     (value * 100.0f - 0.5f));
}

static const char *FinalXYPointTest_State_Name(void)
{
    switch (s_state) {
        case FINAL_XY_POINT_TEST_STATE_IDLE:
            return "IDLE";
        case FINAL_XY_POINT_TEST_STATE_WAIT_ALIGN:
            return "WAIT_ALIGN";
        case FINAL_XY_POINT_TEST_STATE_RUNNING_ALIGN:
            return "RUNNING_ALIGN";
        case FINAL_XY_POINT_TEST_STATE_WAIT_DOTS:
            return "WAIT_DOTS";
        case FINAL_XY_POINT_TEST_STATE_MOVE:
            return "MOVE";
        case FINAL_XY_POINT_TEST_STATE_WAIT_MOVE:
            return "WAIT_MOVE";
        case FINAL_XY_POINT_TEST_STATE_START_SETTLE:
            return "START_SETTLE";
        case FINAL_XY_POINT_TEST_STATE_DOWN_HOLD:
            return "DOWN_HOLD";
        case FINAL_XY_POINT_TEST_STATE_UP_SETTLE:
            return "UP_SETTLE";
        case FINAL_XY_POINT_TEST_STATE_DONE:
            return "DONE";
        case FINAL_XY_POINT_TEST_STATE_STOPPED:
            return "STOPPED";
        case FINAL_XY_POINT_TEST_STATE_ERROR:
            return "ERROR";
        default:
            return "UNKNOWN";
    }
}

static const char *FinalXYPointTest_Action_Name(void)
{
    switch (s_state) {
        case FINAL_XY_POINT_TEST_STATE_WAIT_ALIGN:
            return "M801";
        case FINAL_XY_POINT_TEST_STATE_WAIT_DOTS:
            return "M805";
        case FINAL_XY_POINT_TEST_STATE_RUNNING_ALIGN:
        case FINAL_XY_POINT_TEST_STATE_MOVE:
        case FINAL_XY_POINT_TEST_STATE_WAIT_MOVE:
        case FINAL_XY_POINT_TEST_STATE_START_SETTLE:
        case FINAL_XY_POINT_TEST_STATE_DOWN_HOLD:
        case FINAL_XY_POINT_TEST_STATE_UP_SETTLE:
            return "STOP";
        case FINAL_XY_POINT_TEST_STATE_IDLE:
        case FINAL_XY_POINT_TEST_STATE_DONE:
        case FINAL_XY_POINT_TEST_STATE_STOPPED:
        case FINAL_XY_POINT_TEST_STATE_ERROR:
        default:
            return "NONE";
    }
}

static bool FinalXYPointTest_Is_Running(void)
{
    return (s_state == FINAL_XY_POINT_TEST_STATE_RUNNING_ALIGN) ||
           (s_state == FINAL_XY_POINT_TEST_STATE_MOVE) ||
           (s_state == FINAL_XY_POINT_TEST_STATE_WAIT_MOVE) ||
           (s_state == FINAL_XY_POINT_TEST_STATE_START_SETTLE) ||
           (s_state == FINAL_XY_POINT_TEST_STATE_DOWN_HOLD) ||
           (s_state == FINAL_XY_POINT_TEST_STATE_UP_SETTLE);
}

static bool FinalXYPointTest_Limits_Clear(void)
{
    return !App_Stepper_Stage1_IsLimitHit() &&
           !App_Stepper_Stage2_IsLimitHit();
}

static bool FinalXYPointTest_Config_Matches(void)
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
           (APP_WRITER_A4_ENVELOPE_PROBE_ENABLE == 1u);
}

static void FinalXYPointTest_Sendf(const char *fmt, ...)
{
    char reply[FINAL_XY_POINT_TEST_REPLY_MAX];
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

static bool FinalXYPointTest_Is_At(float x_mm, float y_mm)
{
    const app_writer_pose_t *pose = WriterMotion_Get_Pose();

    return (fabsf(pose->user_point.x_mm - x_mm) <=
            FINAL_XY_POINT_TEST_POSITION_EPS_MM) &&
           (fabsf(pose->user_point.y_mm - y_mm) <=
            FINAL_XY_POINT_TEST_POSITION_EPS_MM);
}

static void FinalXYPointTest_Fail(const char *reason)
{
    App_Servo_Pen_Up();
    s_pen_is_down = false;
    WriterMotion_Emergency_Stop();
    s_state = FINAL_XY_POINT_TEST_STATE_ERROR;

    elog_e("DOTV34", "[DOTV34] error=%s target=%u/%u marks=%u/%u lim1=%d lim2=%d pen=UP rehome=1",
           reason,
           s_target_index + 1u,
           FINAL_XY_POINT_TEST_TARGET_COUNT,
           s_mark_count,
           FINAL_XY_POINT_TEST_MARK_COUNT,
           App_Stepper_Stage1_IsLimitHit(),
           App_Stepper_Stage2_IsLimitHit());
    FinalXYPointTest_Sendf(
        "error:%s id=%s state=ERROR target=%u/%u marks=%u/%u pen=UP rehome=1\r\n",
        reason,
        FINAL_XY_POINT_TEST_BUILD_ID,
        s_target_index + 1u,
        FINAL_XY_POINT_TEST_TARGET_COUNT,
        s_mark_count,
        FINAL_XY_POINT_TEST_MARK_COUNT);
}

static void FinalXYPointTest_Stop(void)
{
    App_Servo_Pen_Up();
    s_pen_is_down = false;
    WriterMotion_Emergency_Stop();
    s_state = FINAL_XY_POINT_TEST_STATE_STOPPED;
    FinalXYPointTest_Sendf(
        "ok STOPPED id=%s state=STOPPED target=%u/%u marks=%u/%u pen=UP rehome=1\r\n",
        FINAL_XY_POINT_TEST_BUILD_ID,
        s_target_index + 1u,
        FINAL_XY_POINT_TEST_TARGET_COUNT,
        s_mark_count,
        FINAL_XY_POINT_TEST_MARK_COUNT);
}

static void FinalXYPointTest_Send_Status(void)
{
    const app_writer_pose_t *pose = WriterMotion_Get_Pose();

    FinalXYPointTest_Sendf(
        "ok STATUS id=%s state=%s action=%s busy=%u setup=%u/15 target=%u/%u marks=%u/%u user_x100=%d user_y100=%d lim1=%d lim2=%d pen=%s\r\n",
        FINAL_XY_POINT_TEST_BUILD_ID,
        FinalXYPointTest_State_Name(),
        FinalXYPointTest_Action_Name(),
        FinalXYPointTest_Is_Running() ? 1u : 0u,
        (uint32_t)s_setup_mask,
        s_target_index + 1u,
        FINAL_XY_POINT_TEST_TARGET_COUNT,
        s_mark_count,
        FINAL_XY_POINT_TEST_MARK_COUNT,
        FinalXYPointTest_Scale_100(pose->user_point.x_mm),
        FinalXYPointTest_Scale_100(pose->user_point.y_mm),
        App_Stepper_Stage1_IsLimitHit(),
        App_Stepper_Stage2_IsLimitHit(),
        s_pen_is_down ? "DOWN" : "UP");
}

static void FinalXYPointTest_Advance(void)
{
    if ((s_target_index + 1u) < FINAL_XY_POINT_TEST_TARGET_COUNT) {
        s_target_index++;
        s_state = FINAL_XY_POINT_TEST_STATE_MOVE;
        return;
    }
    if (s_mark_count != FINAL_XY_POINT_TEST_MARK_COUNT) {
        FinalXYPointTest_Fail("mark_count");
        return;
    }

    s_state = FINAL_XY_POINT_TEST_STATE_DONE;
    elog_i("DOTV34", "[DOTV34] %s done targets=9 marks=9 unique_points=5 center_stamps=5 pen=UP single_pass=1 rehome=1",
           FINAL_XY_POINT_TEST_BUILD_ID);
    FinalXYPointTest_Sendf(
        "ok DONE id=%s state=DONE targets=9 marks=9 unique_points=5 center_stamps=5 pen=UP single_pass=1 rehome=1\r\n",
        FINAL_XY_POINT_TEST_BUILD_ID);
}

static void FinalXYPointTest_Start_Dots(void)
{
    if (!FinalXYPointTest_Limits_Clear() || s_pen_is_down) {
        FinalXYPointTest_Fail("dot_start_precondition");
        return;
    }
    s_target_index = 0u;
    s_mark_count = 0u;
    s_state_start_ms = 0u;
    s_setup_mask = 0u;
    s_state = FINAL_XY_POINT_TEST_STATE_MOVE;
    elog_i("DOTV34", "[DOTV34] M805 accepted order=O,W,O,E,O,S,O,N,O targets=9 marks=9 unique_points=5 move_feed=240 pen=UP");
    FinalXYPointTest_Sendf(
        "ok M805 accepted id=%s targets=9 marks=9 unique_points=5 center_stamps=5 stop=STOP pen=UP\r\n",
        FINAL_XY_POINT_TEST_BUILD_ID);
}

void FinalXYPointTest_Start(void)
{
    elog_set_filter_tag_lvl("BSP", ELOG_LVL_WARN);
    elog_set_filter_tag_lvl("PWM", ELOG_LVL_WARN);
    elog_set_filter_tag_lvl("IRQ", ELOG_LVL_WARN);
    elog_set_filter_tag_lvl("RUN", ELOG_LVL_WARN);
    elog_set_filter_tag_lvl("MOTION", ELOG_LVL_WARN);

    App_Servo_Pen_Up();
    s_pen_is_down = false;
    s_target_index = 0u;
    s_mark_count = 0u;
    s_state_start_ms = 0u;
    s_setup_mask = 0u;

    if (!FinalXYPointTest_Config_Matches()) {
        s_state = FINAL_XY_POINT_TEST_STATE_ERROR;
        elog_e("DOTV34", "[DOTV34] configuration mismatch motion_locked=1 pen=UP");
        FinalXYPointTest_Sendf(
            "error:configuration_mismatch id=%s motion_locked=1 pen=UP\r\n",
            FINAL_XY_POINT_TEST_BUILD_ID);
        return;
    }

    WriterMotion_Init_From_Home();
    s_state = FINAL_XY_POINT_TEST_STATE_WAIT_ALIGN;
    elog_i("DOTV34", "[DOTV34] mode=%s no_auto_motion=1 gates=M801_ALIGN,M805_DOTS gcode=DISABLED dircomp=0 single_pass=1 pen=UP",
           FINAL_XY_POINT_TEST_BUILD_ID);
    elog_i("DOTV34", "[DOTV34] align=(15000,2000) O=(20500,6500) W=(18500,6500) E=(22500,6500) S=(20500,4310) N=(20500,8690) y_scale_x10000=10950 move_feed=240 marks=9");
    FinalXYPointTest_Sendf(
        "ok DOTV34 READY id=%s state=WAIT_ALIGN action=M801 status=STATUS emergency=STOP pen=UP\r\n",
        FINAL_XY_POINT_TEST_BUILD_ID);
}

void FinalXYPointTest_Update(void)
{
    const final_xy_point_target_t *target;

    if (!FinalXYPointTest_Is_Running()) {
        return;
    }
    if (!FinalXYPointTest_Limits_Clear()) {
        FinalXYPointTest_Fail("runtime_limit_active");
        return;
    }

    if (s_state == FINAL_XY_POINT_TEST_STATE_RUNNING_ALIGN) {
        WriterMotion_Task();
        if (WriterMotion_Is_Busy()) {
            return;
        }
        if (!FinalXYPointTest_Is_At(FINAL_XY_POINT_TEST_ALIGN_X_MM,
                                    FINAL_XY_POINT_TEST_ALIGN_Y_MM)) {
            FinalXYPointTest_Fail("align_incomplete");
            return;
        }
        s_setup_mask = 0u;
        s_state = FINAL_XY_POINT_TEST_STATE_WAIT_DOTS;
        FinalXYPointTest_Sendf(
            "ok STAGE_DONE id=%s completed=ALIGN state=WAIT_DOTS action=M805 pen=UP\r\n",
            FINAL_XY_POINT_TEST_BUILD_ID);
        return;
    }

    target = &s_targets[s_target_index];
    switch (s_state) {
        case FINAL_XY_POINT_TEST_STATE_MOVE:
            if (s_pen_is_down) {
                FinalXYPointTest_Fail("move_with_pen_down");
                return;
            }
            elog_i("DOTV34", "[DOTV34] target=%u/%u name=%s x=%d y=%d mark=1 pen=UP",
                   s_target_index + 1u,
                   FINAL_XY_POINT_TEST_TARGET_COUNT,
                   target->name,
                   FinalXYPointTest_Scale_100(target->x_mm),
                   FinalXYPointTest_Scale_100(target->y_mm));
            if (!WriterMotion_Start_To_At_Feed(
                    target->x_mm,
                    target->y_mm,
                    FINAL_XY_POINT_TEST_MOVE_FEED_MM_MIN)) {
                FinalXYPointTest_Fail("move_rejected");
                return;
            }
            s_state = FINAL_XY_POINT_TEST_STATE_WAIT_MOVE;
            return;

        case FINAL_XY_POINT_TEST_STATE_WAIT_MOVE:
            WriterMotion_Task();
            if (WriterMotion_Is_Busy()) {
                return;
            }
            if (!FinalXYPointTest_Is_At(target->x_mm, target->y_mm)) {
                FinalXYPointTest_Fail("move_incomplete");
                return;
            }
            s_state_start_ms = s_sys_tick;
            s_state = FINAL_XY_POINT_TEST_STATE_START_SETTLE;
            return;

        case FINAL_XY_POINT_TEST_STATE_START_SETTLE:
            if ((uint32_t)(s_sys_tick - s_state_start_ms) <
                FINAL_XY_POINT_TEST_START_SETTLE_MS) {
                return;
            }
            App_Servo_Pen_Down();
            s_pen_is_down = true;
            s_state_start_ms = s_sys_tick;
            s_state = FINAL_XY_POINT_TEST_STATE_DOWN_HOLD;
            return;

        case FINAL_XY_POINT_TEST_STATE_DOWN_HOLD:
            if ((uint32_t)(s_sys_tick - s_state_start_ms) <
                FINAL_XY_POINT_TEST_DOWN_HOLD_MS) {
                return;
            }
            App_Servo_Pen_Up();
            s_pen_is_down = false;
            s_mark_count++;
            s_state_start_ms = s_sys_tick;
            s_state = FINAL_XY_POINT_TEST_STATE_UP_SETTLE;
            return;

        case FINAL_XY_POINT_TEST_STATE_UP_SETTLE:
            if ((uint32_t)(s_sys_tick - s_state_start_ms) <
                FINAL_XY_POINT_TEST_UP_SETTLE_MS) {
                return;
            }
            FinalXYPointTest_Advance();
            return;

        case FINAL_XY_POINT_TEST_STATE_IDLE:
        case FINAL_XY_POINT_TEST_STATE_WAIT_ALIGN:
        case FINAL_XY_POINT_TEST_STATE_RUNNING_ALIGN:
        case FINAL_XY_POINT_TEST_STATE_WAIT_DOTS:
        case FINAL_XY_POINT_TEST_STATE_DONE:
        case FINAL_XY_POINT_TEST_STATE_STOPPED:
        case FINAL_XY_POINT_TEST_STATE_ERROR:
            return;

        default:
            FinalXYPointTest_Fail("bad_state");
            return;
    }
}

static bool FinalXYPointTest_Normalize_Command(
    const uint8_t *frame, uint16_t len, char *command, uint16_t command_size)
{
    uint16_t copy_len = 0u;
    uint16_t start = 0u;
    uint16_t end;

    if ((frame == 0) || (len == 0u) ||
        (command == 0) || (command_size < 2u)) {
        return false;
    }
    while ((copy_len < len) && (copy_len < (uint16_t)(command_size - 1u)) &&
           (frame[copy_len] != '\r') && (frame[copy_len] != '\n')) {
        command[copy_len] = (char)toupper((unsigned char)frame[copy_len]);
        copy_len++;
    }
    command[copy_len] = '\0';
    while ((start < copy_len) && isspace((unsigned char)command[start])) {
        start++;
    }
    end = copy_len;
    while ((end > start) && isspace((unsigned char)command[end - 1u])) {
        end--;
    }
    if (start > 0u) {
        memmove(command, &command[start], (size_t)(end - start));
    }
    command[end - start] = '\0';
    return command[0] != '\0';
}

static bool FinalXYPointTest_Accept_Setup(const char *command)
{
    if (strcmp(command, "G21") == 0) {
        s_setup_mask |= FINAL_XY_POINT_TEST_SETUP_G21;
    } else if (strcmp(command, "G90") == 0) {
        s_setup_mask |= FINAL_XY_POINT_TEST_SETUP_G90;
    } else if (strcmp(command, "G94") == 0) {
        s_setup_mask |= FINAL_XY_POINT_TEST_SETUP_G94;
    } else if (strcmp(command, "M5") == 0) {
        App_Servo_Pen_Up();
        s_pen_is_down = false;
        s_setup_mask |= FINAL_XY_POINT_TEST_SETUP_M5;
    } else {
        return false;
    }
    FinalXYPointTest_Sendf(
        "ok %s setup=%u/15 pen=UP\r\n", command, (uint32_t)s_setup_mask);
    return true;
}

static void FinalXYPointTest_Accept_Gate(const char *command)
{
    if (s_setup_mask != FINAL_XY_POINT_TEST_SETUP_ALL) {
        FinalXYPointTest_Sendf(
            "error:setup_incomplete mask=%u required=G21_G90_G94_M5 state=%s pen=UP\r\n",
            (uint32_t)s_setup_mask,
            FinalXYPointTest_State_Name());
        return;
    }
    if (!FinalXYPointTest_Limits_Clear() || s_pen_is_down) {
        FinalXYPointTest_Fail("gate_precondition_failed");
        return;
    }

    if ((strcmp(command, "M801") == 0) &&
        (s_state == FINAL_XY_POINT_TEST_STATE_WAIT_ALIGN)) {
        if (!WriterMotion_Start_To_At_Feed(
                FINAL_XY_POINT_TEST_ALIGN_X_MM,
                FINAL_XY_POINT_TEST_ALIGN_Y_MM,
                FINAL_XY_POINT_TEST_ALIGN_FEED_MM_MIN)) {
            FinalXYPointTest_Fail("align_start_rejected");
            return;
        }
        s_state = FINAL_XY_POINT_TEST_STATE_RUNNING_ALIGN;
        s_setup_mask = 0u;
        FinalXYPointTest_Sendf(
            "ok M801 accepted id=%s stage=ALIGN stop=STOP pen=UP\r\n",
            FINAL_XY_POINT_TEST_BUILD_ID);
        return;
    }
    if ((strcmp(command, "M805") == 0) &&
        (s_state == FINAL_XY_POINT_TEST_STATE_WAIT_DOTS)) {
        FinalXYPointTest_Start_Dots();
        return;
    }

    FinalXYPointTest_Sendf(
        "error:wrong_gate command=%s state=%s expected=%s pen=UP\r\n",
        command,
        FinalXYPointTest_State_Name(),
        FinalXYPointTest_Action_Name());
}

bool FinalXYPointTest_Process_Frame(const uint8_t *frame, uint16_t len)
{
    char command[FINAL_XY_POINT_TEST_COMMAND_MAX];

    if (!FinalXYPointTest_Normalize_Command(
            frame, len, command, sizeof(command))) {
        return false;
    }
    if ((strcmp(command, "STATUS") == 0) ||
        (strcmp(command, "?") == 0)) {
        FinalXYPointTest_Send_Status();
        return true;
    }
    if (strcmp(command, "STOP") == 0) {
        FinalXYPointTest_Stop();
        return true;
    }
    if (FinalXYPointTest_Is_Running()) {
        FinalXYPointTest_Fail("unexpected_uart_while_running");
        return true;
    }
    if ((s_state == FINAL_XY_POINT_TEST_STATE_DONE) ||
        (s_state == FINAL_XY_POINT_TEST_STATE_STOPPED) ||
        (s_state == FINAL_XY_POINT_TEST_STATE_ERROR)) {
        FinalXYPointTest_Sendf(
            "error:reset_required id=%s state=%s pen=UP rehome=1\r\n",
            FINAL_XY_POINT_TEST_BUILD_ID,
            FinalXYPointTest_State_Name());
        return true;
    }
    if (FinalXYPointTest_Accept_Setup(command)) {
        return true;
    }
    if ((strcmp(command, "M801") == 0) ||
        (strcmp(command, "M805") == 0)) {
        FinalXYPointTest_Accept_Gate(command);
        return true;
    }

    FinalXYPointTest_Sendf(
        "error:unsupported allowed=G21_G90_G94_M5_%s_STATUS_STOP gcode=DISABLED pen=UP\r\n",
        FinalXYPointTest_Action_Name());
    return true;
}

bool FinalXYPointTest_Is_Done(void)
{
    return (s_state == FINAL_XY_POINT_TEST_STATE_DONE) ||
           (s_state == FINAL_XY_POINT_TEST_STATE_STOPPED) ||
           (s_state == FINAL_XY_POINT_TEST_STATE_ERROR);
}

final_xy_point_test_state_t FinalXYPointTest_Get_State(void)
{
    return s_state;
}
