import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def compile_and_run(source: str) -> subprocess.CompletedProcess:
    tmp = ROOT / "tests" / "_track_logic_test.c"
    exe = ROOT / "tests" / "_track_logic_test.exe"
    tmp.write_text(source, encoding="utf-8")
    try:
        compile_result = subprocess.run(
            ["gcc", "-std=c99", "-Wall", "-Wextra", "-I", ".", "tests/_track_logic_test.c", "-o", "tests/_track_logic_test.exe"],
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
    finally:
        tmp.unlink(missing_ok=True)
        exe.unlink(missing_ok=True)


class TrackLogicTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
