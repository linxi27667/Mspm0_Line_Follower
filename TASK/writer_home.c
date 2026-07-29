/**
 * @file    writer_home.c
 * @brief   Writer robot initial homing task implementation.
 */
#include "writer_home.h"
#include "app_servo.h"
#include "app_stepper.h"
#include "app_writer_motion.h"
#include "comm_vision_uart.h"
#include "elog.h"
#include <stdbool.h>
#include <ctype.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#define WRITER_HOME_SEARCH_TIMEOUT_MS  (30000u)
#define WRITER_HOME_PULLOFF_TIMEOUT_MS (5000u)
#define WRITER_HOME_CAL_BUILD_ID       "AUTHOR_HOME_CAL_0_135_V1"

extern volatile uint32_t s_sys_tick;

static int32_t WriterHome_Scale_100(float value)
{
    return (int32_t)((value >= 0.0f) ? (value * 100.0f + 0.5f) : (value * 100.0f - 0.5f));
}

static void WriterHome_Delay(uint32_t delay_ms)
{
    uint32_t start_ms = s_sys_tick;
    while ((uint32_t)(s_sys_tick - start_ms) < delay_ms) {
        App_Stepper_Task();
    }
}

static bool WriterHome_Wait_Motors(uint32_t timeout_ms)
{
    uint32_t start_ms = s_sys_tick;
    while (BSP_Stepper_IsRunning(&App_Stepper_X) ||
           BSP_Stepper_IsRunning(&App_Stepper_Y)) {
        App_Stepper_Task();
        if ((uint32_t)(s_sys_tick - start_ms) > timeout_ms) {
            App_Stepper_Stage1_Stop();
            App_Stepper_Stage2_Stop();
            return false;
        }
    }
    return true;
}

static bool WriterHome_Release_Active_Limits(const char *phase,
                                             uint32_t *stage1_pulses,
                                             uint32_t *stage2_pulses)
{
    uint32_t start_ms = s_sys_tick;
    uint32_t start_stage1 = App_Stepper_Stage1_Total_Pulses();
    uint32_t start_stage2 = App_Stepper_Stage2_Total_Pulses();
    uint32_t released_stage1;
    uint32_t released_stage2;

    while (App_Stepper_Stage1_IsLimitHit() || App_Stepper_Stage2_IsLimitHit()) {
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

        App_Stepper_Task();
        if ((uint32_t)(s_sys_tick - start_ms) > WRITER_HOME_PULLOFF_TIMEOUT_MS) {
            App_Stepper_Stage1_Stop();
            App_Stepper_Stage2_Stop();
            elog_e("HOME", "%s limit release timeout lim1=%d lim2=%d",
                   phase,
                   App_Stepper_Stage1_IsLimitHit(),
                   App_Stepper_Stage2_IsLimitHit());
            return false;
        }
    }

    if (!WriterHome_Wait_Motors(WRITER_HOME_PULLOFF_TIMEOUT_MS)) {
        return false;
    }

    released_stage1 = App_Stepper_Stage1_Total_Pulses() - start_stage1;
    released_stage2 = App_Stepper_Stage2_Total_Pulses() - start_stage2;
    if (stage1_pulses != 0) {
        *stage1_pulses = released_stage1;
    }
    if (stage2_pulses != 0) {
        *stage2_pulses = released_stage2;
    }

    elog_w("HOME", "%s limits released s1=%u s2=%u",
           phase,
           released_stage1,
           released_stage2);
    return true;
}

static bool WriterHome_Add_Release_Clearance(const char *phase,
                                             uint32_t *stage1_pulses,
                                             uint32_t *stage2_pulses)
{
    uint32_t stage1_steps = WriterMotion_Stage1_Arm_Deg_To_Steps(
        APP_WRITER_HOMING_PULLOFF_DEG);
    uint32_t stage2_steps = WriterMotion_Stage2_Arm_Deg_To_Steps(
        APP_WRITER_HOMING_PULLOFF_DEG);

    App_Stepper_Stage1_Run((uint8_t)(1u - LIMIT_STAGE1_HOME_DIR),
                           stage1_steps,
                           APP_WRITER_HOMING_LOCATE_FREQ_HZ);
    App_Stepper_Stage2_Run((uint8_t)(1u - LIMIT_STAGE2_HOME_DIR),
                           stage2_steps,
                           APP_WRITER_HOMING_LOCATE_FREQ_HZ);

    if (!WriterHome_Wait_Motors(WRITER_HOME_PULLOFF_TIMEOUT_MS)) {
        elog_e("HOME", "%s release clearance timeout", phase);
        return false;
    }
    if (App_Stepper_Stage1_IsLimitHit() || App_Stepper_Stage2_IsLimitHit()) {
        elog_e("HOME", "%s release clearance failed lim1=%d lim2=%d",
               phase,
               App_Stepper_Stage1_IsLimitHit(),
               App_Stepper_Stage2_IsLimitHit());
        return false;
    }

    if (stage1_pulses != 0) {
        *stage1_pulses = stage1_steps;
    }
    if (stage2_pulses != 0) {
        *stage2_pulses = stage2_steps;
    }

    elog_w("HOME", "%s release clearance s1=%u s2=%u",
           phase,
           stage1_steps,
           stage2_steps);
    return true;
}

