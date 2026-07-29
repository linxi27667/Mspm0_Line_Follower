/**
 * @file    fixed_layout_axis_mark.c
 * @brief   Three 20 x 20 mm Y-range calibration rectangles.
 *
 * V18 draws only the middle paper column X=95..115 mm. The three exact target
 * rectangles are Y=20..40, 65..85, and 110..130 mm. Each region has its own
 * affine inverse correction derived from the twelve manually measured V17
 * vertices. The corrected paper vertices are then passed through the stable
 * quadratic paper-to-command fit from the V13 36-point calibration. The first
 * Y20 approach remains split at command waypoint (220,0), keeping both 1 mm
 * plans below the 192-segment buffer limit.
 *
 * One M801 trigger starts the complete sequence.  The firmware automatically
 * performs every pen-up region move and pen-down square, while STATUS, STOP,
 * runtime limit checks, and pen-up-on-error remain active.
 */
#include "fixed_layout_axis_mark.h"
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

#define AXIS_MARK_REPLY_MAX              (320u)
#define AXIS_MARK_COMMAND_MAX            (32u)
#define AXIS_MARK_SETUP_G21              (1u << 0)
#define AXIS_MARK_SETUP_G90              (1u << 1)
#define AXIS_MARK_SETUP_G94              (1u << 2)
#define AXIS_MARK_SETUP_M5               (1u << 3)
#define AXIS_MARK_SETUP_ALL              (0x0Fu)
#define AXIS_MARK_REGION_COUNT            (3u)
#define AXIS_MARK_MOVE_FEED_MM_MIN       (180.0f)
#define AXIS_MARK_DRAW_FEED_MM_MIN       (120.0f)
#define AXIS_MARK_POSITION_EPS_MM        (0.15f)
#define AXIS_MARK_SERVO_SETTLE_MS        (500u)
#define AXIS_MARK_FIRST_WAYPOINT_X_MM    (220.0f)
#define AXIS_MARK_FIRST_WAYPOINT_Y_MM    (0.0f)

#if APP_WRITER_DIRECTION_COMP_ENABLE || \
    APP_WRITER_DIRECTION_COMP_PRELOAD_ENABLE
#error "The fixed-layout axis mark requires direction compensation off"
#endif

typedef enum {
    AXIS_MARK_OP_PEN_DOWN = 0,
    AXIS_MARK_OP_MOVE_DRAW,
    AXIS_MARK_OP_PEN_UP,
    AXIS_MARK_OP_END
} axis_mark_op_kind_t;

typedef struct {
    axis_mark_op_kind_t kind;
    const char *name;
} axis_mark_op_t;

typedef struct {
    float x_mm;
    float y_mm;
} axis_mark_point_t;

typedef struct {
    const char *name;
    int16_t paper_x0_mm;
    int16_t paper_y0_mm;
    axis_mark_point_t point[4];
} axis_mark_region_t;

static const axis_mark_op_t s_ops[] = {
    {AXIS_MARK_OP_PEN_DOWN,  "PEN_DOWN_SQUARE"},
    {AXIS_MARK_OP_MOVE_DRAW, "SIDE_X_RIGHT"},
    {AXIS_MARK_OP_MOVE_DRAW, "SIDE_Y_UP"},
    {AXIS_MARK_OP_MOVE_DRAW, "SIDE_X_LEFT"},
    {AXIS_MARK_OP_MOVE_DRAW, "SIDE_Y_DOWN_CLOSE"},
    {AXIS_MARK_OP_PEN_UP,    "PEN_UP_SQUARE"},
    {AXIS_MARK_OP_END,       "COMPLETE"},
};

