/**
 * @file    center_reference_mark.h
 * @brief   Mark the corrected lower-left origin of a landscape A4 sheet.
 */
#ifndef CENTER_REFERENCE_MARK_H
#define CENTER_REFERENCE_MARK_H

#include <stdbool.h>

#define CENTER_REFERENCE_MARK_BUILD_ID \
    "KEY3_ORIGIN_PREKEY_KIN_KEYS_LIMIT135_255_F300_V5"

typedef enum {
    CENTER_REFERENCE_MARK_STATE_IDLE = 0,
    CENTER_REFERENCE_MARK_STATE_MOVING,
    CENTER_REFERENCE_MARK_STATE_DOWN_HOLD,
    CENTER_REFERENCE_MARK_STATE_UP_SETTLE,
    CENTER_REFERENCE_MARK_STATE_DONE,
    CENTER_REFERENCE_MARK_STATE_STOPPED,
    CENTER_REFERENCE_MARK_STATE_ERROR
} center_reference_mark_state_t;

bool CenterReferenceMark_Start(void);
void CenterReferenceMark_Update(void);
void CenterReferenceMark_Abort_For_Rehome(void);
bool CenterReferenceMark_Is_Done(void);
center_reference_mark_state_t CenterReferenceMark_Get_State(void);

#endif /* CENTER_REFERENCE_MARK_H */
