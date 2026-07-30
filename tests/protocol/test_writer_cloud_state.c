#include <stdbool.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "bsp_esp_at.h"
#include "bsp_mqtt.h"
#include "gcode_serial.h"
#include "writer_rehome.h"

volatile uint32_t s_sys_tick;

static unsigned int g_checks;

void elog_output(uint8_t level,
                 const char *tag,
                 const char *file,
                 const char *func,
                 const long line,
                 const char *format,
                 ...)
{
    (void)level;
    (void)tag;
    (void)file;
    (void)func;
    (void)line;
    (void)format;
}

bool App_Vision_UART_Try_Send(const uint8_t *data, uint16_t len)
{
    (void)data;
    (void)len;
    return true;
}

uint32_t App_Vision_UART_Get_Rx_Dropped(void)
{
    return 0u;
}

uint32_t App_Vision_UART_Get_Tx_Rejected(void)
{
    return 0u;
}

uint16_t App_Vision_UART_Read(uint8_t *data, uint16_t capacity)
{
    (void)data;
    (void)capacity;
    return 0u;
}

void App_Vision_UART_Service(void)
{
}

bool GCodeSerial_ProcessFrame(const uint8_t *frame, uint16_t len)
{
    (void)frame;
    (void)len;
    return true;
}

void GCodeSerial_Set_Result_Callback(
    gcode_serial_result_callback_t callback,
    void *context)
{
    (void)callback;
    (void)context;
}

bool GCodeSerial_Is_Idle(void)
{
    return true;
}

bool GCodeSerial_Is_Pen_Down(void)
{
    return false;
}

void GCodeSerial_Abort(void)
{
}

void WriterRehome_Init(void)
{
}

bool WriterRehome_Start(void)
{
    return true;
}

void WriterRehome_Update(void)
{
}

void WriterRehome_Abort(void)
{
}

bool WriterRehome_Is_Active(void)
{
    return false;
}

bool WriterRehome_Is_Succeeded(void)
{
    return false;
}

bool WriterRehome_Is_Failed(void)
{
    return false;
}

void App_WriterIdentity_Create_Boot_Id(char boot_id[9])
{
    memcpy(boot_id, "testboot", 9u);
}

#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wpedantic"
#pragma GCC diagnostic ignored "-Wreturn-type"
#pragma GCC diagnostic ignored "-Wunused-function"
#include "../../TASK/writer_cloud.c"
#pragma GCC diagnostic pop

static void Check(bool condition, const char *message)
{
    g_checks++;
    if (!condition) {
        fprintf(stderr, "FAIL: %s\n", message);
        exit(EXIT_FAILURE);
    }
}

static void Reset_State(writer_cloud_link_state_t state)
{
    memset(&s_cloud, 0, sizeof(s_cloud));
    s_cloud.link_state = state;
    s_cloud.step_started = true;
    s_cloud.deadline_ms = 1000u;
    s_cloud.reconnect_delay_ms = WRITER_NET_RECONNECT_MIN_MS;
    s_sys_tick = 100u;
}

static void Complete_Current_At_Step(writer_cloud_link_state_t next)
{
    (void)WriterCloud_Run_At_Step(
        "AT\r\n", WRITER_NET_AT_TIMEOUT_MS, next, false);
}

static void Test_Join_Wifi_Transient_Disconnect_Then_Ok(void)
{
    Reset_State(WRITER_CLOUD_LINK_JOIN_WIFI);

    WriterCloud_Handle_At_Line("WIFI DISCONNECT");
    Check(s_cloud.link_state == WRITER_CLOUD_LINK_JOIN_WIFI,
          "JOIN_WIFI transient disconnect must not reconnect");

    WriterCloud_Handle_At_Line("WIFI CONNECTED");
    WriterCloud_Handle_At_Line("WIFI GOT IP");
    WriterCloud_Handle_At_Line("OK");
    Complete_Current_At_Step(WRITER_CLOUD_LINK_CLOSE_OLD);

    Check(s_cloud.link_state == WRITER_CLOUD_LINK_CLOSE_OLD,
          "JOIN_WIFI final OK must advance to CLOSE_OLD");
}

static void Test_Join_Wifi_Transient_Disconnect_Then_Error(void)
{
    Reset_State(WRITER_CLOUD_LINK_JOIN_WIFI);

    WriterCloud_Handle_At_Line("WIFI DISCONNECT");
    WriterCloud_Handle_At_Line("ERROR");
    Complete_Current_At_Step(WRITER_CLOUD_LINK_CLOSE_OLD);

    Check(s_cloud.link_state == WRITER_CLOUD_LINK_RECONNECT_DELAY,
          "JOIN_WIFI final ERROR must reconnect");
}

