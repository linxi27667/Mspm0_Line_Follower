/**
 * @file    gcode_serial.c
 * @brief   One-command-at-a-time G-code execution for the official host.
 */
#include "gcode_serial.h"
#include "app_servo.h"
#include "app_stepper.h"
#include "app_writer_motion.h"
#include "app_writer_paper_map.h"
#include "comm_vision_uart.h"
#include "elog.h"
#include <ctype.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define GCODE_SERIAL_LINE_MAX              (192u)
#define GCODE_SERIAL_PEN_SETTLE_MS         (700u)
#define GCODE_SERIAL_POSITION_EPSILON_MM   (0.08f)
#define GCODE_SERIAL_DWELL_MAX_MS          (60000u)
#define GCODE_SERIAL_DEFAULT_FEED_MM_MIN   (600.0f)

typedef enum {
    GCODE_SERIAL_STATE_IDLE = 0,
    GCODE_SERIAL_STATE_WAIT_MOTION,
    GCODE_SERIAL_STATE_WAIT_SYNC_PEN,
    GCODE_SERIAL_STATE_WAIT_PEN,
    GCODE_SERIAL_STATE_WAIT_SYNC_DWELL,
    GCODE_SERIAL_STATE_WAIT_DWELL
} gcode_serial_state_t;

typedef struct {
    bool has_g;
    bool has_m;
    bool has_x;
    bool has_y;
    bool has_z;
    bool has_f;
    bool has_s;
    bool has_p;
    int32_t g_code;
    int32_t m_code;
    float x;
    float y;
    float z;
    float feed;
    float power;
    float dwell_s;
} gcode_serial_line_t;

#if GCODE_SERIAL_RESTRICTED_RECT_ENABLE
#if GCODE_SERIAL_RECT_CCW_ENABLE
#define GCODE_SERIAL_RECT_DIRECTION_TEXT "CCW"
#else
#define GCODE_SERIAL_RECT_DIRECTION_TEXT "CW"
#endif

typedef enum {
    GCODE_SERIAL_RECT_PHASE_WAIT_APPROACH = 0,
    GCODE_SERIAL_RECT_PHASE_WAIT_DRAW,
    GCODE_SERIAL_RECT_PHASE_EDGE_LEFT,
    GCODE_SERIAL_RECT_PHASE_EDGE_TOP,
    GCODE_SERIAL_RECT_PHASE_EDGE_RIGHT,
    GCODE_SERIAL_RECT_PHASE_EDGE_BOTTOM,
    GCODE_SERIAL_RECT_PHASE_WAIT_PEN_UP,
    GCODE_SERIAL_RECT_PHASE_COMPLETE,
    GCODE_SERIAL_RECT_PHASE_ABORTED
} gcode_serial_rect_phase_t;
#endif

extern volatile uint32_t s_sys_tick;

static gcode_serial_state_t s_state = GCODE_SERIAL_STATE_IDLE;
static bool s_absolute_mode = true;
static bool s_pen_is_down = false;
static bool s_work_origin_valid = false;
static bool s_source_position_valid = false;
static float s_work_origin_x = 0.0f;
static float s_work_origin_y = 0.0f;
static float s_source_x = 0.0f;
static float s_source_y = 0.0f;
static float s_pending_source_x = 0.0f;
static float s_pending_source_y = 0.0f;
static float s_motion_start_x = 0.0f;
static float s_motion_start_y = 0.0f;
static float s_motion_target_x = 0.0f;
static float s_motion_target_y = 0.0f;
static float s_motion_source_start_x = 0.0f;
static float s_motion_source_start_y = 0.0f;
static float s_motion_source_target_x = 0.0f;
static float s_motion_source_target_y = 0.0f;
static float s_segment_target_x = 0.0f;
static float s_segment_target_y = 0.0f;
static float s_feed_mm_min = 0.0f;
static float s_power = 0.0f;
static uint32_t s_motion_segment_count = 0u;
static uint32_t s_motion_segment_index = 0u;
static uint32_t s_wait_start_ms = 0u;
static uint32_t s_wait_duration_ms = 0u;
static uint32_t s_received_count = 0u;
static uint32_t s_completed_count = 0u;
static int32_t s_modal_motion = 0;
static int32_t s_active_motion = 0;
static int32_t s_pending_m_code = 0;
static gcode_serial_result_callback_t s_result_callback = NULL;
static void *s_result_context = NULL;
#if GCODE_SERIAL_RESTRICTED_RECT_ENABLE
static gcode_serial_rect_phase_t s_rect_phase =
    GCODE_SERIAL_RECT_PHASE_WAIT_APPROACH;
static gcode_serial_rect_phase_t s_rect_pending_phase =
    GCODE_SERIAL_RECT_PHASE_WAIT_APPROACH;
#endif

static void GCodeSerial_Send_Text(const char *text)
{
    if (s_result_callback == NULL) {
        App_Vision_UART_Send(
            (const uint8_t *)text, (uint16_t)strlen(text));
    }
}

static void GCodeSerial_Send_Ok(void)
{
    s_completed_count++;
    if (s_result_callback != NULL) {
        s_result_callback(true, NULL, s_result_context);
    } else {
        GCodeSerial_Send_Text("ok\r\n");
    }
}

static void GCodeSerial_Send_Error(const char *reason)
{
    App_Servo_Pen_Up();
    s_pen_is_down = false;
    WriterMotion_Emergency_Stop();
    s_state = GCODE_SERIAL_STATE_IDLE;
#if GCODE_SERIAL_RESTRICTED_RECT_ENABLE
    s_rect_phase = GCODE_SERIAL_RECT_PHASE_ABORTED;
    s_rect_pending_phase = GCODE_SERIAL_RECT_PHASE_ABORTED;
#endif
    if (s_result_callback != NULL) {
        s_result_callback(false, reason, s_result_context);
    } else {
        GCodeSerial_Send_Text("error:");
        GCodeSerial_Send_Text(reason);
        GCodeSerial_Send_Text("\r\n");
    }
    elog_e("GCODE_RX", "[GCODE_RX] error=%s received=%u completed=%u",
           reason, s_received_count, s_completed_count);
}

static int32_t GCodeSerial_Scale_100(float value)
{
    return (int32_t)((value >= 0.0f) ?
                     (value * 100.0f + 0.5f) :
                     (value * 100.0f - 0.5f));
}

static float GCodeSerial_Abs(float value)
{
    return (value >= 0.0f) ? value : -value;
}

static bool GCodeSerial_Paper_To_User(float paper_x_mm,
                                      float paper_y_mm,
                                      float *user_x_mm,
                                      float *user_y_mm)
{
    bool mapped;

    if ((user_x_mm == 0) || (user_y_mm == 0)) {
        return false;
    }

#if GCODE_SERIAL_PAPER_MAP_ENABLE
    mapped = WriterPaperMap_To_User(paper_x_mm, paper_y_mm,
                                    user_x_mm, user_y_mm);
#else
    *user_x_mm = paper_x_mm;
    *user_y_mm = paper_y_mm;
    mapped = true;
#endif

    if (!mapped) {
        return false;
    }
    *user_x_mm += GCODE_SERIAL_WORKSPACE_SHIFT_X_MM;
    *user_y_mm += GCODE_SERIAL_WORKSPACE_SHIFT_Y_MM;
    return true;
}

