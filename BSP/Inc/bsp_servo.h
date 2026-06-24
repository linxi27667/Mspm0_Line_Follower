/**
 * @file    bsp_servo.h
 * @brief   舵机核心协议层（BSP — 纯逻辑，跨平台）
 */
#ifndef __BSP_SERVO_H__
#define __BSP_SERVO_H__

#include <stdint.h>
#include <stddef.h>

#define BSP_SERVO_MIN_ANGLE  0.0f
#define BSP_SERVO_MAX_ANGLE  180.0f

/* --- 抽象 PWM 资源 --- */
typedef struct {
    void     *timer;
    uint32_t  channel;
} bsp_servo_pwm_t;

/* --- 舵机对象 --- */
typedef struct {
    /* --- 1. 物理配置 (Config) --- */
    bsp_servo_pwm_t pwm_pin;
    float angle;

    /* --- 2. 抽象硬件操作方法 (Function Pointers) --- */
    void   (*Gpio_Config)(void);
    void   (*Tim_Config)(void);
    int8_t (*Init)(void *timer, uint32_t channel);
    void   (*Set_Pulse)(void *timer, uint32_t channel, uint16_t pulse);
} bsp_servo_t;

/* --- 3. 对外核心API (跨平台通用) --- */
void BSP_Servo_Init_Device(bsp_servo_t *servo);
void BSP_Servo_Set_Angle(bsp_servo_t *servo, float angle);

#endif /* __BSP_SERVO_H__ */
