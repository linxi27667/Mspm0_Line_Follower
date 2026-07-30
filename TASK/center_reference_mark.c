/**
 * @file    center_reference_mark.c
 * @brief   One-point mark for puzzle paper zero, independent of machine home.
 */
#include "center_reference_mark.h"

#include "app_servo.h"
#include "app_puzzle_frame.h"
#include "app_stepper.h"
#include "app_writer_motion.h"
#include "elog.h"

#include <math.h>
#include <stdint.h>

#define ORIGIN_PAPER_X_MM              (0.0f)
#define ORIGIN_PAPER_Y_MM              (0.0f)
#define ORIGIN_MOVE_FEED_MM_MIN        (300.0f)
#define ORIGIN_MOVE_LEG_MAX_MM         (120.0f)
#define ORIGIN_POSITION_EPS_MM         (0.20f)
#define ORIGIN_DOWN_HOLD_MS            (700u)
#define ORIGIN_UP_SETTLE_MS            (700u)

extern volatile uint32_t s_sys_tick;

static center_reference_mark_state_t s_state =
    CENTER_REFERENCE_MARK_STATE_IDLE;
static uint32_t s_state_start_ms = 0u;
static float s_target_user_x_mm = 0.0f;
static float s_target_user_y_mm = 0.0f;

static int32_t CenterReferenceMark_Scale_100(float value)
{
    return (int32_t)((value >= 0.0f) ?
                     (value * 100.0f + 0.5f) :
                     (value * 100.0f - 0.5f));
}

static bool CenterReferenceMark_Limits_Clear(void)
{
    return !App_Stepper_Stage1_IsLimitHit() &&
           !App_Stepper_Stage2_IsLimitHit();
}

static bool CenterReferenceMark_Is_At_Target(void)
{
    const app_writer_pose_t *pose = WriterMotion_Get_Pose();

    return (fabsf(pose->user_point.x_mm - s_target_user_x_mm) <=
            ORIGIN_POSITION_EPS_MM) &&
           (fabsf(pose->user_point.y_mm - s_target_user_y_mm) <=
            ORIGIN_POSITION_EPS_MM);
}

static void CenterReferenceMark_Fail(const char *reason)
{
    App_Servo_Pen_Up();
    WriterMotion_Emergency_Stop();
    s_state = CENTER_REFERENCE_MARK_STATE_ERROR;
    elog_e("ORIGIN",
           "[ORIGIN] result=ERROR reason=%s paper_x100=%d paper_y100=%d "
           "lim1=%d lim2=%d pen=UP rehome=1",
           reason,
           CenterReferenceMark_Scale_100(ORIGIN_PAPER_X_MM),
           CenterReferenceMark_Scale_100(ORIGIN_PAPER_Y_MM),
           App_Stepper_Stage1_IsLimitHit(),
           App_Stepper_Stage2_IsLimitHit());
}

static bool CenterReferenceMark_Start_Leg(void)
{
    const app_writer_pose_t *pose = WriterMotion_Get_Pose();
    float delta_x = s_target_user_x_mm - pose->user_point.x_mm;
    float delta_y = s_target_user_y_mm - pose->user_point.y_mm;
    float span = fmaxf(fabsf(delta_x), fabsf(delta_y));
    float ratio = (span > ORIGIN_MOVE_LEG_MAX_MM) ?
                  (ORIGIN_MOVE_LEG_MAX_MM / span) : 1.0f;
    float leg_x = pose->user_point.x_mm + delta_x * ratio;
    float leg_y = pose->user_point.y_mm + delta_y * ratio;

    App_Servo_Pen_Up();
    if (!WriterMotion_Start_To_At_Feed(
            leg_x, leg_y, ORIGIN_MOVE_FEED_MM_MIN)) {
        return false;
    }
    s_state = CENTER_REFERENCE_MARK_STATE_MOVING;
    return true;
}