static const char *GCodeSerial_Paper_Map_Quality(float paper_y_mm)
{
    return ((paper_y_mm >= APP_WRITER_PAPER_CALIBRATED_Y_MIN_MM) &&
            (paper_y_mm <= APP_WRITER_PAPER_CALIBRATED_Y_MAX_MM)) ?
           "CALIBRATED" : "EXTRAPOLATED";
}

#if GCODE_SERIAL_RESTRICTED_RECT_ENABLE
static const char *GCodeSerial_Rect_Phase_Name(void)
{
    switch (s_rect_phase) {
        case GCODE_SERIAL_RECT_PHASE_WAIT_APPROACH:
            return "WAIT_APPROACH";
        case GCODE_SERIAL_RECT_PHASE_WAIT_DRAW:
            return "WAIT_DRAW";
        case GCODE_SERIAL_RECT_PHASE_EDGE_LEFT:
            return "EDGE_LEFT";
        case GCODE_SERIAL_RECT_PHASE_EDGE_TOP:
            return "EDGE_TOP";
        case GCODE_SERIAL_RECT_PHASE_EDGE_RIGHT:
            return "EDGE_RIGHT";
        case GCODE_SERIAL_RECT_PHASE_EDGE_BOTTOM:
            return "EDGE_BOTTOM";
        case GCODE_SERIAL_RECT_PHASE_WAIT_PEN_UP:
            return "WAIT_PEN_UP";
        case GCODE_SERIAL_RECT_PHASE_COMPLETE:
            return "COMPLETE";
        case GCODE_SERIAL_RECT_PHASE_ABORTED:
            return "ABORTED";
        default:
            return "UNKNOWN";
    }
}

static bool GCodeSerial_Rect_Near(float value, float expected)
{
    return GCodeSerial_Abs(value - expected) <= 0.002f;
}

static bool GCodeSerial_Rect_Setup_Allowed(void)
{
    return s_rect_phase == GCODE_SERIAL_RECT_PHASE_WAIT_APPROACH;
}

static const char *GCodeSerial_Rect_Validate_Target(
    int32_t motion_code, gcode_serial_rect_phase_t *next_phase)
{
    float delta;

    if (next_phase == 0) {
        return "restricted_internal_phase";
    }
    *next_phase = s_rect_phase;

    if (motion_code == 0) {
        if ((s_rect_phase != GCODE_SERIAL_RECT_PHASE_WAIT_APPROACH) ||
            s_pen_is_down ||
            !GCodeSerial_Rect_Near(s_motion_target_x,
                                   GCODE_SERIAL_RECT_X0_MM) ||
            !GCodeSerial_Rect_Near(s_motion_target_y,
                                   GCODE_SERIAL_RECT_Y0_MM)) {
            return "restricted_rapid_target";
        }
        *next_phase = GCODE_SERIAL_RECT_PHASE_WAIT_DRAW;
        return 0;
    }

    if (motion_code != 1) {
        return "restricted_motion_code";
    }

    switch (s_rect_phase) {
        case GCODE_SERIAL_RECT_PHASE_EDGE_LEFT:
#if GCODE_SERIAL_RECT_CCW_ENABLE
            delta = s_motion_start_y - s_motion_target_y;
            if (!GCodeSerial_Rect_Near(s_motion_start_x,
                                       GCODE_SERIAL_RECT_X0_MM) ||
                !GCodeSerial_Rect_Near(s_motion_target_x,
                                       GCODE_SERIAL_RECT_X0_MM) ||
                (delta <= 0.002f) ||
                (delta > GCODE_SERIAL_RECT_POINT_STEP_MAX_MM) ||
                (s_motion_target_y < GCODE_SERIAL_RECT_Y0_MM - 0.002f)) {
                return "restricted_left_edge";
            }
            if (GCodeSerial_Rect_Near(s_motion_target_y,
                                      GCODE_SERIAL_RECT_Y0_MM)) {
                *next_phase = GCODE_SERIAL_RECT_PHASE_WAIT_PEN_UP;
            }
#else
            delta = s_motion_target_y - s_motion_start_y;
            if (!GCodeSerial_Rect_Near(s_motion_start_x,
                                       GCODE_SERIAL_RECT_X0_MM) ||
                !GCodeSerial_Rect_Near(s_motion_target_x,
                                       GCODE_SERIAL_RECT_X0_MM) ||
                (delta <= 0.002f) ||
                (delta > GCODE_SERIAL_RECT_POINT_STEP_MAX_MM) ||
                (s_motion_target_y > GCODE_SERIAL_RECT_Y1_MM + 0.002f)) {
                return "restricted_left_edge";
            }
            if (GCodeSerial_Rect_Near(s_motion_target_y,
                                      GCODE_SERIAL_RECT_Y1_MM)) {
                *next_phase = GCODE_SERIAL_RECT_PHASE_EDGE_TOP;
            }
#endif
            return 0;

        case GCODE_SERIAL_RECT_PHASE_EDGE_TOP:
#if GCODE_SERIAL_RECT_CCW_ENABLE
            delta = s_motion_start_x - s_motion_target_x;
            if (!GCodeSerial_Rect_Near(s_motion_start_y,
                                       GCODE_SERIAL_RECT_Y1_MM) ||
                !GCodeSerial_Rect_Near(s_motion_target_y,
                                       GCODE_SERIAL_RECT_Y1_MM) ||
                (delta <= 0.002f) ||
                (delta > GCODE_SERIAL_RECT_POINT_STEP_MAX_MM) ||
                (s_motion_target_x < GCODE_SERIAL_RECT_X0_MM - 0.002f)) {
                return "restricted_top_edge";
            }
            if (GCodeSerial_Rect_Near(s_motion_target_x,
                                      GCODE_SERIAL_RECT_X0_MM)) {
                *next_phase = GCODE_SERIAL_RECT_PHASE_EDGE_LEFT;
            }
#else
            delta = s_motion_target_x - s_motion_start_x;
            if (!GCodeSerial_Rect_Near(s_motion_start_y,
                                       GCODE_SERIAL_RECT_Y1_MM) ||
                !GCodeSerial_Rect_Near(s_motion_target_y,
                                       GCODE_SERIAL_RECT_Y1_MM) ||
                (delta <= 0.002f) ||
                (delta > GCODE_SERIAL_RECT_POINT_STEP_MAX_MM) ||
                (s_motion_target_x > GCODE_SERIAL_RECT_X1_MM + 0.002f)) {
                return "restricted_top_edge";
            }
            if (GCodeSerial_Rect_Near(s_motion_target_x,
                                      GCODE_SERIAL_RECT_X1_MM)) {
                *next_phase = GCODE_SERIAL_RECT_PHASE_EDGE_RIGHT;
            }
#endif
            return 0;

        case GCODE_SERIAL_RECT_PHASE_EDGE_RIGHT:
#if GCODE_SERIAL_RECT_CCW_ENABLE
            delta = s_motion_target_y - s_motion_start_y;
            if (!GCodeSerial_Rect_Near(s_motion_start_x,
                                       GCODE_SERIAL_RECT_X1_MM) ||
                !GCodeSerial_Rect_Near(s_motion_target_x,
                                       GCODE_SERIAL_RECT_X1_MM) ||
                (delta <= 0.002f) ||
                (delta > GCODE_SERIAL_RECT_POINT_STEP_MAX_MM) ||
                (s_motion_target_y > GCODE_SERIAL_RECT_Y1_MM + 0.002f)) {
                return "restricted_right_edge";
            }
            if (GCodeSerial_Rect_Near(s_motion_target_y,
                                      GCODE_SERIAL_RECT_Y1_MM)) {
                *next_phase = GCODE_SERIAL_RECT_PHASE_EDGE_TOP;
            }
#else
            delta = s_motion_start_y - s_motion_target_y;
            if (!GCodeSerial_Rect_Near(s_motion_start_x,
                                       GCODE_SERIAL_RECT_X1_MM) ||
                !GCodeSerial_Rect_Near(s_motion_target_x,
                                       GCODE_SERIAL_RECT_X1_MM) ||
                (delta <= 0.002f) ||
                (delta > GCODE_SERIAL_RECT_POINT_STEP_MAX_MM) ||
                (s_motion_target_y < GCODE_SERIAL_RECT_Y0_MM - 0.002f)) {
                return "restricted_right_edge";
            }
            if (GCodeSerial_Rect_Near(s_motion_target_y,
                                      GCODE_SERIAL_RECT_Y0_MM)) {
                *next_phase = GCODE_SERIAL_RECT_PHASE_EDGE_BOTTOM;
            }
#endif
            return 0;

        case GCODE_SERIAL_RECT_PHASE_EDGE_BOTTOM:
#if GCODE_SERIAL_RECT_CCW_ENABLE
            delta = s_motion_target_x - s_motion_start_x;
            if (!GCodeSerial_Rect_Near(s_motion_start_y,
                                       GCODE_SERIAL_RECT_Y0_MM) ||
                !GCodeSerial_Rect_Near(s_motion_target_y,
                                       GCODE_SERIAL_RECT_Y0_MM) ||
                (delta <= 0.002f) ||
                (delta > GCODE_SERIAL_RECT_POINT_STEP_MAX_MM) ||
                (s_motion_target_x > GCODE_SERIAL_RECT_X1_MM + 0.002f)) {
                return "restricted_bottom_edge";
            }
            if (GCodeSerial_Rect_Near(s_motion_target_x,
                                      GCODE_SERIAL_RECT_X1_MM)) {
                *next_phase = GCODE_SERIAL_RECT_PHASE_EDGE_RIGHT;
            }
#else
            delta = s_motion_start_x - s_motion_target_x;
            if (!GCodeSerial_Rect_Near(s_motion_start_y,
                                       GCODE_SERIAL_RECT_Y0_MM) ||
                !GCodeSerial_Rect_Near(s_motion_target_y,
                                       GCODE_SERIAL_RECT_Y0_MM) ||
                (delta <= 0.002f) ||
                (delta > GCODE_SERIAL_RECT_POINT_STEP_MAX_MM) ||
                (s_motion_target_x < GCODE_SERIAL_RECT_X0_MM - 0.002f)) {
                return "restricted_bottom_edge";
            }
            if (GCodeSerial_Rect_Near(s_motion_target_x,
                                      GCODE_SERIAL_RECT_X0_MM)) {
                *next_phase = GCODE_SERIAL_RECT_PHASE_WAIT_PEN_UP;
            }
#endif
            return 0;

        case GCODE_SERIAL_RECT_PHASE_WAIT_APPROACH:
        case GCODE_SERIAL_RECT_PHASE_WAIT_DRAW:
        case GCODE_SERIAL_RECT_PHASE_WAIT_PEN_UP:
        case GCODE_SERIAL_RECT_PHASE_COMPLETE:
        case GCODE_SERIAL_RECT_PHASE_ABORTED:
            return "restricted_sequence";

        default:
            return "restricted_bad_phase";
    }
}
#endif

