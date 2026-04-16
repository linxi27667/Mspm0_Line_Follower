/**
 * @file    bsp_stepper.c
 * @brief   步进电机核心逻辑实现
 */
#include "bsp_stepper.h"

void BSP_Stepper_Init_Device(bsp_stepper_t *stepper)
{
    if (stepper == NULL || stepper->Init == NULL) return;
    stepper->Init();
}

void BSP_Stepper_Run(bsp_stepper_t *stepper, uint8_t dir, uint32_t steps, uint32_t delay_us)
{
    if (stepper == NULL || stepper->Gpio_Write == NULL || stepper->Delay_us == NULL) return;

    stepper->Gpio_Write(stepper->dir_pin.port, stepper->dir_pin.pin, dir ? 1 : 0);

    for (uint32_t i = 0; i < steps; i++) {
        stepper->Gpio_Write(stepper->step_pin.port, stepper->step_pin.pin, 1);
        stepper->Delay_us(delay_us);
        stepper->Gpio_Write(stepper->step_pin.port, stepper->step_pin.pin, 0);
        stepper->Delay_us(delay_us);
    }
}
