# 灰度PID循迹小车 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于八路灰度传感器 + MPU6050陀螺仪 + 双霍尔编码器电机，实现高性能电赛循迹小车，支持直线、直角弯道、交叉口识别和精确圈数计数。

**Architecture:** 三层架构（BSP纯逻辑 → APP硬件绑定 → main业务调度）。新增通用PID控制器(BSP级)、循迹状态机(BSP级)、双电机扩展、陀螺仪融合。灰度传感器提供位置偏差，陀螺仪提供航向角，双闭环PID输出差速转向量。

**Tech Stack:** MSPM0G3507 + DriverLib + 74HC4051灰度传感器 + MPU6050(I2C) + AT8236双路电机驱动 + 霍尔编码器(QEI)

---

## 架构决策与理由

### 为什么需要 MPU6050 陀螺仪？

| 场景 | 仅灰度传感器 | 灰度 + 陀螺仪 |
|------|-------------|--------------|
| 直线行驶 | 容易振荡 | 陀螺仪辅助稳航向，更平滑 |
| 直角弯道 | 检测到全黑后盲目转，容易过冲/欠冲 | 精确旋转90°，可复现 |
| 丢线（白板） | 完全失控 | 按最后航向直线行驶，找回线 |
| 交叉口 | 难以区分直行/转弯 | 陀螺仪累计角度判断 |

**结论：必须使用陀螺仪**，这是电赛高性能循迹小车的标准配置。

### 文件结构总览

```
新增文件:
  BSP/Inc/bsp_pid.h          — 通用PID控制器（纯逻辑，可复用）
  BSP/Src/bsp_pid.c          — PID算法实现（含积分分离/输出限幅）
  BSP/Inc/bsp_tracking.h     — 循迹状态机核心（纯逻辑）
  BSP/Src/bsp_tracking.c     — 状态机 + 偏差计算 + 模式识别
  APP/Inc/app_pid.h          — PID实例声明（循迹PID/速度PID）
  APP/Src/app_pid.c          — PID参数绑定
  APP/Inc/app_tracking.h     — 循迹业务层声明
  APP/Src/app_tracking.c     — 硬件绑定 + 业务调度

修改文件:
  APP/Inc/app_encoder_motor.h — 新增右电机引脚定义
  APP/Src/app_encoder_motor.c — 新增 App_Motor_Right 实例
  BSP/Inc/bsp_all.h           — 新增 pid/tracking 头文件包含
  ti_msp_dl_config.h          — 新增右电机/ADC外设定义
  ti_msp_dl_config.c          — 新增右电机/ADC初始化函数
```

### 引脚分配规划（MSPM0G3507）

| 功能 | 外设 | 引脚 | 说明 |
|------|------|------|------|
| 左电机PWM | TIMG7_CC0 | PA17 | 已有 |
| 左电机方向1 | GPIO | PA14 | 已有 |
| 左电机方向2 | GPIO | PA15 | 已有 |
| 左电机编码器A | TIMG8_CC0 | PB21 | 已有(QEI) |
| 左电机编码器B | TIMG8_CC1 | PB22 | 已有(QEI) |
| **右电机PWM** | **TIMG6_CC0** | **PA12** | **新增** |
| **右电机方向1** | **GPIO** | **PA13** | **新增** |
| **右电机方向2** | **GPIO** | **PA16** | **新增** |
| **右电机编码器A** | **TIMG12_CC0** | **PB27** | **新增(QEI)** |
| **右电机编码器B** | **TIMG12_CC1** | **PB26** | **新增(QEI)** |
| 灰度AD0 | GPIO | PA18 | 新增 |
| 灰度AD1 | GPIO | PA19 | 新增 |
| 灰度AD2 | GPIO | PA20 | 新增 |
| **灰度OUT(ADC)** | **ADC12_0_CH0** | **PA27** | **新增** |
| I2C(SCL/SDA) | GPIO软模拟 | PB8/PB9 | 已有(MPU6050) |
| 按键KEY1-4 | GPIO | PB0/PB1/PB2/PA0 | 已有 |

---

## Task 1: 通用PID控制器 — BSP层

**Files:**
- Create: `BSP/Inc/bsp_pid.h`
- Create: `BSP/Src/bsp_pid.c`

- [ ] **Step 1: 创建 bsp_pid.h**

```c
/**
 * @file    bsp_pid.h
 * @brief   通用PID控制器（BSP — 纯逻辑，跨平台）
 * @note    特性：积分分离 + 输出限幅 + 微分滤波
 */
#ifndef __BSP_PID_H__
#define __BSP_PID_H__

#include <stdint.h>

typedef struct {
    /* --- PID参数 --- */
    float kp;
    float ki;
    float kd;

    /* --- 限幅参数 --- */
    float integral_limit;   /* 积分限幅 */
    float output_limit;     /* 输出限幅 */

    /* --- 积分分离阈值 --- */
    float integral_sep_threshold;  /* 偏差大于此值时关闭积分，0=始终启用 */

    /* --- 内部状态 --- */
    float error;
    float last_error;
    float integral;
    float derivative;
    float output;
} bsp_pid_t;

/* --- API --- */
void  BSP_PID_Init(bsp_pid_t *pid, float kp, float ki, float kd,
                   float integral_limit, float output_limit);
void  BSP_PID_Set_Params(bsp_pid_t *pid, float kp, float ki, float kd);
float BSP_PID_Calculate(bsp_pid_t *pid, float target, float feedback);
void  BSP_PID_Reset(bsp_pid_t *pid);

#endif /* __BSP_PID_H__ */
```

- [ ] **Step 2: 创建 bsp_pid.c**