static const char *GCodeSerial_Skip_Space(const char *cursor)
{
    while ((*cursor != '\0') && isspace((unsigned char)*cursor)) {
        cursor++;
    }
    return cursor;
}

static bool GCodeSerial_Parse_Integer(float value, int32_t *result)
{
    int32_t rounded = (int32_t)lroundf(value);

    if (fabsf(value - (float)rounded) > 0.001f) {
        return false;
    }
    *result = rounded;
    return true;
}

static bool GCodeSerial_Parse_Number(const char **cursor, float *value)
{
    const char *start;
    const char *scan;
    char number_text[48];
    char *end;
    size_t length;
    bool has_digit = false;

    if ((cursor == 0) || (*cursor == 0) || (value == 0)) {
        return false;
    }

    start = *cursor;
    scan = start;
    if ((*scan == '+') || (*scan == '-')) {
        scan++;
    }
    while (isdigit((unsigned char)*scan)) {
        has_digit = true;
        scan++;
    }
    if (*scan == '.') {
        scan++;
        while (isdigit((unsigned char)*scan)) {
            has_digit = true;
            scan++;
        }
    }
    if (!has_digit) {
        return false;
    }
    if ((*scan == 'e') || (*scan == 'E')) {
        const char *exponent = scan++;
        bool has_exponent_digit = false;

        if ((*scan == '+') || (*scan == '-')) {
            scan++;
        }
        while (isdigit((unsigned char)*scan)) {
            has_exponent_digit = true;
            scan++;
        }
        if (!has_exponent_digit) {
            scan = exponent;
        }
    }

    length = (size_t)(scan - start);
    if ((length == 0u) || (length >= sizeof(number_text))) {
        return false;
    }
    memcpy(number_text, start, length);
    number_text[length] = '\0';
    *value = strtof(number_text, &end);
    if ((end == number_text) || (*end != '\0')) {
        return false;
    }
    *cursor = scan;
    return true;
}

static bool GCodeSerial_Parse_Line(const char *text,
                                   gcode_serial_line_t *line)
{
    const char *cursor = text;

    if ((text == 0) || (line == 0)) {
        return false;
    }

    *line = (gcode_serial_line_t){0};
    while (true) {
        char letter;
        float value;

        cursor = GCodeSerial_Skip_Space(cursor);
        if ((*cursor == '\0') || (*cursor == ';')) {
            return true;
        }
        if (*cursor == '(') {
            while ((*cursor != '\0') && (*cursor != ')')) {
                cursor++;
            }
            if (*cursor != ')') {
                return false;
            }
            cursor++;
            continue;
        }

        letter = (char)toupper((unsigned char)*cursor);
        cursor++;
        if (!GCodeSerial_Parse_Number(&cursor, &value)) {
            return false;
        }

        switch (letter) {
            case 'G':
                if (line->has_g ||
                    !GCodeSerial_Parse_Integer(value, &line->g_code)) {
                    return false;
                }
                line->has_g = true;
                break;

            case 'M':
                if (line->has_m ||
                    !GCodeSerial_Parse_Integer(value, &line->m_code)) {
                    return false;
                }
                line->has_m = true;
                break;

            case 'X':
                if (line->has_x) {
                    return false;
                }
                line->has_x = true;
                line->x = value;
                break;

            case 'Y':
                if (line->has_y) {
                    return false;
                }
                line->has_y = true;
                line->y = value;
                break;

            case 'Z':
                if (line->has_z) {
                    return false;
                }
                line->has_z = true;
                line->z = value;
                break;

            case 'F':
                if (line->has_f) {
                    return false;
                }
                line->has_f = true;
                line->feed = value;
                break;

            case 'S':
                if (line->has_s) {
                    return false;
                }
                line->has_s = true;
                line->power = value;
                break;

            case 'P':
                if (line->has_p) {
                    return false;
                }
                line->has_p = true;
                line->dwell_s = value;
                break;

            default:
                return false;
        }
    }
}

