/**
 * @file    app_esp01s.c
 * @brief   ESP-01S 应用层实现（HW 绑定 + WiFi/TCP 建连 + JSON 收发）
 * @note    分层与 app_uart.c 完全对称：
 *            1) 缓冲区定义（DMA RX 暂存 / RX FIFO / TX FIFO）
 *            2) HW 钩子实现（Init / StartTxChunk / StopTx / RestartRx）—— 绑 UART1+DMA CH2/CH3
 *            3) 对象实例化（ESP_Uart_Dev: bsp_uart_t / g_esp_at: bsp_esp_at_ctx_t）
 *            4) 业务切入（Init / Poll / SendJSON入队 / RegisterRx）
 *            5) 中断回调（供 main.c ISR 调用）
 *
 *          建连流程（参考排队叫号系统 esp8266_mqtt.c 的 MQTT_Init，去掉 MQTT 层）：
 *            AT → ATE0 → CWMODE=1 → CWDHCP=1,1 → CWJAP → CIPMUX=0 → CIPMODE=0 → CIPSTART
 */
#include "app_esp01s.h"
#include "app_common.h"
#include "ti_msp_dl_config.h"
#include <string.h>
#include <stdio.h>
#include "elog.h"

#undef LOG_TAG
#define LOG_TAG  "esp01s"

#define ESP01S_TX_QUEUE_LEN      6
#define ESP01S_TX_FRAME_MAX      ESP01S_IPD_BUF_SIZE
#define ESP01S_TX_STEP_TIMEOUT   ESP01S_AT_TIMEOUT_SEND
#define ESP01S_TX_GAP_MS         100u
#define ESP01S_TCP_RECONNECT_INTERVAL_MS 3000u
#define ESP01S_BAUD_115200       115200u

/* ============================================================
 * 1. 缓冲区定义
 * ============================================================ */

/* DMA 接收暂存（供 main.c ISR 访问，非 static） */
uint8_t g_esp_rx_dma_buf[ESP01S_DMA_RX_BUF_SIZE];
static volatile uint16_t s_esp_rx_dma_pumped = 0;
static uint32_t s_uart_at_tx_bytes = 0;
static uint32_t s_uart_fifo_rx_bytes = 0;

/* RX 软件 FIFO（环形） */
static uint8_t s_esp_rx_fifo_buf[ESP01S_RX_FIFO_SIZE];

/* TX 软件 FIFO（环形）—— DMA 直接读此处，零拷贝 */
static uint8_t s_esp_tx_fifo_buf[ESP01S_TX_FIFO_SIZE];

/* AT 引擎缓冲 */
static uint8_t s_esp_line_buf[ESP01S_LINE_BUF_SIZE];
static uint8_t s_esp_ipd_buf[ESP01S_IPD_BUF_SIZE];

static void HW_ESP_UART_PumpRx(void);
static void HW_ESP_UART_SendCmdBlocking(const uint8_t *data, uint16_t len);

/* ============================================================
 * 2. HW 钩子实现（绑 UART1 + DMA CH2 RX / CH3 TX）
 *    与 app_uart.c 中 UART0 的钩子完全对称，仅替换外设实例与 DMA 通道
 * ============================================================ */

static void HW_ESP_UART_Init(void)
{
    /* SysConfig 已完成 UART1 GPIO/波特率/FIFO/RX Timeout/DMA 通道配置
     * 此处仅补充 DMA 缓冲区地址、传输长度，并启动 DMA 接收 */
    DL_DMA_setSrcAddr(DMA, ESP01S_DMA_CH_RX, (uint32_t)&ESP01S_UART_INST->RXDATA);
    DL_DMA_setDestAddr(DMA, ESP01S_DMA_CH_RX, (uint32_t)g_esp_rx_dma_buf);
    DL_DMA_setTransferSize(DMA, ESP01S_DMA_CH_RX, ESP01S_DMA_RX_BUF_SIZE);
    s_esp_rx_dma_pumped = 0;
    DL_DMA_enableChannel(DMA, ESP01S_DMA_CH_RX);

    /* 显式使能 UART1/DMA NVIC 中断，确保 RX Timeout 与 TX DMA done 都能进 ISR。 */
    NVIC_SetPriority(ESP01S_UART_INT_IRQn, 5);
    NVIC_EnableIRQ(ESP01S_UART_INT_IRQn);
    NVIC_SetPriority(DMA_INT_IRQn, 4);
    NVIC_EnableIRQ(DMA_INT_IRQn);
}