static bool WriterHome_Search(uint32_t freq_hz)
{
    uint32_t start_ms = s_sys_tick;

    App_Stepper_Zero_All_At_Freq(freq_hz);
    while (App_Stepper_IsZeroing()) {
        App_Stepper_Task();
        if ((uint32_t)(s_sys_tick - start_ms) > WRITER_HOME_SEARCH_TIMEOUT_MS) {
            App_Stepper_Cancel_Zeroing();
            elog_e("HOME", "search timeout freq=%u lim1=%d lim2=%d",
                   freq_hz,
                   App_Stepper_Stage1_IsLimitHit(),
                   App_Stepper_Stage2_IsLimitHit());
            return false;
        }
    }

    return App_Stepper_Stage1_IsLimitHit() && App_Stepper_Stage2_IsLimitHit();
}

bool WriterHome_InitialHome_Task(void)
{
    bool ok = false;
    uint32_t final_release_stage1 = 0u;
    uint32_t final_release_stage2 = 0u;
    uint32_t final_clearance_stage1 = 0u;
    uint32_t final_clearance_stage2 = 0u;
    float theta_home = APP_WRITER_THETA_HOME_DEG;
    float psi_home = APP_WRITER_PSI_HOME_DEG;

    elog_i("HOME", "author homing start seek=%u locate=%u pull_off_x100=%d lim1=%d lim2=%d",
           APP_WRITER_HOMING_SEEK_FREQ_HZ,
           APP_WRITER_HOMING_LOCATE_FREQ_HZ,
           WriterHome_Scale_100(APP_WRITER_HOMING_PULLOFF_DEG),
           App_Stepper_Stage1_IsLimitHit(),
           App_Stepper_Stage2_IsLimitHit());

    elog_set_filter_lvl(ELOG_LVL_WARN);

    if ((App_Stepper_Stage1_IsLimitHit() || App_Stepper_Stage2_IsLimitHit()) &&
        !WriterHome_Release_Active_Limits("startup", 0, 0)) {
        goto done;
    }
    WriterHome_Delay(APP_WRITER_HOMING_DEBOUNCE_MS);

    if (!WriterHome_Search(APP_WRITER_HOMING_SEEK_FREQ_HZ)) {
        goto done;
    }
    WriterHome_Delay(APP_WRITER_HOMING_DEBOUNCE_MS);
    if (!WriterHome_Release_Active_Limits("fast", 0, 0)) {
        goto done;
    }
    if (!WriterHome_Add_Release_Clearance("fast", 0, 0)) {
        goto done;
    }
    WriterHome_Delay(APP_WRITER_HOMING_DEBOUNCE_MS);

    if (!WriterHome_Search(APP_WRITER_HOMING_LOCATE_FREQ_HZ)) {
        goto done;
    }
    WriterHome_Delay(APP_WRITER_HOMING_DEBOUNCE_MS);
    if (!WriterHome_Release_Active_Limits("final",
                                          &final_release_stage1,
                                          &final_release_stage2)) {
        goto done;
    }
    if (!WriterHome_Add_Release_Clearance("final",
                                           &final_clearance_stage1,
                                           &final_clearance_stage2)) {
        goto done;
    }

    theta_home = APP_WRITER_THETA_LIMIT_DEG +
                 (float)(final_release_stage1 + final_clearance_stage1) /
                     APP_WRITER_STAGE1_STEPS_PER_DEG;
    psi_home = APP_WRITER_PSI_LIMIT_DEG +
               (float)(final_release_stage2 + final_clearance_stage2) /
                   APP_WRITER_STAGE2_STEPS_PER_DEG;
    if (!WriterMotion_Set_Home_Angles(theta_home, psi_home)) {
        elog_e("HOME", "measured home rejected theta=%d psi=%d",
               WriterHome_Scale_100(theta_home),
               WriterHome_Scale_100(psi_home));
        goto done;
    }

    elog_w("HOME", "measured home release1=%u+%u release2=%u+%u theta=%d psi=%d",
           final_release_stage1,
           final_clearance_stage1,
           final_release_stage2,
           final_clearance_stage2,
           WriterHome_Scale_100(theta_home),
           WriterHome_Scale_100(psi_home));

    ok = true;

done:
    elog_set_filter_lvl(ELOG_FILTER_LVL_ALL);

    elog_i("HOME", "author homing done ok=%d theta=%d psi=%d stage1=%u stage2=%u lim1=%d lim2=%d",
           ok,
           WriterHome_Scale_100(theta_home),
           WriterHome_Scale_100(psi_home),
           App_Stepper_X.step_count,
           App_Stepper_Y.step_count,
           App_Stepper_Stage1_IsLimitHit(),
           App_Stepper_Stage2_IsLimitHit());
    return ok;
}

