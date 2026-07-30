/**
 * @file    app_writer_motion.c
 * @brief   DrawBot absolute-angle kinematics with theta and psi motor targets.
 */
#include "app_writer_motion.h"
#include "app_stepper.h"
#include "elog.h"
#include <math.h>
#include <stdint.h>

static const mid_scara_config_t s_scara_cfg = {
    .l1_mm = APP_WRITER_L1_MM,
    .l2_mm = APP_WRITER_L2_MM,
};

typedef struct {
    float radius_mm;
    float cos_q2;
    float sin_q2;
    float q2_deg;
    float error_x_mm;
    float error_y_mm;
} app_writer_ik_diagnostics_t;

typedef struct {
    mid_scara_point_t user_point;
    mid_scara_point_t machine_point;
    mid_scara_angles_t angles;
    app_writer_ik_diagnostics_t ik;
    uint8_t branch;
} app_writer_plan_segment_t;

typedef enum {
    WRITER_MOTION_PHASE_IDLE = 0,
    WRITER_MOTION_PHASE_PRELOAD,
    WRITER_MOTION_PHASE_MAIN,
} writer_motion_phase_t;

static app_writer_pose_t s_pose;
static app_writer_pose_t s_target_pose;
static app_writer_motion_cmd_t s_last_cmd;
static bool s_motion_busy = false;
static bool s_segment_running = false;
static writer_motion_phase_t s_motion_phase = WRITER_MOTION_PHASE_IDLE;
static bool s_motion_ready = false;
static bool s_kinematics_self_test_done = false;
static float s_home_theta_deg = APP_WRITER_THETA_HOME_DEG;
static float s_home_psi_deg = APP_WRITER_PSI_HOME_DEG;
static int32_t s_stage1_abs_steps = 0;
static int32_t s_stage2_abs_steps = 0;
static int32_t s_stage2_motor_abs_steps = 0;
static int32_t s_stage2_comp_bias_steps = 0;
static int8_t s_stage1_logical_dir = 0;
static int8_t s_stage2_motor_dir = 0;
static int32_t s_target_stage1_abs_steps = 0;
static int32_t s_target_stage2_abs_steps = 0;
static int32_t s_target_stage2_motor_abs_steps = 0;
static int32_t s_target_stage2_comp_bias_steps = 0;
static int8_t s_target_stage1_logical_dir = 0;
static int8_t s_target_stage2_motor_dir = 0;
static app_writer_plan_segment_t s_plan[APP_WRITER_PLAN_MAX_SEGMENTS];
static uint32_t s_plan_count = 0u;
static uint32_t s_plan_index = 0u;
static uint32_t s_segment_start_ms = 0u;
static uint32_t s_segment_timeout_ms = 0u;
static uint32_t s_main_segment_timeout_ms = 0u;
static int32_t s_preload_stage2_delta_steps = 0;
static int32_t s_preload_stage2_target_steps = 0;
static uint32_t s_plan_max_freq_hz = APP_WRITER_MOVE_MAX_FREQ_HZ;
static uint32_t s_plan_min_freq_hz = APP_WRITER_MOVE_MIN_FREQ_HZ;
static float s_plan_feed_mm_min = 0.0f;
static bool s_continuous_mode = false;
static app_writer_pose_t s_planned_pose;
static int32_t s_planned_stage1_abs_steps = 0;
static int32_t s_planned_stage2_abs_steps = 0;
static int8_t s_planned_stage1_logical_dir = 0;
static int8_t s_planned_stage2_logical_dir = 0;

extern volatile uint32_t s_sys_tick;

#if APP_WRITER_AUTHOR_LINE_EXECUTION_ENABLE
#define WRITER_MOTION_CARTESIAN_ONLY __attribute__((unused))
#else
#define WRITER_MOTION_CARTESIAN_ONLY
#endif

static uint32_t WriterMotion_Max_U32(uint32_t a, uint32_t b)
{
    return (a > b) ? a : b;
}

static float WriterMotion_Abs_F32(float value)
{
    return (value >= 0.0f) ? value : -value;
}

static bool WriterMotion_In_Range(float value, float min_value, float max_value)
{
    return (value >= min_value) && (value <= max_value);
}

static int32_t WriterMotion_Scale_100(float value)
{
    return (int32_t)((value >= 0.0f) ? (value * 100.0f + 0.5f) : (value * 100.0f - 0.5f));
}

static int32_t WriterMotion_Angle_To_Absolute_Steps(float angle_deg,
                                                     float steps_per_deg)
{
    return (int32_t)lroundf(angle_deg * steps_per_deg);
}

static uint32_t WriterMotion_Abs_I32(int32_t value)
{
    return (uint32_t)((value < 0) ? -value : value);
}

static int8_t WriterMotion_Step_Direction(int32_t delta_steps,
                                          int8_t previous_direction)
{
    if (delta_steps > 0) {
        return 1;
    }
    if (delta_steps < 0) {
        return -1;
    }
    return previous_direction;
}

static int32_t WriterMotion_Next_Stage2_Cross_Bias(
    int8_t next_stage1_direction)
{
#if APP_WRITER_DIRECTION_COMP_ENABLE
    int32_t bias = s_stage2_comp_bias_steps;

    if ((s_stage1_logical_dir != 0) &&
        (next_stage1_direction != 0) &&
        (next_stage1_direction != s_stage1_logical_dir)) {
        bias -= (int32_t)next_stage1_direction *
                APP_WRITER_DIR_COMP_THETA_REV_PSI_STEPS;
    }
    return bias;
#else
    (void)next_stage1_direction;
    return 0;
#endif
}

static uint32_t WriterMotion_Scaled_Freq(uint32_t axis_steps,
                                         uint32_t max_steps,
                                         uint32_t max_freq_hz,
                                         uint32_t min_freq_hz)
{
    (void)min_freq_hz;

    if ((axis_steps == 0u) || (max_steps == 0u)) {
        return 0u;
    }

    uint32_t freq = (uint32_t)((((uint64_t)max_freq_hz * axis_steps) + (max_steps / 2u)) / max_steps);
    if (freq == 0u) {
        freq = 1u;
    }
    return freq;
}

static uint32_t WriterMotion_Master_Freq(const mid_scara_point_t *user_point,
                                         uint32_t max_steps,
                                         float feed_mm_min,
                                         uint32_t min_freq_hz,
                                         uint32_t max_freq_hz)
{
    float dx;
    float dy;
    float distance_mm;
    float requested_freq;
    uint32_t master_freq;

    if ((user_point == 0) || (max_steps == 0u) ||
        (min_freq_hz == 0u) || (max_freq_hz < min_freq_hz)) {
        return 0u;
    }
    if (feed_mm_min <= 0.0f) {
        return max_freq_hz;
    }

    dx = user_point->x_mm - s_pose.user_point.x_mm;
    dy = user_point->y_mm - s_pose.user_point.y_mm;
    distance_mm = hypotf(dx, dy);
    if (distance_mm <= 0.0001f) {
        return min_freq_hz;
    }

    requested_freq = ((float)max_steps * feed_mm_min) /
                     (60.0f * distance_mm);
    if (requested_freq <= (float)min_freq_hz) {
        return min_freq_hz;
    }
    if (requested_freq >= (float)max_freq_hz) {
        return max_freq_hz;
    }

    master_freq = (uint32_t)lroundf(requested_freq);
    return (master_freq == 0u) ? min_freq_hz : master_freq;
}

static void WriterMotion_User_To_Machine(const mid_scara_point_t *user_point,
                                         mid_scara_point_t *machine_point)
{
#if APP_WRITER_AUTHOR_CORE_ENABLE
    float author_x = user_point->x_mm;
    float author_y = user_point->y_mm;
#else
    float author_x = APP_WRITER_XY_CAL_XX * user_point->x_mm +
                     APP_WRITER_XY_CAL_XY * user_point->y_mm;
    float author_y = APP_WRITER_XY_CAL_YX * user_point->x_mm +
                     APP_WRITER_XY_CAL_YY * user_point->y_mm;
#endif

    machine_point->x_mm = author_x + APP_WRITER_MACHINE_OFFSET_X_MM;
    machine_point->y_mm = author_y + APP_WRITER_MACHINE_OFFSET_Y_MM;
}

static void WriterMotion_Machine_To_User(const mid_scara_point_t *machine_point,
                                         mid_scara_point_t *user_point)
{
    float author_x = machine_point->x_mm - APP_WRITER_MACHINE_OFFSET_X_MM;
    float author_y = machine_point->y_mm - APP_WRITER_MACHINE_OFFSET_Y_MM;
#if APP_WRITER_AUTHOR_CORE_ENABLE
    user_point->x_mm = author_x;
    user_point->y_mm = author_y;
#else
    float det = APP_WRITER_XY_CAL_XX * APP_WRITER_XY_CAL_YY -
                APP_WRITER_XY_CAL_XY * APP_WRITER_XY_CAL_YX;

    user_point->x_mm = (APP_WRITER_XY_CAL_YY * author_x -
                        APP_WRITER_XY_CAL_XY * author_y) / det;
    user_point->y_mm = (-APP_WRITER_XY_CAL_YX * author_x +
                        APP_WRITER_XY_CAL_XX * author_y) / det;
#endif
}

static void WriterMotion_Update_Beta(mid_scara_angles_t *angles)
{
    if (angles != 0) {
        angles->beta_deg = mid_scara_beta_deg(angles->theta_deg, angles->psi_deg);
    }
}

static void WriterMotion_Snap_Home_Limits(mid_scara_angles_t *angles)
{
    if (angles == 0) {
        return;
    }

    if (WriterMotion_Abs_F32(angles->theta_deg - s_home_theta_deg) <=
        APP_WRITER_HOME_LIMIT_EPSILON_DEG) {
        angles->theta_deg = s_home_theta_deg;
    }
    if (WriterMotion_Abs_F32(angles->psi_deg - s_home_psi_deg) <=
        APP_WRITER_HOME_LIMIT_EPSILON_DEG) {
        angles->psi_deg = s_home_psi_deg;
    }
    WriterMotion_Update_Beta(angles);
}

static float WriterMotion_Beta_Abs(const mid_scara_angles_t *angles)
{
    return WriterMotion_Abs_F32(angles->beta_deg);
}

bool WriterMotion_Is_Pose_Safe(float theta_deg, float psi_deg)
{
    float beta_deg = mid_scara_beta_deg(theta_deg, psi_deg);
    float abs_beta_deg = WriterMotion_Abs_F32(beta_deg);

    if (!WriterMotion_In_Range(theta_deg, APP_WRITER_THETA_MIN_DEG, APP_WRITER_THETA_MAX_DEG) ||
        !WriterMotion_In_Range(psi_deg, APP_WRITER_PSI_MIN_DEG, APP_WRITER_PSI_MAX_DEG) ||
        !WriterMotion_In_Range(beta_deg, APP_WRITER_BETA_MIN_DEG, APP_WRITER_BETA_MAX_DEG) ||
        (psi_deg <= theta_deg)) {
        return false;
    }

    if (abs_beta_deg < (APP_WRITER_MIN_BETA_ABS_DEG - 0.001f)) {
        return false;
    }

#if APP_WRITER_DANGER_ZONE_ENABLE
    if (WriterMotion_In_Range(theta_deg, APP_WRITER_DANGER_THETA_MIN_DEG, APP_WRITER_DANGER_THETA_MAX_DEG) &&
        WriterMotion_In_Range(beta_deg, APP_WRITER_DANGER_BETA_MIN_DEG, APP_WRITER_DANGER_BETA_MAX_DEG)) {
        return false;
    }
#endif

    return true;
}

bool scara_is_pose_safe(float theta_deg, float psi_deg)
{
    return WriterMotion_Is_Pose_Safe(theta_deg, psi_deg);
}

static bool WriterMotion_Is_Angle_Safe(const mid_scara_angles_t *angles)
{
    return WriterMotion_Is_Pose_Safe(angles->theta_deg, angles->psi_deg);
}

static bool WriterMotion_Angle_Meets_Beta(const mid_scara_angles_t *angles,
                                          float required_beta_abs_deg)
{
    return WriterMotion_Is_Angle_Safe(angles) &&
           (WriterMotion_Beta_Abs(angles) >= (required_beta_abs_deg - 0.001f));
}

