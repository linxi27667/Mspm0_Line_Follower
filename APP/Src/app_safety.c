/**
 * @file    app_safety.c
 * @brief   安全状态机实现 — 唯一授权电机输出的模块。
 *
 *          设计原则:
 *            1. Track/PID 可计算期望速度，但电机输出仅当
 *               Safety_AllowsMotorOutput() 返回 true 时才执行。
 *            2. BOOT/CALIBRATING/READY/FINISHED 状态始终切断 PWM。
 *            3. 比赛运行不依据灰度、编码器、通信或传感器瞬态自动停车。
 *
 * @note    本模块不直接操作硬件寄存器，通过 BSP/APP API 切断电机:
 *            App_Motor_Enable_Speed_PID(false) — 切开环
 *            Bsp_Motor_Write_Pwm(&Motor_*, 0)  — 直写 PWM=0
 */
#include "app_safety.h"
#include "app_all.h"
#include <elog.h>

/* ============================================================
 * 内部状态
 * ============================================================ */

static safety_state_t s_state = SAFETY_STATE_BOOT;
static safety_fault_t s_fault = SAFETY_FAULT_NONE;

/* 校准完成标志 */
static bool     s_calibration_complete = false;

/* ============================================================
 * 内部工具
 * ============================================================ */

static void Safety_CutMotor(void)
{
    /* 切开环 + 直写 PWM=0，确保即使速度 PID 漏更新也能停车 */
    App_Motor_Enable_Speed_PID(false);
    Bsp_Motor_Write_Pwm(&Motor_Left, 0);
    Bsp_Motor_Write_Pwm(&Motor_Right, 0);
}

static const char *s_state_names[] = {
    "BOOT", "CALIBRATING", "READY", "RUNNING", "FINISHED", "FAULT"
};

static const char *s_fault_names[] = {
    "NONE",
    "GRAYSCALE_EXPIRED",
    "CALIBRATION_INCOMPLETE",
    "CONTROL_TICK_MISSED",
    "ENCODER_ANOMALY",
    "HEARTBEAT_LOST",
    "SENSOR_ABNORMAL",
    "MANUAL_STOP",
    "LINE_LOST_TIMEOUT"
};

/* ============================================================
 * 初始化与状态转换
 * ============================================================ */

void Safety_Init(void)
{
    s_state                = SAFETY_STATE_BOOT;
    s_fault                = SAFETY_FAULT_NONE;
    s_calibration_complete = false;

    Safety_CutMotor();
    elog_i("SAFETY", "init: state=BOOT, motor cut");
}

void Safety_TransitionToCalibrating(void)
{
    if (s_state == SAFETY_STATE_FAULT) return;  /* 故障态锁定 */
    if (s_state == SAFETY_STATE_CALIBRATING) return;

    s_state = SAFETY_STATE_CALIBRATING;
    Safety_CutMotor();
    elog_i("SAFETY", "-> CALIBRATING");
}

void Safety_TransitionToReady(void)
{
    if (s_state == SAFETY_STATE_FAULT) return;
    if (s_state == SAFETY_STATE_READY) return;

    /* 进入 READY 前必须校准完成 */
    if (!s_calibration_complete) {
        elog_w("SAFETY", "READY blocked: calibration incomplete");
        return;
    }

    s_state = SAFETY_STATE_READY;
    Safety_CutMotor();
    elog_i("SAFETY", "-> READY");
}

void Safety_TransitionToRunning(void)
{
    if (s_state == SAFETY_STATE_FAULT) return;
    if (s_state == SAFETY_STATE_RUNNING) return;

    /* 必须从 READY 进入，校准已完成 */
    if (s_state != SAFETY_STATE_READY && s_state != SAFETY_STATE_FINISHED) {
        elog_w("SAFETY", "RUNNING blocked: state=%s",
               Safety_StateName(s_state));
        return;
    }
    if (!s_calibration_complete) {
        elog_w("SAFETY", "RUNNING blocked: calibration incomplete");
        return;
    }

    s_state = SAFETY_STATE_RUNNING;

    elog_i("SAFETY", "-> RUNNING (motor armed)");
}

bool Safety_TransitionToRotation(void)
{
    if (s_state == SAFETY_STATE_FAULT || s_state == SAFETY_STATE_RUNNING) {
        return false;
    }

    /* 原地旋转仅依赖 MPU；灰度黑白校准仍是循迹启动的必要条件。 */
    if (s_state != SAFETY_STATE_BOOT && s_state != SAFETY_STATE_CALIBRATING &&
        s_state != SAFETY_STATE_READY && s_state != SAFETY_STATE_FINISHED) {
        return false;
    }

    s_state = SAFETY_STATE_RUNNING;
    elog_i("SAFETY", "-> RUNNING (rotation, gray calibration not required)");
    return true;
}

