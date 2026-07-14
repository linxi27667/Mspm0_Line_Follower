/**
 * @file    user_tuning.h
 * @brief   全局用户调参默认值 — 固件侧唯一定义源。
 *
 *          所有 USER_* 宏在此文件集中定义。track.h / app_encoder_motor.h
 *          仅保留 TRACK_* / MOTOR_* 别名，不再保留 #ifndef 回退默认值。
 *          main.c 不再重复定义。
 *
 *          远程可调参数（8 个）的 min/max/default 同时由 host/param_schema.py
 *          驱动，tests/test_param_schema.py 验证两者默认值一致。
 *          最终比赛档值唯一落在本文件，RACE 构建直接编译生效。
 *
 * ====== 国一/省一方案学习总结(2024电赛H题) ======
 * 1. 陀螺仪: 国一方案都用JY61P/HWT101数字陀螺仪(直接输出角度,无零漂)
 *    我们用MPU6050需积分,瞬时加速度大会漂移,需开机静止校准+PID稳定
 * 2. 状态机+航向锁定: 每段路锁定目标航向角,陀螺仪PID走直线
 * 3. 循迹时也保持速度闭环: 灰度只输出差速,速度环保证车速稳定
 * 4. 位置前馈: 编码器累计脉冲数判断到达点(我们用圈数+超时)
 * 5. 速度环只用P就够: 省一方案验证P环足够,KI=0避免积分饱和
 * 6. 差速范围: 省一方案离散差速最大±28,我们OLIMIT=30起步
 * 7. 丢线处理: 锁定航向角直行+编码器测距判断,超时停车
 */
#ifndef USER_TUNING_H
#define USER_TUNING_H

/* ==================================================================
 * ====== 1. 循迹线PID (主循迹,输入灰度误差,输出转向量) ======
 * 调参方法:
 *   1. 先只调KP: 从小值(2.0)开始,车能跟线但反应慢→加大KP
 *   2. 车甩出弯道→KP太大,减小
 *   3. 车左右震荡→加KD(从0.5开始),KD约为KP的1/5~1/3
 *   4. 直线有静差→加KI(从0.1开始),但通常循迹KI=0
 *   5. 转向量过大→减小OLIMIT
 * 参考省一方案: 离散差速最大±28,我们用连续PID,OLIMIT建议30起步
 * 参考wandao方案: KP=5 KI=0 KD=3(注意KD=KP*0.6,偏大抑制震荡)
 * 综合建议: KP=5 KD=1(KD=KP/5) 起步,实测调整
 * ================================================================== */
#ifndef USER_LINE_PID_KP
#define USER_LINE_PID_KP           5.0f    /* 比例增益(多方案共识:5.0是稳健起点) */
#endif
#ifndef USER_LINE_PID_KI
#define USER_LINE_PID_KI           0.0f    /* 积分增益(循迹通常为0,国一方案验证) */
#endif
#ifndef USER_LINE_PID_KD
#define USER_LINE_PID_KD           1.0f    /* 微分增益(KP/5,抑制震荡) */
#endif
#ifndef USER_LINE_PID_ILIMIT
#define USER_LINE_PID_ILIMIT       50.0f   /* 积分限幅 */
#endif
#ifndef USER_LINE_PID_OLIMIT
#define USER_LINE_PID_OLIMIT       30.0f   /* 输出限幅(省一参考:差速最大±28) */
#endif
#ifndef USER_LINE_PID_DERIV_ALPHA
#define USER_LINE_PID_DERIV_ALPHA  0.6f    /* 不完全微分系数(0~1,越大滤波越弱) */
#endif
/* 国一方案核心: LINE_FOLLOW 陀螺仪角速度阻尼 (直行稳/弯道灵)
 * 公式: turn_output = line_pid - GYRO_DAMP * gyro_z
 * 调参: 直道抖动→加大(0.15→0.3), 弯道跟踪迟钝→减小(0.15→0.08) */
#ifndef USER_LINE_FOLLOW_GYRO_DAMP
#define USER_LINE_FOLLOW_GYRO_DAMP 0.15f   /* 陀螺仪阻尼系数(0=禁用,0.15起步) */
#endif

/* ==================================================================
 * ====== 2. 陀螺仪PID (丢线/直角弯时用,输入航向角偏差) ======
 * 调参方法:
 *   1. 直角弯转不过去→加大KP
 *   2. 转过头→加KD或减小KP
 *   3. 丢线时车跑偏→加大KP
 * 注意: MPU6050有零漂,省一方案用JY61P免校准,我们需开机静止校准
 * ================================================================== */