static bool WriterMotion_Is_Path_Safe(const mid_scara_angles_t *start_angles,
                                      const mid_scara_angles_t *target_angles,
                                      float required_beta_abs_deg,
                                      float *min_beta_abs_deg)
{
    float d_theta = target_angles->theta_deg - start_angles->theta_deg;
    float d_psi = target_angles->psi_deg - start_angles->psi_deg;
    float max_delta = fmaxf(WriterMotion_Abs_F32(d_theta), WriterMotion_Abs_F32(d_psi));
    uint32_t checks = (uint32_t)(max_delta / APP_WRITER_ANGLE_CHECK_STEP_DEG);
    float path_min_beta = WriterMotion_Beta_Abs(start_angles);

    if ((checks == 0u) || ((float)checks * APP_WRITER_ANGLE_CHECK_STEP_DEG < max_delta)) {
        checks++;
    }

    for (uint32_t i = 0u; i <= checks; i++) {
        float ratio = (checks == 0u) ? 1.0f : ((float)i / (float)checks);
        mid_scara_angles_t check_angles = {
            .theta_deg = start_angles->theta_deg + d_theta * ratio,
            .psi_deg = start_angles->psi_deg + d_psi * ratio,
        };
        WriterMotion_Update_Beta(&check_angles);
        float beta_abs = WriterMotion_Beta_Abs(&check_angles);
        if (beta_abs < path_min_beta) {
            path_min_beta = beta_abs;
        }
        if (!WriterMotion_Angle_Meets_Beta(&check_angles, required_beta_abs_deg)) {
            if (min_beta_abs_deg != 0) {
                *min_beta_abs_deg = path_min_beta;
            }
            return false;
        }
    }

    if (min_beta_abs_deg != 0) {
        *min_beta_abs_deg = path_min_beta;
    }
    return true;
}

static bool WriterMotion_Point_Matches(const mid_scara_point_t *a,
                                       const mid_scara_point_t *b)
{
    return (fabsf(a->x_mm - b->x_mm) <= 0.05f) &&
           (fabsf(a->y_mm - b->y_mm) <= 0.05f);
}

static void WriterMotion_Clear_Plan(void)
{
    s_plan_count = 0u;
    s_plan_index = 0u;
}

static bool WriterMotion_Select_Inverse(const mid_scara_point_t *machine_point,
                                        mid_scara_angles_t *angles,
                                        mid_scara_ik_result_t *ik)
{
    if (!mid_scara_inverse_absolute_ex(&s_scara_cfg, machine_point, MID_SCARA_ELBOW_POSITIVE, ik)) {
        return false;
    }

    WriterMotion_Snap_Home_Limits(&ik->angles);
    if (!WriterMotion_Angle_Meets_Beta(&ik->angles, APP_WRITER_MIN_BETA_ABS_DEG)) {
        return false;
    }

    mid_scara_point_t check_point;
    if (!mid_scara_forward_absolute(&s_scara_cfg, &ik->angles, &check_point) ||
        !WriterMotion_Point_Matches(machine_point, &check_point)) {
        return false;
    }

    ik->fk_point = check_point;
    ik->error_x_mm = check_point.x_mm - machine_point->x_mm;
    ik->error_y_mm = check_point.y_mm - machine_point->y_mm;
    *angles = ik->angles;
    return true;
}

static void WriterMotion_Copy_Ik_Diagnostics(
    app_writer_ik_diagnostics_t *diagnostics,
    const mid_scara_ik_result_t *ik)
{
    if (ik != 0) {
        diagnostics->radius_mm = ik->radius_mm;
        diagnostics->cos_q2 = ik->cos_q2;
        diagnostics->sin_q2 = ik->sin_q2;
        diagnostics->q2_deg = ik->q2_deg;
        diagnostics->error_x_mm = ik->error_x_mm;
        diagnostics->error_y_mm = ik->error_y_mm;
    } else {
        diagnostics->radius_mm = 0.0f;
        diagnostics->cos_q2 = 0.0f;
        diagnostics->sin_q2 = 0.0f;
        diagnostics->q2_deg = 0.0f;
        diagnostics->error_x_mm = 0.0f;
        diagnostics->error_y_mm = 0.0f;
    }
}

static bool WriterMotion_Append_Plan_Segment(const mid_scara_point_t *user_point,
                                             const mid_scara_point_t *machine_point,
                                             const mid_scara_angles_t *angles,
                                             const mid_scara_ik_result_t *ik,
                                             uint8_t branch)
{
    if (s_plan_count >= APP_WRITER_PLAN_MAX_SEGMENTS) {
        elog_e("MOTION", "[MOTION] plan overflow max=%u", APP_WRITER_PLAN_MAX_SEGMENTS);
        return false;
    }

    s_plan[s_plan_count].user_point = *user_point;
    s_plan[s_plan_count].machine_point = *machine_point;
    s_plan[s_plan_count].angles = *angles;
    WriterMotion_Copy_Ik_Diagnostics(&s_plan[s_plan_count].ik, ik);
    s_plan[s_plan_count].branch = branch;
    s_plan_count++;
    return true;
}

static uint32_t WriterMotion_Line_Segment_Count(const mid_scara_point_t *start_point,
                                                const mid_scara_point_t *target_point)
{
    float dx = target_point->x_mm - start_point->x_mm;
    float dy = target_point->y_mm - start_point->y_mm;
    float span = fmaxf(WriterMotion_Abs_F32(dx), WriterMotion_Abs_F32(dy));
    uint32_t segments = (uint32_t)(span / APP_WRITER_PLAN_SEGMENT_MM);

    if ((segments == 0u) || ((float)segments * APP_WRITER_PLAN_SEGMENT_MM < span)) {
        segments++;
    }

    return segments;
}

static bool WriterMotion_Plan_Joint_Target(const mid_scara_point_t *user_point,
                                           const mid_scara_point_t *machine_point,
                                           const mid_scara_angles_t *start_angles,
                                           const mid_scara_angles_t *target_angles,
                                           float required_beta_abs_deg)
{
    float min_beta_abs = 0.0f;

    if (!WriterMotion_Is_Path_Safe(start_angles, target_angles, required_beta_abs_deg, &min_beta_abs)) {
        elog_e("MOTION", "[MOTION] waypoint unsafe theta=%d psi=%d beta=%d path_min_beta=%d min=%d",
               WriterMotion_Scale_100(target_angles->theta_deg),
               WriterMotion_Scale_100(target_angles->psi_deg),
               WriterMotion_Scale_100(target_angles->beta_deg),
               WriterMotion_Scale_100(min_beta_abs),
               WriterMotion_Scale_100(required_beta_abs_deg));
        return false;
    }

    return WriterMotion_Append_Plan_Segment(user_point,
                                            machine_point,
                                            target_angles,
                                            0,
                                            APP_WRITER_BRANCH_DIRECT);
}

static bool WriterMotion_Plan_Line(const mid_scara_point_t *start_user_point,
                                   const mid_scara_angles_t *start_angles,
                                   const mid_scara_point_t *target_user_point,
                                   float required_beta_abs_deg,
                                   mid_scara_point_t *out_user_point,
                                   mid_scara_angles_t *out_angles)
{
    uint32_t segments = WriterMotion_Line_Segment_Count(start_user_point, target_user_point);
    mid_scara_angles_t prev_angles = *start_angles;
    mid_scara_point_t prev_user_point = *start_user_point;

    elog_i("MOTION", "[MOTION] plan line user_x=%d user_y=%d target_user_x=%d target_user_y=%d segments=%u",
           WriterMotion_Scale_100(start_user_point->x_mm),
           WriterMotion_Scale_100(start_user_point->y_mm),
           WriterMotion_Scale_100(target_user_point->x_mm),
           WriterMotion_Scale_100(target_user_point->y_mm),
           segments);

    for (uint32_t i = 1u; i <= segments; i++) {
        float ratio = (float)i / (float)segments;
        mid_scara_point_t user_point = {
            .x_mm = start_user_point->x_mm + (target_user_point->x_mm - start_user_point->x_mm) * ratio,
            .y_mm = start_user_point->y_mm + (target_user_point->y_mm - start_user_point->y_mm) * ratio,
        };
        mid_scara_point_t machine_point;
        mid_scara_angles_t angles;
        mid_scara_ik_result_t ik;
        float min_beta_abs = 0.0f;

        WriterMotion_User_To_Machine(&user_point, &machine_point);
        if (!WriterMotion_Select_Inverse(&machine_point, &angles, &ik)) {
            elog_e("MOTION", "[MOTION] plan inverse rejected step=%u user_x=%d user_y=%d machine_x=%d machine_y=%d",
                   i,
                   WriterMotion_Scale_100(user_point.x_mm),
                   WriterMotion_Scale_100(user_point.y_mm),
                   WriterMotion_Scale_100(machine_point.x_mm),
                   WriterMotion_Scale_100(machine_point.y_mm));
            return false;
        }

        if (!WriterMotion_Is_Path_Safe(&prev_angles, &angles, required_beta_abs_deg, &min_beta_abs)) {
            elog_e("MOTION", "[MOTION] plan path unsafe step=%u theta=%d psi=%d beta=%d path_min_beta=%d min=%d",
                   i,
                   WriterMotion_Scale_100(angles.theta_deg),
                   WriterMotion_Scale_100(angles.psi_deg),
                   WriterMotion_Scale_100(angles.beta_deg),
                   WriterMotion_Scale_100(min_beta_abs),
                   WriterMotion_Scale_100(required_beta_abs_deg));
            return false;
        }

        if (!WriterMotion_Append_Plan_Segment(&user_point,
                                              &machine_point,
                                              &angles,
                                              &ik,
                                              APP_WRITER_BRANCH_IK_ELBOW_POSITIVE)) {
            return false;
        }

        prev_user_point = user_point;
        prev_angles = angles;
    }

    if (out_user_point != 0) {
        *out_user_point = prev_user_point;
    }
    if (out_angles != 0) {
        *out_angles = prev_angles;
    }
    return true;
}

static bool WRITER_MOTION_CARTESIAN_ONLY
WriterMotion_Plan_Direct_To(const mid_scara_point_t *target_user_point)
{
    mid_scara_point_t end_user_point;
    mid_scara_angles_t end_angles;

    WriterMotion_Clear_Plan();
    return WriterMotion_Plan_Line(&s_pose.user_point,
                                  &s_pose.angles,
                                  target_user_point,
                                  APP_WRITER_MIN_BETA_ABS_DEG,
                                  &end_user_point,
                                  &end_angles);
}

static bool WRITER_MOTION_CARTESIAN_ONLY
WriterMotion_Plan_Via_Safe_Waypoint(
    const mid_scara_point_t *target_user_point)
{
    mid_scara_angles_t safe_angles = {
        .theta_deg = APP_WRITER_SAFE_WAYPOINT_THETA_DEG,
        .psi_deg = APP_WRITER_SAFE_WAYPOINT_PSI_DEG,
    };
    mid_scara_point_t safe_machine_point;
    mid_scara_point_t safe_user_point;
    mid_scara_point_t end_user_point;
    mid_scara_angles_t end_angles;

    WriterMotion_Update_Beta(&safe_angles);
    WriterMotion_Clear_Plan();

    if (!WriterMotion_Is_Angle_Safe(&safe_angles) ||
        !mid_scara_forward_absolute(&s_scara_cfg, &safe_angles, &safe_machine_point)) {
        elog_e("MOTION", "[MOTION] safe waypoint invalid theta=%d psi=%d beta=%d",
               WriterMotion_Scale_100(safe_angles.theta_deg),
               WriterMotion_Scale_100(safe_angles.psi_deg),
               WriterMotion_Scale_100(safe_angles.beta_deg));
        return false;
    }
    WriterMotion_Machine_To_User(&safe_machine_point, &safe_user_point);

    elog_w("MOTION", "[MOTION] try safe waypoint theta=%d psi=%d beta=%d user_x=%d user_y=%d",
           WriterMotion_Scale_100(safe_angles.theta_deg),
           WriterMotion_Scale_100(safe_angles.psi_deg),
           WriterMotion_Scale_100(safe_angles.beta_deg),
           WriterMotion_Scale_100(safe_user_point.x_mm),
           WriterMotion_Scale_100(safe_user_point.y_mm));

    if (!WriterMotion_Plan_Joint_Target(&safe_user_point,
                                        &safe_machine_point,
                                        &s_pose.angles,
                                        &safe_angles,
                                        APP_WRITER_MIN_BETA_ABS_DEG)) {
        return false;
    }

    return WriterMotion_Plan_Line(&safe_user_point,
                                  &safe_angles,
                                  target_user_point,
                                  APP_WRITER_MIN_BETA_ABS_DEG,
                                  &end_user_point,
                                  &end_angles);
}

static bool WriterMotion_Dir_Sign_Configured(void)
{
    return (APP_WRITER_STAGE1_DIR_SIGN != 0) && (APP_WRITER_STAGE2_DIR_SIGN != 0);
}

