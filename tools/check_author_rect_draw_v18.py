"""Verify the UART-gated, single-pass 170 x 120 mm draw V18."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np

import check_author_rect_loop_v17 as loop
import check_author_safe_probe_v16 as base


ROOT = Path(__file__).resolve().parents[1]
MOTION_HEADER = ROOT / "APP" / "Inc" / "app_writer_motion.h"
TEST_HEADER = ROOT / "TASK" / "writer_test.h"
TEST_SOURCE = ROOT / "TASK" / "writer_test.c"
PROBE_HEADER = ROOT / "TASK" / "a4_joint_probe.h"
PROBE_SOURCE = ROOT / "TASK" / "a4_joint_probe.c"
PATH_HEADER = ROOT / "TASK" / "author_coordinate_probe_path.h"
MAIN_SOURCE = ROOT / "main.c"
COMMAND_SCRIPT = ROOT / "tools" / "author_rect_draw_command.ps1"
BUILD_LOG = ROOT / "keil" / "AUTHOR_SAFE_170X120_DRAW_GATED_V18_build.log"
KEIL_HTML_LOG = (
    ROOT
    / "keil"
    / "Objects"
    / "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.build_log.htm"
)
HEX_PATH = ROOT / "keil" / "AUTHOR_SAFE_170X120_DRAW_GATED_V18.hex"

BUILD_ID = b"AUTHOR_SAFE_170X120_DRAW_GATED_V18"
PLAN_MAX_SEGMENTS = 192
MAX_LINE_DEVIATION_MM = 0.12

DIRECTION_VERTICES = {
    "CW": (
        ("RECT_BL", 120.0, 5.0),
        ("RECT_TL", 120.0, 125.0),
        ("RECT_TR", 290.0, 125.0),
        ("RECT_BR", 290.0, 5.0),
        ("RECT_BL_CLOSE", 120.0, 5.0),
    ),
    "CCW": (
        ("RECT_BL", 120.0, 5.0),
        ("RECT_BR", 290.0, 5.0),
        ("RECT_TR", 290.0, 125.0),
        ("RECT_TL", 120.0, 125.0),
        ("RECT_BL_CLOSE", 120.0, 5.0),
    ),
}


def check_source_contract() -> None:
    motion = MOTION_HEADER.read_text(encoding="ascii")
    test_h = TEST_HEADER.read_text(encoding="ascii")
    test_c = TEST_SOURCE.read_text(encoding="ascii")
    probe_h = PROBE_HEADER.read_text(encoding="ascii")
    probe_c = PROBE_SOURCE.read_text(encoding="ascii")
    path_h = PATH_HEADER.read_text(encoding="ascii")
    main_c = MAIN_SOURCE.read_text(encoding="ascii")
    command = COMMAND_SCRIPT.read_text(encoding="ascii")

    base.require(
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
        base.require(motion, needle, "motion contract")

    base.require(probe_h, BUILD_ID.decode("ascii"), "build id")
    for needle in (
        "A4_JOINT_PROBE_STATE_WAIT_NEXT",
        "A4_JOINT_PROBE_STATE_WAIT_DRAW",
        "A4_JOINT_PROBE_STATE_DRAWING",
        "A4_JOINT_PROBE_STATE_DONE",
        "A4_JOINT_PROBE_DRAW_FEED_MM_MIN (200.0f)",
        "A4_JOINT_PROBE_PEN_SETTLE_MS (700u)",
    ):
        base.require(probe_h, needle, "state contract")

    for needle in (
        "no_auto_motion=1",
        "no_loop=1",
        "full_A4=DISABLED",
        "single_pass=1",
        "WriterMotion_Start_To_At_Feed",
        "App_Servo_Pen_Down();",
        "App_Servo_Pen_Up();",
        'strcmp(command, "DRAW_CW") == 0',
        'strcmp(command, "DRAW_CCW") == 0',
        'strcmp(command, "STOP") == 0',
        'strcmp(command, "LOOP") == 0',
        "(command[0] == 'G')",
        "s_completed_edges >= A4_JOINT_PROBE_RECT_EDGE_COUNT",
        "A4_JOINT_PROBE_STATE_DONE",
    ):
        base.require(probe_c, needle, "draw state machine")
    for needle in (
        "A4_JOINT_PROBE_RECT_TL_INDEX,\n"
        "    A4_JOINT_PROBE_RECT_TR_INDEX,\n"
        "    A4_JOINT_PROBE_RECT_BR_INDEX,\n"
        "    A4_JOINT_PROBE_RECT_BL_INDEX",
        "A4_JOINT_PROBE_RECT_BR_INDEX,\n"
        "    A4_JOINT_PROBE_RECT_TR_INDEX,\n"
        "    A4_JOINT_PROBE_RECT_TL_INDEX,\n"
        "    A4_JOINT_PROBE_RECT_CLOSE_INDEX",
    ):
        base.require(probe_c, needle, "direction order")

    base.require(test_c, "gate2=DRAW_CW_or_DRAW_CCW", "test selector")
    base.require(
        main_c,
        "(WRITER_TEST_MODE == WRITER_TEST_MODE_AUTHOR_M700_CALIB)",
        "automatic home retained",
    )
    base.require(
        command,
        '[ValidateSet("STATUS", "NEXT", "DRAW_CW", "DRAW_CCW", "STOP")]',
        "host command whitelist",
    )
    base.require(command, "ConfirmPenUpClearance", "NEXT host gate")
    base.require(command, "ConfirmSinglePassPenDown", "draw host gate")
    base.require(command, BUILD_ID.decode("ascii"), "host firmware gate")
    base.require(command, '"state=WAIT_NEXT"', "host NEXT state gate")
    base.require(command, '"state=WAIT_DRAW"', "host draw state gate")
    base.require(command, '"target=RECT_BL"', "host start-point gate")

    expected_header = [base.target_for(*point) for point in base.POINTS]
    actual_header = base.parse_header_targets(path_h)
    if actual_header != expected_header:
        raise AssertionError("endpoint header no longer matches offline IK")

    print(
        "source_contract=PASS mode=AUTHOR_SAFE_170X120_DRAW_GATED_V18 "
        "gates=NEXT,DRAW_CW_OR_CCW single_pass=1 loop=0 gcode=0"
    )


def check_approach() -> None:
    bl = base.target_for(*DIRECTION_VERTICES["CCW"][0])
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
    minimum_pulses, minimum_margin = base.check_dda(
        minimum_home, bl_steps, "minimum_home_to_bl", 0.0
    )
    observed_pulses, observed_margin = base.check_dda(
        observed_home, bl_steps, "observed_home_to_bl", 0.0
    )
    print(
        f"approach_paths=PASS minimum_release_pulses={minimum_pulses} "
        f"minimum_margin_deg={minimum_margin:.6f} "
        f"observed_release_pulses={observed_pulses} "
        f"observed_margin_deg={observed_margin:.6f}"
    )


def check_direction(direction: str) -> None:
    vertices = DIRECTION_VERTICES[direction]
    bl = base.target_for(*vertices[0])
    start_steps = (bl.stage1_steps, bl.stage2_steps)
    current_steps = start_steps
    current_user = loop.user_from_steps(*start_steps)
    edge_segments: list[int] = []
    total_pulses = 0
    minimum_margin = float("inf")
    maximum_deviation = 0.0

    for edge_index, (_, target_x, target_y) in enumerate(
        vertices[1:], start=1
    ):
        edge_target = (target_x, target_y)
        planned_targets = loop.plan_edge(
            current_user, edge_target, f"{direction}_edge_{edge_index}"
        )
        edge_segments.append(len(planned_targets))
        if len(planned_targets) > PLAN_MAX_SEGMENTS:
            raise AssertionError(
                f"{direction} edge {edge_index}: plan buffer exceeded"
            )

        line_start = current_user
        for segment_index, target in enumerate(planned_targets, start=1):
            target_steps = (target.stage1_steps, target.stage2_steps)
            pulses, margin, deviation = loop.check_boundary_dda(
                current_steps,
                target_steps,
                line_start,
                edge_target,
                f"{direction}/edge_{edge_index}/segment_{segment_index}",
            )
            total_pulses += pulses
            minimum_margin = min(minimum_margin, margin)
            maximum_deviation = max(maximum_deviation, deviation)
            current_steps = target_steps
        current_user = edge_target

    if current_steps != start_steps:
        raise AssertionError(
            f"{direction}: closure steps {current_steps}, expected {start_steps}"
        )
    if maximum_deviation > MAX_LINE_DEVIATION_MM:
        raise AssertionError(
            f"{direction}: line deviation {maximum_deviation:.6f} mm"
        )

    print(
        f"direction_{direction}=PASS edge_segments={edge_segments} "
        f"targets={sum(edge_segments)} master_pulses={total_pulses} "
        f"min_margin_deg={minimum_margin:.6f} "
        f"max_line_deviation_mm={maximum_deviation:.6f} "
        "closure_steps=0,0"
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


def check_hex() -> None:
    image, records, data_bytes = base.parse_ihex(HEX_PATH)
    if BUILD_ID not in image:
        raise AssertionError("V18 build id missing from firmware")
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
    check_approach()
    check_direction("CW")
    check_direction("CCW")
    if not args.source_only:
        check_build_log()
        check_hex()


if __name__ == "__main__":
    main()
