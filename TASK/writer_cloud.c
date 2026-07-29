/**
 * @file writer_cloud.c
 * @brief Time-sliced ESP-AT, MQTT, and writer job orchestration.
 */
#include "writer_cloud.h"

#include <stddef.h>
#include <stdio.h>
#include <string.h>

#include "app_writer_identity.h"
#include "bsp_esp_at.h"
#include "bsp_mqtt.h"
#include "bsp_writer_job.h"
#include "bsp_writer_protocol.h"
#include "comm_vision_uart.h"
#include "elog.h"
#include "gcode_serial.h"
#include "writer_net_config.h"
#include "writer_rehome.h"
#include "writer_test.h"

#define WRITER_CLOUD_TOPIC_MAX       (72u)
#define WRITER_CLOUD_JSON_MAX        (384u)
#define WRITER_CLOUD_AT_COMMAND_MAX  (192u)
#define WRITER_CLOUD_MQTT_PACKET_MAX (512u)
#define WRITER_CLOUD_SUB_PACKET_ID   (1u)

typedef enum {
    WRITER_CLOUD_LINK_DISABLED = 0,
    WRITER_CLOUD_LINK_RECONNECT_DELAY,
    WRITER_CLOUD_LINK_AT,
    WRITER_CLOUD_LINK_ECHO_OFF,
    WRITER_CLOUD_LINK_STA_MODE,
    WRITER_CLOUD_LINK_DHCP,
    WRITER_CLOUD_LINK_JOIN_WIFI,
    WRITER_CLOUD_LINK_CLOSE_OLD,
    WRITER_CLOUD_LINK_SINGLE_CONNECTION,
    WRITER_CLOUD_LINK_NORMAL_MODE,
    WRITER_CLOUD_LINK_TCP,
    WRITER_CLOUD_LINK_SEND_CONNECT,
    WRITER_CLOUD_LINK_WAIT_CONNACK,
    WRITER_CLOUD_LINK_SEND_SUBSCRIBE,
    WRITER_CLOUD_LINK_WAIT_SUBACK,
    WRITER_CLOUD_LINK_SEND_AVAILABILITY,
    WRITER_CLOUD_LINK_SEND_INITIAL_STATUS,
    WRITER_CLOUD_LINK_ONLINE,
    WRITER_CLOUD_LINK_CONFIG_ERROR
} writer_cloud_link_state_t;

typedef enum {
    WRITER_CLOUD_TX_IDLE = 0,
    WRITER_CLOUD_TX_WAIT_PROMPT,
    WRITER_CLOUD_TX_SEND_DATA,
    WRITER_CLOUD_TX_WAIT_SEND_OK
} writer_cloud_tx_state_t;

typedef enum {
    WRITER_CLOUD_ACTION_NONE = 0,
    WRITER_CLOUD_ACTION_CONNECT_SENT,
    WRITER_CLOUD_ACTION_SUBSCRIBE_SENT,
    WRITER_CLOUD_ACTION_AVAILABILITY_SENT,
    WRITER_CLOUD_ACTION_STATUS_SENT,
    WRITER_CLOUD_ACTION_EXECUTE_LINE,
    WRITER_CLOUD_ACTION_CLEAR_JOB,
    WRITER_CLOUD_ACTION_FINISH_JOB,
    WRITER_CLOUD_ACTION_SEND_STATUS,
    WRITER_CLOUD_ACTION_PING_SENT
} writer_cloud_action_t;

typedef struct {
    writer_cloud_link_state_t link_state;
    writer_cloud_tx_state_t tx_state;
    writer_cloud_action_t tx_action;
    bsp_esp_at_parser_t at_parser;
    bsp_mqtt_parser_t mqtt_parser;
    bsp_writer_job_t job;
    char boot_id[9];
    char command_topic[WRITER_CLOUD_TOPIC_MAX];
    char ack_topic[WRITER_CLOUD_TOPIC_MAX];
    char status_topic[WRITER_CLOUD_TOPIC_MAX];
    char availability_topic[WRITER_CLOUD_TOPIC_MAX];
    char pending_line[BSP_WRITER_GCODE_BUFFER_SIZE];
    uint8_t mqtt_packet[WRITER_CLOUD_MQTT_PACKET_MAX];
    uint16_t mqtt_packet_len;
    uint16_t mqtt_packet_offset;
    uint32_t tx_trace_id;
    uint32_t deadline_ms;
    uint32_t reconnect_delay_ms;
    uint32_t last_activity_ms;
    uint32_t last_status_ms;
    bool step_started;
    bool at_ok;
    bool at_error;
    bool prompt;
    bool send_ok;
    bool connack;
    bool suback;
    bool online;
    bool needs_rehome;
    bool suppress_gcode_result;
    bool ping_outstanding;
    bool gcode_result_pending;
    bool gcode_result_ok;
    const char *gcode_result_error;
    bool stop_ack_pending;
    char stop_request_id[BSP_WRITER_REQUEST_ID_MAX + 1u];
    bool rehome_completion_pending;
    char rehome_request_id[BSP_WRITER_REQUEST_ID_MAX + 1u];
    bool rehome_has_completed;
    char rehome_completed_request_id[BSP_WRITER_REQUEST_ID_MAX + 1u];
} writer_cloud_context_t;

extern volatile uint32_t s_sys_tick;

static writer_cloud_context_t s_cloud;

static const char *WriterCloud_Link_State_Name(
    writer_cloud_link_state_t state)
{
    switch (state) {
        case WRITER_CLOUD_LINK_DISABLED: return "disabled";
        case WRITER_CLOUD_LINK_RECONNECT_DELAY: return "reconnect_delay";
        case WRITER_CLOUD_LINK_AT: return "at";
        case WRITER_CLOUD_LINK_ECHO_OFF: return "echo_off";
        case WRITER_CLOUD_LINK_STA_MODE: return "sta_mode";
        case WRITER_CLOUD_LINK_DHCP: return "dhcp";
        case WRITER_CLOUD_LINK_JOIN_WIFI: return "join_wifi";
        case WRITER_CLOUD_LINK_CLOSE_OLD: return "close_old";
        case WRITER_CLOUD_LINK_SINGLE_CONNECTION: return "single_connection";
        case WRITER_CLOUD_LINK_NORMAL_MODE: return "normal_mode";
        case WRITER_CLOUD_LINK_TCP: return "tcp";
        case WRITER_CLOUD_LINK_SEND_CONNECT: return "send_connect";
        case WRITER_CLOUD_LINK_WAIT_CONNACK: return "wait_connack";
        case WRITER_CLOUD_LINK_SEND_SUBSCRIBE: return "send_subscribe";
        case WRITER_CLOUD_LINK_WAIT_SUBACK: return "wait_suback";
        case WRITER_CLOUD_LINK_SEND_AVAILABILITY: return "send_availability";
        case WRITER_CLOUD_LINK_SEND_INITIAL_STATUS: return "send_initial_status";
        case WRITER_CLOUD_LINK_ONLINE: return "online";
        case WRITER_CLOUD_LINK_CONFIG_ERROR: return "config_error";
        default: return "unknown";
    }
}

static const char *WriterCloud_Tx_State_Name(writer_cloud_tx_state_t state)
{
    switch (state) {
        case WRITER_CLOUD_TX_IDLE: return "idle";
        case WRITER_CLOUD_TX_WAIT_PROMPT: return "wait_prompt";
        case WRITER_CLOUD_TX_SEND_DATA: return "send_data";
        case WRITER_CLOUD_TX_WAIT_SEND_OK: return "wait_send_ok";
        default: return "unknown";
    }
}

static const char *WriterCloud_Action_Name(writer_cloud_action_t action)
{
    switch (action) {
        case WRITER_CLOUD_ACTION_NONE: return "none";
        case WRITER_CLOUD_ACTION_CONNECT_SENT: return "mqtt_connect";
        case WRITER_CLOUD_ACTION_SUBSCRIBE_SENT: return "mqtt_subscribe";
        case WRITER_CLOUD_ACTION_AVAILABILITY_SENT: return "availability";
        case WRITER_CLOUD_ACTION_STATUS_SENT: return "status";
        case WRITER_CLOUD_ACTION_EXECUTE_LINE: return "gcode_accepted";
        case WRITER_CLOUD_ACTION_CLEAR_JOB: return "clear_job";
        case WRITER_CLOUD_ACTION_FINISH_JOB: return "finish_job";
        case WRITER_CLOUD_ACTION_SEND_STATUS: return "ack_then_status";
        case WRITER_CLOUD_ACTION_PING_SENT: return "ping";
        default: return "unknown";
    }
}

static const char *WriterCloud_Operation_Name(
    bsp_writer_operation_t operation)
{
    switch (operation) {
        case BSP_WRITER_OP_JOB_BEGIN: return "job_begin";
        case BSP_WRITER_OP_GCODE: return "gcode";
        case BSP_WRITER_OP_JOB_END: return "job_end";
        case BSP_WRITER_OP_STATUS: return "status";
        case BSP_WRITER_OP_STOP: return "stop";
        case BSP_WRITER_OP_REHOME: return "rehome";
        case BSP_WRITER_OP_NONE:
        default: return "unknown";
    }
}