static void HW_ESP_UART_RestartRx(void)
{
    s_esp_rx_dma_pumped = 0;
    DL_DMA_setDestAddr(DMA, ESP01S_DMA_CH_RX, (uint32_t)g_esp_rx_dma_buf);
    DL_DMA_setTransferSize(DMA, ESP01S_DMA_CH_RX, ESP01S_DMA_RX_BUF_SIZE);
    DL_DMA_enableChannel(DMA, ESP01S_DMA_CH_RX);
}

static void HW_ESP_UART_StartTxChunk(const uint8_t *src, uint16_t len)
{
    if (len == 0) return;
    DL_DMA_setSrcAddr(DMA, ESP01S_DMA_CH_TX, (uint32_t)src);
    DL_DMA_setDestAddr(DMA, ESP01S_DMA_CH_TX, (uint32_t)&ESP01S_UART_INST->TXDATA);
    DL_DMA_setTransferSize(DMA, ESP01S_DMA_CH_TX, len);
    DL_UART_enableDMATransmitEvent(ESP01S_UART_INST);
    DL_DMA_enableChannel(DMA, ESP01S_DMA_CH_TX);
}

static void HW_ESP_UART_StopTx(void)
{
    DL_UART_disableDMATransmitEvent(ESP01S_UART_INST);
}

/* ============================================================
 * 3. 对象实例化
 * ============================================================ */

bsp_uart_t ESP_Uart_Dev = {
    .Init         = HW_ESP_UART_Init,
    .StartTxChunk = HW_ESP_UART_StartTxChunk,
    .StopTx       = HW_ESP_UART_StopTx,
    .RestartRx    = HW_ESP_UART_RestartRx,
    .PumpRx       = HW_ESP_UART_PumpRx,
    .SendCmdBlocking = HW_ESP_UART_SendCmdBlocking,

    .rx_fifo_buf  = s_esp_rx_fifo_buf,
    .rx_fifo_size = ESP01S_RX_FIFO_SIZE,
    .rx_fifo_head = 0,
    .rx_fifo_tail = 0,

    .rx_frame_head = 0,
    .rx_frame_tail = 0,

    .tx_fifo_buf  = s_esp_tx_fifo_buf,
    .tx_fifo_size = ESP01S_TX_FIFO_SIZE,
    .tx_fifo_head = 0,
    .tx_fifo_tail = 0,
    .tx_chunk_len = 0,
    .tx_busy      = false,

    .tx_overflow       = false,
    .rx_overflow       = false,
    .rx_frame_overflow = false,
};

static void HW_ESP_UART_PumpRx(void)
{
    uint16_t fifo_budget = 32;
    while (!DL_UART_Main_isRXFIFOEmpty(ESP01S_UART_INST) && fifo_budget-- > 0) {
        uint8_t b = (uint8_t)DL_UART_Main_receiveData(ESP01S_UART_INST);
        Bsp_UART_Rx_PushBytes(&ESP_Uart_Dev, &b, 1);
        s_uart_fifo_rx_bytes++;
    }

    uint16_t remain = DL_DMA_getTransferSize(DMA, ESP01S_DMA_CH_RX);
    if (remain > ESP01S_DMA_RX_BUF_SIZE) {
        return;
    }

    uint16_t used = (uint16_t)(ESP01S_DMA_RX_BUF_SIZE - remain);
    if (used == 0) {
        return;
    }
    if (used < s_esp_rx_dma_pumped) {
        s_esp_rx_dma_pumped = 0;
    }
    if (used > s_esp_rx_dma_pumped) {
        Bsp_UART_Rx_PushBytes(&ESP_Uart_Dev,
                              &g_esp_rx_dma_buf[s_esp_rx_dma_pumped],
                              (uint16_t)(used - s_esp_rx_dma_pumped));
        s_esp_rx_dma_pumped = used;
    }
    if (used >= ESP01S_DMA_RX_BUF_SIZE) {
        HW_ESP_UART_RestartRx();
    }
}

