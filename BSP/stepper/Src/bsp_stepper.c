/**
 * @file    bsp_stepper.c
 * @brief   Minimal A4988/DRV8825 stepper driver core for timer-PWM STEP output.
 */
#include "bsp_stepper.h"
#include "elog.h"

#define BSP_STEPPER_TIMER_MAX_LOAD      (0xFFFFu)
#define BSP_STEPPER_TIMER_MAX_PRESCALE  (0xFFu)

pwm_params_t BSP_PWM_Calc_Params(uint32_t clk_freq, uint32_t target_freq, uint8_t duty_percent)
{
    pwm_params_t p = {0, 0, 0};

    if ((clk_freq == 0u) || (target_freq == 0u)) {
        return p;
    }

    if (duty_percent > 100u) {
        duty_percent = 100u;
    }

    uint64_t period_ticks = (uint64_t)clk_freq / target_freq;
    if (period_ticks < 2u) {
        period_ticks = 2u;
    }

    uint32_t prescale = 0u;
    if (period_ticks > (BSP_STEPPER_TIMER_MAX_LOAD + 1u)) {
        prescale = (uint32_t)((period_ticks - 1u) / (BSP_STEPPER_TIMER_MAX_LOAD + 1u));
        if (prescale > BSP_STEPPER_TIMER_MAX_PRESCALE) {
            prescale = BSP_STEPPER_TIMER_MAX_PRESCALE;
        }
    }

    uint64_t load_ticks = ((uint64_t)clk_freq / ((uint64_t)(prescale + 1u) * target_freq));
    if (load_ticks < 2u) {
        load_ticks = 2u;
    }
    if (load_ticks > (BSP_STEPPER_TIMER_MAX_LOAD + 1u)) {
        load_ticks = BSP_STEPPER_TIMER_MAX_LOAD + 1u;
    }

    p.psc = prescale;
    p.load = (uint32_t)(load_ticks - 1u);
    p.cc = (uint32_t)((load_ticks * duty_percent) / 100u);
    if (p.cc == 0u) {
        p.cc = 1u;
    }
    if (p.cc > p.load) {
        p.cc = p.load;
    }

    return p;
}

void BSP_Stepper_Run(bsp_stepper_t *stepper, uint8_t dir, uint32_t steps, uint32_t freq_hz)
{
    if ((stepper == NULL) ||
        (stepper->Gpio_Write == NULL) ||
        (stepper->PWM_Start == NULL) ||
        (stepper->PWM_Stop == NULL) ||
        (stepper->PWM_SetFreq == NULL)) {
        elog_e("BSP", "stepper run rejected: bad handle");
        return;
    }

    BSP_Stepper_Stop(stepper);

    if ((steps == 0u) || (freq_hz == 0u)) {
        stepper->step_count = 0u;
        stepper->target_steps = 0u;
        elog_w("BSP", "stepper run skipped steps=%u freq=%u", steps, freq_hz);
        return;
    }

    elog_i("BSP", "stepper start dir=%u steps=%u freq=%u", dir, steps, freq_hz);
    stepper->Gpio_Write(stepper->dir_pin.port, stepper->dir_pin.pin, dir ? 1u : 0u);
    stepper->step_count = 0u;
    stepper->target_steps = steps;
    stepper->current_dir = dir ? 1u : 0u;
    stepper->running = true;

    stepper->PWM_SetFreq(stepper->pwm_inst, freq_hz);
    stepper->PWM_Start(stepper->pwm_inst);
    elog_i("BSP", "stepper armed inst=%p running=%d", stepper->pwm_inst, stepper->running);
}

void BSP_Stepper_Stop(bsp_stepper_t *stepper)
{
    if (stepper == NULL) {
        return;
    }

    if (stepper->PWM_Stop != NULL) {
        stepper->PWM_Stop(stepper->pwm_inst);
    }
    stepper->running = false;
    elog_i("BSP", "stepper stop inst=%p step=%u target=%u", stepper->pwm_inst, stepper->step_count, stepper->target_steps);
}

void BSP_Stepper_OnPulse(bsp_stepper_t *stepper)
{
    if ((stepper == NULL) || (stepper->running == false)) {
        return;
    }

    stepper->step_count++;
    if ((stepper->step_count <= 3u) || ((stepper->step_count % 200u) == 0u)) {
        elog_i("BSP", "pulse inst=%p step=%u/%u", stepper->pwm_inst, stepper->step_count, stepper->target_steps);
    }
    if (stepper->step_count >= stepper->target_steps) {
        BSP_Stepper_Stop(stepper);
    }
}

bool BSP_Stepper_IsRunning(const bsp_stepper_t *stepper)
{
    return (stepper != NULL) ? stepper->running : false;
}