static void GCodeSerial_Reset_Source_Coordinates(void)
{
#if GCODE_SERIAL_USE_FIXED_SOURCE_ORIGIN
    s_work_origin_valid = true;
    s_work_origin_x = GCODE_SERIAL_SOURCE_ORIGIN_X_MM;
    s_work_origin_y = GCODE_SERIAL_SOURCE_ORIGIN_Y_MM;
#else
    s_work_origin_valid = false;
    s_work_origin_x = 0.0f;
    s_work_origin_y = 0.0f;
#endif
    s_source_x = 0.0f;
    s_source_y = 0.0f;
    s_pending_source_x = 0.0f;
    s_pending_source_y = 0.0f;
    s_source_position_valid = false;
}

#if GCODE_SERIAL_RESTRICTED_RECT_ENABLE
static bool GCodeSerial_Is_At(float x_mm, float y_mm)
{
    const app_writer_pose_t *pose = WriterMotion_Get_Pose();

    return (fabsf(pose->user_point.x_mm - x_mm) <=
            GCODE_SERIAL_POSITION_EPSILON_MM) &&
           (fabsf(pose->user_point.y_mm - y_mm) <=
            GCODE_SERIAL_POSITION_EPSILON_MM);
}
#endif

static app_writer_queue_result_t
GCodeSerial_Queue_Next_Motion_Segment(void)
{
    float ratio;
    uint32_t next_segment_index;
    app_writer_queue_result_t result;

    if (s_motion_segment_index >= s_motion_segment_count) {
        return APP_WRITER_QUEUE_REJECTED;
    }

    next_segment_index = s_motion_segment_index + 1u;
    ratio = (float)next_segment_index /
            (float)s_motion_segment_count;
    if (s_active_motion == 1) {
        float paper_x = s_motion_source_start_x +
            (s_motion_source_target_x - s_motion_source_start_x) * ratio;
        float paper_y = s_motion_source_start_y +
            (s_motion_source_target_y - s_motion_source_start_y) * ratio;

        if (!GCodeSerial_Paper_To_User(
                paper_x, paper_y,
                &s_segment_target_x, &s_segment_target_y)) {
            return APP_WRITER_QUEUE_REJECTED;
        }
    } else {
        s_segment_target_x = s_motion_start_x +
            (s_motion_target_x - s_motion_start_x) * ratio;
        s_segment_target_y = s_motion_start_y +
            (s_motion_target_y - s_motion_start_y) * ratio;
    }

    elog_i("GCODE_RX", "[GCODE_RX] move segment=%u/%u x=%d y=%d",
           next_segment_index,
           s_motion_segment_count,
           GCodeSerial_Scale_100(s_segment_target_x),
           GCodeSerial_Scale_100(s_segment_target_y));

    if (s_active_motion == 1) {
        float feed_mm_min = (s_feed_mm_min > 0.0f) ?
                            s_feed_mm_min :
                            GCODE_SERIAL_DEFAULT_FEED_MM_MIN;
        result = WriterMotion_Queue_To_At_Feed(
            s_segment_target_x, s_segment_target_y,
            feed_mm_min);
    } else {
        result = WriterMotion_Queue_To(
            s_segment_target_x, s_segment_target_y);
    }
    if (result == APP_WRITER_QUEUE_ACCEPTED) {
        s_motion_segment_index = next_segment_index;
    }
    return result;
}

static bool GCodeSerial_Fill_Motion_Queue(void)
{
    while (s_motion_segment_index < s_motion_segment_count) {
        app_writer_queue_result_t result =
            GCodeSerial_Queue_Next_Motion_Segment();

        if (result == APP_WRITER_QUEUE_FULL) {
            s_state = GCODE_SERIAL_STATE_WAIT_MOTION;
            return true;
        }
        if (result != APP_WRITER_QUEUE_ACCEPTED) {
            return false;
        }
    }

    s_source_x = s_pending_source_x;
    s_source_y = s_pending_source_y;
    s_source_position_valid = true;
#if GCODE_SERIAL_RESTRICTED_RECT_ENABLE
    s_rect_phase = s_rect_pending_phase;
#endif
    s_state = GCODE_SERIAL_STATE_IDLE;
    GCodeSerial_Send_Ok();
    return true;
}