static void HW_ESP_UART_SendCmdBlocking(const uint8_t *data, uint16_t len)
{
    if (data == NULL || len == 0) return;

    for (uint16_t i = 0; i < len; i++) {
        uint32_t start = Bsp_GetTick();
        while (DL_UART_Main_isTXFIFOFull(ESP01S_UART_INST)) {
            if ((Bsp_GetTick() - start) > 20u) {
                elog_w(LOG_TAG, "AT TX timeout at byte %u", (unsigned)i);
                return;
            }
        }
        DL_UART_Main_transmitData(ESP01S_UART_INST, data[i]);
        s_uart_at_tx_bytes++;
    }
}

static bsp_esp_at_ctx_t g_esp_at;

/* 运行时状态 */
static volatile bool s_wifi_connected = false;
static volatile bool s_tcp_connected  = false;
static App_ESP01S_RxCallback s_rx_callback = NULL;

typedef enum {
    ESP_TX_IDLE = 0,
    ESP_TX_WAIT_PROMPT,
    ESP_TX_WAIT_SEND_OK
} esp_tx_state_t;

typedef struct {
    uint8_t  data[ESP01S_TX_FRAME_MAX];
    uint16_t len;
    bool     is_telemetry;
} esp_tx_frame_t;

static esp_tx_frame_t s_tx_queue[ESP01S_TX_QUEUE_LEN];
static uint8_t        s_tx_head = 0;
static uint8_t        s_tx_tail = 0;
static uint8_t        s_tx_count = 0;

static uint8_t        s_tx_active[ESP01S_TX_FRAME_MAX];
static uint16_t       s_tx_active_len = 0;
static esp_tx_state_t s_tx_state = ESP_TX_IDLE;
static uint32_t       s_tx_deadline = 0;
static uint32_t       s_tx_next_allowed = 0;

static uint32_t       s_tx_drop_count = 0;
static uint32_t       s_tx_telemetry_overwrite_count = 0;
static uint32_t       s_ipd_dispatch_count = 0;
static uint32_t       s_uart_baud = ESP01S_BAUD_115200;
static uint32_t       s_tcp_reconnect_next = 0;

static void esp_log_at_diag(const char *stage)
{
    elog_w(LOG_TAG,
           "%s diag: baud=%lu at_fail=%lu at_tx=%lu fifo_rx=%lu rx_avail=%u rx_frames=%u tx_pending=%u tx_busy=%u tx_over=%u rx_over=%u rx_frame_over=%u line='%s'",
           stage,
           (unsigned long)s_uart_baud,
           (unsigned long)g_esp_at.at_fail_count,
           (unsigned long)s_uart_at_tx_bytes,
           (unsigned long)s_uart_fifo_rx_bytes,
           (unsigned)Bsp_UART_Available(&ESP_Uart_Dev),
           (unsigned)Bsp_UART_Frame_Count(&ESP_Uart_Dev),
           (unsigned)Bsp_UART_TxPending(&ESP_Uart_Dev),
           ESP_Uart_Dev.tx_busy ? 1u : 0u,
           ESP_Uart_Dev.tx_overflow ? 1u : 0u,
           ESP_Uart_Dev.rx_overflow ? 1u : 0u,
           ESP_Uart_Dev.rx_frame_overflow ? 1u : 0u,
           Bsp_ESP_AT_GetLine(&g_esp_at));
    elog_w(LOG_TAG,
           "UART1 pins: PA8_TX PINCM=0x%08lX PA9_RX PINCM=0x%08lX GPIOA DIN=0x%08lX DOUT=0x%08lX DOE=0x%08lX",
           (unsigned long)IOMUX->SECCFG.PINCM[GPIO_UART_ESP01S_IOMUX_TX],
           (unsigned long)IOMUX->SECCFG.PINCM[GPIO_UART_ESP01S_IOMUX_RX],
           (unsigned long)GPIOA->DIN31_0,
           (unsigned long)GPIOA->DOUT31_0,
           (unsigned long)GPIOA->DOE31_0);
}