static bool WriterMotion_Dir_From_Delta(float delta_deg,
                                        int dir_sign,
                                        uint8_t positive_dir,
                                        uint8_t *dir)
{
    if ((dir == 0) || (dir_sign == 0)) {
        return false;
    }

    bool angle_increases = (delta_deg >= 0.0f);
    bool use_positive_dir = (dir_sign > 0) ? angle_increases : !angle_increases;
    *dir = use_positive_dir ? positive_dir : (uint8_t)(1u - positive_dir);
    return true;
}

static uint32_t WriterMotion_Master_Freq_Between(
    const mid_scara_point_t *start_user_point,
    const mid_scara_point_t *target_user_point,
    uint32_t max_steps,
    float feed_mm_min,
    uint32_t min_freq_hz,
    uint32_t max_freq_hz)
{
    float distance_mm;
    float requested_freq;
    uint32_t master_freq;

    if ((start_user_point == 0) || (target_user_point == 0) ||
        (max_steps == 0u) || (min_freq_hz == 0u) ||
        (max_freq_hz < min_freq_hz)) {
        return 0u;
    }
    if (feed_mm_min <= 0.0f) {
        return max_freq_hz;
    }

    distance_mm = hypotf(
        target_user_point->x_mm - start_user_point->x_mm,
        target_user_point->y_mm - start_user_point->y_mm);
    if (distance_mm <= 0.0001f) {
        return min_freq_hz;
    }

    requested_freq = ((float)max_steps * feed_mm_min) /
                     (60.0f * distance_mm);
    if (requested_freq <= (float)min_freq_hz) {
        return min_freq_hz;
    }
    if (requested_freq >= (float)max_freq_hz) {
        return max_freq_hz;
    }

    master_freq = (uint32_t)lroundf(requested_freq);
    return (master_freq == 0u) ? min_freq_hz : master_freq;
}

static bool WriterMotion_Plan_From_Planned(
    const mid_scara_point_t *target_user_point)
{
    mid_scara_point_t safe_machine_point;
    mid_scara_point_t safe_user_point;
    mid_scara_angles_t safe_angles = {
        .theta_deg = APP_WRITER_SAFE_WAYPOINT_THETA_DEG,
        .psi_deg = APP_WRITER_SAFE_WAYPOINT_PSI_DEG,
    };

    WriterMotion_Clear_Plan();
    if (WriterMotion_Plan_Line(&s_planned_pose.user_point,
                               &s_planned_pose.angles,
                               target_user_point,
                               APP_WRITER_MIN_BETA_ABS_DEG,
                               0, 0)) {
        return true;
    }

    WriterMotion_Clear_Plan();
    WriterMotion_Update_Beta(&safe_angles);
    if (!WriterMotion_Is_Angle_Safe(&safe_angles) ||
        !mid_scara_forward_absolute(&s_scara_cfg, &safe_angles,
                                    &safe_machine_point)) {
        return false;
    }
    WriterMotion_Machine_To_User(&safe_machine_point,
                                 &safe_user_point);
    if (!WriterMotion_Plan_Joint_Target(
            &safe_user_point, &safe_machine_point,
            &s_planned_pose.angles, &safe_angles,
            APP_WRITER_MIN_BETA_ABS_DEG)) {
        WriterMotion_Clear_Plan();
        return false;
    }
    if (!WriterMotion_Plan_Line(&safe_user_point, &safe_angles,
                                target_user_point,
                                APP_WRITER_MIN_BETA_ABS_DEG,
                                0, 0)) {
        WriterMotion_Clear_Plan();
        return false;
    }
    return true;
}

static void WriterMotion_Update_Continuous_Pose(void)
{
    int32_t stage1_steps;
    int32_t stage2_steps;

    App_Stepper_Dual_Queue_Get_Position(&stage1_steps,
                                        &stage2_steps);
    s_stage1_abs_steps = stage1_steps;
    s_stage2_abs_steps = stage2_steps;
    s_stage2_motor_abs_steps = stage2_steps;
    s_stage2_comp_bias_steps = 0;
    s_pose.angles.theta_deg =
        (float)stage1_steps / APP_WRITER_STAGE1_STEPS_PER_DEG;
    s_pose.angles.psi_deg =
        (float)stage2_steps / APP_WRITER_STAGE2_STEPS_PER_DEG;
    WriterMotion_Update_Beta(&s_pose.angles);
    if (mid_scara_forward_absolute(&s_scara_cfg, &s_pose.angles,
                                   &s_pose.machine_point)) {
        WriterMotion_Machine_To_User(&s_pose.machine_point,
                                     &s_pose.user_point);
    }
}

static app_writer_queue_result_t
WriterMotion_Queue_To_Profile(float user_x_mm, float user_y_mm,
                              float feed_mm_min,
                              uint32_t min_freq_hz,
                              uint32_t max_freq_hz)
{
    mid_scara_point_t target_user_point = {
        .x_mm = user_x_mm,
        .y_mm = user_y_mm,
    };
    app_writer_pose_t next_pose;
    int32_t next_stage1_steps;
    int32_t next_stage2_steps;
    int8_t next_stage1_dir;
    int8_t next_stage2_dir;
    uint32_t block_count = 0u;

#if APP_WRITER_DIRECTION_COMP_ENABLE
    elog_e("MOTION", "[MOTION] continuous queue requires dircomp=0");
    return APP_WRITER_QUEUE_REJECTED;
#endif

    if (!s_motion_ready || !WriterMotion_Dir_Sign_Configured() ||
        (min_freq_hz == 0u) || (max_freq_hz < min_freq_hz) ||
        (feed_mm_min < 0.0f)) {
        return APP_WRITER_QUEUE_REJECTED;
    }
    if (!WriterMotion_Plan_From_Planned(&target_user_point)) {
        elog_e("MOTION",
               "[MOTION] continuous plan rejected user_x=%d user_y=%d",
               WriterMotion_Scale_100(user_x_mm),
               WriterMotion_Scale_100(user_y_mm));
        return APP_WRITER_QUEUE_REJECTED;
    }

    next_pose = s_planned_pose;
    next_stage1_steps = s_planned_stage1_abs_steps;
    next_stage2_steps = s_planned_stage2_abs_steps;
    next_stage1_dir = s_planned_stage1_logical_dir;
    next_stage2_dir = s_planned_stage2_logical_dir;

    for (uint32_t i = 0u; i < s_plan_count; i++) {
        const app_writer_plan_segment_t *segment = &s_plan[i];
        int32_t target_stage1_steps =
            WriterMotion_Angle_To_Absolute_Steps(
                segment->angles.theta_deg,
                APP_WRITER_STAGE1_STEPS_PER_DEG);
        int32_t target_stage2_steps =
            WriterMotion_Angle_To_Absolute_Steps(
                segment->angles.psi_deg,
                APP_WRITER_STAGE2_STEPS_PER_DEG);
        int32_t delta_stage1 =
            target_stage1_steps - next_stage1_steps;
        int32_t delta_stage2 =
            target_stage2_steps - next_stage2_steps;
        uint32_t stage1_steps =
            WriterMotion_Abs_I32(delta_stage1);
        uint32_t stage2_steps =
            WriterMotion_Abs_I32(delta_stage2);
        uint32_t master_steps =
            WriterMotion_Max_U32(stage1_steps, stage2_steps);

        if (master_steps != 0u) {
            block_count++;
        }

        next_pose.user_point = segment->user_point;
        next_pose.machine_point = segment->machine_point;
        next_pose.angles = segment->angles;
        next_stage1_steps = target_stage1_steps;
        next_stage2_steps = target_stage2_steps;
        next_stage1_dir = WriterMotion_Step_Direction(
            delta_stage1, next_stage1_dir);
        next_stage2_dir = WriterMotion_Step_Direction(
            delta_stage2, next_stage2_dir);
    }

    if (block_count > App_Stepper_Dual_Queue_Free()) {
        WriterMotion_Clear_Plan();
        return APP_WRITER_QUEUE_FULL;
    }

    next_pose = s_planned_pose;
    next_stage1_steps = s_planned_stage1_abs_steps;
    next_stage2_steps = s_planned_stage2_abs_steps;
    next_stage1_dir = s_planned_stage1_logical_dir;
    next_stage2_dir = s_planned_stage2_logical_dir;

    for (uint32_t i = 0u; i < s_plan_count; i++) {
        const app_writer_plan_segment_t *segment = &s_plan[i];
        int32_t target_stage1_steps =
            WriterMotion_Angle_To_Absolute_Steps(
                segment->angles.theta_deg,
                APP_WRITER_STAGE1_STEPS_PER_DEG);
        int32_t target_stage2_steps =
            WriterMotion_Angle_To_Absolute_Steps(
                segment->angles.psi_deg,
                APP_WRITER_STAGE2_STEPS_PER_DEG);
        int32_t delta_stage1 =
            target_stage1_steps - next_stage1_steps;
        int32_t delta_stage2 =
            target_stage2_steps - next_stage2_steps;
        uint32_t stage1_steps =
            WriterMotion_Abs_I32(delta_stage1);
        uint32_t stage2_steps =
            WriterMotion_Abs_I32(delta_stage2);
        uint32_t master_steps =
            WriterMotion_Max_U32(stage1_steps, stage2_steps);

        if (master_steps != 0u) {
            app_stepper_dual_block_t block = {0};

            if ((stage1_steps != 0u) &&
                !WriterMotion_Dir_From_Delta(
                    (float)delta_stage1,
                    APP_WRITER_STAGE1_DIR_SIGN,
                    APP_WRITER_STAGE1_POSITIVE_DIR,
                    &block.stage1_dir)) {
                WriterMotion_Emergency_Stop();
                return APP_WRITER_QUEUE_REJECTED;
            }
            if ((stage2_steps != 0u) &&
                !WriterMotion_Dir_From_Delta(
                    (float)delta_stage2,
                    APP_WRITER_STAGE2_PSI_DIR_SIGN,
                    APP_WRITER_STAGE2_POSITIVE_DIR,
                    &block.stage2_dir)) {
                WriterMotion_Emergency_Stop();
                return APP_WRITER_QUEUE_REJECTED;
            }
            block.stage1_position_sign =
                (delta_stage1 > 0) ? 1 :
                ((delta_stage1 < 0) ? -1 : 0);
            block.stage2_position_sign =
                (delta_stage2 > 0) ? 1 :
                ((delta_stage2 < 0) ? -1 : 0);
            block.stage1_steps = stage1_steps;
            block.stage2_steps = stage2_steps;
            block.master_freq_hz =
                WriterMotion_Master_Freq_Between(
                    &next_pose.user_point,
                    &segment->user_point,
                    master_steps, feed_mm_min,
                    min_freq_hz, max_freq_hz);
            if ((block.master_freq_hz == 0u) ||
                !App_Stepper_Dual_Queue_Block(&block)) {
                WriterMotion_Emergency_Stop();
                return APP_WRITER_QUEUE_REJECTED;
            }
        }

        next_pose.user_point = segment->user_point;
        next_pose.machine_point = segment->machine_point;
        next_pose.angles = segment->angles;
        next_stage1_steps = target_stage1_steps;
        next_stage2_steps = target_stage2_steps;
        next_stage1_dir = WriterMotion_Step_Direction(
            delta_stage1, next_stage1_dir);
        next_stage2_dir = WriterMotion_Step_Direction(
            delta_stage2, next_stage2_dir);
    }

    s_planned_pose = next_pose;
    s_planned_stage1_abs_steps = next_stage1_steps;
    s_planned_stage2_abs_steps = next_stage2_steps;
    s_planned_stage1_logical_dir = next_stage1_dir;
    s_planned_stage2_logical_dir = next_stage2_dir;
    s_target_pose = next_pose;
    s_target_stage1_abs_steps = next_stage1_steps;
    s_target_stage2_abs_steps = next_stage2_steps;
    s_target_stage2_motor_abs_steps = next_stage2_steps;
    s_target_stage2_comp_bias_steps = 0;
    s_target_stage1_logical_dir = next_stage1_dir;
    s_target_stage2_motor_dir = next_stage2_dir;
    s_motion_busy = App_Stepper_Dual_Queue_IsBusy();
    s_continuous_mode = s_motion_busy;
    WriterMotion_Clear_Plan();
    return APP_WRITER_QUEUE_ACCEPTED;
}

