"""Verify the gated V21 corner and direction-approach point diagnostic."""

from __future__ import annotations

import argparse
import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import check_author_rect_loop_v17 as loop
import check_author_safe_probe_v16 as base


ROOT = Path(__file__).resolve().parents[1]
MOTION_HEADER = ROOT / "APP" / "Inc" / "app_writer_motion.h"
TEST_HEADER = ROOT / "TASK" / "writer_test.h"
TEST_SOURCE = ROOT / "TASK" / "writer_test.c"
DOT_HEADER = ROOT / "TASK" / "workspace_corner_dot_test.h"
DOT_SOURCE = ROOT / "TASK" / "workspace_corner_dot_test.c"
MAIN_SOURCE = ROOT / "main.c"
GCODE_PATH = ROOT / "gcode" / "AUTHOR_SAFE_5POINT_DIR_DOTS_RUN_V21.gcode"
COMMAND_SCRIPT = ROOT / "tools" / "point_dots_v21_control.ps1"
BUILD_LOG = (
    ROOT / "keil" / "AUTHOR_SAFE_5POINT_DIR_DOTS_GATED_V21_build.log"
)
KEIL_HTML_LOG = (
    ROOT
    / "keil"
    / "Objects"
    / "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.build_log.htm"
)
HEX_PATH = ROOT / "keil" / "AUTHOR_SAFE_5POINT_DIR_DOTS_GATED_V21.hex"

BUILD_ID = b"AUTHOR_SAFE_5POINT_DIR_DOTS_GATED_V21"
PLAN_MAX_SEGMENTS = 192
MAX_QUANTIZED_ERROR_MM = 0.09
MAX_LINE_DEVIATION_MM = 0.12


@dataclass(frozen=True)
class PointSpec:
    name: str
    x_mm: float
    y_mm: float
    mark: bool


POINTS = (
    PointSpec("A", 120.0, 5.0, True),
    PointSpec("B", 120.0, 125.0, True),
    PointSpec("C", 290.0, 125.0, True),
    PointSpec("D", 290.0, 5.0, True),
    PointSpec("O_BASE", 205.0, 65.0, True),
    PointSpec("W_APPROACH", 185.0, 65.0, False),
    PointSpec("O_FROM_W", 205.0, 65.0, True),
    PointSpec("E_APPROACH", 225.0, 65.0, False),
    PointSpec("O_FROM_E", 205.0, 65.0, True),
    PointSpec("S_APPROACH", 205.0, 45.0, False),
    PointSpec("O_FROM_S", 205.0, 65.0, True),
    PointSpec("N_APPROACH", 205.0, 85.0, False),
    PointSpec("O_FROM_N", 205.0, 65.0, True),
)

EXPECTED_GCODE = ("G21", "G90", "G94", "M5", "M501")


def quantized_target(
    name: str, x_mm: float, y_mm: float
) -> tuple[int, int, float, float]:
    theta, psi = base.inverse(x_mm, y_mm)
    stage1 = base.lroundf(np.float32(theta * base.STAGE1_STEPS_PER_DEG))
    stage2 = base.lroundf(np.float32(psi * base.STAGE2_STEPS_PER_DEG))
    margin = base.require_hard_safe(stage1, stage2, name)
    actual = loop.user_from_steps(stage1, stage2)
    error = math.hypot(actual[0] - x_mm, actual[1] - y_mm)
    if error > MAX_QUANTIZED_ERROR_MM:
        raise AssertionError(
            f"{name}: quantized endpoint error {error:.6f} mm"
        )
    return stage1, stage2, margin, error


def plan_line(
    start: tuple[float, float], end: tuple[float, float], label: str
) -> list[tuple[int, int]]:
    segments = loop.line_segment_count(start, end)
    if segments > PLAN_MAX_SEGMENTS:
        raise AssertionError(
            f"{label}: {segments} segments exceed {PLAN_MAX_SEGMENTS}"
        )

    start_x = np.float32(start[0])
    start_y = np.float32(start[1])
    end_x = np.float32(end[0])
    end_y = np.float32(end[1])
    planned: list[tuple[int, int]] = []
    for index in range(1, segments + 1):
        ratio = np.float32(index) / np.float32(segments)
        x_mm = np.float32(start_x + np.float32(end_x - start_x) * ratio)
        y_mm = np.float32(start_y + np.float32(end_y - start_y) * ratio)
        stage1, stage2, _, _ = quantized_target(
            f"{label}/IK_{index}", float(x_mm), float(y_mm)
        )
        planned.append((stage1, stage2))
    return planned