static bool is_telemetry_frame(const uint8_t *data, uint16_t len)
{
    const char needle[] = "\"t\":\"tele\"";
    if (data == NULL || len < (sizeof(needle) - 1)) return false;
    for (uint16_t i = 0; i <= (uint16_t)(len - (sizeof(needle) - 1)); i++) {
        if (memcmp(&data[i], needle, sizeof(needle) - 1) == 0) {
            return true;
        }
    }
    return false;
}

static void tx_queue_clear(void)
{
    s_tx_head = 0;
    s_tx_tail = 0;
    s_tx_count = 0;
    s_tx_active_len = 0;
    s_tx_state = ESP_TX_IDLE;
    s_tx_next_allowed = 0;
}

static bool tx_queue_push(const uint8_t *data, uint16_t len)
{
    if (data == NULL || len == 0 || len > ESP01S_TX_FRAME_MAX) {
        s_tx_drop_count++;
        return false;
    }

    bool tele = is_telemetry_frame(data, len);

    if (tele) {
        uint8_t idx = s_tx_head;
        for (uint8_t i = 0; i < s_tx_count; i++) {
            if (s_tx_queue[idx].is_telemetry) {
                memcpy(s_tx_queue[idx].data, data, len);
                s_tx_queue[idx].len = len;
                s_tx_telemetry_overwrite_count++;
                return true;
            }
            idx = (uint8_t)((idx + 1) % ESP01S_TX_QUEUE_LEN);
        }
        if (s_tx_count >= ESP01S_TX_QUEUE_LEN) {
            memcpy(s_tx_queue[s_tx_head].data, data, len);
            s_tx_queue[s_tx_head].len = len;
            s_tx_queue[s_tx_head].is_telemetry = true;
            s_tx_telemetry_overwrite_count++;
            return true;
        }
    }

    if (s_tx_count >= ESP01S_TX_QUEUE_LEN) {
        s_tx_drop_count++;
        return false;
    }

    memcpy(s_tx_queue[s_tx_tail].data, data, len);
    s_tx_queue[s_tx_tail].len = len;
    s_tx_queue[s_tx_tail].is_telemetry = tele;
    s_tx_tail = (uint8_t)((s_tx_tail + 1) % ESP01S_TX_QUEUE_LEN);
    s_tx_count++;
    return true;
}

static bool tx_queue_pop(uint8_t *out, uint16_t *out_len)
{
    if (s_tx_count == 0 || out == NULL || out_len == NULL) return false;
    *out_len = s_tx_queue[s_tx_head].len;
    memcpy(out, s_tx_queue[s_tx_head].data, *out_len);
    s_tx_head = (uint8_t)((s_tx_head + 1) % ESP01S_TX_QUEUE_LEN);
    s_tx_count--;
    return true;
}

static void tx_state_fail(const char *reason)
{
    s_tx_drop_count++;
    s_tx_state = ESP_TX_IDLE;
    s_tx_active_len = 0;
    s_tcp_reconnect_next = Bsp_GetTick() + 500u;
    if (reason != NULL) {
        esp_log_at_diag(reason);
        elog_w(LOG_TAG, "TX async fail: %s", reason);
    }
    Bsp_ESP_AT_ClearLine(&g_esp_at);
}

