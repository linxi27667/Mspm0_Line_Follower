/**
 * @file    writer_rehome.c
 * @brief   Cloud-triggered runtime homing without blocking network service.
 */
#include "writer_rehome.h"

#include "app_servo.h"
#include "app_stepper.h"
#include "app_writer_motion.h"
#include "elog.h"

#include <stdint.h>

#define WRITER_REHOME_PEN_SETTLE_MS      (700u)
#define WRITER_REHOME_SEARCH_TIMEOUT_MS  (30000u)
#define WRITER_REHOME_PULLOFF_TIMEOUT_MS (5000u)
#define WRITER_REHOME_STAGE1_SEARCH_MAX_DEG (165.0f)
#define WRITER_REHOME_STAGE2_SEARCH_MAX_DEG (152.0f)

extern volatile uint32_t s_sys_tick;

static writer_rehome_state_t s_state = WRITER_REHOME_STATE_IDLE;
static writer_rehome_state_t s_after_clearance = WRITER_REHOME_STATE_IDLE;
static uint32_t s_state_start_ms;
static uint32_t s_release_start_stage1;
static uint32_t s_release_start_stage2;
static uint32_t s_final_release_stage1;
static uint32_t s_final_release_stage2;
static uint32_t s_final_clearance_stage1;
static uint32_t s_final_clearance_stage2;
static uint32_t s_last_progress_ms;
static uint32_t s_search_start_stage1;
static uint32_t s_search_start_stage2;

static int32_t WriterRehome_Scale_100(float value)
{
    return (int32_t)((value >= 0.0f) ?
        (value * 100.0f + 0.5f) : (value * 100.0f - 0.5f));
}

static const char *WriterRehome_State_Name(void)
{
    switch (s_state) {
        case WRITER_REHOME_STATE_IDLE: return "IDLE";
        case WRITER_REHOME_STATE_PEN_SETTLE: return "PEN_SETTLE";
        case WRITER_REHOME_STATE_INITIAL_RELEASE: return "INITIAL_RELEASE";
        case WRITER_REHOME_STATE_INITIAL_CLEARANCE:
            return "INITIAL_CLEARANCE";
        case WRITER_REHOME_STATE_FAST_SEARCH_DELAY:
            return "FAST_SEARCH_DELAY";
        case WRITER_REHOME_STATE_FAST_SEARCH: return "FAST_SEARCH";
        case WRITER_REHOME_STATE_FAST_SETTLE: return "FAST_SETTLE";
        case WRITER_REHOME_STATE_FAST_RELEASE: return "FAST_RELEASE";
        case WRITER_REHOME_STATE_FAST_CLEARANCE: return "FAST_CLEARANCE";
        case WRITER_REHOME_STATE_SLOW_SEARCH_DELAY:
            return "SLOW_SEARCH_DELAY";
        case WRITER_REHOME_STATE_SLOW_SEARCH: return "SLOW_SEARCH";
        case WRITER_REHOME_STATE_SLOW_SETTLE: return "SLOW_SETTLE";
        case WRITER_REHOME_STATE_FINAL_RELEASE: return "FINAL_RELEASE";
        case WRITER_REHOME_STATE_FINAL_CLEARANCE:
            return "FINAL_CLEARANCE";
        case WRITER_REHOME_STATE_DONE: return "DONE";
        case WRITER_REHOME_STATE_STOPPED: return "STOPPED";
        case WRITER_REHOME_STATE_ERROR: return "ERROR";
        default: return "UNKNOWN";
    }
}

static bool WriterRehome_Motors_Stopped(void)
{
    return !BSP_Stepper_IsRunning(&App_Stepper_X) &&
           !BSP_Stepper_IsRunning(&App_Stepper_Y);
}

static bool WriterRehome_Limits_Clear(void)
{
    return !App_Stepper_Stage1_IsLimitHit() &&
           !App_Stepper_Stage2_IsLimitHit();
}

