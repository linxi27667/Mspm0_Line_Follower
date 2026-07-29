/**
 * @file    bsp_servo.h
 * @brief   Generic RC servo angle-to-pulse conversion.
 */
#ifndef BSP_SERVO_H
#define BSP_SERVO_H

#include <stddef.h>
#include <stdint.h>

#define BSP_SERVO_MIN_ANGLE_DEG      (0.0f)
#define BSP_SERVO_MAX_ANGLE_DEG      (180.0f)
#define BSP_SERVO_MIN_PULSE_US       (500u)
#define BSP_SERVO_MAX_PULSE_US       (2500u)

typedef struct {
    void *timer;
    uint32_t channel;
} bsp_servo_pwm_t;

typedef struct {
    bsp_servo_pwm_t pwm_pin;
    float angle_deg;
    void (*Gpio_Config)(void);
    void (*Tim_Config)(void);
    int8_t (*Init)(void *timer, uint32_t channel);
    void (*Set_Pulse)(void *timer, uint32_t channel, uint16_t pulse_us);
} bsp_servo_t;

int8_t BSP_Servo_Init_Device(bsp_servo_t *servo);
void BSP_Servo_Set_Angle(bsp_servo_t *servo, float angle_deg);

#endif /* BSP_SERVO_H */
