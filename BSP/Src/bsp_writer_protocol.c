/**
 * @file    bsp_writer_protocol.c
 * @brief   Fixed-field writer V1 JSON command parser and CRC32 helpers.
 */
#include "bsp_writer_protocol.h"

#include <ctype.h>
#include <stddef.h>
#include <string.h>

#define BSP_WRITER_FIELD_V          (1u << 0)
#define BSP_WRITER_FIELD_OP         (1u << 1)
#define BSP_WRITER_FIELD_JOB_ID     (1u << 2)
#define BSP_WRITER_FIELD_TOTAL      (1u << 3)
#define BSP_WRITER_FIELD_CRC32      (1u << 4)
#define BSP_WRITER_FIELD_SEQ        (1u << 5)
#define BSP_WRITER_FIELD_LINE       (1u << 6)
#define BSP_WRITER_FIELD_REQUEST_ID (1u << 7)

typedef struct {
    const uint8_t *json;
    uint16_t len;
    uint16_t index;
} bsp_writer_json_cursor_t;

static void Bsp_Writer_Skip_Space(bsp_writer_json_cursor_t *cursor)
{
    while ((cursor->index < cursor->len) &&
           isspace((int)cursor->json[cursor->index])) {
        cursor->index++;
    }
}

static bool Bsp_Writer_Parse_String(bsp_writer_json_cursor_t *cursor,
                                    char *output,
                                    uint16_t output_capacity,
                                    uint16_t *output_len)
{
    uint16_t count = 0u;

    if (output_len != NULL) {
        *output_len = 0u;
    }
    Bsp_Writer_Skip_Space(cursor);
    if ((cursor->index >= cursor->len) ||
        (cursor->json[cursor->index] != '"') ||
        (output == NULL) || (output_capacity == 0u)) {
        return false;
    }
    cursor->index++;

    while (cursor->index < cursor->len) {
        uint8_t value = cursor->json[cursor->index++];

        if (value == '"') {
            output[count] = '\0';
            if (output_len != NULL) {
                *output_len = count;
            }
            return true;
        }
        if ((value < 0x20u) || (value > 0x7Eu) || (value == '\\') ||
            (count >= (uint16_t)(output_capacity - 1u))) {
            if (output_len != NULL) {
                *output_len = count;
            }
            return false;
        }
        output[count++] = (char)value;
    }
    return false;
}

static bool Bsp_Writer_Parse_U32(bsp_writer_json_cursor_t *cursor,
                                 uint32_t *value)
{
    uint32_t parsed = 0u;
    bool has_digit = false;

    Bsp_Writer_Skip_Space(cursor);
    while (cursor->index < cursor->len) {
        uint8_t digit_char = cursor->json[cursor->index];
        uint8_t digit;

        if ((digit_char < '0') || (digit_char > '9')) {
            break;
        }
        has_digit = true;
        digit = (uint8_t)(digit_char - '0');
        if (parsed > ((UINT32_MAX - digit) / 10u)) {
            return false;
        }
        parsed = parsed * 10u + digit;
        cursor->index++;
    }
    if (!has_digit) {
        return false;
    }
    *value = parsed;
    return true;
}

static bool Bsp_Writer_Parse_Crc32(const char *text, uint32_t *crc32)
{
    uint16_t index;
    uint32_t value = 0u;

    if ((text == NULL) || (crc32 == NULL) || (strlen(text) != 8u)) {
        return false;
    }
    for (index = 0u; index < 8u; index++) {
        uint8_t digit;

        if ((text[index] >= '0') && (text[index] <= '9')) {
            digit = (uint8_t)(text[index] - '0');
        } else if ((text[index] >= 'A') && (text[index] <= 'F')) {
            digit = (uint8_t)(text[index] - 'A' + 10);
        } else if ((text[index] >= 'a') && (text[index] <= 'f')) {
            digit = (uint8_t)(text[index] - 'a' + 10);
        } else {
            return false;
        }
        value = (value << 4) | digit;
    }
    *crc32 = value;
    return true;
}