static void WriterRehome_Fail(const char *reason)
{
    App_Stepper_Cancel_Zeroing();
    App_Servo_Pen_Up();
    s_state = WRITER_REHOME_STATE_ERROR;
    elog_set_filter_lvl(ELOG_FILTER_LVL_ALL);
    elog_e("REHOME",
           "id=%s result=FAILED reason=%s lim1=%d lim2=%d "
           "pulse1=%u pulse2=%u key1=RETRY",
           WRITER_REHOME_BUILD_ID,
           reason,
           App_Stepper_Stage1_IsLimitHit(),
           App_Stepper_Stage2_IsLimitHit(),
           App_Stepper_Stage1_Total_Pulses(),
           App_Stepper_Stage2_Total_Pulses());
}

static void WriterRehome_Start_Release(writer_rehome_state_t state)
{
    s_release_start_stage1 = App_Stepper_Stage1_Total_Pulses();
    s_release_start_stage2 = App_Stepper_Stage2_Total_Pulses();
    s_state_start_ms = s_sys_tick;
    s_state = state;
}

static bool WriterRehome_Service_Release(uint32_t *stage1_pulses,
                                          uint32_t *stage2_pulses)
{
    if (App_Stepper_Stage1_IsLimitHit() &&
        !BSP_Stepper_IsRunning(&App_Stepper_X)) {
        App_Stepper_Stage1_Run((uint8_t)(1u - LIMIT_STAGE1_HOME_DIR),
                               1u,
                               APP_WRITER_HOMING_LOCATE_FREQ_HZ);
    }
    if (App_Stepper_Stage2_IsLimitHit() &&
        !BSP_Stepper_IsRunning(&App_Stepper_Y)) {
        App_Stepper_Stage2_Run((uint8_t)(1u - LIMIT_STAGE2_HOME_DIR),
                               1u,
                               APP_WRITER_HOMING_LOCATE_FREQ_HZ);
    }
    if (!WriterRehome_Limits_Clear() || !WriterRehome_Motors_Stopped()) {
        return false;
    }

    if (stage1_pulses != NULL) {
        *stage1_pulses = App_Stepper_Stage1_Total_Pulses() -
                         s_release_start_stage1;
    }
    if (stage2_pulses != NULL) {
        *stage2_pulses = App_Stepper_Stage2_Total_Pulses() -
                         s_release_start_stage2;
    }
    return true;
}

static void WriterRehome_Start_Clearance(writer_rehome_state_t state,
                                          writer_rehome_state_t next_state)
{
    s_after_clearance = next_state;
    s_final_clearance_stage1 = WriterMotion_Stage1_Arm_Deg_To_Steps(
        APP_WRITER_HOMING_PULLOFF_DEG);
    s_final_clearance_stage2 = WriterMotion_Stage2_Arm_Deg_To_Steps(
        APP_WRITER_HOMING_PULLOFF_DEG);
    App_Stepper_Stage1_Run((uint8_t)(1u - LIMIT_STAGE1_HOME_DIR),
                           s_final_clearance_stage1,
                           APP_WRITER_HOMING_LOCATE_FREQ_HZ);
    App_Stepper_Stage2_Run((uint8_t)(1u - LIMIT_STAGE2_HOME_DIR),
                           s_final_clearance_stage2,
                           APP_WRITER_HOMING_LOCATE_FREQ_HZ);
    s_state_start_ms = s_sys_tick;
    s_state = state;
}

static void WriterRehome_Start_Search(writer_rehome_state_t state,
                                      uint32_t frequency_hz)
{
    s_search_start_stage1 = App_Stepper_Stage1_Total_Pulses();
    s_search_start_stage2 = App_Stepper_Stage2_Total_Pulses();
    App_Stepper_Zero_All_At_Freq(frequency_hz);
    s_state_start_ms = s_sys_tick;
    s_state = state;
}

