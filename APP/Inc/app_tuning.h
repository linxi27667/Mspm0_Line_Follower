/**
 * @file    app_tuning.h
 * @brief   AI 远程调参协议层（JSON 解析 + 遥测组包）
 * @note    架构定位：APP 层调参协议，对接 App_ESP01S 的 Rx 回调与 SendJSON API
 *
 *          协议设计：
 *          下行（PC→小车，AI 决策）：
 *            {"set":{"KP":2.5,"KI":0.0,"KD":1.0,"GDAMP":0.15,
 *                    "VBASE":40,"VSTR":50,"VCUR":30,"RATHR":2.5}}
 *            字段可选，缺省字段不改。
 *            {"cmd":"start"} / {"cmd":"stop"} / {"cmd":"whitecal"} / {"cmd":"blackcal"}
 *
 *          上行（小车→PC，遥测，100Hz）：
 *            {"t":"tele","adc":[8值],"gz":0.12,"el":1024,"er":980,
 *             "le":0.3,"po":45,"st":"LF","kp":5.0,"kd":1.0}
 *
 *          用法：
 *            App_Tuning_Init();          // 初始化（注册 Rx 回调到 ESP01S）
 *            while (1) App_Tuning_Poll(); // 主循环调用，100Hz 自动上报遥测
 */
#ifndef APP_TUNING_H
#define APP_TUNING_H

#include <stdint.h>
#include <stdbool.h>

/* 初始化（注册 JSON 接收回调到 App_ESP01S） */
void App_Tuning_Init(void);

/* 主循环调用：按 100Hz 节拍上报遥测 JSON */
void App_Tuning_Poll(void);

/* ESP01S Rx 回调（由 App_Tuning_Init 注册，无需用户手动调用）
 * 解析 JSON 并调 Track_Set_* setter 或触发 start/stop 等指令 */
void App_Tuning_OnRx(const uint8_t *data, uint16_t len);

#endif /* APP_TUNING_H */