static void Test_Join_Wifi_Transient_Disconnect_Then_Fail(void)
{
    Reset_State(WRITER_CLOUD_LINK_JOIN_WIFI);

    WriterCloud_Handle_At_Line("WIFI DISCONNECT");
    WriterCloud_Handle_At_Line("FAIL");
    Complete_Current_At_Step(WRITER_CLOUD_LINK_CLOSE_OLD);

    Check(s_cloud.link_state == WRITER_CLOUD_LINK_RECONNECT_DELAY,
          "JOIN_WIFI final FAIL must reconnect");
}

static void Test_Join_Wifi_Transient_Disconnect_Then_Busy(void)
{
    Reset_State(WRITER_CLOUD_LINK_JOIN_WIFI);

    WriterCloud_Handle_At_Line("WIFI DISCONNECT");
    WriterCloud_Handle_At_Line("busy p...");
    Complete_Current_At_Step(WRITER_CLOUD_LINK_CLOSE_OLD);

    Check(s_cloud.link_state == WRITER_CLOUD_LINK_RECONNECT_DELAY,
          "JOIN_WIFI final busy response must reconnect");
}

static void Test_Join_Wifi_Transient_Disconnect_Then_Timeout(void)
{
    Reset_State(WRITER_CLOUD_LINK_JOIN_WIFI);

    WriterCloud_Handle_At_Line("WIFI DISCONNECT");
    s_sys_tick = s_cloud.deadline_ms;
    Complete_Current_At_Step(WRITER_CLOUD_LINK_CLOSE_OLD);

    Check(s_cloud.link_state == WRITER_CLOUD_LINK_RECONNECT_DELAY,
          "JOIN_WIFI timeout after transient disconnect must reconnect");
}

static void Test_Connected_Wifi_Disconnect_Reconnects(void)
{
    Reset_State(WRITER_CLOUD_LINK_ONLINE);

    WriterCloud_Handle_At_Line("WIFI DISCONNECT");

    Check(s_cloud.link_state == WRITER_CLOUD_LINK_RECONNECT_DELAY,
          "ONLINE WIFI DISCONNECT must reconnect");
}

static void Test_Connected_Closed_Reconnects(void)
{
    Reset_State(WRITER_CLOUD_LINK_ONLINE);

    WriterCloud_Handle_At_Line("CLOSED");

    Check(s_cloud.link_state == WRITER_CLOUD_LINK_RECONNECT_DELAY,
          "ONLINE CLOSED must reconnect");
}

static void Test_Tcp_Wifi_Disconnect_Reconnects(void)
{
    Reset_State(WRITER_CLOUD_LINK_TCP);

    WriterCloud_Handle_At_Line("WIFI DISCONNECT");

    Check(s_cloud.link_state == WRITER_CLOUD_LINK_RECONNECT_DELAY,
          "TCP WIFI DISCONNECT must reconnect");
}

static void Test_Tcp_Closed_Reconnects(void)
{
    Reset_State(WRITER_CLOUD_LINK_TCP);

    WriterCloud_Handle_At_Line("CLOSED");

    Check(s_cloud.link_state == WRITER_CLOUD_LINK_RECONNECT_DELAY,
          "TCP CLOSED must reconnect");
}

static void Test_Join_Wifi_Closed_Still_Reconnects(void)
{
    Reset_State(WRITER_CLOUD_LINK_JOIN_WIFI);

    WriterCloud_Handle_At_Line("CLOSED");

    Check(s_cloud.link_state == WRITER_CLOUD_LINK_RECONNECT_DELAY,
          "JOIN_WIFI CLOSED must remain a hard link-close event");
}

int main(void)
{
    Test_Join_Wifi_Transient_Disconnect_Then_Ok();
    Test_Join_Wifi_Transient_Disconnect_Then_Error();
    Test_Join_Wifi_Transient_Disconnect_Then_Fail();
    Test_Join_Wifi_Transient_Disconnect_Then_Busy();
    Test_Join_Wifi_Transient_Disconnect_Then_Timeout();
    Test_Connected_Wifi_Disconnect_Reconnects();
    Test_Connected_Closed_Reconnects();
    Test_Tcp_Wifi_Disconnect_Reconnects();
    Test_Tcp_Closed_Reconnects();
    Test_Join_Wifi_Closed_Still_Reconnects();

    printf("PASS: %u writer cloud state checks\n", g_checks);
    return EXIT_SUCCESS;
}
