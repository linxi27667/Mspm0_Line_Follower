/**
 * @file    bsp_servo.c
 * @brief   Generic RC servo angle-to-pulse conversion.
 */
#include "bsp_servo.h"

int8_t BSP_Servo_Init_Device(bsp_servo_t *servo)
{
    if ((servo == NULL) || (servo->Init == NULL) ||
        (servo->Set_Pulse == NULL)) {
        return -1;
    }

    if (servo->Gpio_Config != NULL) {
        servo->Gpio_Config();
    }
    if (servo->Tim_Config != NULL) {
        servo->Tim_Config();
    }

    servo->angle_deg = BSP_SERVO_MIN_ANGLE_DEG;
    return servo->Init(servo->pwm_pin.timer, servo->pwm_pin.channel);
}

void BSP_Servo_Set_Angle(bsp_servo_t *servo, float angle_deg)
{
    float pulse_us;

    if ((servo == NULL) || (servo->Set_Pulse == NULL)) {
        return;
    }

    if (angle_deg < BSP_SERVO_MIN_ANGLE_DEG) {
        angle_deg = BSP_SERVO_MIN_ANGLE_DEG;
    } else if (angle_deg > BSP_SERVO_MAX_ANGLE_DEG) {
        angle_deg = BSP_SERVO_MAX_ANGLE_DEG;
    }

    servo->angle_deg = angle_deg;
    pulse_us = (angle_deg / BSP_SERVO_MAX_ANGLE_DEG) *
               (float)(BSP_SERVO_MAX_PULSE_US - BSP_SERVO_MIN_PULSE_US) +
               (float)BSP_SERVO_MIN_PULSE_US;
    servo->Set_Pulse(servo->pwm_pin.timer, servo->pwm_pin.channel,
                     (uint16_t)(pulse_us + 0.5f));
}
