/**
 * @file    bsp_encoder_motor.h
 * @brief   霍尔电机驱动核心框架（BSP — 纯逻辑，跨平台）
 */
#ifndef __BSP_ENCODER_MOTOR_H__
#define __BSP_ENCODER_MOTOR_H__

#include <stdint.h>
#include <stddef.h>

/* --- 抽象 GPIO 对象 --- */
typedef struct {
    void     *port;
    uint32_t  pin;
} bsp_motor_gpio_t;

/* --- 电机运行方向 --- */
typedef enum {
    BSP_MOTOR_DIR_STOP    = 0,
    BSP_MOTOR_DIR_FORWARD = 1,
    BSP_MOTOR_DIR_REVERSE = 2
} bsp_motor_dir_t;

/* --- 霍尔编码器电机对象 --- */
typedef struct {
    bsp_motor_gpio_t dir_pin1;
    bsp_motor_gpio_t dir_pin2;
    void     *pwm_timer;
    uint32_t  pwm_channel;

    int32_t current_pwm;
    int32_t encoder_speed;
    int32_t total_position;

    void    (*Gpio_Config)(void);
    void    (*Init)(void);
    void    (*Gpio_Write)(void *port, uint32_t pin, uint8_t level);
    void    (*Pwm_Write)(void *timer, uint32_t channel, uint32_t duty);
    int32_t (*Enc_Read)(void);
} bsp_motor_t;

void BSP_Motor_Init_Device(bsp_motor_t *motor);
void BSP_Motor_Set_Speed(bsp_motor_t *motor, int32_t speed_val);
void BSP_Motor_Update_Status(bsp_motor_t *motor);

#endif /* __BSP_ENCODER_MOTOR_H__ */
