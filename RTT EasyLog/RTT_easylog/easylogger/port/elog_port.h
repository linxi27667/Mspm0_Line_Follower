/**
 * @file    elog_port.h
 * @brief   EasyLogger 端口扩展接口（ESP-01S 日志透传后端）
 * @note    在 elog_port.c 基础上新增 ESP-01S 透传后端，使 elog_i/elog_w/...
 *          一条语句同时输出到 RTT 和 ESP-01S（TCP 透传到 PC 上位机）。
 *
 * 用法：
 *          // main.c 在 ESP-01S 建连成功后启用
 *          elog_port_esp_enable(true);
 *
 *          // main.c 主循环中 flush
 *          while (1) {
 *              App_ESP01S_Poll();
 *              App_Tuning_Poll();
 *              elog_port_esp_flush();   // 把 elog 缓冲通过 ESP 发往 PC
 *          }
 */
#ifndef ELOG_PORT_H
#define ELOG_PORT_H

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* 启用/禁用 ESP-01S 日志透传后端
 * 启用后，所有 elog_i/elog_w/elog_e/elog_d 输出会同时写入 RTT 和 ESP 环形缓冲
 * 禁用时清空缓冲，elog 仅输出到 RTT */
void elog_port_esp_enable(bool en);

/* 主循环调用：把缓冲的 elog 日志通过 ESP-01S CIPSEND 发往 PC
 * 非阻塞，TCP 断开时自动丢弃缓冲
 * 每次最多发送 256 字节，避免占用 TCP 通道过久影响遥测 */
void elog_port_esp_flush(void);

#ifdef __cplusplus
}
#endif

#endif /* ELOG_PORT_H */