static bool WriterMotion_Start_Main_Dda(void)
{
    if ((s_last_cmd.stage1_steps == 0u) &&
        (s_last_cmd.stage2_steps == 0u)) {
        s_segment_running = false;
        s_motion_phase = WRITER_MOTION_PHASE_IDLE;
        return true;
    }

    if (!App_Stepper_Dual_Run(s_last_cmd.stage1_dir,
                              s_last_cmd.stage1_steps,
                              s_last_cmd.stage2_dir,
                              s_last_cmd.stage2_steps,
                              s_last_cmd.master_freq_hz)) {
        elog_e("MOTION", "[MOTION] DDA start rejected s1=%u s2=%u master_f=%u",
               s_last_cmd.stage1_steps,
               s_last_cmd.stage2_steps,
               s_last_cmd.master_freq_hz);
        return false;
    }

    s_segment_start_ms = s_sys_tick;
    s_segment_timeout_ms = s_main_segment_timeout_ms;
    s_motion_phase = WRITER_MOTION_PHASE_MAIN;
    s_segment_running = true;
    s_motion_busy = true;
    return true;
}

static void WriterMotion_Commit_Target_State(void)
{
    s_pose = s_target_pose;
    s_stage1_abs_steps = s_target_stage1_abs_steps;
    s_stage2_abs_steps = s_target_stage2_abs_steps;
    s_stage2_motor_abs_steps = s_target_stage2_motor_abs_steps;
    s_stage2_comp_bias_steps = s_target_stage2_comp_bias_steps;
    s_stage1_logical_dir = s_target_stage1_logical_dir;
    s_stage2_motor_dir = s_target_stage2_motor_dir;
}

static bool WriterMotion_Start_Target(const mid_scara_point_t *user_point,
                                       const mid_scara_point_t *machine_point,
                                       const mid_scara_angles_t *target_angles,
                                       uint32_t max_freq_hz,
                                       uint32_t min_freq_hz,
                                       float feed_mm_min,
                                       float required_beta_abs_deg,
                                      uint8_t branch,
                                      const app_writer_ik_diagnostics_t *ik_result,
                                      bool allow_busy,
                                      const char *mode)
{
    if (s_motion_busy && !allow_busy) {
        elog_w("MOTION", "[MOTION] start rejected busy");
        return false;
    }

    if (s_segment_running) {
        elog_w("MOTION", "[MOTION] start rejected segment running");
        return false;
    }

    if (!s_motion_ready) {
        elog_e("MOTION", "[MOTION] start rejected pose not ready");
        return false;
    }

    if ((user_point == 0) || (machine_point == 0) || (target_angles == 0) ||
        (max_freq_hz == 0u) || (min_freq_hz == 0u) ||
        (min_freq_hz > max_freq_hz)) {
        elog_e("MOTION", "[MOTION] start target invalid");
        return false;
    }

    if (!WriterMotion_Dir_Sign_Configured()) {
        elog_e("MOTION", "[MOTION] joint move rejected: set APP_WRITER_STAGE1_DIR_SIGN and APP_WRITER_STAGE2_DIR_SIGN after DIR calibration");
        return false;
    }

    float min_beta_abs = 0.0f;
    if (!WriterMotion_Is_Path_Safe(&s_pose.angles, target_angles, required_beta_abs_deg, &min_beta_abs)) {
        elog_e("MOTION", "[MOTION] unsafe angle theta=%d psi=%d beta=%d path_min_beta=%d min=%d branch=%u",
               WriterMotion_Scale_100(target_angles->theta_deg),
               WriterMotion_Scale_100(target_angles->psi_deg),
               WriterMotion_Scale_100(target_angles->beta_deg),
               WriterMotion_Scale_100(min_beta_abs),
               WriterMotion_Scale_100(required_beta_abs_deg),
               branch);
        return false;
    }

    float d_theta = target_angles->theta_deg - s_pose.angles.theta_deg;
    float d_psi = target_angles->psi_deg - s_pose.angles.psi_deg;
    float d_beta = target_angles->beta_deg - s_pose.angles.beta_deg;
    int32_t target_stage1_steps = WriterMotion_Angle_To_Absolute_Steps(
        target_angles->theta_deg, APP_WRITER_STAGE1_STEPS_PER_DEG);
    int32_t target_stage2_steps = WriterMotion_Angle_To_Absolute_Steps(
        target_angles->psi_deg, APP_WRITER_STAGE2_STEPS_PER_DEG);
    int32_t logical_delta_stage1_steps = target_stage1_steps - s_stage1_abs_steps;
    int32_t logical_delta_stage2_steps = target_stage2_steps - s_stage2_abs_steps;
    int8_t next_stage1_logical_dir = WriterMotion_Step_Direction(
        logical_delta_stage1_steps, s_stage1_logical_dir);
    int8_t next_stage2_motor_dir = WriterMotion_Step_Direction(
        logical_delta_stage2_steps, s_stage2_motor_dir);
    int32_t next_stage2_comp_bias_steps = WriterMotion_Next_Stage2_Cross_Bias(
        next_stage1_logical_dir);

#if APP_WRITER_DIRECTION_COMP_ENABLE
    if ((logical_delta_stage2_steps != 0) &&
        (s_stage2_motor_dir != 0) &&
        (next_stage2_motor_dir != s_stage2_motor_dir)) {
        next_stage2_comp_bias_steps += (int32_t)next_stage2_motor_dir *
                                       APP_WRITER_DIR_COMP_PSI_REV_PSI_STEPS;
    }
#endif

    int32_t preload_stage2_delta_steps = next_stage2_comp_bias_steps -
                                         s_stage2_comp_bias_steps;

    if (next_stage2_comp_bias_steps != s_stage2_comp_bias_steps) {
        elog_i("DIRCOMP", "[DIRCOMP] theta_dir=%d->%d stage2_motor_dir=%d->%d bias=%d->%d preload_delta=%d logical_delta=%d",
               s_stage1_logical_dir,
               next_stage1_logical_dir,
               s_stage2_motor_dir,
               next_stage2_motor_dir,
               s_stage2_comp_bias_steps,
               next_stage2_comp_bias_steps,
               preload_stage2_delta_steps,
               logical_delta_stage2_steps);
    }

    if (WriterMotion_Abs_I32(next_stage2_comp_bias_steps) >
        APP_WRITER_DIRECTION_COMP_MAX_BIAS_STEPS) {
        elog_e("MOTION", "[MOTION] direction compensation bias rejected bias=%d max=%d",
               next_stage2_comp_bias_steps,
               APP_WRITER_DIRECTION_COMP_MAX_BIAS_STEPS);
        return false;
    }

    int32_t target_stage2_motor_steps = target_stage2_steps +
                                        next_stage2_comp_bias_steps;
    int32_t preload_stage2_motor_steps = s_stage2_motor_abs_steps +
                                         preload_stage2_delta_steps;
    int32_t stage2_motor_min_steps = WriterMotion_Angle_To_Absolute_Steps(
        APP_WRITER_PSI_LIMIT_DEG, APP_WRITER_STAGE2_STEPS_PER_DEG);
    int32_t stage2_motor_max_steps = WriterMotion_Angle_To_Absolute_Steps(
        APP_WRITER_PSI_MAX_DEG, APP_WRITER_STAGE2_STEPS_PER_DEG);
    if ((s_stage2_motor_abs_steps !=
         (s_stage2_abs_steps + s_stage2_comp_bias_steps)) ||
        (preload_stage2_motor_steps !=
         (s_stage2_abs_steps + next_stage2_comp_bias_steps))) {
        elog_e("MOTION", "[MOTION] Stage2 logical/motor invariant failed logical=%d motor=%d bias=%d preload_motor=%d next_bias=%d",
               s_stage2_abs_steps,
               s_stage2_motor_abs_steps,
               s_stage2_comp_bias_steps,
               preload_stage2_motor_steps,
               next_stage2_comp_bias_steps);
        return false;
    }
    if ((preload_stage2_motor_steps < stage2_motor_min_steps) ||
        (preload_stage2_motor_steps > stage2_motor_max_steps) ||
        (target_stage2_motor_steps < stage2_motor_min_steps) ||
        (target_stage2_motor_steps > stage2_motor_max_steps)) {
        elog_e("MOTION", "[MOTION] compensated Stage2 target rejected preload=%d motor=%d range=%d..%d logical=%d bias=%d",
               preload_stage2_motor_steps,
               target_stage2_motor_steps,
               stage2_motor_min_steps,
               stage2_motor_max_steps,
               target_stage2_steps,
               next_stage2_comp_bias_steps);
        return false;
    }

    mid_scara_angles_t compensated_start_angles = {
        .theta_deg = (float)s_stage1_abs_steps /
                     APP_WRITER_STAGE1_STEPS_PER_DEG,
        .psi_deg = (float)s_stage2_motor_abs_steps /
                   APP_WRITER_STAGE2_STEPS_PER_DEG,
    };
    mid_scara_angles_t compensated_target_angles = {
        .theta_deg = (float)target_stage1_steps /
                     APP_WRITER_STAGE1_STEPS_PER_DEG,
        .psi_deg = (float)target_stage2_motor_steps /
                   APP_WRITER_STAGE2_STEPS_PER_DEG,
    };
    mid_scara_angles_t compensated_preload_angles = {
        .theta_deg = (float)s_stage1_abs_steps /
                     APP_WRITER_STAGE1_STEPS_PER_DEG,
        .psi_deg = (float)preload_stage2_motor_steps /
                   APP_WRITER_STAGE2_STEPS_PER_DEG,
    };
    float compensated_preload_min_beta_abs = 0.0f;
    float compensated_main_min_beta_abs = 0.0f;
    WriterMotion_Update_Beta(&compensated_start_angles);
    WriterMotion_Update_Beta(&compensated_preload_angles);
    WriterMotion_Update_Beta(&compensated_target_angles);
    if (!WriterMotion_Is_Path_Safe(&compensated_start_angles,
                                   &compensated_preload_angles,
                                   required_beta_abs_deg,
                                   &compensated_preload_min_beta_abs) ||
        !WriterMotion_Is_Path_Safe(&compensated_preload_angles,
                                   &compensated_target_angles,
                                   required_beta_abs_deg,
                                   &compensated_main_min_beta_abs)) {
        elog_e("MOTION", "[MOTION] compensated path rejected theta=%d preload_psi=%d psi_motor=%d beta_motor=%d preload_min_beta=%d main_min_beta=%d bias=%d",
               WriterMotion_Scale_100(compensated_target_angles.theta_deg),
               WriterMotion_Scale_100(compensated_preload_angles.psi_deg),
               WriterMotion_Scale_100(compensated_target_angles.psi_deg),
               WriterMotion_Scale_100(compensated_target_angles.beta_deg),
               WriterMotion_Scale_100(compensated_preload_min_beta_abs),
               WriterMotion_Scale_100(compensated_main_min_beta_abs),
               next_stage2_comp_bias_steps);
        return false;
    }

    int32_t delta_stage1_steps = logical_delta_stage1_steps;
    int32_t delta_stage2_steps = logical_delta_stage2_steps;
    uint32_t stage1_steps = WriterMotion_Abs_I32(delta_stage1_steps);
    uint32_t stage2_steps = WriterMotion_Abs_I32(delta_stage2_steps);
    uint32_t preload_stage2_steps =
        WriterMotion_Abs_I32(preload_stage2_delta_steps);
    uint32_t max_steps = WriterMotion_Max_U32(stage1_steps, stage2_steps);
    uint32_t master_freq = WriterMotion_Master_Freq(user_point,
                                                     max_steps,
                                                     feed_mm_min,
                                                     min_freq_hz,
                                                     max_freq_hz);
    uint8_t stage1_dir = 0u;
    uint8_t stage2_dir = 0u;
    uint8_t preload_stage2_dir = 0u;

    if ((stage1_steps != 0u) &&
        !WriterMotion_Dir_From_Delta((float)delta_stage1_steps, APP_WRITER_STAGE1_DIR_SIGN, APP_WRITER_STAGE1_POSITIVE_DIR, &stage1_dir)) {
        return false;
    }
    if ((stage2_steps != 0u) &&
        !WriterMotion_Dir_From_Delta((float)delta_stage2_steps, APP_WRITER_STAGE2_PSI_DIR_SIGN, APP_WRITER_STAGE2_POSITIVE_DIR, &stage2_dir)) {
        return false;
    }
    if ((preload_stage2_steps != 0u) &&
        !WriterMotion_Dir_From_Delta((float)preload_stage2_delta_steps,
                                     APP_WRITER_STAGE2_PSI_DIR_SIGN,
                                     APP_WRITER_STAGE2_POSITIVE_DIR,
                                     &preload_stage2_dir)) {
        return false;
    }

    uint32_t stage1_freq = WriterMotion_Scaled_Freq(stage1_steps, max_steps, master_freq, min_freq_hz);
    uint32_t stage2_freq = WriterMotion_Scaled_Freq(stage2_steps, max_steps, master_freq, min_freq_hz);
    uint32_t active_freq = (stage1_freq > stage2_freq) ? stage1_freq : stage2_freq;
    uint32_t move_time_ms = (active_freq != 0u) ? (uint32_t)(((uint64_t)max_steps * 1000u) / active_freq) : 0u;

    s_target_pose.user_point = *user_point;
    s_target_pose.machine_point = *machine_point;
    s_target_pose.angles = *target_angles;
    s_last_cmd.target_pose = s_target_pose;
    s_last_cmd.delta_theta_deg = d_theta;
    s_last_cmd.delta_psi_deg = d_psi;
    s_last_cmd.delta_beta_deg = d_beta;
    s_last_cmd.stage1_target_steps = target_stage1_steps;
    s_last_cmd.stage2_target_steps = target_stage2_steps;
    s_last_cmd.stage2_motor_target_steps = target_stage2_motor_steps;
    s_last_cmd.stage2_comp_bias_steps = next_stage2_comp_bias_steps;
    s_last_cmd.stage1_logical_dir = next_stage1_logical_dir;
    s_last_cmd.stage2_motor_dir = next_stage2_motor_dir;
    s_last_cmd.stage1_steps = stage1_steps;
    s_last_cmd.stage2_steps = stage2_steps;
    s_last_cmd.stage1_dir = stage1_dir;
    s_last_cmd.stage2_dir = stage2_dir;
    s_last_cmd.stage1_freq_hz = stage1_freq;
    s_last_cmd.stage2_freq_hz = stage2_freq;
    s_last_cmd.master_freq_hz = master_freq;
    s_last_cmd.requested_feed_mm_min = feed_mm_min;
    s_last_cmd.path_min_beta_abs_deg = min_beta_abs;
    s_last_cmd.required_beta_abs_deg = required_beta_abs_deg;
    s_last_cmd.branch = branch;
    if (ik_result != 0) {
        s_last_cmd.ik_radius_mm = ik_result->radius_mm;
        s_last_cmd.ik_cos_q2 = ik_result->cos_q2;
        s_last_cmd.ik_sin_q2 = ik_result->sin_q2;
        s_last_cmd.ik_q2_deg = ik_result->q2_deg;
        s_last_cmd.ik_error_x_mm = ik_result->error_x_mm;
        s_last_cmd.ik_error_y_mm = ik_result->error_y_mm;
    } else {
        s_last_cmd.ik_radius_mm = 0.0f;
        s_last_cmd.ik_cos_q2 = 0.0f;
        s_last_cmd.ik_sin_q2 = 0.0f;
        s_last_cmd.ik_q2_deg = 0.0f;
        s_last_cmd.ik_error_x_mm = 0.0f;
        s_last_cmd.ik_error_y_mm = 0.0f;
    }

    if (ik_result != 0) {
        elog_i("MOTION", "[MOTION] ik user_x=%d user_y=%d machine_x=%d machine_y=%d std_x=%d std_y=%d r=%d c2=%d s2=%d q2=%d branch=%u",
               WriterMotion_Scale_100(user_point->x_mm),
               WriterMotion_Scale_100(user_point->y_mm),
               WriterMotion_Scale_100(machine_point->x_mm),
               WriterMotion_Scale_100(machine_point->y_mm),
               WriterMotion_Scale_100(-machine_point->x_mm),
               WriterMotion_Scale_100(machine_point->y_mm),
               WriterMotion_Scale_100(ik_result->radius_mm),
               WriterMotion_Scale_100(ik_result->cos_q2),
               WriterMotion_Scale_100(ik_result->sin_q2),
               WriterMotion_Scale_100(ik_result->q2_deg),
               branch);
        elog_i("MOTION", "[MOTION] fk check machine_x=%d machine_y=%d err_x=%d err_y=%d",
               WriterMotion_Scale_100(machine_point->x_mm + ik_result->error_x_mm),
               WriterMotion_Scale_100(machine_point->y_mm + ik_result->error_y_mm),
               WriterMotion_Scale_100(ik_result->error_x_mm),
               WriterMotion_Scale_100(ik_result->error_y_mm));
    }

    elog_i("MOTION", "[MOTION] %s feed=%d master_f=%u theta=%d psi=%d beta=%d cur_theta=%d cur_psi=%d dtheta=%d dpsi=%d dbeta=%d min_beta=%d s1_abs=%d s1=%u d1=%u f1=%u s2_log_abs=%d s2_motor_target=%d s2_bias=%d preload=%u preload_delta=%d ld1=%d md2=%d s2=%u d2=%u f2=%u",
           mode,
           WriterMotion_Scale_100(feed_mm_min),
           master_freq,
           WriterMotion_Scale_100(target_angles->theta_deg),
           WriterMotion_Scale_100(target_angles->psi_deg),
           WriterMotion_Scale_100(target_angles->beta_deg),
           WriterMotion_Scale_100(s_pose.angles.theta_deg),
           WriterMotion_Scale_100(s_pose.angles.psi_deg),
           WriterMotion_Scale_100(d_theta),
           WriterMotion_Scale_100(d_psi),
           WriterMotion_Scale_100(d_beta),
           WriterMotion_Scale_100(min_beta_abs),
           target_stage1_steps,
           stage1_steps,
           stage1_dir,
           stage1_freq,
           target_stage2_steps,
           target_stage2_motor_steps,
           next_stage2_comp_bias_steps,
           preload_stage2_steps,
           preload_stage2_delta_steps,
           next_stage1_logical_dir,
           next_stage2_motor_dir,
           stage2_steps,
           stage2_dir,
           stage2_freq);

    s_target_stage1_abs_steps = target_stage1_steps;
    s_target_stage2_abs_steps = target_stage2_steps;
    s_target_stage2_motor_abs_steps = target_stage2_motor_steps;
    s_target_stage2_comp_bias_steps = next_stage2_comp_bias_steps;
    s_target_stage1_logical_dir = next_stage1_logical_dir;
    s_target_stage2_motor_dir = next_stage2_motor_dir;
    s_main_segment_timeout_ms = move_time_ms +
                                APP_WRITER_SEGMENT_TIMEOUT_MARGIN_MS;
    if (s_main_segment_timeout_ms < APP_WRITER_SEGMENT_TIMEOUT_MARGIN_MS) {
        s_main_segment_timeout_ms = APP_WRITER_SEGMENT_TIMEOUT_MARGIN_MS;
    }

    if ((stage1_steps == 0u) && (stage2_steps == 0u) &&
        (preload_stage2_steps == 0u)) {
        WriterMotion_Commit_Target_State();
        s_segment_running = false;
        s_motion_phase = WRITER_MOTION_PHASE_IDLE;
        return true;
    }

#if APP_WRITER_DIRECTION_COMP_PRELOAD_ENABLE
    if (preload_stage2_steps != 0u) {
        if (!App_Stepper_Dual_Run(0u,
                                  0u,
                                  preload_stage2_dir,
                                  preload_stage2_steps,
                                  APP_WRITER_DIRECTION_COMP_PRELOAD_FREQ_HZ)) {
            elog_e("PRELOAD", "[PRELOAD] start rejected delta=%d steps=%u dir=%u freq=%u",
                   preload_stage2_delta_steps,
                   preload_stage2_steps,
                   preload_stage2_dir,
                   APP_WRITER_DIRECTION_COMP_PRELOAD_FREQ_HZ);
            return false;
        }

        s_preload_stage2_delta_steps = preload_stage2_delta_steps;
        s_preload_stage2_target_steps = preload_stage2_motor_steps;
        s_segment_start_ms = s_sys_tick;
        s_segment_timeout_ms =
            (uint32_t)(((uint64_t)preload_stage2_steps * 1000u) /
                       APP_WRITER_DIRECTION_COMP_PRELOAD_FREQ_HZ) +
            APP_WRITER_SEGMENT_TIMEOUT_MARGIN_MS;
        s_motion_phase = WRITER_MOTION_PHASE_PRELOAD;
        s_segment_running = true;
        s_motion_busy = true;
        elog_i("PRELOAD", "[PRELOAD] start delta=%d steps=%u dir=%u freq=%u motor=%d->%d logical=%d bias=%d->%d",
               preload_stage2_delta_steps,
               preload_stage2_steps,
               preload_stage2_dir,
               APP_WRITER_DIRECTION_COMP_PRELOAD_FREQ_HZ,
               s_stage2_motor_abs_steps,
               preload_stage2_motor_steps,
               s_stage2_abs_steps,
               s_stage2_comp_bias_steps,
               next_stage2_comp_bias_steps);
        return true;
    }
#endif

    return WriterMotion_Start_Main_Dda();
}