static const char *WriterCloud_At_Command_Name(const char *command)
{
    if (command == NULL) return "null";
    if (strcmp(command, "AT\r\n") == 0) return "AT";
    if (strcmp(command, "ATE0\r\n") == 0) return "ATE0";
    if (strcmp(command, "AT+CWMODE=1\r\n") == 0) return "AT+CWMODE=1";
    if (strcmp(command, "AT+CWDHCP=1,1\r\n") == 0) return "AT+CWDHCP=1,1";
    if (strncmp(command, "AT+CWJAP=", 9u) == 0) {
        return "AT+CWJAP=<credentials-redacted>";
    }
    if (strcmp(command, "AT+CIPCLOSE\r\n") == 0) return "AT+CIPCLOSE";
    if (strcmp(command, "AT+CIPMUX=0\r\n") == 0) return "AT+CIPMUX=0";
    if (strcmp(command, "AT+CIPMODE=0\r\n") == 0) return "AT+CIPMODE=0";
    if (strncmp(command, "AT+CIPSTART=", 12u) == 0) {
        return "AT+CIPSTART=<endpoint>";
    }
    return "AT+UNKNOWN";
}

static bool WriterCloud_Time_Reached(uint32_t deadline)
{
    return (int32_t)(s_sys_tick - deadline) >= 0;
}

static bool WriterCloud_Copy_Is_At_Safe(const char *text)
{
    const char *cursor = text;

    if ((text == NULL) || (text[0] == '\0')) {
        return false;
    }
    while (*cursor != '\0') {
        if ((*cursor == '"') || (*cursor == '\\') ||
            (*cursor == '\r') || (*cursor == '\n')) {
            return false;
        }
        cursor++;
    }
    return true;
}

static bool WriterCloud_Optional_Copy_Is_At_Safe(const char *text)
{
    return (text != NULL) &&
           ((text[0] == '\0') || WriterCloud_Copy_Is_At_Safe(text));
}

static bool WriterCloud_Config_Is_Valid(void)
{
    return Bsp_Writer_Id_Is_Valid(WRITER_NET_DEVICE_ID) &&
           Bsp_Writer_Id_Is_Valid(WRITER_NET_MQTT_CLIENT_ID) &&
           WriterCloud_Copy_Is_At_Safe(WRITER_NET_WIFI_SSID) &&
           WriterCloud_Copy_Is_At_Safe(WRITER_NET_WIFI_PASSWORD) &&
           WriterCloud_Copy_Is_At_Safe(WRITER_NET_BROKER_HOST) &&
           WriterCloud_Optional_Copy_Is_At_Safe(
               WRITER_NET_MQTT_USERNAME) &&
           WriterCloud_Optional_Copy_Is_At_Safe(
               WRITER_NET_MQTT_PASSWORD) &&
           ((WRITER_NET_MQTT_PASSWORD[0] == '\0') ||
            (WRITER_NET_MQTT_USERNAME[0] != '\0')) &&
           (WRITER_NET_BROKER_PORT > 0u) &&
           (WRITER_NET_BROKER_PORT <= 65535u);
}

static const char *WriterCloud_Transport_Name(void)
{
#if WRITER_NET_BROKER_TLS
    return "SSL";
#else
    return "TCP";
#endif
}

static void WriterCloud_Clear_Response_Flags(void)
{
    s_cloud.at_ok = false;
    s_cloud.at_error = false;
    s_cloud.prompt = false;
    s_cloud.send_ok = false;
}

static void WriterCloud_Set_Link_State(writer_cloud_link_state_t state)
{
    writer_cloud_link_state_t previous = s_cloud.link_state;

    s_cloud.link_state = state;
    s_cloud.step_started = false;
    WriterCloud_Clear_Response_Flags();
    if (previous != state) {
        elog_i("CLOUD", "link_state=%s->%s",
               WriterCloud_Link_State_Name(previous),
               WriterCloud_Link_State_Name(state));
    }
}

static bool WriterCloud_Send_At(const char *command, uint32_t timeout_ms)
{
    size_t len;

    if (command == NULL) {
        return false;
    }
    len = strlen(command);
    if ((len == 0u) || (len > UINT16_MAX)) {
        elog_e("ESP_AT", "uart=UART1 step=%s fault=bad_command_length",
               WriterCloud_Link_State_Name(s_cloud.link_state));
        return false;
    }
    if (!App_Vision_UART_Try_Send((const uint8_t *)command,
                                  (uint16_t)len)) {
        elog_e("ESP_AT", "uart=UART1 dir=TX step=%s cmd=%s "
               "result=tx_ring_full",
               WriterCloud_Link_State_Name(s_cloud.link_state),
               WriterCloud_At_Command_Name(command));
        return false;
    }
    if (strncmp(command, "AT+CWJAP=", 9u) == 0) {
        elog_i("ESP_AT", "uart=UART1 dir=TX step=%s cmd=AT+CWJAP "
               "ssid=%s password=<redacted> bytes=%u",
               WriterCloud_Link_State_Name(s_cloud.link_state),
               WRITER_NET_WIFI_SSID, (uint32_t)len);
    } else if (strncmp(command, "AT+CIPSTART=", 12u) == 0) {
        elog_i("ESP_AT", "uart=UART1 dir=TX step=%s cmd=AT+CIPSTART "
               "transport=%s host=%s port=%u bytes=%u",
               WriterCloud_Link_State_Name(s_cloud.link_state),
               WriterCloud_Transport_Name(), WRITER_NET_BROKER_HOST,
               WRITER_NET_BROKER_PORT, (uint32_t)len);
    } else {
        elog_i("ESP_AT", "uart=UART1 dir=TX step=%s cmd=%s bytes=%u",
               WriterCloud_Link_State_Name(s_cloud.link_state),
               WriterCloud_At_Command_Name(command), (uint32_t)len);
    }
    WriterCloud_Clear_Response_Flags();
    s_cloud.deadline_ms = s_sys_tick + timeout_ms;
    s_cloud.step_started = true;
    return true;
}

static void WriterCloud_Safe_Abort(const char *reason)
{
    elog_w("CLOUD", "safe_abort reason=%s job_id=%s active_seq=%lu "
           "expected_seq=%lu pen=%s",
           (reason != NULL) ? reason : "unknown",
           s_cloud.job.active ? s_cloud.job.job_id : "",
           (unsigned long)s_cloud.job.active_seq,
           (unsigned long)s_cloud.job.expected_seq,
           GCodeSerial_Is_Pen_Down() ? "down" : "up");
    WriterRehome_Abort();
    s_cloud.suppress_gcode_result = true;
    GCodeSerial_Abort();
    s_cloud.suppress_gcode_result = false;
    Bsp_WriterJob_Abort(&s_cloud.job);
    s_cloud.gcode_result_pending = false;
    s_cloud.gcode_result_error = NULL;
    s_cloud.rehome_completion_pending = false;
    s_cloud.rehome_request_id[0] = '\0';
    s_cloud.rehome_has_completed = false;
    s_cloud.rehome_completed_request_id[0] = '\0';
    s_cloud.needs_rehome = true;
}

static void WriterCloud_Reconnect(const char *reason)
{
    elog_w("CLOUD", "reconnect reason=%s link_state=%s tx_state=%s "
           "action=%s tx_id=%lu online=%u delay_ms=%lu "
           "uart_rx_dropped=%lu uart_tx_rejected=%lu",
           (reason != NULL) ? reason : "unknown",
           WriterCloud_Link_State_Name(s_cloud.link_state),
           WriterCloud_Tx_State_Name(s_cloud.tx_state),
           WriterCloud_Action_Name(s_cloud.tx_action),
           (unsigned long)s_cloud.tx_trace_id,
           s_cloud.online ? 1u : 0u,
           (unsigned long)s_cloud.reconnect_delay_ms,
           (unsigned long)App_Vision_UART_Get_Rx_Dropped(),
           (unsigned long)App_Vision_UART_Get_Tx_Rejected());
    s_cloud.online = false;
    s_cloud.tx_state = WRITER_CLOUD_TX_IDLE;
    s_cloud.tx_action = WRITER_CLOUD_ACTION_NONE;
    s_cloud.mqtt_packet_len = 0u;
    s_cloud.mqtt_packet_offset = 0u;
    Bsp_EspAt_Init(&s_cloud.at_parser);
    Bsp_Mqtt_Parser_Init(&s_cloud.mqtt_parser);
    s_cloud.ping_outstanding = false;
    WriterCloud_Set_Link_State(WRITER_CLOUD_LINK_RECONNECT_DELAY);
    s_cloud.deadline_ms = s_sys_tick + s_cloud.reconnect_delay_ms;
    if (s_cloud.reconnect_delay_ms < WRITER_NET_RECONNECT_MAX_MS) {
        uint32_t next = s_cloud.reconnect_delay_ms * 2u;
        s_cloud.reconnect_delay_ms =
            (next > WRITER_NET_RECONNECT_MAX_MS) ?
            WRITER_NET_RECONNECT_MAX_MS : next;
    }
}