static bool Bsp_Writer_Gcode_Is_Valid(const char *line)
{
    uint16_t index;
    size_t len;

    if (line == NULL) {
        return false;
    }
    len = strlen(line);
    if ((len == 0u) || (len > (BSP_WRITER_GCODE_BUFFER_SIZE - 1u))) {
        return false;
    }
    for (index = 0u; index < (uint16_t)len; index++) {
        uint8_t value = (uint8_t)line[index];

        if ((value < 0x20u) || (value > 0x7Eu) ||
            (value == '"') || (value == '\\')) {
            return false;
        }
    }
    return true;
}

static bool Bsp_Writer_Field_Required(uint32_t fields,
                                      uint32_t required)
{
    return (fields & required) == required;
}

bsp_writer_parse_result_t Bsp_Writer_Parse_Command(
    const uint8_t *json,
    uint16_t json_len,
    bsp_writer_command_t *command)
{
    bsp_writer_json_cursor_t cursor;
    char key[16];
    char value[40];
    uint16_t string_len = 0u;
    uint32_t fields = 0u;
    uint32_t version = 0u;

    if ((json == NULL) || (json_len == 0u) || (command == NULL)) {
        return BSP_WRITER_PARSE_BAD_JSON;
    }
    memset(command, 0, sizeof(*command));
    cursor.json = json;
    cursor.len = json_len;
    cursor.index = 0u;

    Bsp_Writer_Skip_Space(&cursor);
    if ((cursor.index >= cursor.len) || (cursor.json[cursor.index] != '{')) {
        return BSP_WRITER_PARSE_BAD_JSON;
    }
    cursor.index++;

    for (;;) {
        uint32_t field_bit = 0u;

        Bsp_Writer_Skip_Space(&cursor);
        if (cursor.index >= cursor.len) {
            return BSP_WRITER_PARSE_BAD_JSON;
        }
        if (cursor.json[cursor.index] == '}') {
            cursor.index++;
            break;
        }
        if (!Bsp_Writer_Parse_String(&cursor, key, sizeof(key), NULL)) {
            return BSP_WRITER_PARSE_BAD_JSON;
        }
        Bsp_Writer_Skip_Space(&cursor);
        if ((cursor.index >= cursor.len) ||
            (cursor.json[cursor.index] != ':')) {
            return BSP_WRITER_PARSE_BAD_JSON;
        }
        cursor.index++;

        if (strcmp(key, "v") == 0) {
            field_bit = BSP_WRITER_FIELD_V;
            if (!Bsp_Writer_Parse_U32(&cursor, &version)) {
                return BSP_WRITER_PARSE_BAD_FIELD;
            }
        } else if (strcmp(key, "op") == 0) {
            field_bit = BSP_WRITER_FIELD_OP;
            if (!Bsp_Writer_Parse_String(&cursor, value,
                                         sizeof(value), NULL)) {
                return BSP_WRITER_PARSE_BAD_FIELD;
            }
            if (strcmp(value, "job_begin") == 0) {
                command->operation = BSP_WRITER_OP_JOB_BEGIN;
            } else if (strcmp(value, "gcode") == 0) {
                command->operation = BSP_WRITER_OP_GCODE;
            } else if (strcmp(value, "job_end") == 0) {
                command->operation = BSP_WRITER_OP_JOB_END;
            } else if (strcmp(value, "status") == 0) {
                command->operation = BSP_WRITER_OP_STATUS;
            } else if (strcmp(value, "stop") == 0) {
                command->operation = BSP_WRITER_OP_STOP;
            } else if (strcmp(value, "rehome") == 0) {
                command->operation = BSP_WRITER_OP_REHOME;
            } else {
                return BSP_WRITER_PARSE_BAD_OPERATION;
            }
        } else if (strcmp(key, "job_id") == 0) {
            field_bit = BSP_WRITER_FIELD_JOB_ID;
            if (!Bsp_Writer_Parse_String(&cursor, command->job_id,
                                         sizeof(command->job_id), NULL)) {
                return BSP_WRITER_PARSE_BAD_ID;
            }
        } else if (strcmp(key, "request_id") == 0) {
            field_bit = BSP_WRITER_FIELD_REQUEST_ID;
            if (!Bsp_Writer_Parse_String(&cursor, command->request_id,
                                         sizeof(command->request_id), NULL)) {
                return BSP_WRITER_PARSE_BAD_ID;
            }
        } else if (strcmp(key, "total") == 0) {
            field_bit = BSP_WRITER_FIELD_TOTAL;
            if (!Bsp_Writer_Parse_U32(&cursor, &command->total)) {
                return BSP_WRITER_PARSE_BAD_FIELD;
            }
        } else if (strcmp(key, "seq") == 0) {
            field_bit = BSP_WRITER_FIELD_SEQ;
            if (!Bsp_Writer_Parse_U32(&cursor, &command->seq)) {
                return BSP_WRITER_PARSE_BAD_FIELD;
            }
        } else if (strcmp(key, "crc32") == 0) {
            field_bit = BSP_WRITER_FIELD_CRC32;
            if (!Bsp_Writer_Parse_String(&cursor, value,
                                         sizeof(value), NULL) ||
                !Bsp_Writer_Parse_Crc32(value, &command->crc32)) {
                return BSP_WRITER_PARSE_BAD_FIELD;
            }
        } else if (strcmp(key, "line") == 0) {
            field_bit = BSP_WRITER_FIELD_LINE;
            if (!Bsp_Writer_Parse_String(&cursor, command->line,
                                         sizeof(command->line),
                                         &string_len)) {
                if (string_len >=
                    (BSP_WRITER_GCODE_BUFFER_SIZE - 1u)) {
                    return BSP_WRITER_PARSE_LINE_TOO_LONG;
                }
                return BSP_WRITER_PARSE_INVALID_GCODE;
            }
        } else {
            return BSP_WRITER_PARSE_BAD_FIELD;
        }

        if ((fields & field_bit) != 0u) {
            return BSP_WRITER_PARSE_BAD_FIELD;
        }
        fields |= field_bit;

        Bsp_Writer_Skip_Space(&cursor);
        if (cursor.index >= cursor.len) {
            return BSP_WRITER_PARSE_BAD_JSON;
        }
        if (cursor.json[cursor.index] == ',') {
            cursor.index++;
            continue;
        }
        if (cursor.json[cursor.index] == '}') {
            cursor.index++;
            break;
        }
        return BSP_WRITER_PARSE_BAD_JSON;
    }

    Bsp_Writer_Skip_Space(&cursor);
    if (cursor.index != cursor.len) {
        return BSP_WRITER_PARSE_BAD_JSON;
    }
    if (!Bsp_Writer_Field_Required(
            fields, BSP_WRITER_FIELD_V | BSP_WRITER_FIELD_OP)) {
        return BSP_WRITER_PARSE_BAD_FIELD;
    }
    if (version != 1u) {
        return BSP_WRITER_PARSE_BAD_VERSION;
    }

    switch (command->operation) {
        case BSP_WRITER_OP_NONE:
            return BSP_WRITER_PARSE_BAD_OPERATION;

        case BSP_WRITER_OP_JOB_BEGIN:
        case BSP_WRITER_OP_JOB_END:
            if (!Bsp_Writer_Field_Required(
                    fields,
                    BSP_WRITER_FIELD_JOB_ID |
                    BSP_WRITER_FIELD_TOTAL |
                    BSP_WRITER_FIELD_CRC32)) {
                return BSP_WRITER_PARSE_BAD_FIELD;
            }
            if ((fields & ~(BSP_WRITER_FIELD_V |
                            BSP_WRITER_FIELD_OP |
                            BSP_WRITER_FIELD_JOB_ID |
                            BSP_WRITER_FIELD_TOTAL |
                            BSP_WRITER_FIELD_CRC32)) != 0u) {
                return BSP_WRITER_PARSE_BAD_FIELD;
            }
            break;

        case BSP_WRITER_OP_GCODE:
            if (!Bsp_Writer_Field_Required(
                    fields,
                    BSP_WRITER_FIELD_JOB_ID |
                    BSP_WRITER_FIELD_SEQ |
                    BSP_WRITER_FIELD_LINE)) {
                return BSP_WRITER_PARSE_BAD_FIELD;
            }
            if ((fields & ~(BSP_WRITER_FIELD_V |
                            BSP_WRITER_FIELD_OP |
                            BSP_WRITER_FIELD_JOB_ID |
                            BSP_WRITER_FIELD_SEQ |
                            BSP_WRITER_FIELD_LINE)) != 0u) {
                return BSP_WRITER_PARSE_BAD_FIELD;
            }
            if (!Bsp_Writer_Gcode_Is_Valid(command->line)) {
                return BSP_WRITER_PARSE_INVALID_GCODE;
            }
            break;

        case BSP_WRITER_OP_STATUS:
        case BSP_WRITER_OP_STOP:
        case BSP_WRITER_OP_REHOME:
            if (!Bsp_Writer_Field_Required(
                    fields, BSP_WRITER_FIELD_REQUEST_ID)) {
                return BSP_WRITER_PARSE_BAD_FIELD;
            }
            if ((fields & ~(BSP_WRITER_FIELD_V |
                            BSP_WRITER_FIELD_OP |
                            BSP_WRITER_FIELD_REQUEST_ID)) != 0u) {
                return BSP_WRITER_PARSE_BAD_FIELD;
            }
            break;

        default:
            return BSP_WRITER_PARSE_BAD_OPERATION;
    }

    if (((fields & BSP_WRITER_FIELD_JOB_ID) != 0u) &&
        !Bsp_Writer_Id_Is_Valid(command->job_id)) {
        return BSP_WRITER_PARSE_BAD_ID;
    }
    if (((fields & BSP_WRITER_FIELD_REQUEST_ID) != 0u) &&
        !Bsp_Writer_Id_Is_Valid(command->request_id)) {
        return BSP_WRITER_PARSE_BAD_ID;
    }
    return BSP_WRITER_PARSE_OK;
}