void WriterHome_Absolute_Calibration_Task(void)
{
    elog_i("HOMECAL", "[HOMECAL] mode=%s author known pose theta=%d psi=%d beta=%d spd1=%d spd2=%d lim1=%d lim2=%d",
           WRITER_HOME_CAL_BUILD_ID,
           WriterHome_Scale_100(APP_WRITER_CAL_THETA_DEG),
           WriterHome_Scale_100(APP_WRITER_CAL_PSI_DEG),
           WriterHome_Scale_100(APP_WRITER_CAL_PSI_DEG - APP_WRITER_CAL_THETA_DEG),
           WriterHome_Scale_100(APP_WRITER_STAGE1_STEPS_PER_DEG),
           WriterHome_Scale_100(APP_WRITER_STAGE2_STEPS_PER_DEG),
           App_Stepper_Stage1_IsLimitHit(),
           App_Stepper_Stage2_IsLimitHit());

    if (App_Stepper_Stage1_IsLimitHit() || App_Stepper_Stage2_IsLimitHit()) {
        elog_e("HOMECAL", "[HOMECAL] abort: release both limits at author 0/135 calibration pose");
        return;
    }

    uint32_t start_stage1 = App_Stepper_Stage1_Total_Pulses();
    uint32_t start_stage2 = App_Stepper_Stage2_Total_Pulses();
    if (!WriterHome_Search(APP_WRITER_HOMING_LOCATE_FREQ_HZ)) {
        elog_e("HOMECAL", "[HOMECAL] mode=%s abort: homing failed lim1=%d lim2=%d",
               WRITER_HOME_CAL_BUILD_ID,
               App_Stepper_Stage1_IsLimitHit(),
               App_Stepper_Stage2_IsLimitHit());
        return;
    }

    uint32_t stage1_pulses = App_Stepper_Stage1_Total_Pulses() - start_stage1;
    uint32_t stage2_pulses = App_Stepper_Stage2_Total_Pulses() - start_stage2;
    float theta_home = APP_WRITER_CAL_THETA_DEG -
                       ((float)stage1_pulses / APP_WRITER_STAGE1_STEPS_PER_DEG);
    float psi_home = APP_WRITER_CAL_PSI_DEG -
                     ((float)stage2_pulses / APP_WRITER_STAGE2_STEPS_PER_DEG);

    elog_i("HOMECAL", "[HOMECAL] measured s1=%u s2=%u theta=%d psi=%d expected_theta=%d expected_psi=%d lim1=%d lim2=%d",
           stage1_pulses,
           stage2_pulses,
           WriterHome_Scale_100(theta_home),
           WriterHome_Scale_100(psi_home),
           WriterHome_Scale_100(APP_WRITER_THETA_LIMIT_DEG),
           WriterHome_Scale_100(APP_WRITER_PSI_LIMIT_DEG),
           App_Stepper_Stage1_IsLimitHit(),
           App_Stepper_Stage2_IsLimitHit());

    if (!WriterHome_Release_Active_Limits("calibration", 0, 0) ||
        !WriterHome_Add_Release_Clearance("calibration", 0, 0)) {
        elog_e("HOMECAL", "[HOMECAL] mode=%s measured but limit release failed lim1=%d lim2=%d",
               WRITER_HOME_CAL_BUILD_ID,
               App_Stepper_Stage1_IsLimitHit(),
               App_Stepper_Stage2_IsLimitHit());
        return;
    }

    elog_i("HOMECAL", "[HOMECAL] mode=%s done theta_limit=%d psi_limit=%d lim1=%d lim2=%d pen=UP",
           WRITER_HOME_CAL_BUILD_ID,
           WriterHome_Scale_100(theta_home),
           WriterHome_Scale_100(psi_home),
           App_Stepper_Stage1_IsLimitHit(),
           App_Stepper_Stage2_IsLimitHit());
}

#define WRITER_HOME_M700_SEARCH_TIMEOUT_MS       (35000u)
#define WRITER_HOME_M700_RELEASE_TIMEOUT_MS      (5000u)
#define WRITER_HOME_M700_SEARCH_MAX_DEG          (60.0f)
#define WRITER_HOME_M700_REPEAT_CYCLES           (2u)
#define WRITER_HOME_M700_TOTAL_CYCLES            (1u + WRITER_HOME_M700_REPEAT_CYCLES)
#define WRITER_HOME_M700_REPEAT_TOLERANCE_STEPS  (4u)
#define WRITER_HOME_M700_REPLY_MAX               (320u)

/* Full author A4 with offset (-129,+128) needs one degree of clearance
 * beyond the BL theta and TL psi corner angles. */
#define WRITER_HOME_M700_A4_THETA_LIMIT_MAX_DEG  (-19.22f)
#define WRITER_HOME_M700_A4_PSI_LIMIT_MAX_DEG    (93.36f)

static writer_home_m700_state_t s_m700_state =
    WRITER_HOME_M700_STATE_IDLE;
