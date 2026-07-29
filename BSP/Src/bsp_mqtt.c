/**
 * @file    bsp_mqtt.c
 * @brief   Bounded MQTT 3.1.1 encoder and streaming decoder.
 */
#include "bsp_mqtt.h"

#include <stddef.h>
#include <string.h>

#define BSP_MQTT_PACKET_TYPE_CONNECT   (1u)
#define BSP_MQTT_PACKET_TYPE_CONNACK   (2u)
#define BSP_MQTT_PACKET_TYPE_PUBLISH   (3u)
#define BSP_MQTT_PACKET_TYPE_SUBSCRIBE (8u)
#define BSP_MQTT_PACKET_TYPE_SUBACK    (9u)
#define BSP_MQTT_PACKET_TYPE_PINGREQ   (12u)

static void Bsp_Mqtt_Clear_Event(bsp_mqtt_event_t *event)
{
    event->type = BSP_MQTT_EVENT_NONE;
    event->packet.type = 0u;
    event->packet.flags = 0u;
    event->packet.body = NULL;
    event->packet.body_len = 0u;
}

static void Bsp_Mqtt_Reset_Frame(bsp_mqtt_parser_t *parser)
{
    parser->state = BSP_MQTT_PARSE_HEADER;
    parser->fixed_header = 0u;
    parser->remaining_bytes = 0u;
    parser->remaining_len = 0u;
    parser->remaining_multiplier = 1u;
    parser->discard_remaining = 0u;
    parser->body_len = 0u;
}

static bool Bsp_Mqtt_Write_Utf8(uint8_t *output,
                                uint16_t capacity,
                                uint16_t *index,
                                const char *text)
{
    size_t text_len;

    if ((output == NULL) || (index == NULL) || (text == NULL)) {
        return false;
    }
    text_len = strlen(text);
    if ((text_len > UINT16_MAX) ||
        ((uint32_t)(*index) + 2u + (uint32_t)text_len > capacity)) {
        return false;
    }

    output[(*index)++] = (uint8_t)((uint16_t)text_len >> 8);
    output[(*index)++] = (uint8_t)((uint16_t)text_len & 0xFFu);
    memcpy(&output[*index], text, text_len);
    *index = (uint16_t)(*index + (uint16_t)text_len);
    return true;
}

static bool Bsp_Mqtt_Finalize(uint8_t fixed_header,
                              uint8_t *output,
                              uint16_t output_capacity,
                              uint16_t body_start,
                              uint16_t body_len,
                              uint16_t *output_len)
{
    uint8_t encoded[4];
    uint8_t encoded_len;
    uint16_t packet_len;

    if (!Bsp_Mqtt_Encode_Remaining_Length(body_len,
                                          encoded,
                                          &encoded_len)) {
        return false;
    }
    packet_len = (uint16_t)(1u + encoded_len + body_len);
    if (packet_len > output_capacity) {
        return false;
    }

    memmove(&output[1u + encoded_len], &output[body_start], body_len);
    output[0] = fixed_header;
    memcpy(&output[1], encoded, encoded_len);
    *output_len = packet_len;
    return true;
}

void Bsp_Mqtt_Parser_Init(bsp_mqtt_parser_t *parser)
{
    if (parser == NULL) {
        return;
    }
    Bsp_Mqtt_Reset_Frame(parser);
}

