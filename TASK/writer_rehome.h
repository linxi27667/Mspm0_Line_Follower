/**
 * @file    writer_rehome.h
 * @brief   Non-blocking runtime homing for cloud recovery.
 */
#ifndef WRITER_REHOME_H
#define WRITER_REHOME_H

#include <stdbool.h>

#define WRITER_REHOME_BUILD_ID \
    "NONBLOCKING_REHOME_DIR1_DIR1_GUARD165_152_V5"

typedef enum {
    WRITER_REHOME_STATE_IDLE = 0,
    WRITER_REHOME_STATE_PEN_SETTLE,
    WRITER_REHOME_STATE_INITIAL_RELEASE,
    WRITER_REHOME_STATE_INITIAL_CLEARANCE,
    WRITER_REHOME_STATE_FAST_SEARCH_DELAY,
    WRITER_REHOME_STATE_FAST_SEARCH,
    WRITER_REHOME_STATE_FAST_SETTLE,
    WRITER_REHOME_STATE_FAST_RELEASE,
    WRITER_REHOME_STATE_FAST_CLEARANCE,
    WRITER_REHOME_STATE_SLOW_SEARCH_DELAY,
    WRITER_REHOME_STATE_SLOW_SEARCH,
    WRITER_REHOME_STATE_SLOW_SETTLE,
    WRITER_REHOME_STATE_FINAL_RELEASE,
    WRITER_REHOME_STATE_FINAL_CLEARANCE,
    WRITER_REHOME_STATE_DONE,
    WRITER_REHOME_STATE_STOPPED,
    WRITER_REHOME_STATE_ERROR
} writer_rehome_state_t;

void WriterRehome_Init(void);
bool WriterRehome_Start(void);
void WriterRehome_Update(void);
void WriterRehome_Abort(void);
bool WriterRehome_Is_Active(void);
bool WriterRehome_Is_Succeeded(void);
bool WriterRehome_Is_Failed(void);
writer_rehome_state_t WriterRehome_Get_State(void);

#endif /* WRITER_REHOME_H */