static void tx_state_poll(void)
{
    if (!s_tcp_connected) {
        tx_queue_clear();
        return;
    }

    const char *line = Bsp_ESP_AT_GetLine(&g_esp_at);
    uint32_t now = Bsp_GetTick();

    switch (s_tx_state) {
    case ESP_TX_IDLE:
        if ((int32_t)(now - s_tx_next_allowed) < 0) {
            break;
        }
        if (tx_queue_pop(s_tx_active, &s_tx_active_len)) {
            char cmd[24];
            snprintf(cmd, sizeof(cmd), "AT+CIPSEND=%u\r\n",
                     (unsigned)s_tx_active_len);
            Bsp_ESP_AT_ClearLine(&g_esp_at);
            HW_ESP_UART_SendCmdBlocking((const uint8_t *)cmd,
                                        (uint16_t)strlen(cmd));
            s_tx_deadline = now + ESP01S_TX_STEP_TIMEOUT;
            s_tx_state = ESP_TX_WAIT_PROMPT;
        }
        break;

    case ESP_TX_WAIT_PROMPT:
        if (line != NULL && strstr(line, ">") != NULL) {
            Bsp_ESP_AT_ClearLine(&g_esp_at);
            HW_ESP_UART_SendCmdBlocking(s_tx_active, s_tx_active_len);
            s_tx_deadline = now + ESP01S_TX_STEP_TIMEOUT;
            s_tx_state = ESP_TX_WAIT_SEND_OK;
        } else if (line != NULL &&
                   (strstr(line, "ERROR") != NULL ||
                    strstr(line, "FAIL") != NULL ||
                    strstr(line, "CLOSED") != NULL)) {
            s_tcp_connected = false;
            tx_state_fail("prompt error");
        } else if ((int32_t)(now - s_tx_deadline) >= 0) {
            s_tcp_connected = false;
            tx_state_fail("prompt timeout");
        }
        break;

    case ESP_TX_WAIT_SEND_OK:
        if (line != NULL &&
            (strstr(line, "SEND OK") != NULL || strstr(line, "Recv ") != NULL)) {
            Bsp_ESP_AT_ClearLine(&g_esp_at);
            s_tx_active_len = 0;
            s_tx_state = ESP_TX_IDLE;
            s_tx_next_allowed = now + ESP01S_TX_GAP_MS;
        } else if (line != NULL &&
                   (strstr(line, "ERROR") != NULL ||
                    strstr(line, "FAIL") != NULL ||
                    strstr(line, "SEND FAIL") != NULL ||
                    strstr(line, "CLOSED") != NULL)) {
            s_tcp_connected = false;
            tx_state_fail("send error");
        } else if ((int32_t)(now - s_tx_deadline) >= 0) {
            s_tcp_connected = false;
            tx_state_fail("send timeout");
        }
        break;

    default:
        s_tx_state = ESP_TX_IDLE;
        break;
    }
}

/* ============================================================
 * 4. 内部：WiFi + TCP 建连流程
 * ============================================================ */

/* 发送一条 AT 指令并打印结果（失败时 elog_w） */
static bool send_at(const char *cmd, const char *expect, uint32_t timeout_ms)
{
    bool ok = Bsp_ESP_AT_SendCmd(&g_esp_at, cmd, expect, timeout_ms);
    if (!ok) {
        elog_w(LOG_TAG, "AT fail: %.*s", (int)(strlen(cmd) > 40 ? 40 : strlen(cmd)), cmd);
    }
    return ok;
}

static bool connect_wifi(void)
{
    char cmd[96];

    /* 1. AT 测试（参考 esp8266.c：先开接收，再发 AT，缓冲内找 OK） */
    s_uart_baud = ESP01S_BAUD_115200;
    elog_i(LOG_TAG, "AT probe at 115200 baud (STM32 reference)");
    if (!Bsp_ESP_AT_SendCmdRetry(&g_esp_at, "AT\r\n", "OK",
                                 ESP01S_AT_TIMEOUT_SHORT,
                                 ESP01S_AT_RETRIES,
                                 ESP01S_AT_RETRY_DELAY_MS)) {
        esp_log_at_diag("AT probe 115200 fail");
        elog_e(LOG_TAG, "AT no response at 115200, check ESP power/EN/GND/TX/RX");
        return false;
    }
    elog_i(LOG_TAG, "ESP AT ready at 115200");

    /* 2. 关回显 */
    (void)Bsp_ESP_AT_SendCmdRetry(&g_esp_at, "ATE0\r\n", "OK",
                                  ESP01S_AT_TIMEOUT_SHORT, 3,
                                  ESP01S_AT_RETRY_DELAY_MS);

    /* 3. Station 模式 */
    if (!send_at("AT+CWMODE=1\r\n", "OK", ESP01S_AT_TIMEOUT_SHORT)) return false;

    /* 4. 开 DHCP */
    if (!send_at("AT+CWDHCP=1,1\r\n", "OK", ESP01S_AT_TIMEOUT_SHORT)) return false;

    /* 5. 连 AP（信号不稳，多重试） */
    snprintf(cmd, sizeof(cmd), "AT+CWJAP=\"%s\",\"%s\"\r\n",
             ESP01S_WIFI_SSID, ESP01S_WIFI_PASS);
    if (!Bsp_ESP_AT_SendCmdRetry(&g_esp_at, cmd, "GOT IP",
                                 ESP01S_AT_TIMEOUT_LONG, ESP01S_AT_RETRIES_AP,
                                 ESP01S_AT_RETRY_DELAY_MS)) {
        elog_e(LOG_TAG, "CWJAP fail, SSID=%s", ESP01S_WIFI_SSID);
        return false;
    }
    s_wifi_connected = true;
    elog_i(LOG_TAG, "WiFi connected, SSID=%s", ESP01S_WIFI_SSID);
    return true;
}

