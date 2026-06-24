/**
 * @file    bsp_stepper.c
 * @brief   步进电机核心逻辑实现（BSP — 纯逻辑，跨平台）
 */
#include "bsp_stepper.h"

/* ================= 1. 设备初始化 ================= */
void BSP_Stepper_Init_Device(bsp_stepper_t *stepper)
{
    if (stepper == NULL || stepper->Init == NULL) return;
    stepper->state = STEPPER_STATE_IDLE;
    stepper->steps_remaining = 0;
    stepper->delay_counter = 0;
    stepper->Init();
}

/* ================= 2. 启动步进电机 ================= */
void BSP_Stepper_Start(bsp_stepper_t *stepper, uint8_t dir, uint32_t steps, uint32_t delay_ticks)
{
    if (stepper == NULL || steps == 0) return;

    stepper->dir = dir;
    stepper->steps_remaining = steps;
    stepper->delay_ticks = delay_ticks;
    stepper->delay_counter = 0;
    stepper->state = STEPPER_STATE_DIR_SET;
}

/* ================= 3. 状态机任务（非阻塞） ================= */
void BSP_Stepper_Task(bsp_stepper_t *stepper)
{
    if (stepper == NULL || stepper->Gpio_Write == NULL) return;

    switch (stepper->state) {
        case STEPPER_STATE_IDLE:
            /* 空闲状态，等待启动 */
            break;

        case STEPPER_STATE_DIR_SET:
            /* 设置方向 */
            stepper->Gpio_Write(stepper->dir_pin.port, stepper->dir_pin.pin, stepper->dir);
            stepper->state = STEPPER_STATE_STEP_HIGH;
            break;

        case STEPPER_STATE_STEP_HIGH:
            /* 输出高电平 */
            stepper->Gpio_Write(stepper->step_pin.port, stepper->step_pin.pin, 1);
            stepper->delay_counter = 0;
            stepper->state = STEPPER_STATE_STEP_LOW;
            break;

        case STEPPER_STATE_STEP_LOW:
            /* 延时计数 */
            stepper->delay_counter++;
            if (stepper->delay_counter >= stepper->delay_ticks) {
                stepper->Gpio_Write(stepper->step_pin.port, stepper->step_pin.pin, 0);
                stepper->steps_remaining--;
                if (stepper->steps_remaining == 0) {
                    stepper->state = STEPPER_STATE_IDLE;
                } else {
                    stepper->state = STEPPER_STATE_STEP_HIGH;
                }
            }
            break;

        default:
            stepper->state = STEPPER_STATE_IDLE;
            break;
    }
}