#ifndef USER_GYRO_PID_KP
#define USER_GYRO_PID_KP           3.0f    /* 比例增益 */
#endif
#ifndef USER_GYRO_PID_KI
#define USER_GYRO_PID_KI           0.0f    /* 积分增益 */
#endif
#ifndef USER_GYRO_PID_KD
#define USER_GYRO_PID_KD           0.5f    /* 微分增益 */
#endif
#ifndef USER_GYRO_PID_ILIMIT
#define USER_GYRO_PID_ILIMIT       30.0f   /* 积分限幅 */
#endif
#ifndef USER_GYRO_PID_OLIMIT
#define USER_GYRO_PID_OLIMIT       30.0f   /* 输出限幅(与线PID一致) */
#endif

/* ==================================================================
 * ====== 3. 速度PID (电机闭环,输入目标速度,反馈编码器,输出PWM) ======
 * 调参方法:
 *   1. 空转时PWM很高(如90)是正常的(编码器读数≈0,PID拼命加PWM)
 *   2. 接轮子后车不动→加大KP
 *   3. 车速震荡→加KD或减小KP
 *   4. 速度跟不上→加大OLIMIT或减小INTEGRAL_SEP
 * 速度比例尺(SPEED_SCALE): 国一方案必须左右分别标定!
 *   方法1(自动): 悬空车轮, K3长按触发 App_Motor_Calibrate_Scale(), RTT打印scale值
 *   方法2(手动): 设PWM=50,测encoder_speed, scale = encoder_speed / 50
 *   注意: 左编码器QEI 4x / 右编码器GPIO 2x, scale_right约为0.5 * scale_left
 * 速度环只用P就够(省一方案验证),KI=0避免积分饱和
 * ================================================================== */
#ifndef USER_MOTOR_SPEED_PID_KP
#define USER_MOTOR_SPEED_PID_KP    0.55f   /* 5ms encoder P loop; filtered feedback */
#endif
#ifndef USER_MOTOR_SPEED_PID_KI
#define USER_MOTOR_SPEED_PID_KI    0.0f    /* 速度PID积分增益(省一验证:P环足够) */
#endif
#ifndef USER_MOTOR_SPEED_PID_KD
#define USER_MOTOR_SPEED_PID_KD    0.0f    /* 速度PID微分增益 */
#endif
#ifndef USER_MOTOR_SPEED_PID_ILIMIT
#define USER_MOTOR_SPEED_PID_ILIMIT 30.0f  /* 速度PID积分限幅 */
#endif
#ifndef USER_MOTOR_SPEED_PID_OLIMIT
#define USER_MOTOR_SPEED_PID_OLIMIT 20.0f  /* correction limit before feed-forward */
#endif
#ifndef USER_MOTOR_SPEED_PID_INTEGRAL_SEP
#define USER_MOTOR_SPEED_PID_INTEGRAL_SEP 15.0f /* 积分分离阈值(误差>此值不累加I) */
#endif
#ifndef USER_MOTOR_SPEED_SCALE_LEFT
#define USER_MOTOR_SPEED_SCALE_LEFT   0.067f /* observed counts/5ms/PWM, left QEI 4x */
#endif
#ifndef USER_MOTOR_SPEED_SCALE_RIGHT
#define USER_MOTOR_SPEED_SCALE_RIGHT  0.033f /* right GPIO 2x is about half of left */
#endif
#ifndef USER_MOTOR_SPEED_FILTER_ALPHA
#define USER_MOTOR_SPEED_FILTER_ALPHA 0.20f /* about 20ms time constant at 5ms/tick */
#endif
#ifndef USER_MOTOR_SPEED_START_THRESHOLD
#define USER_MOTOR_SPEED_START_THRESHOLD 2.0f
#endif
#ifndef USER_MOTOR_SPEED_MIN_DRIVE_PWM
#define USER_MOTOR_SPEED_MIN_DRIVE_PWM 24  /* measured motors start around PWM=25 */
#endif

/* ==================================================================
 * ====== 4. 循迹策略参数 ======
 * 调参方法:
 *   1. 车速太快冲出弯道→减小BASE_SPEED或SPEED_STRAIGHT
 *   2. 直道不够快→加大SPEED_STRAIGHT
 *   3. 弯道转不过→减小SPEED_CURVE或加大MOTOR_INNER_MIN
 *   4. 急转时内侧轮停转→减小MOTOR_INNER_MIN(最低15)
 * 省一方案: 单圈15秒,说明速度中等,我们用40起步
 * ================================================================== */