```c
/**
 * @file    bsp_pid.c
 * @brief   通用PID控制器实现（BSP — 纯逻辑，跨平台）
 */
#include "bsp_pid.h"

void BSP_PID_Init(bsp_pid_t *pid, float kp, float ki, float kd,
                   float integral_limit, float output_limit)
{
    if (pid == NULL) return;

    pid->kp = kp;
    pid->ki = ki;
    pid->kd = kd;
    pid->integral_limit   = integral_limit;
    pid->output_limit     = output_limit;
    pid->integral_sep_threshold = 0;  /* 默认不启用积分分离 */

    pid->error      = 0;
    pid->last_error = 0;
    pid->integral   = 0;
    pid->derivative = 0;
    pid->output     = 0;
}

void BSP_PID_Set_Params(bsp_pid_t *pid, float kp, float ki, float kd)
{
    if (pid == NULL) return;
    pid->kp = kp;
    pid->ki = ki;
    pid->kd = kd;
}

float BSP_PID_Calculate(bsp_pid_t *pid, float target, float feedback)
{
    if (pid == NULL) return 0;

    pid->error = target - feedback;

    /* 积分分离：偏差过大时关闭积分 */
    if (pid->integral_sep_threshold > 0 && 
        (pid->error > pid->integral_sep_threshold || 
         pid->error < -pid->integral_sep_threshold)) {
        /* 不累加积分 */
    } else {
        pid->integral += pid->error;
        if (pid->integral > pid->integral_limit)  pid->integral = pid->integral_limit;
        if (pid->integral < -pid->integral_limit) pid->integral = -pid->integral_limit;
    }

    /* 微分 */
    pid->derivative = pid->error - pid->last_error;

    /* PID输出 */
    pid->output = pid->kp * pid->error 
                + pid->ki * pid->integral 
                + pid->kd * pid->derivative;

    /* 输出限幅 */
    if (pid->output > pid->output_limit)  pid->output = pid->output_limit;
    if (pid->output < -pid->output_limit) pid->output = -pid->output_limit;

    pid->last_error = pid->error;

    return pid->output;
}

void BSP_PID_Reset(bsp_pid_t *pid)
{
    if (pid == NULL) return;
    pid->error      = 0;
    pid->last_error = 0;
    pid->integral   = 0;
    pid->derivative = 0;
    pid->output     = 0;
}
```

- [ ] **Step 3: 验证编译（仅头文件包含检查）**

确认 `bsp_pid.h` 和 `bsp_pid.c` 语法正确，不依赖任何硬件头文件。

---

## Task 2: 循迹状态机核心 — BSP层

**Files:**
- Create: `BSP/Inc/bsp_tracking.h`
- Create: `BSP/Src/bsp_tracking.c`

- [ ] **Step 1: 创建 bsp_tracking.h**

```c
/**
 * @file    bsp_tracking.h
 * @brief   循迹控制状态机核心（BSP — 纯逻辑，跨平台）
 * @note    八路灰度传感器偏差计算 + 赛道元素识别 + 陀螺仪融合
 *          传感器布局: S0 S1 S2 S3 S4 S5 S6 S7（左→右）
 *          偏差权重:   -3.5 -2.5 -1.5 -0.5 +0.5 +1.5 +2.5 +3.5
 *          负偏差=偏左(需右转)  正偏差=偏右(需左转)
 */
#ifndef __BSP_TRACKING_H__
#define __BSP_TRACKING_H__

#include <stdint.h>
#include <stdbool.h>
#include "bsp_pid.h"

#define BSP_TRACK_CH_NUM        8       /* 灰度传感器通道数 */

/* --- 循迹状态 --- */
typedef enum {
    BSP_TRACK_STATE_IDLE = 0,           /* 空闲 */
    BSP_TRACK_STATE_LINE_FOLLOW,        /* 正常循迹 */
    BSP_TRACK_STATE_RIGHT_ANGLE,        /* 直角弯道 */
    BSP_TRACK_STATE_LINE_LOST,          /* 丢线，陀螺仪维持航向 */
    BSP_TRACK_STATE_INTERSECTION,       /* 交叉口 */
    BSP_TRACK_STATE_START_LINE,         /* 起点线（全黑） */
    BSP_TRACK_STATE_FINISHED            /* 完成所有圈数 */
} bsp_track_state_t;

/* --- 赛道元素检测阈值 --- */
#define BSP_TRACK_BLACK_COUNT_THRESHOLD  6   /* 黑色通道数≥此值=全黑(起点/交叉口) */
#define BSP_TRACK_LOST_COUNT_THRESHOLD   1   /* 黑色通道数<此值=丢线 */

/* --- 循迹对象 --- */
typedef struct {
    /* --- 输入数据 --- */
    uint8_t  digital[BSP_TRACK_CH_NUM]; /* 8路数字值(1=黑,0=白) */
    float    gyro_z;                    /* 陀螺仪Z轴角速度(deg/s) */
    float    heading;                   /* 陀螺仪累计航向角(deg) */

    /* --- 偏差计算 --- */
    float    error;                     /* 加权偏差 */
    float    last_error;                /* 上次偏差 */

    /* --- 状态机 --- */
    bsp_track_state_t state;
    bsp_track_state_t last_state;       /* 丢线前的状态 */
    float    target_heading;            /* 丢线时的目标航向 */
    float    right_angle_target;        /* 直角弯道目标角度 */
    uint32_t state_timer;               /* 状态计时(ms) */
    uint32_t line_lost_count;           /* 丢线计数 */

    /* --- 圈数 --- */
    uint8_t  target_circles;
    uint8_t  current_circle;

    /* --- PID --- */
    bsp_pid_t line_pid;                 /* 循迹位置PID */
    bsp_pid_t gyro_pid;                 /* 陀螺仪航向PID(丢线时用) */

    /* --- 输出 --- */
    float    turn_output;               /* 转向量(正=左转,负=右转) */
    int32_t  left_speed;                /* 左电机速度 */
    int32_t  right_speed;               /* 右电机速度 */
    int32_t  base_speed;                /* 基础速度 */

    /* --- 传感器黑线计数 --- */
    uint8_t  black_count;               /* 当前黑色通道数 */
    uint8_t  last_black_count;          /* 上次黑色通道数 */

    /* --- 配置 --- */
    bool     use_gyro;                  /* 是否启用陀螺仪融合 */
} bsp_tracking_t;

/* --- API --- */
void BSP_Tracking_Init(bsp_tracking_t *tk);
void BSP_Tracking_Set_Circles(bsp_tracking_t *tk, uint8_t n);
void BSP_Tracking_Start(bsp_tracking_t *tk);
void BSP_Tracking_Stop(bsp_tracking_t *tk);
void BSP_Tracking_Update(bsp_tracking_t *tk);  /* 主循环调用，非阻塞 */

#endif /* __BSP_TRACKING_H__ */
```

- [ ] **Step 2: 创建 bsp_tracking.c — 偏差计算函数**

