/**
 * @file    track.h
 * @brief   灰度PID循迹任务调度层（TASK层 — 纯业务逻辑）
 * @note    传感器布局: S0 S1 S2 S3 S4 S5 S6 S7（左→右）
 *          偏差权重:   -3.5 -2.5 -1.5 -0.5 +0.5 +1.5 +2.5 +3.5
 *          负偏差=黑线在左侧(需左转)  正偏差=黑线在右侧(需右转)
 *          turn_output>0=右转(左轮加速) <0=左转(右轮加速)
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
#include "user_tuning.h"

/* ============================================================
 * 循迹调度宏定义
 *
 * 所有 USER_* 默认值唯一定义在 APP/Inc/user_tuning.h。
 * 本文件只保留 TRACK_* 别名，不再保留 #ifndef 回退默认值，
 * 消除三层重复定义导致的死代码与值不一致风险。
 * ============================================================ */

/* 循迹状态机更新周期(ms) */
#define TRACK_UPDATE_PERIOD_MS    5

/* --- 直角弯道检测 --- */
#define TRACK_RIGHT_ANGLE_THRESHOLD       USER_RIGHT_ANGLE_THRESHOLD
#define TRACK_RIGHT_ANGLE_CONFIRM_FRAMES  USER_RIGHT_ANGLE_CONFIRM_FRAMES
#define TRACK_RIGHT_ANGLE_TIMEOUT         USER_RIGHT_ANGLE_TIMEOUT
#define TRACK_RIGHT_ANGLE_DONE_ERR        USER_RIGHT_ANGLE_DONE_ERR
/* 国一方案: 直角弯多条件触发 (单一条件漏检率高)
 * - ERROR_INTEGRAL: 误差累积超限 (弯道持续大误差说明弯很急)
 * - GYRO_RATE: 角速度超限 (车体快速旋转说明进入急弯)
 * 任一条件 + 原始 S0/S7 条件满足即触发, 覆盖黑线没摆到外侧/弯前误差不足的漏检场景 */
#define TRACK_RIGHT_ANGLE_ERROR_INTEGRAL  USER_RIGHT_ANGLE_ERROR_INTEGRAL
#define TRACK_RIGHT_ANGLE_GYRO_RATE       USER_RIGHT_ANGLE_GYRO_RATE
#define TRACK_RIGHT_ANGLE_TARGET_ANGLE    USER_RIGHT_ANGLE_TARGET_ANGLE
#define TRACK_RIGHT_ANGLE_MIN_EXIT_ANGLE  USER_RIGHT_ANGLE_MIN_EXIT_ANGLE
#define TRACK_RIGHT_ANGLE_EXIT_CENTER_MIN USER_RIGHT_ANGLE_EXIT_CENTER_MIN
#define TRACK_RIGHT_ANGLE_EXIT_BLACK_MIN  USER_RIGHT_ANGLE_EXIT_BLACK_MIN
#define TRACK_RIGHT_ANGLE_EXIT_BLACK_MAX  USER_RIGHT_ANGLE_EXIT_BLACK_MAX

/* --- LINE_FOLLOW 陀螺仪角速度阻尼 (国一方案核心) ---
 * 直行时用陀螺仪角速度作阻尼项, 抑制灰度传感器噪声引起的左右抖动
 * 公式: turn_output = line_pid_output - GYRO_DAMP * gyro_z
 * 调参: 直道抖动→加大(0.15→0.3), 弯道跟踪迟钝→减小(0.15→0.08) */
#define TRACK_LINE_FOLLOW_GYRO_DAMP       USER_LINE_FOLLOW_GYRO_DAMP

/* --- 十字路口检测 --- */
#define TRACK_CROSS_MIN_BLACK             USER_CROSS_MIN_BLACK
#define TRACK_CROSS_PASS_MS               300u

/* --- 起点线检测 --- */
#define TRACK_START_LINE_MIN_BLACK        USER_START_LINE_MIN_BLACK
#define TRACK_START_LINE_HOLD_MS          250u