static const axis_mark_region_t s_regions[AXIS_MARK_REGION_COUNT] = {
    {"Y20",  95,  20, {{399.694f, -52.430f}, {412.111f, -34.921f},
                       {390.903f, -24.690f}, {378.572f, -42.392f}}},
    {"Y65",  95,  65, {{355.235f, -28.417f}, {370.148f,  -9.211f},
                       {353.307f,   1.543f}, {338.532f, -17.784f}}},
    {"Y110", 95, 110, {{319.165f,  -3.030f}, {332.208f,  14.116f},
                       {317.285f,  26.326f}, {304.384f,   9.112f}}},
};

extern volatile uint32_t s_sys_tick;

static fixed_layout_axis_mark_state_t s_state =
    FIXED_LAYOUT_AXIS_MARK_STATE_IDLE;
static uint32_t s_region_index = 0u;
static uint32_t s_op_index = 0u;
static uint32_t s_wait_start_ms = 0u;
static uint8_t s_setup_mask = 0u;
static bool s_pen_is_down = false;
static bool s_waiting_motion = false;
static bool s_waiting_servo = false;
static bool s_first_waypoint_pending = false;

static int32_t AxisMark_Scale_100(float value)
{
    return (int32_t)((value >= 0.0f) ?
                     (value * 100.0f + 0.5f) :
                     (value * 100.0f - 0.5f));
}

static const axis_mark_region_t *AxisMark_Current_Region(void)
{
    if (s_region_index >= AXIS_MARK_REGION_COUNT) {
        return &s_regions[AXIS_MARK_REGION_COUNT - 1u];
    }
    return &s_regions[s_region_index];
}

static bool AxisMark_Get_Op_Target(
    uint32_t op_index, float *x_mm, float *y_mm)
{
    const axis_mark_region_t *region = AxisMark_Current_Region();
    uint32_t point_index;

    if ((x_mm == 0) || (y_mm == 0)) {
        return false;
    }
    switch (op_index) {
        case 1u:
            point_index = 1u;
            break;
        case 2u:
            point_index = 2u;
            break;
        case 3u:
            point_index = 3u;
            break;
        case 4u:
            point_index = 0u;
            break;
        default:
            return false;
    }
    *x_mm = region->point[point_index].x_mm;
    *y_mm = region->point[point_index].y_mm;
    return true;
}

static const char *AxisMark_State_Name(void)
{
    switch (s_state) {
        case FIXED_LAYOUT_AXIS_MARK_STATE_IDLE:
            return "IDLE";
        case FIXED_LAYOUT_AXIS_MARK_STATE_WAIT_ALIGN:
            return "WAIT_ALIGN";
        case FIXED_LAYOUT_AXIS_MARK_STATE_RUNNING_ALIGN:
            return "RUNNING_ALIGN";
        case FIXED_LAYOUT_AXIS_MARK_STATE_WAIT_DRAW:
            return "WAIT_DRAW";
        case FIXED_LAYOUT_AXIS_MARK_STATE_RUNNING_DRAW:
            return "RUNNING_DRAW";
        case FIXED_LAYOUT_AXIS_MARK_STATE_DONE:
            return "DONE";
        case FIXED_LAYOUT_AXIS_MARK_STATE_STOPPED:
            return "STOPPED";
        case FIXED_LAYOUT_AXIS_MARK_STATE_ERROR:
            return "ERROR";
        default:
            return "UNKNOWN";
    }
}

static const char *AxisMark_Action_Name(void)
{
    if (s_state == FIXED_LAYOUT_AXIS_MARK_STATE_WAIT_ALIGN) {
        return "M801";
    }
    if ((s_state == FIXED_LAYOUT_AXIS_MARK_STATE_RUNNING_ALIGN) ||
        (s_state == FIXED_LAYOUT_AXIS_MARK_STATE_RUNNING_DRAW)) {
        return "STOP";
    }
    return "NONE";
}

static bool AxisMark_Limits_Clear(void)
{
    return !App_Stepper_Stage1_IsLimitHit() &&
           !App_Stepper_Stage2_IsLimitHit();
}