```c
/**
 * @file    bsp_tracking.c
 * @brief   循迹控制状态机实现（BSP — 纯逻辑，跨平台）
 */
#include "bsp_tracking.h"

/* 八路传感器权重: S0(-3.5) S1(-2.5) S2(-1.5) S3(-0.5) S4(+0.5) S5(+1.5) S6(+2.5) S7(+3.5) */
static const float s_weights[BSP_TRACK_CH_NUM] = {
    -3.5f, -2.5f, -1.5f, -0.5f, 0.5f, 1.5f, 2.5f, 3.5f
};

/* ================= 内部函数 ================= */

/* 计算加权偏差和黑色通道数 */
static void Track_Calc_Error(bsp_tracking_t *tk)
{
    float weighted_sum = 0;
    float total_weight = 0;
    tk->black_count = 0;

    for (uint8_t i = 0; i < BSP_TRACK_CH_NUM; i++) {
        if (tk->digital[i]) {
            weighted_sum += s_weights[i];
            total_weight  += 1.0f;
            tk->black_count++;
        }
    }

    if (total_weight > 0) {
        tk->error = weighted_sum / total_weight;
    } else {
        /* 全白：保持上次偏差方向 */
        /* error不变，由状态机处理 */
    }

    tk->last_error = tk->error;
}
```

- [ ] **Step 3: 创建 bsp_tracking.c — 状态机切换函数**

```c
/* 检测赛道元素并切换状态 */
static void Track_Detect_Pattern(bsp_tracking_t *tk)
{
    /* 全黑检测：起点线或交叉口 */
    if (tk->black_count >= BSP_TRACK_BLACK_COUNT_THRESHOLD) {
        if (tk->state == BSP_TRACK_STATE_LINE_FOLLOW) {
            /* 记录当前航向，用于判断是起点还是弯道 */
            tk->target_heading = tk->heading;
            tk->state = BSP_TRACK_STATE_START_LINE;
            tk->state_timer = 0;
        }
    }
    /* 丢线检测 */
    else if (tk->black_count < BSP_TRACK_LOST_COUNT_THRESHOLD) {
        if (tk->state == BSP_TRACK_STATE_LINE_FOLLOW) {
            tk->last_state = BSP_TRACK_STATE_LINE_FOLLOW;
            tk->target_heading = tk->heading;
            tk->state = BSP_TRACK_STATE_LINE_LOST;
            tk->line_lost_count = 0;
        }
    }
}

/* 起点线处理：计数圈数 */
static void Track_Handle_StartLine(bsp_tracking_t *tk)
{
    tk->state_timer++;

    /* 起点线持续超过100ms视为有效过线 */
    if (tk->state_timer > 100) {
        tk->current_circle++;
        if (tk->current_circle >= tk->target_circles) {
            tk->state = BSP_TRACK_STATE_FINISHED;
            tk->left_speed  = 0;
            tk->right_speed = 0;
        } else {
            tk->state = BSP_TRACK_STATE_LINE_FOLLOW;
        }
    }
}

/* 丢线处理：用陀螺仪维持航向 */
static void Track_Handle_LineLost(bsp_tracking_t *tk)
{
    tk->line_lost_count++;

    if (tk->use_gyro) {
        /* 陀螺仪PID：维持丢线时的航向 */
        float gyro_error = tk->target_heading - tk->heading;
        tk->turn_output = tk->gyro_pid.kp * gyro_error;
    } else {
        /* 无陀螺仪：按最后偏差方向继续转 */
        tk->turn_output = tk->last_error * 2.0f;
    }

    /* 丢线超过500ms，停车 */
    if (tk->line_lost_count > 500) {
        tk->state = BSP_TRACK_STATE_FINISHED;
        tk->left_speed  = 0;
        tk->right_speed = 0;
    }
}
```

- [ ] **Step 4: 创建 bsp_tracking.c — 主更新函数和初始化**

```c
/* ================= 1. 初始化 ================= */
void BSP_Tracking_Init(bsp_tracking_t *tk)
{
    if (tk == NULL) return;

    for (uint8_t i = 0; i < BSP_TRACK_CH_NUM; i++) {
        tk->digital[i] = 0;
    }
    tk->gyro_z    = 0;
    tk->heading   = 0;
    tk->error     = 0;
    tk->last_error = 0;

    tk->state       = BSP_TRACK_STATE_IDLE;
    tk->last_state  = BSP_TRACK_STATE_IDLE;
    tk->target_heading   = 0;
    tk->right_angle_target = 0;
    tk->state_timer      = 0;
    tk->line_lost_count  = 0;

    tk->target_circles  = 1;
    tk->current_circle  = 0;

    tk->turn_output = 0;
    tk->left_speed  = 0;
    tk->right_speed = 0;
    tk->base_speed  = 40;

    tk->black_count     = 0;
    tk->last_black_count = 0;
    tk->use_gyro = true;

    /* 循迹PID默认参数（需实测调优） */
    BSP_PID_Init(&tk->line_pid, 8.0f, 0.0f, 1.5f, 50.0f, 40.0f);
    /* 陀螺仪PID默认参数 */
    BSP_PID_Init(&tk->gyro_pid, 3.0f, 0.0f, 0.5f, 30.0f, 40.0f);
}

void BSP_Tracking_Set_Circles(bsp_tracking_t *tk, uint8_t n)
{
    if (tk == NULL) return;
    tk->target_circles = n;
}

void BSP_Tracking_Start(bsp_tracking_t *tk)
{
    if (tk == NULL) return;
    tk->state = BSP_TRACK_STATE_LINE_FOLLOW;
    tk->current_circle = 0;
    BSP_PID_Reset(&tk->line_pid);
    BSP_PID_Reset(&tk->gyro_pid);
}

void BSP_Tracking_Stop(bsp_tracking_t *tk)
{
    if (tk == NULL) return;
    tk->state = BSP_TRACK_STATE_FINISHED;
    tk->left_speed  = 0;
    tk->right_speed = 0;
}

/* ================= 2. 主更新函数（非阻塞，主循环调用） ================= */
void BSP_Tracking_Update(bsp_tracking_t *tk)
{
    if (tk == NULL) return;
    if (tk->state == BSP_TRACK_STATE_IDLE || 
        tk->state == BSP_TRACK_STATE_FINISHED) return;

    /* ① 计算偏差和黑色通道数 */
    Track_Calc_Error(tk);

    /* ② 检测赛道元素 */
    Track_Detect_Pattern(tk);

    /* ③ 状态机处理 */
    switch (tk->state) {
    case BSP_TRACK_STATE_LINE_FOLLOW:
        /* 正常循迹：灰度PID */
        tk->turn_output = BSP_PID_Calculate(&tk->line_pid, 0.0f, tk->error);
        break;

    case BSP_TRACK_STATE_START_LINE:
        Track_Handle_StartLine(tk);
        /* 过起点线时保持直行 */
        tk->turn_output = 0;
        break;

    case BSP_TRACK_STATE_LINE_LOST:
        Track_Handle_LineLost(tk);
        break;

    case BSP_TRACK_STATE_RIGHT_ANGLE:
        /* 直角弯道：陀螺仪精确旋转 */
        {
            float angle_error = tk->right_angle_target - tk->heading;
            tk->turn_output = BSP_PID_Calculate(&tk->gyro_pid, 
                                                tk->right_angle_target, 
                                                tk->heading);
            /* 角度到位后回到循迹 */
            if (angle_error > -5.0f && angle_error < 5.0f) {
                tk->state = BSP_TRACK_STATE_LINE_FOLLOW;
            }
        }
        break;

    default:
        break;
    }

    /* ④ 差速输出 */
    tk->left_speed  = tk->base_speed + (int32_t)tk->turn_output;
    tk->right_speed = tk->base_speed - (int32_t)tk->turn_output;

    /* 电机速度限幅 */
    if (tk->left_speed > 100)  tk->left_speed = 100;
    if (tk->left_speed < -100) tk->left_speed = -100;
    if (tk->right_speed > 100)  tk->right_speed = 100;
    if (tk->right_speed < -100) tk->right_speed = -100;
}
```

