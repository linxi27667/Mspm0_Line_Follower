/**
 * @file    bsp_tb6612.c
 * @brief   Portable single-channel TB6612FNG DC motor driver.
 */
#include "bsp_tb6612.h"

#include <stddef.h>

static bool Bsp_TB6612_HasDriveCallbacks(const bsp_tb6612_t *motor)
{
    if (motor == NULL) {
        return false;
    }

    return (motor->ain1.write != NULL) &&
           (motor->ain2.write != NULL) &&
           (motor->pwma.write != NULL);
}

static void Bsp_TB6612_WriteStandby(const bsp_tb6612_t *motor, bool level)
{
    if (motor->stby.write != NULL) {
        motor->stby.write(motor->stby.handle, level);
    }
}

bool Bsp_TB6612_Init(bsp_tb6612_t *motor)
{
    if (!Bsp_TB6612_HasDriveCallbacks(motor)) {
        return false;
    }

    if (motor->hardware_init != NULL) {
        motor->hardware_init(motor->hardware_context);
    }

    motor->pwma.write(motor->pwma.handle, 0U);
    motor->ain1.write(motor->ain1.handle, false);
    motor->ain2.write(motor->ain2.handle, false);
    Bsp_TB6612_WriteStandby(motor, false);

    motor->signed_duty_percent = 0;
    motor->enabled = false;
    return true;
}

bool Bsp_TB6612_SetEnabled(bsp_tb6612_t *motor, bool enable)
{
    if (!Bsp_TB6612_HasDriveCallbacks(motor)) {
        return false;
    }

    motor->pwma.write(motor->pwma.handle, 0U);
    motor->ain1.write(motor->ain1.handle, false);
    motor->ain2.write(motor->ain2.handle, false);
    Bsp_TB6612_WriteStandby(motor, enable);

    motor->signed_duty_percent = 0;
    motor->enabled = enable;
    return true;
}

bool Bsp_TB6612_Coast(bsp_tb6612_t *motor)
{
    if (!Bsp_TB6612_HasDriveCallbacks(motor)) {
        return false;
    }

    motor->pwma.write(motor->pwma.handle, 0U);
    motor->ain1.write(motor->ain1.handle, false);
    motor->ain2.write(motor->ain2.handle, false);
    motor->signed_duty_percent = 0;
    return true;
}

bool Bsp_TB6612_SetSignedDuty(bsp_tb6612_t *motor,
                              int16_t signed_duty_percent)
{
    uint8_t duty_percent;

    if (!Bsp_TB6612_HasDriveCallbacks(motor) || !motor->enabled) {
        return false;
    }

    if (signed_duty_percent > (int16_t)BSP_TB6612_DUTY_MAX_PERCENT) {
        signed_duty_percent = (int16_t)BSP_TB6612_DUTY_MAX_PERCENT;
    }
    if (signed_duty_percent < -(int16_t)BSP_TB6612_DUTY_MAX_PERCENT) {
        signed_duty_percent = -(int16_t)BSP_TB6612_DUTY_MAX_PERCENT;
    }

    if (signed_duty_percent == 0) {
        return Bsp_TB6612_Coast(motor);
    }

    /* Remove PWM before changing direction. */
    motor->pwma.write(motor->pwma.handle, 0U);

    if (signed_duty_percent > 0) {
        motor->ain1.write(motor->ain1.handle, true);
        motor->ain2.write(motor->ain2.handle, false);
        duty_percent = (uint8_t)signed_duty_percent;
    } else {
        motor->ain1.write(motor->ain1.handle, false);
        motor->ain2.write(motor->ain2.handle, true);
        duty_percent = (uint8_t)(-signed_duty_percent);
    }

    motor->pwma.write(motor->pwma.handle, duty_percent);
    motor->signed_duty_percent = (int8_t)signed_duty_percent;
    return true;
}

bool Bsp_TB6612_Brake(bsp_tb6612_t *motor)
{
    if (!Bsp_TB6612_HasDriveCallbacks(motor) || !motor->enabled) {
        return false;
    }

    motor->pwma.write(motor->pwma.handle, 0U);
    motor->ain1.write(motor->ain1.handle, true);
    motor->ain2.write(motor->ain2.handle, true);
    motor->pwma.write(motor->pwma.handle, BSP_TB6612_DUTY_MAX_PERCENT);
    motor->signed_duty_percent = 0;
    return true;
}
