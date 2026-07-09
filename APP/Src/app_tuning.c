/**
 * @file    app_tuning.c
 * @brief   AI 远程调参协议层实现
 * @note    极简 JSON 解析（针对调参协议，不引 cJSON）+ 100Hz 遥测组包
 *
 *          解析策略：用 strstr 定位 "set"/"cmd" 模式，再对每个已知 key
 *          用 strstr 查找 "KEY" 后跟 :数字，atof 解析。
 *          优点：零内存分配，栈占用极小，针对性强。
 *          限制：不处理嵌套对象/数组/转义，但调参协议用不到这些。
 */
#include "app_tuning.h"
#include "app_esp01s.h"
#include "app_common.h"
#include "track.h"
#include "bsp_common.h"
#include "bsp_grayscale.h"
#include "bsp_encoder_motor.h"
#include "elog.h"
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

#undef LOG_TAG
#define LOG_TAG  "tuning"

/* ESP-01S AT+CIPSEND 单帧有握手开销。远程调试先用 2Hz，避免日志/遥测挤占链路。 */
#define TUNING_TELEM_INTERVAL_MS   500

/* ============================================================
 * 内部状态
 * ============================================================ */
static uint32_t s_last_telem_tick = 0;
static char     s_telem_buf[256];    /* 遥测组包缓冲（栈外静态，避免栈占用） */
static char     s_rx_buf[256];       /* Rx 拷贝缓冲（OnRx 回调中加 NUL 结尾用） */

/* 状态枚举 → 2 字母缩写 */
static const char *state_abbr(track_state_t st)
{
    switch (st) {
    case TRACK_STATE_IDLE:        return "ID";
    case TRACK_STATE_LINE_FOLLOW: return "LF";
    case TRACK_STATE_RIGHT_ANGLE: return "RA";
    case TRACK_STATE_LINE_LOST:   return "LL";
    case TRACK_STATE_START_LINE:  return "SL";
    case TRACK_STATE_CROSS:       return "CR";
    case TRACK_STATE_FINISHED:    return "FN";
    default:                      return "??";
    }
}

/* ============================================================
 * 极简 JSON 解析
 * ============================================================ */

/* 在 buf 中查找 "key":数字 模式，返回是否找到并输出数值
 * 例：find_num(buf, "KP", &val) 匹配 "KP":2.5 或 "KP": 2.5 */
static bool find_num(const char *buf, const char *key, float *out)
{
    char pattern[8];
    snprintf(pattern, sizeof(pattern), "\"%s\"", key);
    const char *p = strstr(buf, pattern);
    if (p == NULL) return false;

    /* 跳过 "key" 后的空白和冒号 */
    p += strlen(pattern);
    while (*p == ' ' || *p == '\t') p++;
    if (*p != ':') return false;
    p++;
    while (*p == ' ' || *p == '\t') p++;

    /* atof 解析数字（支持负数和小数） */
    *out = (float)atof(p);
    return true;
}

/* 解析 set 模式：{"set":{"KP":...,"KD":...}} */
static void parse_set(const char *buf)
{
    float v;
    bool  changed = false;

    if (find_num(buf, "KP", &v)) {
        Track_Set_TrackPID(v, Track.line_pid.ki, Track.line_pid.kd);
        elog_i(LOG_TAG, "set KP=%.3f", v);
        changed = true;
    }
    if (find_num(buf, "KI", &v)) {
        Track_Set_TrackPID(Track.line_pid.kp, v, Track.line_pid.kd);
        elog_i(LOG_TAG, "set KI=%.3f", v);
        changed = true;
    }
    if (find_num(buf, "KD", &v)) {
        Track_Set_TrackPID(Track.line_pid.kp, Track.line_pid.ki, v);
        elog_i(LOG_TAG, "set KD=%.3f", v);
        changed = true;
    }
    if (find_num(buf, "GDAMP", &v)) {
        Track_Set_GyroDamp(v);
        elog_i(LOG_TAG, "set GDAMP=%.3f", (double)v);
        changed = true;
    }
    if (find_num(buf, "VBASE", &v)) {
        Track_Set_Speed((int32_t)v);
        elog_i(LOG_TAG, "set VBASE=%d", (int)v);
        changed = true;
    }
    if (find_num(buf, "VSTR", &v)) {
        Track_Set_SpeedStraight((int32_t)v);
        elog_i(LOG_TAG, "set VSTR=%d", (int)v);
        changed = true;
    }
    if (find_num(buf, "VCUR", &v)) {
        Track_Set_SpeedCurve((int32_t)v);
        elog_i(LOG_TAG, "set VCUR=%d", (int)v);
        changed = true;
    }
    if (find_num(buf, "RATHR", &v)) {
        Track_Set_RightAngleThreshold(v);
        elog_i(LOG_TAG, "set RATHR=%.3f", (double)v);
        changed = true;
    }
    (void)changed;
}