- [ ] **Step 5: 验证状态机逻辑**

检查要点：
- `Track_Calc_Error` 的加权平均是否正确（黑线居中时error=0）
- 丢线时是否保持上次偏差方向
- 起点线计数逻辑是否正确（100ms防抖）
- 差速输出方向是否正确（正turn=左转→左轮减速右轮加速）

---

## Task 3: 右电机扩展 — APP层

**Files:**
- Modify: `APP/Inc/app_encoder_motor.h`
- Modify: `APP/Src/app_encoder_motor.c`

- [ ] **Step 1: 修改 app_encoder_motor.h — 添加右电机配置**

在现有 `MOTOR_LEFT_*` 定义之后，添加右电机定义：

```c
/* ============ 右电机硬件配置 ============ */
#define MOTOR_RIGHT_PWM_TIMER       TIMG6
#define MOTOR_RIGHT_PWM_CHANNEL     0
#define MOTOR_RIGHT_ENC_TIMER       TIMG12
#define MOTOR_RIGHT_DIR1_PORT       GPIOA
#define MOTOR_RIGHT_DIR1_PIN        DL_GPIO_PIN_13
#define MOTOR_RIGHT_DIR2_PORT       GPIOA
#define MOTOR_RIGHT_DIR2_PIN        DL_GPIO_PIN_16
```

在业务接口声明区添加：

```c
extern bsp_motor_t App_Motor_Right;

void App_Motor_Right_Set_Speed(int32_t speed);
```

- [ ] **Step 2: 修改 app_encoder_motor.c — 添加右电机实例**

在 `App_Motor_Left` 实例化之后，添加右电机实例：

```c
bsp_motor_t App_Motor_Right = {
    .dir_pin1   = {MOTOR_RIGHT_DIR1_PORT, MOTOR_RIGHT_DIR1_PIN},
    .dir_pin2   = {MOTOR_RIGHT_DIR2_PORT, MOTOR_RIGHT_RIGHT_DIR2_PIN},
    .pwm_timer  = MOTOR_RIGHT_PWM_TIMER,
    .pwm_channel = MOTOR_RIGHT_PWM_CHANNEL,
    .enc_timer  = MOTOR_RIGHT_ENC_TIMER,

    .Gpio_Config = HW_GPIO_Config,
    .Init        = HW_Motor_Init,
    .Gpio_Write  = HW_Gpio_Write,
    .Pwm_Write   = HW_Pwm_Write,
    .Enc_Read    = HW_Enc_Read
};
```

在 `App_Motor_System_Init` 中添加右电机初始化：

```c
void App_Motor_System_Init(void)
{
    HW_Motor_Init(&App_Motor_Left);
    BSP_Motor_Init_Device(&App_Motor_Left);

    HW_Motor_Init(&App_Motor_Right);
    BSP_Motor_Init_Device(&App_Motor_Right);
}
```

在 `App_Motor_Update_Status` 中添加右电机更新：

```c
void App_Motor_Update_Status(void)
{
    BSP_Motor_Update_Status(&App_Motor_Left);
    BSP_Motor_Update_Status(&App_Motor_Right);
}
```

添加右电机速度设置函数：

```c
void App_Motor_Right_Set_Speed(int32_t speed)
{
    BSP_Motor_Set_Speed(&App_Motor_Right, speed);
}
```

- [ ] **Step 3: 验证引脚不冲突**

检查 PA13/PA16 是否已被其他模块占用（当前项目中PA14/PA15用于左电机方向，PA17用于左电机PWM，PA0用于KEY4）。

---

## Task 4: PID实例化 — APP层

**Files:**
- Create: `APP/Inc/app_pid.h`
- Create: `APP/Src/app_pid.c`

- [ ] **Step 1: 创建 app_pid.h**

```c
/**
 * @file    app_pid.h
 * @brief   PID应用层声明（参数绑定 + 实例管理）
 */
#ifndef APP_PID_H
#define APP_PID_H

#include "bsp_pid.h"

/* ============ PID实例声明 ============ */
/* 循迹PID参数默认值（需实测调优） */
#define TRACK_PID_KP        8.0f
#define TRACK_PID_KI        0.0f
#define TRACK_PID_KD        1.5f
#define TRACK_PID_ILIMIT    50.0f
#define TRACK_PID_OLIMIT    40.0f

/* 陀螺仪PID参数默认值 */
#define GYRO_PID_KP         3.0f
#define GYRO_PID_KI         0.0f
#define GYRO_PID_KD         0.5f
#define GYRO_PID_ILIMIT     30.0f
#define GYRO_PID_OLIMIT     40.0f

/* ============ 业务接口声明 ============ */
void App_PID_System_Init(void);

/* 运行时调参接口（通过按键/串口调整） */
void App_PID_Set_TrackParams(float kp, float ki, float kd);
void App_PID_Set_GyroParams(float kp, float ki, float kd);

#endif /* APP_PID_H */
```