const char *Bsp_Writer_Parse_Result_Name(bsp_writer_parse_result_t result)
{
    switch (result) {
        case BSP_WRITER_PARSE_OK:
            return "ok";
        case BSP_WRITER_PARSE_BAD_JSON:
            return "bad_json";
        case BSP_WRITER_PARSE_BAD_VERSION:
            return "bad_version";
        case BSP_WRITER_PARSE_BAD_OPERATION:
            return "bad_operation";
        case BSP_WRITER_PARSE_BAD_ID:
            return "bad_job_id";
        case BSP_WRITER_PARSE_LINE_TOO_LONG:
            return "line_too_long";
        case BSP_WRITER_PARSE_INVALID_GCODE:
            return "invalid_gcode_chars";
        case BSP_WRITER_PARSE_BAD_FIELD:
        default:
            return "bad_json";
    }
}

bool Bsp_Writer_Id_Is_Valid(const char *id)
{
    uint16_t index;
    size_t len;

    if (id == NULL) {
        return false;
    }
    len = strlen(id);
    if ((len == 0u) || (len > BSP_WRITER_ID_MAX)) {
        return false;
    }
    for (index = 0u; index < (uint16_t)len; index++) {
        char value = id[index];

        if (!(((value >= 'A') && (value <= 'Z')) ||
              ((value >= 'a') && (value <= 'z')) ||
              ((value >= '0') && (value <= '9')) ||
              (value == '_') || (value == '-'))) {
            return false;
        }
    }
    return true;
}

