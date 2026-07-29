/**
 * @file    app_stepper.h
 * @brief   Dual-axis stepper hardware binding for the writer robot.
 */
#ifndef APP_STEPPER_H
#define APP_STEPPER_H

#include <stdbool.h>
#include <stdint.h>
#include "ti_msp_dl_config.h"
#include "bsp_stepper.h"

/* Axis wiring:
 *   Arm1 STEP -> PA10 / TIMA1_C0
 *   Arm1 DIR  -> PA11 / GPIO output
 *   Arm2 STEP -> PA8  / TIMA0_C0
 *   Arm2 DIR  -> PA9  / GPIO output
 */
#define STEPPER_X_DIR_PORT      GPIOA
#define STEPPER_X_DIR_PIN       DL_GPIO_PIN_11
#define STEPPER_X_STEP_PORT     GPIOA
#define STEPPER_X_STEP_PIN      DL_GPIO_PIN_10
#define STEPPER_Y_DIR_PORT      GPIOA
#define STEPPER_Y_DIR_PIN       DL_GPIO_PIN_9
#define STEPPER_Y_STEP_PORT     GPIOA
#define STEPPER_Y_STEP_PIN      DL_GPIO_PIN_8

#define STEPPER_X_PWM_INST      STEP_INST
#define STEPPER_X_PWM_IRQn      STEP_INST_INT_IRQN
#define STEPPER_X_PWM_INT_FLAG  DL_TIMER_INTERRUPT_ZERO_EVENT
#define STEPPER_X_PWM_CC_IDX    GPIO_STEP_C0_IDX
#define STEPPER_X_PWM_CLK_FREQ  STEP_INST_CLK_FREQ

#define STEPPER_Y_PWM_INST      STEP2_INST
#define STEPPER_Y_PWM_IRQn      STEP2_INST_INT_IRQN
#define STEPPER_Y_PWM_INT_FLAG  DL_TIMER_INTERRUPT_ZERO_EVENT
#define STEPPER_Y_PWM_CC_IDX    GPIO_STEP2_C0_IDX
#define STEPPER_Y_PWM_CLK_FREQ  STEP2_INST_CLK_FREQ

#define LIMIT_STAGE1_PORT       GPIOA
#define LIMIT_STAGE1_PIN        DL_GPIO_PIN_26
#define LIMIT_STAGE1_HOME_DIR   (1u)
#define LIMIT_STAGE2_PORT       GPIOA
#define LIMIT_STAGE2_PIN        DL_GPIO_PIN_27
#define LIMIT_STAGE2_HOME_DIR   (1u)

#define APP_STEPPER_DUAL_QUEUE_CAPACITY (32u)
#define APP_STEPPER_JUNCTION_PLANNER_ENABLE (1u)
#define APP_STEPPER_AMASS_ENABLE (1u)
#define APP_STEPPER_AMASS_MAX_LEVEL (3u)

typedef struct {
    uint8_t stage1_dir;
    uint8_t stage2_dir;
    int8_t stage1_position_sign;
    int8_t stage2_position_sign;
    uint32_t stage1_steps;
    uint32_t stage2_steps;
    uint32_t master_freq_hz;
    /*
     * Queue-planner fields. Callers only provide the fields above; the
     * stepper queue fills these values when the block is appended.
     */
    uint32_t max_entry_freq_hz;
    uint32_t planned_entry_freq_hz;
    uint32_t planned_exit_freq_hz;
} app_stepper_dual_block_t;

extern bsp_stepper_t App_Stepper_X;
extern bsp_stepper_t App_Stepper_Y;

void App_Stepper_Stage1_Run(uint8_t dir, uint32_t steps, uint32_t freq_hz);
void App_Stepper_Stage2_Run(uint8_t dir, uint32_t steps, uint32_t freq_hz);
bool App_Stepper_Dual_Run(uint8_t stage1_dir, uint32_t stage1_steps,
                          uint8_t stage2_dir, uint32_t stage2_steps,
                          uint32_t master_freq_hz);
bool App_Stepper_Dual_Queue_Block(
    const app_stepper_dual_block_t *block);
uint32_t App_Stepper_Dual_Queue_Free(void);
uint32_t App_Stepper_Dual_Queue_Count(void);
uint32_t App_Stepper_Dual_Queue_Completed(void);
void App_Stepper_Dual_Queue_Set_Position(int32_t stage1_steps,
                                         int32_t stage2_steps);
void App_Stepper_Dual_Queue_Get_Position(int32_t *stage1_steps,
                                         int32_t *stage2_steps);
void App_Stepper_Dual_Queue_Clear(void);
bool App_Stepper_Dual_Queue_IsBusy(void);
void App_Stepper_Dual_Stop(void);
bool App_Stepper_Dual_IsRunning(void);
void App_Stepper_Stage1_Stop(void);
void App_Stepper_Stage2_Stop(void);
bool App_Stepper_Stage1_IsLimitHit(void);
bool App_Stepper_Stage2_IsLimitHit(void);
uint32_t App_Stepper_Stage1_Total_Pulses(void);
uint32_t App_Stepper_Stage2_Total_Pulses(void);
void App_Stepper_Zero_All(void);
void App_Stepper_Zero_All_At_Freq(uint32_t freq_hz);
void App_Stepper_Cancel_Zeroing(void);
bool App_Stepper_IsZeroing(void);
void App_Stepper_Task(void);

#endif /* APP_STEPPER_H */