static bool GCodeSerial_Start_Motion(const gcode_serial_line_t *line,
                                     int32_t motion_code)
{
    const app_writer_pose_t *pose =
        WriterMotion_Get_Planned_Pose();
    float dx;
    float dy;
    float span;
    float source_span;
#if GCODE_SERIAL_RESTRICTED_RECT_ENABLE
    const char *restricted_error;
#endif

    if ((motion_code == 0) && s_pen_is_down) {
        GCodeSerial_Send_Error("rapid_with_pen_down");
        return false;
    }
    if ((motion_code == 1) && !s_pen_is_down) {
        GCodeSerial_Send_Error("linear_with_pen_up");
        return false;
    }
    if ((motion_code == 1) && !s_source_position_valid) {
        GCodeSerial_Send_Error("linear_without_paper_position");
        return false;
    }

    s_pending_source_x = s_source_x;
    s_pending_source_y = s_source_y;

    if (s_absolute_mode) {
        if (line->has_x) {
            s_pending_source_x = line->x;
        }
        if (line->has_y) {
            s_pending_source_y = line->y;
        }

        if (!s_work_origin_valid) {
            s_work_origin_x = s_pending_source_x;
            s_work_origin_y = s_pending_source_y;
            s_work_origin_valid = true;
            elog_i("GCODE_RX", "[GCODE_RX] source origin x=%d y=%d -> user 0,0",
                   GCodeSerial_Scale_100(s_work_origin_x),
                   GCodeSerial_Scale_100(s_work_origin_y));
        }
    } else {
        s_pending_source_x += line->has_x ? line->x : 0.0f;
        s_pending_source_y += line->has_y ? line->y : 0.0f;
    }

    s_motion_source_start_x = s_source_x - s_work_origin_x;
    s_motion_source_start_y = s_source_y - s_work_origin_y;
    s_motion_source_target_x =
        s_pending_source_x - s_work_origin_x;
    s_motion_source_target_y =
        s_pending_source_y - s_work_origin_y;
    if (!GCodeSerial_Paper_To_User(
            s_motion_source_target_x,
            s_motion_source_target_y,
            &s_motion_target_x,
            &s_motion_target_y)) {
        GCodeSerial_Send_Error("paper_coordinate_out_of_bounds");
        return false;
    }
    s_motion_start_x = pose->user_point.x_mm;
    s_motion_start_y = pose->user_point.y_mm;
    dx = s_motion_target_x - s_motion_start_x;
    dy = s_motion_target_y - s_motion_start_y;
    span = fmaxf(GCodeSerial_Abs(dx), GCodeSerial_Abs(dy));
    source_span = fmaxf(
        GCodeSerial_Abs(
            s_motion_source_target_x - s_motion_source_start_x),
        GCodeSerial_Abs(
            s_motion_source_target_y - s_motion_source_start_y));

#if GCODE_SERIAL_RESTRICTED_RECT_ENABLE
    restricted_error = GCodeSerial_Rect_Validate_Target(
        motion_code, &s_rect_pending_phase);
    if (restricted_error != 0) {
        GCodeSerial_Send_Error(restricted_error);
        return false;
    }
#endif

    elog_i("GCODE_RX", "[GCODE_RX] G%d source_x=%d source_y=%d target_x=%d target_y=%d map=%s mode=%s pen=%s",
           motion_code,
           GCodeSerial_Scale_100(s_pending_source_x),
           GCodeSerial_Scale_100(s_pending_source_y),
           GCodeSerial_Scale_100(s_motion_target_x),
           GCodeSerial_Scale_100(s_motion_target_y),
           GCodeSerial_Paper_Map_Quality(s_motion_source_target_y),
           s_absolute_mode ? "ABS" : "REL",
           s_pen_is_down ? "DOWN" : "UP");

    if (span <= GCODE_SERIAL_POSITION_EPSILON_MM) {
        s_source_x = s_pending_source_x;
        s_source_y = s_pending_source_y;
        s_source_position_valid = true;
#if GCODE_SERIAL_RESTRICTED_RECT_ENABLE
        s_rect_phase = s_rect_pending_phase;
#endif
        GCodeSerial_Send_Ok();
        return true;
    }

#if APP_WRITER_AUTHOR_LINE_EXECUTION_ENABLE
    /* Match DrawBot planner.c: one inverse solution and one motor block per line. */
    s_motion_segment_count = 1u;
#else
    if (motion_code == 1) {
        s_motion_segment_count = (uint32_t)(
            source_span / GCODE_SERIAL_PAPER_DRAW_SEGMENT_MM);
        if ((s_motion_segment_count == 0u) ||
            ((float)s_motion_segment_count *
             GCODE_SERIAL_PAPER_DRAW_SEGMENT_MM < source_span)) {
            s_motion_segment_count++;
        }
    } else {
        s_motion_segment_count = (uint32_t)(
            span / GCODE_SERIAL_RAPID_SEGMENT_MM);
        if ((s_motion_segment_count == 0u) ||
            ((float)s_motion_segment_count *
             GCODE_SERIAL_RAPID_SEGMENT_MM < span)) {
            s_motion_segment_count++;
        }
    }
    if (s_motion_segment_count == 0u) {
        s_motion_segment_count++;
    }
#endif
    s_motion_segment_index = 0u;
    s_active_motion = motion_code;
    s_state = GCODE_SERIAL_STATE_WAIT_MOTION;

    if (!GCodeSerial_Fill_Motion_Queue()) {
        GCodeSerial_Send_Error("motion_rejected");
        return false;
    }
    return true;
}

static bool GCodeSerial_Begin_Pen_Action(int32_t m_code)
{
    if (m_code == 3) {
        if (!s_source_position_valid) {
            GCodeSerial_Send_Error(
                "pen_down_without_paper_position");
            return false;
        }
#if GCODE_SERIAL_RESTRICTED_RECT_ENABLE
        if ((s_rect_phase != GCODE_SERIAL_RECT_PHASE_WAIT_DRAW) ||
            s_pen_is_down ||
            !GCodeSerial_Is_At(GCODE_SERIAL_RECT_X0_MM,
                               GCODE_SERIAL_RECT_Y0_MM)) {
            GCodeSerial_Send_Error("restricted_pen_down_phase");
            return false;
        }
#if GCODE_SERIAL_RECT_CCW_ENABLE
        s_rect_phase = GCODE_SERIAL_RECT_PHASE_EDGE_BOTTOM;
#else
        s_rect_phase = GCODE_SERIAL_RECT_PHASE_EDGE_LEFT;
#endif
        s_rect_pending_phase = s_rect_phase;
#endif
        App_Servo_Pen_Down();
        s_pen_is_down = true;
    } else if (m_code == 5) {
#if GCODE_SERIAL_RESTRICTED_RECT_ENABLE
        if ((s_rect_phase == GCODE_SERIAL_RECT_PHASE_WAIT_APPROACH) &&
            !s_pen_is_down) {
            /* Initial M5 is an explicit pen-up preflight. */
        } else if ((s_rect_phase ==
                    GCODE_SERIAL_RECT_PHASE_WAIT_PEN_UP) &&
                   s_pen_is_down &&
                   GCodeSerial_Is_At(GCODE_SERIAL_RECT_X0_MM,
                                     GCODE_SERIAL_RECT_Y0_MM)) {
            s_rect_phase = GCODE_SERIAL_RECT_PHASE_COMPLETE;
            s_rect_pending_phase = s_rect_phase;
        } else {
            GCodeSerial_Send_Error("restricted_pen_up_phase");
            return false;
        }
#endif
        App_Servo_Pen_Up();
        s_pen_is_down = false;
    } else {
        GCodeSerial_Send_Error("unsupported_m_code");
        return false;
    }

    s_pending_m_code = 0;
    s_wait_start_ms = s_sys_tick;
    s_wait_duration_ms = GCODE_SERIAL_PEN_SETTLE_MS;
    s_state = GCODE_SERIAL_STATE_WAIT_PEN;
    return true;
}