static bool WriterCloud_Start_Mqtt_Send(uint16_t packet_len,
                                        writer_cloud_action_t action)
{
    char command[32];
    int command_len;

    if ((s_cloud.tx_state != WRITER_CLOUD_TX_IDLE) ||
        (packet_len == 0u) ||
        (packet_len > sizeof(s_cloud.mqtt_packet))) {
        elog_e("MQTT_TX", "result=start_rejected tx_state=%s "
               "packet_bytes=%u capacity=%u action=%s",
               WriterCloud_Tx_State_Name(s_cloud.tx_state),
               packet_len, (uint32_t)sizeof(s_cloud.mqtt_packet),
               WriterCloud_Action_Name(action));
        return false;
    }
    command_len = snprintf(command, sizeof(command),
                           "AT+CIPSEND=%u\r\n", packet_len);
    if ((command_len <= 0) ||
        ((uint32_t)command_len >= sizeof(command))) {
        elog_e("MQTT_TX", "fault=bad_cipsend_length packet_bytes=%u",
               packet_len);
        return false;
    }
    if (!App_Vision_UART_Try_Send((const uint8_t *)command,
                                  (uint16_t)command_len)) {
        elog_e("MQTT_TX", "uart=UART1 dir=TX cmd=AT+CIPSEND "
               "packet_bytes=%u action=%s result=tx_ring_full",
               packet_len, WriterCloud_Action_Name(action));
        return false;
    }

    s_cloud.tx_trace_id++;
    if (s_cloud.tx_trace_id == 0u) {
        s_cloud.tx_trace_id = 1u;
    }
    elog_i("ESP_AT", "uart=UART1 dir=TX cmd=AT+CIPSEND=%u "
           "tx_id=%lu action=%s",
           packet_len, (unsigned long)s_cloud.tx_trace_id,
           WriterCloud_Action_Name(action));
    elog_i("MQTT_TX", "tx_id=%lu staged action=%s packet_bytes=%u",
           (unsigned long)s_cloud.tx_trace_id,
           WriterCloud_Action_Name(action), packet_len);

    WriterCloud_Clear_Response_Flags();
    s_cloud.mqtt_packet_len = packet_len;
    s_cloud.mqtt_packet_offset = 0u;
    s_cloud.tx_action = action;
    s_cloud.tx_state = WRITER_CLOUD_TX_WAIT_PROMPT;
    s_cloud.deadline_ms = s_sys_tick + WRITER_NET_AT_TIMEOUT_MS;
    return true;
}

static bool WriterCloud_Publish(const char *topic,
                                const char *json,
                                bool retained,
                                writer_cloud_action_t action)
{
    uint16_t packet_len;
    bool started;

    if ((topic == NULL) || (json == NULL) ||
        !Bsp_Mqtt_Build_Publish(
            topic,
            (const uint8_t *)json,
            (uint16_t)strlen(json),
            retained,
            s_cloud.mqtt_packet,
            sizeof(s_cloud.mqtt_packet),
            &packet_len)) {
        elog_e("MQTT_TX", "type=PUBLISH result=encode_failed topic=%s",
               (topic != NULL) ? topic : "<null>");
        return false;
    }
    started = WriterCloud_Start_Mqtt_Send(packet_len, action);
    if (started) {
        elog_i("MQTT_TX", "tx_id=%lu type=PUBLISH topic=%s retained=%u "
               "payload=%s",
               (unsigned long)s_cloud.tx_trace_id, topic,
               retained ? 1u : 0u, json);
    }
    return started;
}

static const char *WriterCloud_State_Name(void)
{
    if (WriterRehome_Is_Active()) {
        return "homing";
    }
    if (s_cloud.needs_rehome) {
        return "needs_rehome";
    }
    if (s_cloud.job.line_active) {
        return "executing";
    }
    if (s_cloud.online) {
        return "idle";
    }
    return "connecting";
}

static bool WriterCloud_Publish_Status(writer_cloud_action_t action)
{
    char json[WRITER_CLOUD_JSON_MAX];
    int len;
    int32_t active_seq =
        s_cloud.job.line_active ? (int32_t)s_cloud.job.active_seq : -1;

    len = snprintf(
        json,
        sizeof(json),
        "{\"v\":1,\"device_id\":\"%s\",\"boot_id\":\"%s\","
        "\"state\":\"%s\",\"online\":%s,\"job_id\":\"%s\","
        "\"active_seq\":%ld,\"expected_seq\":%lu,"
        "\"completed_lines\":%lu,\"total_lines\":%lu,"
        "\"pen\":\"%s\",\"needs_rehome\":%s,"
        "\"paper\":{\"x_min\":25.0,\"x_max\":185.0,"
        "\"y_min\":45.0,\"y_max\":265.0},"
        "\"firmware\":\"" GCODE_SERIAL_BUILD_ID "\"}",
        WRITER_NET_DEVICE_ID,
        s_cloud.boot_id,
        WriterCloud_State_Name(),
        s_cloud.online ? "true" : "false",
        s_cloud.job.active ? s_cloud.job.job_id : "",
        (long)active_seq,
        (unsigned long)s_cloud.job.expected_seq,
        (unsigned long)s_cloud.job.expected_seq,
        (unsigned long)s_cloud.job.total,
        GCodeSerial_Is_Pen_Down() ? "down" : "up",
        s_cloud.needs_rehome ? "true" : "false");
    if ((len <= 0) || ((uint32_t)len >= sizeof(json))) {
        return false;
    }
    if (!WriterCloud_Publish(
            s_cloud.status_topic, json, true, action)) {
        return false;
    }
    s_cloud.last_status_ms = s_sys_tick;
    return true;
}

static bool WriterCloud_Publish_Availability(bool online,
                                             writer_cloud_action_t action)
{
    char json[160];
    int len = snprintf(
        json,
        sizeof(json),
        "{\"v\":1,\"device_id\":\"%s\",\"boot_id\":\"%s\","
        "\"online\":%s}",
        WRITER_NET_DEVICE_ID,
        s_cloud.boot_id,
        online ? "true" : "false");

    return (len > 0) && ((uint32_t)len < sizeof(json)) &&
           WriterCloud_Publish(
               s_cloud.availability_topic, json, true, action);
}

static bool WriterCloud_Publish_Ack(
    const bsp_writer_command_t *command,
    const char *phase,
    bool ok,
    const char *error,
    writer_cloud_action_t action)
{
    char json[WRITER_CLOUD_JSON_MAX];
    int len;
    const char *op;
    uint32_t ack_expected_seq;
    bool published;

    if ((command == NULL) || (phase == NULL)) {
        return false;
    }
    switch (command->operation) {
        case BSP_WRITER_OP_NONE:
            op = "unknown";
            break;
        case BSP_WRITER_OP_JOB_BEGIN:
            op = "job_begin";
            break;
        case BSP_WRITER_OP_GCODE:
            op = "gcode";
            break;
        case BSP_WRITER_OP_JOB_END:
            op = "job_end";
            break;
        case BSP_WRITER_OP_STATUS:
            op = "status";
            break;
        case BSP_WRITER_OP_STOP:
            op = "stop";
            break;
        case BSP_WRITER_OP_REHOME:
            op = "rehome";
            break;
    }
    ack_expected_seq = s_cloud.job.expected_seq;
    if ((command->operation == BSP_WRITER_OP_JOB_END) &&
        !s_cloud.job.active && s_cloud.job.has_ended &&
        (strcmp(command->job_id,
                s_cloud.job.last_ended_job_id) == 0)) {
        ack_expected_seq = s_cloud.job.last_ended_total;
    }

    if (command->operation == BSP_WRITER_OP_GCODE) {
        if (ok) {
            len = snprintf(
                json,
                sizeof(json),
                "{\"v\":1,\"device_id\":\"%s\",\"boot_id\":\"%s\","
                "\"op\":\"%s\",\"job_id\":\"%s\",\"seq\":%lu,"
                "\"phase\":\"%s\",\"ok\":true,\"expected_seq\":%lu}",
                WRITER_NET_DEVICE_ID, s_cloud.boot_id, op,
                command->job_id, (unsigned long)command->seq, phase,
                (unsigned long)ack_expected_seq);
        } else {
            len = snprintf(
                json,
                sizeof(json),
                "{\"v\":1,\"device_id\":\"%s\",\"boot_id\":\"%s\","
                "\"op\":\"%s\",\"job_id\":\"%s\",\"seq\":%lu,"
                "\"phase\":\"rejected\",\"ok\":false,"
                "\"expected_seq\":%lu,\"error\":\"%s\","
                "\"needs_rehome\":%s}",
                WRITER_NET_DEVICE_ID, s_cloud.boot_id, op,
                command->job_id, (unsigned long)command->seq,
                (unsigned long)ack_expected_seq,
                (error != NULL) ? error : "network_error",
                s_cloud.needs_rehome ? "true" : "false");
        }
    } else if ((command->operation == BSP_WRITER_OP_STOP) ||
               (command->operation == BSP_WRITER_OP_REHOME)) {
        len = snprintf(
            json,
            sizeof(json),
            "{\"v\":1,\"device_id\":\"%s\",\"boot_id\":\"%s\","
            "\"op\":\"%s\",\"request_id\":\"%s\","
            "\"phase\":\"%s\",\"ok\":%s,\"expected_seq\":%lu,"
            "\"needs_rehome\":%s%s%s%s}",
            WRITER_NET_DEVICE_ID, s_cloud.boot_id, op,
            command->request_id, phase, ok ? "true" : "false",
            (unsigned long)ack_expected_seq,
            s_cloud.needs_rehome ? "true" : "false",
            ok ? "" : ",\"error\":\"",
            ok ? "" : ((error != NULL) ? error : "network_error"),
            ok ? "" : "\"");
    } else if (command->operation == BSP_WRITER_OP_STATUS) {
        len = snprintf(
            json,
            sizeof(json),
            "{\"v\":1,\"device_id\":\"%s\",\"boot_id\":\"%s\","
            "\"op\":\"%s\",\"request_id\":\"%s\","
            "\"phase\":\"%s\",\"ok\":%s,\"expected_seq\":%lu%s%s%s}",
            WRITER_NET_DEVICE_ID, s_cloud.boot_id, op,
            command->request_id, phase, ok ? "true" : "false",
            (unsigned long)ack_expected_seq,
            ok ? "" : ",\"error\":\"",
            ok ? "" : ((error != NULL) ? error : "network_error"),
            ok ? "" : "\"");
    } else {
        len = snprintf(
            json,
            sizeof(json),
            "{\"v\":1,\"device_id\":\"%s\",\"boot_id\":\"%s\","
            "\"op\":\"%s\",\"job_id\":\"%s\","
            "\"phase\":\"%s\",\"ok\":%s,\"expected_seq\":%lu%s%s%s}",
            WRITER_NET_DEVICE_ID, s_cloud.boot_id, op,
            command->job_id, phase, ok ? "true" : "false",
            (unsigned long)ack_expected_seq,
            ok ? "" : ",\"error\":\"",
            ok ? "" : ((error != NULL) ? error : "network_error"),
            ok ? "" : "\"");
    }

    if ((len <= 0) || ((uint32_t)len >= sizeof(json))) {
        elog_e("ACK_TX", "op=%s phase=%s result=json_overflow",
               op, phase);
        return false;
    }
    published = WriterCloud_Publish(
        s_cloud.ack_topic, json, false, action);
    if (published) {
        elog_i("ACK_TX", "tx_id=%lu op=%s job_id=%s request_id=%s "
               "seq=%lu phase=%s ok=%u expected_seq=%lu error=%s "
               "result=queued",
               (unsigned long)s_cloud.tx_trace_id, op,
               command->job_id, command->request_id,
               (unsigned long)command->seq, phase, ok ? 1u : 0u,
               (unsigned long)ack_expected_seq,
               (error != NULL) ? error : "none");
    } else {
        elog_e("ACK_TX", "op=%s job_id=%s request_id=%s seq=%lu "
               "phase=%s result=queue_failed",
               op, command->job_id, command->request_id,
               (unsigned long)command->seq, phase);
    }
    return published;
}