static uint8_t s_m700_cycle = 0u;
static uint32_t s_m700_state_start_ms = 0u;
static uint32_t s_m700_stage1_start_pulses = 0u;
static uint32_t s_m700_stage2_start_pulses = 0u;
static uint32_t s_m700_search_stage1[WRITER_HOME_M700_TOTAL_CYCLES];
static uint32_t s_m700_search_stage2[WRITER_HOME_M700_TOTAL_CYCLES];
static uint32_t s_m700_release_stage1[WRITER_HOME_M700_TOTAL_CYCLES];
static uint32_t s_m700_release_stage2[WRITER_HOME_M700_TOTAL_CYCLES];
static uint32_t s_m700_clearance_stage1 = 0u;
static uint32_t s_m700_clearance_stage2 = 0u;
static float s_m700_theta_limit_deg = 0.0f;
static float s_m700_psi_limit_deg = 135.0f;
static bool s_m700_limit_valid = false;

static uint32_t WriterHome_M700_Abs_Diff(uint32_t a, uint32_t b)
{
    return (a >= b) ? (a - b) : (b - a);
}

static const char *WriterHome_M700_State_Name(void)
{
    switch (s_m700_state) {
        case WRITER_HOME_M700_STATE_IDLE:
            return "IDLE";
        case WRITER_HOME_M700_STATE_WAIT_CAL:
            return "WAIT_CAL";
        case WRITER_HOME_M700_STATE_SEARCHING:
            return "SEARCHING";
        case WRITER_HOME_M700_STATE_LIMIT_SETTLE:
            return "LIMIT_SETTLE";
        case WRITER_HOME_M700_STATE_RELEASING:
            return "RELEASING";
        case WRITER_HOME_M700_STATE_CLEARANCE:
            return "CLEARANCE";
        case WRITER_HOME_M700_STATE_REPEAT_DELAY:
            return "REPEAT_DELAY";
        case WRITER_HOME_M700_STATE_DONE:
            return "DONE";
        case WRITER_HOME_M700_STATE_STOPPED:
            return "STOPPED";
        case WRITER_HOME_M700_STATE_ERROR:
            return "ERROR";
        default:
            return "UNKNOWN";
    }
}

static void WriterHome_M700_Sendf(const char *fmt, ...)
{
    char reply[WRITER_HOME_M700_REPLY_MAX];
    va_list args;
    int count;

    va_start(args, fmt);
    count = vsnprintf(reply, sizeof(reply), fmt, args);
    va_end(args);
    if (count < 0) {
        return;
    }
    if ((uint32_t)count >= sizeof(reply)) {
        count = (int)(sizeof(reply) - 1u);
    }
    App_Vision_UART_Send((const uint8_t *)reply, (uint16_t)count);
}

static void WriterHome_M700_Stop(writer_home_m700_state_t state,
                                 const char *reason)
{
    App_Stepper_Cancel_Zeroing();
    App_Servo_Pen_Up();
    s_m700_state = state;

    elog_e("M700CAL", "[M700CAL] stop=%s state=%s cycle=%u/%u lim1=%d lim2=%d pen=UP reposition_0_135=1",
           reason,
           WriterHome_M700_State_Name(),
           (uint32_t)(s_m700_cycle + 1u),
           WRITER_HOME_M700_TOTAL_CYCLES,
           App_Stepper_Stage1_IsLimitHit(),
           App_Stepper_Stage2_IsLimitHit());
    WriterHome_M700_Sendf(
        "error:%s id=%s state=%s pen=UP reposition_0_135=1\r\n",
        reason,
        WRITER_HOME_M700_BUILD_ID,
        WriterHome_M700_State_Name());
}

static bool WriterHome_M700_Limits_Clear(void)
{
    return !App_Stepper_Stage1_IsLimitHit() &&
           !App_Stepper_Stage2_IsLimitHit();
}

static bool WriterHome_M700_Motors_Stopped(void)
{
    return !BSP_Stepper_IsRunning(&App_Stepper_X) &&
           !BSP_Stepper_IsRunning(&App_Stepper_Y);
}

static void WriterHome_M700_Start_Search(uint8_t cycle)
{
    s_m700_cycle = cycle;
    s_m700_stage1_start_pulses = App_Stepper_Stage1_Total_Pulses();
    s_m700_stage2_start_pulses = App_Stepper_Stage2_Total_Pulses();
    s_m700_state_start_ms = s_sys_tick;
    s_m700_state = WRITER_HOME_M700_STATE_SEARCHING;
    App_Stepper_Zero_All_At_Freq(APP_WRITER_HOMING_LOCATE_FREQ_HZ);

    elog_i("M700CAL", "[M700CAL] search_start cycle=%u/%u freq=%u max_deg=%d lim1=0 lim2=0 pen=UP",
           (uint32_t)(cycle + 1u),
           WRITER_HOME_M700_TOTAL_CYCLES,
           APP_WRITER_HOMING_LOCATE_FREQ_HZ,
           WriterHome_Scale_100(WRITER_HOME_M700_SEARCH_MAX_DEG));
}