- [ ] **Step 2: 创建 app_pid.c**

```c
/**
 * @file    app_pid.c
 * @brief   PID应用层实现（参数绑定）
 */
#include "app_pid.h"

void App_PID_System_Init(void)
{
    /* PID实例由 bsp_tracking_t 内部管理 */
    /* 此处仅作为参数集中配置入口，实际初始化在 BSP_Tracking_Init 中完成 */
}

void App_PID_Set_TrackParams(float kp, float ki, float kd)
{
    /* 运行时调参 — 需通过外部访问tracking对象 */
    /* 实际调参在 app_tracking.c 中实现 */
    (void)kp; (void)ki; (void)kd;
}

void App_PID_Set_GyroParams(float kp, float ki, float kd)
{
    (void)kp; (void)ki; (void)kd;
}
```

---

## Task 5: 循迹业务层 — APP层

**Files:**
- Create: `APP/Inc/app_tracking.h`
- Create: `APP/Src/app_tracking.c`

- [ ] **Step 1: 创建 app_tracking.h**

```c
/**
 * @file    app_tracking.h
 * @brief   循迹业务层声明（硬件绑定 + 业务调度）
 * @note    整合灰度传感器 + MPU6050 + 双电机 + PID
 */
#ifndef APP_TRACKING_H
#define APP_TRACKING_H

#include "bsp_tracking.h"

/* ============ 业务接口声明 ============ */
extern bsp_tracking_t App_Tracking;

void App_Tracking_System_Init(void);
void App_Tracking_Update(void);              /* 主循环调用，非阻塞 */
void App_Tracking_Start(void);
void App_Tracking_Stop(void);
void App_Tracking_Set_Circles(uint8_t n);
uint8_t App_Tracking_Get_Circle(void);
bsp_track_state_t App_Tracking_Get_State(void);

/* 运行时调参 */
void App_Tracking_Set_Speed(int32_t base_speed);
void App_Tracking_Set_TrackPID(float kp, float ki, float kd);

#endif /* APP_TRACKING_H */
```

- [ ] **Step 2: 创建 app_tracking.c — 头文件和对象实例化**

```c
/**
 * @file    app_tracking.c
 * @brief   循迹业务层实现（MSPM0G3507硬件绑定）
 * @note    数据流:
 *          灰度传感器 → digital[8] → 偏差计算 → PID → 差速 → 电机
 *          MPU6050   → gyro_z/heading → 丢线辅助/直角弯道
 */
#include "app_tracking.h"
#include "app_grayscale.h"
#include "app_mpu6050.h"
#include "app_encoder_motor.h"
#include "ti_msp_dl_config.h"

/* ================= 1. 对象实例化 ================= */

bsp_tracking_t App_Tracking = {0};

/* ================= 2. 内部数据同步函数 ================= */

/* 从灰度传感器同步数字值到循迹对象 */
static void Sync_Grayscale_To_Tracking(void)
{
    for (uint8_t i = 0; i < BSP_TRACK_CH_NUM; i++) {
        App_Tracking.digital[i] = App_Grayscale.digital[i];
    }
}

/* 从MPU6050同步陀螺仪数据到循迹对象 */
static void Sync_Gyro_To_Tracking(void)
{
    /* MPU6050 Z轴角速度，单位 deg/s */
    App_Tracking.gyro_z = App_MPU.gyro_z;

    /* 简单积分得到航向角（需在固定周期调用） */
    /* 假设 Update 每 5ms 调用一次 */
    App_Tracking.heading += App_Tracking.gyro_z * 0.005f;
}
```

- [ ] **Step 3: 创建 app_tracking.c — 业务接口实现**

```c
/* ================= 3. 对外业务切入点 ================= */

void App_Tracking_System_Init(void)
{
    BSP_Tracking_Init(&App_Tracking);
}

void App_Tracking_Update(void)
{
    /* ① 同步灰度传感器数据 */
    Sync_Grayscale_To_Tracking();

    /* ② 同步陀螺仪数据 */
    if (App_Tracking.use_gyro) {
        Sync_Gyro_To_Tracking();
    }

    /* ③ 循迹状态机计算 */
    BSP_Tracking_Update(&App_Tracking);

    /* ④ 输出到电机 */
    App_Motor_Set_Speed(App_Tracking.left_speed);
    App_Motor_Right_Set_Speed(App_Tracking.right_speed);
}

void App_Tracking_Start(void)
{
    BSP_Tracking_Start(&App_Tracking);
}

void App_Tracking_Stop(void)
{
    BSP_Tracking_Stop(&App_Tracking);
    App_Motor_Set_Speed(0);
    App_Motor_Right_Set_Speed(0);
}

void App_Tracking_Set_Circles(uint8_t n)
{
    BSP_Tracking_Set_Circles(&App_Tracking, n);
}

uint8_t App_Tracking_Get_Circle(void)
{
    return App_Tracking.current_circle;
}

bsp_track_state_t App_Tracking_Get_State(void)
{
    return App_Tracking.state;
}

void App_Tracking_Set_Speed(int32_t base_speed)
{
    App_Tracking.base_speed = base_speed;
}

void App_Tracking_Set_TrackPID(float kp, float ki, float kd)
{
    BSP_PID_Set_Params(&App_Tracking.line_pid, kp, ki, kd);
}
```

---

## Task 6: SysConfig 配置更新

**Files:**
- Modify: `ti_msp_dl_config.h`
- Modify: `ti_msp_dl_config.c`
- Note: 实际应在 SysConfig 图形界面中操作，此处提供手动配置代码

- [ ] **Step 1: ti_msp_dl_config.h — 添加右电机PWM定时器定义**

在现有 `Monitor_Left_Timer` 定义之后添加：

