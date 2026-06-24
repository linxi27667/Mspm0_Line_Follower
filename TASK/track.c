/**
 * @file    track.c
 * @brief   灰度PID循迹任务调度实现（TASK层）
 * @note    数据流:
 *          Track_Grayscale_Scan → data_ready → Track_Calc_Error → PID → 差速 → Track_Motor
 *          Track_Gyro_Read      → heading    → 丢线辅助/直角弯道
 *
 *          修复清单:
 *          ✅ 灰度 data_ready 同步（PID只在完整扫描后执行）
 *          ✅ 模拟量差比和偏差计算（连续精度）
 *          ✅ 直角弯多帧确认（3帧防误触发）
 *          ✅ 十字路口处理（CROSS状态）
 *          ✅ 丢线恢复PID复位
 *          ✅ 起点线退出条件（black_count下降也退出）
 *          ✅ 电机内侧最低速度限制
 *          ✅ 变速策略（直道加速/弯道减速/渐变）
 */
#include "track.h"

/* systick_ms 定义在 main.c */
extern volatile uint32_t systick_ms;

/* ============================================================
 * 常量
 * ============================================================ */

/* 八路传感器权重: S0(-3.5) ... S7(+3.5) */
static const float s_weights[8] = {
    -3.5f, -2.5f, -1.5f, -0.5f, 0.5f, 1.5f, 2.5f, 3.5f
};

/* ============================================================
 * 全局对象
 * ============================================================ */

track_t Track = {0};

/* ============================================================
 * 内部函数：偏差计算（模拟量差比和 — 连续精度）
 * ============================================================ */

static void Track_Calc_Error(void)
{
    Track_Gray.black_count = 0;

    /* 保存上次偏差 */
    Track.last_error = Track.error;

    /* 方法1：模拟量差比和（归一化值，连续精度）
     * 左侧权重为负，右侧权重为正
     * norm[i] = 1 表示黑线，0 表示白色
     * error = Σ(weight[i] × norm[i]) / Σ(norm[i]) */
    float weighted_sum = 0;
    float total_weight = 0;

    for (uint8_t i = 0; i < TRACK_GRAY_CHANNEL_NUM; i++) {
        if (Track_Gray.digital[i]) {
            Track_Gray.black_count++;
        }
        /* 用归一化值做加权（连续精度，不受数字量跳变影响） */
        weighted_sum += s_weights[i] * Track_Gray.norm[i];
        total_weight  += Track_Gray.norm[i];
    }

    if (total_weight > TRACK_ERROR_MIN_DENOM) {
        Track.error = weighted_sum / total_weight;
    }
    /* 全白时保持上次 error 不变，由状态机处理 */
}

/* ============================================================
 * 内部函数：变速策略
 * ============================================================ */

static void Track_Update_Speed(void)
{
    /* 根据偏差大小决定目标速度 */
    if (Track.error > -TRACK_SPEED_SWITCH_ERR &&
        Track.error <  TRACK_SPEED_SWITCH_ERR) {
        Track.target_speed = TRACK_SPEED_STRAIGHT;   /* 直道加速 */
    } else {
        Track.target_speed = TRACK_SPEED_CURVE;       /* 弯道减速 */
    }

    /* 速度渐变（避免突变导致车身抖动） */
    if (Track.base_speed < Track.target_speed) {
        Track.base_speed += TRACK_SPEED_RAMP_STEP;
        if (Track.base_speed > Track.target_speed)
            Track.base_speed = Track.target_speed;
    } else if (Track.base_speed > Track.target_speed) {
        Track.base_speed -= TRACK_SPEED_RAMP_STEP;
        if (Track.base_speed < Track.target_speed)
            Track.base_speed = Track.target_speed;
    }
}

/* ============================================================
 * 内部函数：赛道元素检测
 * ============================================================ */

