/**
 * @file writer_cloud.h
 * @brief Non-blocking ESP-01S/MQTT writer task.
 */
#ifndef WRITER_CLOUD_H
#define WRITER_CLOUD_H

#include <stdbool.h>

void WriterCloud_Init(bool homed);
void WriterCloud_Update(void);
bool WriterCloud_Is_Enabled(void);
bool WriterCloud_Is_Online(void);
bool WriterCloud_Needs_Rehome(void);
const char *WriterCloud_Get_Boot_Id(void);

#endif /* WRITER_CLOUD_H */