/* --- 丢线检测 --- */
#define TRACK_LINE_LOST_MAX_BLACK         1
#define TRACK_LINE_LOST_TIMEOUT           USER_LINE_LOST_TIMEOUT
#define TRACK_LINE_LOST_GAIN              USER_LINE_LOST_GAIN
#define TRACK_LINE_LOST_CONFIRM_FRAMES    5     /* 连续5帧全白才确认丢线(抗干扰) */

/* --- 变速策略 --- */
#define TRACK_SPEED_STRAIGHT              USER_TRACK_SPEED_STRAIGHT
#define TRACK_SPEED_CURVE                 USER_TRACK_SPEED_CURVE
#define TRACK_SPEED_SWITCH_ERR            1.0f
#define TRACK_SPEED_RAMP_STEP             USER_TRACK_SPEED_RAMP_STEP
/* 国一方案: 连续曲率变速 (替代二档跳变)
 * error=0 → SPEED_STRAIGHT, |error|>=CURVE_ERROR_MAX → SPEED_CURVE, 中间线性插值
 * 效果: 进弯平滑减速不甩出, 出弯平滑加速不慢 */
#define TRACK_CURVE_ERROR_MAX             USER_TRACK_CURVE_ERROR_MAX

/* --- 电机差速 --- */
#define TRACK_MOTOR_INNER_MIN             USER_TRACK_MOTOR_INNER_MIN
#define TRACK_MOTOR_SPEED_MAX             100
#define TRACK_MOTOR_SPEED_MIN             (-100)

/* --- 偏差计算 --- */
#define TRACK_ERROR_MIN_DENOM             0.01f

/* --- 默认参数 --- */
#define TRACK_DEFAULT_BASE_SPEED          USER_TRACK_BASE_SPEED
#define TRACK_DEFAULT_CIRCLES             USER_TRACK_CIRCLES

/* 循迹PID默认参数（需实测调优） */
#define TRACK_LINE_PID_KP        USER_LINE_PID_KP
#define TRACK_LINE_PID_KI        USER_LINE_PID_KI
#define TRACK_LINE_PID_KD        USER_LINE_PID_KD
#define TRACK_LINE_PID_ILIMIT    USER_LINE_PID_ILIMIT
#define TRACK_LINE_PID_OLIMIT    USER_LINE_PID_OLIMIT
#define TRACK_LINE_PID_DERIV_ALPHA USER_LINE_PID_DERIV_ALPHA

/* 陀螺仪PID默认参数 */
#define TRACK_GYRO_PID_KP        USER_GYRO_PID_KP
#define TRACK_GYRO_PID_KI        USER_GYRO_PID_KI
#define TRACK_GYRO_PID_KD        USER_GYRO_PID_KD
#define TRACK_GYRO_PID_ILIMIT    USER_GYRO_PID_ILIMIT
#define TRACK_GYRO_PID_OLIMIT    USER_GYRO_PID_OLIMIT

#define TRACK_ROTATE_DONE_ERR_DEG USER_ROTATE_DONE_ERR_DEG

#include "track_logic.h"

/* ============================================================
 * 循迹调度对象 — 只包含状态机和输出（纯业务数据）
 * ============================================================ */