def check_segment_dda(
    start_steps: tuple[int, int],
    end_steps: tuple[int, int],
    line_start: tuple[float, float],
    line_end: tuple[float, float],
    label: str,
) -> tuple[int, float, float]:
    delta1 = end_steps[0] - start_steps[0]
    delta2 = end_steps[1] - start_steps[1]
    steps1 = abs(delta1)
    steps2 = abs(delta2)
    master = max(steps1, steps2)
    direction1 = 1 if delta1 > 0 else -1
    direction2 = 1 if delta2 > 0 else -1
    current1, current2 = start_steps
    error1 = master // 2
    error2 = master // 2
    minimum_margin = base.require_hard_safe(
        current1, current2, f"{label}/start"
    )
    maximum_deviation = loop.point_line_distance(
        loop.user_from_steps(current1, current2), line_start, line_end
    )

    for tick in range(master):
        error1 += steps1
        if error1 >= master:
            error1 -= master
            current1 += direction1
        error2 += steps2
        if error2 >= master:
            error2 -= master
            current2 += direction2
        margin = base.require_hard_safe(
            current1, current2, f"{label}/tick_{tick + 1}"
        )
        minimum_margin = min(minimum_margin, margin)
        maximum_deviation = max(
            maximum_deviation,
            loop.point_line_distance(
                loop.user_from_steps(current1, current2),
                line_start,
                line_end,
            ),
        )

    if (current1, current2) != end_steps:
        raise AssertionError(f"{label}: DDA endpoint mismatch")
    return master, minimum_margin, maximum_deviation


def user_from_home_delta(
    stage1_delta: int, stage2_delta: int
) -> tuple[tuple[float, float], tuple[int, int]]:
    theta = np.float32(
        base.THETA_LIMIT_DEG
        + np.float32(stage1_delta) / base.STAGE1_STEPS_PER_DEG
    )
    psi = np.float32(
        base.PSI_LIMIT_DEG
        + np.float32(stage2_delta) / base.STAGE2_STEPS_PER_DEG
    )
    stage1 = base.lroundf(np.float32(theta * base.STAGE1_STEPS_PER_DEG))
    stage2 = base.lroundf(np.float32(psi * base.STAGE2_STEPS_PER_DEG))
    base.require_hard_safe(stage1, stage2, "home")

    to_rad = np.float32(math.pi / 180.0)
    raw_x = np.float32(
        -np.cos(np.float32(theta * to_rad), dtype=np.float32) * base.L1_MM
        - np.cos(np.float32(psi * to_rad), dtype=np.float32) * base.L2_MM
    )
    raw_y = np.float32(
        np.sin(np.float32(theta * to_rad), dtype=np.float32) * base.L1_MM
        + np.sin(np.float32(psi * to_rad), dtype=np.float32) * base.L2_MM
    )
    user = (
        float(np.float32(raw_x - base.OFFSET_X_MM)),
        float(np.float32(raw_y - base.OFFSET_Y_MM)),
    )
    return user, (stage1, stage2)


