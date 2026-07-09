/**
 * @file    track_logic.h
 * @brief   Pure tracking decision helpers that can be tested on host.
 */
#ifndef TRACK_LOGIC_H
#define TRACK_LOGIC_H

#include <stdbool.h>
#include <stdint.h>

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
