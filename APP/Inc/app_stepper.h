/**
 * @file    app_stepper.h
 * @brief   步进电机应用层声明（硬件绑定 + 业务逻辑入口）
 */
#ifndef APP_STEPPER_H
#define APP_STEPPER_H

#include "bsp_stepper.h"

/* ============ 步进电机X硬件配置 ============ */
/* PA1已被I2C0_SCL占用, 步进引脚迁移到PA2/PA3 */
#define STEPPER_X_DIR_PORT          GPIOA
#define STEPPER_X_DIR_PIN           DL_GPIO_PIN_2
#define STEPPER_X_STEP_PORT         GPIOA
#define STEPPER_X_STEP_PIN          DL_GPIO_PIN_3

/* ============ 业务接口声明 ============ */
extern bsp_stepper_t Stepper_X;

void App_Stepper_Init(void);
void Stepper_Start(uint8_t dir, uint32_t steps, uint32_t delay_ticks);
void Stepper_Task(void);

#endif /* APP_STEPPER_H */
