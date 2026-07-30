/**
 * @file    app_writer_motion.h
 * @brief   Writer robot motion wrapper over dual stepper axes.
 */
#ifndef APP_WRITER_MOTION_H
#define APP_WRITER_MOTION_H

#include <stdbool.h>
#include <stdint.h>
#include "mid_scara.h"

#define APP_WRITER_L1_MM                    (205.0f)
#define APP_WRITER_L2_MM                    (203.0f)

/*
 * DrawBot machine frame. Keep the author's fixed SCARA tower offset separate
 * from any paper/work-coordinate origin. The host sends M370 for "set origin",
 * but that command is absent from the available author firmware source.
 * V15 measured 31/33 pulses from the author's manually established 0/135
 * calibration pose to the fixed switches. V24's repeated 263 mm Stage1
 * long-chord result updates theta to 40.099216 steps/degree. V26/V27 Stage2
 * chord measurements update psi to 40.115790 steps/degree. Both dependent
 * switch angles are recomputed from their original pulse counts.
 */
#define APP_WRITER_AUTHOR_BASELINE_ENABLE    (1u)

#if APP_WRITER_AUTHOR_BASELINE_ENABLE
#define APP_WRITER_MACHINE_OFFSET_X_MM      (-129.0f)
#define APP_WRITER_MACHINE_OFFSET_Y_MM      (128.0f)
#define APP_WRITER_AUTHOR_CORE_ENABLE        (1u)
/* V27 uses the Cartesian planner for the pen-up approach to its start mark. */
#define APP_WRITER_AUTHOR_LINE_EXECUTION_ENABLE (0u)
#define APP_WRITER_THETA_LIMIT_DEG          (-0.773082f)
#define APP_WRITER_PSI_LIMIT_DEG            (134.177381f)
#define APP_WRITER_STAGE1_STEPS_PER_DEG     (40.099216f)
#define APP_WRITER_STAGE2_STEPS_PER_DEG     (40.115790f)
#define APP_WRITER_DIRECTION_COMP_ENABLE     (0u)
#else
#define APP_WRITER_MACHINE_OFFSET_X_MM      (-126.174610f)
#define APP_WRITER_MACHINE_OFFSET_Y_MM      (186.754553f)
#define APP_WRITER_AUTHOR_CORE_ENABLE        (1u)
#define APP_WRITER_AUTHOR_LINE_EXECUTION_ENABLE (0u)
#define APP_WRITER_THETA_LIMIT_DEG          (-17.887811f)
#define APP_WRITER_PSI_LIMIT_DEG            (107.286506f)
#define APP_WRITER_STAGE1_STEPS_PER_DEG     (43.708318f)
#define APP_WRITER_STAGE2_STEPS_PER_DEG     (50.917449f)
#define APP_WRITER_DIRECTION_COMP_ENABLE     (0u)
#endif

/* Local paper-coordinate calibration fitted from the measured A/B/C/D/A1 points. */
#define APP_WRITER_XY_CAL_XX                 (0.816962f)
#define APP_WRITER_XY_CAL_XY                 (-0.397980f)
#define APP_WRITER_XY_CAL_YX                 (-0.057668f)
#define APP_WRITER_XY_CAL_YY                 (0.790620f)

#define APP_WRITER_HOMING_PULLOFF_DEG       (1.0f)
#define APP_WRITER_THETA_HOME_DEG           (APP_WRITER_THETA_LIMIT_DEG + APP_WRITER_HOMING_PULLOFF_DEG)
#define APP_WRITER_PSI_HOME_DEG             (APP_WRITER_PSI_LIMIT_DEG + APP_WRITER_HOMING_PULLOFF_DEG)
#define APP_WRITER_BETA_HOME_DEG            (APP_WRITER_PSI_HOME_DEG - APP_WRITER_THETA_HOME_DEG)
#define APP_WRITER_CAL_THETA_DEG            (0.0f)
#define APP_WRITER_CAL_PSI_DEG              (135.0f)

#define APP_WRITER_STAGE1_MOTOR_STEPS_PER_REV (3200.0f)
#define APP_WRITER_STAGE2_MOTOR_STEPS_PER_REV (3200.0f)
#define APP_WRITER_STAGE1_MOTOR_GEAR_TEETH  (2.0f)
#define APP_WRITER_STAGE1_ARM_GEAR_TEETH    (11.0f)
#define APP_WRITER_STAGE2_MOTOR_GEAR_TEETH  (2.0f)
#define APP_WRITER_STAGE2_ARM_GEAR_TEETH    (11.0f)
#define APP_WRITER_STAGE1_REDUCTION_RATIO   (APP_WRITER_STAGE1_ARM_GEAR_TEETH / APP_WRITER_STAGE1_MOTOR_GEAR_TEETH)
#define APP_WRITER_STAGE2_REDUCTION_RATIO   (APP_WRITER_STAGE2_ARM_GEAR_TEETH / APP_WRITER_STAGE2_MOTOR_GEAR_TEETH)
#define APP_WRITER_STAGE1_ARM_STEP_SCALE    (1.0f)
#define APP_WRITER_STAGE2_ARM_STEP_SCALE    (1.0f)

