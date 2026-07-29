/**
 * @file    bsp_all.h
 * @brief   BSP 统一包含头文件 — 业务层只需包含此文件
 */
#ifndef __BSP_ALL_H__
#define __BSP_ALL_H__

/* 公共基础设施 */
#include "bsp_common.h"

/* 硬件驱动层 (BSP) */
#include "bsp_led.h"
#include "bsp_key.h"
#include "bsp_uart.h"
#include "bsp_servo.h"
#include "bsp_encoder_motor.h"
#include "bsp_stepper.h"
#include "bsp_sw_i2c.h"
#include "bsp_mpu6050.h"

/* 硬件绑定层 (APP_HW) */
#include "app_led.h"
#include "app_key.h"
#include "app_servo.h"
#include "app_encoder_motor.h"
#include "app_stepper.h"
#include "app_mpu6050.h"

#endif /* __BSP_ALL_H__ */
