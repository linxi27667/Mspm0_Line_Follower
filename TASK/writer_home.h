/**
 * @file    writer_home.h
 * @brief   Writer robot initial homing task.
 */
#ifndef WRITER_HOME_H
#define WRITER_HOME_H

#include <stdbool.h>
#include <stdint.h>

#define WRITER_HOME_M700_BUILD_ID "AUTHOR_M700_HOME_CAL_GATED_V15"

typedef enum {
    WRITER_HOME_M700_STATE_IDLE = 0,
    WRITER_HOME_M700_STATE_WAIT_CAL,
    WRITER_HOME_M700_STATE_SEARCHING,
    WRITER_HOME_M700_STATE_LIMIT_SETTLE,
    WRITER_HOME_M700_STATE_RELEASING,
    WRITER_HOME_M700_STATE_CLEARANCE,
    WRITER_HOME_M700_STATE_REPEAT_DELAY,
    WRITER_HOME_M700_STATE_DONE,
    WRITER_HOME_M700_STATE_STOPPED,
    WRITER_HOME_M700_STATE_ERROR
} writer_home_m700_state_t;

bool WriterHome_InitialHome_Task(void);
void WriterHome_Absolute_Calibration_Task(void);
void WriterHome_M700_Start(void);
void WriterHome_M700_Update(void);
bool WriterHome_M700_Process_Frame(const uint8_t *frame, uint16_t len);
bool WriterHome_M700_Is_Done(void);
writer_home_m700_state_t WriterHome_M700_Get_State(void);

#endif /* WRITER_HOME_H */