uint32_t Bsp_Writer_Crc32_Init(void)
{
    return 0xFFFFFFFFu;
}

uint32_t Bsp_Writer_Crc32_Update(uint32_t crc,
                                 const uint8_t *data,
                                 uint16_t len)
{
    uint16_t index;

    if ((data == NULL) && (len > 0u)) {
        return crc;
    }
    for (index = 0u; index < len; index++) {
        uint8_t bit;

        crc ^= data[index];
        for (bit = 0u; bit < 8u; bit++) {
            uint32_t mask = (uint32_t)(-(int32_t)(crc & 1u));
            crc = (crc >> 1) ^ (0xEDB88320u & mask);
        }
    }
    return crc;
}

uint32_t Bsp_Writer_Crc32_Final(uint32_t crc)
{
    return crc ^ 0xFFFFFFFFu;
}

void Bsp_Writer_Make_Boot_Id(uint32_t trace_id,
                             uint32_t boot_entropy,
                             char boot_id[9])
{
    static const char hex[] = "0123456789ABCDEF";
    uint32_t value;
    uint8_t index;

    if (boot_id == NULL) {
        return;
    }
    value = trace_id ^ (boot_entropy * 2654435761u);
    value ^= value << 13;
    value ^= value >> 17;
    value ^= value << 5;
    for (index = 0u; index < 8u; index++) {
        uint8_t shift = (uint8_t)((7u - index) * 4u);
        boot_id[index] = hex[(value >> shift) & 0x0Fu];
    }
    boot_id[8] = '\0';
}
