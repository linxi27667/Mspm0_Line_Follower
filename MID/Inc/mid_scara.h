/**
 * @file    mid_scara.h
 * @brief   Two-link writer robot kinematics.
 */
#ifndef MID_SCARA_H
#define MID_SCARA_H

#include <stdbool.h>

#define MID_SCARA_PI             (3.14159265358979323846f)
#define MID_SCARA_RAD_TO_DEG     (180.0f / MID_SCARA_PI)
#define MID_SCARA_DEG_TO_RAD     (MID_SCARA_PI / 180.0f)
#define MID_SCARA_C2_EPSILON     (0.0005f)

typedef enum {
    MID_SCARA_ELBOW_POSITIVE = 1,
    MID_SCARA_ELBOW_NEGATIVE = -1
} mid_scara_elbow_mode_t;

typedef struct {
    float l1_mm;
    float l2_mm;
} mid_scara_config_t;

typedef struct {
    float x_mm;
    float y_mm;
} mid_scara_point_t;

typedef struct {
    float theta_deg;      /* Stage1 absolute angle. */
    float psi_deg;        /* Stage2 absolute angle. */
    float beta_deg;       /* Derived debug value: psi - theta. */
} mid_scara_angles_t;

typedef struct {
    mid_scara_angles_t angles;
    mid_scara_point_t fk_point;
    float standard_x_mm;  /* Standard two-link X: X = -machine_x. */
    float standard_y_mm;  /* Standard two-link Y: Y = machine_y. */
    float radius_mm;
    float cos_q2;
    float sin_q2;
    float q2_deg;         /* Relative geometric angle, q2 = psi - theta. */
    float k1;
    float k2;
    float error_x_mm;
    float error_y_mm;
    int reachable;
    mid_scara_elbow_mode_t elbow_mode;
} mid_scara_ik_result_t;

float mid_scara_beta_deg(float theta_deg, float psi_deg);
bool mid_scara_forward_absolute(const mid_scara_config_t *cfg,
                                const mid_scara_angles_t *angles,
                                mid_scara_point_t *point);
bool mid_scara_inverse_absolute_ex(const mid_scara_config_t *cfg,
                                   const mid_scara_point_t *point,
                                   mid_scara_elbow_mode_t elbow_mode,
                                   mid_scara_ik_result_t *result);
bool mid_scara_inverse_absolute(const mid_scara_config_t *cfg,
                                const mid_scara_point_t *point,
                                mid_scara_angles_t *angles);

#endif /* MID_SCARA_H */