static void Track_Detect_Pattern(void)
{
    /* --- 十字路口检测 --- */
    /* 中间4路(S2~S5)全黑 + 外侧至少1路白 */
    uint8_t mid_black = 0;
    for (uint8_t i = 2; i <= 5; i++) {
        if (Track_Gray.digital[i]) mid_black++;
    }
    uint8_t outer_white = (!Track_Gray.digital[0] || !Track_Gray.digital[7]) ? 1 : 0;

    if (mid_black >= TRACK_CROSS_MIN_BLACK && outer_white) {
        if (Track.state == TRACK_STATE_LINE_FOLLOW) {
            Track.state = TRACK_STATE_CROSS;
            Track.state_timer = 0;
            return;
        }
    }

    /* --- 起点线检测（≥6路黑） --- */
    if (Track_Gray.black_count >= TRACK_START_LINE_MIN_BLACK) {
        if (Track.state == TRACK_STATE_LINE_FOLLOW) {
            Track.target_heading = Track_Gyro.heading;
            Track.state = TRACK_STATE_START_LINE;
            Track.state_timer = 0;
        }
        return;
    }

    /* --- 直角弯道检测（多帧确认） --- */
    if ((Track_Gray.digital[0] || Track_Gray.digital[7]) &&
        (Track.error > TRACK_RIGHT_ANGLE_THRESHOLD ||
         Track.error < -TRACK_RIGHT_ANGLE_THRESHOLD)) {
        Track.right_angle_confirm++;
        if (Track.right_angle_confirm >= TRACK_RIGHT_ANGLE_CONFIRM_FRAMES) {
            if (Track.state == TRACK_STATE_LINE_FOLLOW) {
                Track.last_state = TRACK_STATE_LINE_FOLLOW;
                Track.right_angle_target = Track_Gyro.heading +
                    (Track.error > 0 ? 90.0f : -90.0f);
                Track.state = TRACK_STATE_RIGHT_ANGLE;
                Track.state_timer = 0;
                Track.right_angle_confirm = 0;
            }
        }
    } else {
        /* 条件不满足，重置确认计数 */
        Track.right_angle_confirm = 0;
    }

    /* --- 丢线检测 --- */
    if (Track_Gray.black_count < TRACK_LINE_LOST_MAX_BLACK) {
        if (Track.state == TRACK_STATE_LINE_FOLLOW) {
            Track.last_state = TRACK_STATE_LINE_FOLLOW;
            Track.target_heading = Track_Gyro.heading;
            Track.state = TRACK_STATE_LINE_LOST;
            Track.line_lost_count = 0;
        }
    }
}

/* ============================================================
 * 内部函数：状态处理
 * ============================================================ */

/* 起点线处理：计数圈数 */
static void Track_Handle_StartLine(void)
{
    Track.state_timer++;

    /* 起点线持续超过阈值视为有效过线 */
    if (Track.state_timer > TRACK_START_LINE_COUNT) {
        Track.current_circle++;
        if (Track.current_circle >= Track.target_circles) {
            Track.state = TRACK_STATE_FINISHED;
            Track.left_speed  = 0;
            Track.right_speed = 0;
        } else {
            Track.state = TRACK_STATE_LINE_FOLLOW;
        }
        return;
    }

    /* 起点线消失（black_count 降到阈值以下）也退出 */
    if (Track_Gray.black_count < TRACK_START_LINE_MIN_BLACK) {
        Track.state = TRACK_STATE_LINE_FOLLOW;
        return;
    }

    /* 起点线期间保持直行 */
    Track.turn_output = 0;
}

/* 丢线处理：用陀螺仪维持航向 */
static void Track_Handle_LineLost(void)
{
    Track.line_lost_count++;

    if (Track.use_gyro && Track_Gyro.gyro_ok) {
        float gyro_error = Track.target_heading - Track_Gyro.heading;
        Track.turn_output = Track.gyro_pid.kp * gyro_error;
    } else {
        Track.turn_output = Track.last_error * TRACK_LINE_LOST_GAIN;
    }

    /* 丢线超时停车 */
    if (Track.line_lost_count > TRACK_LINE_LOST_TIMEOUT) {
        Track.state = TRACK_STATE_FINISHED;
        Track.left_speed  = 0;
        Track.right_speed = 0;
        return;
    }

    /* 重新检测到线，恢复循迹（PID复位防止积分突跳） */
    if (Track_Gray.black_count > 0) {
        Track.state = TRACK_STATE_LINE_FOLLOW;
        Track_PID_Reset(&Track.line_pid);
    }
}

