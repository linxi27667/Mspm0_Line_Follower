#ifndef ENCODER_HEALTH_LOGIC_H
#define ENCODER_HEALTH_LOGIC_H

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    uint16_t left_stall_ticks;
    uint16_t right_stall_ticks;
} encoder_health_monitor_t;

static inline bool Encoder_Health_UpdateSide(
    int32_t target, int32_t delta, int32_t min_target,
    int32_t max_delta, uint16_t stall_limit, uint16_t *stall_ticks)
{
    bool delta_valid = delta >= -max_delta && delta <= max_delta;
    bool driven = target >= min_target || target <= -min_target;
    if (!delta_valid) return false;
    if (!driven || delta != 0) {
        *stall_ticks = 0u;
        return true;
    }
    if (*stall_ticks < stall_limit) (*stall_ticks)++;
    return *stall_ticks < stall_limit;
}

#endif