typedef struct {
    /* --- 偏差计算 --- */
    float    error;                 /* 加权偏差 */
    float    last_error;            /* 上次偏差 */
    float    error_accum;           /* 误差累积积分(直角弯检测用, 衰减式) */

    /* --- 状态机 --- */
    track_state_t state;
    track_state_t last_state;
    float    target_heading;        /* 丢线时的目标航向 */
    float    right_angle_target;    /* 直角弯道目标角度 */
    float    right_angle_entry_heading; /* 进入直角弯时的航向 */
    float    right_angle_direction; /* 直角弯方向: +1右转, -1左转 */
    uint32_t state_timer;           /* 当前状态进入时刻(ms) */
    uint32_t line_lost_count;       /* 丢线持续时间(ms) */

    /* --- 陀螺仪辅助 (国一方案) --- */
    float    gyro_rate;             /* 当前Z轴角速度(deg/s), LINE_FOLLOW阻尼用 */
    float    heading_baseline;      /* 直行基准航向(进入LINE_FOLLOW时锁定, 备用) */

    /* --- 远程原地旋转（相对航向闭环） --- */
    float    rotate_heading_baseline;
    float    rotate_target_deg;
    float    rotate_actual_deg;
    float    rotate_error_deg;
    uint32_t rotate_started_at;
    uint32_t rotate_timeout_ms;
    uint8_t  rotate_settle_frames;
    const char *rotate_result;

    /* --- Current-heading hold (absolute heading PID) --- */
    float    heading_hold_target;
    float    heading_hold_actual;
    float    heading_hold_error;
    const char *heading_hold_result;

    /* --- 直角弯道多帧确认 --- */
    uint8_t  right_angle_confirm;   /* 直角弯连续确认计数 */
    uint8_t  line_lost_confirm;     /* 丢线连续确认计数 */

    /* --- 起点线防重复计数 --- */
    bool     start_line_armed;      /* true=可检测起点线, false=需等黑线消失后重新武装 */

    /* --- 圈数 --- */
    uint8_t  target_circles;
    uint8_t  current_circle;
    uint16_t right_angle_count;  /* 已完成直角弯总数(正方形: 4个=1圈) */

    /* --- PID（使用BSP层 bsp_pid_t） --- */
    bsp_pid_t line_pid;             /* 循迹位置PID */
    bsp_pid_t gyro_pid;             /* 陀螺仪航向PID */

    /* --- 输出 --- */
    float    turn_output;           /* 转向量(正=右转,负=左转) */
    int32_t  left_speed;            /* 左电机速度 */
    int32_t  right_speed;           /* 右电机速度 */
    int32_t  base_speed;            /* 当前基础速度（渐变） */
    int32_t  target_speed;          /* 目标基础速度（由变速策略决定） */

    /* --- AI 调参运行时可调参数（原 #define 宏常量，改为字段以支持在线调整） --- */
    float    gyro_damp;             /* 循迹陀螺仪阻尼（原 USER_LINE_FOLLOW_GYRO_DAMP）*/
    int32_t  speed_straight;        /* 直道速度（原 USER_TRACK_SPEED_STRAIGHT）*/
    int32_t  speed_curve;           /* 弯道速度（原 USER_TRACK_SPEED_CURVE）*/
    float    right_angle_threshold; /* 直角弯检测误差阈值（原 USER_RIGHT_ANGLE_THRESHOLD）*/

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
bool Track_Start_Rotation(float target_deg); /* READY状态开始相对角度原地旋转 */
bool Track_Is_Rotating(void);
void Track_Abort_Rotation(const char *result); /* Safety 故障时结束旋转并发布结果 */
float Track_Get_Rotation_Target(void);
float Track_Get_Rotation_Angle(void);
float Track_Get_Rotation_Error(void);
const char *Track_Get_Rotation_Result(void);
bool Track_Start_Heading_Hold(void);
bool Track_Stop_Heading_Hold(void);
bool Track_Is_Heading_Hold(void);
float Track_Get_Heading_Hold_Target(void);
float Track_Get_Heading_Hold_Actual(void);
float Track_Get_Heading_Hold_Error(void);
const char *Track_Get_Heading_Hold_Result(void);
void Track_Check_RightAngle_Completion(void); /* 正方形直角计圈检查 */
void Track_Set_Circles(uint8_t n);      /* 设置目标圈数 */
void Track_Set_Speed(int32_t base_speed); /* 设置基础速度 */
void Track_Set_TrackPID(float kp, float ki, float kd); /* 调循迹PID */

/* AI 远程调参 setter（运行时修改原宏常量参数） */
void Track_Set_GyroDamp(float damp);                /* 陀螺仪阻尼 */
void Track_Set_SpeedStraight(int32_t spd);          /* 直道速度 */
void Track_Set_SpeedCurve(int32_t spd);             /* 弯道速度 */
void Track_Set_RightAngleThreshold(float thr);      /* 直角弯检测误差阈值 */
void Track_Calibrate_White(void);       /* 白纸校准 */
void Track_Calibrate_Black(void);       /* 黑纸校准 */
track_state_t Track_Get_State(void);    /* 获取当前状态 */
uint8_t Track_Get_Circle(void);         /* 获取当前圈数 */

#endif /* __TRACK_H__ */