bool CenterReferenceMark_Start(void)
{
    app_puzzle_frame_map_t frame_map;

    App_Servo_Pen_Up();
    s_state_start_ms = 0u;

    if (WriterMotion_Is_Busy()) {
        elog_w("ORIGIN", "[ORIGIN] start rejected reason=motion_busy");
        return false;
    }
    if (!CenterReferenceMark_Limits_Clear()) {
        elog_w("ORIGIN",
               "[ORIGIN] start rejected reason=limit_active lim1=%d lim2=%d",
               App_Stepper_Stage1_IsLimitHit(),
               App_Stepper_Stage2_IsLimitHit());
        return false;
    }
    if (!App_PuzzleFrame_To_User(
            ORIGIN_PAPER_X_MM, ORIGIN_PAPER_Y_MM, &frame_map)) {
        CenterReferenceMark_Fail("puzzle_frame_rejected");
        return false;
    }
    s_target_user_x_mm = frame_map.user_x_mm;
    s_target_user_y_mm = frame_map.user_y_mm;

    elog_i("ORIGIN",
           "[ORIGIN] id=%s zero_type=PAPER_ZERO "
           "machine_home=%s paper_frame=%s origin_corner=P4 "
           "axis=X_RIGHT_Y_DOWN paper_x100=%d paper_y100=%d "
           "grid_in_x100=%d grid_in_y100=%d "
           "legacy_x100=%d legacy_y100=%d "
           "user_x100=%d user_y100=%d feed_x100=%d "
           "action=MOVE_AND_MARK",
           CENTER_REFERENCE_MARK_BUILD_ID,
           APP_PUZZLE_MACHINE_HOME_TEXT,
           APP_PUZZLE_PAPER_FRAME_TEXT,
           CenterReferenceMark_Scale_100(ORIGIN_PAPER_X_MM),
           CenterReferenceMark_Scale_100(ORIGIN_PAPER_Y_MM),
           CenterReferenceMark_Scale_100(
               frame_map.calibration_input_x_mm),
           CenterReferenceMark_Scale_100(
               frame_map.calibration_input_y_mm),
           CenterReferenceMark_Scale_100(
               frame_map.legacy_work_x_mm),
           CenterReferenceMark_Scale_100(
               frame_map.legacy_work_y_mm),
           CenterReferenceMark_Scale_100(s_target_user_x_mm),
           CenterReferenceMark_Scale_100(s_target_user_y_mm),
           CenterReferenceMark_Scale_100(ORIGIN_MOVE_FEED_MM_MIN));

    if (CenterReferenceMark_Is_At_Target()) {
        s_state = CENTER_REFERENCE_MARK_STATE_MOVING;
        return true;
    }
    if (!CenterReferenceMark_Start_Leg()) {
        CenterReferenceMark_Fail("first_move_rejected");
        return false;
    }
    return true;
}

void CenterReferenceMark_Update(void)
{
    if ((s_state == CENTER_REFERENCE_MARK_STATE_IDLE) ||
        CenterReferenceMark_Is_Done()) {
        return;
    }
    if (!CenterReferenceMark_Limits_Clear()) {
        CenterReferenceMark_Fail("runtime_limit_active");
        return;
    }

    if (s_state == CENTER_REFERENCE_MARK_STATE_MOVING) {
        App_Servo_Pen_Up();
        WriterMotion_Task();
        if (WriterMotion_Is_Busy()) {
            return;
        }
        if (!CenterReferenceMark_Is_At_Target()) {
            if (!CenterReferenceMark_Start_Leg()) {
                CenterReferenceMark_Fail("move_leg_rejected");
            }
            return;
        }
        App_Servo_Pen_Down();
        s_state_start_ms = s_sys_tick;
        s_state = CENTER_REFERENCE_MARK_STATE_DOWN_HOLD;
        elog_i("ORIGIN",
               "[ORIGIN] action=PEN_DOWN paper_x100=%d paper_y100=%d "
               "hold_ms=%u",
               CenterReferenceMark_Scale_100(ORIGIN_PAPER_X_MM),
               CenterReferenceMark_Scale_100(ORIGIN_PAPER_Y_MM),
               ORIGIN_DOWN_HOLD_MS);
        return;
    }

    if (s_state == CENTER_REFERENCE_MARK_STATE_DOWN_HOLD) {
        if ((uint32_t)(s_sys_tick - s_state_start_ms) <
            ORIGIN_DOWN_HOLD_MS) {
            return;
        }
        App_Servo_Pen_Up();
        s_state_start_ms = s_sys_tick;
        s_state = CENTER_REFERENCE_MARK_STATE_UP_SETTLE;
        return;
    }

    App_Servo_Pen_Up();
    if ((uint32_t)(s_sys_tick - s_state_start_ms) <
        ORIGIN_UP_SETTLE_MS) {
        return;
    }
    s_state = CENTER_REFERENCE_MARK_STATE_DONE;
    elog_i("ORIGIN",
           "[ORIGIN] result=DONE zero_type=PAPER_ZERO "
           "machine_home=%s paper_frame=%s "
           "paper_x100=%d paper_y100=%d pen=UP",
           APP_PUZZLE_MACHINE_HOME_TEXT,
           APP_PUZZLE_PAPER_FRAME_TEXT,
           CenterReferenceMark_Scale_100(ORIGIN_PAPER_X_MM),
           CenterReferenceMark_Scale_100(ORIGIN_PAPER_Y_MM));
}

void CenterReferenceMark_Abort_For_Rehome(void)
{
    App_Servo_Pen_Up();
    WriterMotion_Emergency_Stop();
    if (!CenterReferenceMark_Is_Done()) {
        s_state = CENTER_REFERENCE_MARK_STATE_STOPPED;
    }
    elog_w("ORIGIN", "[ORIGIN] action=ABORT_FOR_REHOME pen=UP");
}

bool CenterReferenceMark_Is_Done(void)
{
    return (s_state == CENTER_REFERENCE_MARK_STATE_DONE) ||
           (s_state == CENTER_REFERENCE_MARK_STATE_STOPPED) ||
           (s_state == CENTER_REFERENCE_MARK_STATE_ERROR);
}

center_reference_mark_state_t CenterReferenceMark_Get_State(void)
{
    return s_state;
}
