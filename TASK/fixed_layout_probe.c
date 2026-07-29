/**
 * @file    fixed_layout_probe.c
 * @brief   Gated, pen-up X/Y direction probe for the fixed physical layout.
 *
 * This task intentionally has no paper origin and no drawing path. M801 moves
 * to the author's previously verified Cartesian ALIGN point. The following
 * gates move exactly 10 mm from that point and return after each direction.
 */
#include "fixed_layout_probe.h"
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

#define FIXED_LAYOUT_REPLY_MAX           (320u)
#define FIXED_LAYOUT_COMMAND_MAX         (32u)
#define FIXED_LAYOUT_SETUP_G21           (1u << 0)
#define FIXED_LAYOUT_SETUP_G90           (1u << 1)
#define FIXED_LAYOUT_SETUP_G94           (1u << 2)
#define FIXED_LAYOUT_SETUP_M5            (1u << 3)
#define FIXED_LAYOUT_SETUP_ALL           (0x0Fu)
#define FIXED_LAYOUT_STEP_COUNT          (9u)
#define FIXED_LAYOUT_DELTA_MM            (10.0f)
#define FIXED_LAYOUT_MOVE_FEED_MM_MIN    (180.0f)
#define FIXED_LAYOUT_POSITION_EPS_MM     (0.15f)
#define FIXED_LAYOUT_ALIGN_X_MM          (150.0f)
#define FIXED_LAYOUT_ALIGN_Y_MM          (20.0f)

#if APP_WRITER_DIRECTION_COMP_ENABLE || \
    APP_WRITER_DIRECTION_COMP_PRELOAD_ENABLE
#error "The fixed-layout direction probe requires direction compensation off"
#endif

typedef struct {
    const char *gate;
    const char *name;
    float dx_mm;
    float dy_mm;
} fixed_layout_step_t;

static const fixed_layout_step_t s_steps[FIXED_LAYOUT_STEP_COUNT] = {
    {"M801", "AUTHOR_ALIGN_X150_Y20", 0.0f, 0.0f},
    {"M802", "X_PLUS_10",         10.0f, 0.0f},
    {"M803", "X_RETURN",           0.0f, 0.0f},
    {"M804", "X_MINUS_10",       -10.0f, 0.0f},
    {"M805", "X_CENTER",           0.0f, 0.0f},
    {"M806", "Y_PLUS_10",          0.0f, 10.0f},
    {"M807", "Y_RETURN",           0.0f, 0.0f},
    {"M808", "Y_MINUS_10",         0.0f, -10.0f},
    {"M809", "Y_CENTER",           0.0f, 0.0f},
};

static fixed_layout_probe_state_t s_state =
    FIXED_LAYOUT_PROBE_STATE_IDLE;
static uint32_t s_step_index = 0u;
static uint32_t s_setup_mask = 0u;
static float s_origin_x_mm = 0.0f;
static float s_origin_y_mm = 0.0f;
static float s_target_x_mm = 0.0f;
static float s_target_y_mm = 0.0f;
static bool s_origin_valid = false;

static int32_t FixedLayoutProbe_Scale_100(float value)
{
    return (int32_t)((value >= 0.0f) ?
                     (value * 100.0f + 0.5f) :
                     (value * 100.0f - 0.5f));
}

static const char *FixedLayoutProbe_State_Name(void)
{
    switch (s_state) {
        case FIXED_LAYOUT_PROBE_STATE_IDLE:
            return "IDLE";
        case FIXED_LAYOUT_PROBE_STATE_WAIT_GATE:
            return "WAIT_GATE";
        case FIXED_LAYOUT_PROBE_STATE_RUNNING:
            return "RUNNING";
        case FIXED_LAYOUT_PROBE_STATE_DONE:
            return "DONE";
        case FIXED_LAYOUT_PROBE_STATE_STOPPED:
            return "STOPPED";
        case FIXED_LAYOUT_PROBE_STATE_ERROR:
            return "ERROR";
        default:
            return "UNKNOWN";
    }
}