static bool WriterMotion_Start_Raw_Motor(uint8_t motor_index, float motor_delta_deg, uint32_t freq_hz)
{
    if (s_motion_busy || s_segment_running) {
        elog_w("MOTION", "[MOTION] raw motor rejected busy");
        return false;
    }
    if (!s_motion_ready) {
        elog_e("MOTION", "[MOTION] raw motor rejected pose not ready");
        return false;
    }

    uint32_t steps = 0u;
    uint8_t dir = (motor_delta_deg >= 0.0f) ? 1u : 0u;
    uint32_t run_freq = (freq_hz == 0u) ? APP_WRITER_MANUAL_JOG_FREQ_HZ : freq_hz;

    if (motor_index == 1u) {
        steps = WriterMotion_Motor_Deg_To_Steps(motor_delta_deg, APP_WRITER_STAGE1_MOTOR_STEPS_PER_REV);
        dir = (motor_delta_deg >= 0.0f) ? APP_WRITER_STAGE1_POSITIVE_DIR : (uint8_t)(1u - APP_WRITER_STAGE1_POSITIVE_DIR);
    } else if (motor_index == 2u) {
        steps = WriterMotion_Motor_Deg_To_Steps(motor_delta_deg, APP_WRITER_STAGE2_MOTOR_STEPS_PER_REV);
        dir = (motor_delta_deg >= 0.0f) ? APP_WRITER_STAGE2_POSITIVE_DIR : (uint8_t)(1u - APP_WRITER_STAGE2_POSITIVE_DIR);
    } else {
        elog_e("MOTION", "[MOTION] bad motor index=%u", motor_index);
        return false;
    }

    if (steps == 0u) {
        return true;
    }

    s_target_pose = s_pose;
    s_last_cmd.target_pose = s_pose;
    s_last_cmd.delta_theta_deg = 0.0f;
    s_last_cmd.delta_psi_deg = 0.0f;
    s_last_cmd.delta_beta_deg = 0.0f;
    s_last_cmd.stage1_target_steps = s_stage1_abs_steps;
    s_last_cmd.stage2_target_steps = s_stage2_abs_steps;
    s_last_cmd.stage2_motor_target_steps = s_stage2_motor_abs_steps;
    s_last_cmd.stage2_comp_bias_steps = s_stage2_comp_bias_steps;
    s_last_cmd.stage1_logical_dir = s_stage1_logical_dir;
    s_last_cmd.stage2_motor_dir = s_stage2_motor_dir;
    s_last_cmd.stage1_steps = (motor_index == 1u) ? steps : 0u;
    s_last_cmd.stage2_steps = (motor_index == 2u) ? steps : 0u;
    s_last_cmd.stage1_dir = (motor_index == 1u) ? dir : 0u;
    s_last_cmd.stage2_dir = (motor_index == 2u) ? dir : 0u;
    s_last_cmd.stage1_freq_hz = (motor_index == 1u) ? run_freq : 0u;
    s_last_cmd.stage2_freq_hz = (motor_index == 2u) ? run_freq : 0u;
    s_last_cmd.master_freq_hz = run_freq;
    s_last_cmd.requested_feed_mm_min = 0.0f;
    s_last_cmd.path_min_beta_abs_deg = WriterMotion_Beta_Abs(&s_pose.angles);
    s_last_cmd.required_beta_abs_deg = APP_WRITER_MIN_BETA_ABS_DEG;
    s_last_cmd.branch = APP_WRITER_BRANCH_DIRECT;

    elog_w("MOTION", "[MOTION] raw M%u motor_deg=%d steps=%u dir=%u freq=%u pose_not_updated=1",
           motor_index,
           WriterMotion_Scale_100(motor_delta_deg),
           steps,
           dir,
           run_freq);

    if (motor_index == 1u) {
        App_Stepper_Stage1_Run(dir, steps, run_freq);
    } else {
        App_Stepper_Stage2_Run(dir, steps, run_freq);
    }

    s_segment_start_ms = s_sys_tick;
    s_segment_timeout_ms = (uint32_t)(((uint64_t)steps * 1000u) / run_freq) + APP_WRITER_SEGMENT_TIMEOUT_MARGIN_MS;
    s_motion_phase = WRITER_MOTION_PHASE_MAIN;
    s_segment_running = true;
    s_motion_busy = true;
    return true;
}

