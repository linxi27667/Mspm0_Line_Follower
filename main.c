#include "ti_msp_dl_config.h"
#include "main.h"
#include "app_stepper.h"
#include "app_servo.h"
#include "app_key.h"
#include "app_actuator.h"
#include "app_puzzle_frame.h"
#include "TASK/writer_rehome.h"
#include "TASK/writer_test.h"
#include "TASK/writer_cloud.h"
#include "comm_vision_uart.h"
#include "elog.h"
#include "SEGGER_RTT.h"

volatile uint32_t s_sys_tick = 0u;

#define SERVO_STARTUP_SETTLE_MS       (700u)


void SysTick_Handler(void)
{
    s_sys_tick++;
}

int main(void)
{
    bool homed = false;
    bool writer_test_started = false;
    bool rehome_result_pending = false;
    bool cloud_initialized = false;

    SYSCFG_DL_init();
    SEGGER_RTT_Init();
    elog_init();
    elog_set_fmt(ELOG_LVL_ASSERT, ELOG_FMT_LVL | ELOG_FMT_TAG | ELOG_FMT_TIME);
    elog_set_fmt(ELOG_LVL_ERROR,  ELOG_FMT_LVL | ELOG_FMT_TAG | ELOG_FMT_TIME);
    elog_set_fmt(ELOG_LVL_WARN,   ELOG_FMT_LVL | ELOG_FMT_TAG | ELOG_FMT_TIME);
    elog_set_fmt(ELOG_LVL_INFO,   ELOG_FMT_LVL | ELOG_FMT_TAG | ELOG_FMT_TIME);
    elog_set_fmt(ELOG_LVL_DEBUG,  ELOG_FMT_ALL & ~ELOG_FMT_FUNC);
    elog_start();
    SysTick_Config(CPUCLK_FREQ / 1000u);
    App_Key_Init(s_sys_tick);
    if (!App_Actuator_Init()) {
        elog_e("BOOT", "actuator driver init failed; outputs forced off");
        App_Actuator_AllOutputsOff();
        while (1) {
            __WFI();
        }
    }

    elog_i("LOG", "EasyLogger output=SEGGER_RTT channel=0 level=VERBOSE");
    elog_i("BOOT", "writer_robot bare-metal start");
    elog_i("PIN", "STAGE1=PA10/PA11 STAGE2=PA8/PA9 SERVO=PA12 UART1_TX=PB4 UART1_RX=PB5 STAGE1_LIMIT=PA26 STAGE2_LIMIT=PA27");
    elog_i("ACT",
           "ROTATE_PWM=PA7 AIN1=PB0 AIN2=PB1 STBY=3V3 "
           "ENC_A=PB11 ENC_B=PB14 ENC_IRQ=DISABLED "
           "MAGNET=PA30 LED=PB10 BUZZER=PA2 outputs=OFF");
    elog_i("KEY", "active_low pull_up debounce_ms=%u KEY1_REHOME=PB26 KEY2_AREA_MARK=PA29 KEY3_ORIGIN_MARK=PB23 KEY4_RESERVED=PB27",
           APP_KEY_DEBOUNCE_MS);
    elog_i("FRAME",
           "machine_home=%s paper_zero=P4 paper_frame=%s "
           "axes=X_RIGHT_Y_DOWN "
           "paper_region=TRAPEZOID_0_0__199_0__160_243__40_243 "
           "relation=INDEPENDENT",
           APP_PUZZLE_MACHINE_HOME_TEXT,
           APP_PUZZLE_PAPER_FRAME_TEXT);
    elog_i("CFG", "CPUCLK=%uHz STEP1_CLK=%uHz STEP2_CLK=%uHz", CPUCLK_FREQ, STEPPER_X_PWM_CLK_FREQ, STEPPER_Y_PWM_CLK_FREQ);
    App_Vision_UART_Init();
    if (App_Servo_System_Init() != 0) {
        elog_e("BOOT", "servo init failed; writer test locked");
        while (1) {
            App_Vision_UART_Task();
        }
    }
    elog_i("SERVO", "startup PEN_UP angle=%d settle_ms=%u",
           (int32_t)(APP_SERVO_PEN_UP_ANGLE_DEG * 100.0f),
           SERVO_STARTUP_SETTLE_MS);
    {
        uint32_t servo_start_ms = s_sys_tick;
        while ((uint32_t)(s_sys_tick - servo_start_ms) <
               SERVO_STARTUP_SETTLE_MS) {
        }
    }
    WriterRehome_Init();
    if (WriterRehome_Start()) {
        rehome_result_pending = true;
    } else {
        App_Servo_Pen_Up();
        elog_e("BOOT",
               "nonblocking homing start failed; KEY1 can retry");
    }

    while (1) {
        App_Key_Update(s_sys_tick);
        if (App_Key_Take_Press(APP_KEY_1_REHOME)) {
            /*
             * KEY1 has priority over every other panel action. It can also
             * restart a homing pass that is currently searching.
             */
            App_Key_Clear_Events();
            elog_w("KEY",
                   "KEY1 PB26 accepted action=NONBLOCKING_FULL_REHOME "
                   "zero_type=MECHANICAL_HOME paper_zero=UNCHANGED");
            if (WriterRehome_Is_Active()) {
                WriterRehome_Abort();
            }
            if (writer_test_started) {
                WriterTest_Abort_For_Rehome();
                writer_test_started = false;
            }
            if (cloud_initialized) {
                WriterCloud_Init(false);
            } else {
                WriterRehome_Init();
            }
            homed = false;
            if (WriterRehome_Start()) {
                rehome_result_pending = true;
                elog_w("KEY",
                       "KEY1 FULL_REHOME result=STARTED keys_active=1");
            } else {
                rehome_result_pending = false;
                App_Servo_Pen_Up();
                elog_e("KEY",
                       "KEY1 FULL_REHOME result=START_REJECTED pen=UP");
            }
            continue;
        }

        if (WriterRehome_Is_Active()) {
            if (App_Key_Take_Press(APP_KEY_2_AREA_MARK)) {
                elog_w("KEY",
                       "KEY2 PA29 rejected reason=HOMING_ACTIVE");
            }
            if (App_Key_Take_Press(APP_KEY_3_ORIGIN_MARK)) {
                elog_w("KEY",
                       "KEY3 PB23 rejected reason=HOMING_ACTIVE");
            }
            if (App_Key_Take_Press(APP_KEY_4_RESERVED)) {
                elog_i("KEY",
                       "KEY4 PB27 pressed action=RESERVED homing_active=1");
            }
            WriterRehome_Update();
            App_Vision_UART_Task();
            continue;
        }

        if (rehome_result_pending) {
            rehome_result_pending = false;
            if (WriterRehome_Is_Succeeded()) {
                homed = true;
                WriterTest_Start();
                writer_test_started = true;
                if (cloud_initialized) {
                    WriterCloud_Init(true);
                }
                elog_i("BOOT",
                       "mechanical_homing complete machine_home=%s "
                       "paper_zero=P4 paper_frame=%s panel_actions=UNLOCKED",
                       APP_PUZZLE_MACHINE_HOME_TEXT,
                       APP_PUZZLE_PAPER_FRAME_TEXT);
            } else {
                writer_rehome_state_t failed_state =
                    WriterRehome_Get_State();

                homed = false;
                App_Servo_Pen_Up();
                elog_e("BOOT",
                       "homing failed state=%u; KEY1 can retry",
                       (uint32_t)failed_state);
            }
        }

        if (!homed) {
            if (App_Key_Take_Press(APP_KEY_2_AREA_MARK)) {
                elog_w("KEY",
                       "KEY2 PA29 rejected reason=HOME_REQUIRED");
            }
            if (App_Key_Take_Press(APP_KEY_3_ORIGIN_MARK)) {
                elog_w("KEY",
                       "KEY3 PB23 rejected reason=HOME_REQUIRED");
            }
            if (App_Key_Take_Press(APP_KEY_4_RESERVED)) {
                elog_i("KEY",
                       "KEY4 PB27 pressed action=RESERVED home_required=1");
            }
            if (!cloud_initialized) {
                WriterCloud_Init(false);
                cloud_initialized = true;
            }
            if (WriterCloud_Is_Enabled()) {
                WriterCloud_Update();
            } else {
                App_Vision_UART_Task();
            }
            continue;
        }

        if (App_Key_Take_Press(APP_KEY_2_AREA_MARK)) {
            if (WriterTest_Trigger_Puzzle_Area_Marks()) {
                elog_i("KEY", "KEY2 PA29 accepted action=AREA_4CORNER_MARK");
            } else {
                elog_w("KEY", "KEY2 PA29 rejected reason=TASK_BUSY_OR_REHOME_REQUIRED");
            }
        }
        if (App_Key_Take_Press(APP_KEY_3_ORIGIN_MARK)) {
            if (WriterTest_Trigger_Paper_Origin_Mark()) {
                elog_i("KEY",
                       "KEY3 PB23 accepted action=PAPER_ZERO_MARK "
                       "origin=P4 frame=%s paper_x100=0 paper_y100=0 "
                       "machine_home=%s",
                       APP_PUZZLE_PAPER_FRAME_TEXT,
                       APP_PUZZLE_MACHINE_HOME_TEXT);
            } else {
                elog_w("KEY",
                       "KEY3 PB23 rejected "
                       "reason=TASK_BUSY_OR_REHOME_REQUIRED");
            }
        }
        if (App_Key_Take_Press(APP_KEY_4_RESERVED)) {
            elog_i("KEY", "KEY4 PB27 pressed action=RESERVED");
        }

        if (!cloud_initialized) {
            App_Vision_UART_Task();
            WriterTest_Update();
            if (WriterTest_Startup_Is_Complete()) {
                bool startup_ok = WriterTest_Startup_Succeeded();

                WriterCloud_Init(startup_ok);
                cloud_initialized = true;
                if (startup_ok) {
#if WRITER_TEST_BOOT_PATROL_4DOT_ENABLE
                    elog_i("BOOT", "startup patrol complete; cloud and G-code unlocked");
#else
                    elog_i("BOOT", "startup patrol disabled; cloud and G-code unlocked");
#endif
                } else {
                    elog_e("BOOT", "startup patrol failed; cloud online with needs_rehome=1");
                }
            }
            continue;
        }
        if (WriterCloud_Is_Enabled()) {
            WriterCloud_Update();
        } else {
            App_Vision_UART_Task();
        }
        WriterTest_Update();
    }
}
