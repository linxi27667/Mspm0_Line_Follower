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
                if (!Safety_Logic_CanEnterRotation(2u)) return 5;
                if (Safety_Logic_CanEnterRotation(0u) || Safety_Logic_CanEnterRotation(1u) ||
                    Safety_Logic_CanEnterRotation(3u) || Safety_Logic_CanEnterRotation(4u)) return 6;
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

    def test_right_angle_exit_requires_min_angle_before_line_capture(self):
        result = compile_and_run(
            r'''
            #include <stdbool.h>
            #include "TASK/track_logic.h"

            int main(void) {
                if (Track_RightAngle_ShouldExit(40.0f, 40.0f, 2, 2)) return 1;
                if (!Track_RightAngle_ShouldExit(60.0f, 30.0f, 2, 2)) return 2;
                if (!Track_RightAngle_ShouldExit(84.0f, 4.0f, 0, 0)) return 3;
                return 0;
            }
            '''
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_timing_state_and_direction_helpers(self):
        result = compile_and_run(
            r'''
            #include <stdint.h>
            #include "TASK/track_logic.h"

            int main(void) {
                if (Track_State_Allows_Motor(TRACK_STATE_IDLE)) return 1;
                if (!Track_State_Allows_Motor(TRACK_STATE_LINE_FOLLOW)) return 2;
                if (Track_State_Allows_Motor(TRACK_STATE_FINISHED)) return 3;
                if (Track_Timeout_Reached(1049u, 1000u, 50u)) return 4;
                if (!Track_Timeout_Reached(1050u, 1000u, 50u)) return 5;
                if (!Track_Timeout_Reached(3u, UINT32_MAX - 5u, 8u)) return 6;
                if (Track_RightAngle_Direction(-2.0f, 2.0f, 4.0f) > 0.0f) return 7;
                if (Track_RightAngle_Direction(0.0f, 1.0f, -4.0f) < 0.0f) return 8;
                if (Track_RightAngle_Direction(0.0f, 0.0f, -4.0f) > 0.0f) return 9;
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


if __name__ == "__main__":
    unittest.main()