static void WriterRehome_Finish(void)
{
    float theta_home = APP_WRITER_THETA_LIMIT_DEG +
        (float)(s_final_release_stage1 + s_final_clearance_stage1) /
            APP_WRITER_STAGE1_STEPS_PER_DEG;
    float psi_home = APP_WRITER_PSI_LIMIT_DEG +
        (float)(s_final_release_stage2 + s_final_clearance_stage2) /
            APP_WRITER_STAGE2_STEPS_PER_DEG;

    if (!WriterMotion_Set_Home_Angles(theta_home, psi_home)) {
        WriterRehome_Fail("home_angle_rejected");
        return;
    }
    WriterMotion_Init_From_Home();
    s_state = WRITER_REHOME_STATE_DONE;
    elog_set_filter_lvl(ELOG_FILTER_LVL_ALL);
    elog_i("REHOME",
           "id=%s result=DONE theta=%d psi=%d "
           "release1=%u+%u release2=%u+%u",
           WRITER_REHOME_BUILD_ID,
           WriterRehome_Scale_100(theta_home),
           WriterRehome_Scale_100(psi_home),
           s_final_release_stage1, s_final_clearance_stage1,
           s_final_release_stage2, s_final_clearance_stage2);
}

void WriterRehome_Init(void)
{
    s_state = WRITER_REHOME_STATE_IDLE;
    s_after_clearance = WRITER_REHOME_STATE_IDLE;
    s_state_start_ms = 0u;
    s_final_release_stage1 = 0u;
    s_final_release_stage2 = 0u;
    s_final_clearance_stage1 = 0u;
    s_final_clearance_stage2 = 0u;
    s_last_progress_ms = 0u;
    s_search_start_stage1 = 0u;
    s_search_start_stage2 = 0u;
}

bool WriterRehome_Start(void)
{
    if (WriterRehome_Is_Active() || App_Stepper_IsZeroing() ||
        !WriterRehome_Motors_Stopped()) {
        return false;
    }

    App_Servo_Pen_Up();
    s_state_start_ms = s_sys_tick;
    s_last_progress_ms = s_sys_tick;
    s_search_start_stage1 = App_Stepper_Stage1_Total_Pulses();
    s_search_start_stage2 = App_Stepper_Stage2_Total_Pulses();
    s_state = WRITER_REHOME_STATE_PEN_SETTLE;
    elog_w("REHOME",
           "id=%s accepted mode=NONBLOCKING_TWO_PASS "
           "seek=%u locate=%u dir1=%u dir2=%u "
           "lim1=%d lim2=%d key1=RESTART",
           WRITER_REHOME_BUILD_ID,
           APP_WRITER_HOMING_SEEK_FREQ_HZ,
           APP_WRITER_HOMING_LOCATE_FREQ_HZ,
           LIMIT_STAGE1_HOME_DIR,
           LIMIT_STAGE2_HOME_DIR,
           App_Stepper_Stage1_IsLimitHit(),
           App_Stepper_Stage2_IsLimitHit());
    /*
     * Independent one-pulse homing produces many INFO messages. Keep those
     * suppressed while emitting one compact WARN progress record per second.
     */
    elog_set_filter_lvl(ELOG_LVL_WARN);
    return true;
}