#ifndef USER_TRACK_BASE_SPEED
#define USER_TRACK_BASE_SPEED      40      /* 基础速度(启动时,省一参考值) */
#endif
#ifndef USER_TRACK_SPEED_STRAIGHT
#define USER_TRACK_SPEED_STRAIGHT  50      /* 直道速度(降低,先求稳) */
#endif
#ifndef USER_TRACK_SPEED_CURVE
#define USER_TRACK_SPEED_CURVE     26      /* 弯道/直角速度(先求稳,后续每次+3) */
#endif
#ifndef USER_TRACK_SPEED_RAMP_STEP
#define USER_TRACK_SPEED_RAMP_STEP 2       /* 速度渐变步进(避免突变抖动) */
#endif
#ifndef USER_TRACK_MOTOR_INNER_MIN
#define USER_TRACK_MOTOR_INNER_MIN 15      /* 内侧电机最低速度(防急转停转) */
#endif
#ifndef USER_TRACK_CIRCLES
#define USER_TRACK_CIRCLES         1       /* 目标圈数 */
#endif
/* 国一方案: 连续曲率变速 (替代二档跳变)
 * |error|=0→SPEED_STRAIGHT, |error|>=此值→SPEED_CURVE, 中间线性插值 */
#ifndef USER_TRACK_CURVE_ERROR_MAX
#define USER_TRACK_CURVE_ERROR_MAX 2.5f    /* 误差达此值时降到弯道速度 */
#endif

/* ==================================================================
 * ====== 5. 丢线/直角弯参数 ======
 * 调参方法:
 *   1. 丢线后车立即停车→加大LINE_LOST_TIMEOUT
 *   2. 直角弯检测不到→减小RIGHT_ANGLE_THRESHOLD或GYRO_RATE或ERROR_INTEGRAL
 *   3. 普通弯道被误判为直角弯→加大RIGHT_ANGLE_THRESHOLD或CONFIRM_FRAMES
 * 国一方案: 直角弯多条件触发 (任一满足即检测)
 *   cond_outer: S0/S7黑+大误差 | cond_accum: 误差累积 | cond_rate: 角速度超限
 * ================================================================== */
#ifndef USER_LINE_LOST_TIMEOUT
#define USER_LINE_LOST_TIMEOUT     500     /* 丢线超时停车(ms) */
#endif
#ifndef USER_LINE_LOST_GAIN
#define USER_LINE_LOST_GAIN        2.0f    /* 丢线时转向增益(无陀螺仪时用) */
#endif
#ifndef USER_RIGHT_ANGLE_THRESHOLD
#define USER_RIGHT_ANGLE_THRESHOLD 2.5f    /* 直角弯检测误差阈值(cond_outer) */
#endif
#ifndef USER_RIGHT_ANGLE_CONFIRM_FRAMES
#define USER_RIGHT_ANGLE_CONFIRM_FRAMES 3  /* 直角弯连续确认帧数 */
#endif
#ifndef USER_RIGHT_ANGLE_TIMEOUT
#define USER_RIGHT_ANGLE_TIMEOUT   1000    /* 直角弯超时(ms) */
#endif
#ifndef USER_RIGHT_ANGLE_DONE_ERR
#define USER_RIGHT_ANGLE_DONE_ERR  5.0f    /* 直角弯完成角度误差(度) */
#endif
#ifndef USER_RIGHT_ANGLE_ERROR_INTEGRAL
#define USER_RIGHT_ANGLE_ERROR_INTEGRAL  8.0f  /* 误差累积阈值(cond_accum,连续大误差) */
#endif
#ifndef USER_RIGHT_ANGLE_GYRO_RATE
#define USER_RIGHT_ANGLE_GYRO_RATE       80.0f /* 角速度阈值(cond_rate,deg/s,急弯触发) */
#endif
#ifndef USER_RIGHT_ANGLE_TARGET_ANGLE
#define USER_RIGHT_ANGLE_TARGET_ANGLE    88.0f /* 目标转角(略小于90,靠灰度捕线修正) */
#endif
#ifndef USER_RIGHT_ANGLE_MIN_EXIT_ANGLE
#define USER_RIGHT_ANGLE_MIN_EXIT_ANGLE  55.0f /* 转过此角度后允许灰度捕线提前退出 */
#endif
#ifndef USER_RIGHT_ANGLE_EXIT_CENTER_MIN
#define USER_RIGHT_ANGLE_EXIT_CENTER_MIN 2     /* 出弯捕线: S2~S5至少2路黑 */
#endif
#ifndef USER_RIGHT_ANGLE_EXIT_BLACK_MIN
#define USER_RIGHT_ANGLE_EXIT_BLACK_MIN  1     /* 出弯捕线: 总黑通道下限 */
#endif
#ifndef USER_RIGHT_ANGLE_EXIT_BLACK_MAX
#define USER_RIGHT_ANGLE_EXIT_BLACK_MAX  5     /* 出弯捕线: 避免起点线/大片黑误退出 */
#endif

/* Rotation/heading outer loop: angle P + measured yaw-rate damping. Its
 * output is a wheel-speed target; the encoder P loop below it produces PWM. */
