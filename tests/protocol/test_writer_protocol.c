#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "bsp_esp_at.h"
#include "bsp_mqtt.h"
#include "bsp_writer_job.h"
#include "bsp_writer_protocol.h"

static unsigned g_checks;

#define CHECK(condition)                                                        \
    do {                                                                        \
        g_checks++;                                                             \
        if (!(condition)) {                                                     \
            fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__,            \
                    #condition);                                                \
            exit(1);                                                            \
        }                                                                       \
    } while (0)

static bsp_writer_parse_result_t Parse(const char *json,
                                       bsp_writer_command_t *command)
{
    return Bsp_Writer_Parse_Command((const uint8_t *)json,
                                    (uint16_t)strlen(json),
                                    command);
}

static void Test_At_Lines_And_Prompt(void)
{
    static const char stream[] = "\r\nOK\r\nERROR\r\nFAIL\r\n>";
    static const char *expected[] = {"OK", "ERROR", "FAIL"};
    bsp_esp_at_parser_t parser;
    bsp_esp_at_event_t event;
    unsigned lines = 0u;
    unsigned prompts = 0u;
    size_t index;

    Bsp_EspAt_Init(&parser);
    for (index = 0u; index < sizeof(stream) - 1u; index++) {
        Bsp_EspAt_Feed(&parser, (uint8_t)stream[index], &event);
        if (event.type == BSP_ESP_AT_EVENT_LINE) {
            CHECK(lines < 3u);
            CHECK(strcmp(event.line, expected[lines]) == 0);
            lines++;
        } else if (event.type == BSP_ESP_AT_EVENT_PROMPT) {
            prompts++;
        }
    }
    CHECK(lines == 3u);
    CHECK(prompts == 1u);
}

static void Test_Ipd_Streaming(void)
{
    static const char stream[] = "+IPD,0,5:hello+IPD,3:bye";
    static const char expected[] = "hellobye";
    bsp_esp_at_parser_t parser;
    bsp_esp_at_event_t event;
    char payload[sizeof(expected)] = {0};
    unsigned begins = 0u;
    unsigned data_count = 0u;
    size_t index;

    Bsp_EspAt_Init(&parser);
    for (index = 0u; index < sizeof(stream) - 1u; index++) {
        Bsp_EspAt_Feed(&parser, (uint8_t)stream[index], &event);
        if (event.type == BSP_ESP_AT_EVENT_IPD_BEGIN) {
            CHECK((event.ipd_len == 5u) || (event.ipd_len == 3u));
            begins++;
        } else if (event.type == BSP_ESP_AT_EVENT_IPD_DATA) {
            CHECK(data_count < sizeof(payload) - 1u);
            payload[data_count++] = (char)event.data;
        }
    }
    CHECK(begins == 2u);
    CHECK(data_count == 8u);
    CHECK(strcmp(payload, expected) == 0);
}

static void Test_Mqtt_Remaining_Length(void)
{
    uint8_t encoded[4];
    uint8_t len;

    CHECK(Bsp_Mqtt_Encode_Remaining_Length(127u, encoded, &len));
    CHECK(len == 1u);
    CHECK(encoded[0] == 0x7Fu);
    CHECK(Bsp_Mqtt_Encode_Remaining_Length(128u, encoded, &len));
    CHECK(len == 2u);
    CHECK(encoded[0] == 0x80u);
    CHECK(encoded[1] == 0x01u);
    CHECK(Bsp_Mqtt_Encode_Remaining_Length(268435455u, encoded, &len));
    CHECK(len == 4u);
    CHECK(!Bsp_Mqtt_Encode_Remaining_Length(268435456u, encoded, &len));
}

static void Test_Mqtt_Connect_Anonymous_And_Authenticated(void)
{
    bsp_mqtt_connect_options_t options;
    uint8_t anonymous[128];
    uint8_t authenticated[128];
    uint16_t anonymous_len;
    uint16_t authenticated_len;

    options.client_id = "writer-test";
    options.username = "";
    options.password = "";
    options.will_topic = "writer/v1/devices/writer-test/availability";
    options.will_payload = "{}";
    options.keepalive_s = 30u;

    CHECK(Bsp_Mqtt_Build_Connect(
        &options, anonymous, sizeof(anonymous), &anonymous_len));
    CHECK(anonymous[0] == 0x10u);
    CHECK(anonymous[9] == 0x26u);

    options.username = "user";
    options.password = "pass";
    CHECK(Bsp_Mqtt_Build_Connect(
        &options, authenticated, sizeof(authenticated), &authenticated_len));
    CHECK(authenticated[9] == 0xE6u);
    CHECK(authenticated_len == (uint16_t)(anonymous_len + 12u));

    options.username = "";
    CHECK(!Bsp_Mqtt_Build_Connect(
        &options, authenticated, sizeof(authenticated), &authenticated_len));
}

