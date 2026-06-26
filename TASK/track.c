/**
 * @file    track.c
 * @brief   灰度PID循迹任务调度实现（TASK层 — 纯业务逻辑）
 * @note    数据流:
 *          Grayscale_Update → data_ready → Track_Calc_Error → PID → 差速 → Motor
 *          Mpu_Update_Heading → heading → 丢线辅助/直角弯道
 *
 *          本文件不直接操作任何硬件寄存器，全部通过 BSP/APP 层 API 调用
 */
#include "track.h"
#include "bsp_common.h"
#include <elog.h>

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
    /* 保存上次偏差 */
    Track.last_error = Track.error;

    /* 模拟量差比和（归一化值，连续精度）
     * 左侧权重为负，右侧权重为正
     * norm[i] = 1 表示黑线，0 表示白色
     * error = Σ(weight[i] × norm[i]) / Σ(norm[i]) */
    float weighted_sum = 0;
    float total_weight = 0;

    for (uint8_t i = 0; i < BSP_GRAY_CHANNEL_NUM; i++) {
        /* 用归一化值做加权（连续精度，不受数字量跳变影响） */
        weighted_sum += s_weights[i] * Grayscale_Sensor.norm[i];
        total_weight  += Grayscale_Sensor.norm[i];
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
    /* --- 起点线检测（≥6路黑） — 必须在十字路口之前检测 ---
     * 修复1: 原代码先检测十字(中4路黑+外侧白)，起点线(6路黑)会满足
     *        十字条件被误判为十字路口，导致圈数计数失效。
     * 修复2: 添加 start_line_armed 标志，起点线必须先消失再出现才重新计数，
     *        避免慢速通过时一条起点线被记多圈。 */
    if (Track.start_line_armed &&
        Grayscale_Sensor.black_count >= TRACK_START_LINE_MIN_BLACK) {
        if (Track.state == TRACK_STATE_LINE_FOLLOW) {
            Track.target_heading = Mpu_Sensor.heading;
            Track.state = TRACK_STATE_START_LINE;
            Track.state_timer = 0;
            Track.start_line_armed = false;  /* 需等黑线消失后重新武装 */
            elog_i("TRACK", "LINE_FOLLOW -> START_LINE (bc=%d)",
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
            Track.state_timer = 0;
            elog_i("TRACK", "LINE_FOLLOW -> CROSS (bc=%d)",
                   Grayscale_Sensor.black_count);
            return;
        }
    }

    /* --- 直角弯道检测（多帧确认） --- */
    if ((Grayscale_Sensor.digital[0] || Grayscale_Sensor.digital[7]) &&
        (Track.error > TRACK_RIGHT_ANGLE_THRESHOLD ||
         Track.error < -TRACK_RIGHT_ANGLE_THRESHOLD)) {
        Track.right_angle_confirm++;
        if (Track.right_angle_confirm >= TRACK_RIGHT_ANGLE_CONFIRM_FRAMES) {
            if (Track.state == TRACK_STATE_LINE_FOLLOW) {
                Track.last_state = TRACK_STATE_LINE_FOLLOW;
                Track.right_angle_target = Mpu_Sensor.heading +
                    (Track.error > 0 ? 90.0f : -90.0f);
                Track.state = TRACK_STATE_RIGHT_ANGLE;
                Track.state_timer = 0;
                Track.right_angle_confirm = 0;
                elog_i("TRACK", "LINE_FOLLOW -> RIGHT_ANGLE (err=%d target=%d)",
                       (int)Track.error, (int)Track.right_angle_target);
            }
        }
    } else {
        /* 条件不满足，重置确认计数 */
        Track.right_angle_confirm = 0;
    }

    /* --- 丢线检测（多帧确认，抗瞬时干扰） --- */
    if (Grayscale_Sensor.black_count < TRACK_LINE_LOST_MAX_BLACK) {
        Track.line_lost_confirm++;
        if (Track.line_lost_confirm >= TRACK_LINE_LOST_CONFIRM_FRAMES) {
            if (Track.state == TRACK_STATE_LINE_FOLLOW) {
                Track.last_state = TRACK_STATE_LINE_FOLLOW;
                Track.target_heading = Mpu_Sensor.heading;
                Track.state = TRACK_STATE_LINE_LOST;
                Track.line_lost_count = 0;
                Pid_Reset(&Track.gyro_pid);  /* 进入丢线时复位 gyro_pid 防积分突跳 */
                elog_w("TRACK", "LINE_FOLLOW -> LINE_LOST (hdg=%d)",
                       (int)Mpu_Sensor.heading);
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
            Track_Motor_Stop_Immediate();   /* 立即停车(安全) */
            elog_i("TRACK", "FINISHED! circles=%d/%d", Track.current_circle, Track.target_circles);
        } else {
            Track.state = TRACK_STATE_LINE_FOLLOW;
            elog_i("TRACK", "Circle %d/%d completed", Track.current_circle, Track.target_circles);
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

/* 丢线处理：用陀螺仪维持航向 */
static void Track_Handle_LineLost(void)
{
    Track.line_lost_count++;

    if (Track.use_gyro && Mpu_Sensor.gyro_ok) {
        /* 修复: 统一用完整 PID(含 D 项)而非仅 P 控制，与直角弯道策略一致。
         * Pid_Compute 内部 error = target - feedback = target_heading - heading */
        Track.turn_output = Pid_Compute(&Track.gyro_pid,
                                        Track.target_heading,
                                        Mpu_Sensor.heading);
    } else {
        Track.turn_output = Track.last_error * TRACK_LINE_LOST_GAIN;
    }

    /* 丢线超时停车 */
    if (Track.line_lost_count > TRACK_LINE_LOST_TIMEOUT) {
        Track.state = TRACK_STATE_FINISHED;
        Track_Motor_Stop_Immediate();   /* 立即停车(安全) */
        return;
    }

    /* 重新检测到线，恢复循迹（PID复位防止积分突跳） */
    if (Grayscale_Sensor.black_count > 0) {
        Track.state = TRACK_STATE_LINE_FOLLOW;
        Pid_Reset(&Track.line_pid);
        Track.line_lost_confirm = 0;    /* 修复: 复位确认计数，避免立即重入 LINE_LOST */
        elog_i("TRACK", "LINE_LOST -> LINE_FOLLOW (recovered, bc=%d)",
               Grayscale_Sensor.black_count);
    }
}

/* 直角弯道处理：陀螺仪精确旋转90度 */
static void Track_Handle_RightAngle(void)
{
    Track.state_timer++;

    float angle_error = Track.right_angle_target - Mpu_Sensor.heading;
    Track.turn_output = Pid_Compute(&Track.gyro_pid,
                                     Track.right_angle_target,
                                     Mpu_Sensor.heading);

    /* 角度误差小于阈值，视为完成转弯 */
    if (angle_error > -TRACK_RIGHT_ANGLE_DONE_ERR &&
        angle_error <  TRACK_RIGHT_ANGLE_DONE_ERR) {
        Track.state = TRACK_STATE_LINE_FOLLOW;
        Pid_Reset(&Track.line_pid);
        return;
    }

    /* 超时保护 */
    if (Track.state_timer > TRACK_RIGHT_ANGLE_TIMEOUT) {
        Track.state = TRACK_STATE_LINE_FOLLOW;
        Pid_Reset(&Track.line_pid);
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
    if (Grayscale_Sensor.black_count < 1 && Track.state_timer > 10) {
        Track.state = TRACK_STATE_LINE_FOLLOW;
    }
}

/* 差速输出到电机（内侧电机最低速度限制） */
static void Track_Motor_Output(void)
{
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
    Track.state              = TRACK_STATE_IDLE;
    Track.last_state         = TRACK_STATE_IDLE;
    Track.target_heading     = 0;
    Track.right_angle_target = 0;
    Track.state_timer        = 0;
    Track.line_lost_count    = 0;
    Track.right_angle_confirm = 0;
    Track.line_lost_confirm  = 0;
    Track.start_line_armed   = true;  /* 初始可检测起点线 */
    Track.target_circles     = TRACK_DEFAULT_CIRCLES;
    Track.current_circle     = 0;
    Track.turn_output        = 0;
    Track.left_speed         = 0;
    Track.right_speed        = 0;
    Track.base_speed         = TRACK_DEFAULT_BASE_SPEED;
    Track.target_speed       = TRACK_DEFAULT_BASE_SPEED;
    Track.use_gyro           = true;
    Track.use_motor          = true;

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
    App_Mpu_Init();
    Mpu_Calibrate();
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
    elog_i("TRACK", "Gray auto-cal WHITE (place car on white surface):");
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
        elog_i("TRACK", "  S%d: ADC=%u white=%u black=%u",
               i, adc, adc, Grayscale_Sensor.black[i]);
    }
    Grayscale_Sensor.calibrated = 1;

    /* 启用速度PID闭环（编码器反馈修正PWM） */
    App_Motor_Enable_Speed_PID(true);
}

void Track_Update(void)
{
    /* ① 灰度传感器非阻塞扫描（APP层API） */
    Grayscale_Update();

    /* ② 固定5ms周期执行循迹状态机 */
    static uint32_t last_update_tick = 0;
    uint32_t now = Bsp_GetTick();
    if ((now - last_update_tick) < TRACK_UPDATE_PERIOD_MS) return;

    if (Track.state == TRACK_STATE_IDLE ||
        Track.state == TRACK_STATE_FINISHED) return;

    /* ③ 等待灰度传感器完成一轮完整扫描（数据同步） */
    if (!Grayscale_Sensor.data_ready) return;
    Grayscale_Sensor.data_ready = 0;  /* 消费标志 */

    /* 修复: 时间戳必须在真正执行时才更新(原代码在 data_ready 检查前更新，
     * 导致因 data_ready=0 提前返回时时间戳仍推进，dt 与实际周期不匹配)。
     * 同时传入真实 dt(而非固定 5ms)，保证陀螺仪航向积分准确。 */
    float dt = (now - last_update_tick) / 1000.0f;
    last_update_tick = now;

    /* ④ 读取陀螺仪数据并更新航向（APP层API） */
    if (Track.use_gyro) {
        Mpu_Update_Heading(dt);
    }

    /* ⑤ 计算偏差 */
    Track_Calc_Error();

    /* ⑥ 变速策略 */
    Track_Update_Speed();

    /* ⑦ 检测赛道元素 */
    Track_Detect_Pattern();

    /* ⑧ 状态机处理 */
    switch (Track.state) {
    case TRACK_STATE_LINE_FOLLOW:
        /* 偏差>0表示黑线在车体右侧，需要右转 → turn_output应为正
         * Pid_Compute(pid, setpoint, feedback) 内部 error = setpoint - feedback
         * 传入 (Track.error, 0) 使 PID error = Track.error，输出极性正确
         * 修复: 原代码 (0, Track.error) 导致 PID 极性反接，车会偏离黑线 */
        Track.turn_output = Pid_Compute(&Track.line_pid, Track.error, 0.0f);
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

    /* ⑨ 差速输出到电机（BSP层API） */
    Track_Motor_Output();

    /* 速度PID闭环更新已移至 main.c 的 5ms 独立节拍，
     * 保证 IDLE/FINISHED 状态下也能更新(避免电机保持最后PWM)。 */
}

void Track_Start(void)
{
    /* 检查黑色校准状态,未校准时警告(允许启动但循迹不可靠) */
    if (!Grayscale_Sensor.black_calibrated) {
        elog_w("TRACK", "WARNING: Black NOT calibrated! Place car on black line and press K4");
    }

    Track.state = TRACK_STATE_LINE_FOLLOW;
    Track.current_circle = 0;
    Track.right_angle_confirm = 0;
    Track.line_lost_confirm = 0;
    Track.start_line_armed = true;
    Pid_Reset(&Track.line_pid);
    Pid_Reset(&Track.gyro_pid);
    elog_i("TRACK", "Tracking started (circles=%d speed=%d black_cal=%d)",
           Track.target_circles, Track.base_speed,
           Grayscale_Sensor.black_calibrated);
}

void Track_Stop(void)
{
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
    elog_i("TRACK", "Tracking stopped (state=FINISHED)");
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
    Pid_Set_Params(&Track.line_pid, kp, ki, kd);
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
