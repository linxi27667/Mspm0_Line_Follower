#ifndef SAFETY_LOGIC_H
#define SAFETY_LOGIC_H

#include <stdbool.h>
#include <stdint.h>

typedef enum {
    SAFETY_LOGIC_OK = 0,
    SAFETY_LOGIC_GRAYSCALE_EXPIRED,
    SAFETY_LOGIC_CONTROL_TICK_MISSED,
    SAFETY_LOGIC_ENCODER_ANOMALY,
    SAFETY_LOGIC_HEARTBEAT_LOST,
    SAFETY_LOGIC_SENSOR_ABNORMAL,
} safety_logic_result_t;

typedef struct {
    bool remote_armed;
    bool grayscale_required;
    bool grayscale_seen;
    bool heartbeat_seen;
    bool encoder_left_ok;
    bool encoder_right_ok;
    bool sensor_abnormal;
    uint32_t last_heartbeat_tick;
    uint32_t last_grayscale_tick;
    uint32_t last_control_tick;
} safety_health_t;

static inline bool Safety_Logic_CanEnterRotation(uint8_t state)
{
    /* Rotation is IMU/encoder based and does not consume grayscale data.
     * BOOT here means only that grayscale white+black calibration is pending;
     * the caller still validates IMU health and a fresh remote heartbeat. */
    return state == 0u || state == 2u; /* BOOT or READY */
}

static inline safety_logic_result_t Safety_Logic_Check(
    uint32_t now, const safety_health_t *health,
    uint32_t heartbeat_timeout, uint32_t grayscale_timeout,
    uint32_t control_timeout)
{
    if (health->sensor_abnormal) return SAFETY_LOGIC_SENSOR_ABNORMAL;
    if (health->grayscale_required &&
        (!health->grayscale_seen ||
         (uint32_t)(now - health->last_grayscale_tick) > grayscale_timeout)) {
        return SAFETY_LOGIC_GRAYSCALE_EXPIRED;
    }
    if (!health->encoder_left_ok || !health->encoder_right_ok) {
        return SAFETY_LOGIC_ENCODER_ANOMALY;
    }
    if (health->remote_armed &&
        (!health->heartbeat_seen ||
         (uint32_t)(now - health->last_heartbeat_tick) > heartbeat_timeout)) {
        return SAFETY_LOGIC_HEARTBEAT_LOST;
    }
    if ((uint32_t)(now - health->last_control_tick) > control_timeout) {
        return SAFETY_LOGIC_CONTROL_TICK_MISSED;
    }
    return SAFETY_LOGIC_OK;
}

#endif
