import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def compile_and_run(source: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory(prefix="track_logic_test_") as tmpdir:
        tmp = Path(tmpdir) / "_track_logic_test.c"
        exe = Path(tmpdir) / "_track_logic_test.exe"
        tmp.write_text(source, encoding="utf-8")
        compile_result = subprocess.run(
            ["gcc", "-std=c99", "-Wall", "-Wextra", "-I", str(ROOT), str(tmp), "-o", str(exe)],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=ROOT,
        )
        if compile_result.returncode != 0:
            return compile_result
        return subprocess.run(
            [str(exe)],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=ROOT,
        )


class TrackLogicTests(unittest.TestCase):
    def test_line_error_uses_only_digital_channel_weights(self):
        result = compile_and_run(
            r'''
            #include "TASK/track_logic.h"

            int main(void) {
                float centered = Track_ComputeDigitalLineError8(0x18u, 2.0f);
                if (centered < -0.01f || centered > 0.01f) return 1;
                if (Track_ComputeDigitalLineError8(0x00u, -1.25f) != -1.25f) return 2;
                if (Track_ComputeDigitalLineError8(0x06u, 0.0f) != -2.0f) return 3;
                if (Track_ComputeDigitalLineError8(0x60u, 0.0f) != 2.0f) return 4;
                if (Track_ComputeDigitalLineError8(0x08u, 0.0f) != -0.5f) return 5;
                if (Track_ComputeDigitalLineError8(0x10u, 0.0f) != 0.5f) return 6;
                return 0;
            }
            '''
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_line_classifier_is_symmetric_and_rejects_split_patterns(self):
        result = compile_and_run(
            r'''
            #include "TASK/track_logic.h"

            int main(void) {
                track_line_observation_t center = Track_ClassifyLine8(0x18u, 3.0f, 4u);
                track_line_observation_t left = Track_ClassifyLine8(0x0Cu, 0.0f, 4u);
                track_line_observation_t right = Track_ClassifyLine8(0x30u, 0.0f, 4u);
                if (center.type != TRACK_LINE_NORMAL || center.error != 0.0f) return 1;
                if (left.type != TRACK_LINE_NORMAL || right.type != TRACK_LINE_NORMAL) return 2;
                if (left.error != -right.error || left.error != -1.0f) return 3;
                if (Track_ClassifyLine8(0x00u, 1.25f, 4u).type != TRACK_LINE_LOST) return 4;
                if (Track_ClassifyLine8(0x81u, 1.25f, 4u).type != TRACK_LINE_INVALID) return 5;
                if (Track_ClassifyLine8(0xFFu, 1.25f, 4u).type != TRACK_LINE_INVALID) return 6;
                if (Track_ClassifyLine8(0x0Eu, 0.0f, 4u).type != TRACK_LINE_NORMAL) return 7;
                if (Track_ClassifyLine8(0x0Fu, 0.0f, 4u).type != TRACK_LINE_INVALID) return 8;
                if (Track_ClassifyLine8(0x1Eu, 0.0f, 4u).type != TRACK_LINE_LEFT_CORNER) return 9;
                return 0;
            }
            '''
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_corner_and_capture_require_continuous_frames(self):
        result = compile_and_run(
            r'''
            #include "TASK/track_logic.h"

            int main(void) {
                uint8_t corner = 0u;
                uint8_t capture = 0u;
                track_line_observation_t good = Track_ClassifyLine8(0x18u, 0.0f, 4u);
                track_line_observation_t bad = Track_ClassifyLine8(0x81u, 0.0f, 4u);
                corner = Track_UpdateCornerConfirm(corner, 1u, true);
                if (corner != 0u) return 1;
                corner = Track_UpdateCornerConfirm(corner, 2u, true);
                corner = Track_UpdateCornerConfirm(corner, 2u, true);
                if (corner != 2u) return 2;
                corner = Track_UpdateCornerConfirm(corner, 2u, false);
                if (corner != 0u) return 3;
                for (int i = 0; i < 2; ++i) {
                    capture = Track_UpdateConfirmFrames(
                        capture, Track_CaptureLineValid(good, 1.0f));
                }
                if (capture != 2u) return 4;
                capture = Track_UpdateConfirmFrames(
                    capture, Track_CaptureLineValid(bad, 1.0f));
                if (capture != 0u) return 5;
                return 0;
            }
            '''
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_encoder_distance_is_independent_and_wrap_safe(self):
        result = compile_and_run(
            r'''
            #include <stdint.h>
            #include "TASK/track_logic.h"

            int main(void) {
                int32_t start = INT32_MAX - 10;
                int32_t current = (int32_t)((uint32_t)start + 40u);
                if (Track_EncoderDelta(current, start) != 40) return 1;
                if (!Track_EncoderDistanceReached(200, 100, 0, 0,
                                                   2.0f, 1.0f, 100.0f)) return 2;
                if (Track_EncoderDistanceReached(200, 50, 0, 0,
                                                  2.0f, 1.0f, 100.0f)) return 3;
                if (Track_EncoderDistanceReached(200, 100, 0, 0,
                                                  0.0f, 1.0f, 10.0f)) return 4;
                return 0;
            }
            '''
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_all_eight_calibration_channels_must_have_contrast(self):
        result = compile_and_run(
            r'''
            #include "BSP/Inc/bsp_grayscale.h"

            int main(void) {
                uint16_t white[8] = {1200,1200,1200,1200,1200,1200,1200,1200};
                uint16_t black[8] = {400,400,400,400,400,400,400,400};
                if (!Bsp_Grayscale_ContrastValid8(white, black, 200u)) return 1;
                black[6] = 1050u;
                if (Bsp_Grayscale_ContrastValid8(white, black, 200u)) return 2;
                black[6] = 1400u;
                if (!Bsp_Grayscale_ContrastValid8(white, black, 200u)) return 3;
                return 0;
            }
            '''
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_periodic_logs_are_gated_by_motion_state(self):
        source = (ROOT / "main.c").read_text(encoding="utf-8")
        vehicle_log = source.split("static void Main_LogVehicleStatus", 1)[1].split(
            "static void Main_LogGrayscale", 1
        )[0]
        grayscale_log = source.split("static void Main_LogGrayscale", 1)[1].split(
            "static void Main_HandleKeyPush", 1
        )[0]

        self.assertIn("if (!Track_State_Allows_Motor(Track.state)) return;", vehicle_log)
        self.assertIn("if (!Track_State_Is_LineTracking(Track.state)) return;", grayscale_log)

    def test_safety_health_and_ready_gate(self):
        result = compile_and_run(
            r'''
            #include <stdint.h>
            #include "APP/Inc/safety_logic.h"

            int main(void) {
                safety_health_t h = {0};
                h.encoder_left_ok = true;
                h.encoder_right_ok = true;
                h.remote_armed = true;
                h.heartbeat_seen = true;
                h.last_heartbeat_tick = 100u;
                h.last_control_tick = 180u;
                if (Safety_Logic_Check(200u, &h, 500u, 50u, 25u) != SAFETY_LOGIC_OK) return 1;
                if (Safety_Logic_Check(601u, &h, 500u, 50u, 25u) != SAFETY_LOGIC_HEARTBEAT_LOST) return 2;
                h.last_heartbeat_tick = UINT32_MAX - 10u;
                h.last_control_tick = 4u;
                if (Safety_Logic_Check(9u, &h, 500u, 50u, 25u) != SAFETY_LOGIC_OK) return 3;
                h.encoder_left_ok = false;
                if (Safety_Logic_Check(9u, &h, 500u, 50u, 25u) != SAFETY_LOGIC_ENCODER_ANOMALY) return 4;
                h.encoder_left_ok = true;
                h.grayscale_required = true;
                h.grayscale_seen = true;
                h.last_grayscale_tick = UINT32_MAX - 10u;
                if (Safety_Logic_Check(9u, &h, 500u, 50u, 25u) != SAFETY_LOGIC_OK) return 7;
                if (Safety_Logic_Check(50u, &h, 500u, 50u, 100u) != SAFETY_LOGIC_GRAYSCALE_EXPIRED) return 8;
                if (!Safety_Logic_CanEnterRotation(0u) ||
                    !Safety_Logic_CanEnterRotation(2u)) return 5;
                if (Safety_Logic_CanEnterRotation(1u) ||
                    Safety_Logic_CanEnterRotation(3u) ||
                    Safety_Logic_CanEnterRotation(4u)) return 6;
                if (Safety_Logic_FinishedHoldElapsed(1999u, 1000u, 1000u)) return 9;
                if (!Safety_Logic_FinishedHoldElapsed(2000u, 1000u, 1000u)) return 10;
                if (!Safety_Logic_FinishedHoldElapsed(3u, UINT32_MAX - 996u, 1000u)) return 11;
                return 0;
            }
            '''
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_encoder_stall_and_impossible_delta_are_faults(self):
        result = compile_and_run(
            r'''
            #include "APP/Inc/encoder_health_logic.h"

            int main(void) {
                encoder_health_monitor_t h = {0};
                for (int i = 0; i < 39; ++i) {
                    if (!Encoder_Health_UpdateSide(20, 0, 8, 20000, 40, &h.left_stall_ticks)) return 1;
                }
                if (Encoder_Health_UpdateSide(20, 0, 8, 20000, 40, &h.left_stall_ticks)) return 2;
                if (!Encoder_Health_UpdateSide(20, 3, 8, 20000, 40, &h.left_stall_ticks)) return 3;
                if (h.left_stall_ticks != 0) return 4;
                if (Encoder_Health_UpdateSide(20, 20001, 8, 20000, 40, &h.left_stall_ticks)) return 5;
                if (!Encoder_Health_UpdateSide(0, 0, 8, 20000, 40, &h.left_stall_ticks)) return 6;
                return 0;
            }
            '''
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_gpio_quadrature_decoder_counts_all_four_edges(self):
        result = compile_and_run(
            r'''
            #include "APP/Inc/encoder_quadrature_logic.h"

            int main(void) {
                const unsigned char forward[] = {0u, 2u, 3u, 1u, 0u};
                const unsigned char reverse[] = {0u, 1u, 3u, 2u, 0u};
                int forward_sum = 0;
                int reverse_sum = 0;
                for (int i = 1; i < 5; ++i) {
                    forward_sum += Encoder_Quadrature_Delta(forward[i - 1], forward[i]);
                    reverse_sum += Encoder_Quadrature_Delta(reverse[i - 1], reverse[i]);
                }
                if (forward_sum != 4) return 1;
                if (reverse_sum != -4) return 2;
                if (Encoder_Quadrature_Delta(0u, 3u) != 0) return 3;
                if (Encoder_Quadrature_Delta(2u, 2u) != 0) return 4;
                return 0;
            }
            '''
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_sysconfig_uses_symmetric_gpio_quadrature_inputs(self):
        syscfg = (ROOT / "TI_moban.syscfg").read_text(encoding="utf-8")
        generated = (ROOT / "ti_msp_dl_config.c").read_text(encoding="utf-8")
        motor_source = (ROOT / "APP" / "Src" / "app_encoder_motor.c").read_text(
            encoding="utf-8"
        )

        self.assertNotIn('addModule("/ti/driverlib/QEI"', syscfg)
        for group in ("GPIO9", "GPIO11"):
            for channel in (0, 1):
                prefix = f"{group}.associatedPins[{channel}]"
                self.assertIn(f"{prefix}.interruptEn", syscfg)
                self.assertIn(f'{prefix}.polarity         = "RISE_FALL"', syscfg)
        self.assertIn("DL_GPIO_setUpperPinsPolarity", generated)
        self.assertIn("LEFT_ENC_PHA_PIN | LEFT_ENC_PHB_PIN", motor_source)
        self.assertIn("RIGHT_ENC_PHA_PIN | RIGHT_ENC_PHB_PIN", motor_source)

    def test_motor_bench_test_is_nonblocking_bounded_and_stoppable(self):
        track_source = (ROOT / "TASK" / "track.c").read_text(encoding="utf-8")
        tuning_source = (ROOT / "APP" / "Src" / "app_tuning.c").read_text(
            encoding="utf-8"
        )
        start = track_source.split("bool Track_Start_Motor_Test", 1)[1].split(
            "bool Track_Is_Motor_Test", 1
        )[0]
        handler = track_source.split("static void Track_Handle_Motor_Test", 1)[1].split(
            "static void Track_Handle_Heading_Hold", 1
        )[0]

        self.assertIn("Safety_TransitionToBenchTest", start)
        self.assertIn("App_Motor_Enable_Speed_PID(false);", start)
        self.assertIn("TRACK_MOTOR_TEST_TIMEOUT_MS", handler)
        self.assertIn("encoder_sign_or_stall", handler)
        self.assertIn("App_Motor_Enable_Speed_PID(true);", handler)
        self.assertNotIn("Bsp_Delay_ms", handler)
        self.assertIn('strcmp(cmd, "motor_test") == 0', tuning_source)
        self.assertIn('find_bool(json, "lifted", &lifted)', tuning_source)
        self.assertIn('Track_Motor_Test_End("stopped")', track_source)

    def test_motion_rejections_are_specific_and_faults_auto_recover(self):
        tuning_source = (ROOT / "APP" / "Src" / "app_tuning.c").read_text(
            encoding="utf-8"
        )
        safety_source = (ROOT / "APP" / "Src" / "app_safety.c").read_text(
            encoding="utf-8"
        )
        main_source = (ROOT / "main.c").read_text(encoding="utf-8")
        motor_start = (ROOT / "TASK" / "track.c").read_text(
            encoding="utf-8"
        ).split("bool Track_Start_Motor_Test", 1)[1].split(
            "bool Track_Is_Motor_Test", 1
        )[0]

        self.assertNotIn("safety_not_ready", tuning_source)
        self.assertIn('"grayscale_not_ready"', tuning_source)
        self.assertIn('"link_not_ready"', tuning_source)
        self.assertIn('"motion_busy"', tuning_source)
        self.assertIn("SAFETY_STATE_BOOT", motor_start)
        self.assertIn('elog_w("MOTION", "motion stopped: %s (auto recovery)"',
                      safety_source)
        self.assertIn("Safety_ClearFault();", main_source)

        common_header = (ROOT / "APP" / "Inc" / "app_common.h").read_text(
            encoding="utf-8"
        )
        host_config = (ROOT / "host" / "config.py").read_text(encoding="utf-8")
        self.assertIn("APP_TUNING_HEARTBEAT_TIMEOUT_MS   1500u", common_header)
        self.assertIn("HEARTBEAT_INTERVAL_MS = 250", host_config)

    def test_right_angle_heading_lock_requires_angle_and_rate(self):
        result = compile_and_run(
            r'''
            #include <stdbool.h>
            #include "TASK/track_logic.h"

            int main(void) {
                if (!Track_RightAngle_HeadingSettled(3.0f, 12.0f)) return 1;
                if (Track_RightAngle_HeadingSettled(3.1f, 0.0f)) return 2;
                if (Track_RightAngle_HeadingSettled(0.0f, 12.1f)) return 3;
                return 0;
            }
            '''
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_square_corner_accepts_only_counterclockwise_left_chain(self):
        result = compile_and_run(
            r'''
            #include <stdbool.h>
            #include "TASK/track_logic.h"

            int main(void) {
                if (Track_SquareLeftCorner(0x03u, 3u)) return 1;
                if (Track_SquareLeftCorner(0x18u, 3u)) return 2;
                /* 0x0E=S1/S2/S3: captured real-car straight-line drift. */
                if (Track_SquareLeftCorner(0x0Eu, 3u)) return 3;
                if (Track_SquareLeftCorner(0x70u, 3u)) return 4;
                if (Track_SquareLeftCorner(0xFFu, 3u)) return 5;
                if (!Track_SquareLeftCorner(0x1Eu, 4u)) return 6;
                if (!Track_SquareLeftCorner(0x1Fu, 4u)) return 7;
                if (Track_SquareLeftCorner(0x1Eu, 5u)) return 8;
                return 0;
            }
            '''
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_start_pattern_requires_one_to_three_centered_black_channels(self):
        result = compile_and_run(
            r'''
            #include "TASK/track_logic.h"

            int main(void) {
                if (Track_StartPatternValid(0x00u)) return 1;
                if (!Track_StartPatternValid(0x04u)) return 2;
                if (!Track_StartPatternValid(0x18u)) return 3;
                if (!Track_StartPatternValid(0x38u)) return 4;
                if (Track_StartPatternValid(0x03u)) return 5;
                if (Track_StartPatternValid(0x3Cu)) return 6;
                if (Track_StartPatternValid(0xFFu)) return 7;
                return 0;
            }
            '''
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_corner_phases_pivot_pwm_and_lap_count(self):
        result = compile_and_run(
            r'''
            #include "TASK/track_logic.h"

            int main(void) {
                uint8_t frames = 0;
                frames = Track_UpdateConfirmFrames(frames, true);
                frames = Track_UpdateConfirmFrames(frames, true);
                if (frames != 2u) return 1;
                frames = Track_UpdateConfirmFrames(frames, false);
                if (frames != 0u) return 2;
                if (Track_RightAngle_PivotPwm(90.0f, 0.0f, 0.8f, 0.08f, 28, 50) != 50) return 10;
                if (Track_RightAngle_PivotPwm(-90.0f, 0.0f, 0.8f, 0.08f, 28, 50) != -50) return 11;
                if (Track_RightAngle_PivotPwm(4.0f, 0.0f, 0.8f, 0.08f, 28, 50) != 28) return 12;
                if (Track_RightAngle_PivotPwm(3.0f, 0.0f, 0.8f, 0.08f, 28, 50) != 0) return 13;
                for (uint8_t laps = 1u; laps <= 5u; laps++) {
                    uint16_t corners = (uint16_t)laps * 4u;
                    if (Track_CornersComplete((uint16_t)(corners - 1u), laps)) return 6;
                    if (!Track_CornersComplete(corners, laps)) return 7;
                    if (Track_CirclesFromCorners(corners, laps) != laps) return 8;
                }
                return 0;
            }
            '''
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_square_runtime_does_not_dispatch_legacy_track_states(self):
        source = (ROOT / "TASK" / "track.c").read_text(encoding="utf-8")
        update_switch = source.split("switch (Track.state)", 1)[1].split(
            "if (!Track_State_Allows_Motor", 1
        )[0]
        self.assertNotIn("case TRACK_STATE_START_LINE", update_switch)
        self.assertNotIn("case TRACK_STATE_CROSS", update_switch)
        timeout = source.split('APP_TRACK_LOG_W("TRACK", "CORNER_FAIL reason=timeout', 1)[0].rsplit(
            "if (Track_Timeout_Reached(now, Track.corner_started_at", 1
        )[1]
        self.assertNotIn("right_angle_count++", timeout)
        self.assertIn("Track.state = TRACK_STATE_FINISHED;", timeout)
        self.assertIn("Track_Motor_Stop_Immediate();", timeout)
        self.assertIn("Track.corner_phase == TRACK_CORNER_PIVOT", source)
        self.assertIn("Track_EncoderDistanceReached", source)
        self.assertNotIn("USER_RIGHT_ANGLE_APPROACH_MS", source)
        self.assertIn("App_Motor_Enable_Speed_PID(false);", source)
        self.assertIn("TRACK_MOTOR_INNER_MIN", source)

    def test_line_lost_stops_safety_and_manual_stop_returns_ready(self):
        track_source = (ROOT / "TASK" / "track.c").read_text(encoding="utf-8")
        line_lost = track_source.split("static void Track_Handle_LineLost", 1)[1].split(
            "static void Track_Handle_RightAngle", 1
        )[0]
        stop = track_source.split("void Track_Stop(void)", 1)[1].split(
            "bool Track_Start_Rotation", 1
        )[0]
        self.assertIn("Safety_TransitionToFinished();", line_lost)
        self.assertLess(
            stop.index("Safety_TransitionToFinished();"),
            stop.index("Safety_TransitionToReady();"),
        )
        self.assertIn("Safety_ClearFault();", stop)

        tuning_source = (ROOT / "APP" / "Src" / "app_tuning.c").read_text(
            encoding="utf-8"
        )
        start = tuning_source.split('strcmp(cmd, "start") == 0', 1)[1].split(
            'strcmp(cmd, "stop") == 0', 1
        )[0]
        self.assertNotIn("SAFETY_STATE_FINISHED", start)

    def test_start_validation_precedes_motor_arm_and_rejection_is_acked(self):
        track_source = (ROOT / "TASK" / "track.c").read_text(encoding="utf-8")
        start = track_source.split("bool Track_Start(void)", 1)[1].split(
            "void Track_Stop(void)", 1
        )[0]
        self.assertLess(
            start.index("Track_StartPatternValid"),
            start.index("Safety_TransitionToRunning"),
        )

        tuning_source = (ROOT / "APP" / "Src" / "app_tuning.c").read_text(
            encoding="utf-8"
        )
        self.assertIn("*error = Track_Get_Start_Result();", tuning_source)

    def test_timing_state_and_direction_helpers(self):
        result = compile_and_run(
            r'''
            #include <stdint.h>
            #include "TASK/track_logic.h"

            int main(void) {
                if (Track_State_Allows_Motor(TRACK_STATE_IDLE)) return 1;
                if (!Track_State_Allows_Motor(TRACK_STATE_LINE_FOLLOW)) return 2;
                if (Track_State_Allows_Motor(TRACK_STATE_FINISHED)) return 3;
                if (Track_State_Is_LineTracking(TRACK_STATE_IDLE)) return 4;
                if (!Track_State_Is_LineTracking(TRACK_STATE_LINE_FOLLOW)) return 5;
                if (!Track_State_Is_LineTracking(TRACK_STATE_RIGHT_ANGLE)) return 6;
                if (!Track_State_Is_LineTracking(TRACK_STATE_LINE_LOST)) return 7;
                if (!Track_State_Is_LineTracking(TRACK_STATE_START_LINE)) return 8;
                if (!Track_State_Is_LineTracking(TRACK_STATE_CROSS)) return 9;
                if (Track_State_Is_LineTracking(TRACK_STATE_ROTATE)) return 10;
                if (Track_State_Is_LineTracking(TRACK_STATE_HEADING_HOLD)) return 11;
                if (Track_State_Is_LineTracking(TRACK_STATE_FINISHED)) return 12;
                if (Track_Timeout_Reached(1049u, 1000u, 50u)) return 13;
                if (!Track_Timeout_Reached(1050u, 1000u, 50u)) return 14;
                if (!Track_Timeout_Reached(3u, UINT32_MAX - 5u, 8u)) return 15;
                if (Track_LineTurn_WithGyroDamping(-12.0f, 20.0f, 0.15f) != -9.0f) return 19;
                if (Track_LineTurn_WithGyroDamping(12.0f, -20.0f, 0.15f) != 9.0f) return 20;
                return 0;
            }
            '''
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_rotate_logic_validates_direction_and_completion(self):
        result = compile_and_run(
            r'''
            #include "TASK/track_logic.h"

            int main(void) {
                int32_t left = 0, right = 0;
                if (!Track_Rotate_TargetValid(90.0f)) return 1;
                if (Track_Rotate_TargetValid(0.0f)) return 2;
                if (Track_Rotate_TargetValid(180.1f)) return 3;
                if (Track_Rotate_Error(100.0f, 130.0f, 90.0f) != 60.0f) return 4;
                if (!Track_Rotate_Complete(3.0f, 6.0f)) return 5;
                if (Track_Rotate_Complete(3.1f, 0.0f)) return 6;
                if (!Track_Rotate_AngleInside(-3.0f)) return 9;
                if (Track_Rotate_AngleInside(3.1f)) return 10;
                if (Track_Rotate_SpeedLimit(20.0f, 20.0f, 40.0f, 5.0f, 16.0f) != 5.0f) return 11;
                if (Track_Rotate_SpeedLimit(40.0f, 20.0f, 40.0f, 5.0f, 16.0f) != 16.0f) return 12;
                if (Track_Rotate_SpeedLimit(30.0f, 20.0f, 40.0f, 5.0f, 16.0f) != 10.5f) return 13;
                Track_Rotate_Command(90.0f, 30, &left, &right);
                if (left >= 0 || right <= 0) return 7;
                Track_Rotate_Command(-90.0f, 30, &left, &right);
                return (left > 0 && right < 0) ? 0 : 8;
            }
            '''
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_rotate_slew_crosses_zero_before_reversing(self):
        result = compile_and_run(
            r'''
            #include "TASK/track_logic.h"

            int main(void) {
                int32_t value = -2;
                value = Track_Slew_Command(value, 8, 1);
                if (value != -1) return 1;
                value = Track_Slew_Command(value, 8, 1);
                if (value != 0) return 2;
                value = Track_Slew_Command(value, 8, 1);
                if (value != 1) return 3;
                if (Track_Slew_Command(7, 8, 2) != 8) return 4;
                return Track_Slew_Command(5, 0, 1) == 0 ? 0 : 5;
            }
            '''
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_manual_rotation_uses_low_slip_speed_envelope(self):
        tuning = (ROOT / "APP" / "Inc" / "user_tuning.h").read_text(
            encoding="utf-8"
        )
        self.assertIn("USER_ROTATE_PID_MAX_SPEED        8.0f", tuning)
        self.assertIn("USER_ROTATE_PID_MIN_SPEED       5", tuning)
        self.assertIn("USER_ROTATE_PID_FINE_ZONE_DEG    25.0f", tuning)
        self.assertIn("USER_ROTATE_PID_BLEND_ZONE_DEG   60.0f", tuning)
        self.assertIn("USER_RIGHT_ANGLE_PIVOT_MAX_PWM    40", tuning)

    def test_rotation_requires_twenty_continuous_settle_frames(self):
        result = compile_and_run(
            r'''
            #include "TASK/track_logic.h"

            int main(void) {
                uint8_t frames = 0;
                for (int i = 0; i < 19; ++i) {
                    frames = Track_Rotate_UpdateSettleFrames(frames, true);
                }
                if (Track_Rotate_Settled(frames, 20u)) return 1;
                frames = Track_Rotate_UpdateSettleFrames(frames, false);
                if (frames != 0u) return 2;
                for (int i = 0; i < 20; ++i) {
                    frames = Track_Rotate_UpdateSettleFrames(frames, true);
                }
                return Track_Rotate_Settled(frames, 20u) ? 0 : 3;
            }
            '''
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_speed_pwm_never_reverses_requested_direction(self):
        result = compile_and_run(
            r'''
            #include "APP/Inc/motor_speed_logic.h"

            int main(void) {
                if (Motor_Speed_ConstrainPwm(-12, 28, 24) != 0) return 1;
                if (Motor_Speed_ConstrainPwm(12, -28, 24) != 0) return 2;
                if (Motor_Speed_ConstrainPwm(-12, -8, 24) != -24) return 3;
                if (Motor_Speed_ConstrainPwm(12, 8, 24) != 24) return 4;
                if (Motor_Speed_ConstrainPwm(0, 90, 24) != 0) return 5;
                return 0;
            }
            '''
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_tracking_speed_pi_is_default_and_encoder_monitoring_stays_active(self):
        track_source = (ROOT / "TASK" / "track.c").read_text(encoding="utf-8")
        start = track_source.split("bool Track_Start(void)", 1)[1].split(
            "void Track_Stop(void)", 1
        )[0]
        output = track_source.split("static void Track_Motor_Output", 1)[1].split(
            "void Track_Init", 1
        )[0]
        self.assertIn("App_Motor_Enable_Speed_PID(Track.use_speed_pid);", start)
        self.assertIn("USER_TRACK_SPEED_PID_ENABLE 1", (ROOT / "APP/Inc/user_tuning.h").read_text(encoding="utf-8"))
        self.assertIn("App_Motor_Enable_Speed_PID(true);", track_source)
        self.assertIn("Motor_Set_Speed(Track.left_speed);", output)
        self.assertIn("Motor_Right_Set_Speed(Track.right_speed);", output)

        motor_source = (ROOT / "APP" / "Src" / "app_encoder_motor.c").read_text(
            encoding="utf-8"
        )
        update = motor_source.split("static void Speed_PID_Update_Single", 1)[1].split(
            "void App_Motor_Speed_PID_Update", 1
        )[0]
        self.assertLess(
            update.index("Bsp_Motor_Update_Status(motor);"),
            update.index("if (!motor->use_speed_pid) return;"),
        )

    def test_five_white_frames_finish_without_counting_a_corner(self):
        source = (ROOT / "TASK" / "track.c").read_text(encoding="utf-8")
        detect = source.split("static void Track_Detect_Pattern", 1)[1].split(
            "static void Track_Motor_Stop_Immediate", 1
        )[0]
        lost = source.split("static void Track_Handle_LineLost", 1)[1].split(
            "static void Track_Handle_RightAngle", 1
        )[0]
        self.assertIn("TRACK_LINE_LOST_CONFIRM_FRAMES", detect)
        self.assertIn("Track.state = TRACK_STATE_LINE_LOST;", detect)
        self.assertIn("Track.state = TRACK_STATE_FINISHED;", lost)
        self.assertIn("Track_Motor_Stop_Immediate();", lost)
        self.assertNotIn("right_angle_count", lost)
        self.assertNotIn("search", lost.lower())

    def test_rotate_timeout_is_wrap_safe(self):
        result = compile_and_run(
            r'''
            #include <stdint.h>
            #include "TASK/track_logic.h"

            int main(void) {
                return Track_Rotate_Timeout(20u, UINT32_MAX - 9u, 30u) ? 0 : 1;
            }
            '''
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_imu_health_gate_rejects_uncalibrated_or_invalid_data(self):
        result = compile_and_run(
            r'''
            #include <stdbool.h>
            #include "TASK/imu_health_logic.h"

            int main(void) {
                if (Imu_Health_AllowsMotion(false, true, IMU_CAL_DONE)) return 1;
                if (Imu_Health_AllowsMotion(true, false, IMU_CAL_DONE)) return 2;
                if (Imu_Health_AllowsMotion(true, true, IMU_CAL_RUNNING)) return 3;
                if (!Imu_Health_AllowsMotion(true, true, IMU_CAL_DONE)) return 4;
                return 0;
            }
            '''
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