static bool WriterCloud_Publish_Parse_Rejection(
    const bsp_writer_command_t *command,
    bsp_writer_parse_result_t result)
{
    char json[WRITER_CLOUD_JSON_MAX];
    int len;
    bool published;

    if ((command != NULL) &&
        (command->operation != BSP_WRITER_OP_NONE)) {
        return WriterCloud_Publish_Ack(
            command, "rejected", false,
            Bsp_Writer_Parse_Result_Name(result),
            WRITER_CLOUD_ACTION_NONE);
    }
    len = snprintf(
        json,
        sizeof(json),
        "{\"v\":1,\"device_id\":\"%s\",\"boot_id\":\"%s\","
        "\"phase\":\"rejected\",\"ok\":false,\"expected_seq\":%lu,"
        "\"error\":\"%s\",\"needs_rehome\":%s}",
        WRITER_NET_DEVICE_ID,
        s_cloud.boot_id,
        (unsigned long)s_cloud.job.expected_seq,
        Bsp_Writer_Parse_Result_Name(result),
        s_cloud.needs_rehome ? "true" : "false");
    if ((len <= 0) || ((uint32_t)len >= sizeof(json))) {
        elog_e("ACK_TX", "op=unknown phase=rejected "
               "error=%s result=json_overflow",
               Bsp_Writer_Parse_Result_Name(result));
        return false;
    }
    published = WriterCloud_Publish(
        s_cloud.ack_topic, json, false,
        WRITER_CLOUD_ACTION_NONE);
    if (published) {
        elog_i("ACK_TX", "tx_id=%lu op=unknown phase=rejected "
               "error=%s result=queued",
               (unsigned long)s_cloud.tx_trace_id,
               Bsp_Writer_Parse_Result_Name(result));
    } else {
        elog_e("ACK_TX", "op=unknown phase=rejected error=%s "
               "result=queue_failed",
               Bsp_Writer_Parse_Result_Name(result));
    }
    return published;
}

static bool WriterCloud_Topic_Equals(const uint8_t *topic,
                                     uint16_t topic_len,
                                     const char *expected)
{
    size_t expected_len = strlen(expected);

    return (expected_len == topic_len) &&
           (memcmp(topic, expected, topic_len) == 0);
}

static const char *WriterCloud_Job_Error(
    bsp_writer_job_result_t result)
{
    switch (result) {
        case BSP_WRITER_JOB_ACCEPTED:
        case BSP_WRITER_JOB_DUPLICATE_BEGIN:
        case BSP_WRITER_JOB_DUPLICATE_ACTIVE:
        case BSP_WRITER_JOB_DUPLICATE_COMPLETED:
        case BSP_WRITER_JOB_DUPLICATE_END:
            return "bad_device_state";
        case BSP_WRITER_JOB_BUSY:
            return "busy";
        case BSP_WRITER_JOB_BAD_ID:
            return "bad_job_id";
        case BSP_WRITER_JOB_OUT_OF_ORDER:
            return "out_of_order";
        case BSP_WRITER_JOB_TOTAL_MISMATCH:
            return "job_total_mismatch";
        case BSP_WRITER_JOB_CRC_MISMATCH:
            return "crc_mismatch";
        case BSP_WRITER_JOB_NO_ACTIVE:
            return "bad_device_state";
    }
}

static const char *WriterCloud_Map_Gcode_Error(const char *detail)
{
    if (detail == NULL) {
        return "motion_rejected";
    }
    if (strcmp(detail, "runtime_limit_active") == 0) {
        return "runtime_limit_active";
    }
    if ((strcmp(detail, "parse_error") == 0) ||
        (strcmp(detail, "empty_command") == 0) ||
        (strcmp(detail, "bad_feed") == 0) ||
        (strcmp(detail, "bad_power") == 0) ||
        (strcmp(detail, "bad_dwell") == 0)) {
        return "parse_error";
    }
    return "motion_rejected";
}

