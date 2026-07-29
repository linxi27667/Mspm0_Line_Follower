/**
 * @file    bsp_esp_at.c
 * @brief   Streaming ESP-AT line and +IPD parser without hardware access.
 */
#include "bsp_esp_at.h"

#include <stddef.h>
#include <string.h>

static void Bsp_EspAt_Clear_Event(bsp_esp_at_event_t *event)
{
    event->type = BSP_ESP_AT_EVENT_NONE;
    event->line = NULL;
    event->line_len = 0u;
    event->ipd_len = 0u;
    event->data = 0u;
}

static bool Bsp_EspAt_Parse_Ipd_Length(const char *text,
                                       uint16_t len,
                                       uint32_t *ipd_len)
{
    uint16_t index;
    uint16_t digits_start;
    uint32_t value = 0u;

    if ((text == NULL) || (ipd_len == NULL) || (len < 7u) ||
        (memcmp(text, "+IPD,", 5u) != 0) || (text[len - 1u] != ':')) {
        return false;
    }

    digits_start = 5u;
    for (index = 5u; index < (uint16_t)(len - 1u); index++) {
        if (text[index] == ',') {
            digits_start = (uint16_t)(index + 1u);
        }
    }
    if (digits_start >= (uint16_t)(len - 1u)) {
        return false;
    }

    for (index = digits_start; index < (uint16_t)(len - 1u); index++) {
        uint8_t digit;

        if ((text[index] < '0') || (text[index] > '9')) {
            return false;
        }
        digit = (uint8_t)(text[index] - '0');
        if (value > ((UINT32_MAX - digit) / 10u)) {
            return false;
        }
        value = value * 10u + digit;
    }

    *ipd_len = value;
    return true;
}

void Bsp_EspAt_Init(bsp_esp_at_parser_t *parser)
{
    if (parser == NULL) {
        return;
    }

    parser->line[0] = '\0';
    parser->line_len = 0u;
    parser->ipd_remaining = 0u;
    parser->discard_line = false;
}

void Bsp_EspAt_Feed(bsp_esp_at_parser_t *parser,
                    uint8_t data,
                    bsp_esp_at_event_t *event)
{
    uint32_t ipd_len;

    if ((parser == NULL) || (event == NULL)) {
        return;
    }
    Bsp_EspAt_Clear_Event(event);

    if (parser->ipd_remaining > 0u) {
        parser->ipd_remaining--;
        event->type = BSP_ESP_AT_EVENT_IPD_DATA;
        event->data = data;
        return;
    }

    if (parser->discard_line) {
        if (data == '\n') {
            parser->discard_line = false;
            parser->line_len = 0u;
            parser->line[0] = '\0';
        }
        return;
    }

    if ((data == '>') && (parser->line_len == 0u)) {
        event->type = BSP_ESP_AT_EVENT_PROMPT;
        return;
    }
    if (data == '\r') {
        return;
    }
    if (data == '\n') {
        if (parser->line_len > 0u) {
            parser->line[parser->line_len] = '\0';
            event->type = BSP_ESP_AT_EVENT_LINE;
            event->line = parser->line;
            event->line_len = parser->line_len;
            parser->line_len = 0u;
        }
        return;
    }

    if (parser->line_len >= (uint16_t)(sizeof(parser->line) - 1u)) {
        parser->line_len = 0u;
        parser->line[0] = '\0';
        parser->discard_line = true;
        event->type = BSP_ESP_AT_EVENT_OVERFLOW;
        return;
    }

    parser->line[parser->line_len++] = (char)data;
    parser->line[parser->line_len] = '\0';

    if ((data == ':') &&
        Bsp_EspAt_Parse_Ipd_Length(parser->line,
                                   parser->line_len,
                                   &ipd_len)) {
        parser->line_len = 0u;
        parser->line[0] = '\0';
        parser->ipd_remaining = ipd_len;
        event->type = BSP_ESP_AT_EVENT_IPD_BEGIN;
        event->ipd_len = ipd_len;
    }
}