static bool WriterMotion_Start_Next_Plan_Segment(void)
{
    while (!s_segment_running) {
        if (s_plan_index >= s_plan_count) {
            s_motion_busy = false;
            WriterMotion_Clear_Plan();
            elog_i("MOTION", "[MOTION] plan done");
            return true;
        }

        app_writer_plan_segment_t *segment = &s_plan[s_plan_index];
        const app_writer_ik_diagnostics_t *ik =
            (segment->branch == APP_WRITER_BRANCH_DIRECT) ? 0 : &segment->ik;
        s_plan_index++;

        if (!WriterMotion_Start_Target(&segment->user_point,
                                       &segment->machine_point,
                                       &segment->angles,
                                        s_plan_max_freq_hz,
                                        s_plan_min_freq_hz,
                                        s_plan_feed_mm_min,
                                        APP_WRITER_MIN_BETA_ABS_DEG,
                                       segment->branch,
                                       ik,
                                       true,
                                       "plan")) {
            s_motion_busy = false;
            s_segment_running = false;
            WriterMotion_Clear_Plan();
            return false;
        }
    }

    return true;
}

static bool WriterMotion_Last_Segment_Completed(void)
{
    bool stage1_done = (s_last_cmd.stage1_steps == 0u) ||
                       (App_Stepper_X.step_count >= s_last_cmd.stage1_steps);
    bool stage2_done = (s_last_cmd.stage2_steps == 0u) ||
                       (App_Stepper_Y.step_count >= s_last_cmd.stage2_steps);
    bool stage1_home_limit =
        (s_last_cmd.stage1_steps != 0u) &&
        (App_Stepper_X.current_dir == LIMIT_STAGE1_HOME_DIR) &&
        App_Stepper_Stage1_IsLimitHit() &&
        (WriterMotion_Abs_F32(s_target_pose.angles.theta_deg - APP_WRITER_THETA_LIMIT_DEG) <=
         APP_WRITER_HOME_LIMIT_EPSILON_DEG);
    bool stage2_home_limit =
        (s_last_cmd.stage2_steps != 0u) &&
        (App_Stepper_Y.current_dir == LIMIT_STAGE2_HOME_DIR) &&
        App_Stepper_Stage2_IsLimitHit() &&
        (WriterMotion_Abs_F32(s_target_pose.angles.psi_deg - APP_WRITER_PSI_LIMIT_DEG) <=
         APP_WRITER_HOME_LIMIT_EPSILON_DEG);

    if (!stage1_done && stage1_home_limit) {
        stage1_done = true;
        elog_w("MOTION", "[MOTION] stage1 home limit accepted theta=%d steps=%u/%u",
               WriterMotion_Scale_100(s_target_pose.angles.theta_deg),
               App_Stepper_X.step_count,
               s_last_cmd.stage1_steps);
    }
    if (!stage2_done && stage2_home_limit) {
        stage2_done = true;
        elog_w("MOTION", "[MOTION] stage2 home limit accepted psi=%d steps=%u/%u",
               WriterMotion_Scale_100(s_target_pose.angles.psi_deg),
               App_Stepper_Y.step_count,
               s_last_cmd.stage2_steps);
    }

    if (!stage1_done || !stage2_done) {
        elog_e("MOTION", "[MOTION] segment incomplete s1=%u/%u s2=%u/%u lim1=%d lim2=%d",
               App_Stepper_X.step_count,
               s_last_cmd.stage1_steps,
               App_Stepper_Y.step_count,
               s_last_cmd.stage2_steps,
               App_Stepper_Stage1_IsLimitHit(),
               App_Stepper_Stage2_IsLimitHit());
        return false;
    }

    return true;
}

static void WriterMotion_Log_Ik_Test_Case(const char *name, float theta_deg, float psi_deg)
{
    mid_scara_angles_t angles = {
        .theta_deg = theta_deg,
        .psi_deg = psi_deg,
    };
    WriterMotion_Update_Beta(&angles);

    mid_scara_point_t machine_point;
    mid_scara_ik_result_t ik;
    if (!mid_scara_forward_absolute(&s_scara_cfg, &angles, &machine_point)) {
        elog_e("IKTEST", "[IKTEST] %s forward failed", name);
        return;
    }
    if (!mid_scara_inverse_absolute_ex(&s_scara_cfg, &machine_point, MID_SCARA_ELBOW_POSITIVE, &ik)) {
        elog_e("IKTEST", "[IKTEST] %s inverse failed machine_x=%d machine_y=%d",
               name,
               WriterMotion_Scale_100(machine_point.x_mm),
               WriterMotion_Scale_100(machine_point.y_mm));
        return;
    }

    elog_i("IKTEST", "[IKTEST] %s theta=%d psi=%d beta=%d machine_x=%d machine_y=%d theta2=%d psi2=%d beta2=%d err_x=%d err_y=%d",
           name,
           WriterMotion_Scale_100(theta_deg),
           WriterMotion_Scale_100(psi_deg),
           WriterMotion_Scale_100(angles.beta_deg),
           WriterMotion_Scale_100(machine_point.x_mm),
           WriterMotion_Scale_100(machine_point.y_mm),
           WriterMotion_Scale_100(ik.angles.theta_deg),
           WriterMotion_Scale_100(ik.angles.psi_deg),
           WriterMotion_Scale_100(ik.angles.beta_deg),
           WriterMotion_Scale_100(ik.error_x_mm),
           WriterMotion_Scale_100(ik.error_y_mm));
}

static void WriterMotion_Log_User_Ik_Test_Case(const char *name,
                                                float user_x_mm,
                                                float user_y_mm)
{
    mid_scara_point_t user_point = {
        .x_mm = user_x_mm,
        .y_mm = user_y_mm,
    };
    mid_scara_point_t machine_point;
    mid_scara_ik_result_t ik;

    WriterMotion_User_To_Machine(&user_point, &machine_point);
    if (!mid_scara_inverse_absolute_ex(&s_scara_cfg,
                                       &machine_point,
                                       MID_SCARA_ELBOW_POSITIVE,
                                       &ik)) {
        elog_e("IKTEST", "[IKTEST] USER %s rejected x=%d y=%d",
               name,
               WriterMotion_Scale_100(user_x_mm),
               WriterMotion_Scale_100(user_y_mm));
        return;
    }

    elog_i("IKTEST", "[IKTEST] USER %s x=%d y=%d machine_x=%d machine_y=%d theta=%d psi=%d beta=%d s1_abs=%d s2_abs=%d err_x=%d err_y=%d",
           name,
           WriterMotion_Scale_100(user_x_mm),
           WriterMotion_Scale_100(user_y_mm),
           WriterMotion_Scale_100(machine_point.x_mm),
           WriterMotion_Scale_100(machine_point.y_mm),
           WriterMotion_Scale_100(ik.angles.theta_deg),
           WriterMotion_Scale_100(ik.angles.psi_deg),
           WriterMotion_Scale_100(ik.angles.beta_deg),
           WriterMotion_Angle_To_Absolute_Steps(ik.angles.theta_deg,
                                                APP_WRITER_STAGE1_STEPS_PER_DEG),
           WriterMotion_Angle_To_Absolute_Steps(ik.angles.psi_deg,
                                                APP_WRITER_STAGE2_STEPS_PER_DEG),
           WriterMotion_Scale_100(ik.error_x_mm),
           WriterMotion_Scale_100(ik.error_y_mm));
}

static void WriterMotion_Run_Kinematics_Self_Test(void)
{
#if APP_WRITER_KINEMATICS_SELF_TEST_ENABLE
    if (s_kinematics_self_test_done) {
        return;
    }
    s_kinematics_self_test_done = true;

    elog_i("IKTEST", "[IKTEST] DRAWBOT_AUTHOR_BASELINE_V1 baseline=%u native_frame=%u L1=%d L2=%d offset_x=%d offset_y=%d home_theta=%d home_psi=%d spd1=%d spd2=%d dir_comp=%u cal_xx=%d cal_xy=%d cal_yx=%d cal_yy=%d",
           APP_WRITER_AUTHOR_BASELINE_ENABLE,
           APP_WRITER_AUTHOR_CORE_ENABLE,
           WriterMotion_Scale_100(APP_WRITER_L1_MM),
           WriterMotion_Scale_100(APP_WRITER_L2_MM),
           WriterMotion_Scale_100(APP_WRITER_MACHINE_OFFSET_X_MM),
           WriterMotion_Scale_100(APP_WRITER_MACHINE_OFFSET_Y_MM),
           WriterMotion_Scale_100(s_home_theta_deg),
           WriterMotion_Scale_100(s_home_psi_deg),
           WriterMotion_Scale_100(APP_WRITER_STAGE1_STEPS_PER_DEG),
           WriterMotion_Scale_100(APP_WRITER_STAGE2_STEPS_PER_DEG),
           APP_WRITER_DIRECTION_COMP_ENABLE,
           WriterMotion_Scale_100(APP_WRITER_XY_CAL_XX),
           WriterMotion_Scale_100(APP_WRITER_XY_CAL_XY),
           WriterMotion_Scale_100(APP_WRITER_XY_CAL_YX),
           WriterMotion_Scale_100(APP_WRITER_XY_CAL_YY));

    WriterMotion_Log_Ik_Test_Case("HOME", s_home_theta_deg, s_home_psi_deg);
    WriterMotion_Log_Ik_Test_Case("CAL_0_135", APP_WRITER_CAL_THETA_DEG, APP_WRITER_CAL_PSI_DEG);
    WriterMotion_Log_User_Ik_Test_Case("ORIGIN", 0.0f, 0.0f);
    WriterMotion_Log_User_Ik_Test_Case("R10_D0", 10.0f, 0.0f);
    WriterMotion_Log_User_Ik_Test_Case("R10_D10", 10.0f, -10.0f);
    WriterMotion_Log_User_Ik_Test_Case("R0_D10", 0.0f, -10.0f);
#endif
}