/* Electrical DIR levels used when the corresponding joint angle increases. Set after calibration. */
#define APP_WRITER_STAGE1_DIR_SIGN          (-1)
#define APP_WRITER_STAGE2_DIR_SIGN          (1)
#define APP_WRITER_STAGE2_PSI_DIR_SIGN      (1)
#define APP_WRITER_STAGE1_POSITIVE_DIR      (1u)
#define APP_WRITER_STAGE2_POSITIVE_DIR      (0u)

/* Direction-hysteresis compensation measured with diagnostics 19 and 20.
 * Keep logical psi steps separate from the Stage2 motor bias so homing,
 * limits, IK, and the reported Cartesian pose remain unchanged. */
#define APP_WRITER_DIR_COMP_THETA_REV_PSI_STEPS       (0)
#define APP_WRITER_DIR_COMP_PSI_REV_PSI_STEPS         (0)
#define APP_WRITER_DIRECTION_COMP_MAX_BIAS_STEPS      (64)
#define APP_WRITER_DIRECTION_COMP_PRELOAD_ENABLE      (0u)
#define APP_WRITER_DIRECTION_COMP_PRELOAD_FREQ_HZ     (100u)

#if APP_WRITER_DIRECTION_COMP_ENABLE && \
    (APP_WRITER_DIRECTION_COMP_MAX_BIAS_STEPS < \
     (APP_WRITER_DIR_COMP_THETA_REV_PSI_STEPS + \
      APP_WRITER_DIR_COMP_PSI_REV_PSI_STEPS))
#error "Direction compensation bias limit is smaller than the reachable bias"
#endif

#if APP_WRITER_DIRECTION_COMP_ENABLE && \
    !APP_WRITER_DIRECTION_COMP_PRELOAD_ENABLE
#error "Direction compensation requires the independent preload phase"
#endif

#if APP_WRITER_DIRECTION_COMP_PRELOAD_ENABLE && \
    (APP_WRITER_DIRECTION_COMP_PRELOAD_FREQ_HZ == 0u)
#error "Direction compensation preload frequency must be nonzero"
#endif

/*
 * Restore the pre-panel-key, physically exercised paper-map envelope.
 * The later 155/277 degree extension admitted the auxiliary-linkage overlap
 * region even though the two-link IK model considered those poses valid.
 */
#define APP_WRITER_A4_ENVELOPE_PROBE_ENABLE  (1u)

#define APP_WRITER_THETA_MIN_DEG            APP_WRITER_THETA_HOME_DEG
#define APP_WRITER_PSI_MIN_DEG              APP_WRITER_PSI_HOME_DEG
#if APP_WRITER_A4_ENVELOPE_PROBE_ENABLE
#define APP_WRITER_THETA_MAX_DEG            (135.0f)
#define APP_WRITER_PSI_MAX_DEG              (255.0f)
#else
#define APP_WRITER_THETA_MAX_DEG            (45.0f)
#define APP_WRITER_PSI_MAX_DEG              (179.0f)
#endif
#define APP_WRITER_BETA_MIN_DEG             (1.0f)
#define APP_WRITER_BETA_MAX_DEG             (179.0f)
#define APP_WRITER_MIN_BETA_ABS_DEG         (1.0f)
#define APP_WRITER_HOME_LIMIT_EPSILON_DEG   (0.05f)

#define APP_WRITER_DANGER_ZONE_ENABLE       (0u)
#define APP_WRITER_DANGER_THETA_MIN_DEG     (0.0f)
#define APP_WRITER_DANGER_THETA_MAX_DEG     (0.0f)
#define APP_WRITER_DANGER_BETA_MIN_DEG      (0.0f)
#define APP_WRITER_DANGER_BETA_MAX_DEG      (0.0f)

#define APP_WRITER_PLAN_SEGMENT_MM          (1.0f)
#define APP_WRITER_ANGLE_CHECK_STEP_DEG     (1.0f)
#define APP_WRITER_PLAN_MAX_SEGMENTS        (192u)
#define APP_WRITER_SAFE_WAYPOINT_THETA_DEG  (18.286086f)
#define APP_WRITER_SAFE_WAYPOINT_PSI_DEG    (144.095491f)