void WriterRehome_Update(void)
{
    uint32_t elapsed_ms;

    if (!WriterRehome_Is_Active()) {
        return;
    }

    App_Stepper_Task();
    elapsed_ms = (uint32_t)(s_sys_tick - s_state_start_ms);
    if ((uint32_t)(s_sys_tick - s_last_progress_ms) >= 1000u) {
        s_last_progress_ms = s_sys_tick;
        elog_w("REHOME",
               "progress state=%s state_ms=%u lim1=%d lim2=%d "
               "run1=%d run2=%d step1=%u step2=%u "
               "pulse1=%u pulse2=%u search1=%u search2=%u",
               WriterRehome_State_Name(),
               elapsed_ms,
               App_Stepper_Stage1_IsLimitHit(),
               App_Stepper_Stage2_IsLimitHit(),
               BSP_Stepper_IsRunning(&App_Stepper_X),
               BSP_Stepper_IsRunning(&App_Stepper_Y),
               App_Stepper_X.step_count,
               App_Stepper_Y.step_count,
               App_Stepper_Stage1_Total_Pulses(),
               App_Stepper_Stage2_Total_Pulses(),
               App_Stepper_Stage1_Total_Pulses() -
                   s_search_start_stage1,
               App_Stepper_Stage2_Total_Pulses() -
                   s_search_start_stage2);
    }

    switch (s_state) {
        case WRITER_REHOME_STATE_PEN_SETTLE:
            if (elapsed_ms >= WRITER_REHOME_PEN_SETTLE_MS) {
                if (WriterRehome_Limits_Clear()) {
                    s_state_start_ms = s_sys_tick;
                    s_state = WRITER_REHOME_STATE_FAST_SEARCH_DELAY;
                } else {
                    WriterRehome_Start_Release(
                        WRITER_REHOME_STATE_INITIAL_RELEASE);
                }
            }
            break;

        case WRITER_REHOME_STATE_INITIAL_RELEASE:
            if (elapsed_ms > WRITER_REHOME_PULLOFF_TIMEOUT_MS) {
                WriterRehome_Fail("initial_release_timeout");
            } else if (WriterRehome_Service_Release(NULL, NULL)) {
                WriterRehome_Start_Clearance(
                    WRITER_REHOME_STATE_INITIAL_CLEARANCE,
                    WRITER_REHOME_STATE_FAST_SEARCH_DELAY);
            }
            break;

        case WRITER_REHOME_STATE_INITIAL_CLEARANCE:
        case WRITER_REHOME_STATE_FAST_CLEARANCE:
        case WRITER_REHOME_STATE_FINAL_CLEARANCE:
            if (elapsed_ms > WRITER_REHOME_PULLOFF_TIMEOUT_MS) {
                WriterRehome_Fail("clearance_timeout");
            } else if (WriterRehome_Motors_Stopped()) {
                if (!WriterRehome_Limits_Clear()) {
                    WriterRehome_Fail("clearance_limit_active");
                } else if (s_after_clearance == WRITER_REHOME_STATE_DONE) {
                    WriterRehome_Finish();
                } else {
                    s_state_start_ms = s_sys_tick;
                    s_state = s_after_clearance;
                }
            }
            break;

        case WRITER_REHOME_STATE_FAST_SEARCH_DELAY:
            if (elapsed_ms >= APP_WRITER_HOMING_DEBOUNCE_MS) {
                WriterRehome_Start_Search(WRITER_REHOME_STATE_FAST_SEARCH,
                                          APP_WRITER_HOMING_SEEK_FREQ_HZ);
            }
            break;

        case WRITER_REHOME_STATE_FAST_SEARCH:
        case WRITER_REHOME_STATE_SLOW_SEARCH:
            if (!App_Stepper_Stage1_IsLimitHit() &&
                ((App_Stepper_Stage1_Total_Pulses() -
                  s_search_start_stage1) >
                 WriterMotion_Stage1_Arm_Deg_To_Steps(
                     WRITER_REHOME_STAGE1_SEARCH_MAX_DEG))) {
                WriterRehome_Fail("stage1_search_travel_exceeded");
            } else if (!App_Stepper_Stage2_IsLimitHit() &&
                       ((App_Stepper_Stage2_Total_Pulses() -
                         s_search_start_stage2) >
                        WriterMotion_Stage2_Arm_Deg_To_Steps(
                            WRITER_REHOME_STAGE2_SEARCH_MAX_DEG))) {
                WriterRehome_Fail("stage2_search_travel_exceeded");
            } else if (elapsed_ms > WRITER_REHOME_SEARCH_TIMEOUT_MS) {
                WriterRehome_Fail("search_timeout");
            } else if (!App_Stepper_IsZeroing()) {
                if (!App_Stepper_Stage1_IsLimitHit() ||
                    !App_Stepper_Stage2_IsLimitHit()) {
                    WriterRehome_Fail("search_without_both_limits");
                } else {
                    s_state_start_ms = s_sys_tick;
                    s_state = (s_state == WRITER_REHOME_STATE_FAST_SEARCH) ?
                        WRITER_REHOME_STATE_FAST_SETTLE :
                        WRITER_REHOME_STATE_SLOW_SETTLE;
                }
            }
            break;

        case WRITER_REHOME_STATE_FAST_SETTLE:
        case WRITER_REHOME_STATE_SLOW_SETTLE:
            if (!App_Stepper_Stage1_IsLimitHit() ||
                !App_Stepper_Stage2_IsLimitHit()) {
                WriterRehome_Fail("limit_unstable");
            } else if (elapsed_ms >= APP_WRITER_HOMING_DEBOUNCE_MS) {
                WriterRehome_Start_Release(
                    (s_state == WRITER_REHOME_STATE_FAST_SETTLE) ?
                    WRITER_REHOME_STATE_FAST_RELEASE :
                    WRITER_REHOME_STATE_FINAL_RELEASE);
            }
            break;

        case WRITER_REHOME_STATE_FAST_RELEASE:
            if (elapsed_ms > WRITER_REHOME_PULLOFF_TIMEOUT_MS) {
                WriterRehome_Fail("fast_release_timeout");
            } else if (WriterRehome_Service_Release(NULL, NULL)) {
                WriterRehome_Start_Clearance(
                    WRITER_REHOME_STATE_FAST_CLEARANCE,
                    WRITER_REHOME_STATE_SLOW_SEARCH_DELAY);
            }
            break;

        case WRITER_REHOME_STATE_SLOW_SEARCH_DELAY:
            if (elapsed_ms >= APP_WRITER_HOMING_DEBOUNCE_MS) {
                WriterRehome_Start_Search(WRITER_REHOME_STATE_SLOW_SEARCH,
                                          APP_WRITER_HOMING_LOCATE_FREQ_HZ);
            }
            break;

        case WRITER_REHOME_STATE_FINAL_RELEASE:
            if (elapsed_ms > WRITER_REHOME_PULLOFF_TIMEOUT_MS) {
                WriterRehome_Fail("final_release_timeout");
            } else if (WriterRehome_Service_Release(
                           &s_final_release_stage1,
                           &s_final_release_stage2)) {
                WriterRehome_Start_Clearance(
                    WRITER_REHOME_STATE_FINAL_CLEARANCE,
                    WRITER_REHOME_STATE_DONE);
            }
            break;

        case WRITER_REHOME_STATE_IDLE:
        case WRITER_REHOME_STATE_DONE:
        case WRITER_REHOME_STATE_STOPPED:
        case WRITER_REHOME_STATE_ERROR:
        default:
            break;
    }
}

void WriterRehome_Abort(void)
{
    App_Stepper_Cancel_Zeroing();
    App_Servo_Pen_Up();
    elog_set_filter_lvl(ELOG_FILTER_LVL_ALL);
    if (WriterRehome_Is_Active()) {
        s_state = WRITER_REHOME_STATE_STOPPED;
        elog_w("REHOME",
               "id=%s result=ABORTED key1_can_restart=1",
               WRITER_REHOME_BUILD_ID);
    }
}

bool WriterRehome_Is_Active(void)
{
    return (s_state >= WRITER_REHOME_STATE_PEN_SETTLE) &&
           (s_state <= WRITER_REHOME_STATE_FINAL_CLEARANCE);
}

bool WriterRehome_Is_Succeeded(void)
{
    return s_state == WRITER_REHOME_STATE_DONE;
}

bool WriterRehome_Is_Failed(void)
{
    return s_state == WRITER_REHOME_STATE_ERROR;
}

writer_rehome_state_t WriterRehome_Get_State(void)
{
    return s_state;
}
