/**
 * @file    app_safety.h
 * @brief   安全状态机 — 唯一授权电机输出的模块。
 *
 *          状态: BOOT → CALIBRATING → READY → RUNNING → FINISHED。
 *          比赛运行不使用灰度、编码器、通信或传感器瞬态作为自动停车条件。
 *          FAULT 仅保留给未来明确调用 Safety_EnterFault() 的外部扩展。
 *
 *          核心原则: Track/PID 可计算期望速度，但电机输出
 *          仅当 Safety_AllowsMotorOutput() 返回 true 时才执行。
 */
#ifndef APP_SAFETY_H
#define APP_SAFETY_H

#include "app_common.h"
#include <stdint.h>
#include <stdbool.h>

/* 安全状态 */
typedef enum {
    SAFETY_STATE_BOOT = 0,          /* 初始化中,电机禁止 */
    SAFETY_STATE_CALIBRATING,       /* 校准中,电机禁止 */
    SAFETY_STATE_READY,             /* 就绪,等待启动,电机禁止 */
    SAFETY_STATE_RUNNING,           /* 循迹运行中,电机允许 */
    SAFETY_STATE_FINISHED,          /* 正常完成,电机禁止 */
    SAFETY_STATE_FAULT,             /* 故障停车,电机禁止 */
} safety_state_t;

/* 故障类型 */
typedef enum {
    SAFETY_FAULT_NONE = 0,
    SAFETY_FAULT_GRAYSCALE_EXPIRED,      /* 灰度帧过期 */
    SAFETY_FAULT_CALIBRATION_INCOMPLETE, /* 校准未完成 */
    SAFETY_FAULT_CONTROL_TICK_MISSED,    /* 控制漏期 */
    SAFETY_FAULT_ENCODER_ANOMALY,        /* 编码器异常 */
    SAFETY_FAULT_HEARTBEAT_LOST,         /* TUNING心跳丢失 */
    SAFETY_FAULT_SENSOR_ABNORMAL,        /* 传感器抬起/异常 */
    SAFETY_FAULT_MANUAL_STOP,            /* 手动停止 */
    SAFETY_FAULT_LINE_LOST_TIMEOUT,      /* 丢线超时 */
} safety_fault_t;

/* ============================================================
 * 初始化与状态转换
 * ============================================================ */
void Safety_Init(void);

void Safety_TransitionToCalibrating(void);
void Safety_TransitionToReady(void);
void Safety_TransitionToRunning(void);
bool Safety_TransitionToRotation(void);  /* MPU 原地旋转：不要求灰度黑白校准 */
void Safety_TransitionAfterRotation(void); /* 旋转结束：按灰度校准状态回到 READY 或 BOOT */
void Safety_TransitionToFinished(void);
void Safety_EnterFault(safety_fault_t fault);
void Safety_ClearFault(void);  /* 故障清除→回到 READY(需手动) */

/* ============================================================
 * 控制tick — 每5ms由主循环调用，按状态授权电机输出。
 * ============================================================ */
bool Safety_ControlTick(void);

/* ============================================================
 * 查询接口
 * ============================================================ */
safety_state_t Safety_GetState(void);
safety_fault_t Safety_GetFault(void);
bool Safety_AllowsMotorOutput(void);
const char *Safety_StateName(safety_state_t state);
const char *Safety_FaultName(safety_fault_t fault);

/* ============================================================
 * 传感器健康更新 (由各模块调用)
 * ============================================================ */

/* 保留为兼容现有调用；不参与停车判定。 */
void Safety_NotifyGrayscaleFrame(uint32_t tick);

/* 保留为兼容现有调用；不参与停车判定。 */
void Safety_NotifyEncoderHealth(bool left_ok, bool right_ok);

/* 保留为兼容现有调用；不参与停车判定。 */
void Safety_NotifyHeartbeat(uint32_t tick);

/* 保留为兼容现有调用；不参与停车判定。 */
void Safety_NotifySensorAbnormal(void);

/* 校准完成通知 */
void Safety_NotifyCalibrationComplete(void);

/* 校准后尝试推进到 READY（检查 white+black 都完成）
 * 由 K3/K4 校准按键调用，避免 main.c 直接访问 Grayscale_Sensor */
void Safety_TryAdvanceAfterCalibration(void);

/* ============================================================
 * 强制停车 — 切断所有电机输出
 * ============================================================ */
void Safety_ForceMotorStop(void);

#endif /* APP_SAFETY_H */