static void WriterHome_M700_Start_Release(void)
{
    s_m700_stage1_start_pulses = App_Stepper_Stage1_Total_Pulses();
    s_m700_stage2_start_pulses = App_Stepper_Stage2_Total_Pulses();
    s_m700_state_start_ms = s_sys_tick;
    s_m700_state = WRITER_HOME_M700_STATE_RELEASING;
}

static void WriterHome_M700_Start_Clearance(uint32_t released_stage1,
                                            uint32_t released_stage2)
{
    s_m700_release_stage1[s_m700_cycle] = released_stage1;
    s_m700_release_stage2[s_m700_cycle] = released_stage2;
    s_m700_state_start_ms = s_sys_tick;
    s_m700_state = WRITER_HOME_M700_STATE_CLEARANCE;

    App_Stepper_Stage1_Run((uint8_t)(1u - LIMIT_STAGE1_HOME_DIR),
                           s_m700_clearance_stage1,
                           APP_WRITER_HOMING_LOCATE_FREQ_HZ);
    App_Stepper_Stage2_Run((uint8_t)(1u - LIMIT_STAGE2_HOME_DIR),
                           s_m700_clearance_stage2,
                           APP_WRITER_HOMING_LOCATE_FREQ_HZ);

    elog_i("M700CAL", "[M700CAL] release cycle=%u/%u released_s1=%u released_s2=%u clearance_s1=%u clearance_s2=%u",
           (uint32_t)(s_m700_cycle + 1u),
           WRITER_HOME_M700_TOTAL_CYCLES,
           released_stage1,
           released_stage2,
           s_m700_clearance_stage1,
           s_m700_clearance_stage2);
}

static void WriterHome_M700_Finish(void)
{
    uint32_t diff_stage1 = WriterHome_M700_Abs_Diff(
        s_m700_search_stage1[1], s_m700_search_stage1[2]);
    uint32_t diff_stage2 = WriterHome_M700_Abs_Diff(
        s_m700_search_stage2[1], s_m700_search_stage2[2]);
    bool repeat_ok =
        (diff_stage1 <= WRITER_HOME_M700_REPEAT_TOLERANCE_STEPS) &&
        (diff_stage2 <= WRITER_HOME_M700_REPEAT_TOLERANCE_STEPS);
    bool author_a4_candidate = s_m700_limit_valid &&
        (s_m700_theta_limit_deg <=
         WRITER_HOME_M700_A4_THETA_LIMIT_MAX_DEG) &&
        (s_m700_psi_limit_deg <=
         WRITER_HOME_M700_A4_PSI_LIMIT_MAX_DEG);

    App_Servo_Pen_Up();
    elog_i("M700CAL", "[M700CAL] result initial_s1=%u initial_s2=%u theta_limit=%d psi_limit=%d repeat1_s1=%u repeat1_s2=%u repeat2_s1=%u repeat2_s2=%u diff_s1=%u diff_s2=%u tolerance=%u repeat_ok=%d author_a4_candidate=%d required_theta_limit_max=%d required_psi_limit_max=%d lim1=0 lim2=0 pen=UP",
           s_m700_search_stage1[0],
           s_m700_search_stage2[0],
           WriterHome_Scale_100(s_m700_theta_limit_deg),
           WriterHome_Scale_100(s_m700_psi_limit_deg),
           s_m700_search_stage1[1],
           s_m700_search_stage2[1],
           s_m700_search_stage1[2],
           s_m700_search_stage2[2],
           diff_stage1,
           diff_stage2,
           WRITER_HOME_M700_REPEAT_TOLERANCE_STEPS,
           repeat_ok,
           author_a4_candidate,
           WriterHome_Scale_100(
               WRITER_HOME_M700_A4_THETA_LIMIT_MAX_DEG),
           WriterHome_Scale_100(
               WRITER_HOME_M700_A4_PSI_LIMIT_MAX_DEG));

    if (!repeat_ok) {
        s_m700_state = WRITER_HOME_M700_STATE_ERROR;
        WriterHome_M700_Sendf(
            "error:repeatability id=%s diff_s1=%u diff_s2=%u tolerance=%u pen=UP reposition_0_135=1\r\n",
            WRITER_HOME_M700_BUILD_ID,
            diff_stage1,
            diff_stage2,
            WRITER_HOME_M700_REPEAT_TOLERANCE_STEPS);
        return;
    }

    s_m700_state = WRITER_HOME_M700_STATE_DONE;
    elog_i("M700CAL", "[M700CAL] %s done calibration_valid=1 author_a4_candidate=%d lim1=0 lim2=0 pen=UP",
           WRITER_HOME_M700_BUILD_ID,
           author_a4_candidate);
    WriterHome_M700_Sendf(
        "ok DONE id=%s theta_limit_x100=%d psi_limit_x100=%d diff_s1=%u diff_s2=%u author_a4_candidate=%d pen=UP\r\n",
        WRITER_HOME_M700_BUILD_ID,
        WriterHome_Scale_100(s_m700_theta_limit_deg),
        WriterHome_Scale_100(s_m700_psi_limit_deg),
        diff_stage1,
        diff_stage2,
        author_a4_candidate);
}