void Safety_TransitionAfterRotation(void)
{
    if (s_state == SAFETY_STATE_FAULT) return;

    Safety_CutMotor();
    if (s_calibration_complete) {
        s_state = SAFETY_STATE_READY;
        elog_i("SAFETY", "rotation ended -> READY");
    } else {
        s_state = SAFETY_STATE_BOOT;
        elog_i("SAFETY", "rotation ended -> BOOT (gray calibration pending)");
    }
}

void Safety_TransitionToFinished(void)
{
    if (s_state == SAFETY_STATE_FAULT) return;
    s_state = SAFETY_STATE_FINISHED;
    Safety_CutMotor();
    elog_i("SAFETY", "-> FINISHED");
}

void Safety_EnterFault(safety_fault_t fault)
{
    if (s_state == SAFETY_STATE_FAULT && s_fault == fault) return;

    s_state = SAFETY_STATE_FAULT;
    s_fault = fault;
    Safety_CutMotor();
    elog_e("SAFETY", "-> FAULT: %s", Safety_FaultName(fault));
}

void Safety_ClearFault(void)
{
    if (s_state != SAFETY_STATE_FAULT) return;

    s_fault = SAFETY_FAULT_NONE;
    s_state = SAFETY_STATE_READY;
    elog_i("SAFETY", "fault cleared -> READY");
}

/* ============================================================
 * 控制 tick — 每 5ms 由主循环调用，按状态授权电机输出。
 * ============================================================ */
bool Safety_ControlTick(void)
{
    /* --- BOOT 态: 电机禁止 --- */
    if (s_state == SAFETY_STATE_BOOT ||
        s_state == SAFETY_STATE_CALIBRATING) {
        Safety_CutMotor();
        return false;
    }

    /* --- FAULT/FINISHED: 持续切断电机 --- */
    if (s_state == SAFETY_STATE_FAULT ||
        s_state == SAFETY_STATE_FINISHED) {
        Safety_CutMotor();
        return false;
    }

    /* READY 状态: 通过所有检查但仍禁止电机 */
    if (s_state == SAFETY_STATE_READY) {
        return false;
    }

    /* RUNNING 状态: 所有检查通过，授权电机输出 */
    return (s_state == SAFETY_STATE_RUNNING);
}

/* ============================================================
 * 查询接口
 * ============================================================ */

safety_state_t Safety_GetState(void) { return s_state; }
safety_fault_t Safety_GetFault(void) { return s_fault; }

bool Safety_AllowsMotorOutput(void)
{
    /* 同步查询接口：仅 RUNNING 且无故障时允许
     * 注意: 这不替代 Safety_ControlTick 的活跃监测，
     * 电机输出路径仍应先调用 Safety_ControlTick */
    return (s_state == SAFETY_STATE_RUNNING) &&
           (s_fault == SAFETY_FAULT_NONE);
}

const char *Safety_StateName(safety_state_t state)
{
    if ((uint32_t)state >= sizeof(s_state_names)/sizeof(s_state_names[0])) {
        return "?";
    }
    return s_state_names[state];
}

const char *Safety_FaultName(safety_fault_t fault)
{
    if ((uint32_t)fault >= sizeof(s_fault_names)/sizeof(s_fault_names[0])) {
        return "?";
    }
    return s_fault_names[fault];
}

/* ============================================================
 * 传感器健康更新
 * ============================================================ */

void Safety_NotifyGrayscaleFrame(uint32_t tick)
{
    (void)tick;
}

void Safety_NotifyEncoderHealth(bool left_ok, bool right_ok)
{
    (void)left_ok;
    (void)right_ok;
}

void Safety_NotifyHeartbeat(uint32_t tick)
{
    (void)tick;
}

void Safety_NotifySensorAbnormal(void)
{
}

void Safety_NotifyCalibrationComplete(void)
{
    s_calibration_complete = true;
}

void Safety_TryAdvanceAfterCalibration(void)
{
    /* 检查灰度白+黑校准都完成 */
    if (Grayscale_Sensor.calibrated && Grayscale_Sensor.black_calibrated) {
        if (!s_calibration_complete) {
            s_calibration_complete = true;
            elog_i("SAFETY", "calibration complete (white+black)");
        }
        if (s_state == SAFETY_STATE_BOOT || s_state == SAFETY_STATE_CALIBRATING) {
            Safety_TransitionToReady();
        }
    }
}

/* ============================================================
 * 强制停车
 * ============================================================ */

void Safety_ForceMotorStop(void)
{
    Safety_CutMotor();
    /* 不强制进入 FAULT，仅切电机；由调用方决定是否升级状态 */
}