static bool connect_tcp(void)
{
    char cmd[80];

    /* 关闭旧连接（若有） */
    (void)Bsp_ESP_AT_SendCmd(&g_esp_at, "AT+CIPCLOSE\r\n", "OK",
                             ESP01S_AT_TIMEOUT_SHORT);

    /* 单连接模式 + 非透传 */
    if (!send_at("AT+CIPMUX=0\r\n", "OK", ESP01S_AT_TIMEOUT_SHORT)) return false;
    if (!send_at("AT+CIPMODE=0\r\n", "OK", ESP01S_AT_TIMEOUT_SHORT)) return false;

    /* TCP 连服务器 */
    snprintf(cmd, sizeof(cmd), "AT+CIPSTART=\"TCP\",\"%s\",%d\r\n",
             ESP01S_SERVER_IP, ESP01S_SERVER_PORT);
    if (!Bsp_ESP_AT_SendCmdRetry(&g_esp_at, cmd, "CONNECT",
                                 ESP01S_AT_TIMEOUT_CONNECT, ESP01S_AT_RETRIES,
                                 ESP01S_AT_RETRY_DELAY_MS)) {
        elog_e(LOG_TAG, "CIPSTART fail, server=%s:%d",
               ESP01S_SERVER_IP, ESP01S_SERVER_PORT);
        return false;
    }
    s_tcp_connected = true;
    s_tcp_reconnect_next = 0;
    elog_i(LOG_TAG, "TCP connected, server=%s:%d",
           ESP01S_SERVER_IP, ESP01S_SERVER_PORT);
    return true;
}

/* ============================================================
 * 5. 业务切入点
 * ============================================================ */

bool App_ESP01S_Init(App_ESP01S_ProgressCb progress)
{
    s_wifi_connected = false;
    s_tcp_connected  = false;
    s_rx_callback    = NULL;
    s_tcp_reconnect_next = 0;
    tx_queue_clear();

    /* 5.1 初始化 ESP UART（UART1 + DMA） */
    Bsp_UART_Init(&ESP_Uart_Dev);

    /* 5.2 初始化 AT 引擎 */
    Bsp_ESP_AT_Init(&g_esp_at, &ESP_Uart_Dev,
                    s_esp_line_buf, ESP01S_LINE_BUF_SIZE,
                    s_esp_ipd_buf,  ESP01S_IPD_BUF_SIZE);

    /* 5.3 ESP-01S 上电稳定 */
    if (progress) progress(1, "ESP01S booting");
    elog_i(LOG_TAG, "boot delay %dms", ESP01S_BOOT_DELAY_MS);
    Bsp_Delay_ms(ESP01S_BOOT_DELAY_MS);

    /* 5.4 WiFi 建连 */
    if (progress) progress(2, "WiFi connecting");
    if (!connect_wifi()) {
        if (progress) progress(0xFF, "WiFi FAIL");
        return false;
    }

    /* 5.5 TCP 建连 */
    if (progress) progress(3, "TCP connecting");
    if (!connect_tcp()) {
        if (progress) progress(0xFF, "TCP FAIL");
        return false;
    }

    if (progress) progress(4, "ESP01S ready");
    elog_i(LOG_TAG, "ESP-01S ready, AI tuning link up");
    return true;
}

bool App_ESP01S_ReconnectTCP(void)
{
    s_tcp_connected = false;
    tx_queue_clear();
    elog_w(LOG_TAG, "reconnecting TCP");
    return connect_tcp();
}

