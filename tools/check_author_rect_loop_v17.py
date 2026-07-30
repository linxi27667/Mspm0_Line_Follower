"""Verify the infinite, pen-up author-frame rectangle loop V17."""

from __future__ import annotations

import argparse
import hashlib
import math
from pathlib import Path

import numpy as np

import check_author_safe_probe_v16 as base


ROOT = Path(__file__).resolve().parents[1]
MOTION_HEADER = ROOT / "APP" / "Inc" / "app_writer_motion.h"
TEST_HEADER = ROOT / "TASK" / "writer_test.h"
PROBE_HEADER = ROOT / "TASK" / "a4_joint_probe.h"
PROBE_SOURCE = ROOT / "TASK" / "a4_joint_probe.c"
PATH_HEADER = ROOT / "TASK" / "author_coordinate_probe_path.h"
MAIN_SOURCE = ROOT / "main.c"
COMMAND_SCRIPT = ROOT / "tools" / "author_rect_loop_command.ps1"
BUILD_LOG = ROOT / "keil" / "AUTHOR_SAFE_170X120_PENUP_LOOP_V17_build.log"
KEIL_HTML_LOG = (
    ROOT
    / "keil"
    / "Objects"
    / "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.build_log.htm"
)
HEX_PATH = ROOT / "keil" / "AUTHOR_SAFE_170X120_PENUP_LOOP_V17.hex"

BUILD_ID = b"AUTHOR_SAFE_170X120_PENUP_LOOP_V17"
PLAN_SEGMENT_MM = np.float32(1.0)
PLAN_MAX_SEGMENTS = 192
RECT_VERTICES = (
    ("RECT_BL", 120.0, 5.0),
    ("RECT_BR", 290.0, 5.0),
    ("RECT_TR", 290.0, 125.0),
    ("RECT_TL", 120.0, 125.0),
    ("RECT_CLOSE", 120.0, 5.0),
)


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"{label}: missing {needle!r}")


def user_from_steps(stage1_steps: int, stage2_steps: int) -> tuple[float, float]:
    theta = np.float32(stage1_steps) / base.STAGE1_STEPS_PER_DEG
    psi = np.float32(stage2_steps) / base.STAGE2_STEPS_PER_DEG
    to_rad = np.float32(math.pi / 180.0)
    raw_x = np.float32(
        -np.cos(np.float32(theta * to_rad), dtype=np.float32) * base.L1_MM
        - np.cos(np.float32(psi * to_rad), dtype=np.float32) * base.L2_MM
    )
    raw_y = np.float32(
        np.sin(np.float32(theta * to_rad), dtype=np.float32) * base.L1_MM
        + np.sin(np.float32(psi * to_rad), dtype=np.float32) * base.L2_MM
    )
    return (
        float(np.float32(raw_x - base.OFFSET_X_MM)),
        float(np.float32(raw_y - base.OFFSET_Y_MM)),
    )


def line_segment_count(
    start: tuple[float, float], target: tuple[float, float]
) -> int:
    dx = np.float32(np.float32(target[0]) - np.float32(start[0]))
    dy = np.float32(np.float32(target[1]) - np.float32(start[1]))
    span = np.float32(max(abs(float(dx)), abs(float(dy))))
    segments = int(np.float32(span / PLAN_SEGMENT_MM))
    if segments == 0 or np.float32(segments) * PLAN_SEGMENT_MM < span:
        segments += 1
    return segments


def plan_edge(
    start: tuple[float, float], target: tuple[float, float], label: str
) -> list[base.Target]:
    start_x = np.float32(start[0])
    start_y = np.float32(start[1])
    target_x = np.float32(target[0])
    target_y = np.float32(target[1])
    segments = line_segment_count(start, target)
    if segments > PLAN_MAX_SEGMENTS:
        raise AssertionError(
            f"{label}: segments {segments} exceed {PLAN_MAX_SEGMENTS}"
        )

    result: list[base.Target] = []
    for index in range(1, segments + 1):
        ratio = np.float32(index) / np.float32(segments)
        work_x = np.float32(start_x + np.float32(target_x - start_x) * ratio)
        work_y = np.float32(start_y + np.float32(target_y - start_y) * ratio)
        result.append(
            base.target_for(f"{label}_{index}", float(work_x), float(work_y))
        )
    return result


def point_line_distance(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)
    if length <= 0.0:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    return abs(
        dy * point[0] - dx * point[1] + end[0] * start[1]
        - end[1] * start[0]
    ) / length