static void Test_Mqtt_Publish_Fragment_And_Coalesce(void)
{
    static const char topic[] = "writer/v1/devices/writer-01/command";
    static const uint8_t payload1[] = "{\"v\":1}";
    static const uint8_t payload2[] = "{\"v\":1,\"op\":\"status\"}";
    uint8_t packet1[128];
    uint8_t packet2[128];
    uint16_t packet1_len;
    uint16_t packet2_len;
    bsp_mqtt_parser_t parser;
    bsp_mqtt_event_t event;
    unsigned packets = 0u;
    uint16_t index;

    CHECK(Bsp_Mqtt_Build_Publish(topic, payload1,
                                 (uint16_t)(sizeof(payload1) - 1u),
                                 false, packet1, sizeof(packet1), &packet1_len));
    CHECK(Bsp_Mqtt_Build_Publish(topic, payload2,
                                 (uint16_t)(sizeof(payload2) - 1u),
                                 false, packet2, sizeof(packet2), &packet2_len));

    Bsp_Mqtt_Parser_Init(&parser);
    for (index = 0u; index < packet1_len; index++) {
        const uint8_t *decoded_topic;
        const uint8_t *decoded_payload;
        uint16_t decoded_topic_len;
        uint16_t decoded_payload_len;
        uint8_t qos;

        Bsp_Mqtt_Parser_Feed(&parser, packet1[index], &event);
        if (event.type == BSP_MQTT_EVENT_PACKET) {
            CHECK(Bsp_Mqtt_Decode_Publish(&event.packet,
                                          &decoded_topic,
                                          &decoded_topic_len,
                                          &decoded_payload,
                                          &decoded_payload_len,
                                          &qos));
            CHECK(decoded_topic_len == strlen(topic));
            CHECK(memcmp(decoded_topic, topic, decoded_topic_len) == 0);
            CHECK(decoded_payload_len == sizeof(payload1) - 1u);
            CHECK(memcmp(decoded_payload, payload1, decoded_payload_len) == 0);
            CHECK(qos == 0u);
            packets++;
        }
    }
    for (index = 0u; index < packet2_len; index++) {
        Bsp_Mqtt_Parser_Feed(&parser, packet2[index], &event);
        if (event.type == BSP_MQTT_EVENT_PACKET) {
            packets++;
        }
    }
    CHECK(packets == 2u);
}

static void Test_Mqtt_Control_Packets(void)
{
    static const uint8_t connack[] = {0x20u, 0x02u, 0x00u, 0x00u};
    static const uint8_t suback[] = {0x90u, 0x03u, 0x12u, 0x34u, 0x00u};
    bsp_mqtt_parser_t parser;
    bsp_mqtt_event_t event;
    size_t index;

    Bsp_Mqtt_Parser_Init(&parser);
    for (index = 0u; index < sizeof(connack); index++) {
        Bsp_Mqtt_Parser_Feed(&parser, connack[index], &event);
    }
    CHECK(event.type == BSP_MQTT_EVENT_PACKET);
    CHECK(Bsp_Mqtt_Is_ConnAck_Accepted(&event.packet));

    for (index = 0u; index < sizeof(suback); index++) {
        Bsp_Mqtt_Parser_Feed(&parser, suback[index], &event);
    }
    CHECK(event.type == BSP_MQTT_EVENT_PACKET);
    CHECK(Bsp_Mqtt_Is_SubAck(&event.packet, 0x1234u));
}

static void Feed_Ipd_To_Mqtt(const uint8_t *payload,
                             uint16_t payload_len,
                             bsp_esp_at_parser_t *at_parser,
                             bsp_mqtt_parser_t *mqtt_parser,
                             unsigned *publish_count)
{
    char header[24];
    int header_len = snprintf(
        header, sizeof(header), "+IPD,%u:", payload_len);
    uint16_t index;

    CHECK(header_len > 0);
    for (index = 0u; index < (uint16_t)header_len; index++) {
        bsp_esp_at_event_t at_event;
        Bsp_EspAt_Feed(at_parser, (uint8_t)header[index], &at_event);
    }
    for (index = 0u; index < payload_len; index++) {
        bsp_esp_at_event_t at_event;
        Bsp_EspAt_Feed(at_parser, payload[index], &at_event);
        if (at_event.type == BSP_ESP_AT_EVENT_IPD_DATA) {
            bsp_mqtt_event_t mqtt_event;
            Bsp_Mqtt_Parser_Feed(
                mqtt_parser, at_event.data, &mqtt_event);
            if ((mqtt_event.type == BSP_MQTT_EVENT_PACKET) &&
                (mqtt_event.packet.type == 3u)) {
                (*publish_count)++;
            }
        }
    }
}

