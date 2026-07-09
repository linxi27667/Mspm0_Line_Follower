/**
 * @file    app_esp01s.h
 * @brief   ESP-01S 应用层（HW 绑定 + WiFi/TCP 建连 + JSON 收发 API）
 * @note    架构定位（对应 app_uart.c 的分层模式）：
 *            - 实例化一个 bsp_uart_t（绑定 UART1 + DMA CH2/CH3）供 AT 引擎使用
 *            - 实例化一个 bsp_esp_at_ctx_t，驱动 AT 指令与 +IPD 重组
 *            - 实现 WiFi(STA) + TCP 客户端 建连流程（阻塞，仅在启动时调用）
 *            - 提供 JSON 透传收发 API（非阻塞，供主循环/任务调用）
 *
 *          AI 闭环调参用法：
 *            App_ESP01S_Init(on_progress);              // 启动时一次
 *            App_ESP01S_RegisterRx(json_handler);       // 注册 JSON 处理回调
 *            while (1) {
 *                App_ESP01S_Poll();                     // 主循环喂狗
 *                if (需要上报) App_ESP01S_SendJSON(buf, len); // 入队, 不阻塞
 *            }
 */
#ifndef APP_ESP01S_H
#define APP_ESP01S_H

#include "bsp_esp_at.h"
#include "app_esp01s_cfg.h"
#include <stdint.h>
#include <stdbool.h>

/* ============================================================
 * 回调类型
 * ============================================================ */

/* 建连进度回调（step 见实现；msg 为简短英文描述，用于 OLED/RTT 显示） */
typedef void (*App_ESP01S_ProgressCb)(uint8_t step, const char *msg);

/* 接收到一帧 JSON 的回调（data 非 NUL 结尾，长度由 len 给出，建议立即拷走） */
typedef void (*App_ESP01S_RxCallback)(const uint8_t *data, uint16_t len);

/* ============================================================
 * 生命周期
 * ============================================================ */

/* 初始化：UART + DMA + AT 引擎 + WiFi + TCP 建连（阻塞，启动时调用一次）
 * 返回 true = 建连成功，可收发数据；false = 失败（查 at_fail_count） */
bool App_ESP01S_Init(App_ESP01S_ProgressCb progress);

/* 重连 TCP（WiFi 已连但 TCP 断开时调用；不重连 WiFi） */
bool App_ESP01S_ReconnectTCP(void);

/* 主循环轮询：排空 UART → 重组 +IPD → 触发 RxCallback
 * 非阻塞，建议每个主循环迭代调用一次 */
void App_ESP01S_Poll(void);

/* 注册 JSON 接收回调（仅允许注册一个） */
void App_ESP01S_RegisterRx(App_ESP01S_RxCallback cb);

/* ============================================================
 * 数据收发
 * ============================================================ */

/* 发送一帧 JSON 到 PC（AT+CIPSEND 透传）
 * 运行期非阻塞: 仅入队并立即返回, 实际发送由 App_ESP01S_Poll 推进。
 * telemetry 帧队列中只保留最新帧, 日志满队列时允许丢弃, 避免影响车控闭环。
 * 返回 true = 已入队/已替换旧遥测；false = 未连接、长度越界或队列满 */
bool App_ESP01S_SendJSON(const uint8_t *data, uint16_t len);

/* 发送 C 字符串 JSON */
bool App_ESP01S_SendJSONString(const char *s);

/* ============================================================
 * 状态查询
 * ============================================================ */
bool     App_ESP01S_IsWiFiConnected(void);
bool     App_ESP01S_IsTCPConnected(void);
uint32_t App_ESP01S_GetATFailCount(void);
uint32_t App_ESP01S_GetIPDOverflowCount(void);
uint32_t App_ESP01S_GetTxDropCount(void);
uint32_t App_ESP01S_GetTelemetryOverwriteCount(void);
uint32_t App_ESP01S_GetIPDDispatchCount(void);

/* ============================================================
 * 中断回调（main.c ISR 中调用，与 app_uart 同模式）
 * ============================================================ */
void App_ESP01S_Tx_DMA_Done_IRQHandler(void);   /* DMA CH3 完成 */
void App_ESP01S_RX_IRQHandler(uint16_t rx_len); /* UART1 IDLE/Timeout */

#endif /* APP_ESP01S_H */