void WriterHome_M700_Start(void)
{
    memset(s_m700_search_stage1, 0, sizeof(s_m700_search_stage1));
    memset(s_m700_search_stage2, 0, sizeof(s_m700_search_stage2));
    memset(s_m700_release_stage1, 0, sizeof(s_m700_release_stage1));
    memset(s_m700_release_stage2, 0, sizeof(s_m700_release_stage2));
    s_m700_cycle = 0u;
    s_m700_limit_valid = false;
    s_m700_theta_limit_deg = APP_WRITER_CAL_THETA_DEG;
    s_m700_psi_limit_deg = APP_WRITER_CAL_PSI_DEG;
    s_m700_clearance_stage1 = WriterMotion_Stage1_Arm_Deg_To_Steps(
        APP_WRITER_HOMING_PULLOFF_DEG);
    s_m700_clearance_stage2 = WriterMotion_Stage2_Arm_Deg_To_Steps(
        APP_WRITER_HOMING_PULLOFF_DEG);
    s_m700_state = WRITER_HOME_M700_STATE_WAIT_CAL;
    App_Servo_Pen_Up();

    elog_i("M700CAL", "[M700CAL] mode=%s ready command=CAL_or_M700 no_auto_motion=1 no_gcode=1 no_draw=1 pen=UP",
           WRITER_HOME_M700_BUILD_ID);
    elog_i("M700CAL", "[M700CAL] known_pose theta=%d psi=%d beta=%d large_arm_parallel_base=1 arm_angle=4500 limits_must_be_clear=1 spd1=%d spd2=%d",
           WriterHome_Scale_100(APP_WRITER_CAL_THETA_DEG),
           WriterHome_Scale_100(APP_WRITER_CAL_PSI_DEG),
           WriterHome_Scale_100(APP_WRITER_CAL_PSI_DEG -
                                APP_WRITER_CAL_THETA_DEG),
           WriterHome_Scale_100(APP_WRITER_STAGE1_STEPS_PER_DEG),
           WriterHome_Scale_100(APP_WRITER_STAGE2_STEPS_PER_DEG));
    elog_i("M700CAL", "[M700CAL] author_current_contract offset_x=-12900 offset_y=12800 A4=29700x21000 required_theta_limit_max=%d required_psi_limit_max=%d repeat_cycles=%u tolerance_steps=%u lim1=%d lim2=%d",
           WriterHome_Scale_100(
               WRITER_HOME_M700_A4_THETA_LIMIT_MAX_DEG),
           WriterHome_Scale_100(
               WRITER_HOME_M700_A4_PSI_LIMIT_MAX_DEG),
           WRITER_HOME_M700_REPEAT_CYCLES,
           WRITER_HOME_M700_REPEAT_TOLERANCE_STEPS,
           App_Stepper_Stage1_IsLimitHit(),
           App_Stepper_Stage2_IsLimitHit());
    WriterHome_M700_Sendf(
        "ok READY id=%s action=CAL known_pose=0_135 limits_clear_required=1 pen=UP\r\n",
        WRITER_HOME_M700_BUILD_ID);
}

