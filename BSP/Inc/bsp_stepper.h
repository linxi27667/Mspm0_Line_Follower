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

typedef enum {
    STEPPER_STATE_IDLE = 0,
    STEPPER_STATE_DIR_SET,
    STEPPER_STATE_STEP_HIGH,
    STEPPER_STATE_STEP_LOW
} bsp_stepper_state_t;

typedef struct {
    bsp_stepper_gpio_t dir_pin;
    bsp_stepper_gpio_t step_pin;

    /* --- 运行状态 --- */
    bsp_stepper_state_t state;
    uint8_t  dir;
    uint32_t steps_remaining;
    uint32_t delay_ticks;
    uint32_t delay_counter;

    /* --- 抽象硬件操作方法 --- */
    void (*Init)(void);
    void (*Gpio_Write)(void *port, uint32_t pin, uint8_t level);
} bsp_stepper_t;

void BSP_Stepper_Init_Device(bsp_stepper_t *stepper);
void BSP_Stepper_Start(bsp_stepper_t *stepper, uint8_t dir, uint32_t steps, uint32_t delay_ticks);
void BSP_Stepper_Task(bsp_stepper_t *stepper);

#endif /* __BSP_STEPPER_H__ */