def check_source_contract() -> None:
    motion = MOTION_HEADER.read_text(encoding="ascii")
    test_h = TEST_HEADER.read_text(encoding="ascii")
    test_c = TEST_SOURCE.read_text(encoding="ascii")
    dot_h = DOT_HEADER.read_text(encoding="ascii")
    dot_c = DOT_SOURCE.read_text(encoding="ascii")
    main_c = MAIN_SOURCE.read_text(encoding="ascii")
    command = COMMAND_SCRIPT.read_text(encoding="ascii")

    for needle in (
        "#define APP_WRITER_MACHINE_OFFSET_X_MM      (-129.0f)",
        "#define APP_WRITER_MACHINE_OFFSET_Y_MM      (128.0f)",
        "#define APP_WRITER_THETA_LIMIT_DEG          (-0.709247f)",
        "#define APP_WRITER_PSI_LIMIT_DEG            (134.323770f)",
        "#define APP_WRITER_STAGE1_STEPS_PER_DEG     (43.708318f)",
        "#define APP_WRITER_STAGE2_STEPS_PER_DEG     (48.8f)",
        "#define APP_WRITER_DIRECTION_COMP_ENABLE     (0u)",
        "#define APP_WRITER_AUTHOR_LINE_EXECUTION_ENABLE (0u)",
        "#define APP_WRITER_A4_ENVELOPE_PROBE_ENABLE  (1u)",
        "#define APP_WRITER_PLAN_SEGMENT_MM          (1.0f)",
        "#define APP_WRITER_PLAN_MAX_SEGMENTS        (192u)",
    ):
        base.require(motion, needle, "motion contract")
    base.require(
        test_h,
        "#define WRITER_TEST_MODE             WRITER_TEST_MODE_WORKSPACE_CORNER_DOTS",
        "selected mode",
    )
    for needle in (
        "(WRITER_TEST_MODE != WRITER_TEST_MODE_WORKSPACE_CORNER_DOTS)",
        "return WorkspaceCornerDotTest_Process_Frame(frame, len);",
        "targets=13 marks=9 isolated_points=5",
    ):
        base.require(test_c, needle, "task integration")
    for needle in (
        BUILD_ID.decode("ascii"),
        "#define WORKSPACE_CORNER_DOT_TARGET_COUNT      (13u)",
        "#define WORKSPACE_CORNER_DOT_MARK_COUNT        (9u)",
        "WORKSPACE_CORNER_DOT_STATE_WAIT_RUN",
        "WORKSPACE_CORNER_DOT_STATE_STOPPED",
        "WorkspaceCornerDotTest_Process_Frame",
    ):
        base.require(dot_h, needle, "dot header")
    for needle in (
        "no_auto_motion=1",
        "gate=M501_or_RUN",
        "WriterMotion_Start_To(target->x_mm, target->y_mm)",
        "App_Servo_Pen_Down();",
        "App_Servo_Pen_Up();",
        "WriterMotion_Emergency_Stop();",
        '(strcmp(command, "M501") == 0)',
        '(strcmp(command, "RUN") == 0)',
        "s_setup_mask != WORKSPACE_CORNER_DOT_SETUP_ALL",
        'WorkspaceCornerDotTest_Fail("unexpected_uart_while_running")',
        "single_pass=1",
        "center_stamps=5",
    ):
        base.require(dot_c, needle, "dot executor")
    base.require(
        main_c,
        "if (WriterHome_InitialHome_Task())",
        "automatic homing",
    )
    for needle in (
        '[ValidateSet("STATUS", "START", "STOP")]',
        "-ConfirmPaperFixed",
        BUILD_ID.decode("ascii"),
        '$preflight -notmatch "state=WAIT_RUN"',
        'foreach ($command in @("G21", "G90", "G94", "M5"))',
        'Send-WriterCommand -Command "M501"',
    ):
        base.require(command, needle, "host control")

    pattern = re.compile(
        r'\{"([A-Z0-9_]+)",\s*(-?\d+(?:\.\d+)?)f,\s*'
        r'(-?\d+(?:\.\d+)?)f,\s*(true|false)\},'
    )
    source_points = tuple(
        PointSpec(
            match.group(1),
            float(match.group(2)),
            float(match.group(3)),
            match.group(4) == "true",
        )
        for match in pattern.finditer(dot_c)
    )
    if source_points != POINTS:
        raise AssertionError(
            f"embedded point list mismatch\nexpected={POINTS}\nactual={source_points}"
        )
    if sum(point.mark for point in POINTS) != 9:
        raise AssertionError("mark count is not nine")
    print(
        "source_contract=PASS mode=V21 gate=G21_G90_G94_M5_M501 "
        "targets=13 marks=9 center_stamps=5 generic_motion=0 single_pass=1"
    )


def check_gcode() -> str:
    lines = tuple(GCODE_PATH.read_text(encoding="ascii").splitlines())
    if lines != EXPECTED_GCODE:
        raise AssertionError(
            f"gate G-code mismatch expected={EXPECTED_GCODE} actual={lines}"
        )
    if any(re.search(r"[XYZFS]|M3|G0|G1", line) for line in lines):
        raise AssertionError("gate file contains a motion or pen-down word")
    digest = hashlib.sha256(GCODE_PATH.read_bytes()).hexdigest().upper()
    print(
        f"gcode_gate=PASS lines=5 motion_words=0 pen_down=0 final=M501 "
        f"sha256={digest}"
    )
    return digest