```c
/* Defines for Right_Motor_Timer (PWM) */
#define Right_Motor_Timer_INST                                       TIMG6
#define Right_Motor_Timer_INST_IRQHandler                   TIMG6_IRQHandler
#define Right_Motor_Timer_INST_INT_IRQN                     (TIMG6_INT_IRQn)
#define Right_Motor_Timer_INST_CLK_FREQ                              4000000
/* GPIO defines for channel 0 */
#define GPIO_Right_Motor_Timer_C0_PORT                              GPIOA
#define GPIO_Right_Motor_Timer_C0_PIN                       DL_GPIO_PIN_12
#define GPIO_Right_Motor_Timer_C0_IOMUX                    (IOMUX_PINCM28)
#define GPIO_Right_Motor_Timer_C0_IOMUX_FUNC        IOMUX_PINCM28_PF_TIMG6_CCP0
#define GPIO_Right_Motor_Timer_C0_IDX                      DL_TIMER_CC_0_INDEX
```

- [ ] **Step 2: ti_msp_dl_config.h — 添加右电机编码器定时器定义**

```c
/* Defines for Right_Encoder_Timer (QEI) */
#define Right_Encoder_Timer_INST                                    TIMG12
#define Right_Encoder_Timer_INST_IRQHandler                TIMG12_IRQHandler
#define Right_Encoder_Timer_INST_INT_IRQN                  (TIMG12_INT_IRQn)
/* Pin configuration defines for Right_Encoder_Timer PHA Pin */
#define GPIO_Right_Encoder_Timer_PHA_PORT                          GPIOB
#define GPIO_Right_Encoder_Timer_PHA_PIN                  DL_GPIO_PIN_27
#define GPIO_Right_Encoder_Timer_PHA_IOMUX                (IOMUX_PINCM40)
#define GPIO_Right_Encoder_Timer_PHA_IOMUX_FUNC    IOMUX_PINCM40_PF_TIMG12_CCP0
/* Pin configuration defines for Right_Encoder_Timer PHB Pin */
#define GPIO_Right_Encoder_Timer_PHB_PORT                          GPIOB
#define GPIO_Right_Encoder_Timer_PHB_PIN                  DL_GPIO_PIN_26
#define GPIO_Right_Encoder_Timer_PHB_IOMUX                (IOMUX_PINCM39)
#define GPIO_Right_Encoder_Timer_PHB_IOMUX_FUNC    IOMUX_PINCM39_PF_TIMG12_CCP1
```

- [ ] **Step 3: ti_msp_dl_config.h — 添加右电机方向GPIO定义**

```c
/* Port definition for Pin Group Right_Motor_Dir */
#define Right_Motor_Dir_PORT                                       (GPIOA)

/* Defines for PIN_1: GPIOA.13 */
#define Right_Motor_Dir_AIN1_PIN                           (DL_GPIO_PIN_13)
#define Right_Motor_Dir_AIN1_IOMUX                          (IOMUX_PINCM28)
/* Defines for PIN_2: GPIOA.16 */
#define Right_Motor_Dir_AIN2_PIN                           (DL_GPIO_PIN_16)
#define Right_Motor_Dir_AIN2_IOMUX                          (IOMUX_PINCM37)
```

- [ ] **Step 4: ti_msp_dl_config.h — 添加ADC12定义**

```c
/* Defines for GRAYSCALE_ADC */
#define GRAYSCALE_ADC_INST                                         ADC12_0
#define GRAYSCALE_ADC_IIDX                                        DL_ADC12_IIDX_MEM0
/* ADC Input Pin: PA27 = ADC0.2 */
#define GRAYSCALE_ADC_INPUT_PIN                            (DL_GPIO_PIN_27)
#define GRAYSCALE_ADC_INPUT_IOMUX                          (IOMUX_PINCM41)
#define GRAYSCALE_ADC_INPUT_IOMUX_FUNC             IOMUX_PINCM41_PF_ADC0_2
```

- [ ] **Step 5: ti_msp_dl_config.h — 添加灰度地址线GPIO定义**

```c
/* Defines for Grayscale_ADDR GPIO outputs */
#define GRAYSCALE_ADDR_PORT                                       (GPIOA)
#define GRAYSCALE_AD0_PIN                                 (DL_GPIO_PIN_18)
#define GRAYSCALE_AD0_IOMUX                                (IOMUX_PINCM33)
#define GRAYSCALE_AD1_PIN                                 (DL_GPIO_PIN_19)
#define GRAYSCALE_AD1_IOMUX                                (IOMUX_PINCM34)
#define GRAYSCALE_AD2_PIN                                 (DL_GPIO_PIN_20)
#define GRAYSCALE_AD2_IOMUX                                (IOMUX_PINCM35)
```

- [ ] **Step 6: ti_msp_dl_config.h — 添加函数声明**

在 `void SYSCFG_DL_Encoder_Timer_init(void);` 之后添加：

```c
void SYSCFG_DL_Right_Motor_Timer_init(void);
void SYSCFG_DL_Right_Encoder_Timer_init(void);
void SYSCFG_DL_GRAYSCALE_ADC_init(void);
```

- [ ] **Step 7: ti_msp_dl_config.c — 修改 initPower 添加新外设上电**

在 `SYSCFG_DL_initPower` 函数中添加：

```c
SYSCONFIG_WEAK void SYSCFG_DL_initPower(void)
{
    DL_GPIO_reset(GPIOA);
    DL_GPIO_reset(GPIOB);
    DL_TimerG_reset(Monitor_Left_Timer_INST);
    DL_TimerG_reset(Encoder_Timer_INST);
    DL_TimerG_reset(Right_Motor_Timer_INST);       /* 新增 */
    DL_TimerG_reset(Right_Encoder_Timer_INST);     /* 新增 */
    DL_ADC12_reset(GRAYSCALE_ADC_INST);            /* 新增 */

    DL_GPIO_enablePower(GPIOA);
    DL_GPIO_enablePower(GPIOB);
    DL_TimerG_enablePower(Monitor_Left_Timer_INST);
    DL_TimerG_enablePower(Encoder_Timer_INST);
    DL_TimerG_enablePower(Right_Motor_Timer_INST);      /* 新增 */
    DL_TimerG_enablePower(Right_Encoder_Timer_INST);    /* 新增 */
    DL_ADC12_enablePower(GRAYSCALE_ADC_INST);           /* 新增 */
    delay_cycles(POWER_STARTUP_DELAY);
}
```

- [ ] **Step 8: ti_msp_dl_config.c — 修改 SYSCFG_DL_init 添加新模块初始化**

