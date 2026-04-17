/**
 * @file    bsp_servo.c
 * @brief   舵机核心逻辑实现
 */
#include "bsp_servo.h"

void BSP_Servo_Init_Device(bsp_servo_t *servo)
{
    if (servo == NULL) return;

    servo->angle = BSP_SERVO_MIN_ANGLE;

    if (servo->Init != NULL) {
        servo->Init(servo->pwm_pin.timer, servo->pwm_pin.channel);
    }
}

void BSP_Servo_Set_Angle(bsp_servo_t *servo, float angle)
{
    if (servo == NULL) return;

    if (angle < BSP_SERVO_MIN_ANGLE) angle = BSP_SERVO_MIN_ANGLE;
    if (angle > BSP_SERVO_MAX_ANGLE) angle = BSP_SERVO_MAX_ANGLE;

    servo->angle = angle;

    /* 0.5ms~2.5ms 映射到 PWM 计数值（20ms 周期，ARR=19999） */
    uint16_t pulse = (uint16_t)((angle / 180.0f) * 2000.0f + 500.0f);

    if (servo->Set_Pulse != NULL) {
        servo->Set_Pulse(servo->pwm_pin.timer, servo->pwm_pin.channel, pulse);
    }
}