static void Test_Ipd_Mqtt_Cross_Boundaries(void)
{
    static const char topic[] = "writer/v1/devices/writer-01/command";
    static const uint8_t payload[] =
        "{\"v\":1,\"op\":\"status\",\"request_id\":\"R1\"}";
    uint8_t packet[160];
    uint16_t packet_len;
    uint16_t split;
    bsp_esp_at_parser_t at_parser;
    bsp_mqtt_parser_t mqtt_parser;
    unsigned publish_count = 0u;

    CHECK(Bsp_Mqtt_Build_Publish(
        topic, payload, (uint16_t)(sizeof(payload) - 1u),
        false, packet, sizeof(packet), &packet_len));
    split = 3u;
    Bsp_EspAt_Init(&at_parser);
    Bsp_Mqtt_Parser_Init(&mqtt_parser);
    Feed_Ipd_To_Mqtt(packet, split, &at_parser,
                     &mqtt_parser, &publish_count);
    Feed_Ipd_To_Mqtt(&packet[split],
                     (uint16_t)(packet_len - split),
                     &at_parser, &mqtt_parser, &publish_count);
    CHECK(publish_count == 1u);
}

static void Test_Json_Commands(void)
{
    bsp_writer_command_t command;
    char overlong[320];
    char maximum[320];
    size_t index;

    CHECK(Parse("{\"v\":1,\"op\":\"job_begin\",\"job_id\":\"JOB-1\","
                "\"total\":2,\"crc32\":\"1234ABCD\"}", &command) ==
          BSP_WRITER_PARSE_OK);
    CHECK(command.operation == BSP_WRITER_OP_JOB_BEGIN);
    CHECK(command.total == 2u);
    CHECK(command.crc32 == 0x1234ABCDu);

    CHECK(Parse("{\"v\":2,\"op\":\"status\",\"request_id\":\"R1\"}",
                &command) == BSP_WRITER_PARSE_BAD_VERSION);
    CHECK(Parse("{\"v\":1,\"op\":\"rehome\",\"request_id\":\"R1\"}",
                &command) == BSP_WRITER_PARSE_OK);
    CHECK(command.operation == BSP_WRITER_OP_REHOME);
    CHECK(Parse("{\"v\":1,\"op\":\"rehome\",\"request_id\":\"R1\","
                "\"job_id\":\"J\"}", &command) ==
          BSP_WRITER_PARSE_BAD_FIELD);
    CHECK(Parse("{\"v\":1,\"op\":\"gcode\",\"job_id\":\"J\",\"seq\":0}",
                &command) == BSP_WRITER_PARSE_BAD_FIELD);
    CHECK(Parse("{\"v\":1,\"op\":\"gcode\",\"job_id\":\"bad id\","
                "\"seq\":0,\"line\":\"G21\"}", &command) ==
          BSP_WRITER_PARSE_BAD_ID);
    CHECK(Parse("{\"v\":1,\"op\":\"gcode\",\"job_id\":\"J\",\"seq\":0,"
                "\"line\":\"G1 X1\\\\Y2\"}", &command) ==
          BSP_WRITER_PARSE_INVALID_GCODE);
    CHECK(Parse("{\"v\":1,\"op\":\"status\",\"request_id\":\"R1\","
                "\"job_id\":\"J\"}", &command) ==
          BSP_WRITER_PARSE_BAD_FIELD);

    strcpy(maximum,
           "{\"v\":1,\"op\":\"gcode\",\"job_id\":\"J\",\"seq\":0,\"line\":\"");
    index = strlen(maximum);
    memset(&maximum[index], 'G', 191u);
    index += 191u;
    strcpy(&maximum[index], "\"}");
    CHECK(Parse(maximum, &command) == BSP_WRITER_PARSE_OK);

    strcpy(overlong,
           "{\"v\":1,\"op\":\"gcode\",\"job_id\":\"J\",\"seq\":0,\"line\":\"");
    index = strlen(overlong);
    memset(&overlong[index], 'G', 192u);
    index += 192u;
    strcpy(&overlong[index], "\"}");
    CHECK(Parse(overlong, &command) == BSP_WRITER_PARSE_LINE_TOO_LONG);
}

