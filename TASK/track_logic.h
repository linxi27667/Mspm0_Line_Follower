/**
 * @file    track_logic.h
 * @brief   Pure tracking decision helpers that can be tested on host.
 */
#ifndef TRACK_LOGIC_H
#define TRACK_LOGIC_H

#include <stdbool.h>
#include <stdint.h>

typedef enum {
    TRACK_STATE_IDLE = 0,
    TRACK_STATE_LINE_FOLLOW,
    TRACK_STATE_RIGHT_ANGLE,
    TRACK_STATE_LINE_LOST,
    TRACK_STATE_START_LINE,
    TRACK_STATE_CROSS,
    TRACK_STATE_ROTATE,
    TRACK_STATE_HEADING_HOLD,
    TRACK_STATE_FINISHED
} track_state_t;

#ifndef TRACK_RIGHT_ANGLE_DONE_ERR
#define TRACK_RIGHT_ANGLE_DONE_ERR        5.0f
#endif
#ifndef TRACK_RIGHT_ANGLE_MIN_EXIT_ANGLE
#define TRACK_RIGHT_ANGLE_MIN_EXIT_ANGLE  55.0f
#endif
#ifndef TRACK_RIGHT_ANGLE_EXIT_CENTER_MIN
#define TRACK_RIGHT_ANGLE_EXIT_CENTER_MIN 2
#endif
#ifndef TRACK_RIGHT_ANGLE_EXIT_BLACK_MIN
#define TRACK_RIGHT_ANGLE_EXIT_BLACK_MIN  1
#endif
#ifndef TRACK_RIGHT_ANGLE_EXIT_BLACK_MAX
#define TRACK_RIGHT_ANGLE_EXIT_BLACK_MAX  5
#endif

static inline float Track_Abs_Float(float v)
{
    return (v >= 0.0f) ? v : -v;
}

#define TRACK_ROTATE_MIN_DEG       1.0f
#define TRACK_ROTATE_MAX_DEG       180.0f
#ifndef TRACK_ROTATE_DONE_ERR_DEG
#define TRACK_ROTATE_DONE_ERR_DEG  3.0f
#endif
#define TRACK_ROTATE_SETTLE_RATE   6.0f

static inline bool Track_Rotate_TargetValid(float target_deg)
{
    float magnitude;

    if (target_deg != target_deg) return false;
    magnitude = Track_Abs_Float(target_deg);
    return magnitude >= TRACK_ROTATE_MIN_DEG &&
           magnitude <= TRACK_ROTATE_MAX_DEG;
}

static inline float Track_Rotate_Error(float heading_baseline,
                                       float heading,
                                       float target_deg)
{
    return target_deg - (heading - heading_baseline);
}

static inline bool Track_Rotate_AngleInside(float angle_error_deg)
{
    return Track_Abs_Float(angle_error_deg) <= TRACK_ROTATE_DONE_ERR_DEG;
}

static inline bool Track_Rotate_Complete(float angle_error_deg,
                                          float gyro_abs_deg_s)
{
    return Track_Rotate_AngleInside(angle_error_deg) &&
           gyro_abs_deg_s <= TRACK_ROTATE_SETTLE_RATE;
}

static inline uint8_t Track_Rotate_UpdateSettleFrames(uint8_t current,
                                                       bool inside_tolerance)
{
    if (!inside_tolerance) return 0u;
    return (current < 255u) ? (uint8_t)(current + 1u) : current;
}

static inline bool Track_Rotate_Settled(uint8_t settle_frames,
                                         uint8_t required_frames)
{
    return required_frames > 0u && settle_frames >= required_frames;
}

static inline float Track_Rotate_SpeedLimit(float error_abs_deg,
                                             float fine_zone_deg,
                                             float blend_zone_deg,
                                             float fine_max_speed,
                                             float max_speed)
{
    if (error_abs_deg <= fine_zone_deg) return fine_max_speed;
    if (blend_zone_deg <= fine_zone_deg || error_abs_deg >= blend_zone_deg) {
        return max_speed;
    }

    float ratio = (error_abs_deg - fine_zone_deg) /
                  (blend_zone_deg - fine_zone_deg);
    return fine_max_speed + ratio * (max_speed - fine_max_speed);
}

static inline void Track_Rotate_Command(float target_deg,
                                        int32_t speed,
                                        int32_t *left_speed,
                                        int32_t *right_speed)
{
    if (left_speed == 0 || right_speed == 0) return;

    if (target_deg > 0.0f) {
        *left_speed = -speed;
        *right_speed = speed;
    } else {
        *left_speed = speed;
        *right_speed = -speed;
    }
}

static inline int32_t Track_Slew_Command(int32_t current,
                                          int32_t target,
                                          int32_t step)
{
    /* Zero means coast. Do not walk through tiny nonzero targets because the
     * motor loop converts them to its minimum startup PWM. */
    if (target == 0) return 0;
    if (step <= 0) return target;
    if (current < target) {
        current += step;
        return (current > target) ? target : current;
    }
    if (current > target) {
        current -= step;
        return (current < target) ? target : current;
    }
    return current;
}

static inline bool Track_Rotate_Timeout(uint32_t now,
                                        uint32_t started_at,
                                        uint32_t timeout_ms)
{
    return (uint32_t)(now - started_at) >= timeout_ms;
}

static inline bool Track_State_Allows_Motor(track_state_t state)
{
    return state != TRACK_STATE_IDLE && state != TRACK_STATE_FINISHED;
}

static inline bool Track_Timeout_Reached(uint32_t now,
                                         uint32_t started_at,
                                         uint32_t timeout_ms)
{
    return (uint32_t)(now - started_at) >= timeout_ms;
}

static inline float Track_RightAngle_Direction(float error,
                                                float last_error,
                                                float gyro_rate)
{
    float source = error;
    if (Track_Abs_Float(source) < 0.25f) source = last_error;
    if (Track_Abs_Float(source) < 0.25f) source = gyro_rate;
    return (source >= 0.0f) ? 1.0f : -1.0f;
}

static inline bool Track_RightAngle_ShouldExit(float turned_abs_deg,
                                               float angle_error_deg,
                                               uint8_t center_black_count,
                                               uint8_t black_count)
{
    if (Track_Abs_Float(angle_error_deg) <= TRACK_RIGHT_ANGLE_DONE_ERR) {
        return true;
    }

    return (turned_abs_deg >= TRACK_RIGHT_ANGLE_MIN_EXIT_ANGLE) &&
           (center_black_count >= TRACK_RIGHT_ANGLE_EXIT_CENTER_MIN) &&
           (black_count >= TRACK_RIGHT_ANGLE_EXIT_BLACK_MIN) &&
           (black_count <= TRACK_RIGHT_ANGLE_EXIT_BLACK_MAX);
}

#endif /* TRACK_LOGIC_H */
