/**
 * @file    bsp_writer_protocol.h
 * @brief   Fixed-field writer V1 JSON command parser and CRC32 helpers.
 */
#ifndef BSP_WRITER_PROTOCOL_H
#define BSP_WRITER_PROTOCOL_H

#include <stdbool.h>
#include <stdint.h>

#define BSP_WRITER_ID_MAX          (32u)
#define BSP_WRITER_REQUEST_ID_MAX  (32u)
#define BSP_WRITER_GCODE_BUFFER_SIZE (192u)

typedef enum {
    BSP_WRITER_OP_NONE = 0,
    BSP_WRITER_OP_JOB_BEGIN,
    BSP_WRITER_OP_GCODE,
    BSP_WRITER_OP_JOB_END,
    BSP_WRITER_OP_STATUS,
    BSP_WRITER_OP_STOP,
    BSP_WRITER_OP_REHOME
} bsp_writer_operation_t;

typedef enum {
    BSP_WRITER_PARSE_OK = 0,
    BSP_WRITER_PARSE_BAD_JSON,
    BSP_WRITER_PARSE_BAD_VERSION,
    BSP_WRITER_PARSE_BAD_OPERATION,
    BSP_WRITER_PARSE_BAD_FIELD,
    BSP_WRITER_PARSE_BAD_ID,
    BSP_WRITER_PARSE_LINE_TOO_LONG,
    BSP_WRITER_PARSE_INVALID_GCODE
} bsp_writer_parse_result_t;

typedef struct {
    bsp_writer_operation_t operation;
    char job_id[BSP_WRITER_ID_MAX + 1u];
    char request_id[BSP_WRITER_REQUEST_ID_MAX + 1u];
    char line[BSP_WRITER_GCODE_BUFFER_SIZE];
    uint32_t total;
    uint32_t seq;
    uint32_t crc32;
} bsp_writer_command_t;

bsp_writer_parse_result_t Bsp_Writer_Parse_Command(
    const uint8_t *json,
    uint16_t json_len,
    bsp_writer_command_t *command);
const char *Bsp_Writer_Parse_Result_Name(bsp_writer_parse_result_t result);
bool Bsp_Writer_Id_Is_Valid(const char *id);

uint32_t Bsp_Writer_Crc32_Init(void);
uint32_t Bsp_Writer_Crc32_Update(uint32_t crc,
                                 const uint8_t *data,
                                 uint16_t len);
uint32_t Bsp_Writer_Crc32_Final(uint32_t crc);
void Bsp_Writer_Make_Boot_Id(uint32_t trace_id,
                             uint32_t boot_entropy,
                             char boot_id[9]);

#endif /* BSP_WRITER_PROTOCOL_H */