static bool GCodeSerial_Execute(const gcode_serial_line_t *line)
{
    int32_t motion_code = s_modal_motion;

#if GCODE_SERIAL_RESTRICTED_RECT_ENABLE
    if ((s_rect_phase == GCODE_SERIAL_RECT_PHASE_COMPLETE) ||
        (s_rect_phase == GCODE_SERIAL_RECT_PHASE_ABORTED)) {
        GCodeSerial_Send_Error("restricted_reset_required");
        return false;
    }
#endif

    if (line->has_g && line->has_m) {
        GCodeSerial_Send_Error("mixed_g_m");
        return false;
    }

    if (line->has_f) {
#if GCODE_SERIAL_RESTRICTED_RECT_ENABLE
        if (!GCodeSerial_Rect_Setup_Allowed()) {
            GCodeSerial_Send_Error("restricted_feed_phase");
            return false;
        }
#endif
        if (line->feed < 0.0f) {
            GCodeSerial_Send_Error("bad_feed");
            return false;
        }
        s_feed_mm_min = line->feed;
    }
    if (line->has_s) {
#if GCODE_SERIAL_RESTRICTED_RECT_ENABLE
        if (!GCodeSerial_Rect_Setup_Allowed()) {
            GCodeSerial_Send_Error("restricted_power_phase");
            return false;
        }
#endif
        if (line->power < 0.0f) {
            GCodeSerial_Send_Error("bad_power");
            return false;
        }
        s_power = line->power;
    }

    if (line->has_m) {
        if (line->has_x || line->has_y || line->has_z || line->has_p) {
            GCodeSerial_Send_Error("axis_on_m_code");
            return false;
        }
        if (line->m_code == 501) {
#if GCODE_SERIAL_RESTRICTED_RECT_ENABLE
            if (!GCodeSerial_Rect_Setup_Allowed()) {
                GCodeSerial_Send_Error("restricted_probe_phase");
                return false;
            }
#endif
            elog_i("GCODE_RX", "[GCODE_RX] M501 host probe acknowledged");
            GCodeSerial_Send_Ok();
            return true;
        }
        if ((line->m_code != 3) && (line->m_code != 5)) {
            GCodeSerial_Send_Error("unsupported_m_code");
            return false;
        }
        s_pending_m_code = line->m_code;
        if (!WriterMotion_Queue_Is_Idle()) {
            s_state = GCODE_SERIAL_STATE_WAIT_SYNC_PEN;
            return true;
        }
        return GCodeSerial_Begin_Pen_Action(
            s_pending_m_code);
    }

    if (line->has_g) {
        switch (line->g_code) {
            case 0:
            case 1:
                motion_code = line->g_code;
                s_modal_motion = motion_code;
                break;

            case 4:
                if (line->has_x || line->has_y || line->has_z ||
                    line->has_f) {
                    GCodeSerial_Send_Error("bad_dwell");
                    return false;
                }
                if (line->has_p &&
                    ((line->dwell_s < 0.0f) ||
                     (line->dwell_s * 1000.0f >
                      (float)GCODE_SERIAL_DWELL_MAX_MS))) {
                    GCodeSerial_Send_Error("bad_dwell");
                    return false;
                }
                s_wait_duration_ms = line->has_p ?
                    (uint32_t)lroundf(line->dwell_s * 1000.0f) : 0u;
                if (!WriterMotion_Queue_Is_Idle()) {
                    s_state = GCODE_SERIAL_STATE_WAIT_SYNC_DWELL;
                    return true;
                }
                if (s_wait_duration_ms == 0u) {
                    GCodeSerial_Send_Ok();
                    return true;
                }
                s_wait_start_ms = s_sys_tick;
                s_state = GCODE_SERIAL_STATE_WAIT_DWELL;
                return true;

            case 21:
                if (line->has_x || line->has_y || line->has_z ||
                    line->has_p) {
                    GCodeSerial_Send_Error("bad_units_command");
                    return false;
                }
#if GCODE_SERIAL_RESTRICTED_RECT_ENABLE
                if (!GCodeSerial_Rect_Setup_Allowed()) {
                    GCodeSerial_Send_Error("restricted_units_phase");
                    return false;
                }
#endif
                GCodeSerial_Reset_Source_Coordinates();
                s_absolute_mode = true;
                s_modal_motion = 0;
                elog_i("GCODE_RX", "[GCODE_RX] G21 mm; source origin x=%d y=%d fixed=%u",
                       GCodeSerial_Scale_100(s_work_origin_x),
                       GCodeSerial_Scale_100(s_work_origin_y),
                       GCODE_SERIAL_USE_FIXED_SOURCE_ORIGIN);
                GCodeSerial_Send_Ok();
                return true;

            case 90:
            case 91:
                if (line->has_x || line->has_y || line->has_z ||
                    line->has_p) {
                    GCodeSerial_Send_Error("axis_on_distance_mode");
                    return false;
                }
#if GCODE_SERIAL_RESTRICTED_RECT_ENABLE
                if (!GCodeSerial_Rect_Setup_Allowed() ||
                    (line->g_code != 90)) {
                    GCodeSerial_Send_Error("restricted_absolute_only");
                    return false;
                }
#endif
                s_absolute_mode = (line->g_code == 90);
                GCodeSerial_Send_Ok();
                return true;

            case 94:
                if (line->has_x || line->has_y || line->has_z ||
                    line->has_p) {
                    GCodeSerial_Send_Error("bad_feed_mode");
                    return false;
                }
#if GCODE_SERIAL_RESTRICTED_RECT_ENABLE
                if (!GCodeSerial_Rect_Setup_Allowed()) {
                    GCodeSerial_Send_Error("restricted_feed_mode_phase");
                    return false;
                }
#endif
                GCodeSerial_Send_Ok();
                return true;

            default:
                GCodeSerial_Send_Error("unsupported_g_code");
                return false;
        }
    }

    if (line->has_x || line->has_y) {
        return GCodeSerial_Start_Motion(line, motion_code);
    }

    /* The official generator emits standalone F/S and G0Z0 metadata. */
    if (line->has_g || line->has_z || line->has_f || line->has_s) {
#if GCODE_SERIAL_RESTRICTED_RECT_ENABLE
        if (!GCodeSerial_Rect_Setup_Allowed()) {
            GCodeSerial_Send_Error("restricted_metadata_phase");
            return false;
        }
#endif
        GCodeSerial_Send_Ok();
        return true;
    }

    GCodeSerial_Send_Error("empty_command");
    return false;
}

