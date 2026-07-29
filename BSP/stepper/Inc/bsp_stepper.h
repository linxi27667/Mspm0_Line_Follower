/**
 * @file    bsp_stepper.h
 * @brief   Minimal A4988/DRV8825 stepper driver core for TI bare-metal projects.
 */
#ifndef __BSP_STEPPER_H__
#define __BSP_STEPPER_H__

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct {
    void *port;
    uint32_t pin;
} bsp_stepper_gpio_t;

typedef struct {
    uint32_t psc;
    uint32_t load;
    uint32_t cc;
} pwm_params_t;

typedef struct {
    bsp_stepper_gpio_t dir_pin;
    void *pwm_inst;

    void (*Gpio_Write)(void *port, uint32_t pin, uint8_t level);
    void (*PWM_Start)(void *inst);
    void (*PWM_Stop)(void *inst);
    void (*PWM_SetFreq)(void *inst, uint32_t freq_hz);

    volatile uint32_t step_count;
    uint32_t target_steps;
    uint8_t current_dir;
    volatile bool running;
} bsp_stepper_t;

pwm_params_t BSP_PWM_Calc_Params(uint32_t clk_freq, uint32_t target_freq, uint8_t duty_percent);

void BSP_Stepper_Run(bsp_stepper_t *stepper, uint8_t dir, uint32_t steps, uint32_t freq_hz);
void BSP_Stepper_Stop(bsp_stepper_t *stepper);
void BSP_Stepper_OnPulse(bsp_stepper_t *stepper);
bool BSP_Stepper_IsRunning(const bsp_stepper_t *stepper);

#endif /* __BSP_STEPPER_H__ */