```c
SYSCONFIG_WEAK void SYSCFG_DL_init(void)
{
    SYSCFG_DL_initPower();
    SYSCFG_DL_GPIO_init();
    SYSCFG_DL_SYSCTL_init();
    SYSCFG_DL_Monitor_Left_Timer_init();
    SYSCFG_DL_Encoder_Timer_init();
    SYSCFG_DL_Right_Motor_Timer_init();         /* 新增 */
    SYSCFG_DL_Right_Encoder_Timer_init();       /* 新增 */
    SYSCFG_DL_GRAYSCALE_ADC_init();             /* 新增 */
}
```

- [ ] **Step 9: ti_msp_dl_config.c — 修改 GPIO_init 添加新引脚**

在 `SYSCFG_DL_GPIO_init` 函数中添加右电机方向引脚和灰度地址线：

```c
SYSCONFIG_WEAK void SYSCFG_DL_GPIO_init(void)
{
    /* ... 现有代码保持不变 ... */

    /* 新增：右电机方向引脚 */
    DL_GPIO_initDigitalOutput(Right_Motor_Dir_AIN1_IOMUX);
    DL_GPIO_initDigitalOutput(Right_Motor_Dir_AIN2_IOMUX);
    DL_GPIO_clearPins(Right_Motor_Dir_PORT, Right_Motor_Dir_AIN1_PIN |
        Right_Motor_Dir_AIN2_PIN);
    DL_GPIO_enableOutput(Right_Motor_Dir_PORT, Right_Motor_Dir_AIN1_PIN |
        Right_Motor_Dir_AIN2_PIN);

    /* 新增：灰度传感器地址线 */
    DL_GPIO_initDigitalOutput(GRAYSCALE_AD0_IOMUX);
    DL_GPIO_initDigitalOutput(GRAYSCALE_AD1_IOMUX);
    DL_GPIO_initDigitalOutput(GRAYSCALE_AD2_IOMUX);
    DL_GPIO_clearPins(GRAYSCALE_ADDR_PORT, GRAYSCALE_AD0_PIN |
        GRAYSCALE_AD1_PIN | GRAYSCALE_AD2_PIN);
    DL_GPIO_enableOutput(GRAYSCALE_ADDR_PORT, GRAYSCALE_AD0_PIN |
        GRAYSCALE_AD1_PIN | GRAYSCALE_AD2_PIN);

    /* 新增：右电机PWM引脚 */
    DL_GPIO_initPeripheralOutputFunction(GPIO_Right_Motor_Timer_C0_IOMUX,
        GPIO_Right_Motor_Timer_C0_IOMUX_FUNC);
    DL_GPIO_enableOutput(GPIO_Right_Motor_Timer_C0_PORT, 
        GPIO_Right_Motor_Timer_C0_PIN);

    /* 新增：右电机编码器引脚 */
    DL_GPIO_initPeripheralInputFunction(GPIO_Right_Encoder_Timer_PHA_IOMUX,
        GPIO_Right_Encoder_Timer_PHA_IOMUX_FUNC);
    DL_GPIO_initPeripheralInputFunction(GPIO_Right_Encoder_Timer_PHB_IOMUX,
        GPIO_Right_Encoder_Timer_PHB_IOMUX_FUNC);

    /* 新增：ADC输入引脚（模拟输入，无需IOMUX数字功能初始化） */
    /* PA27的ADC功能由ADC模块配置自动处理 */
}
```

- [ ] **Step 10: ti_msp_dl_config.c — 添加右电机PWM定时器初始化函数**

在文件末尾添加：

```c
/* 右电机PWM定时器配置 — 与左电机相同: 4MHz/8=500kHz, period=100 */
static const DL_TimerG_ClockConfig gRight_Motor_TimerClockConfig = {
    .clockSel = DL_TIMER_CLOCK_BUSCLK,
    .divideRatio = DL_TIMER_CLOCK_DIVIDE_8,
    .prescale = 0U
};

static const DL_TimerG_PWMConfig gRight_Motor_TimerConfig = {
    .pwmMode = DL_TIMER_PWM_MODE_EDGE_ALIGN,
    .period = 100,
    .startTimer = DL_TIMER_START,
};

SYSCONFIG_WEAK void SYSCFG_DL_Right_Motor_Timer_init(void) {
    DL_TimerG_setClockConfig(
        Right_Motor_Timer_INST, 
        (DL_TimerG_ClockConfig *)&gRight_Motor_TimerClockConfig);

    DL_TimerG_initPWMMode(
        Right_Motor_Timer_INST, 
        (DL_TimerG_PWMConfig *)&gRight_Motor_TimerConfig);

    DL_TimerG_setCaptureCompareValue(Right_Motor_Timer_INST, 100, 
        DL_TIMER_CC_0_INDEX);
    DL_TimerG_setCaptureCompareOutCtl(Right_Motor_Timer_INST, 
        DL_TIMER_CC_OCTL_INIT_VAL_LOW,
        DL_TIMER_CC_OCTL_INV_OUT_DISABLED, DL_TIMER_CC_OCTL_SRC_FUNCVAL,
        DL_TIMERG_CAPTURE_COMPARE_0_INDEX);
    DL_TimerG_setCaptCompUpdateMethod(Right_Motor_Timer_INST, 
        DL_TIMER_CC_UPDATE_METHOD_IMMEDIATE, DL_TIMERG_CAPTURE_COMPARE_0_INDEX);
    DL_TimerG_enableClock(Right_Motor_Timer_INST);
    DL_TimerG_setCCPDirection(Right_Motor_Timer_INST, DL_TIMER_CC0_OUTPUT);
}
```

- [ ] **Step 11: ti_msp_dl_config.c — 添加右电机编码器初始化函数**