void Bsp_Mqtt_Parser_Feed(bsp_mqtt_parser_t *parser,
                          uint8_t data,
                          bsp_mqtt_event_t *event)
{
    if ((parser == NULL) || (event == NULL)) {
        return;
    }
    Bsp_Mqtt_Clear_Event(event);

    switch (parser->state) {
        case BSP_MQTT_PARSE_HEADER:
            parser->fixed_header = data;
            parser->remaining_bytes = 0u;
            parser->remaining_len = 0u;
            parser->remaining_multiplier = 1u;
            parser->body_len = 0u;
            parser->state = BSP_MQTT_PARSE_REMAINING;
            return;

        case BSP_MQTT_PARSE_REMAINING:
            parser->remaining_bytes++;
            if (parser->remaining_bytes > 4u) {
                Bsp_Mqtt_Reset_Frame(parser);
                event->type = BSP_MQTT_EVENT_ERROR;
                return;
            }
            parser->remaining_len +=
                (uint32_t)(data & 0x7Fu) * parser->remaining_multiplier;
            if ((data & 0x80u) != 0u) {
                if (parser->remaining_bytes == 4u) {
                    Bsp_Mqtt_Reset_Frame(parser);
                    event->type = BSP_MQTT_EVENT_ERROR;
                    return;
                }
                parser->remaining_multiplier *= 128u;
                return;
            }
            if (parser->remaining_len > BSP_MQTT_BODY_MAX) {
                parser->discard_remaining = parser->remaining_len;
                parser->state = BSP_MQTT_PARSE_DISCARD;
                event->type = BSP_MQTT_EVENT_ERROR;
                return;
            }
            if (parser->remaining_len == 0u) {
                event->type = BSP_MQTT_EVENT_PACKET;
                event->packet.type =
                    (uint8_t)((parser->fixed_header >> 4) & 0x0Fu);
                event->packet.flags =
                    (uint8_t)(parser->fixed_header & 0x0Fu);
                event->packet.body = parser->body;
                event->packet.body_len = 0u;
                Bsp_Mqtt_Reset_Frame(parser);
                return;
            }
            parser->state = BSP_MQTT_PARSE_BODY;
            return;

        case BSP_MQTT_PARSE_BODY:
            parser->body[parser->body_len++] = data;
            if (parser->body_len == parser->remaining_len) {
                event->type = BSP_MQTT_EVENT_PACKET;
                event->packet.type =
                    (uint8_t)((parser->fixed_header >> 4) & 0x0Fu);
                event->packet.flags =
                    (uint8_t)(parser->fixed_header & 0x0Fu);
                event->packet.body = parser->body;
                event->packet.body_len = parser->body_len;
                Bsp_Mqtt_Reset_Frame(parser);
            }
            return;

        case BSP_MQTT_PARSE_DISCARD:
            if (parser->discard_remaining > 0u) {
                parser->discard_remaining--;
            }
            if (parser->discard_remaining == 0u) {
                Bsp_Mqtt_Reset_Frame(parser);
            }
            return;

        default:
            Bsp_Mqtt_Reset_Frame(parser);
            event->type = BSP_MQTT_EVENT_ERROR;
            return;
    }
}

bool Bsp_Mqtt_Encode_Remaining_Length(uint32_t value,
                                      uint8_t encoded[4],
                                      uint8_t *encoded_len)
{
    uint8_t count = 0u;

    if ((encoded == NULL) || (encoded_len == NULL) ||
        (value > 268435455u)) {
        return false;
    }

    do {
        uint8_t byte = (uint8_t)(value % 128u);

        value /= 128u;
        if (value > 0u) {
            byte |= 0x80u;
        }
        if (count >= 4u) {
            return false;
        }
        encoded[count++] = byte;
    } while (value > 0u);

    *encoded_len = count;
    return true;
}

bool Bsp_Mqtt_Build_Connect(const bsp_mqtt_connect_options_t *options,
                            uint8_t *output,
                            uint16_t output_capacity,
                            uint16_t *output_len)
{
    uint16_t index = 5u;
    uint16_t body_start = index;
    uint8_t connect_flags = 0x26u;
    bool has_username;
    bool has_password;

    if ((options == NULL) || (output == NULL) || (output_len == NULL) ||
        (options->client_id == NULL) || (options->client_id[0] == '\0') ||
        (options->username == NULL) ||
        (options->password == NULL) ||
        (options->will_topic == NULL) ||
        (options->will_payload == NULL)) {
        return false;
    }
    has_username = options->username[0] != '\0';
    has_password = options->password[0] != '\0';
    if (has_password && !has_username) {
        return false;
    }
    if (has_username) {
        connect_flags |= 0x80u;
    }
    if (has_password) {
        connect_flags |= 0x40u;
    }

    if (!Bsp_Mqtt_Write_Utf8(output, output_capacity, &index, "MQTT") ||
        ((uint32_t)index + 4u > output_capacity)) {
        return false;
    }
    output[index++] = 0x04u;
    output[index++] = connect_flags;
    output[index++] = (uint8_t)(options->keepalive_s >> 8);
    output[index++] = (uint8_t)(options->keepalive_s & 0xFFu);

    if (!Bsp_Mqtt_Write_Utf8(output, output_capacity,
                             &index, options->client_id) ||
        !Bsp_Mqtt_Write_Utf8(output, output_capacity,
                             &index, options->will_topic) ||
        !Bsp_Mqtt_Write_Utf8(output, output_capacity,
                             &index, options->will_payload)) {
        return false;
    }
    if (has_username &&
        !Bsp_Mqtt_Write_Utf8(output, output_capacity,
                             &index, options->username)) {
        return false;
    }
    if (has_password &&
        !Bsp_Mqtt_Write_Utf8(output, output_capacity,
                             &index, options->password)) {
        return false;
    }

    return Bsp_Mqtt_Finalize(
        (uint8_t)(BSP_MQTT_PACKET_TYPE_CONNECT << 4),
        output,
        output_capacity,
        body_start,
        (uint16_t)(index - body_start),
        output_len);
}