static void WriterCloud_Handle_Command(const uint8_t *payload,
                                       uint16_t payload_len)
{
    bsp_writer_command_t command;
    bsp_writer_parse_result_t parse_result;
    bsp_writer_job_result_t job_result;

    parse_result =
        Bsp_Writer_Parse_Command(payload, payload_len, &command);
    if (parse_result != BSP_WRITER_PARSE_OK) {
        elog_w("CLOUD", "command rejected before op parse: %s",
               Bsp_Writer_Parse_Result_Name(parse_result));
        (void)WriterCloud_Publish_Parse_Rejection(
            &command, parse_result);
        return;
    }

    if (command.operation == BSP_WRITER_OP_GCODE) {
        elog_i("CMD_RX", "op=gcode job_id=%s seq=%lu line=%s",
               command.job_id, (unsigned long)command.seq,
               command.line);
    } else if ((command.operation == BSP_WRITER_OP_JOB_BEGIN) ||
               (command.operation == BSP_WRITER_OP_JOB_END)) {
        elog_i("CMD_RX", "op=%s job_id=%s total=%lu crc32=%08lX",
               WriterCloud_Operation_Name(command.operation),
               command.job_id, (unsigned long)command.total,
               (unsigned long)command.crc32);
    } else {
        elog_i("CMD_RX", "op=%s request_id=%s",
               WriterCloud_Operation_Name(command.operation),
               command.request_id);
    }

    if (command.operation == BSP_WRITER_OP_STOP) {
        WriterCloud_Safe_Abort("stop_command");
        s_cloud.tx_action = WRITER_CLOUD_ACTION_NONE;
        memcpy(s_cloud.stop_request_id, command.request_id,
               strlen(command.request_id) + 1u);
        s_cloud.stop_ack_pending = true;
        return;
    }
    if (s_cloud.tx_state != WRITER_CLOUD_TX_IDLE) {
        elog_w("CMD_RX", "op=%s result=ignored reason=tx_busy "
               "retry_required=1 tx_id=%lu tx_state=%s",
               WriterCloud_Operation_Name(command.operation),
               (unsigned long)s_cloud.tx_trace_id,
               WriterCloud_Tx_State_Name(s_cloud.tx_state));
        return;
    }
    if (command.operation == BSP_WRITER_OP_STATUS) {
        (void)WriterCloud_Publish_Ack(
            &command, "completed", true, NULL,
            WRITER_CLOUD_ACTION_SEND_STATUS);
        return;
    }
    if (command.operation == BSP_WRITER_OP_REHOME) {
        if (WriterRehome_Is_Active()) {
            if (strcmp(command.request_id, s_cloud.rehome_request_id) == 0) {
                (void)WriterCloud_Publish_Ack(
                    &command, "accepted", true, NULL,
                    WRITER_CLOUD_ACTION_NONE);
            } else {
                (void)WriterCloud_Publish_Ack(
                    &command, "rejected", false, "busy",
                    WRITER_CLOUD_ACTION_NONE);
            }
        } else if (s_cloud.rehome_has_completed &&
                   (strcmp(command.request_id,
                           s_cloud.rehome_completed_request_id) == 0)) {
            (void)WriterCloud_Publish_Ack(
                &command, "completed", true, NULL,
                WRITER_CLOUD_ACTION_NONE);
        } else if (!s_cloud.needs_rehome) {
            (void)WriterCloud_Publish_Ack(
                &command, "rejected", false, "bad_device_state",
                WRITER_CLOUD_ACTION_NONE);
        } else if (s_cloud.job.active || s_cloud.job.line_active ||
                   !GCodeSerial_Is_Idle() || !WriterRehome_Start()) {
            (void)WriterCloud_Publish_Ack(
                &command, "rejected", false, "busy",
                WRITER_CLOUD_ACTION_NONE);
        } else {
            memcpy(s_cloud.rehome_request_id, command.request_id,
                   strlen(command.request_id) + 1u);
            s_cloud.rehome_has_completed = false;
            if (WriterCloud_Publish_Ack(
                    &command, "accepted", true, NULL,
                    WRITER_CLOUD_ACTION_NONE)) {
                s_cloud.rehome_completion_pending = true;
            } else {
                WriterRehome_Abort();
                s_cloud.rehome_request_id[0] = '\0';
            }
        }
        return;
    }
    if (command.operation == BSP_WRITER_OP_JOB_BEGIN) {
        if (s_cloud.needs_rehome) {
            (void)WriterCloud_Publish_Ack(
                &command, "rejected", false, "needs_rehome",
                WRITER_CLOUD_ACTION_NONE);
            return;
        }
        job_result = Bsp_WriterJob_Begin(
            &s_cloud.job, command.job_id,
            command.total, command.crc32);
        if ((job_result == BSP_WRITER_JOB_ACCEPTED) ||
            (job_result == BSP_WRITER_JOB_DUPLICATE_BEGIN)) {
            (void)WriterCloud_Publish_Ack(
                &command, "accepted", true, NULL,
                WRITER_CLOUD_ACTION_NONE);
        } else {
            (void)WriterCloud_Publish_Ack(
                &command, "rejected", false,
                WriterCloud_Job_Error(job_result),
                WRITER_CLOUD_ACTION_NONE);
        }
        return;
    }
    if (command.operation == BSP_WRITER_OP_GCODE) {
        job_result = Bsp_WriterJob_Accept_Line(
            &s_cloud.job, command.job_id, command.seq);
        if (job_result == BSP_WRITER_JOB_ACCEPTED) {
            memcpy(s_cloud.pending_line, command.line,
                   strlen(command.line) + 1u);
            (void)WriterCloud_Publish_Ack(
                &command, "accepted", true, NULL,
                WRITER_CLOUD_ACTION_EXECUTE_LINE);
        } else if (job_result == BSP_WRITER_JOB_DUPLICATE_ACTIVE) {
            (void)WriterCloud_Publish_Ack(
                &command, "accepted", true, NULL,
                Bsp_WriterJob_Line_Needs_Start(&s_cloud.job) ?
                    WRITER_CLOUD_ACTION_EXECUTE_LINE :
                    WRITER_CLOUD_ACTION_NONE);
        } else if (job_result == BSP_WRITER_JOB_DUPLICATE_COMPLETED) {
            (void)WriterCloud_Publish_Ack(
                &command, "completed", true, NULL,
                WRITER_CLOUD_ACTION_NONE);
        } else {
            (void)WriterCloud_Publish_Ack(
                &command, "rejected", false,
                WriterCloud_Job_Error(job_result),
                WRITER_CLOUD_ACTION_NONE);
        }
        return;
    }
    if (command.operation == BSP_WRITER_OP_JOB_END) {
        job_result = Bsp_WriterJob_End(
            &s_cloud.job, command.job_id,
            command.total, command.crc32);
        if (job_result == BSP_WRITER_JOB_ACCEPTED) {
            (void)WriterCloud_Publish_Ack(
                &command, "completed", true, NULL,
                WRITER_CLOUD_ACTION_FINISH_JOB);
        } else if (job_result == BSP_WRITER_JOB_DUPLICATE_END) {
            (void)WriterCloud_Publish_Ack(
                &command, "completed", true, NULL,
                WRITER_CLOUD_ACTION_NONE);
        } else {
            (void)WriterCloud_Publish_Ack(
                &command, "rejected", false,
                WriterCloud_Job_Error(job_result),
                WRITER_CLOUD_ACTION_NONE);
        }
    }
}

static void WriterCloud_Handle_Mqtt_Packet(
    const bsp_mqtt_packet_t *packet)
{
    const uint8_t *topic;
    const uint8_t *payload;
    uint16_t topic_len;
    uint16_t payload_len;
    uint8_t qos;

    s_cloud.ping_outstanding = false;
    s_cloud.last_activity_ms = s_sys_tick;
    if (packet->type == 2u) {
        if (Bsp_Mqtt_Is_ConnAck_Accepted(packet)) {
            elog_i("MQTT_RX", "type=CONNACK result=accepted");
            s_cloud.connack = true;
        } else {
            uint32_t return_code =
                (packet->body_len >= 2u) ? packet->body[1] : 0xFFu;

            elog_e("MQTT_RX", "type=CONNACK result=rejected code=%lu",
                   (unsigned long)return_code);
            WriterCloud_Reconnect("connack_rejected");
        }
        return;
    }
    if (packet->type == 9u) {
        if (Bsp_Mqtt_Is_SubAck(packet, WRITER_CLOUD_SUB_PACKET_ID)) {
            elog_i("MQTT_RX", "type=SUBACK packet_id=%u result=accepted",
                   WRITER_CLOUD_SUB_PACKET_ID);
            s_cloud.suback = true;
        } else {
            uint32_t packet_id = (packet->body_len >= 2u) ?
                (((uint32_t)packet->body[0] << 8) | packet->body[1]) :
                0xFFFFFFFFu;
            uint32_t return_code =
                (packet->body_len >= 3u) ? packet->body[2] : 0xFFu;

            elog_e("MQTT_RX", "type=SUBACK result=rejected "
                   "packet_id=%lu code=%lu",
                   (unsigned long)packet_id,
                   (unsigned long)return_code);
            WriterCloud_Reconnect("suback_rejected");
        }
        return;
    }
    if (packet->type == 13u) {
        elog_i("MQTT_RX", "type=PINGRESP");
        return;
    }
    if (!Bsp_Mqtt_Decode_Publish(
            packet, &topic, &topic_len,
            &payload, &payload_len, &qos)) {
        elog_d("MQTT_RX", "type=%u flags=%u body_bytes=%u ignored=1",
               packet->type, packet->flags, packet->body_len);
        return;
    }
    elog_i("MQTT_RX", "type=PUBLISH topic=%.*s qos=%u payload_bytes=%u",
           (int)topic_len, (const char *)topic, qos, payload_len);
    if ((qos == 0u) &&
        WriterCloud_Topic_Equals(
            topic, topic_len, s_cloud.command_topic)) {
        WriterCloud_Handle_Command(payload, payload_len);
    } else {
        elog_w("MQTT_RX", "publish_ignored reason=%s topic=%.*s qos=%u",
               (qos == 0u) ? "unexpected_topic" : "unsupported_qos",
               (int)topic_len, (const char *)topic, qos);
    }
}

static void WriterCloud_Handle_At_Line(const char *line)
{
    if (line == NULL) {
        return;
    }
    if (strstr(line, "CWJAP") != NULL) {
        elog_i("ESP_AT", "uart=UART1 dir=RX step=%s "
               "line=<credentials-redacted>",
               WriterCloud_Link_State_Name(s_cloud.link_state));
    } else {
        elog_i("ESP_AT", "uart=UART1 dir=RX step=%s line=%s",
               WriterCloud_Link_State_Name(s_cloud.link_state), line);
    }
    if (strcmp(line, "OK") == 0) {
        s_cloud.at_ok = true;
    } else if ((strcmp(line, "ERROR") == 0) ||
               (strcmp(line, "FAIL") == 0) ||
               (strstr(line, "busy ") != NULL)) {
        s_cloud.at_error = true;
    } else if (strcmp(line, "SEND OK") == 0) {
        s_cloud.send_ok = true;
    } else if ((strstr(line, "ALREADY CONNECTED") != NULL) ||
               (strcmp(line, "CONNECT") == 0)) {
        s_cloud.at_ok = true;
    } else if (strstr(line, "WIFI DISCONNECT") != NULL) {
        /*
         * ESP-AT may emit this transient URC while AT+CWJAP is joining.
         * Let the command's final OK/error/timeout own that state change.
         */
        if (s_cloud.link_state != WRITER_CLOUD_LINK_JOIN_WIFI) {
            WriterCloud_Reconnect("esp_link_closed");
        }
    } else if (strcmp(line, "CLOSED") == 0) {
        WriterCloud_Reconnect("esp_link_closed");
    }
}