#define APP_WRITER_RAPID_MAX_FREQ_HZ        (200u)
#define APP_WRITER_RAPID_MIN_FREQ_HZ        (80u)
#define APP_WRITER_DRAW_MAX_FREQ_HZ         (120u)
#define APP_WRITER_DRAW_MIN_FREQ_HZ         (40u)
#define APP_WRITER_MOVE_MAX_FREQ_HZ         APP_WRITER_RAPID_MAX_FREQ_HZ
#define APP_WRITER_MOVE_MIN_FREQ_HZ         APP_WRITER_RAPID_MIN_FREQ_HZ
#define APP_WRITER_SEGMENT_TIMEOUT_MARGIN_MS (1000u)
#define APP_WRITER_ANGLE_TEST_MAX_FREQ_HZ   (200u)
#define APP_WRITER_ANGLE_TEST_MIN_FREQ_HZ   (100u)
#define APP_WRITER_MANUAL_JOG_FREQ_HZ       (200u)
#define APP_WRITER_HOMING_SEEK_FREQ_HZ      (300u)
#define APP_WRITER_HOMING_LOCATE_FREQ_HZ    (100u)
#define APP_WRITER_HOMING_DEBOUNCE_MS       (250u)
#define APP_WRITER_KINEMATICS_SELF_TEST_ENABLE (1u)

#define APP_WRITER_BRANCH_DIRECT            (0u)
#define APP_WRITER_BRANCH_IK_ELBOW_POSITIVE (1u)
#define APP_WRITER_BRANCH_IK_ELBOW_NEGATIVE (2u)

typedef struct {
    mid_scara_point_t user_point;
    mid_scara_point_t machine_point;
    mid_scara_angles_t angles;
} app_writer_pose_t;

typedef struct {
    app_writer_pose_t target_pose;
    float delta_theta_deg;
    float delta_psi_deg;
    float delta_beta_deg;
    int32_t stage1_target_steps;
    int32_t stage2_target_steps;
    int32_t stage2_motor_target_steps;
    int32_t stage2_comp_bias_steps;
    int8_t stage1_logical_dir;
    int8_t stage2_motor_dir;
    uint32_t stage1_steps;
    uint32_t stage2_steps;
    uint8_t stage1_dir;
    uint8_t stage2_dir;
    uint32_t stage1_freq_hz;
    uint32_t stage2_freq_hz;
    uint32_t master_freq_hz;
    float requested_feed_mm_min;
    float path_min_beta_abs_deg;
    float required_beta_abs_deg;
    uint8_t branch;
    float ik_radius_mm;
    float ik_cos_q2;
    float ik_sin_q2;
    float ik_q2_deg;
    float ik_error_x_mm;
    float ik_error_y_mm;
} app_writer_motion_cmd_t;

typedef enum {
    APP_WRITER_QUEUE_REJECTED = 0,
    APP_WRITER_QUEUE_ACCEPTED,
    APP_WRITER_QUEUE_FULL
} app_writer_queue_result_t;

void WriterMotion_Init_From_Home(void);
bool WriterMotion_Set_Home_Angles(float theta_deg, float psi_deg);
void WriterMotion_Get_Home_Angles(float *theta_deg, float *psi_deg);
bool WriterMotion_Start_To(float user_x_mm, float user_y_mm);
bool WriterMotion_Start_To_At_Feed(float user_x_mm, float user_y_mm,
                                   float feed_mm_min);
bool WriterMotion_Start_To_At_Feed_Limited(
    float user_x_mm, float user_y_mm, float feed_mm_min,
    uint32_t min_freq_hz, uint32_t max_freq_hz);
app_writer_queue_result_t WriterMotion_Queue_To(
    float user_x_mm, float user_y_mm);
app_writer_queue_result_t WriterMotion_Queue_To_At_Feed(
    float user_x_mm, float user_y_mm, float feed_mm_min);
uint32_t WriterMotion_Queue_Free(void);
bool WriterMotion_Queue_Is_Idle(void);
const app_writer_pose_t *WriterMotion_Get_Planned_Pose(void);
bool WriterMotion_Start_Joints(float theta_deg, float psi_deg);
bool WriterMotion_Start_Relative_Joints(float delta_theta_deg, float delta_psi_deg);
bool WriterMotion_Start_Stage1_Relative(float delta_theta_deg);
bool WriterMotion_Start_Stage2_Relative(float delta_psi_deg);
bool WriterMotion_Start_Motor_Deg(uint8_t motor_index, float motor_delta_deg, uint32_t freq_hz);
uint32_t WriterMotion_Stage1_Arm_Deg_To_Steps(float arm_delta_deg);
uint32_t WriterMotion_Stage2_Arm_Deg_To_Steps(float arm_delta_deg);
uint32_t WriterMotion_Motor_Deg_To_Steps(float motor_delta_deg, float motor_steps_per_rev);
bool WriterMotion_Is_Pose_Safe(float theta_deg, float psi_deg);
bool scara_is_pose_safe(float theta_deg, float psi_deg);
void WriterMotion_Task(void);
bool WriterMotion_Is_Busy(void);
void WriterMotion_Emergency_Stop(void);
const app_writer_pose_t *WriterMotion_Get_Pose(void);
const app_writer_motion_cmd_t *WriterMotion_Get_Last_Cmd(void);

#endif /* APP_WRITER_MOTION_H */
