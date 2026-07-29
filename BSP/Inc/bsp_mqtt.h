/**
 * @file    bsp_mqtt.h
 * @brief   Bounded MQTT 3.1.1 encoder and streaming decoder.
 */
#ifndef BSP_MQTT_H
#define BSP_MQTT_H

#include <stdbool.h>
#include <stdint.h>

#define BSP_MQTT_BODY_MAX (512u)

typedef enum {
    BSP_MQTT_EVENT_NONE = 0,
    BSP_MQTT_EVENT_PACKET,
    BSP_MQTT_EVENT_ERROR
} bsp_mqtt_event_type_t;

typedef struct {
    uint8_t type;
    uint8_t flags;
    const uint8_t *body;
    uint16_t body_len;
} bsp_mqtt_packet_t;

typedef struct {
    bsp_mqtt_event_type_t type;
    bsp_mqtt_packet_t packet;
} bsp_mqtt_event_t;

typedef enum {
    BSP_MQTT_PARSE_HEADER = 0,
    BSP_MQTT_PARSE_REMAINING,
    BSP_MQTT_PARSE_BODY,
    BSP_MQTT_PARSE_DISCARD
} bsp_mqtt_parse_state_t;

typedef struct {
    bsp_mqtt_parse_state_t state;
    uint8_t fixed_header;
    uint8_t remaining_bytes;
    uint32_t remaining_len;
    uint32_t remaining_multiplier;
    uint32_t discard_remaining;
    uint16_t body_len;
    uint8_t body[BSP_MQTT_BODY_MAX];
} bsp_mqtt_parser_t;

typedef struct {
    const char *client_id;
    const char *username;
    const char *password;
    const char *will_topic;
    const char *will_payload;
    uint16_t keepalive_s;
} bsp_mqtt_connect_options_t;

void Bsp_Mqtt_Parser_Init(bsp_mqtt_parser_t *parser);
void Bsp_Mqtt_Parser_Feed(bsp_mqtt_parser_t *parser,
                          uint8_t data,
                          bsp_mqtt_event_t *event);

bool Bsp_Mqtt_Encode_Remaining_Length(uint32_t value,
                                      uint8_t encoded[4],
                                      uint8_t *encoded_len);
bool Bsp_Mqtt_Build_Connect(const bsp_mqtt_connect_options_t *options,
                            uint8_t *output,
                            uint16_t output_capacity,
                            uint16_t *output_len);
bool Bsp_Mqtt_Build_Subscribe(uint16_t packet_id,
                              const char *topic,
                              uint8_t *output,
                              uint16_t output_capacity,
                              uint16_t *output_len);
bool Bsp_Mqtt_Build_Publish(const char *topic,
                            const uint8_t *payload,
                            uint16_t payload_len,
                            bool retained,
                            uint8_t *output,
                            uint16_t output_capacity,
                            uint16_t *output_len);
bool Bsp_Mqtt_Build_Ping(uint8_t *output,
                         uint16_t output_capacity,
                         uint16_t *output_len);

bool Bsp_Mqtt_Is_ConnAck_Accepted(const bsp_mqtt_packet_t *packet);
bool Bsp_Mqtt_Is_SubAck(const bsp_mqtt_packet_t *packet,
                        uint16_t expected_packet_id);
bool Bsp_Mqtt_Decode_Publish(const bsp_mqtt_packet_t *packet,
                             const uint8_t **topic,
                             uint16_t *topic_len,
                             const uint8_t **payload,
                             uint16_t *payload_len,
                             uint8_t *qos);

#endif /* BSP_MQTT_H */