static bool AxisMark_Is_At(float x_mm, float y_mm)
{
    const app_writer_pose_t *pose = WriterMotion_Get_Pose();

    return (fabsf(pose->user_point.x_mm - x_mm) <=
            AXIS_MARK_POSITION_EPS_MM) &&
           (fabsf(pose->user_point.y_mm - y_mm) <=
            AXIS_MARK_POSITION_EPS_MM);
}

static void AxisMark_Sendf(const char *fmt, ...)
{
    char reply[AXIS_MARK_REPLY_MAX];
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

static void AxisMark_Fail(const char *reason)
{
    const axis_mark_region_t *region = AxisMark_Current_Region();

    App_Servo_Pen_Up();
    s_pen_is_down = false;
    WriterMotion_Emergency_Stop();
    s_waiting_motion = false;
    s_waiting_servo = false;
    s_first_waypoint_pending = false;
    s_state = FIXED_LAYOUT_AXIS_MARK_STATE_ERROR;
    AxisMark_Sendf(
        "error:%s id=%s state=ERROR region=%s region_step=%u/%u "
        "op=%u/%u lim1=%d lim2=%d "
        "pen=UP rehome=1\r\n",
        reason,
        FIXED_LAYOUT_AXIS_MARK_BUILD_ID,
        region->name,
        s_region_index + 1u,
        AXIS_MARK_REGION_COUNT,
        s_op_index + 1u,
        (uint32_t)(sizeof(s_ops) / sizeof(s_ops[0])),
        App_Stepper_Stage1_IsLimitHit(),
        App_Stepper_Stage2_IsLimitHit());
}

static void AxisMark_Stop(void)
{
    const axis_mark_region_t *region = AxisMark_Current_Region();

    App_Servo_Pen_Up();
    s_pen_is_down = false;
    WriterMotion_Emergency_Stop();
    s_waiting_motion = false;
    s_waiting_servo = false;
    s_first_waypoint_pending = false;
    s_state = FIXED_LAYOUT_AXIS_MARK_STATE_STOPPED;
    AxisMark_Sendf(
        "ok STOPPED id=%s state=STOPPED region=%s region_step=%u/%u "
        "op=%u pen=UP rehome=1\r\n",
        FIXED_LAYOUT_AXIS_MARK_BUILD_ID,
        region->name,
        s_region_index + 1u,
        AXIS_MARK_REGION_COUNT,
        s_op_index);
}

static void AxisMark_Send_Status(void)
{
    const app_writer_pose_t *pose = WriterMotion_Get_Pose();
    const axis_mark_region_t *region = AxisMark_Current_Region();
    const char *op_name = ((s_state == FIXED_LAYOUT_AXIS_MARK_STATE_WAIT_ALIGN) ||
        (s_state == FIXED_LAYOUT_AXIS_MARK_STATE_RUNNING_ALIGN)) ?
        "MOVE_REGION_START" : ((s_op_index <
        (uint32_t)(sizeof(s_ops) / sizeof(s_ops[0]))) ?
        s_ops[s_op_index].name : "COMPLETE");

    AxisMark_Sendf(
        "ok STATUS id=%s state=%s action=%s setup=%u/15 op=%u/%u "
        "op_name=%s region=%s region_step=%u/%u paper_start=(%d,%d) "
        "square_mm=(20,20) completed=%u/%u "
        "user_x100=%d user_y100=%d "
        "lim1=%d lim2=%d pen=%s\r\n",
        FIXED_LAYOUT_AXIS_MARK_BUILD_ID,
        AxisMark_State_Name(),
        AxisMark_Action_Name(),
        (uint32_t)s_setup_mask,
        s_op_index + 1u,
        (uint32_t)(sizeof(s_ops) / sizeof(s_ops[0])),
        op_name,
        region->name,
        s_region_index + 1u,
        AXIS_MARK_REGION_COUNT,
        (int)region->paper_x0_mm,
        (int)region->paper_y0_mm,
        s_region_index,
        AXIS_MARK_REGION_COUNT,
        AxisMark_Scale_100(pose->user_point.x_mm),
        AxisMark_Scale_100(pose->user_point.y_mm),
        App_Stepper_Stage1_IsLimitHit(),
        App_Stepper_Stage2_IsLimitHit(),
        s_pen_is_down ? "DOWN" : "UP");
}

void FixedLayoutAxisMark_Start(void)
{
    elog_set_filter_tag_lvl("BSP", ELOG_LVL_WARN);
    elog_set_filter_tag_lvl("PWM", ELOG_LVL_WARN);
    elog_set_filter_tag_lvl("IRQ", ELOG_LVL_WARN);
    elog_set_filter_tag_lvl("RUN", ELOG_LVL_WARN);
    elog_set_filter_tag_lvl("MOTION", ELOG_LVL_WARN);

    App_Servo_Pen_Up();
    s_pen_is_down = false;
    s_region_index = 0u;
    s_op_index = 0u;
    s_wait_start_ms = 0u;
    s_setup_mask = 0u;
    s_waiting_motion = false;
    s_waiting_servo = false;
    s_first_waypoint_pending = false;

    WriterMotion_Init_From_Home();
    s_state = FIXED_LAYOUT_AXIS_MARK_STATE_WAIT_ALIGN;
    elog_i("AXISMARK", "[AXISMARK] id=%s "
           "paper=A4_210X297 test=Y_RANGE_3RECT regions=3 "
           "square_mm=(20,20) order=Y20_Y65_Y110 "
           "transform=V17_MEASURED_LOCAL_AFFINE_PLUS_GRID9_QUADRATIC "
           "paper_x_mm=95_115 x_unchanged=1 "
           "paper_y_limit_mm=20_130 paper_y_starts_mm=20_65_110 "
           "first_waypoint=(22000,0) plan_segments_max=192 "
           "gcode=RESTRICTED_M801 no_motion_before_trigger=1 "
           "execution=ONEFILE_AUTO pen=UP",
           FIXED_LAYOUT_AXIS_MARK_BUILD_ID);
    AxisMark_Sendf(
        "ok AXIS_MARK READY id=%s state=WAIT_ALIGN action=M801 "
        "region=Y20 region_step=1/3 paper_start=(95,20) "
        "square_mm=(20,20) calibration=Y_RANGE_3RECT_LOCALCAL_V18 "
        "first_waypoint=(22000,0) "
        "paper_y_limit_mm=20_130 "
        "execution=ONEFILE_AUTO "
        "status=STATUS emergency=STOP pen=UP\r\n",
        FIXED_LAYOUT_AXIS_MARK_BUILD_ID);
}

static void AxisMark_Start_Next_Op(void)
{
    const axis_mark_op_t *op;
    const axis_mark_region_t *region;
    uint32_t op_count = (uint32_t)(sizeof(s_ops) / sizeof(s_ops[0]));
    float target_x_mm;
    float target_y_mm;

    if (s_op_index >= op_count) {
        AxisMark_Fail("op_index");
        return;
    }
    op = &s_ops[s_op_index];
    region = AxisMark_Current_Region();

    switch (op->kind) {
        case AXIS_MARK_OP_PEN_DOWN:
            if (s_pen_is_down) {
                AxisMark_Fail("pen_already_down");
                return;
            }
            App_Servo_Pen_Down();
            s_pen_is_down = true;
            s_wait_start_ms = s_sys_tick;
            s_waiting_servo = true;
            return;

        case AXIS_MARK_OP_MOVE_DRAW:
            if (!s_pen_is_down) {
                AxisMark_Fail("pen_up_for_draw");
                return;
            }
            if (!AxisMark_Get_Op_Target(
                    s_op_index, &target_x_mm, &target_y_mm)) {
                AxisMark_Fail("bad_draw_target");
                return;
            }
            if (!WriterMotion_Start_To_At_Feed(
                    target_x_mm,
                    target_y_mm,
                    AXIS_MARK_DRAW_FEED_MM_MIN)) {
                AxisMark_Fail("draw_move_rejected");
                return;
            }
            s_waiting_motion = true;
            return;

        case AXIS_MARK_OP_PEN_UP:
            App_Servo_Pen_Up();
            s_pen_is_down = false;
            s_wait_start_ms = s_sys_tick;
            s_waiting_servo = true;
            return;

        case AXIS_MARK_OP_END:
            App_Servo_Pen_Up();
            s_pen_is_down = false;
            if ((s_region_index + 1u) < AXIS_MARK_REGION_COUNT) {
                const char *completed_name = region->name;

                s_region_index++;
                region = AxisMark_Current_Region();
                s_op_index = 0u;
                s_setup_mask = 0u;
                s_waiting_motion = false;
                s_waiting_servo = false;
                s_first_waypoint_pending = false;
                if (!WriterMotion_Start_To_At_Feed(
                        region->point[0].x_mm,
                        region->point[0].y_mm,
                        AXIS_MARK_MOVE_FEED_MM_MIN)) {
                    AxisMark_Fail("next_align_start_rejected");
                    return;
                }
                s_state = FIXED_LAYOUT_AXIS_MARK_STATE_RUNNING_ALIGN;
                AxisMark_Sendf(
                    "ok REGION_DONE id=%s completed=%s "
                    "completed_count=%u/%u state=RUNNING_ALIGN action=STOP "
                    "next=%s paper_start=(%d,%d) automatic=1 pen=UP\r\n",
                    FIXED_LAYOUT_AXIS_MARK_BUILD_ID,
                    completed_name,
                    s_region_index,
                    AXIS_MARK_REGION_COUNT,
                    region->name,
                    (int)region->paper_x0_mm,
                    (int)region->paper_y0_mm);
            } else {
                s_state = FIXED_LAYOUT_AXIS_MARK_STATE_DONE;
                AxisMark_Sendf(
                    "ok DONE id=%s completed_count=3/3 "
                    "test=Y_RANGE_3RECT square_mm=(20,20) regions=3 "
                    "measure_y_edges=20_40_65_85_110_130 "
                    "pen=UP rehome=1\r\n",
                    FIXED_LAYOUT_AXIS_MARK_BUILD_ID);
            }
            return;

        default:
            AxisMark_Fail("bad_op");
            return;
    }
}

void FixedLayoutAxisMark_Update(void)
{
    const axis_mark_region_t *region;
    float target_x_mm;
    float target_y_mm;

    if ((s_state != FIXED_LAYOUT_AXIS_MARK_STATE_RUNNING_ALIGN) &&
        (s_state != FIXED_LAYOUT_AXIS_MARK_STATE_RUNNING_DRAW)) {
        return;
    }
    if (!AxisMark_Limits_Clear()) {
        AxisMark_Fail("runtime_limit_active");
        return;
    }
    region = AxisMark_Current_Region();

    if (s_state == FIXED_LAYOUT_AXIS_MARK_STATE_RUNNING_ALIGN) {
        WriterMotion_Task();
        if (WriterMotion_Is_Busy()) {
            return;
        }
        if (s_first_waypoint_pending) {
            if (!AxisMark_Is_At(
                    AXIS_MARK_FIRST_WAYPOINT_X_MM,
                    AXIS_MARK_FIRST_WAYPOINT_Y_MM)) {
                AxisMark_Fail("first_waypoint_incomplete");
                return;
            }
            s_first_waypoint_pending = false;
            if (!WriterMotion_Start_To_At_Feed(
                    region->point[0].x_mm,
                    region->point[0].y_mm,
                    AXIS_MARK_MOVE_FEED_MM_MIN)) {
                AxisMark_Fail("align_after_waypoint_rejected");
                return;
            }
            AxisMark_Sendf(
                "ok WAYPOINT_DONE id=%s command=(22000,0) "
                "next=%s paper_start=(%d,%d) pen=UP\r\n",
                FIXED_LAYOUT_AXIS_MARK_BUILD_ID,
                region->name,
                (int)region->paper_x0_mm,
                (int)region->paper_y0_mm);
            return;
        }
        if (!AxisMark_Is_At(
                region->point[0].x_mm, region->point[0].y_mm)) {
            AxisMark_Fail("align_incomplete");
            return;
        }
        s_op_index = 0u;
        s_waiting_motion = false;
        s_waiting_servo = false;
        s_state = FIXED_LAYOUT_AXIS_MARK_STATE_RUNNING_DRAW;
        AxisMark_Sendf(
            "ok STAGE_DONE id=%s completed=MOVE_REGION_START "
            "region=%s region_step=%u/%u paper_start=(%d,%d) "
            "state=RUNNING_DRAW action=STOP pen=UP "
            "next=DRAW_SQUARE_20MM automatic=1\r\n",
            FIXED_LAYOUT_AXIS_MARK_BUILD_ID,
            region->name,
            s_region_index + 1u,
            AXIS_MARK_REGION_COUNT,
            (int)region->paper_x0_mm,
            (int)region->paper_y0_mm);
        return;
    }

    if (s_waiting_motion) {
        WriterMotion_Task();
        if (WriterMotion_Is_Busy()) {
            return;
        }
        if (!AxisMark_Get_Op_Target(
                s_op_index, &target_x_mm, &target_y_mm)) {
            AxisMark_Fail("bad_verify_target");
            return;
        }
        if (!AxisMark_Is_At(target_x_mm, target_y_mm)) {
            AxisMark_Fail("move_incomplete");
            return;
        }
        s_waiting_motion = false;
        s_op_index++;
        return;
    }
    if (s_waiting_servo) {
        if ((uint32_t)(s_sys_tick - s_wait_start_ms) <
            AXIS_MARK_SERVO_SETTLE_MS) {
            return;
        }
        s_waiting_servo = false;
        s_op_index++;
        return;
    }
    AxisMark_Start_Next_Op();
}

static bool AxisMark_Normalize_Command(
    const uint8_t *frame, uint16_t len, char *command, uint16_t command_size)
{
    uint16_t copy_len = 0u;
    uint16_t start = 0u;
    uint16_t end;

    if ((frame == 0) || (len == 0u) ||
        (command == 0) || (command_size < 2u)) {
        return false;
    }
    while ((copy_len < len) &&
           (copy_len < (uint16_t)(command_size - 1u)) &&
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

static bool AxisMark_Accept_Setup(const char *command)
{
    if (strcmp(command, "G21") == 0) {
        s_setup_mask |= AXIS_MARK_SETUP_G21;
    } else if (strcmp(command, "G90") == 0) {
        s_setup_mask |= AXIS_MARK_SETUP_G90;
    } else if (strcmp(command, "G94") == 0) {
        s_setup_mask |= AXIS_MARK_SETUP_G94;
    } else if (strcmp(command, "M5") == 0) {
        App_Servo_Pen_Up();
        s_pen_is_down = false;
        s_setup_mask |= AXIS_MARK_SETUP_M5;
    } else {
        return false;
    }
    AxisMark_Sendf(
        "ok %s setup=%u/15 pen=UP\r\n",
        command,
        (uint32_t)s_setup_mask);
    return true;
}

static void AxisMark_Accept_Gate(const char *command)
{
    const axis_mark_region_t *region = AxisMark_Current_Region();

    if (s_setup_mask != AXIS_MARK_SETUP_ALL) {
        AxisMark_Sendf(
            "error:setup_incomplete mask=%u required=G21_G90_G94_M5 "
            "state=%s action=%s pen=UP\r\n",
            (uint32_t)s_setup_mask,
            AxisMark_State_Name(),
            AxisMark_Action_Name());
        return;
    }
    if (!AxisMark_Limits_Clear() || s_pen_is_down) {
        AxisMark_Fail("gate_precondition_failed");
        return;
    }

    if ((strcmp(command, "M801") == 0) &&
        (s_state == FIXED_LAYOUT_AXIS_MARK_STATE_WAIT_ALIGN)) {
        if (!WriterMotion_Start_To_At_Feed(
                AXIS_MARK_FIRST_WAYPOINT_X_MM,
                AXIS_MARK_FIRST_WAYPOINT_Y_MM,
                AXIS_MARK_MOVE_FEED_MM_MIN)) {
            AxisMark_Fail("first_waypoint_start_rejected");
            return;
        }
        s_first_waypoint_pending = true;
        s_setup_mask = 0u;
        s_state = FIXED_LAYOUT_AXIS_MARK_STATE_RUNNING_ALIGN;
        AxisMark_Sendf(
            "ok M801 accepted id=%s stage=MOVE_REGION_START "
            "region=%s region_step=%u/%u paper_start=(%d,%d) "
            "via=(22000,0) execution=ONEFILE_AUTO regions=3 "
            "stop=STOP pen=UP\r\n",
            FIXED_LAYOUT_AXIS_MARK_BUILD_ID,
            region->name,
            s_region_index + 1u,
            AXIS_MARK_REGION_COUNT,
            (int)region->paper_x0_mm,
            (int)region->paper_y0_mm);
        return;
    }

    AxisMark_Sendf(
        "error:wrong_gate command=%s state=%s expected=%s pen=UP\r\n",
        command,
        AxisMark_State_Name(),
        AxisMark_Action_Name());
}

bool FixedLayoutAxisMark_Process_Frame(const uint8_t *frame, uint16_t len)
{
    char command[AXIS_MARK_COMMAND_MAX];

    if (!AxisMark_Normalize_Command(
            frame, len, command, sizeof(command))) {
        return false;
    }
    if ((strcmp(command, "STATUS") == 0) ||
        (strcmp(command, "?") == 0)) {
        AxisMark_Send_Status();
        return true;
    }
    if (strcmp(command, "STOP") == 0) {
        AxisMark_Stop();
        return true;
    }
    if ((s_state == FIXED_LAYOUT_AXIS_MARK_STATE_RUNNING_ALIGN) ||
        (s_state == FIXED_LAYOUT_AXIS_MARK_STATE_RUNNING_DRAW)) {
        AxisMark_Sendf(
            "error:busy action=STOP command=%s pen=%s\r\n",
            command,
            s_pen_is_down ? "DOWN" : "UP");
        return true;
    }
    if ((s_state == FIXED_LAYOUT_AXIS_MARK_STATE_DONE) ||
        (s_state == FIXED_LAYOUT_AXIS_MARK_STATE_STOPPED) ||
        (s_state == FIXED_LAYOUT_AXIS_MARK_STATE_ERROR)) {
        AxisMark_Sendf(
            "error:reset_required id=%s state=%s pen=UP rehome=1\r\n",
            FIXED_LAYOUT_AXIS_MARK_BUILD_ID,
            AxisMark_State_Name());
        return true;
    }
    if (AxisMark_Accept_Setup(command)) {
        return true;
    }
    if (strcmp(command, "M801") == 0) {
        AxisMark_Accept_Gate(command);
        return true;
    }

    App_Servo_Pen_Up();
    s_pen_is_down = false;
    AxisMark_Sendf(
        "error:unsupported command=%s expected=%s status=STATUS "
        "emergency=STOP pen=UP\r\n",
        command,
        AxisMark_Action_Name());
    return true;
}

bool FixedLayoutAxisMark_Is_Done(void)
{
    return (s_state == FIXED_LAYOUT_AXIS_MARK_STATE_DONE) ||
           (s_state == FIXED_LAYOUT_AXIS_MARK_STATE_STOPPED) ||
           (s_state == FIXED_LAYOUT_AXIS_MARK_STATE_ERROR);
}

fixed_layout_axis_mark_state_t FixedLayoutAxisMark_Get_State(void)
{
    return s_state;
}