void App_ESP01S_RegisterRx(App_ESP01S_RxCallback cb)
{
    s_rx_callback = cb;
}

void App_ESP01S_Poll(void)
{
    uint16_t len;
    uint32_t now = Bsp_GetTick();

    /* 排空 UART，重组 +IPD；每收到一帧完整 JSON 立即派发给回调 */
    while (Bsp_ESP_AT_Poll(&g_esp_at, &len)) {
        if (s_rx_callback != NULL && len > 0) {
            s_ipd_dispatch_count++;
            s_rx_callback(g_esp_at.ipd_buf, len);
        }
    }

    /* 被动检测连接断开（异步通知在响应流缓冲中）
     * 数据阶段无 AT 指令交互，响应流缓冲里只有 ESP 主动上报的 CLOSED/WIFI DISCONNECT
     * 检测到后清空缓冲，避免下次重复触发 */
    const char *line = Bsp_ESP_AT_GetLine(&g_esp_at);
    if (line != NULL && line[0] != '\0') {
        if (strstr(line, "CLOSED") != NULL) {
            s_tcp_connected = false;
            elog_w(LOG_TAG, "TCP closed by remote");
            Bsp_ESP_AT_ClearLine(&g_esp_at);
        } else if (strstr(line, "WIFI DISCONNECT") != NULL) {
            s_wifi_connected = false;
            s_tcp_connected  = false;
            elog_w(LOG_TAG, "WiFi disconnected");
            Bsp_ESP_AT_ClearLine(&g_esp_at);
        }
    }

    if (s_wifi_connected && !s_tcp_connected &&
        (int32_t)(now - s_tcp_reconnect_next) >= 0) {
        s_tcp_reconnect_next = now + ESP01S_TCP_RECONNECT_INTERVAL_MS;
        tx_queue_clear();
        elog_w(LOG_TAG, "TCP reconnect attempt");
        (void)connect_tcp();
        return;
    }

    tx_state_poll();
}

bool App_ESP01S_SendJSON(const uint8_t *data, uint16_t len)
{
    if (!s_tcp_connected) return false;
    if (data == NULL || len == 0) return false;
    return tx_queue_push(data, len);
}

bool App_ESP01S_SendJSONString(const char *s)
{
    if (s == NULL) return false;
    return App_ESP01S_SendJSON((const uint8_t *)s, (uint16_t)strlen(s));
}

/* ============================================================
 * 6. 状态查询
 * ============================================================ */
bool     App_ESP01S_IsWiFiConnected(void)   { return s_wifi_connected; }
bool     App_ESP01S_IsTCPConnected(void)    { return s_tcp_connected; }
uint32_t App_ESP01S_GetATFailCount(void)    { return g_esp_at.at_fail_count; }
uint32_t App_ESP01S_GetIPDOverflowCount(void) { return g_esp_at.ipd_overflow_count; }
uint32_t App_ESP01S_GetTxDropCount(void)    { return s_tx_drop_count; }
uint32_t App_ESP01S_GetTelemetryOverwriteCount(void) { return s_tx_telemetry_overwrite_count; }
uint32_t App_ESP01S_GetIPDDispatchCount(void) { return s_ipd_dispatch_count; }

/* ============================================================
 * 7. 中断回调（main.c ISR 调用）
 * ============================================================ */

void App_ESP01S_Tx_DMA_Done_IRQHandler(void)
{
    Bsp_UART_Tx_OnDMAComplete(&ESP_Uart_Dev);
}

void App_ESP01S_RX_IRQHandler(uint16_t rx_len)
{
    if (rx_len > ESP01S_DMA_RX_BUF_SIZE) {
        rx_len = ESP01S_DMA_RX_BUF_SIZE;
    }
    if (rx_len > s_esp_rx_dma_pumped) {
        Bsp_UART_Rx_PushBytes(&ESP_Uart_Dev,
                              &g_esp_rx_dma_buf[s_esp_rx_dma_pumped],
                              (uint16_t)(rx_len - s_esp_rx_dma_pumped));
    }
    HW_ESP_UART_RestartRx();
}