/* 直角弯道处理：陀螺仪精确旋转90度 */
static void Track_Handle_RightAngle(void)
{
    Track.state_timer++;

    float angle_error = Track.right_angle_target - Track_Gyro.heading;
    Track.turn_output = Track_PID_Calculate(&Track.gyro_pid,
                                            Track.right_angle_target,
                                            Track_Gyro.heading);

    /* 角度误差小于阈值，视为完成转弯 */
    if (angle_error > -TRACK_RIGHT_ANGLE_DONE_ERR &&
        angle_error <  TRACK_RIGHT_ANGLE_DONE_ERR) {
        Track.state = TRACK_STATE_LINE_FOLLOW;
        Track_PID_Reset(&Track.line_pid);
        return;
    }

    /* 超时保护 */
    if (Track.state_timer > TRACK_RIGHT_ANGLE_TIMEOUT) {
        Track.state = TRACK_STATE_LINE_FOLLOW;
        Track_PID_Reset(&Track.line_pid);
    }
}

/* 十字路口处理：保持当前方向直行通过 */
static void Track_Handle_Cross(void)
{
    Track.state_timer++;

    /* 十字路口期间保持直行（turn_output=0） */
    Track.turn_output = 0;

    /* 通过计数超过阈值，视为已通过 */
    if (Track.state_timer > TRACK_CROSS_PASS_COUNT) {
        Track.state = TRACK_STATE_LINE_FOLLOW;
    }

    /* 如果检测到全白（偏离十字），也退出 */
    if (Track_Gray.black_count < 1 && Track.state_timer > 10) {
        Track.state = TRACK_STATE_LINE_FOLLOW;
    }
}

/* 差速输出到电机（内侧电机最低速度限制） */
static void Track_Motor_Output(void)
{
    Track.left_speed  = Track.base_speed + (int32_t)Track.turn_output;
    Track.right_speed = Track.base_speed - (int32_t)Track.turn_output;

    /* 内侧电机最低速度限制（不允许反转，避免急转抖动） */
    if (Track.left_speed < TRACK_MOTOR_INNER_MIN && Track.right_speed > TRACK_MOTOR_INNER_MIN) {
        Track.left_speed = TRACK_MOTOR_INNER_MIN;
    }
    if (Track.right_speed < TRACK_MOTOR_INNER_MIN && Track.left_speed > TRACK_MOTOR_INNER_MIN) {
        Track.right_speed = TRACK_MOTOR_INNER_MIN;
    }

    /* 电机速度限幅 */
    if (Track.left_speed >  TRACK_MOTOR_SPEED_MAX) Track.left_speed  =  TRACK_MOTOR_SPEED_MAX;
    if (Track.left_speed <  TRACK_MOTOR_SPEED_MIN) Track.left_speed  =  TRACK_MOTOR_SPEED_MIN;
    if (Track.right_speed > TRACK_MOTOR_SPEED_MAX) Track.right_speed =  TRACK_MOTOR_SPEED_MAX;
    if (Track.right_speed < TRACK_MOTOR_SPEED_MIN) Track.right_speed =  TRACK_MOTOR_SPEED_MIN;

    if (Track.use_motor) {
        Track_Motor_SetLeft(Track.left_speed);
        Track_Motor_SetRight(Track.right_speed);
    }
}

/* ============================================================
 * 对外接口实现
 * ============================================================ */