static const char *FixedLayoutProbe_Action_Name(void)
{
    if (s_state == FIXED_LAYOUT_PROBE_STATE_RUNNING) {
        return "STOP";
    }
    if ((s_state == FIXED_LAYOUT_PROBE_STATE_WAIT_GATE) &&
        (s_step_index < FIXED_LAYOUT_STEP_COUNT)) {
        return s_steps[s_step_index].gate;
    }
    return "NONE";
}

static bool FixedLayoutProbe_Limits_Clear(void)
{
    return !App_Stepper_Stage1_IsLimitHit() &&
           !App_Stepper_Stage2_IsLimitHit();
}

static void FixedLayoutProbe_Sendf(const char *fmt, ...)
{
    char reply[FIXED_LAYOUT_REPLY_MAX];
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

static void FixedLayoutProbe_Fail(const char *reason)
{
    App_Servo_Pen_Up();
    WriterMotion_Emergency_Stop();
    s_state = FIXED_LAYOUT_PROBE_STATE_ERROR;
    elog_e("FIXLAY", "[FIXLAY] error=%s step=%u/%u action=%s lim1=%d lim2=%d pen=UP rehome=1",
           reason,
           (s_step_index < FIXED_LAYOUT_STEP_COUNT) ?
               (s_step_index + 1u) : FIXED_LAYOUT_STEP_COUNT,
           FIXED_LAYOUT_STEP_COUNT,
           FixedLayoutProbe_Action_Name(),
           App_Stepper_Stage1_IsLimitHit(),
           App_Stepper_Stage2_IsLimitHit());
    FixedLayoutProbe_Sendf(
        "error:%s id=%s state=ERROR step=%u/%u pen=UP rehome=1\r\n",
        reason,
        FIXED_LAYOUT_PROBE_BUILD_ID,
        (s_step_index < FIXED_LAYOUT_STEP_COUNT) ?
            (s_step_index + 1u) : FIXED_LAYOUT_STEP_COUNT,
        FIXED_LAYOUT_STEP_COUNT);
}

static void FixedLayoutProbe_Stop(void)
{
    App_Servo_Pen_Up();
    WriterMotion_Emergency_Stop();
    s_state = FIXED_LAYOUT_PROBE_STATE_STOPPED;
    FixedLayoutProbe_Sendf(
        "ok STOPPED id=%s step=%u/%u pen=UP rehome=1\r\n",
        FIXED_LAYOUT_PROBE_BUILD_ID,
        (s_step_index < FIXED_LAYOUT_STEP_COUNT) ?
            (s_step_index + 1u) : FIXED_LAYOUT_STEP_COUNT,
        FIXED_LAYOUT_STEP_COUNT);
}

static void FixedLayoutProbe_Send_Status(void)
{
    const app_writer_pose_t *pose = WriterMotion_Get_Pose();
    const char *step_name = (s_step_index < FIXED_LAYOUT_STEP_COUNT) ?
        s_steps[s_step_index].name : "COMPLETE";

    FixedLayoutProbe_Sendf(
        "ok STATUS id=%s state=%s action=%s step=%u/%u name=%s setup=%u/15 "
        "origin_valid=%u origin_x100=%d origin_y100=%d "
        "user_x100=%d user_y100=%d lim1=%d lim2=%d pen=UP\r\n",
        FIXED_LAYOUT_PROBE_BUILD_ID,
        FixedLayoutProbe_State_Name(),
        FixedLayoutProbe_Action_Name(),
        (s_step_index < FIXED_LAYOUT_STEP_COUNT) ?
            (s_step_index + 1u) : FIXED_LAYOUT_STEP_COUNT,
        FIXED_LAYOUT_STEP_COUNT,
        step_name,
        s_setup_mask,
        s_origin_valid ? 1u : 0u,
        FixedLayoutProbe_Scale_100(s_origin_x_mm),
        FixedLayoutProbe_Scale_100(s_origin_y_mm),
        FixedLayoutProbe_Scale_100(pose->user_point.x_mm),
        FixedLayoutProbe_Scale_100(pose->user_point.y_mm),
        App_Stepper_Stage1_IsLimitHit(),
        App_Stepper_Stage2_IsLimitHit());
}

static bool FixedLayoutProbe_Is_At_Target(void)
{
    const app_writer_pose_t *pose = WriterMotion_Get_Pose();

    if (s_step_index == 0u) {
        return (fabsf(pose->user_point.x_mm -
                      FIXED_LAYOUT_ALIGN_X_MM) <=
                FIXED_LAYOUT_POSITION_EPS_MM) &&
               (fabsf(pose->user_point.y_mm -
                      FIXED_LAYOUT_ALIGN_Y_MM) <=
                FIXED_LAYOUT_POSITION_EPS_MM);
    }
    return (fabsf(pose->user_point.x_mm - s_target_x_mm) <=
            FIXED_LAYOUT_POSITION_EPS_MM) &&
           (fabsf(pose->user_point.y_mm - s_target_y_mm) <=
            FIXED_LAYOUT_POSITION_EPS_MM);
}

static bool FixedLayoutProbe_Start_Step(void)
{
    const fixed_layout_step_t *step = &s_steps[s_step_index];

    App_Servo_Pen_Up();
    if (s_step_index == 0u) {
        return WriterMotion_Start_To_At_Feed(FIXED_LAYOUT_ALIGN_X_MM,
                                             FIXED_LAYOUT_ALIGN_Y_MM,
                                             FIXED_LAYOUT_MOVE_FEED_MM_MIN);
    }
    if (!s_origin_valid) {
        return false;
    }

    s_target_x_mm = s_origin_x_mm + step->dx_mm;
    s_target_y_mm = s_origin_y_mm + step->dy_mm;
    return WriterMotion_Start_To_At_Feed(s_target_x_mm,
                                         s_target_y_mm,
                                         FIXED_LAYOUT_MOVE_FEED_MM_MIN);
}

void FixedLayoutProbe_Start(void)
{
    elog_set_filter_tag_lvl("BSP", ELOG_LVL_WARN);
    elog_set_filter_tag_lvl("PWM", ELOG_LVL_WARN);
    elog_set_filter_tag_lvl("IRQ", ELOG_LVL_WARN);
    elog_set_filter_tag_lvl("RUN", ELOG_LVL_WARN);

    App_Servo_Pen_Up();
    s_step_index = 0u;
    s_setup_mask = 0u;
    s_origin_x_mm = 0.0f;
    s_origin_y_mm = 0.0f;
    s_target_x_mm = 0.0f;
    s_target_y_mm = 0.0f;
    s_origin_valid = false;

    WriterMotion_Init_From_Home();
    s_state = FIXED_LAYOUT_PROBE_STATE_WAIT_GATE;
    elog_i("FIXLAY", "[FIXLAY] id=%s paper_frame=UNSET no_auto_motion=1 "
           "author_axes=1 align_xy=(15000,2000) delta_x100=1000 gates=M801..M809 "
           "gcode=DISABLED pen=UP",
           FIXED_LAYOUT_PROBE_BUILD_ID);
    FixedLayoutProbe_Sendf(
        "ok FIXLAY READY id=%s state=WAIT_GATE action=M801 "
        "paper_frame=UNSET delta_mm=10 status=STATUS emergency=STOP pen=UP\r\n",
        FIXED_LAYOUT_PROBE_BUILD_ID);
}

void FixedLayoutProbe_Update(void)
{
    const app_writer_pose_t *pose;
    const char *completed_name;

    if (s_state != FIXED_LAYOUT_PROBE_STATE_RUNNING) {
        return;
    }
    if (!FixedLayoutProbe_Limits_Clear()) {
        FixedLayoutProbe_Fail("runtime_limit_active");
        return;
    }

    WriterMotion_Task();
    if (WriterMotion_Is_Busy()) {
        return;
    }
    if (!FixedLayoutProbe_Is_At_Target()) {
        FixedLayoutProbe_Fail("move_incomplete");
        return;
    }

    pose = WriterMotion_Get_Pose();
    completed_name = s_steps[s_step_index].name;
    if (s_step_index == 0u) {
        s_origin_x_mm = pose->user_point.x_mm;
        s_origin_y_mm = pose->user_point.y_mm;
        s_origin_valid = true;
    }

    s_step_index++;
    s_setup_mask = 0u;
    if (s_step_index >= FIXED_LAYOUT_STEP_COUNT) {
        s_state = FIXED_LAYOUT_PROBE_STATE_DONE;
        elog_i("FIXLAY", "[FIXLAY] done origin=(%d,%d) pen=UP rehome=1",
               FixedLayoutProbe_Scale_100(s_origin_x_mm),
               FixedLayoutProbe_Scale_100(s_origin_y_mm));
        FixedLayoutProbe_Sendf(
            "ok DONE id=%s origin_x100=%d origin_y100=%d "
            "moves=X+10_X-10_Y+10_Y-10 pen=UP rehome=1\r\n",
            FIXED_LAYOUT_PROBE_BUILD_ID,
            FixedLayoutProbe_Scale_100(s_origin_x_mm),
            FixedLayoutProbe_Scale_100(s_origin_y_mm));
        return;
    }

    s_state = FIXED_LAYOUT_PROBE_STATE_WAIT_GATE;
    FixedLayoutProbe_Sendf(
        "ok STEP_DONE id=%s completed=%s completed_count=%u/%u "
        "state=WAIT_GATE action=%s user_x100=%d user_y100=%d pen=UP\r\n",
        FIXED_LAYOUT_PROBE_BUILD_ID,
        completed_name,
        s_step_index,
        FIXED_LAYOUT_STEP_COUNT,
        FixedLayoutProbe_Action_Name(),
        FixedLayoutProbe_Scale_100(pose->user_point.x_mm),
        FixedLayoutProbe_Scale_100(pose->user_point.y_mm));
}

static bool FixedLayoutProbe_Normalize_Command(
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

static bool FixedLayoutProbe_Accept_Setup(const char *command)
{
    if (strcmp(command, "G21") == 0) {
        s_setup_mask |= FIXED_LAYOUT_SETUP_G21;
    } else if (strcmp(command, "G90") == 0) {
        s_setup_mask |= FIXED_LAYOUT_SETUP_G90;
    } else if (strcmp(command, "G94") == 0) {
        s_setup_mask |= FIXED_LAYOUT_SETUP_G94;
    } else if (strcmp(command, "M5") == 0) {
        App_Servo_Pen_Up();
        s_setup_mask |= FIXED_LAYOUT_SETUP_M5;
    } else {
        return false;
    }
    FixedLayoutProbe_Sendf(
        "ok %s setup=%u/15 pen=UP\r\n", command, s_setup_mask);
    return true;
}

static bool FixedLayoutProbe_Is_Gate_Command(const char *command)
{
    uint32_t index;

    for (index = 0u; index < FIXED_LAYOUT_STEP_COUNT; index++) {
        if (strcmp(command, s_steps[index].gate) == 0) {
            return true;
        }
    }
    return false;
}

static void FixedLayoutProbe_Accept_Gate(const char *command)
{
    if (s_state != FIXED_LAYOUT_PROBE_STATE_WAIT_GATE) {
        FixedLayoutProbe_Sendf(
            "error:wrong_state command=%s state=%s action=%s pen=UP\r\n",
            command,
            FixedLayoutProbe_State_Name(),
            FixedLayoutProbe_Action_Name());
        return;
    }
    if ((s_step_index >= FIXED_LAYOUT_STEP_COUNT) ||
        (strcmp(command, s_steps[s_step_index].gate) != 0)) {
        FixedLayoutProbe_Sendf(
            "error:wrong_gate command=%s expected=%s step=%u/%u pen=UP\r\n",
            command,
            FixedLayoutProbe_Action_Name(),
            s_step_index + 1u,
            FIXED_LAYOUT_STEP_COUNT);
        return;
    }
    if (s_setup_mask != FIXED_LAYOUT_SETUP_ALL) {
        FixedLayoutProbe_Sendf(
            "error:setup_incomplete mask=%u required=G21_G90_G94_M5 "
            "action=%s pen=UP\r\n",
            s_setup_mask,
            FixedLayoutProbe_Action_Name());
        return;
    }
    if (!FixedLayoutProbe_Limits_Clear()) {
        FixedLayoutProbe_Fail("gate_limit_active");
        return;
    }
    if (!FixedLayoutProbe_Start_Step()) {
        FixedLayoutProbe_Fail("move_start_rejected");
        return;
    }

    s_state = FIXED_LAYOUT_PROBE_STATE_RUNNING;
    s_setup_mask = 0u;
    FixedLayoutProbe_Sendf(
        "ok %s accepted id=%s step=%u/%u name=%s "
        "stop=STOP pen=UP\r\n",
        command,
        FIXED_LAYOUT_PROBE_BUILD_ID,
        s_step_index + 1u,
        FIXED_LAYOUT_STEP_COUNT,
        s_steps[s_step_index].name);
}

bool FixedLayoutProbe_Process_Frame(const uint8_t *frame, uint16_t len)
{
    char command[FIXED_LAYOUT_COMMAND_MAX];

    if (!FixedLayoutProbe_Normalize_Command(
            frame, len, command, sizeof(command))) {
        return false;
    }
    if ((strcmp(command, "STATUS") == 0) ||
        (strcmp(command, "?") == 0)) {
        FixedLayoutProbe_Send_Status();
        return true;
    }
    if (strcmp(command, "STOP") == 0) {
        FixedLayoutProbe_Stop();
        return true;
    }
    if (s_state == FIXED_LAYOUT_PROBE_STATE_RUNNING) {
        FixedLayoutProbe_Sendf(
            "error:busy action=STOP command=%s pen=UP\r\n", command);
        return true;
    }
    if ((s_state == FIXED_LAYOUT_PROBE_STATE_DONE) ||
        (s_state == FIXED_LAYOUT_PROBE_STATE_STOPPED) ||
        (s_state == FIXED_LAYOUT_PROBE_STATE_ERROR)) {
        FixedLayoutProbe_Sendf(
            "error:reset_required id=%s state=%s pen=UP rehome=1\r\n",
            FIXED_LAYOUT_PROBE_BUILD_ID,
            FixedLayoutProbe_State_Name());
        return true;
    }
    if (FixedLayoutProbe_Accept_Setup(command)) {
        return true;
    }
    if (FixedLayoutProbe_Is_Gate_Command(command)) {
        FixedLayoutProbe_Accept_Gate(command);
        return true;
    }

    FixedLayoutProbe_Sendf(
        "error:unsupported allowed=G21_G90_G94_M5_%s_STATUS_STOP "
        "gcode=DISABLED pen=UP\r\n",
        FixedLayoutProbe_Action_Name());
    return true;
}

bool FixedLayoutProbe_Is_Done(void)
{
    return (s_state == FIXED_LAYOUT_PROBE_STATE_DONE) ||
           (s_state == FIXED_LAYOUT_PROBE_STATE_STOPPED) ||
           (s_state == FIXED_LAYOUT_PROBE_STATE_ERROR);
}

fixed_layout_probe_state_t FixedLayoutProbe_Get_State(void)
{
    return s_state;
}