void WriterHome_M700_Update(void)
{
    uint32_t elapsed_ms;

    if ((s_m700_state == WRITER_HOME_M700_STATE_IDLE) ||
        (s_m700_state == WRITER_HOME_M700_STATE_WAIT_CAL) ||
        (s_m700_state == WRITER_HOME_M700_STATE_DONE) ||
        (s_m700_state == WRITER_HOME_M700_STATE_STOPPED) ||
        (s_m700_state == WRITER_HOME_M700_STATE_ERROR)) {
        return;
    }

    App_Stepper_Task();
    elapsed_ms = (uint32_t)(s_sys_tick - s_m700_state_start_ms);

    switch (s_m700_state) {
        case WRITER_HOME_M700_STATE_IDLE:
        case WRITER_HOME_M700_STATE_WAIT_CAL:
        case WRITER_HOME_M700_STATE_DONE:
        case WRITER_HOME_M700_STATE_STOPPED:
        case WRITER_HOME_M700_STATE_ERROR:
            return;

        case WRITER_HOME_M700_STATE_SEARCHING: {
            uint32_t stage1_pulses = App_Stepper_Stage1_Total_Pulses() -
                                     s_m700_stage1_start_pulses;
            uint32_t stage2_pulses = App_Stepper_Stage2_Total_Pulses() -
                                     s_m700_stage2_start_pulses;
            uint32_t max_stage1 = WriterMotion_Stage1_Arm_Deg_To_Steps(
                WRITER_HOME_M700_SEARCH_MAX_DEG);
            uint32_t max_stage2 = WriterMotion_Stage2_Arm_Deg_To_Steps(
                WRITER_HOME_M700_SEARCH_MAX_DEG);

            if ((!App_Stepper_Stage1_IsLimitHit() &&
                 (stage1_pulses > max_stage1)) ||
                (!App_Stepper_Stage2_IsLimitHit() &&
                 (stage2_pulses > max_stage2))) {
                WriterHome_M700_Stop(WRITER_HOME_M700_STATE_ERROR,
                                     "search_travel_limit");
                return;
            }
            if (elapsed_ms > WRITER_HOME_M700_SEARCH_TIMEOUT_MS) {
                WriterHome_M700_Stop(WRITER_HOME_M700_STATE_ERROR,
                                     "search_timeout");
                return;
            }
            if (App_Stepper_IsZeroing()) {
                return;
            }
            if (!App_Stepper_Stage1_IsLimitHit() ||
                !App_Stepper_Stage2_IsLimitHit()) {
                WriterHome_M700_Stop(WRITER_HOME_M700_STATE_ERROR,
                                     "search_without_both_limits");
                return;
            }

            s_m700_search_stage1[s_m700_cycle] = stage1_pulses;
            s_m700_search_stage2[s_m700_cycle] = stage2_pulses;
            if (s_m700_cycle == 0u) {
                s_m700_theta_limit_deg = APP_WRITER_CAL_THETA_DEG -
                    ((float)stage1_pulses /
                     APP_WRITER_STAGE1_STEPS_PER_DEG);
                s_m700_psi_limit_deg = APP_WRITER_CAL_PSI_DEG -
                    ((float)stage2_pulses /
                     APP_WRITER_STAGE2_STEPS_PER_DEG);
                s_m700_limit_valid = true;
            }

            elog_i("M700CAL", "[M700CAL] search_hit cycle=%u/%u s1=%u s2=%u theta_limit=%d psi_limit=%d lim1=1 lim2=1 pen=UP",
                   (uint32_t)(s_m700_cycle + 1u),
                   WRITER_HOME_M700_TOTAL_CYCLES,
                   stage1_pulses,
                   stage2_pulses,
                   WriterHome_Scale_100(s_m700_theta_limit_deg),
                   WriterHome_Scale_100(s_m700_psi_limit_deg));
            s_m700_state_start_ms = s_sys_tick;
            s_m700_state = WRITER_HOME_M700_STATE_LIMIT_SETTLE;
            return;
        }

        case WRITER_HOME_M700_STATE_LIMIT_SETTLE:
            if (!App_Stepper_Stage1_IsLimitHit() ||
                !App_Stepper_Stage2_IsLimitHit()) {
                WriterHome_M700_Stop(WRITER_HOME_M700_STATE_ERROR,
                                     "limit_unstable");
                return;
            }
            if (elapsed_ms >= APP_WRITER_HOMING_DEBOUNCE_MS) {
                WriterHome_M700_Start_Release();
            }
            return;

        case WRITER_HOME_M700_STATE_RELEASING:
            if (elapsed_ms > WRITER_HOME_M700_RELEASE_TIMEOUT_MS) {
                WriterHome_M700_Stop(WRITER_HOME_M700_STATE_ERROR,
                                     "release_timeout");
                return;
            }
            if (App_Stepper_Stage1_IsLimitHit() &&
                !BSP_Stepper_IsRunning(&App_Stepper_X)) {
                App_Stepper_Stage1_Run(
                    (uint8_t)(1u - LIMIT_STAGE1_HOME_DIR),
                    1u,
                    APP_WRITER_HOMING_LOCATE_FREQ_HZ);
            }
            if (App_Stepper_Stage2_IsLimitHit() &&
                !BSP_Stepper_IsRunning(&App_Stepper_Y)) {
                App_Stepper_Stage2_Run(
                    (uint8_t)(1u - LIMIT_STAGE2_HOME_DIR),
                    1u,
                    APP_WRITER_HOMING_LOCATE_FREQ_HZ);
            }
            if (WriterHome_M700_Limits_Clear() &&
                WriterHome_M700_Motors_Stopped()) {
                WriterHome_M700_Start_Clearance(
                    App_Stepper_Stage1_Total_Pulses() -
                        s_m700_stage1_start_pulses,
                    App_Stepper_Stage2_Total_Pulses() -
                        s_m700_stage2_start_pulses);
            }
            return;

        case WRITER_HOME_M700_STATE_CLEARANCE:
            if (elapsed_ms > WRITER_HOME_M700_RELEASE_TIMEOUT_MS) {
                WriterHome_M700_Stop(WRITER_HOME_M700_STATE_ERROR,
                                     "clearance_timeout");
                return;
            }
            if (!WriterHome_M700_Motors_Stopped()) {
                return;
            }
            if (!WriterHome_M700_Limits_Clear()) {
                WriterHome_M700_Stop(WRITER_HOME_M700_STATE_ERROR,
                                     "clearance_limit_active");
                return;
            }

            s_m700_release_stage1[s_m700_cycle] +=
                s_m700_clearance_stage1;
            s_m700_release_stage2[s_m700_cycle] +=
                s_m700_clearance_stage2;
            elog_i("M700CAL", "[M700CAL] clearance_done cycle=%u/%u away_s1=%u away_s2=%u lim1=0 lim2=0 pen=UP",
                   (uint32_t)(s_m700_cycle + 1u),
                   WRITER_HOME_M700_TOTAL_CYCLES,
                   s_m700_release_stage1[s_m700_cycle],
                   s_m700_release_stage2[s_m700_cycle]);

            if ((uint32_t)(s_m700_cycle + 1u) <
                WRITER_HOME_M700_TOTAL_CYCLES) {
                s_m700_state_start_ms = s_sys_tick;
                s_m700_state = WRITER_HOME_M700_STATE_REPEAT_DELAY;
            } else {
                WriterHome_M700_Finish();
            }
            return;

        case WRITER_HOME_M700_STATE_REPEAT_DELAY:
            if (!WriterHome_M700_Limits_Clear()) {
                WriterHome_M700_Stop(WRITER_HOME_M700_STATE_ERROR,
                                     "repeat_start_limit_active");
                return;
            }
            if (elapsed_ms >= APP_WRITER_HOMING_DEBOUNCE_MS) {
                WriterHome_M700_Start_Search((uint8_t)(s_m700_cycle + 1u));
            }
            return;

        default:
            WriterHome_M700_Stop(WRITER_HOME_M700_STATE_ERROR,
                                 "bad_state");
            return;
    }
}

