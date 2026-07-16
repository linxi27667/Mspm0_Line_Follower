/**
 * @file    track.c
 * @brief   灰度PID循迹任务调度实现（TASK层 — 纯业务逻辑）
 * @note    数据流:
 *          Grayscale_Update → data_ready → Track_Calc_Error → PID → 差速 → Motor
 *          Imu_Update_Heading → heading → 丢线辅助/直角弯道
 *
 *          本文件不直接操作任何硬件寄存器，全部通过 BSP/APP 层 API 调用
 */
#include "track.h"
#include "app_log.h"
#include "bsp_common.h"
#include "app_safety.h"
#include "imu_health_logic.h"
#include <elog.h>
#include <math.h>

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

static bool Track_Imu_Healthy(void)
{
    return Imu_Health_AllowsMotion(Imu_Sensor.initialized,
                                   Imu_Sensor.data_valid,
                                   Imu_Sensor.calibration_state) &&
           isfinite(Imu_Sensor.heading) && isfinite(Imu_Sensor.gyro_z);
}

/* ============================================================
 * 内部函数：偏差计算（模拟量差比和 — 连续精度）
 * ============================================================ */

static void Track_Calc_Error(void)
{
    /* 保存上次偏差 */
    Track.last_error = Track.error;

    /* 模拟量差比和（归一化值，连续精度）
     * 左侧权重为负，右侧权重为正
     * norm[i] = 1 表示黑线，0 表示白色
     * error = Σ(weight[i] × norm[i]) / Σ(norm[i])
     *
     * 国一方案增强: 最近黑通道(norm最大)权重 ×1.5, 提升急弯响应速度 10-20%
     * 量纲不变(仍是-3.5~+3.5), 仅增大最黑通道在加权平均中的占比 */
    uint8_t max_idx = 0;
    float max_norm = -1.0f;
    for (uint8_t i = 0; i < BSP_GRAY_CHANNEL_NUM; i++) {
        if (Grayscale_Sensor.norm[i] > max_norm) {
            max_norm = Grayscale_Sensor.norm[i];
            max_idx = i;
        }
    }

    float weighted_sum = 0;
    float total_weight = 0;

    for (uint8_t i = 0; i < BSP_GRAY_CHANNEL_NUM; i++) {
        float n = Grayscale_Sensor.norm[i];
        if (i == max_idx) n *= 1.5f;  /* 最近通道高权重, 提升响应 */
        weighted_sum += s_weights[i] * n;
        total_weight  += n;
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
    /* 国一方案: 连续曲率变速 (基于误差绝对值线性插值)
     * |error|=0 → SPEED_STRAIGHT (直道最快)
     * |error|>=CURVE_ERROR_MAX → SPEED_CURVE (弯道最慢)
     * 中间线性过渡, 进弯/出弯平滑无突变
     * 相比二档跳变: 进弯不甩出, 出弯不慢, 平均速度更高 */
    float abs_err = (Track.error >= 0) ? Track.error : -Track.error;
    float ratio = abs_err / TRACK_CURVE_ERROR_MAX;
    if (ratio > 1.0f) ratio = 1.0f;
    Track.target_speed = (int32_t)(Track.speed_straight +
                        (float)(Track.speed_curve - Track.speed_straight) * ratio);

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
    if (Track.state != TRACK_STATE_LINE_FOLLOW) {
        Track.right_angle_confirm = 0;
        Track.line_lost_confirm = 0;
        return;
    }

    /* --- 起点线检测（≥6路黑） — 必须在十字路口之前检测 ---
     * 修复1: 原代码先检测十字(中4路黑+外侧白)，起点线(6路黑)会满足
     *        十字条件被误判为十字路口，导致圈数计数失效。
     * 修复2: 添加 start_line_armed 标志，起点线必须先消失再出现才重新计数，
     *        避免慢速通过时一条起点线被记多圈。 */
    if (Track.start_line_armed &&
        Grayscale_Sensor.black_count >= TRACK_START_LINE_MIN_BLACK) {
        if (Track.state == TRACK_STATE_LINE_FOLLOW) {
            Track.target_heading = Imu_Sensor.heading;
            Track.state = TRACK_STATE_START_LINE;
            Track.state_timer = Bsp_GetTick();
            Track.start_line_armed = false;  /* 需等黑线消失后重新武装 */
            APP_TRACK_LOG_I("TRACK", "LINE_FOLLOW -> START_LINE (bc=%d)",
                   Grayscale_Sensor.black_count);
        }
        return;
    }

    /* 起点线未检测到时，若黑通道数降到阈值以下，重新武装起点线检测 */
    if (!Track.start_line_armed &&
        Grayscale_Sensor.black_count < TRACK_START_LINE_MIN_BLACK) {
        Track.start_line_armed = true;
    }

    /* --- 十字路口检测 --- */
    /* 中间4路(S2~S5)全黑 + 外侧至少1路白 + 非起点线(黑通道<6) */
    uint8_t mid_black = 0;
    for (uint8_t i = 2; i <= 5; i++) {
        if (Grayscale_Sensor.digital[i]) mid_black++;
    }
    uint8_t outer_white = (!Grayscale_Sensor.digital[0] || !Grayscale_Sensor.digital[7]) ? 1 : 0;

    if (mid_black >= TRACK_CROSS_MIN_BLACK && outer_white &&
        Grayscale_Sensor.black_count < TRACK_START_LINE_MIN_BLACK) {
        if (Track.state == TRACK_STATE_LINE_FOLLOW) {
            Track.state = TRACK_STATE_CROSS;
            Track.state_timer = Bsp_GetTick();
            APP_TRACK_LOG_I("TRACK", "LINE_FOLLOW -> CROSS (bc=%d)",
                   Grayscale_Sensor.black_count);
            return;
        }
    }

    /* --- 直角弯道检测（国一方案: 多条件多帧确认） ---
     * 单一条件漏检率高, 国一方案必有多条件冗余:
     *   条件1 cond_outer: 原始 S0/S7 黑 + 大误差 (黑线摆到外侧)
     *   条件2 cond_accum: 误差累积超限 (弯道持续大误差, 说明弯很急)
     *   条件3 cond_rate:  角速度超限 (车体快速旋转, 说明进入急弯)
     * 任一条件持续满足 CONFIRM_FRAMES 帧即触发, 覆盖:
     *   - 黑线没摆到外侧 (cond_outer 漏) → cond_accum/cond_rate 兜底
     *   - 弯前误差不足 (cond_outer 漏)   → cond_rate 兜底 */
    {
        bool cond_outer = (Grayscale_Sensor.digital[0] || Grayscale_Sensor.digital[7]) &&
                          (Track.error > Track.right_angle_threshold ||
                           Track.error < -Track.right_angle_threshold);
        bool cond_accum = (Track.error_accum > TRACK_RIGHT_ANGLE_ERROR_INTEGRAL ||
                           Track.error_accum < -TRACK_RIGHT_ANGLE_ERROR_INTEGRAL);
        bool cond_rate  = (Track.gyro_rate > TRACK_RIGHT_ANGLE_GYRO_RATE ||
                           Track.gyro_rate < -TRACK_RIGHT_ANGLE_GYRO_RATE);

        bool gyro_available = Track.use_gyro && Track_Imu_Healthy();

        if (gyro_available && (cond_outer || cond_accum || cond_rate)) {
            Track.right_angle_confirm++;
            if (Track.right_angle_confirm >= TRACK_RIGHT_ANGLE_CONFIRM_FRAMES) {
                if (Track.state == TRACK_STATE_LINE_FOLLOW) {
                    Track.last_state = TRACK_STATE_LINE_FOLLOW;
                    /* 旋转方向: 根据 last_error 符号 (黑线最后偏哪边就往哪边转)
                     * 用 last_error 比 error 更稳定 (进入弯道瞬间 error 可能跳变) */
                    float direction = Track_RightAngle_Direction(
                        Track.error, Track.last_error, Track.gyro_rate);
                    Track.right_angle_direction = direction;
                    Track.right_angle_entry_heading = Imu_Sensor.heading;
                    Track.right_angle_target =
                        Imu_Sensor.heading + direction * TRACK_RIGHT_ANGLE_TARGET_ANGLE;
                    Track.state = TRACK_STATE_RIGHT_ANGLE;
                    Track.state_timer = Bsp_GetTick();
                    Track.right_angle_confirm = 0;
                    Pid_Reset(&Track.gyro_pid);
                    APP_TRACK_LOG_I("TRACK", "LINE_FOLLOW -> RIGHT_ANGLE (err=%d accum=%d rate=%d target=%d)",
                           (int)Track.error, (int)Track.error_accum, (int)Track.gyro_rate,
                           (int)Track.right_angle_target);
                    Track.error_accum = 0;  /* 清零累积, 避免出弯后重复触发 */
                }
            }
        } else {
            /* 条件不满足，重置确认计数 */
            Track.right_angle_confirm = 0;
        }
    }

    /* --- 丢线检测（多帧确认，抗瞬时干扰） --- */
    if (Grayscale_Sensor.black_count < TRACK_LINE_LOST_MAX_BLACK) {
        Track.line_lost_confirm++;
        if (Track.line_lost_confirm >= TRACK_LINE_LOST_CONFIRM_FRAMES) {
            if (Track.state == TRACK_STATE_LINE_FOLLOW) {
                Track.last_state = TRACK_STATE_LINE_FOLLOW;
                Track.target_heading = Imu_Sensor.heading;
                Track.state = TRACK_STATE_LINE_LOST;
                Track.line_lost_count = 0;
                Track.state_timer = Bsp_GetTick();
                Pid_Reset(&Track.gyro_pid);  /* 进入丢线时复位 gyro_pid 防积分突跳 */
                APP_TRACK_LOG_W("TRACK", "LINE_FOLLOW -> LINE_LOST (hdg=%d)",
                       (int)Imu_Sensor.heading);
            }
        }
    } else {
        Track.line_lost_confirm = 0;
    }
}

/* ============================================================
 * 内部函数：立即停车（切开环+直写PWM=0，避免闭环下电机持续运转）
 * ============================================================ */
static void Track_Motor_Stop_Immediate(void)
{
    Track.left_speed  = 0;
    Track.right_speed = 0;
    Track.turn_output = 0;
    if (Track.use_motor) {
        App_Motor_Enable_Speed_PID(false);
        Bsp_Motor_Write_Pwm(&Motor_Left, 0);
        Bsp_Motor_Write_Pwm(&Motor_Right, 0);
    }
}

static void Track_Rotate_End(const char *result)
{
    APP_ROTATE_LOG_I("ROTATE", "end result=%s actual=%d error=%d",
                     result, (int)Track.rotate_actual_deg,
                     (int)Track.rotate_error_deg);
    Track.rotate_result = result;
    Track.rotate_settle_frames = 0;
    Track.state = TRACK_STATE_IDLE;
    Track.left_speed = 0;
    Track.right_speed = 0;
    Track.turn_output = 0;

    if (Track.use_motor) {
        Motor_Set_Speed(0);
        Motor_Right_Set_Speed(0);
        App_Motor_Enable_Speed_PID(false);
        Bsp_Motor_Write_Pwm(&Motor_Left, 0);
        Bsp_Motor_Write_Pwm(&Motor_Right, 0);
    }

    if (Safety_GetState() != SAFETY_STATE_FAULT) {
        Safety_TransitionAfterRotation();
    }
}

/* Angle P plus measured yaw-rate D. Do not use Pid_Compute here: its D term
 * is a per-control-tick angle difference, while MPU gyro_z is the physical
 * derivative required to brake the chassis before it reaches the target. */
static void Track_Apply_Rotate_PD(float angle_error_deg, float gyro_rate_deg_s,
                                  float max_speed, int32_t min_speed,
                                  float coast_output)
{
    float output = USER_ROTATE_PID_KP * angle_error_deg -
                   USER_ROTATE_PID_KD_RATE * gyro_rate_deg_s;
    int32_t speed;
    int32_t desired_left = 0;
    int32_t desired_right = 0;

    if (output > max_speed) {
        output = max_speed;
    } else if (output < -max_speed) {
        output = -max_speed;
    }
    Track.turn_output = output;

    /* Near the target, forcing a motor's minimum speed causes a limit cycle.
     * Let the vehicle coast until angle/rate demand is large enough to brake. */
    if (Track_Abs_Float(output) < coast_output) {
        speed = 0;
    } else {
        speed = (int32_t)Track_Abs_Float(output);
        if (speed < min_speed) speed = min_speed;
        Track_Rotate_Command(output, speed, &desired_left, &desired_right);
    }

    Track.left_speed = Track_Slew_Command(Track.left_speed, desired_left,
                                          USER_ROTATE_SPEED_SLEW_STEP);
    Track.right_speed = Track_Slew_Command(Track.right_speed, desired_right,
                                           USER_ROTATE_SPEED_SLEW_STEP);
}

static void Track_Handle_Rotate(void)
{
    uint32_t now = Bsp_GetTick();

    if (!Track_Imu_Healthy()) {
        Track_Rotate_End("imu_unavailable");
        return;
    }
    if (!Safety_AllowsMotorOutput()) {
        Track_Rotate_End("safety_revoked");
        return;
    }

    Track.rotate_actual_deg = Imu_Sensor.heading - Track.rotate_heading_baseline;
    Track.rotate_error_deg = Track_Rotate_Error(Track.rotate_heading_baseline,
                                                 Imu_Sensor.heading,
                                                 Track.rotate_target_deg);

    if (Track_Rotate_Timeout(now, Track.rotate_started_at,
                             Track.rotate_timeout_ms)) {
        Track_Rotate_End("rotate_timeout");
        return;
    }

    bool angle_inside = Track_Rotate_AngleInside(Track.rotate_error_deg);
    bool inside_tolerance = Track_Rotate_Complete(
        Track.rotate_error_deg, Track_Abs_Float(Imu_Sensor.gyro_z));
    Track.rotate_settle_frames = Track_Rotate_UpdateSettleFrames(
        Track.rotate_settle_frames, inside_tolerance);
    /* Once the angle is inside the acceptance band, coast to remove residual
     * yaw energy. Active rate braking here causes a low-speed limit cycle. */
    if (angle_inside) {
        Track.left_speed = 0;
        Track.right_speed = 0;
        Track.turn_output = 0;
        Motor_Set_Speed(0);
        Motor_Right_Set_Speed(0);
        if (Track_Rotate_Settled(Track.rotate_settle_frames,
                                 USER_ROTATE_SETTLE_FRAMES)) {
            Track_Rotate_End("complete");
        }
        return;
    }

    float error_abs = Track_Abs_Float(Track.rotate_error_deg);
    if (error_abs < USER_ROTATE_PID_BLEND_ZONE_DEG) {
        float speed_limit = Track_Rotate_SpeedLimit(
            error_abs,
            USER_ROTATE_PID_FINE_ZONE_DEG,
            USER_ROTATE_PID_BLEND_ZONE_DEG,
            USER_ROTATE_PID_FINE_MAX_SPEED,
            USER_ROTATE_PID_MAX_SPEED);
        Track_Apply_Rotate_PD(Track.rotate_error_deg, Imu_Sensor.gyro_z,
                              speed_limit, USER_ROTATE_PID_FINE_MIN_SPEED,
                              USER_ROTATE_PID_COAST_OUTPUT);
    } else {
        Track_Apply_Rotate_PD(Track.rotate_error_deg, Imu_Sensor.gyro_z,
                              USER_ROTATE_PID_MAX_SPEED,
                              USER_ROTATE_PID_MIN_SPEED,
                              USER_ROTATE_PID_COAST_OUTPUT);
    }
    Motor_Set_Speed(Track.left_speed);
    Motor_Right_Set_Speed(Track.right_speed);
}

static void Track_Heading_Hold_End(const char *result)
{
    Track.heading_hold_result = result;
    Track.state = TRACK_STATE_IDLE;
    Track.left_speed = 0;
    Track.right_speed = 0;
    Track.turn_output = 0;

    if (Track.use_motor) {
        Motor_Set_Speed(0);
        Motor_Right_Set_Speed(0);
        App_Motor_Enable_Speed_PID(false);
        Bsp_Motor_Write_Pwm(&Motor_Left, 0);
        Bsp_Motor_Write_Pwm(&Motor_Right, 0);
    }
    if (Safety_GetState() != SAFETY_STATE_FAULT) {
        Safety_TransitionAfterRotation();
    }
}

static void Track_Handle_Heading_Hold(void)
{
    if (!Track_Imu_Healthy()) {
        Track_Heading_Hold_End("imu_unavailable");
        return;
    }
    if (!Safety_AllowsMotorOutput()) {
        Track_Heading_Hold_End("safety_revoked");
        return;
    }

    Track.heading_hold_actual = Imu_Sensor.heading;
    Track.heading_hold_error = Track.heading_hold_target - Track.heading_hold_actual;
    if (Track_Abs_Float(Track.heading_hold_error) <= USER_HEADING_HOLD_DEADBAND_DEG &&
        Track_Abs_Float(Imu_Sensor.gyro_z) <= USER_HEADING_HOLD_SETTLE_RATE_DEG_S) {
        Track.left_speed = 0;
        Track.right_speed = 0;
        Motor_Set_Speed(0);
        Motor_Right_Set_Speed(0);
        return;
    }

    Track_Apply_Rotate_PD(Track.heading_hold_error, Imu_Sensor.gyro_z,
                          USER_HEADING_HOLD_MAX_SPEED, USER_HEADING_HOLD_MIN_SPEED,
                          USER_HEADING_HOLD_COAST_OUTPUT);
    Motor_Set_Speed(Track.left_speed);
    Motor_Right_Set_Speed(Track.right_speed);
}

/* ============================================================
 * 内部函数：状态处理
 * ============================================================ */

/* 起点线处理：计数圈数 */
static void Track_Handle_StartLine(void)
{
    uint32_t now = Bsp_GetTick();

    /* 起点线持续超过阈值视为有效过线 */
    if (Track_Timeout_Reached(now, Track.state_timer,
                              TRACK_START_LINE_HOLD_MS)) {
        Track.current_circle++;
        if (Track.current_circle >= Track.target_circles) {
            Track.state = TRACK_STATE_FINISHED;
            Track_Motor_Stop_Immediate();   /* 立即停车(安全) */
            Safety_TransitionToFinished();  /* 通知 Safety 持续切断 */
        APP_TRACK_LOG_I("TRACK", "FINISHED! circles=%d/%d", Track.current_circle, Track.target_circles);
        } else {
            Track.state = TRACK_STATE_LINE_FOLLOW;
        APP_TRACK_LOG_I("TRACK", "Circle %d/%d completed", Track.current_circle, Track.target_circles);
        }
        return;
    }

    /* 起点线消失（black_count 降到阈值以下）也退出 */
    if (Grayscale_Sensor.black_count < TRACK_START_LINE_MIN_BLACK) {
        Track.state = TRACK_STATE_LINE_FOLLOW;
        return;
    }

    /* 起点线期间保持直行 */
    Track.turn_output = 0;
}

/* 丢线处理：用陀螺仪维持航向
 * 国一方案参考: 丢线时锁定航向角直行,用编码器脉冲数判断是否到达下一段
 * 我们方案: 陀螺仪PID维持航向 + last_error方向修正 + 超时停车
 * 国一方案恢复条件: black_count>=2 (单点噪声不恢复, 避免误恢复到错误位置) */
static void Track_Handle_LineLost(void)
{
    uint32_t now = Bsp_GetTick();
    Track.line_lost_count = (uint32_t)(now - Track.state_timer);

    if (Track.use_gyro && Track_Imu_Healthy()) {
        /* 修复: 统一用完整 PID(含 D 项)而非仅 P 控制，与直角弯道策略一致。
         * Pid_Compute 内部 error = target - feedback = target_heading - heading */
        Track.turn_output = Pid_Compute(&Track.gyro_pid,
                                        Track.target_heading,
                                        Imu_Sensor.heading);
    } else {
        /* 无陀螺仪时: 用上次误差方向修正(last_error符号=方向记忆),逐渐衰减 */
        float decay = 1.0f - (float)Track.line_lost_count / TRACK_LINE_LOST_TIMEOUT;
        if (decay < 0.3f) decay = 0.3f;  /* 最低保留30%修正 */
        Track.turn_output = Track.last_error * TRACK_LINE_LOST_GAIN * decay;
    }

    /* 丢线超时停车 */
    if (Track_Timeout_Reached(now, Track.state_timer,
                              TRACK_LINE_LOST_TIMEOUT)) {
        Track.state = TRACK_STATE_FINISHED;
        Track_Motor_Stop_Immediate();   /* 立即停车(安全) */
        APP_TRACK_LOG_W("TRACK", "LINE_LOST timeout -> FINISHED");
        return;
    }

    /* 重新检测到线，恢复循迹 (国一方案: black_count>=2 才恢复, 防单点噪声误恢复)
     * last_error 符号天然保留丢线前方向, Track_Calc_Error 全白时不更新 error */
    if (Grayscale_Sensor.black_count >= 2) {
        Track.state = TRACK_STATE_LINE_FOLLOW;
        Pid_Reset(&Track.line_pid);
        Track.line_lost_confirm = 0;    /* 修复: 复位确认计数，避免立即重入 LINE_LOST */
        APP_TRACK_LOG_I("TRACK", "LINE_LOST -> LINE_FOLLOW (recovered, bc=%d)",
               Grayscale_Sensor.black_count);
    }
}

/* 直角弯道处理：陀螺仪精确旋转90度 */
static void Track_Handle_RightAngle(void)
{
    uint32_t now = Bsp_GetTick();

    if (!Track.use_gyro || !Track_Imu_Healthy()) {
        Track.state = (Grayscale_Sensor.black_count >= 2)
                    ? TRACK_STATE_LINE_FOLLOW
                    : TRACK_STATE_LINE_LOST;
        Track.state_timer = now;
        Track.line_lost_count = 0;
        Pid_Reset(&Track.line_pid);
        Pid_Reset(&Track.gyro_pid);
        APP_TRACK_LOG_W("TRACK", "RIGHT_ANGLE aborted: gyro unavailable");
        return;
    }

    float angle_error = Track.right_angle_target - Imu_Sensor.heading;
    float turned_abs = Track_Abs_Float(Imu_Sensor.heading -
                                       Track.right_angle_entry_heading);
    uint8_t center_black = 0;
    for (uint8_t i = 2; i <= 5; i++) {
        if (Grayscale_Sensor.digital[i]) center_black++;
    }

    /* 方形赛道直角弯中强制低速，避免入弯速度继承直道速度 */
    Track.target_speed = Track.speed_curve;
    if (Track.base_speed > Track.speed_curve) {
        Track.base_speed = Track.speed_curve;
    }

    Track.turn_output = Pid_Compute(&Track.gyro_pid,
                                     Track.right_angle_target,
                                     Imu_Sensor.heading);

    /* 转过最小角度后, 中间通道重新捕到线即可提前退出; 接近目标角兜底退出 */
    if (Track_RightAngle_ShouldExit(turned_abs, angle_error, center_black,
                                    Grayscale_Sensor.black_count)) {
        Track.state = TRACK_STATE_LINE_FOLLOW;
        Pid_Reset(&Track.line_pid);
        Track.error_accum = 0;
        Track.right_angle_confirm = 0;
        Track.right_angle_count++;  /* 正方形计圈: 直角完成计数 */
        Track_Check_RightAngle_Completion();
        APP_TRACK_LOG_I("TRACK", "RIGHT_ANGLE -> LINE_FOLLOW (turn=%d err=%d center=%d bc=%d ra=%d)",
               (int)turned_abs, (int)angle_error, center_black,
               Grayscale_Sensor.black_count, Track.right_angle_count);
        return;
    }

    /* 超时保护 */
    if (Track_Timeout_Reached(now, Track.state_timer,
                              TRACK_RIGHT_ANGLE_TIMEOUT)) {
        Track.state = TRACK_STATE_LINE_FOLLOW;
        Pid_Reset(&Track.line_pid);
        Track.error_accum = 0;
        Track.right_angle_confirm = 0;
        Track.right_angle_count++;  /* 超时退出也计数(已完成转向) */
        Track_Check_RightAngle_Completion();
        APP_TRACK_LOG_W("TRACK", "RIGHT_ANGLE timeout -> LINE_FOLLOW (turn=%d err=%d center=%d bc=%d ra=%d)",
               (int)turned_abs, (int)angle_error, center_black,
               Grayscale_Sensor.black_count, Track.right_angle_count);
    }
}

/* 正方形计圈检查: 4个直角=1圈, 4*N个直角后停车
 * 由 Track_Handle_RightAngle 在每次直角完成时调用 */
void Track_Check_RightAngle_Completion(void)
{
    uint16_t target_total = (uint16_t)Track.target_circles * 4u;
    if (Track.right_angle_count >= target_total) {
        Track.current_circle = Track.target_circles;
        Track.state = TRACK_STATE_FINISHED;
        Track_Motor_Stop_Immediate();
        Safety_TransitionToFinished();
        APP_TRACK_LOG_I("TRACK", "FINISHED! right_angles=%d/%d (circles=%d/%d)",
               Track.right_angle_count, target_total,
               Track.current_circle, Track.target_circles);
        return;
    }
    /* 每4个直角更新圈数（用于遥测显示） */
    Track.current_circle = (uint8_t)(Track.right_angle_count / 4u);
}

/* 十字路口处理：保持当前方向直行通过 */
static void Track_Handle_Cross(void)
{
    uint32_t now = Bsp_GetTick();
    uint32_t elapsed = (uint32_t)(now - Track.state_timer);

    /* 十字路口期间保持直行（turn_output=0） */
    Track.turn_output = 0;

    /* 通过计数超过阈值，视为已通过 */
    if (elapsed >= TRACK_CROSS_PASS_MS) {
        Track.state = TRACK_STATE_LINE_FOLLOW;
    }

    /* 如果检测到全白（偏离十字），也退出 */
    if (Grayscale_Sensor.black_count < 1 && elapsed > 50u) {
        Track.state = TRACK_STATE_LINE_FOLLOW;
    }
}

/* 差速输出到电机（内侧电机最低速度限制） */
static void Track_Motor_Output(void)
{
    /* 双重保险: Track 状态机 + Safety 授权
     * Safety_AllowsMotorOutput() 是唯一权威授权 */
    if (!Track_State_Allows_Motor(Track.state) ||
        !Safety_AllowsMotorOutput()) {
        Track_Motor_Stop_Immediate();
        return;
    }

    Track.left_speed  = Track.base_speed + (int32_t)Track.turn_output;
    Track.right_speed = Track.base_speed - (int32_t)Track.turn_output;

    /* 内侧电机最低速度限制（不允许反转，避免急转抖动）
     * 修复: 原代码双 if 互斥条件在两轮都低于 MIN 时均不执行，
     * 导致内侧电机可反转。改为分别钳位。 */
    if (Track.left_speed  < TRACK_MOTOR_INNER_MIN) Track.left_speed  = TRACK_MOTOR_INNER_MIN;
    if (Track.right_speed < TRACK_MOTOR_INNER_MIN) Track.right_speed = TRACK_MOTOR_INNER_MIN;

    /* 电机速度限幅 */
    if (Track.left_speed >  TRACK_MOTOR_SPEED_MAX) Track.left_speed  =  TRACK_MOTOR_SPEED_MAX;
    if (Track.left_speed <  TRACK_MOTOR_SPEED_MIN) Track.left_speed  =  TRACK_MOTOR_SPEED_MIN;
    if (Track.right_speed > TRACK_MOTOR_SPEED_MAX) Track.right_speed =  TRACK_MOTOR_SPEED_MAX;
    if (Track.right_speed < TRACK_MOTOR_SPEED_MIN) Track.right_speed =  TRACK_MOTOR_SPEED_MIN;

    if (Track.use_motor) {
        Motor_Set_Speed(Track.left_speed);
        Motor_Right_Set_Speed(Track.right_speed);
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
    Track.error_accum        = 0;
    Track.state              = TRACK_STATE_IDLE;
    Track.last_state         = TRACK_STATE_IDLE;
    Track.target_heading     = 0;
    Track.right_angle_target = 0;
    Track.right_angle_entry_heading = 0;
    Track.right_angle_direction = 0;
    Track.state_timer        = 0;
    Track.line_lost_count    = 0;
    Track.gyro_rate          = 0;
    Track.heading_baseline   = 0;
    Track.rotate_heading_baseline = 0;
    Track.rotate_target_deg  = 0;
    Track.rotate_actual_deg  = 0;
    Track.rotate_error_deg   = 0;
    Track.rotate_started_at  = 0;
    Track.rotate_timeout_ms  = 0;
    Track.rotate_settle_frames = 0;
    Track.rotate_result      = "idle";
    Track.heading_hold_target = 0;
    Track.heading_hold_actual = 0;
    Track.heading_hold_error = 0;
    Track.heading_hold_result = "idle";
    Track.right_angle_confirm = 0;
    Track.line_lost_confirm  = 0;
    Track.start_line_armed   = true;  /* 初始可检测起点线 */
    Track.target_circles     = TRACK_DEFAULT_CIRCLES;
    Track.current_circle     = 0;
    Track.right_angle_count  = 0;
    Track.turn_output        = 0;
    Track.left_speed         = 0;
    Track.right_speed        = 0;
    Track.base_speed         = TRACK_DEFAULT_BASE_SPEED;
    Track.target_speed       = TRACK_DEFAULT_BASE_SPEED;
    Track.use_gyro           = true;
    Track.use_motor          = true;

    /* AI 调参运行时可调参数初始化（从宏默认值载入） */
    Track.gyro_damp             = TRACK_LINE_FOLLOW_GYRO_DAMP;
    Track.speed_straight        = TRACK_SPEED_STRAIGHT;
    Track.speed_curve           = TRACK_SPEED_CURVE;
    Track.right_angle_threshold = TRACK_RIGHT_ANGLE_THRESHOLD;

    /* PID 初始化（使用BSP层 bsp_pid_t） */
    Pid_Init(&Track.line_pid,
             TRACK_LINE_PID_KP, TRACK_LINE_PID_KI, TRACK_LINE_PID_KD,
             TRACK_LINE_PID_ILIMIT, TRACK_LINE_PID_OLIMIT);
    Track.line_pid.deriv_alpha = TRACK_LINE_PID_DERIV_ALPHA;  /* 不完全微分 */

    Pid_Init(&Track.gyro_pid,
             TRACK_GYRO_PID_KP, TRACK_GYRO_PID_KI, TRACK_GYRO_PID_KD,
             TRACK_GYRO_PID_ILIMIT, TRACK_GYRO_PID_OLIMIT);
    Track.gyro_pid.deriv_alpha = 0.4f;  /* 修复: 启用微分滤波，抑制陀螺仪噪声 */

    App_Grayscale_Init();
    (void)App_Imu_Init();
    Imu_Calibration_Start();
    App_Motor_Init();

    /* ====== 灰度校准策略: 自动校准白色(一次) + 手动K4校准黑色 ======
     * 传感器硬件现状: 8通道极性不一致(部分反向)。
     * 方案:
     *   1. 开机时车放白地 → 自动校准每通道 white (只一次)
     *   2. black 初始化为 white 的一半 (假设黑线ADC约为白地一半)
     *      这样滞回区间大致在 [white/4, 3*white/4], 白地ADC>3*white/4判白
     *   3. 手动 K4 校准黑色 (车放黑线按K4, 直接覆盖black为真实值)
     *   4. 不做动态跟踪 (实测会把black拉低到0导致失效)
     * white 保持开机值不更新, black 保持初始值直到K4校准。
     * 滞回比较器通过 black/white 大小自适应极性。 */
    APP_TRACK_LOG_I("TRACK", "Gray auto-cal WHITE (place car on white surface):");
    /* 扫描3轮让ADC稳定 + 取每通道当前ADC作为white */
    for (uint8_t round = 0; round < 3; round++) {
        for (uint8_t i = 0; i < 8; i++) {
            Grayscale_Update();
            Bsp_Delay_ms(3);
        }
    }
    for (uint8_t i = 0; i < 8; i++) {
        uint16_t adc = Grayscale_Sensor.analog[i];
        Grayscale_Sensor.white[i] = adc;
        /* black 初始化为 white/2 (合理猜测: 黑线ADC约为白地一半)
         * 用户按K4手动校准后会更新为真实黑线值 */
        Grayscale_Sensor.black[i] = adc / 2;
        Grayscale_Sensor.digital[i] = 0;
        APP_TRACK_LOG_I("TRACK", "  S%d: ADC=%u white=%u black=%u",
               i, adc, adc, Grayscale_Sensor.black[i]);
    }
    Grayscale_Sensor.calibrated = 1;

    /* 启用速度PID闭环（编码器反馈修正PWM） */
    /* Safety owns motor authorization; startup must leave both bridges off. */
    App_Motor_Enable_Speed_PID(false);
    Bsp_Motor_Write_Pwm(&Motor_Left, 0);
    Bsp_Motor_Write_Pwm(&Motor_Right, 0);
}

void Track_Update(void)
{
    /* Safety_ControlTick() 已在外部 5ms 节拍调用并授权，
     * 本函数仅在 motor_allowed=true 时被调用。
     * 灰度扫描已由 main.c 顶层 Grayscale_Update() 推进。 */

    /* ① 真实 dt 计算 (Safety 节拍已保证 5ms 周期，此处测量实际间隔) */
    static uint32_t last_update_tick = 0;
    uint32_t now = Bsp_GetTick();
    uint32_t elapsed_ms = (last_update_tick == 0) ? TRACK_UPDATE_PERIOD_MS
                                                  : (uint32_t)(now - last_update_tick);
    if (elapsed_ms > 20u) elapsed_ms = 20u;
    float dt = elapsed_ms / 1000.0f;
    last_update_tick = now;

    /* ② 读取 IMU 并更新航向。任何无效帧都在本控制节拍内撤销输出。 */
    if (Track.use_gyro) {
        if (!Imu_Update_Heading(dt) || !Track_Imu_Healthy()) {
            Track.gyro_rate = 0.0f;
            Track_Motor_Stop_Immediate();
            Safety_NotifySensorAbnormal();
            APP_TRACK_LOG_W("TRACK", "IMU invalid -> immediate motor stop");
            return;
        }
        /* 记录当前角速度 (已减零偏), 供 LINE_FOLLOW 阻尼和上位机遥测使用 */
        Track.gyro_rate = Imu_Sensor.gyro_z;
    }

    /* 原地旋转不能等待灰度帧，必须每个5ms控制周期闭环。 */
    if (Track.state == TRACK_STATE_ROTATE) {
        Track_Handle_Rotate();
        return;
    }
    if (Track.state == TRACK_STATE_HEADING_HOLD) {
        Track_Handle_Heading_Hold();
        return;
    }

    /* ③ 等待灰度传感器完成一轮完整扫描（数据同步） */
    if (!Grayscale_Sensor.data_ready) return;
    Grayscale_Sensor.data_ready = 0;  /* 消费标志 */

    /* ③.5 传感器健康度检测 → 通知 Safety 模块
     * 检测条件: 8路ADC全部低于基准一半(传感器抬起/悬空/被遮挡)
     * 处理: 通知 Safety，由 Safety 决定是否停车 (单一授权原则) */
    uint8_t abnormal_count = 0;
    for (uint8_t i = 0; i < BSP_GRAY_CHANNEL_NUM; i++) {
        uint16_t min_base = (Grayscale_Sensor.white[i] < Grayscale_Sensor.black[i])
                          ? Grayscale_Sensor.white[i] : Grayscale_Sensor.black[i];
        if (Grayscale_Sensor.analog[i] < (uint16_t)(min_base / 2)) {
            abnormal_count++;
        }
    }
    if (abnormal_count >= 6 && Track.state == TRACK_STATE_LINE_FOLLOW) {
        APP_TRACK_LOG_W("TRACK", "SENSOR ABNORMAL (abnormal=%d) -> notify Safety", abnormal_count);
        Safety_NotifySensorAbnormal();
        return;  /* Safety 下个 tick 会切断电机 */
    }

    /* ⑤ 计算偏差 */
    Track_Calc_Error();

    /* ⑤.5 误差累积积分 (直角弯检测用, 衰减式)
     * 连续大误差累积, 小误差衰减, 用于检测急弯 */
    Track.error_accum = Track.error_accum * 0.9f + Track.error;

    /* ⑥ 变速策略 */
    Track_Update_Speed();

    /* ⑦ 检测赛道元素 */
    Track_Detect_Pattern();

    /* ⑧ 状态机处理 */
    switch (Track.state) {
    case TRACK_STATE_LINE_FOLLOW:
        /* 国一方案: LINE_FOLLOW 串级混合控制
         * 主控: 灰度 PID 输出位置转向量 (line_turn)
         * 阻尼: 陀螺仪角速度抑制灰度传感器噪声引起的左右抖动 (gyro_damp)
         * 极性: 右转时 gyro_z>0, 阻尼项 -gyro_damp*gyro_z 抑制右转, 反之亦然
         * 效果: 直行稳(抖动被阻尼), 弯道灵(角速度小阻尼小不影响跟踪)
         * IMU 失效时由本节拍入口立即停车，禁止使用陈旧航向。 */
        {
            float line_turn = Pid_Compute(&Track.line_pid, Track.error, 0.0f);
            float gyro_damp = 0.0f;
            if (Track.use_gyro && Track_Imu_Healthy()) {
                gyro_damp = Track.gyro_rate * Track.gyro_damp;
            }
            Track.turn_output = line_turn - gyro_damp;
        }
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

    if (!Track_State_Allows_Motor(Track.state)) {
        Track_Motor_Stop_Immediate();
        return;
    }

    /* ⑨ 差速输出到电机（BSP层API） */
    Track_Motor_Output();

    /* 速度PID闭环更新已移至 main.c 的 5ms 独立节拍，
     * 保证 IDLE/FINISHED 状态下也能更新(避免电机保持最后PWM)。 */
}

bool Track_Start(void)
{
    if (!Track_Imu_Healthy()) {
        APP_TRACK_LOG_W("TRACK", "Start rejected: imu_unavailable");
        return false;
    }

    /* 检查黑色校准状态,未校准时警告(允许启动但循迹不可靠) */
    if (!Grayscale_Sensor.black_calibrated) {
        APP_TRACK_LOG_W("TRACK", "WARNING: Black NOT calibrated! Place car on black line and press K4");
    }

    /* Safety 授权进入 RUNNING（校准未完成会被 Safety 拒绝） */
    Safety_TransitionToRunning();
    if (!Safety_AllowsMotorOutput()) {
        APP_TRACK_LOG_W("TRACK", "Start blocked by Safety (state=%s)",
               Safety_StateName(Safety_GetState()));
        return false;
    }

    Track.state = TRACK_STATE_LINE_FOLLOW;
    Track.current_circle = 0;
    Track.right_angle_count = 0;
    Track.right_angle_confirm = 0;
    Track.line_lost_confirm = 0;
    Track.start_line_armed = true;
    Pid_Reset(&Track.line_pid);
    Pid_Reset(&Track.gyro_pid);
    if (Track.use_motor) {
        App_Motor_Enable_Speed_PID(true);
    }
    APP_TRACK_LOG_I("TRACK", "Tracking started (circles=%d speed=%d black_cal=%d)",
           Track.target_circles, Track.base_speed,
           Grayscale_Sensor.black_calibrated);
    return true;
}

void Track_Stop(void)
{
    if (Track.state == TRACK_STATE_ROTATE) {
        Track_Rotate_End("stopped");
        return;
    }
    if (Track.state == TRACK_STATE_HEADING_HOLD) {
        Track_Heading_Hold_End("stopped");
        return;
    }

    Track.state = TRACK_STATE_FINISHED;
    Track.left_speed  = 0;
    Track.right_speed = 0;
    Track.turn_output = 0;
    if (Track.use_motor) {
        /* 修复: 闭环模式下 Motor_Set_Speed 只更新 target_speed，
         * 不写 PWM；而 Track_Update 在 FINISHED 状态直接 return，
         * 速度 PID 永远不会再执行 → 电机保持最后一次 PWM 持续运转。
         * 必须切开环 + 直写 PWM=0 才能真正停车。 */
        App_Motor_Enable_Speed_PID(false);
        Bsp_Motor_Write_Pwm(&Motor_Left, 0);
        Bsp_Motor_Write_Pwm(&Motor_Right, 0);
    }
    /* 通知 Safety 进入 FINISHED 态（持续切断电机） */
    Safety_TransitionToFinished();
    APP_TRACK_LOG_I("TRACK", "Tracking stopped (state=FINISHED)");
}

bool Track_Start_Rotation(float target_deg)
{
    uint32_t target_abs;

    Track.rotate_result = "rejected";
    if (!Track_Rotate_TargetValid(target_deg)) {
        Track.rotate_result = "invalid_angle";
        APP_ROTATE_LOG_W("ROTATE", "reject reason=invalid_angle target=%d", (int)target_deg);
        return false;
    }
    if (Track.state != TRACK_STATE_IDLE) {
        Track.rotate_result = "not_ready";
        APP_ROTATE_LOG_W("ROTATE", "reject reason=not_ready track_state=%d",
                         (int)Track.state);
        return false;
    }
    if (!Track_Imu_Healthy()) {
        Track.rotate_result = "imu_unavailable";
        APP_ROTATE_LOG_W("ROTATE", "reject reason=imu_unavailable");
        return false;
    }

    if (!Safety_TransitionToRotation() || !Safety_AllowsMotorOutput()) {
        Track.rotate_result = "safety_rejected";
        APP_ROTATE_LOG_W("ROTATE", "reject reason=safety_rejected");
        return false;
    }

    target_abs = (uint32_t)Track_Abs_Float(target_deg);
    Track.rotate_heading_baseline = Imu_Sensor.heading;
    Track.rotate_target_deg = target_deg;
    Track.rotate_actual_deg = 0;
    Track.rotate_error_deg = target_deg;
    Track.rotate_started_at = Bsp_GetTick();
    Track.rotate_timeout_ms = USER_ROTATE_TIMEOUT_BASE_MS +
                              target_abs * USER_ROTATE_TIMEOUT_PER_DEG_MS;
    Track.rotate_settle_frames = 0;
    Track.rotate_result = "running";
    Track.state = TRACK_STATE_ROTATE;
    Track.left_speed = 0;
    Track.right_speed = 0;
    Pid_Reset(&Track.gyro_pid);
    if (Track.use_motor) {
        Motor_Set_Speed(0);
        Motor_Right_Set_Speed(0);
        App_Motor_Enable_Speed_PID(true);
    }
    APP_ROTATE_LOG_I("ROTATE", "start target=%d timeout=%lu motor=closed_loop",
                     (int)target_deg, (unsigned long)Track.rotate_timeout_ms);
    return true;
}

bool Track_Is_Rotating(void)
{
    return Track.state == TRACK_STATE_ROTATE;
}

void Track_Abort_Rotation(const char *result)
{
    if (Track.state == TRACK_STATE_ROTATE) {
        Track_Rotate_End(result != NULL ? result : "safety_fault");
    }
}

float Track_Get_Rotation_Target(void) { return Track.rotate_target_deg; }
float Track_Get_Rotation_Angle(void) { return Track.rotate_actual_deg; }
float Track_Get_Rotation_Error(void) { return Track.rotate_error_deg; }
const char *Track_Get_Rotation_Result(void) { return Track.rotate_result; }

bool Track_Start_Heading_Hold(void)
{
    Track.heading_hold_result = "rejected";
    if (Track.state != TRACK_STATE_IDLE) {
        Track.heading_hold_result = "not_ready";
        return false;
    }
    if (!Track_Imu_Healthy()) {
        Track.heading_hold_result = "imu_unavailable";
        return false;
    }
    if (!Safety_TransitionToRotation() || !Safety_AllowsMotorOutput()) {
        Track.heading_hold_result = "safety_rejected";
        return false;
    }

    Track.heading_hold_target = Imu_Sensor.heading;
    Track.heading_hold_actual = Imu_Sensor.heading;
    Track.heading_hold_error = 0;
    Track.heading_hold_result = "holding";
    Track.state = TRACK_STATE_HEADING_HOLD;
    Track.left_speed = 0;
    Track.right_speed = 0;
    Pid_Reset(&Track.gyro_pid);
    if (Track.use_motor) {
        Motor_Set_Speed(0);
        Motor_Right_Set_Speed(0);
        App_Motor_Enable_Speed_PID(true);
    }
    APP_ROTATE_LOG_I("HOLD", "start target=%d motor=closed_loop",
                     (int)Track.heading_hold_target);
    return true;
}

bool Track_Stop_Heading_Hold(void)
{
    if (Track.state != TRACK_STATE_HEADING_HOLD) {
        return false;
    }
    Track_Heading_Hold_End("stopped");
    APP_ROTATE_LOG_I("HOLD", "stopped");
    return true;
}

bool Track_Is_Heading_Hold(void)
{
    return Track.state == TRACK_STATE_HEADING_HOLD;
}

float Track_Get_Heading_Hold_Target(void) { return Track.heading_hold_target; }
float Track_Get_Heading_Hold_Actual(void) { return Track.heading_hold_actual; }
float Track_Get_Heading_Hold_Error(void) { return Track.heading_hold_error; }
const char *Track_Get_Heading_Hold_Result(void) { return Track.heading_hold_result; }

void Track_Set_Circles(uint8_t n)
{
    if (n < 1u) n = 1u;
    if (n > 20u) n = 20u;
    Track.target_circles = n;
}

void Track_Set_Speed(int32_t base_speed)
{
    if (base_speed < 0) base_speed = 0;
    if (base_speed > 100) base_speed = 100;
    Track.base_speed   = base_speed;
    Track.target_speed = base_speed;
}

void Track_Set_TrackPID(float kp, float ki, float kd)
{
    if (!isfinite(kp) || !isfinite(ki) || !isfinite(kd)) return;
    if (kp < 0.0f) kp = 0.0f;
    if (kp > 50.0f) kp = 50.0f;
    if (ki < 0.0f) ki = 0.0f;
    if (ki > 5.0f) ki = 5.0f;
    if (kd < 0.0f) kd = 0.0f;
    if (kd > 20.0f) kd = 20.0f;
    Pid_Set_Params(&Track.line_pid, kp, ki, kd);
}

void Track_Set_GyroDamp(float damp)
{
    if (!isfinite(damp)) return;
    if (damp < 0.0f) damp = 0.0f;
    if (damp > 1.0f) damp = 1.0f;   /* 钳位 0~1 */
    Track.gyro_damp = damp;
}

void Track_Set_SpeedStraight(int32_t spd)
{
    if (spd < 0)   spd = 0;
    if (spd > 100) spd = 100;        /* 钳位 0~100 */
    Track.speed_straight = spd;
}

void Track_Set_SpeedCurve(int32_t spd)
{
    if (spd < 0)   spd = 0;
    if (spd > 100) spd = 100;
    Track.speed_curve = spd;
}

void Track_Set_RightAngleThreshold(float thr)
{
    if (!isfinite(thr)) return;
    if (thr < 0.5f) thr = 0.5f;
    if (thr > 10.0f) thr = 10.0f;   /* 钳位 0.5~10 */
    Track.right_angle_threshold = thr;
}

void Track_Calibrate_White(void)
{
    Grayscale_Calibrate_White();
}

void Track_Calibrate_Black(void)
{
    Grayscale_Calibrate_Black();
}

track_state_t Track_Get_State(void)
{
    return Track.state;
}

uint8_t Track_Get_Circle(void)
{
    return Track.current_circle;
}