void GCodeSerial_Start(void)
{
    WriterMotion_Init_From_Home();
    App_Servo_Pen_Up();
    s_state = GCODE_SERIAL_STATE_IDLE;
    s_absolute_mode = true;
    s_pen_is_down = false;
    s_modal_motion = 0;
    s_active_motion = 0;
    s_pending_m_code = 0;
    s_feed_mm_min = 0.0f;
    s_power = 0.0f;
    s_motion_segment_count = 0u;
    s_motion_segment_index = 0u;
    s_motion_source_start_x = 0.0f;
    s_motion_source_start_y = 0.0f;
    s_motion_source_target_x = 0.0f;
    s_motion_source_target_y = 0.0f;
    s_wait_start_ms = 0u;
    s_wait_duration_ms = 0u;
    s_received_count = 0u;
    s_completed_count = 0u;
#if GCODE_SERIAL_RESTRICTED_RECT_ENABLE
    s_rect_phase = GCODE_SERIAL_RECT_PHASE_WAIT_APPROACH;
    s_rect_pending_phase = GCODE_SERIAL_RECT_PHASE_WAIT_APPROACH;
#endif
    GCodeSerial_Reset_Source_Coordinates();

    elog_i("GCODE_RX", "[GCODE_RX] mode=%s limit_theta=%d limit_psi=%d offset_x=%d offset_y=%d spd1=%d spd2=%d dircomp=%u",
           GCODE_SERIAL_BUILD_ID,
           GCodeSerial_Scale_100(APP_WRITER_THETA_LIMIT_DEG),
           GCodeSerial_Scale_100(APP_WRITER_PSI_LIMIT_DEG),
           GCodeSerial_Scale_100(APP_WRITER_MACHINE_OFFSET_X_MM),
           GCodeSerial_Scale_100(APP_WRITER_MACHINE_OFFSET_Y_MM),
           GCodeSerial_Scale_100(APP_WRITER_STAGE1_STEPS_PER_DEG),
           GCodeSerial_Scale_100(APP_WRITER_STAGE2_STEPS_PER_DEG),
           APP_WRITER_DIRECTION_COMP_ENABLE);
    elog_i("GCODE_RX", "[GCODE_RX] ready UART1 PB4=TX PB5=RX baud=115200 response=ok_CRLF");
#if GCODE_SERIAL_PAPER_MAP_ENABLE
    elog_i("GCODE_RX", "[GCODE_RX] placement=PAPER_LEFT_BOTTOM "
           "paper_x=%d..%d paper_y=%d..%d source_x=%d source_y=%d "
           "fixed=%u shift_x=%d shift_y=%d author_line=%u "
           "rapid_segment_mm=%d draw_segment_mm=%d",
           GCodeSerial_Scale_100(APP_WRITER_PAPER_X_MIN_MM),
           GCodeSerial_Scale_100(APP_WRITER_PAPER_X_MAX_MM),
           GCodeSerial_Scale_100(APP_WRITER_PAPER_Y_MIN_MM),
           GCodeSerial_Scale_100(APP_WRITER_PAPER_Y_MAX_MM),
           GCodeSerial_Scale_100(s_work_origin_x),
           GCodeSerial_Scale_100(s_work_origin_y),
           GCODE_SERIAL_USE_FIXED_SOURCE_ORIGIN,
           GCodeSerial_Scale_100(
               GCODE_SERIAL_WORKSPACE_SHIFT_X_MM),
           GCodeSerial_Scale_100(
               GCODE_SERIAL_WORKSPACE_SHIFT_Y_MM),
           APP_WRITER_AUTHOR_LINE_EXECUTION_ENABLE,
           GCodeSerial_Scale_100(GCODE_SERIAL_RAPID_SEGMENT_MM),
           GCodeSerial_Scale_100(GCODE_SERIAL_PAPER_DRAW_SEGMENT_MM));
    elog_w("GCODE_RX", "[GCODE_RX] paper_y_trial=%u allowed_y=%d..%d calibrated_y=%d..%d outside_calibrated=EXTRAPOLATED",
           APP_WRITER_PAPER_EXTENDED_Y_TRIAL_ENABLE,
           GCodeSerial_Scale_100(APP_WRITER_PAPER_Y_MIN_MM),
           GCodeSerial_Scale_100(APP_WRITER_PAPER_Y_MAX_MM),
           GCodeSerial_Scale_100(
               APP_WRITER_PAPER_CALIBRATED_Y_MIN_MM),
           GCodeSerial_Scale_100(
               APP_WRITER_PAPER_CALIBRATED_Y_MAX_MM));
#else
    elog_i("GCODE_RX", "[GCODE_RX] placement=DIRECT_USER "
           "source_x=%d source_y=%d fixed=%u author_line=%u "
           "shift_x=%d shift_y=%d rapid_segment_mm=%d "
           "draw_segment_mm=%d",
           GCodeSerial_Scale_100(s_work_origin_x),
           GCodeSerial_Scale_100(s_work_origin_y),
           GCODE_SERIAL_USE_FIXED_SOURCE_ORIGIN,
           APP_WRITER_AUTHOR_LINE_EXECUTION_ENABLE,
           GCodeSerial_Scale_100(
               GCODE_SERIAL_WORKSPACE_SHIFT_X_MM),
           GCodeSerial_Scale_100(
               GCODE_SERIAL_WORKSPACE_SHIFT_Y_MM),
           GCodeSerial_Scale_100(GCODE_SERIAL_RAPID_SEGMENT_MM),
           GCodeSerial_Scale_100(GCODE_SERIAL_PAPER_DRAW_SEGMENT_MM));
#endif
    elog_i("GCODE_RX", "[GCODE_RX] continuous_queue=1 capacity=%u "
           "junction_planner=%u reverse_forward=1 amass=%u amass_max=%u "
           "paper_map_enable=%u paper_map=%s grid4x7=%u sbow=%u "
           "vsbow_right=%u vsbow_x0=%d vsbow_x1=%d xscale10000=%d",
            APP_STEPPER_DUAL_QUEUE_CAPACITY,
            APP_STEPPER_JUNCTION_PLANNER_ENABLE,
            APP_STEPPER_AMASS_ENABLE,
            APP_STEPPER_AMASS_MAX_LEVEL,
            GCODE_SERIAL_PAPER_MAP_ENABLE,
           APP_WRITER_PAPER_MAP_BUILD_ID,
           APP_WRITER_PAPER_GRID_CORRECTION_ENABLE,
           APP_WRITER_PAPER_S_BOW_CORRECTION_ENABLE,
           APP_WRITER_PAPER_VERTICAL_SBOW_RIGHT_ONLY_ENABLE,
           GCodeSerial_Scale_100(
               APP_WRITER_PAPER_VERTICAL_SBOW_RIGHT_X0_MM),
           GCodeSerial_Scale_100(
               APP_WRITER_PAPER_VERTICAL_SBOW_RIGHT_X1_MM),
           (int32_t)(APP_WRITER_PAPER_X_SCALE_OBSERVED *
                     10000.0f + 0.5f));
    elog_i("GCODE_RX", "[GCODE_RX] supported=G0,G1,G4,G21,G90,G91,G94,M3,M5,M501,F,S,Z");
#if GCODE_SERIAL_RESTRICTED_RECT_ENABLE
    elog_i("GCODE_RX", "[GCODE_RX] restricted=1 direction=%s single_pass=1 rect_x=12000..29000 rect_y=500..12500 point_step_max=%d reset_after_done=1",
           GCODE_SERIAL_RECT_DIRECTION_TEXT,
           GCodeSerial_Scale_100(GCODE_SERIAL_RECT_POINT_STEP_MAX_MM));
#endif
}

void GCodeSerial_Set_Result_Callback(
    gcode_serial_result_callback_t callback,
    void *context)
{
    s_result_callback = callback;
    s_result_context = context;
}

bool GCodeSerial_Is_Idle(void)
{
    return (s_state == GCODE_SERIAL_STATE_IDLE) &&
           !WriterMotion_Is_Busy() &&
           WriterMotion_Queue_Is_Idle();
}

bool GCodeSerial_Is_Pen_Down(void)
{
    return s_pen_is_down;
}

void GCodeSerial_Abort(void)
{
    App_Servo_Pen_Up();
    s_pen_is_down = false;
    WriterMotion_Emergency_Stop();
    s_state = GCODE_SERIAL_STATE_IDLE;
#if GCODE_SERIAL_RESTRICTED_RECT_ENABLE
    s_rect_phase = GCODE_SERIAL_RECT_PHASE_ABORTED;
    s_rect_pending_phase = GCODE_SERIAL_RECT_PHASE_ABORTED;
#endif
}