def check_boundary_dda(
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
    maximum_deviation = point_line_distance(
        user_from_steps(current1, current2), line_start, line_end
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
            current1, current2, f"{label}/tick{tick + 1}"
        )
        minimum_margin = min(minimum_margin, margin)
        maximum_deviation = max(
            maximum_deviation,
            point_line_distance(
                user_from_steps(current1, current2), line_start, line_end
            ),
        )

    if (current1, current2) != end_steps:
        raise AssertionError(f"{label}: DDA endpoint mismatch")
    if minimum_margin < base.OPERATING_MARGIN_DEG - 1.0e-6:
        raise AssertionError(
            f"{label}: margin {minimum_margin:.6f} below operating guard"
        )
    return master, minimum_margin, maximum_deviation


def check_source_contract() -> None:
    motion = MOTION_HEADER.read_text(encoding="ascii")
    test_h = TEST_HEADER.read_text(encoding="ascii")
    probe_h = PROBE_HEADER.read_text(encoding="ascii")
    probe_c = PROBE_SOURCE.read_text(encoding="ascii")
    path_h = PATH_HEADER.read_text(encoding="ascii")
    main_c = MAIN_SOURCE.read_text(encoding="ascii")
    command = COMMAND_SCRIPT.read_text(encoding="ascii")

    require(
        test_h,
        "#define WRITER_TEST_MODE             WRITER_TEST_MODE_A4_JOINT_PROBE",
        "selected mode",
    )
    for needle in (
        "#define APP_WRITER_MACHINE_OFFSET_X_MM      (-129.0f)",
        "#define APP_WRITER_MACHINE_OFFSET_Y_MM      (128.0f)",
        "#define APP_WRITER_THETA_LIMIT_DEG          (-0.709247f)",
        "#define APP_WRITER_PSI_LIMIT_DEG            (134.323770f)",
        "#define APP_WRITER_STAGE1_STEPS_PER_DEG     (43.708318f)",
        "#define APP_WRITER_STAGE2_STEPS_PER_DEG     (48.8f)",
        "#define APP_WRITER_AUTHOR_LINE_EXECUTION_ENABLE (0u)",
        "#define APP_WRITER_A4_ENVELOPE_PROBE_ENABLE  (1u)",
        "#define APP_WRITER_PLAN_SEGMENT_MM          (1.0f)",
        "#define APP_WRITER_PLAN_MAX_SEGMENTS        (192u)",
    ):
        require(motion, needle, "motion contract")
    require(probe_h, BUILD_ID.decode("ascii"), "build id")
    require(probe_h, "A4_JOINT_PROBE_STATE_WAIT_LOOP", "wait state")
    require(probe_h, "A4_JOINT_PROBE_STATE_LOOPING", "loop state")
    require(probe_c, "no_auto_loop_motion=1", "UART start gate")
    require(probe_c, "full_A4=DISABLED", "full A4 lockout")
    require(probe_c, "WriterMotion_Start_To", "Cartesian edge planner")
    require(probe_c, "s_loop_count++", "unbounded loop counter")
    require(probe_c, 'strcmp(command, "LOOP") != 0', "LOOP command")
    require(probe_c, 'strcmp(command, "STOP") == 0', "STOP command")
    require(probe_c, 'strcmp(command, "DRAW") == 0', "DRAW rejection")
    require(probe_c, "(command[0] == 'G')", "G-code rejection")
    require(
        main_c,
        "(WRITER_TEST_MODE == WRITER_TEST_MODE_AUTHOR_M700_CALIB)",
        "automatic home retained",
    )
    require(
        command,
        '[ValidateSet("STATUS", "LOOP", "STOP")]',
        "host command whitelist",
    )
    require(
        command,
        "$LoopCommand -eq \"LOOP\") -and -not $ConfirmContinuousPenUpLoop",
        "host confirmation gate",
    )
    require(command, BUILD_ID.decode("ascii"), "host firmware preflight")
    require(command, '$preflight -notmatch "state=WAIT_LOOP"', "host state gate")

    expected_header = [base.target_for(*point) for point in base.POINTS]
    actual_header = base.parse_header_targets(path_h)
    if actual_header != expected_header:
        raise AssertionError("endpoint header no longer matches offline IK")
    print(
        "source_contract=PASS mode=AUTHOR_SAFE_170X120_PENUP_LOOP_V17 "
        "command=LOOP continuous=1 stop=STOP gcode=0 draw=0 pen=UP"
    )


def check_loop_path() -> None:
    bl = base.target_for(*RECT_VERTICES[0])
    bl_steps = (bl.stage1_steps, bl.stage2_steps)
    minimum_home = (
        base.lroundf(np.float32(base.THETA_LIMIT_DEG * base.STAGE1_STEPS_PER_DEG))
        + 1
        + base.lroundf(base.STAGE1_STEPS_PER_DEG),
        base.lroundf(np.float32(base.PSI_LIMIT_DEG * base.STAGE2_STEPS_PER_DEG))
        + 1
        + base.lroundf(base.STAGE2_STEPS_PER_DEG),
    )
    observed_home = (
        base.lroundf(np.float32(base.THETA_LIMIT_DEG * base.STAGE1_STEPS_PER_DEG))
        + 52,
        base.lroundf(np.float32(base.PSI_LIMIT_DEG * base.STAGE2_STEPS_PER_DEG))
        + 57,
    )
    minimum_approach_pulses, minimum_approach_margin = base.check_dda(
        minimum_home, bl_steps, "minimum_home_to_bl", 0.0
    )
    observed_approach_pulses, observed_approach_margin = base.check_dda(
        observed_home, bl_steps, "observed_home_to_bl", 0.0
    )

    current_steps = bl_steps
    current_user = user_from_steps(*bl_steps)
    total_segments = 0
    total_pulses = 0
    minimum_margin = float("inf")
    maximum_deviation = 0.0
    edge_segment_counts: list[int] = []

    for edge_index, (_, target_x, target_y) in enumerate(
        RECT_VERTICES[1:], start=1
    ):
        edge_target = (target_x, target_y)
        planned_targets = plan_edge(
            current_user, edge_target, f"edge_{edge_index}"
        )
        edge_segment_counts.append(len(planned_targets))
        total_segments += len(planned_targets)
        line_start = current_user
        for segment_index, target in enumerate(planned_targets, start=1):
            target_steps = (target.stage1_steps, target.stage2_steps)
            pulses, margin, deviation = check_boundary_dda(
                current_steps,
                target_steps,
                line_start,
                edge_target,
                f"edge_{edge_index}/segment_{segment_index}",
            )
            total_pulses += pulses
            minimum_margin = min(minimum_margin, margin)
            maximum_deviation = max(maximum_deviation, deviation)
            current_steps = target_steps
        current_user = edge_target

    if current_steps != bl_steps:
        raise AssertionError(
            f"closed loop ended at {current_steps}, expected {bl_steps}"
        )
    if maximum_deviation > 0.12:
        raise AssertionError(
            f"integer-pulse line deviation {maximum_deviation:.6f} mm"
        )
    if max(edge_segment_counts) > PLAN_MAX_SEGMENTS:
        raise AssertionError("edge plan exceeds firmware buffer")

    print(
        f"approach_paths=PASS minimum_release_pulses={minimum_approach_pulses} "
        f"minimum_margin_deg={minimum_approach_margin:.6f} "
        f"observed_release_pulses={observed_approach_pulses} "
        f"observed_margin_deg={observed_approach_margin:.6f}"
    )
    print(
        f"loop_path=PASS edge_segments={edge_segment_counts} "
        f"total_segments={total_segments} total_master_pulses={total_pulses} "
        f"min_margin_deg={minimum_margin:.6f} "
        f"max_line_deviation_mm={maximum_deviation:.6f}"
    )
    print("repeat_seam=PASS end=RECT_BL next=RECT_BR loops=UNBOUNDED")


def check_build_log() -> None:
    text = BUILD_LOG.read_text(encoding="utf-8", errors="replace")
    html = KEIL_HTML_LOG.read_text(encoding="utf-8", errors="replace")
    require(
        html,
        "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx",
        "correct Keil project",
    )
    require(text, "0 Error(s), 0 Warning(s).", "clean build")
    if "Target not created" in text:
        raise AssertionError("build log reports target not created")
    print("keil_build=PASS errors=0 warnings=0")


def check_hex() -> None:
    image, records, data_bytes = base.parse_ihex(HEX_PATH)
    if BUILD_ID not in image:
        raise AssertionError("V17 build id missing from firmware")
    digest = hashlib.sha256(HEX_PATH.read_bytes()).hexdigest().upper()
    print(
        f"intel_hex=PASS records={records} data_bytes={data_bytes} "
        f"build_id=PASS sha256={digest}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    check_source_contract()
    check_loop_path()
    if not args.source_only:
        check_build_log()
        check_hex()


if __name__ == "__main__":
    main()