#ifndef USER_ROTATE_PID_KP
#define USER_ROTATE_PID_KP              0.80f  /* wheel-speed / degree */
#endif
#ifndef USER_ROTATE_PID_KD_RATE
#define USER_ROTATE_PID_KD_RATE         0.08f  /* wheel-speed / (degree/second) */
#endif
#ifndef USER_ROTATE_PID_MAX_SPEED
#define USER_ROTATE_PID_MAX_SPEED       16.0f
#endif
#ifndef USER_ROTATE_PID_MIN_SPEED
#define USER_ROTATE_PID_MIN_SPEED       8
#endif
#ifndef USER_ROTATE_PID_COAST_OUTPUT
#define USER_ROTATE_PID_COAST_OUTPUT    2.4f
#endif
#ifndef USER_ROTATE_PID_FINE_ZONE_DEG
#define USER_ROTATE_PID_FINE_ZONE_DEG    20.0f
#endif
#ifndef USER_ROTATE_PID_BLEND_ZONE_DEG
#define USER_ROTATE_PID_BLEND_ZONE_DEG   40.0f
#endif
#ifndef USER_ROTATE_PID_FINE_MAX_SPEED
#define USER_ROTATE_PID_FINE_MAX_SPEED    5.0f
#endif
#ifndef USER_ROTATE_PID_FINE_MIN_SPEED
#define USER_ROTATE_PID_FINE_MIN_SPEED   3
#endif
#ifndef USER_ROTATE_DONE_ERR_DEG
#define USER_ROTATE_DONE_ERR_DEG          3.0f
#endif
#ifndef USER_ROTATE_SPEED_SLEW_STEP
#define USER_ROTATE_SPEED_SLEW_STEP      1
#endif
#ifndef USER_ROTATE_SETTLE_FRAMES
#define USER_ROTATE_SETTLE_FRAMES        20u  /* 100ms at the 5ms control tick */
#endif
#ifndef USER_ROTATE_TIMEOUT_BASE_MS
#define USER_ROTATE_TIMEOUT_BASE_MS     1000u
#endif
#ifndef USER_ROTATE_TIMEOUT_PER_DEG_MS
#define USER_ROTATE_TIMEOUT_PER_DEG_MS  50u
#endif

/* Current-heading hold uses the rotation PD settings above. */
#ifndef USER_HEADING_HOLD_DEADBAND_DEG
#define USER_HEADING_HOLD_DEADBAND_DEG   2.0f
#endif
#ifndef USER_HEADING_HOLD_SETTLE_RATE_DEG_S
#define USER_HEADING_HOLD_SETTLE_RATE_DEG_S  8.0f
#endif
#ifndef USER_HEADING_HOLD_MAX_SPEED
#define USER_HEADING_HOLD_MAX_SPEED       14.0f
#endif
#ifndef USER_HEADING_HOLD_MIN_SPEED
#define USER_HEADING_HOLD_MIN_SPEED         6
#endif
#ifndef USER_HEADING_HOLD_COAST_OUTPUT
#define USER_HEADING_HOLD_COAST_OUTPUT     1.5f
#endif

/* ==================================================================
 * ====== 6. 起点线/十字路口参数 ======
 * ================================================================== */
#ifndef USER_START_LINE_MIN_BLACK
#define USER_START_LINE_MIN_BLACK  6       /* 起点线最少黑色通道数 */
#endif
#ifndef USER_CROSS_MIN_BLACK
#define USER_CROSS_MIN_BLACK       4       /* 十字路口中间黑色通道数 */
#endif

/* ==================================================================
 * ====== 远程可调参数范围 (与 host/param_schema.py 一致) ======
 * 用于 app_tuning.c 对下发参数做固件侧钳位，防止第三方客户端绕过主机校验。
 * tests/test_param_schema.py 验证这些范围与 param_schema.py 一致。
 * ================================================================== */
#define USER_PARAM_KP_MIN     0.0f
#define USER_PARAM_KP_MAX     50.0f
#define USER_PARAM_KI_MIN     0.0f
#define USER_PARAM_KI_MAX     5.0f
#define USER_PARAM_KD_MIN     0.0f
#define USER_PARAM_KD_MAX     20.0f
#define USER_PARAM_GDAMP_MIN  0.0f
#define USER_PARAM_GDAMP_MAX  1.0f
#define USER_PARAM_VBASE_MIN  0
#define USER_PARAM_VBASE_MAX  100
#define USER_PARAM_VSTR_MIN   0
#define USER_PARAM_VSTR_MAX   100
#define USER_PARAM_VCUR_MIN   0
#define USER_PARAM_VCUR_MAX   100
#define USER_PARAM_RATHR_MIN  0.5f
#define USER_PARAM_RATHR_MAX  10.0f

#endif /* USER_TUNING_H */