void GCodeSerial_Update(void)
{
    if (((s_state != GCODE_SERIAL_STATE_IDLE) ||
         WriterMotion_Is_Busy()) &&
        (App_Stepper_Stage1_IsLimitHit() ||
         App_Stepper_Stage2_IsLimitHit())) {
        GCodeSerial_Send_Error("runtime_limit_active");
        return;
    }
    WriterMotion_Task();

    switch (s_state) {
        case GCODE_SERIAL_STATE_IDLE:
            return;

        case GCODE_SERIAL_STATE_WAIT_MOTION:
            if (!GCodeSerial_Fill_Motion_Queue()) {
                GCodeSerial_Send_Error("motion_rejected");
            }
            return;

        case GCODE_SERIAL_STATE_WAIT_SYNC_PEN:
            if (!WriterMotion_Queue_Is_Idle()) {
                return;
            }
            (void)GCodeSerial_Begin_Pen_Action(
                s_pending_m_code);
            return;

        case GCODE_SERIAL_STATE_WAIT_PEN:
            if ((uint32_t)(s_sys_tick - s_wait_start_ms) <
                s_wait_duration_ms) {
                return;
            }
            s_state = GCODE_SERIAL_STATE_IDLE;
            GCodeSerial_Send_Ok();
            return;

        case GCODE_SERIAL_STATE_WAIT_SYNC_DWELL:
            if (!WriterMotion_Queue_Is_Idle()) {
                return;
            }
            if (s_wait_duration_ms == 0u) {
                s_state = GCODE_SERIAL_STATE_IDLE;
                GCodeSerial_Send_Ok();
                return;
            }
            s_wait_start_ms = s_sys_tick;
            s_state = GCODE_SERIAL_STATE_WAIT_DWELL;
            return;

        case GCODE_SERIAL_STATE_WAIT_DWELL:
            if ((uint32_t)(s_sys_tick - s_wait_start_ms) <
                s_wait_duration_ms) {
                return;
            }
            s_state = GCODE_SERIAL_STATE_IDLE;
            GCodeSerial_Send_Ok();
            return;

        default:
            GCodeSerial_Send_Error("bad_state");
            return;
    }
}

bool GCodeSerial_ProcessFrame(const uint8_t *frame, uint16_t len)
{
    char line_text[GCODE_SERIAL_LINE_MAX];
    gcode_serial_line_t line;
    uint16_t copy_len = 0u;
    const char *trimmed;
    char reply[384];
    int reply_len;

    if ((frame == 0) || (len == 0u)) {
        return false;
    }

    while ((copy_len < len) &&
           (copy_len < (uint16_t)(sizeof(line_text) - 1u)) &&
           (frame[copy_len] != '\r') && (frame[copy_len] != '\n')) {
        line_text[copy_len] = (char)frame[copy_len];
        copy_len++;
    }
    line_text[copy_len] = '\0';
    trimmed = GCodeSerial_Skip_Space(line_text);

    /* Ignore the extra CR sent after the host's injected G94 command. */
    if (*trimmed == '\0') {
        return false;
    }
    if ((copy_len < len) &&
        (frame[copy_len] != '\r') &&
        (frame[copy_len] != '\n')) {
        GCodeSerial_Send_Error("line_too_long");
        return false;
    }
    if (strcmp(trimmed, "STOP") == 0) {
        GCodeSerial_Abort();
        if (s_result_callback != NULL) {
            s_result_callback(true, "stopped", s_result_context);
        } else {
            GCodeSerial_Send_Text(
                "ok STOPPED id=" GCODE_SERIAL_BUILD_ID
                " rehome=1 pen=UP\r\n");
        }
        return true;
    }
    if (strcmp(trimmed, "STATUS") == 0) {
        if (s_result_callback != NULL) {
            s_result_callback(true, "status", s_result_context);
            return true;
        }
#if GCODE_SERIAL_RESTRICTED_RECT_ENABLE
        reply_len = snprintf(
            reply,
            sizeof(reply),
            "ok STATUS id=%s phase=%s busy=%u received=%u completed=%u lim1=%d lim2=%d pen=%s\r\n",
            GCODE_SERIAL_BUILD_ID,
            GCodeSerial_Rect_Phase_Name(),
            ((s_state != GCODE_SERIAL_STATE_IDLE) ||
             WriterMotion_Is_Busy()) ? 1u : 0u,
            s_received_count,
            s_completed_count,
            App_Stepper_Stage1_IsLimitHit(),
            App_Stepper_Stage2_IsLimitHit(),
            s_pen_is_down ? "DOWN" : "UP");
#else
        const app_writer_pose_t *pose = WriterMotion_Get_Pose();

        reply_len = snprintf(
            reply,
            sizeof(reply),
            "ok STATUS id=%s paper_map=%s grid4x7=%u "
            "sbow=%u vsbow_right=%u map_enable=%u "
            "busy=%u queue=%u free=%u "
            "received=%u completed=%u source_valid=%u "
            "paper_x100=%d paper_y100=%d "
            "shift_x100=%d shift_y100=%d "
            "user_x100=%d user_y100=%d "
            "lim1=%d lim2=%d pen=%s\r\n",
            GCODE_SERIAL_BUILD_ID,
            APP_WRITER_PAPER_MAP_BUILD_ID,
            APP_WRITER_PAPER_GRID_CORRECTION_ENABLE,
            APP_WRITER_PAPER_S_BOW_CORRECTION_ENABLE,
            APP_WRITER_PAPER_VERTICAL_SBOW_RIGHT_ONLY_ENABLE,
            GCODE_SERIAL_PAPER_MAP_ENABLE,
            ((s_state != GCODE_SERIAL_STATE_IDLE) ||
             WriterMotion_Is_Busy()) ? 1u : 0u,
            App_Stepper_Dual_Queue_Count(),
            WriterMotion_Queue_Free(),
            s_received_count,
            s_completed_count,
            s_source_position_valid ? 1u : 0u,
            GCodeSerial_Scale_100(
                s_source_x - s_work_origin_x),
            GCodeSerial_Scale_100(
                s_source_y - s_work_origin_y),
            GCodeSerial_Scale_100(
                GCODE_SERIAL_WORKSPACE_SHIFT_X_MM),
            GCodeSerial_Scale_100(
                GCODE_SERIAL_WORKSPACE_SHIFT_Y_MM),
            GCodeSerial_Scale_100(pose->user_point.x_mm),
            GCodeSerial_Scale_100(pose->user_point.y_mm),
            App_Stepper_Stage1_IsLimitHit(),
            App_Stepper_Stage2_IsLimitHit(),
            s_pen_is_down ? "DOWN" : "UP");
#endif
        if (reply_len > 0) {
            if ((uint32_t)reply_len >= sizeof(reply)) {
                reply_len = (int)(sizeof(reply) - 1u);
            }
            App_Vision_UART_Send((const uint8_t *)reply,
                                 (uint16_t)reply_len);
        }
        return true;
    }
    if (s_state != GCODE_SERIAL_STATE_IDLE) {
        if (s_result_callback != NULL) {
            s_result_callback(false, "busy", s_result_context);
        } else {
            GCodeSerial_Send_Text("error:busy\r\n");
        }
        elog_e("GCODE_RX", "[GCODE_RX] input while busy text=%s", trimmed);
        return false;
    }

    s_received_count++;
    elog_i("GCODE_RX", "[GCODE_RX] line=%u text=%s",
           s_received_count, trimmed);
    if (!GCodeSerial_Parse_Line(trimmed, &line)) {
        GCodeSerial_Send_Error("parse_error");
        return false;
    }
    return GCodeSerial_Execute(&line);
}
