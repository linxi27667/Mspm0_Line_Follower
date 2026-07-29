/**
 * @file    bsp_esp_at.h
 * @brief   Streaming ESP-AT line and +IPD parser without hardware access.
 */
#ifndef BSP_ESP_AT_H
#define BSP_ESP_AT_H

#include <stdbool.h>
#include <stdint.h>

#define BSP_ESP_AT_LINE_MAX (128u)

typedef enum {
    BSP_ESP_AT_EVENT_NONE = 0,
    BSP_ESP_AT_EVENT_LINE,
    BSP_ESP_AT_EVENT_PROMPT,
    BSP_ESP_AT_EVENT_IPD_BEGIN,
    BSP_ESP_AT_EVENT_IPD_DATA,
    BSP_ESP_AT_EVENT_OVERFLOW
} bsp_esp_at_event_type_t;

typedef struct {
    bsp_esp_at_event_type_t type;
    const char *line;
    uint16_t line_len;
    uint32_t ipd_len;
    uint8_t data;
} bsp_esp_at_event_t;

typedef struct {
    char line[BSP_ESP_AT_LINE_MAX];
    uint16_t line_len;
    uint32_t ipd_remaining;
    bool discard_line;
} bsp_esp_at_parser_t;

void Bsp_EspAt_Init(bsp_esp_at_parser_t *parser);
void Bsp_EspAt_Feed(bsp_esp_at_parser_t *parser,
                    uint8_t data,
                    bsp_esp_at_event_t *event);

#endif /* BSP_ESP_AT_H */