void Track_Init(void)
{
    /* 状态机清零 */
    Track.error              = 0;
    Track.last_error         = 0;
    Track.state              = TRACK_STATE_IDLE;
    Track.last_state         = TRACK_STATE_IDLE;
    Track.target_heading     = 0;
    Track.right_angle_target = 0;
    Track.state_timer        = 0;
    Track.line_lost_count    = 0;
    Track.right_angle_confirm = 0;
    Track.target_circles     = TRACK_DEFAULT_CIRCLES;
    Track.current_circle     = 0;
    Track.turn_output        = 0;
    Track.left_speed         = 0;
    Track.right_speed        = 0;
    Track.base_speed         = TRACK_DEFAULT_BASE_SPEED;
    Track.target_speed       = TRACK_DEFAULT_BASE_SPEED;
    Track.use_gyro           = true;
    Track.use_motor          = true;

    /* PID 初始化 */
    Track_PID_Init(&Track.line_pid,
                   TRACK_LINE_PID_KP, TRACK_LINE_PID_KI, TRACK_LINE_PID_KD,
                   TRACK_LINE_PID_ILIMIT, TRACK_LINE_PID_OLIMIT);
    Track_PID_Init(&Track.gyro_pid,
                   TRACK_GYRO_PID_KP, TRACK_GYRO_PID_KI, TRACK_GYRO_PID_KD,
                   TRACK_GYRO_PID_ILIMIT, TRACK_GYRO_PID_OLIMIT);

    /* 子模块初始化 */
    Track_Grayscale_Init();
#if TRACK_USE_MPU6050
    Track_Gyro_Init();
#endif
}

void Track_Update(void)
{
    /* ① 灰度传感器非阻塞扫描 */
    Track_Grayscale_Scan();

    /* ② 固定5ms周期执行循迹状态机 */
    static uint32_t last_update_tick = 0;
    uint32_t now = systick_ms;
    if ((now - last_update_tick) < TRACK_UPDATE_PERIOD_MS) return;
    last_update_tick = now;

    if (Track.state == TRACK_STATE_IDLE ||
        Track.state == TRACK_STATE_FINISHED) return;

    /* ③ 等待灰度传感器完成一轮完整扫描（数据同步） */
    if (!Track_Gray.data_ready) return;
    Track_Gray.data_ready = 0;  /* 消费标志 */

    /* ④ 读取陀螺仪数据 */
#if TRACK_USE_MPU6050
    if (Track.use_gyro) {
        Track_Gyro_Read();
    }
#endif

    /* ⑤ 计算偏差 */
    Track_Calc_Error();

    /* ⑥ 变速策略 */
    Track_Update_Speed();

    /* ⑦ 检测赛道元素 */
    Track_Detect_Pattern();

    /* ⑧ 状态机处理 */
    switch (Track.state) {
    case TRACK_STATE_LINE_FOLLOW:
        Track.turn_output = Track_PID_Calculate(&Track.line_pid, 0.0f, Track.error);
        break;

    case TRACK_STATE_START_LINE:
        Track_Handle_StartLine();
        break;

    case TRACK_STATE_LINE_LOST:
        Track_Handle_LineLost();
        break;

    case TRACK_STATE_RIGHT_ANGLE:
        Track_Handle_RightAngle();
        break;

    case TRACK_STATE_CROSS:
        Track_Handle_Cross();
        break;

    default:
        break;
    }

    /* ⑨ 差速输出到电机 */
    Track_Motor_Output();
}

void Track_Start(void)
{
    Track.state = TRACK_STATE_LINE_FOLLOW;
    Track.current_circle = 0;
    Track.right_angle_confirm = 0;
    Track_PID_Reset(&Track.line_pid);
    Track_PID_Reset(&Track.gyro_pid);
}

void Track_Stop(void)
{
    Track.state = TRACK_STATE_FINISHED;
    Track.left_speed  = 0;
    Track.right_speed = 0;
    if (Track.use_motor) {
        Track_Motor_SetLeft(0);
        Track_Motor_SetRight(0);
    }
}

void Track_Set_Circles(uint8_t n)
{
    Track.target_circles = n;
}

void Track_Set_Speed(int32_t base_speed)
{
    Track.base_speed   = base_speed;
    Track.target_speed = base_speed;
}

void Track_Set_TrackPID(float kp, float ki, float kd)
{
    Track_PID_Set_Params(&Track.line_pid, kp, ki, kd);
}

void Track_Calibrate_White(void)
{
    Track_Grayscale_Calibrate_White();
}

void Track_Calibrate_Black(void)
{
    Track_Grayscale_Calibrate_Black();
}

track_state_t Track_Get_State(void)
{
    return Track.state;
}

uint8_t Track_Get_Circle(void)
{
    return Track.current_circle;
}