static void WriterCloud_Process_Rx(void)
{
    uint8_t data[WRITER_NET_UPDATE_RX_BUDGET];
    uint16_t count = App_Vision_UART_Read(data, sizeof(data));
    uint16_t index;

    for (index = 0u; index < count; index++) {
        bsp_esp_at_event_t at_event;

        Bsp_EspAt_Feed(&s_cloud.at_parser, data[index], &at_event);
        if (at_event.type == BSP_ESP_AT_EVENT_LINE) {
            WriterCloud_Handle_At_Line(at_event.line);
        } else if (at_event.type == BSP_ESP_AT_EVENT_PROMPT) {
            elog_i("ESP_AT", "uart=UART1 dir=RX tx_id=%lu token=PROMPT",
                   (unsigned long)s_cloud.tx_trace_id);
            s_cloud.prompt = true;
        } else if (at_event.type == BSP_ESP_AT_EVENT_IPD_BEGIN) {
            elog_d("MQTT_RX", "uart=UART1 transport=ESP_IPD "
                   "frame_bytes=%lu",
                   (unsigned long)at_event.ipd_len);
        } else if (at_event.type == BSP_ESP_AT_EVENT_IPD_DATA) {
            bsp_mqtt_event_t mqtt_event;

            s_cloud.last_activity_ms = s_sys_tick;
            Bsp_Mqtt_Parser_Feed(
                &s_cloud.mqtt_parser, at_event.data, &mqtt_event);
            if (mqtt_event.type == BSP_MQTT_EVENT_PACKET) {
                WriterCloud_Handle_Mqtt_Packet(&mqtt_event.packet);
            } else if (mqtt_event.type == BSP_MQTT_EVENT_ERROR) {
                elog_w("CLOUD", "oversize or malformed MQTT packet");
                WriterCloud_Reconnect("mqtt_parse_error");
                break;
            }
        } else if (at_event.type == BSP_ESP_AT_EVENT_OVERFLOW) {
            elog_w("CLOUD", "ESP-AT response line overflow");
        }
    }
}

static void WriterCloud_Gcode_Result(bool ok,
                                     const char *detail,
                                     void *context)
{
    (void)context;
    if (s_cloud.suppress_gcode_result ||
        !s_cloud.job.line_active ||
        s_cloud.gcode_result_pending) {
        return;
    }
    s_cloud.gcode_result_ok = ok;
    s_cloud.gcode_result_error =
        ok ? NULL : WriterCloud_Map_Gcode_Error(detail);
    s_cloud.gcode_result_pending = true;
    elog_i("GCODE_ACK", "job_id=%s seq=%lu executor_result=%s detail=%s",
           s_cloud.job.job_id, (unsigned long)s_cloud.job.active_seq,
           ok ? "ok" : "error", (detail != NULL) ? detail : "none");
}

static void WriterCloud_Process_Gcode_Result(void)
{
    bsp_writer_command_t command;

    if (!s_cloud.online ||
        !s_cloud.gcode_result_pending ||
        (s_cloud.tx_state != WRITER_CLOUD_TX_IDLE)) {
        return;
    }
    s_cloud.gcode_result_pending = false;
    memset(&command, 0, sizeof(command));
    command.operation = BSP_WRITER_OP_GCODE;
    memcpy(command.job_id, s_cloud.job.job_id,
           strlen(s_cloud.job.job_id) + 1u);
    command.seq = s_cloud.job.active_seq;

    if (s_cloud.gcode_result_ok) {
        if (!Bsp_WriterJob_Complete_Line(
                &s_cloud.job,
                (const uint8_t *)s_cloud.pending_line,
                (uint16_t)strlen(s_cloud.pending_line))) {
            WriterCloud_Safe_Abort("complete_line_state_error");
            (void)WriterCloud_Publish_Ack(
                &command, "rejected", false, "bad_device_state",
                WRITER_CLOUD_ACTION_SEND_STATUS);
            return;
        }
        (void)WriterCloud_Publish_Ack(
            &command, "completed", true, NULL,
            WRITER_CLOUD_ACTION_NONE);
    } else {
        s_cloud.needs_rehome = true;
        (void)WriterCloud_Publish_Ack(
            &command, "rejected", false,
            s_cloud.gcode_result_error,
            WRITER_CLOUD_ACTION_CLEAR_JOB);
    }
}

static void WriterCloud_Process_Stop_Ack(void)
{
    bsp_writer_command_t command;

    if (!s_cloud.online ||
        !s_cloud.stop_ack_pending ||
        (s_cloud.tx_state != WRITER_CLOUD_TX_IDLE)) {
        return;
    }
    memset(&command, 0, sizeof(command));
    command.operation = BSP_WRITER_OP_STOP;
    memcpy(command.request_id, s_cloud.stop_request_id,
           strlen(s_cloud.stop_request_id) + 1u);
    if (WriterCloud_Publish_Ack(
            &command, "completed", true, NULL,
            WRITER_CLOUD_ACTION_SEND_STATUS)) {
        s_cloud.stop_ack_pending = false;
    }
}

static void WriterCloud_Process_Rehome_Result(void)
{
    bsp_writer_command_t command;

    if (!s_cloud.online ||
        !s_cloud.rehome_completion_pending ||
        (s_cloud.tx_state != WRITER_CLOUD_TX_IDLE) ||
        (!WriterRehome_Is_Succeeded() && !WriterRehome_Is_Failed())) {
        return;
    }

    memset(&command, 0, sizeof(command));
    command.operation = BSP_WRITER_OP_REHOME;
    memcpy(command.request_id, s_cloud.rehome_request_id,
           strlen(s_cloud.rehome_request_id) + 1u);
    if (WriterRehome_Is_Succeeded()) {
        /* The completed ACK is the only event that unlocks new jobs. */
        s_cloud.needs_rehome = false;
        if (WriterCloud_Publish_Ack(
                &command, "completed", true, NULL,
                WRITER_CLOUD_ACTION_SEND_STATUS)) {
            s_cloud.rehome_completion_pending = false;
            s_cloud.rehome_has_completed = true;
            memcpy(s_cloud.rehome_completed_request_id,
                   s_cloud.rehome_request_id,
                   strlen(s_cloud.rehome_request_id) + 1u);
        } else {
            s_cloud.needs_rehome = true;
        }
    } else if (WriterCloud_Publish_Ack(
                   &command, "rejected", false, "motion_rejected",
                   WRITER_CLOUD_ACTION_SEND_STATUS)) {
        s_cloud.needs_rehome = true;
        s_cloud.rehome_completion_pending = false;
    }
}

static void WriterCloud_Complete_Tx_Action(void)
{
    writer_cloud_action_t action = s_cloud.tx_action;

    elog_i("MQTT_TX", "tx_id=%lu result=SEND_OK action=%s",
           (unsigned long)s_cloud.tx_trace_id,
           WriterCloud_Action_Name(action));
    s_cloud.tx_action = WRITER_CLOUD_ACTION_NONE;
    s_cloud.tx_state = WRITER_CLOUD_TX_IDLE;

    switch (action) {
        case WRITER_CLOUD_ACTION_CONNECT_SENT:
            WriterCloud_Set_Link_State(
                WRITER_CLOUD_LINK_WAIT_CONNACK);
            s_cloud.deadline_ms =
                s_sys_tick + WRITER_NET_MQTT_TIMEOUT_MS;
            break;
        case WRITER_CLOUD_ACTION_SUBSCRIBE_SENT:
            WriterCloud_Set_Link_State(
                WRITER_CLOUD_LINK_WAIT_SUBACK);
            s_cloud.deadline_ms =
                s_sys_tick + WRITER_NET_MQTT_TIMEOUT_MS;
            break;
        case WRITER_CLOUD_ACTION_AVAILABILITY_SENT:
            WriterCloud_Set_Link_State(
                WRITER_CLOUD_LINK_SEND_INITIAL_STATUS);
            break;
        case WRITER_CLOUD_ACTION_EXECUTE_LINE:
            if (!Bsp_WriterJob_Mark_Line_Started(&s_cloud.job)) {
                WriterCloud_Safe_Abort("line_start_state_error");
            } else {
                elog_i("GCODE_ACK", "job_id=%s seq=%lu phase=started",
                       s_cloud.job.job_id,
                       (unsigned long)s_cloud.job.active_seq);
                (void)GCodeSerial_ProcessFrame(
                    (const uint8_t *)s_cloud.pending_line,
                    (uint16_t)strlen(s_cloud.pending_line));
            }
            break;
        case WRITER_CLOUD_ACTION_CLEAR_JOB:
            Bsp_WriterJob_Abort(&s_cloud.job);
            s_cloud.pending_line[0] = '\0';
            (void)WriterCloud_Publish_Status(
                WRITER_CLOUD_ACTION_STATUS_SENT);
            break;
        case WRITER_CLOUD_ACTION_FINISH_JOB:
            if (!Bsp_WriterJob_Finish(&s_cloud.job)) {
                WriterCloud_Safe_Abort("finish_job_state_error");
            }
            s_cloud.pending_line[0] = '\0';
            (void)WriterCloud_Publish_Status(
                WRITER_CLOUD_ACTION_STATUS_SENT);
            break;
        case WRITER_CLOUD_ACTION_SEND_STATUS:
            (void)WriterCloud_Publish_Status(
                WRITER_CLOUD_ACTION_STATUS_SENT);
            break;
        case WRITER_CLOUD_ACTION_PING_SENT:
            s_cloud.ping_outstanding = true;
            s_cloud.deadline_ms =
                s_sys_tick + WRITER_NET_MQTT_TIMEOUT_MS;
            break;
        case WRITER_CLOUD_ACTION_STATUS_SENT:
        case WRITER_CLOUD_ACTION_NONE:
        default:
            break;
    }
}