void WriterMotion_Init_From_Home(void)
{
    App_Stepper_Dual_Queue_Clear();
    s_motion_busy = false;
    s_segment_running = false;
    s_motion_phase = WRITER_MOTION_PHASE_IDLE;
    s_continuous_mode = false;
    s_motion_ready = false;
    s_segment_start_ms = 0u;
    s_segment_timeout_ms = 0u;
    s_main_segment_timeout_ms = 0u;
    s_preload_stage2_delta_steps = 0;
    s_preload_stage2_target_steps = 0;
    s_plan_max_freq_hz = APP_WRITER_MOVE_MAX_FREQ_HZ;
    s_plan_min_freq_hz = APP_WRITER_MOVE_MIN_FREQ_HZ;
    s_plan_feed_mm_min = 0.0f;
    WriterMotion_Clear_Plan();

    s_pose.angles.theta_deg = s_home_theta_deg;
    s_pose.angles.psi_deg = s_home_psi_deg;
    WriterMotion_Update_Beta(&s_pose.angles);

    if (!mid_scara_forward_absolute(&s_scara_cfg, &s_pose.angles, &s_pose.machine_point)) {
        elog_e("MOTION", "[MOTION] home pose invalid");
        return;
    }

    WriterMotion_Machine_To_User(&s_pose.machine_point, &s_pose.user_point);

    if (!WriterMotion_Is_Angle_Safe(&s_pose.angles)) {
        elog_e("MOTION", "[MOTION] home angle unsafe theta=%d psi=%d beta=%d",
               WriterMotion_Scale_100(s_pose.angles.theta_deg),
               WriterMotion_Scale_100(s_pose.angles.psi_deg),
               WriterMotion_Scale_100(s_pose.angles.beta_deg));
        return;
    }

    s_stage1_abs_steps = WriterMotion_Angle_To_Absolute_Steps(
        s_pose.angles.theta_deg, APP_WRITER_STAGE1_STEPS_PER_DEG);
    s_stage2_abs_steps = WriterMotion_Angle_To_Absolute_Steps(
        s_pose.angles.psi_deg, APP_WRITER_STAGE2_STEPS_PER_DEG);
    s_stage2_motor_abs_steps = s_stage2_abs_steps;
    s_stage2_comp_bias_steps = 0;
    /* The final DIR=0 pull-off increases both logical joint angles. */
    s_stage1_logical_dir = 1;
    s_stage2_motor_dir = 1;
    s_target_stage1_abs_steps = s_stage1_abs_steps;
    s_target_stage2_abs_steps = s_stage2_abs_steps;
    s_target_stage2_motor_abs_steps = s_stage2_motor_abs_steps;
    s_target_stage2_comp_bias_steps = 0;
    s_target_stage1_logical_dir = 1;
    s_target_stage2_motor_dir = 1;
    s_planned_pose = s_pose;
    s_planned_stage1_abs_steps = s_stage1_abs_steps;
    s_planned_stage2_abs_steps = s_stage2_abs_steps;
    s_planned_stage1_logical_dir = 1;
    s_planned_stage2_logical_dir = 1;
    App_Stepper_Dual_Queue_Set_Position(
        s_stage1_abs_steps, s_stage2_abs_steps);

    s_target_pose = s_pose;
    s_last_cmd.target_pose = s_pose;
    s_last_cmd.delta_theta_deg = 0.0f;
    s_last_cmd.delta_psi_deg = 0.0f;
    s_last_cmd.delta_beta_deg = 0.0f;
    s_last_cmd.stage1_target_steps = s_stage1_abs_steps;
    s_last_cmd.stage2_target_steps = s_stage2_abs_steps;
    s_last_cmd.stage2_motor_target_steps = s_stage2_motor_abs_steps;
    s_last_cmd.stage2_comp_bias_steps = 0;
    s_last_cmd.stage1_logical_dir = 1;
    s_last_cmd.stage2_motor_dir = 1;
    s_last_cmd.stage1_steps = 0u;
    s_last_cmd.stage2_steps = 0u;
    s_last_cmd.stage1_dir = APP_WRITER_STAGE1_POSITIVE_DIR;
    s_last_cmd.stage2_dir = APP_WRITER_STAGE2_POSITIVE_DIR;
    s_last_cmd.stage1_freq_hz = 0u;
    s_last_cmd.stage2_freq_hz = 0u;
    s_last_cmd.master_freq_hz = 0u;
    s_last_cmd.requested_feed_mm_min = 0.0f;
    s_last_cmd.path_min_beta_abs_deg = WriterMotion_Beta_Abs(&s_pose.angles);
    s_last_cmd.required_beta_abs_deg = APP_WRITER_MIN_BETA_ABS_DEG;
    s_last_cmd.branch = APP_WRITER_BRANCH_DIRECT;
    s_last_cmd.ik_radius_mm = 0.0f;
    s_last_cmd.ik_cos_q2 = 0.0f;
    s_last_cmd.ik_sin_q2 = 0.0f;
    s_last_cmd.ik_q2_deg = 0.0f;
    s_last_cmd.ik_error_x_mm = 0.0f;
    s_last_cmd.ik_error_y_mm = 0.0f;
    s_motion_ready = true;

    elog_i("MOTION", "[MOTION] author home user_x=%d user_y=%d machine_x=%d machine_y=%d theta=%d psi=%d beta=%d s1_abs=%d s2_abs=%d",
           WriterMotion_Scale_100(s_pose.user_point.x_mm),
           WriterMotion_Scale_100(s_pose.user_point.y_mm),
           WriterMotion_Scale_100(s_pose.machine_point.x_mm),
           WriterMotion_Scale_100(s_pose.machine_point.y_mm),
           WriterMotion_Scale_100(s_pose.angles.theta_deg),
           WriterMotion_Scale_100(s_pose.angles.psi_deg),
           WriterMotion_Scale_100(s_pose.angles.beta_deg),
           s_stage1_abs_steps,
           s_stage2_abs_steps);
    elog_i("MOTION", "[MOTION] author pulse_per_deg s1=%d s2=%d dir_sign1=%d dir_sign2=%d",
           WriterMotion_Scale_100(APP_WRITER_STAGE1_STEPS_PER_DEG),
           WriterMotion_Scale_100(APP_WRITER_STAGE2_STEPS_PER_DEG),
           APP_WRITER_STAGE1_DIR_SIGN,
           APP_WRITER_STAGE2_DIR_SIGN);
    elog_i("MOTION", "[MOTION] DIRCOMP_STAGE2_PRELOAD_V2 enable=%u theta_rev=%d psi_rev=%d max_bias=%d preload=%u preload_f=%u",
           APP_WRITER_DIRECTION_COMP_ENABLE,
           APP_WRITER_DIR_COMP_THETA_REV_PSI_STEPS,
           APP_WRITER_DIR_COMP_PSI_REV_PSI_STEPS,
           APP_WRITER_DIRECTION_COMP_MAX_BIAS_STEPS,
           APP_WRITER_DIRECTION_COMP_PRELOAD_ENABLE,
           APP_WRITER_DIRECTION_COMP_PRELOAD_FREQ_HZ);

    if (!WriterMotion_Dir_Sign_Configured()) {
        elog_w("MOTION", "[MOTION] DIR signs are not calibrated; use raw M1/M2 motor jogs before XY or joint moves");
    }

    WriterMotion_Run_Kinematics_Self_Test();
}

bool WriterMotion_Set_Home_Angles(float theta_deg, float psi_deg)
{
    if ((theta_deg < APP_WRITER_THETA_LIMIT_DEG) ||
        (theta_deg > APP_WRITER_THETA_MAX_DEG) ||
        (psi_deg < APP_WRITER_PSI_LIMIT_DEG) ||
        (psi_deg > APP_WRITER_PSI_MAX_DEG) ||
        (psi_deg <= theta_deg)) {
        return false;
    }

    s_home_theta_deg = theta_deg;
    s_home_psi_deg = psi_deg;
    return true;
}

void WriterMotion_Get_Home_Angles(float *theta_deg, float *psi_deg)
{
    if (theta_deg != 0) {
        *theta_deg = s_home_theta_deg;
    }
    if (psi_deg != 0) {
        *psi_deg = s_home_psi_deg;
    }
}

static bool WriterMotion_Start_To_Profile(float user_x_mm, float user_y_mm,
                                          float feed_mm_min,
                                          uint32_t min_freq_hz,
                                          uint32_t max_freq_hz)
{
    mid_scara_point_t target_user_point = {
        .x_mm = user_x_mm,
        .y_mm = user_y_mm,
    };
    mid_scara_point_t target_machine_point;

    if (s_motion_busy) {
        elog_w("MOTION", "[MOTION] plan rejected busy");
        return false;
    }

    if (!s_motion_ready) {
        elog_e("MOTION", "[MOTION] plan rejected pose not ready");
        return false;
    }

    if ((min_freq_hz == 0u) || (max_freq_hz < min_freq_hz) ||
        (feed_mm_min < 0.0f)) {
        elog_e("MOTION", "[MOTION] invalid profile feed=%d min_f=%u max_f=%u",
               WriterMotion_Scale_100(feed_mm_min),
               min_freq_hz,
               max_freq_hz);
        return false;
    }

    s_plan_feed_mm_min = feed_mm_min;
    s_plan_min_freq_hz = min_freq_hz;
    s_plan_max_freq_hz = max_freq_hz;

    WriterMotion_User_To_Machine(&target_user_point, &target_machine_point);
    elog_i("MOTION", "[MOTION] target user_x=%d user_y=%d machine_x=%d machine_y=%d",
           WriterMotion_Scale_100(user_x_mm),
           WriterMotion_Scale_100(user_y_mm),
           WriterMotion_Scale_100(target_machine_point.x_mm),
           WriterMotion_Scale_100(target_machine_point.y_mm));

#if APP_WRITER_AUTHOR_LINE_EXECUTION_ENABLE
    /*
     * DrawBot author path (scara.c + planner.c): solve only the G-code line
     * endpoint, convert absolute theta/psi directly to steps, then execute one
     * synchronized Bresenham block. The MSPM0 limit and path checks remain in
     * WriterMotion_Start_Target().
     */
    mid_scara_angles_t target_angles;
    mid_scara_ik_result_t ik;
    app_writer_ik_diagnostics_t ik_diagnostics;

    WriterMotion_Clear_Plan();
    if (!WriterMotion_Select_Inverse(&target_machine_point,
                                     &target_angles,
                                     &ik)) {
        elog_e("MOTION", "[MOTION] author inverse rejected user_x=%d user_y=%d machine_x=%d machine_y=%d",
               WriterMotion_Scale_100(user_x_mm),
               WriterMotion_Scale_100(user_y_mm),
               WriterMotion_Scale_100(target_machine_point.x_mm),
               WriterMotion_Scale_100(target_machine_point.y_mm));
        return false;
    }

    elog_i("MOTION", "[MOTION] author block accepted endpoints=1 theta=%d psi=%d",
           WriterMotion_Scale_100(target_angles.theta_deg),
           WriterMotion_Scale_100(target_angles.psi_deg));
    WriterMotion_Copy_Ik_Diagnostics(&ik_diagnostics, &ik);
    if (!WriterMotion_Start_Target(&target_user_point,
                                   &target_machine_point,
                                   &target_angles,
                                   max_freq_hz,
                                   min_freq_hz,
                                   feed_mm_min,
                                   APP_WRITER_MIN_BETA_ABS_DEG,
                                   APP_WRITER_BRANCH_IK_ELBOW_POSITIVE,
                                   &ik_diagnostics,
                                   false,
                                   "author_block")) {
        return false;
    }

    /* A rounded target can legitimately require zero new motor steps. */
    if (!s_segment_running) {
        s_motion_busy = false;
    }
    return true;
#else
    if (!WriterMotion_Plan_Direct_To(&target_user_point)) {
        elog_w("MOTION", "[MOTION] direct path unsafe, try waypoint");
        if (!WriterMotion_Plan_Via_Safe_Waypoint(&target_user_point)) {
            WriterMotion_Clear_Plan();
            elog_e("MOTION", "[MOTION] motion rejected user_x=%d user_y=%d",
                   WriterMotion_Scale_100(user_x_mm),
                   WriterMotion_Scale_100(user_y_mm));
            return false;
        }
    }

    elog_i("MOTION", "[MOTION] plan accepted segments=%u", s_plan_count);
    s_motion_busy = true;
    s_segment_running = false;
    s_plan_index = 0u;
    return WriterMotion_Start_Next_Plan_Segment();
#endif
}

bool WriterMotion_Start_To(float user_x_mm, float user_y_mm)
{
    return WriterMotion_Start_To_Profile(user_x_mm,
                                         user_y_mm,
                                         0.0f,
                                         APP_WRITER_RAPID_MIN_FREQ_HZ,
                                         APP_WRITER_RAPID_MAX_FREQ_HZ);
}

bool WriterMotion_Start_To_At_Feed(float user_x_mm, float user_y_mm,
                                   float feed_mm_min)
{
    return WriterMotion_Start_To_Profile(user_x_mm,
                                         user_y_mm,
                                         feed_mm_min,
                                         APP_WRITER_DRAW_MIN_FREQ_HZ,
                                         APP_WRITER_DRAW_MAX_FREQ_HZ);
}

bool WriterMotion_Start_To_At_Feed_Limited(
    float user_x_mm, float user_y_mm, float feed_mm_min,
    uint32_t min_freq_hz, uint32_t max_freq_hz)
{
    return WriterMotion_Start_To_Profile(user_x_mm,
                                         user_y_mm,
                                         feed_mm_min,
                                         min_freq_hz,
                                         max_freq_hz);
}

app_writer_queue_result_t WriterMotion_Queue_To(
    float user_x_mm, float user_y_mm)
{
    return WriterMotion_Queue_To_Profile(
        user_x_mm, user_y_mm, 0.0f,
        APP_WRITER_RAPID_MIN_FREQ_HZ,
        APP_WRITER_RAPID_MAX_FREQ_HZ);
}

app_writer_queue_result_t WriterMotion_Queue_To_At_Feed(
    float user_x_mm, float user_y_mm, float feed_mm_min)
{
    return WriterMotion_Queue_To_Profile(
        user_x_mm, user_y_mm, feed_mm_min,
        APP_WRITER_DRAW_MIN_FREQ_HZ,
        APP_WRITER_DRAW_MAX_FREQ_HZ);
}

uint32_t WriterMotion_Queue_Free(void)
{
    return App_Stepper_Dual_Queue_Free();
}

bool WriterMotion_Queue_Is_Idle(void)
{
    return !App_Stepper_Dual_Queue_IsBusy();
}

const app_writer_pose_t *WriterMotion_Get_Planned_Pose(void)
{
    return &s_planned_pose;
}

static bool WriterMotion_Start_Joints_With_Freq(float theta_deg,
                                                float psi_deg,
                                                uint32_t max_freq_hz,
                                                uint32_t min_freq_hz)
{
    mid_scara_angles_t target_angles = {
        .theta_deg = theta_deg,
        .psi_deg = psi_deg,
    };
    mid_scara_point_t target_machine_point;
    mid_scara_point_t target_user_point;

    WriterMotion_Update_Beta(&target_angles);
    if (!mid_scara_forward_absolute(&s_scara_cfg, &target_angles, &target_machine_point)) {
        elog_e("MOTION", "[MOTION] forward failed theta=%d psi=%d",
               WriterMotion_Scale_100(theta_deg),
               WriterMotion_Scale_100(psi_deg));
        return false;
    }
    WriterMotion_Machine_To_User(&target_machine_point, &target_user_point);

    return WriterMotion_Start_Target(&target_user_point,
                                     &target_machine_point,
                                     &target_angles,
                                     max_freq_hz,
                                     min_freq_hz,
                                     0.0f,
                                     APP_WRITER_MIN_BETA_ABS_DEG,
                                     APP_WRITER_BRANCH_DIRECT,
                                     0,
                                     false,
                                     "joint");
}