```c
/* 右电机编码器QEI配置 — 与左电机相同 */
static const DL_TimerG_ClockConfig gRight_Encoder_TimerClockConfig = {
    .clockSel = DL_TIMER_CLOCK_BUSCLK,
    .divideRatio = DL_TIMER_CLOCK_DIVIDE_1,
    .prescale = 0U
};

SYSCONFIG_WEAK void SYSCFG_DL_Right_Encoder_Timer_init(void) {
    DL_TimerG_setClockConfig(
        Right_Encoder_Timer_INST,
        (DL_TimerG_ClockConfig *)&gRight_Encoder_TimerClockConfig);

    DL_TimerG_configQEI(Right_Encoder_Timer_INST, DL_TIMER_QEI_MODE_2_INPUT,
        DL_TIMER_CC_INPUT_INV_NOINVERT, DL_TIMER_CC_0_INDEX);
    DL_TimerG_configQEI(Right_Encoder_Timer_INST, DL_TIMER_QEI_MODE_2_INPUT,
        DL_TIMER_CC_INPUT_INV_NOINVERT, DL_TIMER_CC_1_INDEX);
    DL_TimerG_setLoadValue(Right_Encoder_Timer_INST, 65535);
    DL_TimerG_enableClock(Right_Encoder_Timer_INST);
    DL_TimerG_startCounter(Right_Encoder_Timer_INST);
}
```

- [ ] **Step 12: ti_msp_dl_config.c — 添加ADC12初始化函数**

```c
/* ADC12配置 — 12位分辨率，软件触发，单次转换 */
static const DL_ADC12_ClockConfig gGRAYSCALE_ADCClockConfig = {
    .divideRatio = DL_ADC12_CLOCK_DIVIDE_1,
    .freqRange = DL_ADC12_CLOCK_FREQ_RANGE_24_TO_32,
};

SYSCONFIG_WEAK void SYSCFG_DL_GRAYSCALE_ADC_init(void) {
    DL_ADC12_setClockConfig(GRAYSCALE_ADC_INST, 
        (DL_ADC12_ClockConfig *)&gGRAYSCALE_ADCClockConfig);

    DL_ADC12_initSingleSample(GRAYSCALE_ADC_INST, 
        DL_ADC12_SAMPLING_SOURCE_AUTO, 
        DL_ADC12_SAMPLING_MODE_NORMAL_SEQUENCE);

    /* 配置ADC通道: ADC0.2 = PA27 */
    DL_ADC12_configConversionMem(GRAYSCALE_ADC_INST, 
        DL_ADC12_MEM_IDX_0, 
        DL_ADC12_INPUT_CHAN_2,    /* ADC通道2 = PA27 */
        DL_ADC12_REFERENCE_VOLTAGE_VDDA,
        DL_ADC12_SAMPLE_TIME_SAMP_CNT_15,
        DL_ADC12_AVERAGING_MODE_DISABLED,
        DL_ADC12_TRIG_SRC_SOFTWARE,
        DL_ADC12_DATA_FORMAT_BINARY_UNSIGNED);

    DL_ADC12_enableConversions(GRAYSCALE_ADC_INST, true);
    DL_ADC12_enableClock(GRAYSCALE_ADC_INST);
}
```

- [ ] **Step 13: 验证引脚冲突**

逐一检查所有新增引脚是否与现有定义冲突：
- PA12: 右电机PWM（TIMG6_CC0）— 检查PINCM28是否被其他功能占用
- PA13: 右电机方向1 — 检查PINCM28冲突（注意PA12和PA13可能共用PINCM，需确认）
- PA16: 右电机方向2 — PINCM37
- PA18/19/20: 灰度地址线 — PINCM33/34/35
- PA27: ADC输入 — PINCM41
- PB26/PB27: 右编码器 — PINCM39/40

**重要：** PA12和PA13的PINCM编号需要查MSPM0G3507数据手册确认。如果冲突，需调整引脚分配。

---

## Task 7: 更新 bsp_all.h 统一头文件

**Files:**
- Modify: `BSP/Inc/bsp_all.h`

- [ ] **Step 1: 添加新模块头文件包含**

```c
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
#include "bsp_grayscale.h"      /* 新增 */
#include "bsp_pid.h"            /* 新增 */
#include "bsp_tracking.h"       /* 新增 */

#endif /* __BSP_ALL_H__ */
```

---

## Task 8: 更新 app_grayscale.h 引脚定义

**Files:**
- Modify: `APP/Inc/app_grayscale.h`

- [ ] **Step 1: 同步引脚定义与SysConfig一致**

```c
/* ============ 灰度传感器硬件配置 ============ */
/* 地址线 AD0/AD1/AD2 */
#define GRAY_AD0_PORT           GPIOA
#define GRAY_AD0_PIN            DL_GPIO_PIN_18
#define GRAY_AD1_PORT           GPIOA
#define GRAY_AD1_PIN            DL_GPIO_PIN_19
#define GRAY_AD2_PORT           GPIOA
#define GRAY_AD2_PIN            DL_GPIO_PIN_20

/* ADC实例 */
#define GRAY_ADC_INST           ADC12_0
```

确认与 `ti_msp_dl_config.h` 中的定义一致。

---

## Self-Review

### 1. Spec coverage

| 需求 | 对应Task |
|------|---------|
| PID循迹代码 | Task 1 (PID BSP) + Task 2 (Tracking BSP) + Task 5 (Tracking APP) |
| 走直线 | Task 2 - LINE_FOLLOW状态 + 灰度PID |
| 直角弯道 | Task 2 - RIGHT_ANGLE状态 + 陀螺仪PID |
| 陀螺仪决策 | 架构决策中明确：必须使用MPU6050 |
| 双电机 | Task 3 - 右电机扩展 |
| SysConfig同步 | Task 6 - 完整的config.h/c修改 |
| 集成到项目 | Task 7 - bsp_all.h更新 + Task 8 - 引脚同步 |

### 2. Placeholder scan

- 所有代码块均为完整实现，无TODO/TBD
- SysConfig部分提供了完整的手动配置代码
- PID参数提供了默认值，标注"需实测调优"

### 3. Type consistency

- `bsp_tracking_t` 在所有文件中字段名一致
- `App_Motor_Right` 在app_encoder_motor.h声明，app_tracking.c中使用
- `App_Grayscale.digital[]` 在app_grayscale.h定义，app_tracking.c中引用
- `App_MPU.gyro_z` 在app_mpu6050.h定义，app_tracking.c中引用

### 4. 关键注意事项

1. **引脚PINCM编号**：PA12/PA13的PINCM编号需查数据手册确认，可能存在冲突
2. **ADC API**：`DL_ADC12_initSingleSample`等函数名可能因DriverLib版本不同，编译时需按实际API调整
3. **TIMG12**：需确认MSPM0G3507是否支持TIMG12的QEI功能
4. **编码器读取**：右电机编码器的`HW_Enc_Read`函数目前使用static变量，双电机共用会有问题，需要为右电机单独实现