/* 解析 cmd 模式：{"cmd":"start"} 等 */
static void parse_cmd(const char *buf)
{
    if (strstr(buf, "\"start\"") != NULL) {
        elog_i(LOG_TAG, "cmd start");
        Track_Start();
    } else if (strstr(buf, "\"stop\"") != NULL) {
        elog_i(LOG_TAG, "cmd stop");
        Track_Stop();
    } else if (strstr(buf, "\"whitecal\"") != NULL) {
        elog_i(LOG_TAG, "cmd whitecal");
        Track_Calibrate_White();
    } else if (strstr(buf, "\"blackcal\"") != NULL) {
        elog_i(LOG_TAG, "cmd blackcal");
        Track_Calibrate_Black();
    } else if (strstr(buf, "\"reconnect\"") != NULL) {
        elog_i(LOG_TAG, "cmd reconnect");
        App_ESP01S_ReconnectTCP();
    }
}

/* ============================================================
 * 对外 API
 * ============================================================ */

void App_Tuning_OnRx(const uint8_t *data, uint16_t len)
{
    if (data == NULL || len == 0) return;
    if (len >= sizeof(s_rx_buf)) len = sizeof(s_rx_buf) - 1;  /* 截断防溢出 */

    memcpy(s_rx_buf, data, len);
    s_rx_buf[len] = '\0';

    /* 派发：set / cmd / 其它（忽略） */
    if (strstr(s_rx_buf, "\"set\"") != NULL) {
        parse_set(s_rx_buf);
    } else if (strstr(s_rx_buf, "\"cmd\"") != NULL) {
        parse_cmd(s_rx_buf);
    } else {
        elog_d(LOG_TAG, "rx unknown: %.*s", (int)len, s_rx_buf);
    }
}

void App_Tuning_Init(void)
{
    s_last_telem_tick = Bsp_GetTick();
    App_ESP01S_RegisterRx(App_Tuning_OnRx);
    elog_i(LOG_TAG, "tuning layer ready, telemetry %dms/frame", TUNING_TELEM_INTERVAL_MS);
}

void App_Tuning_Poll(void)
{
    /* 仅在 TCP 连接时上报，避免 CIPSEND 失败 */
    if (!App_ESP01S_IsTCPConnected()) return;

    uint32_t now = Bsp_GetTick();
    if ((now - s_last_telem_tick) < TUNING_TELEM_INTERVAL_MS) return;
    s_last_telem_tick = now;

    /* 组包遥测 JSON
     * 字段说明：
     *   t   = "tele"（帧类型）
     *   adc = 8 路灰度原始 ADC
     *   gz  = 陀螺仪 Z 轴角速度
     *   el  = 左编码器速度
     *   er  = 右编码器速度
     *   le  = 当前循迹误差
     *   po  = PID 转向输出
     *   st  = 状态缩写
     *   kp/kd = 当前 PID 参数（便于 AI 确认参数已生效）
     */
    int n = snprintf(s_telem_buf, sizeof(s_telem_buf),
        "{\"t\":\"tele\",\"adc\":[%u,%u,%u,%u,%u,%u,%u,%u],"
        "\"gz\":%.2f,\"el\":%d,\"er\":%d,\"le\":%.2f,\"po\":%.2f,"
        "\"st\":\"%s\",\"kp\":%.3f,\"kd\":%.3f}\n",
        Grayscale_Sensor.analog[0], Grayscale_Sensor.analog[1],
        Grayscale_Sensor.analog[2], Grayscale_Sensor.analog[3],
        Grayscale_Sensor.analog[4], Grayscale_Sensor.analog[5],
        Grayscale_Sensor.analog[6], Grayscale_Sensor.analog[7],
        (double)Track.gyro_rate,
        (int)Motor_Left.encoder_speed, (int)Motor_Right.encoder_speed,
        (double)Track.error, (double)Track.turn_output,
        state_abbr(Track.state),
        (double)Track.line_pid.kp, (double)Track.line_pid.kd);

    if (n > 0 && n < (int)sizeof(s_telem_buf)) {
        if (!App_ESP01S_SendJSON((uint8_t *)s_telem_buf, (uint16_t)n)) {
            /* 发送失败已由 ESP01S 内部记日志，此处静默避免日志风暴 */
        }
    }
}