bool WriterMotion_Start_Joints(float theta_deg, float psi_deg)
{
    return WriterMotion_Start_Joints_With_Freq(theta_deg,
                                               psi_deg,
                                               APP_WRITER_ANGLE_TEST_MAX_FREQ_HZ,
                                               APP_WRITER_ANGLE_TEST_MIN_FREQ_HZ);
}

bool WriterMotion_Start_Relative_Joints(float delta_theta_deg, float delta_psi_deg)
{
    const app_writer_pose_t *pose = WriterMotion_Get_Pose();

    return WriterMotion_Start_Joints_With_Freq(pose->angles.theta_deg + delta_theta_deg,
                                               pose->angles.psi_deg + delta_psi_deg,
                                               APP_WRITER_MANUAL_JOG_FREQ_HZ,
                                               APP_WRITER_ANGLE_TEST_MIN_FREQ_HZ);
}

bool WriterMotion_Start_Stage1_Relative(float delta_theta_deg)
{
    return WriterMotion_Start_Relative_Joints(delta_theta_deg, 0.0f);
}

bool WriterMotion_Start_Stage2_Relative(float delta_psi_deg)
{
    return WriterMotion_Start_Relative_Joints(0.0f, delta_psi_deg);
}

bool WriterMotion_Start_Motor_Deg(uint8_t motor_index, float motor_delta_deg, uint32_t freq_hz)
{
    if (!WriterMotion_Dir_Sign_Configured()) {
        return WriterMotion_Start_Raw_Motor(motor_index, motor_delta_deg, freq_hz);
    }

    float joint_delta_deg;
    uint32_t max_freq_hz = (freq_hz == 0u) ? APP_WRITER_MANUAL_JOG_FREQ_HZ : freq_hz;

    if (motor_index == 1u) {
        joint_delta_deg = (motor_delta_deg / APP_WRITER_STAGE1_REDUCTION_RATIO) *
                          (float)APP_WRITER_STAGE1_DIR_SIGN;
        const app_writer_pose_t *pose = WriterMotion_Get_Pose();
        return WriterMotion_Start_Joints_With_Freq(pose->angles.theta_deg + joint_delta_deg,
                                                   pose->angles.psi_deg,
                                                   max_freq_hz,
                                                   APP_WRITER_ANGLE_TEST_MIN_FREQ_HZ);
    }

    if (motor_index == 2u) {
        joint_delta_deg = (motor_delta_deg / APP_WRITER_STAGE2_REDUCTION_RATIO) *
                          (float)APP_WRITER_STAGE2_DIR_SIGN;
        const app_writer_pose_t *pose = WriterMotion_Get_Pose();
        return WriterMotion_Start_Joints_With_Freq(pose->angles.theta_deg,
                                                   pose->angles.psi_deg + joint_delta_deg,
                                                   max_freq_hz,
                                                   APP_WRITER_ANGLE_TEST_MIN_FREQ_HZ);
    }

    elog_e("MOTION", "[MOTION] bad motor index=%u", motor_index);
    return false;
}

uint32_t WriterMotion_Stage1_Arm_Deg_To_Steps(float arm_delta_deg)
{
    return (uint32_t)lroundf(fabsf(arm_delta_deg) * APP_WRITER_STAGE1_STEPS_PER_DEG);
}

uint32_t WriterMotion_Stage2_Arm_Deg_To_Steps(float arm_delta_deg)
{
    return (uint32_t)lroundf(fabsf(arm_delta_deg) * APP_WRITER_STAGE2_STEPS_PER_DEG);
}

uint32_t WriterMotion_Motor_Deg_To_Steps(float motor_delta_deg, float motor_steps_per_rev)
{
    float steps = fabsf(motor_delta_deg) * motor_steps_per_rev / 360.0f;

    if (steps <= 0.0f) {
        return 0u;
    }
    return (uint32_t)(steps + 0.5f);
}

void WriterMotion_Emergency_Stop(void)
{
    App_Stepper_Dual_Stop();
    App_Stepper_Stage1_Stop();
    App_Stepper_Stage2_Stop();
    s_motion_busy = false;
    s_segment_running = false;
    s_motion_phase = WRITER_MOTION_PHASE_IDLE;
    s_continuous_mode = false;
    s_motion_ready = false;
    s_preload_stage2_delta_steps = 0;
    s_preload_stage2_target_steps = 0;
    s_segment_timeout_ms = 0u;
    WriterMotion_Clear_Plan();

    elog_e("MOTION", "[MOTION] emergency stop position_valid=0 rehome_required=1");
}

void WriterMotion_Task(void)
{
    App_Stepper_Task();

    if (s_continuous_mode) {
        WriterMotion_Update_Continuous_Pose();
        s_motion_busy = App_Stepper_Dual_Queue_IsBusy();
        if (!s_motion_busy) {
            s_continuous_mode = false;
            s_segment_running = false;
            s_motion_phase = WRITER_MOTION_PHASE_IDLE;
            s_stage1_logical_dir =
                s_planned_stage1_logical_dir;
            s_stage2_motor_dir =
                s_planned_stage2_logical_dir;
            s_planned_pose = s_pose;
            s_planned_stage1_abs_steps =
                s_stage1_abs_steps;
            s_planned_stage2_abs_steps =
                s_stage2_abs_steps;
            s_target_pose = s_pose;
            s_target_stage1_abs_steps =
                s_stage1_abs_steps;
            s_target_stage2_abs_steps =
                s_stage2_abs_steps;
            s_target_stage2_motor_abs_steps =
                s_stage2_abs_steps;
        }
        return;
    }

    if (s_segment_running &&
        (s_segment_timeout_ms != 0u) &&
        ((uint32_t)(s_sys_tick - s_segment_start_ms) > s_segment_timeout_ms)) {
        writer_motion_phase_t timed_out_phase = s_motion_phase;
        uint32_t expected_stage1 =
            (s_motion_phase == WRITER_MOTION_PHASE_PRELOAD) ?
            0u : s_last_cmd.stage1_steps;
        uint32_t expected_stage2 =
            (s_motion_phase == WRITER_MOTION_PHASE_PRELOAD) ?
            WriterMotion_Abs_I32(s_preload_stage2_delta_steps) :
            s_last_cmd.stage2_steps;

        App_Stepper_Stage1_Stop();
        App_Stepper_Stage2_Stop();
        s_motion_busy = false;
        s_segment_running = false;
        s_motion_phase = WRITER_MOTION_PHASE_IDLE;
        s_motion_ready = false;
        s_preload_stage2_delta_steps = 0;
        s_preload_stage2_target_steps = 0;
        WriterMotion_Clear_Plan();
        elog_e("MOTION", "[MOTION] segment timeout phase=%u s1=%u/%u s2=%u/%u timeout_ms=%u",
               (uint32_t)timed_out_phase,
               App_Stepper_X.step_count,
               expected_stage1,
               App_Stepper_Y.step_count,
               expected_stage2,
               s_segment_timeout_ms);
        return;
    }

    if (s_segment_running &&
        !BSP_Stepper_IsRunning(&App_Stepper_X) &&
        !BSP_Stepper_IsRunning(&App_Stepper_Y)) {
        if (s_motion_phase == WRITER_MOTION_PHASE_PRELOAD) {
            uint32_t expected_preload_steps =
                WriterMotion_Abs_I32(s_preload_stage2_delta_steps);

            if ((App_Stepper_X.step_count != 0u) ||
                (App_Stepper_Y.step_count < expected_preload_steps)) {
                s_motion_busy = false;
                s_segment_running = false;
                s_motion_phase = WRITER_MOTION_PHASE_IDLE;
                s_motion_ready = false;
                WriterMotion_Clear_Plan();
                elog_e("PRELOAD", "[PRELOAD] incomplete s1=%u/0 s2=%u/%u lim1=%d lim2=%d",
                       App_Stepper_X.step_count,
                       App_Stepper_Y.step_count,
                       expected_preload_steps,
                       App_Stepper_Stage1_IsLimitHit(),
                       App_Stepper_Stage2_IsLimitHit());
                s_preload_stage2_delta_steps = 0;
                s_preload_stage2_target_steps = 0;
                return;
            }

            elog_i("PRELOAD", "[PRELOAD] done delta=%d steps=%u motor=%d->%d bias=%d->%d main_s1=%u main_s2=%u",
                   s_preload_stage2_delta_steps,
                   expected_preload_steps,
                   s_stage2_motor_abs_steps,
                   s_preload_stage2_target_steps,
                   s_stage2_comp_bias_steps,
                   s_target_stage2_comp_bias_steps,
                   s_last_cmd.stage1_steps,
                   s_last_cmd.stage2_steps);

            s_stage2_motor_abs_steps = s_preload_stage2_target_steps;
            s_stage2_comp_bias_steps = s_target_stage2_comp_bias_steps;
            s_stage2_motor_dir = s_target_stage2_motor_dir;
            s_preload_stage2_delta_steps = 0;
            s_preload_stage2_target_steps = 0;
            s_segment_running = false;
            s_motion_phase = WRITER_MOTION_PHASE_IDLE;

            if ((s_last_cmd.stage1_steps == 0u) &&
                (s_last_cmd.stage2_steps == 0u)) {
                WriterMotion_Commit_Target_State();
                if (s_plan_count != 0u) {
                    (void)WriterMotion_Start_Next_Plan_Segment();
                } else {
                    s_motion_busy = false;
                }
                return;
            }

            if (!WriterMotion_Start_Main_Dda()) {
                s_motion_busy = false;
                s_segment_running = false;
                s_motion_phase = WRITER_MOTION_PHASE_IDLE;
                s_motion_ready = false;
                WriterMotion_Clear_Plan();
                elog_e("PRELOAD", "[PRELOAD] main DDA start failed; motion locked");
            }
            return;
        }

        if (s_motion_phase != WRITER_MOTION_PHASE_MAIN) {
            writer_motion_phase_t invalid_phase = s_motion_phase;
            s_motion_busy = false;
            s_segment_running = false;
            s_motion_phase = WRITER_MOTION_PHASE_IDLE;
            s_motion_ready = false;
            WriterMotion_Clear_Plan();
            elog_e("MOTION", "[MOTION] stopped in invalid phase=%u",
                   (uint32_t)invalid_phase);
            return;
        }

        if (!WriterMotion_Last_Segment_Completed()) {
            s_motion_busy = false;
            s_segment_running = false;
            s_motion_phase = WRITER_MOTION_PHASE_IDLE;
            s_motion_ready = false;
            WriterMotion_Clear_Plan();
            elog_e("MOTION", "[MOTION] plan aborted by incomplete segment");
            return;
        }

        WriterMotion_Commit_Target_State();
        s_segment_running = false;
        s_motion_phase = WRITER_MOTION_PHASE_IDLE;
        elog_i("MOTION", "[MOTION] segment done user_x=%d user_y=%d machine_x=%d machine_y=%d theta=%d psi=%d beta=%d s1_abs=%d s2_log_abs=%d s2_motor_abs=%d s2_bias=%d ld1=%d md2=%d plan=%u/%u",
               WriterMotion_Scale_100(s_pose.user_point.x_mm),
               WriterMotion_Scale_100(s_pose.user_point.y_mm),
               WriterMotion_Scale_100(s_pose.machine_point.x_mm),
               WriterMotion_Scale_100(s_pose.machine_point.y_mm),
               WriterMotion_Scale_100(s_pose.angles.theta_deg),
               WriterMotion_Scale_100(s_pose.angles.psi_deg),
               WriterMotion_Scale_100(s_pose.angles.beta_deg),
               s_stage1_abs_steps,
               s_stage2_abs_steps,
               s_stage2_motor_abs_steps,
               s_stage2_comp_bias_steps,
               s_stage1_logical_dir,
               s_stage2_motor_dir,
               s_plan_index,
               s_plan_count);

        if (s_plan_count != 0u) {
            (void)WriterMotion_Start_Next_Plan_Segment();
        } else {
            s_motion_busy = false;
        }
    }
}

bool WriterMotion_Is_Busy(void)
{
    return s_motion_busy;
}

const app_writer_pose_t *WriterMotion_Get_Pose(void)
{
    return &s_pose;
}

const app_writer_motion_cmd_t *WriterMotion_Get_Last_Cmd(void)
{
    return &s_last_cmd;
}