static void WriterCloud_Service_Mqtt_Tx(void)
{
    if (s_cloud.tx_state == WRITER_CLOUD_TX_IDLE) {
        return;
    }
    if (WriterCloud_Time_Reached(s_cloud.deadline_ms) ||
        s_cloud.at_error) {
        const char *expected =
            (s_cloud.tx_state == WRITER_CLOUD_TX_WAIT_PROMPT) ?
                "PROMPT" :
            (s_cloud.tx_state == WRITER_CLOUD_TX_WAIT_SEND_OK) ?
                "SEND_OK" : "UART_TX_DRAIN";
        const char *result = s_cloud.at_error ? "AT_ERROR" : "TIMEOUT";

        elog_e("MQTT_TX", "tx_id=%lu action=%s expected=%s result=%s "
               "offset=%u packet_bytes=%u",
               (unsigned long)s_cloud.tx_trace_id,
               WriterCloud_Action_Name(s_cloud.tx_action),
               expected, result, s_cloud.mqtt_packet_offset,
               s_cloud.mqtt_packet_len);
        WriterCloud_Reconnect(
            s_cloud.at_error ? "mqtt_tx_at_error" : "mqtt_tx_timeout");
        return;
    }
    if ((s_cloud.tx_state == WRITER_CLOUD_TX_WAIT_PROMPT) &&
        s_cloud.prompt) {
        s_cloud.prompt = false;
        s_cloud.tx_state = WRITER_CLOUD_TX_SEND_DATA;
        s_cloud.deadline_ms =
            s_sys_tick + WRITER_NET_MQTT_TIMEOUT_MS;
        return;
    }
    if (s_cloud.tx_state == WRITER_CLOUD_TX_SEND_DATA) {
        uint16_t remaining =
            (uint16_t)(s_cloud.mqtt_packet_len -
                       s_cloud.mqtt_packet_offset);
        uint16_t chunk = (remaining > 64u) ? 64u : remaining;

        if ((chunk > 0u) &&
            App_Vision_UART_Try_Send(
                &s_cloud.mqtt_packet[s_cloud.mqtt_packet_offset],
                chunk)) {
            elog_d("UART_IO", "uart=UART1 dir=TX mode=cloud tx_id=%lu "
                   "type=MQTT offset=%u chunk=%u packet_bytes=%u",
                   (unsigned long)s_cloud.tx_trace_id,
                   s_cloud.mqtt_packet_offset, chunk,
                   s_cloud.mqtt_packet_len);
            s_cloud.mqtt_packet_offset =
                (uint16_t)(s_cloud.mqtt_packet_offset + chunk);
        }
        if (s_cloud.mqtt_packet_offset == s_cloud.mqtt_packet_len) {
            s_cloud.tx_state = WRITER_CLOUD_TX_WAIT_SEND_OK;
            elog_i("MQTT_TX", "tx_id=%lu uart_bytes_queued=%u "
                   "expected=SEND_OK",
                   (unsigned long)s_cloud.tx_trace_id,
                   s_cloud.mqtt_packet_len);
        }
        return;
    }
    if ((s_cloud.tx_state == WRITER_CLOUD_TX_WAIT_SEND_OK) &&
        s_cloud.send_ok) {
        s_cloud.send_ok = false;
        WriterCloud_Complete_Tx_Action();
    }
}

static bool WriterCloud_Run_At_Step(const char *command,
                                    uint32_t timeout_ms,
                                    writer_cloud_link_state_t next,
                                    bool allow_error)
{
    if (!s_cloud.step_started) {
        (void)WriterCloud_Send_At(command, timeout_ms);
        return false;
    }
    if (s_cloud.at_ok || (allow_error && s_cloud.at_error)) {
        elog_i("ESP_AT", "step=%s expected=OK result=%s",
               WriterCloud_Link_State_Name(s_cloud.link_state),
               s_cloud.at_ok ? "OK" : "allowed_error");
        WriterCloud_Set_Link_State(next);
        return true;
    }
    if ((!allow_error && s_cloud.at_error) ||
        WriterCloud_Time_Reached(s_cloud.deadline_ms)) {
        elog_e("ESP_AT", "step=%s expected=OK result=%s",
               WriterCloud_Link_State_Name(s_cloud.link_state),
               s_cloud.at_error ? "AT_ERROR" : "TIMEOUT");
        WriterCloud_Reconnect(
            s_cloud.at_error ? "at_command_error" : "at_command_timeout");
    }
    return false;
}

