/**
 * @file    mid_scara.c
 * @brief   Two-link writer robot kinematics implementation.
 */
#include "mid_scara.h"
#include <math.h>

static const float MID_SCARA_REACH_EPSILON_MM = 0.01f;

static float mid_scara_sq(float v)
{
    return v * v;
}

static float mid_scara_abs(float v)
{
    return (v >= 0.0f) ? v : -v;
}

static float mid_scara_clamp_unit(float v)
{
    if (v > 1.0f) {
        return 1.0f;
    }
    if (v < -1.0f) {
        return -1.0f;
    }
    return v;
}

float mid_scara_beta_deg(float theta_deg, float psi_deg)
{
    return psi_deg - theta_deg;
}

bool mid_scara_forward_absolute(const mid_scara_config_t *cfg,
                                const mid_scara_angles_t *angles,
                                mid_scara_point_t *point)
{
    if ((cfg == 0) || (angles == 0) || (point == 0) ||
        (cfg->l1_mm <= 0.0f) || (cfg->l2_mm <= 0.0f)) {
        return false;
    }

    float theta = angles->theta_deg * MID_SCARA_DEG_TO_RAD;
    float psi = angles->psi_deg * MID_SCARA_DEG_TO_RAD;

    point->x_mm = -(cosf(theta) * cfg->l1_mm) - (cosf(psi) * cfg->l2_mm);
    point->y_mm =  (sinf(theta) * cfg->l1_mm) + (sinf(psi) * cfg->l2_mm);

    return true;
}

bool mid_scara_inverse_absolute(const mid_scara_config_t *cfg,
                                const mid_scara_point_t *point,
                                mid_scara_angles_t *angles)
{
    mid_scara_ik_result_t result;

    if (angles == 0) {
        return false;
    }

    if (!mid_scara_inverse_absolute_ex(cfg, point, MID_SCARA_ELBOW_POSITIVE, &result)) {
        return false;
    }

    *angles = result.angles;
    return true;
}

bool mid_scara_inverse_absolute_ex(const mid_scara_config_t *cfg,
                                   const mid_scara_point_t *point,
                                   mid_scara_elbow_mode_t elbow_mode,
                                   mid_scara_ik_result_t *result)
{
    if ((cfg == 0) || (point == 0) || (result == 0) ||
        (cfg->l1_mm <= 0.0f) || (cfg->l2_mm <= 0.0f)) {
        return false;
    }

    if ((elbow_mode != MID_SCARA_ELBOW_POSITIVE) &&
        (elbow_mode != MID_SCARA_ELBOW_NEGATIVE)) {
        return false;
    }

    result->reachable = 0;
    result->elbow_mode = elbow_mode;

    /* Convert machine coordinates to a standard two-link frame. */
    float standard_x = -point->x_mm;
    float standard_y = point->y_mm;
    float l1_sq = mid_scara_sq(cfg->l1_mm);
    float l2_sq = mid_scara_sq(cfg->l2_mm);
    float radius_sq = mid_scara_sq(standard_x) + mid_scara_sq(standard_y);
    float radius = sqrtf(radius_sq);
    float max_reach = cfg->l1_mm + cfg->l2_mm;
    float min_reach = mid_scara_abs(cfg->l1_mm - cfg->l2_mm);

    result->standard_x_mm = standard_x;
    result->standard_y_mm = standard_y;
    result->radius_mm = radius;

    if ((radius > (max_reach + MID_SCARA_REACH_EPSILON_MM)) ||
        (radius < (min_reach - MID_SCARA_REACH_EPSILON_MM))) {
        return false;
    }

    float c2_raw = (radius_sq - l1_sq - l2_sq) / (2.0f * cfg->l1_mm * cfg->l2_mm);
    if ((c2_raw > (1.0f + MID_SCARA_C2_EPSILON)) ||
        (c2_raw < (-1.0f - MID_SCARA_C2_EPSILON))) {
        return false;
    }

    float c2 = mid_scara_clamp_unit(c2_raw);
    float s2_sq = 1.0f - mid_scara_sq(c2);
    if (s2_sq < 0.0f) {
        s2_sq = 0.0f;
    }

    float s2 = (float)elbow_mode * sqrtf(s2_sq);
    /* The author's squared K terms are equivalent only when L1 == L2.
     * Keep the author's swapped atan2 convention, but use the general
     * two-link terms so unequal measured link lengths remain invertible.
     */
    float k1 = cfg->l1_mm + cfg->l2_mm * c2;
    float k2 = cfg->l2_mm * s2;
    float q2 = atan2f(s2, c2);
    float theta = atan2f(k1, k2) - atan2f(standard_x, standard_y);
    float psi = theta + q2;

    result->angles.theta_deg = theta * MID_SCARA_RAD_TO_DEG;
    result->angles.psi_deg = psi * MID_SCARA_RAD_TO_DEG;
    result->angles.beta_deg = mid_scara_beta_deg(result->angles.theta_deg,
                                                 result->angles.psi_deg);
    result->q2_deg = q2 * MID_SCARA_RAD_TO_DEG;
    result->cos_q2 = c2;
    result->sin_q2 = s2;
    result->k1 = k1;
    result->k2 = k2;
    result->reachable = 1;

    if (!mid_scara_forward_absolute(cfg, &result->angles, &result->fk_point)) {
        result->reachable = 0;
        return false;
    }

    result->error_x_mm = result->fk_point.x_mm - point->x_mm;
    result->error_y_mm = result->fk_point.y_mm - point->y_mm;

    return true;
}
