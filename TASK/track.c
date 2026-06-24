/**
 * @file    track.c
 * @brief   灰度PID循迹任务调度实现（TASK层）
 * @note    数据流:
 *          Track_Grayscale_Scan → Track_Gray.digital[8] → Track_Calc_Error → PID → 差速 → Track_Motor
 *          Track_Gyro_Read      → Track_Gyro.heading    → 丢线辅助/直角弯道
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
 * 内部函数：偏差计算
 * ============================================================ */

static void Track_Calc_Error(void)
{
    float weighted_sum = 0;
    float total_weight = 0;
    Track_Gray.black_count = 0;

    /* 保存上次偏差（用于丢线时方向判断） */
    Track.last_error = Track.error;

    for (uint8_t i = 0; i < TRACK_GRAY_CHANNEL_NUM; i++) {
        if (Track_Gray.digital[i]) {
            weighted_sum += s_weights[i];
            total_weight  += 1.0f;
            Track_Gray.black_count++;
        }
    }

    if (total_weight > 0) {
        Track.error = weighted_sum / total_weight;
    }
    /* 全白时保持上次 error 不变，由状态机处理 */
}

/* ============================================================
 * 内部函数：赛道元素检测
 * ============================================================ */

static void Track_Detect_Pattern(void)
{
    /* 全黑检测：起点线 */
    if (Track_Gray.black_count >= TRACK_START_LINE_MIN_BLACK) {
        if (Track.state == TRACK_STATE_LINE_FOLLOW) {
            Track.target_heading = Track_Gyro.heading;
            Track.state = TRACK_STATE_START_LINE;
            Track.state_timer = 0;
        }
    }
    /* 直角弯道检测：外侧传感器检测到黑线且偏差较大 */
    else if ((Track_Gray.digital[0] || Track_Gray.digital[7]) &&
             (Track.error > TRACK_RIGHT_ANGLE_THRESHOLD ||
              Track.error < -TRACK_RIGHT_ANGLE_THRESHOLD)) {
        if (Track.state == TRACK_STATE_LINE_FOLLOW) {
            Track.last_state = TRACK_STATE_LINE_FOLLOW;
            Track.right_angle_target = Track_Gyro.heading +
                (Track.error > 0 ? 90.0f : -90.0f);
            Track.state = TRACK_STATE_RIGHT_ANGLE;
            Track.state_timer = 0;
        }
    }
    /* 丢线检测 */
    else if (Track_Gray.black_count < TRACK_LINE_LOST_MAX_BLACK) {
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

    if (Track.state_timer > TRACK_START_LINE_COUNT) {
        Track.current_circle++;
        if (Track.current_circle >= Track.target_circles) {
            Track.state = TRACK_STATE_FINISHED;
            Track.left_speed  = 0;
            Track.right_speed = 0;
        } else {
            Track.state = TRACK_STATE_LINE_FOLLOW;
        }
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
    }

    /* 重新检测到线，恢复循迹 */
    if (Track_Gray.black_count > 0) {
        Track.state = TRACK_STATE_LINE_FOLLOW;
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
    }

    /* 超时保护 */
    if (Track.state_timer > TRACK_RIGHT_ANGLE_TIMEOUT) {
        Track.state = TRACK_STATE_LINE_FOLLOW;
    }
}

/* 差速输出到电机 */
static void Track_Motor_Output(void)
{
    Track.left_speed  = Track.base_speed + (int32_t)Track.turn_output;
    Track.right_speed = Track.base_speed - (int32_t)Track.turn_output;

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
    Track.error          = 0;
    Track.last_error     = 0;
    Track.state          = TRACK_STATE_IDLE;
    Track.last_state     = TRACK_STATE_IDLE;
    Track.target_heading = 0;
    Track.right_angle_target = 0;
    Track.state_timer    = 0;
    Track.line_lost_count = 0;
    Track.target_circles = TRACK_DEFAULT_CIRCLES;
    Track.current_circle = 0;
    Track.turn_output    = 0;
    Track.left_speed     = 0;
    Track.right_speed    = 0;
    Track.base_speed     = TRACK_DEFAULT_BASE_SPEED;
    Track.use_gyro       = true;
    Track.use_motor      = true;

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

    /* ③ 读取陀螺仪数据 */
#if TRACK_USE_MPU6050
    if (Track.use_gyro) {
        Track_Gyro_Read();
    }
#endif

    /* ④ 计算偏差 */
    Track_Calc_Error();

    /* ⑤ 检测赛道元素 */
    Track_Detect_Pattern();

    /* ⑥ 状态机处理 */
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

    default:
        break;
    }

    /* ⑦ 差速输出到电机 */
    Track_Motor_Output();
}

void Track_Start(void)
{
    Track.state = TRACK_STATE_LINE_FOLLOW;
    Track.current_circle = 0;
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
    Track.base_speed = base_speed;
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