static uint32_t Crc_For_Two_Lines(void)
{
    static const uint8_t first[] = "G21\n";
    static const uint8_t second[] = "M5\n";
    uint32_t crc = Bsp_Writer_Crc32_Init();

    crc = Bsp_Writer_Crc32_Update(crc, first,
                                  (uint16_t)(sizeof(first) - 1u));
    crc = Bsp_Writer_Crc32_Update(crc, second,
                                  (uint16_t)(sizeof(second) - 1u));
    return Bsp_Writer_Crc32_Final(crc);
}

static void Test_Job_Sequence_Crc_Stop_And_Reboot(void)
{
    static const uint8_t g21[] = "G21";
    static const uint8_t m5[] = "M5";
    bsp_writer_job_t job;
    uint32_t expected_crc = Crc_For_Two_Lines();
    char boot_a[9];
    char boot_b[9];

    Bsp_WriterJob_Init(&job);
    CHECK(Bsp_WriterJob_Begin(&job, "JOB1", 2u, expected_crc) ==
          BSP_WRITER_JOB_ACCEPTED);
    CHECK(Bsp_WriterJob_Begin(&job, "JOB1", 2u, expected_crc) ==
          BSP_WRITER_JOB_DUPLICATE_BEGIN);
    CHECK(Bsp_WriterJob_Accept_Line(&job, "JOB1", 0u) ==
          BSP_WRITER_JOB_ACCEPTED);
    CHECK(Bsp_WriterJob_Line_Needs_Start(&job));
    CHECK(Bsp_WriterJob_Accept_Line(&job, "JOB1", 0u) ==
          BSP_WRITER_JOB_DUPLICATE_ACTIVE);
    CHECK(Bsp_WriterJob_Mark_Line_Started(&job));
    CHECK(!Bsp_WriterJob_Line_Needs_Start(&job));
    CHECK(!Bsp_WriterJob_Mark_Line_Started(&job));
    CHECK(Bsp_WriterJob_Complete_Line(&job, g21, sizeof(g21) - 1u));
    CHECK(Bsp_WriterJob_Accept_Line(&job, "JOB1", 0u) ==
          BSP_WRITER_JOB_DUPLICATE_COMPLETED);
    CHECK(Bsp_WriterJob_Accept_Line(&job, "JOB1", 2u) ==
          BSP_WRITER_JOB_OUT_OF_ORDER);
    CHECK(Bsp_WriterJob_Accept_Line(&job, "JOB1", 1u) ==
          BSP_WRITER_JOB_ACCEPTED);
    CHECK(Bsp_WriterJob_Mark_Line_Started(&job));
    CHECK(Bsp_WriterJob_Complete_Line(&job, m5, sizeof(m5) - 1u));
    CHECK(Bsp_WriterJob_End(&job, "JOB1", 2u, expected_crc) ==
          BSP_WRITER_JOB_ACCEPTED);
    CHECK(Bsp_WriterJob_End(&job, "JOB1", 2u, expected_crc ^ 1u) ==
          BSP_WRITER_JOB_CRC_MISMATCH);
    CHECK(Bsp_WriterJob_Finish(&job));
    CHECK(!job.active);
    CHECK(job.has_ended);
    CHECK(Bsp_WriterJob_End(&job, "JOB1", 2u, expected_crc) ==
          BSP_WRITER_JOB_DUPLICATE_END);
    CHECK(Bsp_WriterJob_End(&job, "JOB1", 2u, expected_crc ^ 1u) ==
          BSP_WRITER_JOB_NO_ACTIVE);

    Bsp_WriterJob_Abort(&job);
    CHECK(!job.active);
    CHECK(!job.line_active);
    CHECK(job.expected_seq == 0u);
    CHECK(!job.has_ended);

    Bsp_WriterJob_Init(&job);
    CHECK(!job.active);
    CHECK(job.job_id[0] == '\0');
    CHECK(job.running_crc32 == Bsp_Writer_Crc32_Init());

    Bsp_Writer_Make_Boot_Id(0x12345678u, 100u, boot_a);
    Bsp_Writer_Make_Boot_Id(0x12345678u, 101u, boot_b);
    CHECK(strlen(boot_a) == 8u);
    CHECK(strlen(boot_b) == 8u);
    CHECK(strcmp(boot_a, boot_b) != 0);
}

int main(void)
{
    Test_At_Lines_And_Prompt();
    Test_Ipd_Streaming();
    Test_Mqtt_Remaining_Length();
    Test_Mqtt_Connect_Anonymous_And_Authenticated();
    Test_Mqtt_Publish_Fragment_And_Coalesce();
    Test_Mqtt_Control_Packets();
    Test_Ipd_Mqtt_Cross_Boundaries();
    Test_Json_Commands();
    Test_Job_Sequence_Crc_Stop_And_Reboot();

    printf("PASS: %u protocol checks\n", g_checks);
    return 0;
}