static void WriterCloud_Run_Link_State(void)
{
    char command[WRITER_CLOUD_AT_COMMAND_MAX];
    char lwt[160];
    bsp_mqtt_connect_options_t options;
    uint16_t packet_len;
    int len;

    switch (s_cloud.link_state) {
        case WRITER_CLOUD_LINK_RECONNECT_DELAY:
            if (WriterCloud_Time_Reached(s_cloud.deadline_ms)) {
                WriterCloud_Set_Link_State(WRITER_CLOUD_LINK_AT);
            }
            break;
        case WRITER_CLOUD_LINK_AT:
            (void)WriterCloud_Run_At_Step(
                "AT\r\n", WRITER_NET_AT_TIMEOUT_MS,
                WRITER_CLOUD_LINK_ECHO_OFF, false);
            break;
        case WRITER_CLOUD_LINK_ECHO_OFF:
            (void)WriterCloud_Run_At_Step(
                "ATE0\r\n", WRITER_NET_AT_TIMEOUT_MS,
                WRITER_CLOUD_LINK_STA_MODE, false);
            break;
        case WRITER_CLOUD_LINK_STA_MODE:
            (void)WriterCloud_Run_At_Step(
                "AT+CWMODE=1\r\n", WRITER_NET_AT_TIMEOUT_MS,
                WRITER_CLOUD_LINK_DHCP, false);
            break;
        case WRITER_CLOUD_LINK_DHCP:
            (void)WriterCloud_Run_At_Step(
                "AT+CWDHCP=1,1\r\n", WRITER_NET_AT_TIMEOUT_MS,
                WRITER_CLOUD_LINK_JOIN_WIFI, false);
            break;
        case WRITER_CLOUD_LINK_JOIN_WIFI:
            len = snprintf(command, sizeof(command),
                           "AT+CWJAP=\"%s\",\"%s\"\r\n",
                           WRITER_NET_WIFI_SSID,
                           WRITER_NET_WIFI_PASSWORD);
            if ((len <= 0) || ((uint32_t)len >= sizeof(command))) {
                WriterCloud_Set_Link_State(
                    WRITER_CLOUD_LINK_CONFIG_ERROR);
                break;
            }
            (void)WriterCloud_Run_At_Step(
                command, WRITER_NET_WIFI_TIMEOUT_MS,
                WRITER_CLOUD_LINK_CLOSE_OLD, false);
            break;
        case WRITER_CLOUD_LINK_CLOSE_OLD:
            (void)WriterCloud_Run_At_Step(
                "AT+CIPCLOSE\r\n", WRITER_NET_AT_TIMEOUT_MS,
                WRITER_CLOUD_LINK_SINGLE_CONNECTION, true);
            break;
        case WRITER_CLOUD_LINK_SINGLE_CONNECTION:
            (void)WriterCloud_Run_At_Step(
                "AT+CIPMUX=0\r\n", WRITER_NET_AT_TIMEOUT_MS,
                WRITER_CLOUD_LINK_NORMAL_MODE, false);
            break;
        case WRITER_CLOUD_LINK_NORMAL_MODE:
            (void)WriterCloud_Run_At_Step(
                "AT+CIPMODE=0\r\n", WRITER_NET_AT_TIMEOUT_MS,
                WRITER_CLOUD_LINK_TCP, false);
            break;
        case WRITER_CLOUD_LINK_TCP:
            len = snprintf(
                command, sizeof(command),
                "AT+CIPSTART=\"%s\",\"%s\",%u\r\n",
                WriterCloud_Transport_Name(),
                WRITER_NET_BROKER_HOST,
                WRITER_NET_BROKER_PORT);
            if ((len <= 0) || ((uint32_t)len >= sizeof(command))) {
                WriterCloud_Set_Link_State(
                    WRITER_CLOUD_LINK_CONFIG_ERROR);
                break;
            }
            (void)WriterCloud_Run_At_Step(
                command, WRITER_NET_TCP_TIMEOUT_MS,
                WRITER_CLOUD_LINK_SEND_CONNECT, false);
            break;
        case WRITER_CLOUD_LINK_SEND_CONNECT:
            len = snprintf(
                lwt, sizeof(lwt),
                "{\"v\":1,\"device_id\":\"%s\",\"boot_id\":\"%s\","
                "\"online\":false}",
                WRITER_NET_DEVICE_ID, s_cloud.boot_id);
            if ((len <= 0) || ((uint32_t)len >= sizeof(lwt))) {
                WriterCloud_Reconnect("mqtt_lwt_encode_failed");
                break;
            }
            options.client_id = WRITER_NET_MQTT_CLIENT_ID;
            options.username = WRITER_NET_MQTT_USERNAME;
            options.password = WRITER_NET_MQTT_PASSWORD;
            options.will_topic = s_cloud.availability_topic;
            options.will_payload = lwt;
            options.keepalive_s = WRITER_NET_KEEPALIVE_S;
            elog_i("MQTT_TX", "type=CONNECT client_id=%s username=%s "
                   "password=<redacted> keepalive_s=%u "
                   "will_topic=%s will_retain=1",
                   WRITER_NET_MQTT_CLIENT_ID,
                   WRITER_NET_MQTT_USERNAME,
                   WRITER_NET_KEEPALIVE_S,
                   s_cloud.availability_topic);
            if (!Bsp_Mqtt_Build_Connect(
                    &options,
                    s_cloud.mqtt_packet,
                    sizeof(s_cloud.mqtt_packet),
                    &packet_len) ||
                !WriterCloud_Start_Mqtt_Send(
                    packet_len,
                    WRITER_CLOUD_ACTION_CONNECT_SENT)) {
                WriterCloud_Reconnect("mqtt_connect_send_failed");
            }
            break;
        case WRITER_CLOUD_LINK_WAIT_CONNACK:
            if (s_cloud.connack) {
                s_cloud.connack = false;
                elog_i("MQTT_RX", "expected=CONNACK result=received");
                WriterCloud_Set_Link_State(
                    WRITER_CLOUD_LINK_SEND_SUBSCRIBE);
            } else if (WriterCloud_Time_Reached(s_cloud.deadline_ms)) {
                elog_e("MQTT_RX", "expected=CONNACK result=TIMEOUT");
                WriterCloud_Reconnect("connack_timeout");
            }
            break;
        case WRITER_CLOUD_LINK_SEND_SUBSCRIBE:
            elog_i("MQTT_TX", "type=SUBSCRIBE packet_id=%u topic=%s qos=0",
                   WRITER_CLOUD_SUB_PACKET_ID, s_cloud.command_topic);
            if (!Bsp_Mqtt_Build_Subscribe(
                    WRITER_CLOUD_SUB_PACKET_ID,
                    s_cloud.command_topic,
                    s_cloud.mqtt_packet,
                    sizeof(s_cloud.mqtt_packet),
                    &packet_len) ||
                !WriterCloud_Start_Mqtt_Send(
                    packet_len,
                    WRITER_CLOUD_ACTION_SUBSCRIBE_SENT)) {
                WriterCloud_Reconnect("mqtt_subscribe_send_failed");
            }
            break;
        case WRITER_CLOUD_LINK_WAIT_SUBACK:
            if (s_cloud.suback) {
                s_cloud.suback = false;
                elog_i("MQTT_RX", "expected=SUBACK packet_id=%u "
                       "result=received", WRITER_CLOUD_SUB_PACKET_ID);
                WriterCloud_Set_Link_State(
                    WRITER_CLOUD_LINK_SEND_AVAILABILITY);
            } else if (WriterCloud_Time_Reached(s_cloud.deadline_ms)) {
                elog_e("MQTT_RX", "expected=SUBACK packet_id=%u "
                       "result=TIMEOUT", WRITER_CLOUD_SUB_PACKET_ID);
                WriterCloud_Reconnect("suback_timeout");
            }
            break;
        case WRITER_CLOUD_LINK_SEND_AVAILABILITY:
            if (!WriterCloud_Publish_Availability(
                    true,
                    WRITER_CLOUD_ACTION_AVAILABILITY_SENT)) {
                WriterCloud_Reconnect("availability_publish_failed");
            }
            break;
        case WRITER_CLOUD_LINK_SEND_INITIAL_STATUS:
            s_cloud.online = true;
            s_cloud.reconnect_delay_ms =
                WRITER_NET_RECONNECT_MIN_MS;
            if (WriterCloud_Publish_Status(
                    WRITER_CLOUD_ACTION_STATUS_SENT)) {
                elog_i("CLOUD", "online device_id=%s boot_id=%s",
                       WRITER_NET_DEVICE_ID, s_cloud.boot_id);
                WriterCloud_Set_Link_State(
                    WRITER_CLOUD_LINK_ONLINE);
            } else {
                WriterCloud_Reconnect("initial_status_publish_failed");
            }
            break;
        case WRITER_CLOUD_LINK_ONLINE:
            if (s_cloud.ping_outstanding &&
                WriterCloud_Time_Reached(s_cloud.deadline_ms)) {
                elog_e("MQTT_RX", "expected=PINGRESP result=TIMEOUT");
                WriterCloud_Reconnect("pingresp_timeout");
            } else if ((s_cloud.tx_state == WRITER_CLOUD_TX_IDLE) &&
                s_cloud.job.line_active &&
                ((uint32_t)(s_sys_tick - s_cloud.last_status_ms) >=
                 2000u)) {
                (void)WriterCloud_Publish_Status(
                    WRITER_CLOUD_ACTION_STATUS_SENT);
            } else if (!s_cloud.ping_outstanding &&
                       (s_cloud.tx_state == WRITER_CLOUD_TX_IDLE) &&
                       ((uint32_t)(s_sys_tick -
                                   s_cloud.last_activity_ms) >=
                        (WRITER_NET_KEEPALIVE_S * 500u))) {
                if (Bsp_Mqtt_Build_Ping(
                        s_cloud.mqtt_packet,
                        sizeof(s_cloud.mqtt_packet),
                        &packet_len)) {
                    (void)WriterCloud_Start_Mqtt_Send(
                        packet_len, WRITER_CLOUD_ACTION_PING_SENT);
                }
            }
            break;
        case WRITER_CLOUD_LINK_DISABLED:
        case WRITER_CLOUD_LINK_CONFIG_ERROR:
        default:
            break;
    }
}

void WriterCloud_Init(bool homed)
{
    int len;

    memset(&s_cloud, 0, sizeof(s_cloud));
    Bsp_EspAt_Init(&s_cloud.at_parser);
    Bsp_Mqtt_Parser_Init(&s_cloud.mqtt_parser);
    Bsp_WriterJob_Init(&s_cloud.job);
    WriterRehome_Init();
    App_WriterIdentity_Create_Boot_Id(s_cloud.boot_id);
    s_cloud.needs_rehome = !homed;
    s_cloud.reconnect_delay_ms = WRITER_NET_RECONNECT_MIN_MS;
    s_cloud.last_activity_ms = s_sys_tick;
    s_cloud.last_status_ms = s_sys_tick;

    len = snprintf(s_cloud.command_topic,
                   sizeof(s_cloud.command_topic),
                   "writer/v1/devices/%s/command",
                   WRITER_NET_DEVICE_ID);
    if ((len <= 0) ||
        ((uint32_t)len >= sizeof(s_cloud.command_topic))) {
        s_cloud.link_state = WRITER_CLOUD_LINK_CONFIG_ERROR;
        return;
    }
    (void)snprintf(s_cloud.ack_topic, sizeof(s_cloud.ack_topic),
                   "writer/v1/devices/%s/ack",
                   WRITER_NET_DEVICE_ID);
    (void)snprintf(s_cloud.status_topic, sizeof(s_cloud.status_topic),
                   "writer/v1/devices/%s/status",
                   WRITER_NET_DEVICE_ID);
    (void)snprintf(
        s_cloud.availability_topic,
        sizeof(s_cloud.availability_topic),
        "writer/v1/devices/%s/availability",
        WRITER_NET_DEVICE_ID);

    if (WriterCloud_Is_Enabled() &&
        !WriterCloud_Config_Is_Valid()) {
        s_cloud.link_state = WRITER_CLOUD_LINK_CONFIG_ERROR;
        elog_e("CLOUD", "network config invalid; check ignored local file");
        return;
    }
    if (WriterCloud_Is_Enabled()) {
        GCodeSerial_Set_Result_Callback(
            WriterCloud_Gcode_Result, &s_cloud);
        s_cloud.link_state = WRITER_CLOUD_LINK_RECONNECT_DELAY;
        s_cloud.deadline_ms = s_sys_tick;
        elog_i("CLOUD", "enabled device=%s boot=%s tls=%u",
               WRITER_NET_DEVICE_ID, s_cloud.boot_id,
               WRITER_NET_BROKER_TLS);
    } else {
        s_cloud.link_state = WRITER_CLOUD_LINK_DISABLED;
        GCodeSerial_Set_Result_Callback(NULL, NULL);
        elog_i("CLOUD", "disabled; local UART G-code mode active");
    }
}

void WriterCloud_Update(void)
{
    if (!WriterCloud_Is_Enabled()) {
        return;
    }
    if (s_cloud.link_state == WRITER_CLOUD_LINK_CONFIG_ERROR) {
        App_Vision_UART_Service();
        return;
    }
    App_Vision_UART_Service();
    WriterRehome_Update();
    WriterCloud_Process_Stop_Ack();
    WriterCloud_Process_Rehome_Result();
    WriterCloud_Process_Gcode_Result();
    WriterCloud_Process_Rx();
    WriterCloud_Service_Mqtt_Tx();
    if (s_cloud.tx_state == WRITER_CLOUD_TX_IDLE) {
        WriterCloud_Run_Link_State();
    }
}

bool WriterCloud_Is_Enabled(void)
{
    return (WRITER_NET_ENABLE != 0u) &&
           (WRITER_TEST_LOCAL_UART_CONTROL_ENABLE == 0u);
}

bool WriterCloud_Is_Online(void)
{
    return s_cloud.online;
}

bool WriterCloud_Needs_Rehome(void)
{
    return s_cloud.needs_rehome;
}

const char *WriterCloud_Get_Boot_Id(void)
{
    return s_cloud.boot_id;
}
