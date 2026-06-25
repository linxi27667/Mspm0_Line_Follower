/**
 * @file    track.h
 * @brief   灰度PID循迹任务调度层（TASK层 — 纯业务逻辑）
 * @note    传感器布局: S0 S1 S2 S3 S4 S5 S6 S7（左→右）
 *          偏差权重:   -3.5 -2.5 -1.5 -0.5 +0.5 +1.5 +2.5 +3.5
 *          负偏差=偏左(需右转)  正偏差=偏右(需左转)
 *
 *          架构:
 *          BSP层: bsp_grayscale / bsp_pid / bsp_mpu6050 / bsp_encoder_motor
 *          APP层: app_grayscale / app_mpu6050 / app_encoder_motor
 *          TASK层: 本文件 — 只写业务逻辑，不碰任何硬件寄存器
 */
#ifndef __TRACK_H__
#define __TRACK_H__

#include <stdint.h>
#include <stdbool.h>
#include "app_pid.h"
#include "app_grayscale.h"
#include "app_mpu6050.h"
#include "app_encoder_motor.h"

/* ============================================================
 * 循迹调度宏定义
 * ============================================================ */

/* 循迹状态机更新周期(ms) */
#define TRACK_UPDATE_PERIOD_MS    5

/* --- 直角弯道检测 --- */
#define TRACK_RIGHT_ANGLE_THRESHOLD       2.5f
#define TRACK_RIGHT_ANGLE_CONFIRM_FRAMES  3
#define TRACK_RIGHT_ANGLE_TIMEOUT         1000
#define TRACK_RIGHT_ANGLE_DONE_ERR        5.0f

/* --- 十字路口检测 --- */
#define TRACK_CROSS_MIN_BLACK             4
#define TRACK_CROSS_PASS_COUNT            60

/* --- 起点线检测 --- */
#define TRACK_START_LINE_MIN_BLACK        6
#define TRACK_START_LINE_COUNT            100

/* --- 丢线检测 --- */
#define TRACK_LINE_LOST_MAX_BLACK         1
#define TRACK_LINE_LOST_TIMEOUT           500
#define TRACK_LINE_LOST_GAIN              2.0f

/* --- 变速策略 --- */
#define TRACK_SPEED_STRAIGHT              60
#define TRACK_SPEED_CURVE                 35
#define TRACK_SPEED_SWITCH_ERR            1.0f
#define TRACK_SPEED_RAMP_STEP             2

/* --- 电机差速 --- */
#define TRACK_MOTOR_INNER_MIN             0
#define TRACK_MOTOR_SPEED_MAX             100
#define TRACK_MOTOR_SPEED_MIN             (-100)

/* --- 偏差计算 --- */
#define TRACK_ERROR_MIN_DENOM             0.01f

/* --- 默认参数 --- */
#define TRACK_DEFAULT_BASE_SPEED          40
#define TRACK_DEFAULT_CIRCLES             1

/* 循迹PID默认参数（需实测调优） */
#define TRACK_LINE_PID_KP        8.0f
#define TRACK_LINE_PID_KI        0.0f
#define TRACK_LINE_PID_KD        1.5f
#define TRACK_LINE_PID_ILIMIT    50.0f
#define TRACK_LINE_PID_OLIMIT    40.0f
#define TRACK_LINE_PID_DERIV_ALPHA 0.6f   /* 不完全微分系数 */

/* 陀螺仪PID默认参数 */
#define TRACK_GYRO_PID_KP        3.0f
#define TRACK_GYRO_PID_KI        0.0f
#define TRACK_GYRO_PID_KD        0.5f
#define TRACK_GYRO_PID_ILIMIT    30.0f
#define TRACK_GYRO_PID_OLIMIT    40.0f

/* ============================================================
 * 循迹状态机
 * ============================================================ */
typedef enum {
    TRACK_STATE_IDLE = 0,           /* 空闲 */
    TRACK_STATE_LINE_FOLLOW,        /* 正常循迹 */
    TRACK_STATE_RIGHT_ANGLE,        /* 直角弯道 */
    TRACK_STATE_LINE_LOST,          /* 丢线，陀螺仪维持航向 */
    TRACK_STATE_START_LINE,         /* 起点线（全黑） */
    TRACK_STATE_CROSS,              /* 十字路口 */
    TRACK_STATE_FINISHED            /* 完成所有圈数 */
} track_state_t;

/* ============================================================
 * 循迹调度对象 — 只包含状态机和输出（纯业务数据）
 * ============================================================ */
typedef struct {
    /* --- 偏差计算 --- */
    float    error;                 /* 加权偏差 */
    float    last_error;            /* 上次偏差 */

    /* --- 状态机 --- */
    track_state_t state;
    track_state_t last_state;
    float    target_heading;        /* 丢线时的目标航向 */
    float    right_angle_target;    /* 直角弯道目标角度 */
    uint32_t state_timer;           /* 状态计时 */
    uint32_t line_lost_count;       /* 丢线计数 */

    /* --- 直角弯道多帧确认 --- */
    uint8_t  right_angle_confirm;   /* 直角弯连续确认计数 */

    /* --- 圈数 --- */
    uint8_t  target_circles;
    uint8_t  current_circle;

    /* --- PID（使用BSP层 bsp_pid_t） --- */
    bsp_pid_t line_pid;             /* 循迹位置PID */
    bsp_pid_t gyro_pid;             /* 陀螺仪航向PID */

    /* --- 输出 --- */
    float    turn_output;           /* 转向量(正=左转,负=右转) */
    int32_t  left_speed;            /* 左电机速度 */
    int32_t  right_speed;           /* 右电机速度 */
    int32_t  base_speed;            /* 当前基础速度（渐变） */
    int32_t  target_speed;          /* 目标基础速度（由变速策略决定） */

    /* --- 配置 --- */
    bool     use_gyro;              /* 是否启用陀螺仪融合 */
    bool     use_motor;             /* 是否输出到电机 */
} track_t;

/* ============================================================
 * 全局对象
 * ============================================================ */
extern track_t Track;

/* ============================================================
 * 对外接口（主循环调度）
 * ============================================================ */
void Track_Init(void);                  /* 初始化所有硬件+状态 */
void Track_Update(void);                /* 主循环调用，非阻塞，内部5ms周期 */
void Track_Start(void);                 /* 启动循迹 */
void Track_Stop(void);                  /* 停止循迹 */
void Track_Set_Circles(uint8_t n);      /* 设置目标圈数 */
void Track_Set_Speed(int32_t base_speed); /* 设置基础速度 */
void Track_Set_TrackPID(float kp, float ki, float kd); /* 调循迹PID */
void Track_Calibrate_White(void);       /* 白纸校准 */
void Track_Calibrate_Black(void);       /* 黑纸校准 */
track_state_t Track_Get_State(void);    /* 获取当前状态 */
uint8_t Track_Get_Circle(void);         /* 获取当前圈数 */

#endif /* __TRACK_H__ */