static void WriterHome_M700_Send_Status(void)
{
    WriterHome_M700_Sendf(
        "ok STATUS id=%s state=%s cycle=%u/%u theta_limit_x100=%d psi_limit_x100=%d limit_valid=%d lim1=%d lim2=%d pen=UP\r\n",
        WRITER_HOME_M700_BUILD_ID,
        WriterHome_M700_State_Name(),
        (uint32_t)(s_m700_cycle + 1u),
        WRITER_HOME_M700_TOTAL_CYCLES,
        WriterHome_Scale_100(s_m700_theta_limit_deg),
        WriterHome_Scale_100(s_m700_psi_limit_deg),
        s_m700_limit_valid,
        App_Stepper_Stage1_IsLimitHit(),
        App_Stepper_Stage2_IsLimitHit());
}

bool WriterHome_M700_Process_Frame(const uint8_t *frame, uint16_t len)
{
    char command[24];
    uint16_t command_len = 0u;

    if ((frame == 0) || (len == 0u)) {
        return false;
    }

    for (uint16_t i = 0u; i < len; i++) {
        unsigned char ch = frame[i];
        if ((ch == '\0') || isspace(ch)) {
            continue;
        }
        if (command_len >= (uint16_t)(sizeof(command) - 1u)) {
            WriterHome_M700_Sendf("error:command_too_long\r\n");
            return true;
        }
        command[command_len++] = (char)toupper(ch);
    }
    command[command_len] = '\0';

    if (strcmp(command, "STATUS") == 0) {
        WriterHome_M700_Send_Status();
        return true;
    }

    if (strcmp(command, "STOP") == 0) {
        WriterHome_M700_Stop(WRITER_HOME_M700_STATE_STOPPED,
                             "user_stop");
        return true;
    }

    if ((strcmp(command, "CAL") == 0) ||
        (strcmp(command, "M700") == 0)) {
        if (s_m700_state != WRITER_HOME_M700_STATE_WAIT_CAL) {
            WriterHome_M700_Sendf(
                "error:state_%s action=STATUS_or_STOP\r\n",
                WriterHome_M700_State_Name());
            return true;
        }
        if (!WriterHome_M700_Limits_Clear()) {
            WriterHome_M700_Sendf(
                "error:known_pose_limit_active lim1=%d lim2=%d action=reposition_0_135\r\n",
                App_Stepper_Stage1_IsLimitHit(),
                App_Stepper_Stage2_IsLimitHit());
            return true;
        }
        if (!WriterHome_M700_Motors_Stopped()) {
            WriterHome_M700_Sendf("error:motor_busy\r\n");
            return true;
        }

        WriterHome_M700_Start_Search(0u);
        WriterHome_M700_Sendf(
            "ok CAL accepted id=%s cycles=%u pen=UP\r\n",
            WRITER_HOME_M700_BUILD_ID,
            WRITER_HOME_M700_TOTAL_CYCLES);
        return true;
    }

    if ((strcmp(command, "DRAW") == 0) ||
        (strcmp(command, "NEXT") == 0) ||
        (command[0] == 'G') || (command[0] == 'M')) {
        WriterHome_M700_Sendf(
            "error:motion_command_rejected calibration_only=1 pen=UP\r\n");
        return true;
    }

    WriterHome_M700_Sendf(
        "error:unsupported command=CAL_or_M700_STATUS_STOP\r\n");
    return true;
}

bool WriterHome_M700_Is_Done(void)
{
    return (s_m700_state == WRITER_HOME_M700_STATE_DONE) ||
           (s_m700_state == WRITER_HOME_M700_STATE_STOPPED) ||
           (s_m700_state == WRITER_HOME_M700_STATE_ERROR);
}

writer_home_m700_state_t WriterHome_M700_Get_State(void)
{
    return s_m700_state;
}
