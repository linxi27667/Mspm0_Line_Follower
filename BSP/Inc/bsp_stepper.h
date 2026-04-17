/**
 * @file    bsp_stepper.h
 * @brief   步进电机核心驱动层（BSP — 纯逻辑，跨平台）
 */
#ifndef __BSP_STEPPER_H__
#define __BSP_STEPPER_H__

#include <stdint.h>
#include <stddef.h>

typedef struct {
    void     *port;
    uint32_t  pin;
} bsp_stepper_gpio_t;

typedef struct {
    bsp_stepper_gpio_t dir_pin;
    bsp_stepper_gpio_t step_pin;

    void (*Init)(void);
    void (*Gpio_Write)(void *port, uint32_t pin, uint8_t level);
    void (*Delay_us)(uint32_t us);
} bsp_stepper_t;

void BSP_Stepper_Init_Device(bsp_stepper_t *stepper);
void BSP_Stepper_Run(bsp_stepper_t *stepper, uint8_t dir, uint32_t steps, uint32_t delay_us);

#endif /* __BSP_STEPPER_H__ */