def check_integer_paths() -> None:
    first = (POINTS[0].x_mm, POINTS[0].y_mm)
    minimum_home_margin = float("inf")
    maximum_approach_deviation = 0.0
    approach_segment_counts: list[int] = []

    # One switch-release pulse plus one degree is the minimum possible home.
    # The upper ends reproduce the last observed 52/57-pulse release homes.
    for delta1 in range(1 + base.lroundf(base.STAGE1_STEPS_PER_DEG), 53):
        for delta2 in range(1 + base.lroundf(base.STAGE2_STEPS_PER_DEG), 58):
            home_user, current_steps = user_from_home_delta(delta1, delta2)
            planned = plan_line(home_user, first, "HOME_TO_A")
            approach_segment_counts.append(len(planned))
            for segment_index, target_steps in enumerate(planned, start=1):
                _, margin, deviation = check_segment_dda(
                    current_steps,
                    target_steps,
                    home_user,
                    first,
                    f"HOME_TO_A/{delta1}_{delta2}/{segment_index}",
                )
                minimum_home_margin = min(minimum_home_margin, margin)
                maximum_approach_deviation = max(
                    maximum_approach_deviation, deviation
                )
                current_steps = target_steps

    observed_home_user, current_steps = user_from_home_delta(52, 57)
    current_user = observed_home_user
    total_segments = 0
    total_master_pulses = 0
    minimum_margin = float("inf")
    maximum_deviation = 0.0
    maximum_endpoint_error = 0.0
    segment_counts: list[int] = []
    target_margins: list[float] = []

    for target_index, point in enumerate(POINTS, start=1):
        target_user = (point.x_mm, point.y_mm)
        planned = plan_line(current_user, target_user, f"TARGET_{target_index}")
        segment_counts.append(len(planned))
        total_segments += len(planned)
        for segment_index, target_steps in enumerate(planned, start=1):
            pulses, margin, deviation = check_segment_dda(
                current_steps,
                target_steps,
                current_user,
                target_user,
                f"TARGET_{target_index}/SEGMENT_{segment_index}",
            )
            total_master_pulses += pulses
            minimum_margin = min(minimum_margin, margin)
            maximum_deviation = max(maximum_deviation, deviation)
            current_steps = target_steps

        expected1, expected2, target_margin, endpoint_error = quantized_target(
            point.name, point.x_mm, point.y_mm
        )
        if current_steps != (expected1, expected2):
            raise AssertionError(f"{point.name}: final integer target mismatch")
        target_margins.append(target_margin)
        maximum_endpoint_error = max(maximum_endpoint_error, endpoint_error)
        current_user = target_user

    if max(segment_counts) > PLAN_MAX_SEGMENTS:
        raise AssertionError("a target-to-target move exceeds the planner")
    if maximum_deviation > MAX_LINE_DEVIATION_MM:
        raise AssertionError(
            f"quantized line deviation {maximum_deviation:.6f} mm"
        )
    if maximum_approach_deviation > MAX_LINE_DEVIATION_MM:
        raise AssertionError(
            f"home approach deviation {maximum_approach_deviation:.6f} mm"
        )

    print(
        "home_envelope=PASS release_delta_s1=45..52 release_delta_s2=50..57 "
        f"approach_segments={min(approach_segment_counts)}.."
        f"{max(approach_segment_counts)} min_margin_deg={minimum_home_margin:.6f} "
        f"max_deviation_mm={maximum_approach_deviation:.6f}"
    )
    print(
        f"integer_paths=PASS move_segments={segment_counts} "
        f"total_segments={total_segments} master_pulses={total_master_pulses} "
        f"target_min_margin_deg={min(target_margins):.6f} "
        f"path_min_margin_deg={minimum_margin:.6f} "
        f"max_endpoint_error_mm={maximum_endpoint_error:.6f} "
        f"max_line_deviation_mm={maximum_deviation:.6f}"
    )


def check_build_log() -> None:
    text = BUILD_LOG.read_text(encoding="utf-8", errors="replace")
    html = KEIL_HTML_LOG.read_text(encoding="utf-8", errors="replace")
    base.require(
        html,
        "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx",
        "correct Keil project",
    )
    base.require(text, "0 Error(s), 0 Warning(s).", "clean build")
    if "Target not created" in text:
        raise AssertionError("build log reports target not created")
    print("keil_build=PASS project=CORRECT errors=0 warnings=0")


def check_hex() -> str:
    image, records, data_bytes = base.parse_ihex(HEX_PATH)
    if BUILD_ID not in image:
        raise AssertionError("V21 build ID missing from firmware")
    for stale_id in (
        b"AUTHOR_SAFE_170X120_CCW_GCODE_V20",
        b"AUTHOR_SAFE_170X120_CW_GCODE_V19",
    ):
        if stale_id in image:
            raise AssertionError(f"stale build ID in firmware: {stale_id!r}")
    digest = hashlib.sha256(HEX_PATH.read_bytes()).hexdigest().upper()
    print(
        f"intel_hex=PASS records={records} data_bytes={data_bytes} "
        f"build_id=PASS sha256={digest}"
    )
    return digest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    check_source_contract()
    check_gcode()
    check_integer_paths()
    if not args.source_only:
        check_build_log()
        check_hex()


if __name__ == "__main__":
    main()
