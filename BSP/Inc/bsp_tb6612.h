/**
 * @file    bsp_tb6612.h
 * @brief   Portable single-channel TB6612FNG DC motor driver.
 *
 * The STBY callback is optional. Leave it NULL when STBY is hard-wired high.
 */
#ifndef BSP_TB6612_H
#define BSP_TB6612_H

#include <stdbool.h>
#include <stdint.h>

#define BSP_TB6612_DUTY_MAX_PERCENT    (100U)

typedef void (*bsp_tb6612_gpio_write_fn)(void *handle, bool level);
typedef void (*bsp_tb6612_pwm_write_fn)(void *handle, uint8_t duty_percent);
typedef void (*bsp_tb6612_hardware_init_fn)(void *context);

typedef struct {
    void *handle;
    bsp_tb6612_gpio_write_fn write;
} bsp_tb6612_gpio_t;

typedef struct {
    void *handle;
    bsp_tb6612_pwm_write_fn write;
} bsp_tb6612_pwm_t;

typedef struct {
    bsp_tb6612_gpio_t ain1;
    bsp_tb6612_gpio_t ain2;
    bsp_tb6612_gpio_t stby;
    bsp_tb6612_pwm_t pwma;

    void *hardware_context;
    bsp_tb6612_hardware_init_fn hardware_init;

    int8_t signed_duty_percent;
    bool enabled;
} bsp_tb6612_t;

bool Bsp_TB6612_Init(bsp_tb6612_t *motor);
bool Bsp_TB6612_SetEnabled(bsp_tb6612_t *motor, bool enable);
bool Bsp_TB6612_SetSignedDuty(bsp_tb6612_t *motor,
                              int16_t signed_duty_percent);
bool Bsp_TB6612_Coast(bsp_tb6612_t *motor);
bool Bsp_TB6612_Brake(bsp_tb6612_t *motor);

#endif /* BSP_TB6612_H */