bool Bsp_Mqtt_Build_Subscribe(uint16_t packet_id,
                              const char *topic,
                              uint8_t *output,
                              uint16_t output_capacity,
                              uint16_t *output_len)
{
    uint16_t index = 5u;
    uint16_t body_start = index;

    if ((packet_id == 0u) || (topic == NULL) || (topic[0] == '\0') ||
        (output == NULL) || (output_len == NULL) ||
        ((uint32_t)index + 2u > output_capacity)) {
        return false;
    }

    output[index++] = (uint8_t)(packet_id >> 8);
    output[index++] = (uint8_t)(packet_id & 0xFFu);
    if (!Bsp_Mqtt_Write_Utf8(output, output_capacity, &index, topic) ||
        (index >= output_capacity)) {
        return false;
    }
    output[index++] = 0x00u;

    return Bsp_Mqtt_Finalize(
        (uint8_t)((BSP_MQTT_PACKET_TYPE_SUBSCRIBE << 4) | 0x02u),
        output,
        output_capacity,
        body_start,
        (uint16_t)(index - body_start),
        output_len);
}

bool Bsp_Mqtt_Build_Publish(const char *topic,
                            const uint8_t *payload,
                            uint16_t payload_len,
                            bool retained,
                            uint8_t *output,
                            uint16_t output_capacity,
                            uint16_t *output_len)
{
    uint16_t index = 5u;
    uint16_t body_start = index;
    uint8_t fixed_header =
        (uint8_t)(BSP_MQTT_PACKET_TYPE_PUBLISH << 4);

    if ((topic == NULL) || (topic[0] == '\0') ||
        ((payload == NULL) && (payload_len > 0u)) ||
        (output == NULL) || (output_len == NULL)) {
        return false;
    }
    if (!Bsp_Mqtt_Write_Utf8(output, output_capacity, &index, topic) ||
        ((uint32_t)index + payload_len > output_capacity)) {
        return false;
    }
    if (payload_len > 0u) {
        memcpy(&output[index], payload, payload_len);
        index = (uint16_t)(index + payload_len);
    }
    if (retained) {
        fixed_header |= 0x01u;
    }

    return Bsp_Mqtt_Finalize(
        fixed_header,
        output,
        output_capacity,
        body_start,
        (uint16_t)(index - body_start),
        output_len);
}

bool Bsp_Mqtt_Build_Ping(uint8_t *output,
                         uint16_t output_capacity,
                         uint16_t *output_len)
{
    if ((output == NULL) || (output_len == NULL) ||
        (output_capacity < 2u)) {
        return false;
    }
    output[0] = (uint8_t)(BSP_MQTT_PACKET_TYPE_PINGREQ << 4);
    output[1] = 0u;
    *output_len = 2u;
    return true;
}

bool Bsp_Mqtt_Is_ConnAck_Accepted(const bsp_mqtt_packet_t *packet)
{
    return (packet != NULL) &&
           (packet->type == BSP_MQTT_PACKET_TYPE_CONNACK) &&
           (packet->flags == 0u) &&
           (packet->body_len == 2u) &&
           (packet->body[1] == 0u);
}

bool Bsp_Mqtt_Is_SubAck(const bsp_mqtt_packet_t *packet,
                        uint16_t expected_packet_id)
{
    uint16_t packet_id;

    if ((packet == NULL) ||
        (packet->type != BSP_MQTT_PACKET_TYPE_SUBACK) ||
        (packet->flags != 0u) ||
        (packet->body_len < 3u)) {
        return false;
    }
    packet_id = (uint16_t)(((uint16_t)packet->body[0] << 8) |
                           packet->body[1]);
    return (packet_id == expected_packet_id) &&
           (packet->body[2] != 0x80u);
}

bool Bsp_Mqtt_Decode_Publish(const bsp_mqtt_packet_t *packet,
                             const uint8_t **topic,
                             uint16_t *topic_len,
                             const uint8_t **payload,
                             uint16_t *payload_len,
                             uint8_t *qos)
{
    uint16_t index;
    uint16_t parsed_topic_len;
    uint8_t parsed_qos;

    if ((packet == NULL) || (topic == NULL) || (topic_len == NULL) ||
        (payload == NULL) || (payload_len == NULL) || (qos == NULL) ||
        (packet->type != BSP_MQTT_PACKET_TYPE_PUBLISH) ||
        (packet->body_len < 2u)) {
        return false;
    }

    parsed_topic_len =
        (uint16_t)(((uint16_t)packet->body[0] << 8) | packet->body[1]);
    index = 2u;
    if ((parsed_topic_len == 0u) ||
        ((uint32_t)index + parsed_topic_len > packet->body_len)) {
        return false;
    }
    *topic = &packet->body[index];
    *topic_len = parsed_topic_len;
    index = (uint16_t)(index + parsed_topic_len);

    parsed_qos = (uint8_t)((packet->flags >> 1) & 0x03u);
    if (parsed_qos > 0u) {
        if ((uint32_t)index + 2u > packet->body_len) {
            return false;
        }
        index = (uint16_t)(index + 2u);
    }
    *qos = parsed_qos;
    *payload = &packet->body[index];
    *payload_len = (uint16_t)(packet->body_len - index);
    return true;
}
