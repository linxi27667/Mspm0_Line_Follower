/**
 * @file    track_motor.c
 * @brief   双电机驱动实现 — 直接操作 PWM 定时器 + GPIO 方向
 */
#include "track_motor.h"
#include "ti_msp_dl_config.h"

void Track_Motor_SetLeft(int32_t speed)
{
    if (speed > 0) {
        DL_GPIO_setPins  (Monitor_Dir_PORT, Monitor_Dir_Monitor_AIN1_PIN);
        DL_GPIO_clearPins(Monitor_Dir_PORT, Monitor_Dir_Monitor_AIN2_PIN);
        DL_TimerG_setCaptureCompareValue(Monitor_Left_Timer_INST,
                                         (uint32_t)speed, DL_TIMER_CC_0_INDEX);
    } else if (speed < 0) {
        DL_GPIO_clearPins(Monitor_Dir_PORT, Monitor_Dir_Monitor_AIN1_PIN);
        DL_GPIO_setPins  (Monitor_Dir_PORT, Monitor_Dir_Monitor_AIN2_PIN);
        DL_TimerG_setCaptureCompareValue(Monitor_Left_Timer_INST,
                                         (uint32_t)(-speed), DL_TIMER_CC_0_INDEX);
    } else {
        DL_GPIO_clearPins(Monitor_Dir_PORT, Monitor_Dir_Monitor_AIN1_PIN);
        DL_GPIO_clearPins(Monitor_Dir_PORT, Monitor_Dir_Monitor_AIN2_PIN);
        DL_TimerG_setCaptureCompareValue(Monitor_Left_Timer_INST,
                                         0, DL_TIMER_CC_0_INDEX);
    }
}

void Track_Motor_SetRight(int32_t speed)
{
    if (speed > 0) {
        DL_GPIO_setPins  (Right_Motor_Dir_PORT, Right_Motor_Dir_AIN1_PIN);
        DL_GPIO_clearPins(Right_Motor_Dir_PORT, Right_Motor_Dir_AIN2_PIN);
        DL_TimerG_setCaptureCompareValue(Right_Motor_Timer_INST,
                                         (uint32_t)speed, DL_TIMER_CC_0_INDEX);
    } else if (speed < 0) {
        DL_GPIO_clearPins(Right_Motor_Dir_PORT, Right_Motor_Dir_AIN1_PIN);
        DL_GPIO_setPins  (Right_Motor_Dir_PORT, Right_Motor_Dir_AIN2_PIN);
        DL_TimerG_setCaptureCompareValue(Right_Motor_Timer_INST,
                                         (uint32_t)(-speed), DL_TIMER_CC_0_INDEX);
    } else {
        DL_GPIO_clearPins(Right_Motor_Dir_PORT, Right_Motor_Dir_AIN1_PIN);
        DL_GPIO_clearPins(Right_Motor_Dir_PORT, Right_Motor_Dir_AIN2_PIN);
        DL_TimerG_setCaptureCompareValue(Right_Motor_Timer_INST,
                                         0, DL_TIMER_CC_0_INDEX);
    }
}
