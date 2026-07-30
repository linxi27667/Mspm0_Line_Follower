"""Generate and verify the restricted 170 x 120 mm CW G-code V19."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np

import check_author_rect_loop_v17 as loop
import check_author_safe_probe_v16 as base


ROOT = Path(__file__).resolve().parents[1]
GCODE_PATH = ROOT / "gcode" / "AUTHOR_SAFE_170X120_CW_SINGLE_V19.gcode"
MOTION_HEADER = ROOT / "APP" / "Inc" / "app_writer_motion.h"
TEST_HEADER = ROOT / "TASK" / "writer_test.h"
TEST_SOURCE = ROOT / "TASK" / "writer_test.c"
SERIAL_HEADER = ROOT / "TASK" / "gcode_serial.h"
SERIAL_SOURCE = ROOT / "TASK" / "gcode_serial.c"
BUILD_LOG = ROOT / "keil" / "AUTHOR_SAFE_170X120_CW_GCODE_V19_build.log"
KEIL_HTML_LOG = (
    ROOT
    / "keil"
    / "Objects"
    / "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.build_log.htm"
)
HEX_PATH = ROOT / "keil" / "AUTHOR_SAFE_170X120_CW_GCODE_V19.hex"

BUILD_ID = b"AUTHOR_SAFE_170X120_CW_GCODE_V19"
FEED_MM_MIN = 200
MAX_LINE_DEVIATION_MM = 0.12

BL = (120.0, 5.0)
TL = (120.0, 125.0)
TR = (290.0, 125.0)
BR = (290.0, 5.0)


def coordinate_line(code: str, x_mm: float, y_mm: float) -> str:
    return f"{code} X{x_mm:.3f} Y{y_mm:.3f}"


def expected_lines() -> list[str]:
    lines = [
        "G21",
        "G90",
        "G94",
        f"F{FEED_MM_MIN}",
        "S1000",
        "G0Z0",
        "M5",
        coordinate_line("G0", *BL),
        "M3",
    ]
    lines.extend(coordinate_line("G1", 120.0, float(y)) for y in range(6, 126))
    lines.extend(coordinate_line("G1", float(x), 125.0) for x in range(121, 291))
    lines.extend(coordinate_line("G1", 290.0, float(y)) for y in range(124, 4, -1))
    lines.extend(coordinate_line("G1", float(x), 5.0) for x in range(289, 119, -1))
    lines.append("M5")
    return lines


def write_gcode() -> None:
    GCODE_PATH.parent.mkdir(parents=True, exist_ok=True)
    GCODE_PATH.write_text("\n".join(expected_lines()) + "\n", encoding="ascii")
    print(f"gcode_written={GCODE_PATH}")


def check_source_contract() -> None:
    motion = MOTION_HEADER.read_text(encoding="ascii")
    test_h = TEST_HEADER.read_text(encoding="ascii")
    test_c = TEST_SOURCE.read_text(encoding="ascii")
    serial_h = SERIAL_HEADER.read_text(encoding="ascii")
    serial_c = SERIAL_SOURCE.read_text(encoding="ascii")

    for needle in (
        "#define APP_WRITER_MACHINE_OFFSET_X_MM      (-129.0f)",
        "#define APP_WRITER_MACHINE_OFFSET_Y_MM      (128.0f)",
        "#define APP_WRITER_THETA_LIMIT_DEG          (-0.709247f)",
        "#define APP_WRITER_PSI_LIMIT_DEG            (134.323770f)",
        "#define APP_WRITER_STAGE1_STEPS_PER_DEG     (43.708318f)",
        "#define APP_WRITER_STAGE2_STEPS_PER_DEG     (48.8f)",
        "#define APP_WRITER_DIRECTION_COMP_ENABLE     (0u)",
        "#define APP_WRITER_AUTHOR_LINE_EXECUTION_ENABLE (1u)",
        "#define APP_WRITER_A4_ENVELOPE_PROBE_ENABLE  (1u)",
    ):
        base.require(motion, needle, "motion contract")
    base.require(
        test_h,
        "#define WRITER_TEST_MODE             WRITER_TEST_MODE_GCODE_SERIAL",
        "selected mode",
    )
    base.require(test_c, "GCODE_SERIAL_RESTRICTED_RECT_ENABLE", "mode guard")
    base.require(serial_h, BUILD_ID.decode("ascii"), "build id")
    for needle in (
        "#define GCODE_SERIAL_USE_FIXED_SOURCE_ORIGIN  (1u)",
        "#define GCODE_SERIAL_SOURCE_ORIGIN_X_MM       (0.0f)",
        "#define GCODE_SERIAL_SOURCE_ORIGIN_Y_MM       (0.0f)",
        "#define GCODE_SERIAL_RESTRICTED_RECT_ENABLE   (1u)",
        "#define GCODE_SERIAL_RECT_X0_MM               (120.0f)",
        "#define GCODE_SERIAL_RECT_Y0_MM               (5.0f)",
        "#define GCODE_SERIAL_RECT_X1_MM               (290.0f)",
        "#define GCODE_SERIAL_RECT_Y1_MM               (125.0f)",
        "#define GCODE_SERIAL_RECT_POINT_STEP_MAX_MM   (1.01f)",
    ):
        base.require(serial_h, needle, "restricted header")
    for needle in (
        "GCODE_SERIAL_RECT_PHASE_WAIT_APPROACH",
        "GCODE_SERIAL_RECT_PHASE_EDGE_LEFT",
        "GCODE_SERIAL_RECT_PHASE_EDGE_TOP",
        "GCODE_SERIAL_RECT_PHASE_EDGE_RIGHT",
        "GCODE_SERIAL_RECT_PHASE_EDGE_BOTTOM",
        "GCODE_SERIAL_RECT_PHASE_WAIT_PEN_UP",
        "GCODE_SERIAL_RECT_PHASE_COMPLETE",
        "GCODE_SERIAL_RECT_PHASE_ABORTED",
        "GCodeSerial_Rect_Validate_Target",
        "restricted_rapid_target",
        "restricted_left_edge",
        "restricted_top_edge",
        "restricted_right_edge",
        "restricted_bottom_edge",
        "restricted_reset_required",
        'strcmp(trimmed, "STOP") == 0',
        'strcmp(trimmed, "STATUS") == 0',
        "WriterMotion_Emergency_Stop();",
        "direction=CW single_pass=1",
    ):
        base.require(serial_c, needle, "restricted executor")
    print(
        "source_contract=PASS mode=RESTRICTED_GCODE_CW_V19 "
        "origin=0,0 single_pass=1 generic_motion=0"
    )


def parse_xy(line: str) -> tuple[float, float]:
    fields = line.split()
    return float(fields[1][1:]), float(fields[2][1:])


def check_gcode_file() -> list[tuple[float, float]]:
    actual = GCODE_PATH.read_text(encoding="ascii").splitlines()
    expected = expected_lines()
    if actual != expected:
        raise AssertionError("G-code differs from deterministic V19 program")
    if any((not line) or (len(line) >= 192) for line in actual):
        raise AssertionError("blank or overlength G-code line")

    draw_points = [parse_xy(line) for line in actual if line.startswith("G1 ")]
    if len(draw_points) != 580:
        raise AssertionError(f"expected 580 G1 targets, got {len(draw_points)}")
    if draw_points[-1] != BL:
        raise AssertionError("program does not close at BL")

    digest = hashlib.sha256(GCODE_PATH.read_bytes()).hexdigest().upper()
    print(
        f"gcode_protocol=PASS lines={len(actual)} g0=1 g1={len(draw_points)} "
        f"m3=1 m5=2 feed={FEED_MM_MIN} final_pen=UP sha256={digest}"
    )
    return draw_points


def check_approach(bl_steps: tuple[int, int]) -> None:
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
        f"approach=PASS minimum_release_pulses={minimum_pulses} "
        f"minimum_margin_deg={minimum_margin:.6f} "
        f"observed_release_pulses={observed_pulses} "
        f"observed_margin_deg={observed_margin:.6f}"
    )


def edge_for_index(index: int) -> tuple[tuple[float, float], tuple[float, float]]:
    if index < 120:
        return BL, TL
    if index < 290:
        return TL, TR
    if index < 410:
        return TR, BR
    return BR, BL


def check_integer_path(draw_points: list[tuple[float, float]]) -> None:
    bl_target = base.target_for("RECT_BL", *BL)
    start_steps = (bl_target.stage1_steps, bl_target.stage2_steps)
    current_steps = start_steps
    total_pulses = 0
    minimum_margin = float("inf")
    maximum_deviation = 0.0

    check_approach(start_steps)
    for index, point in enumerate(draw_points):
        target = base.target_for(f"CW_G1_{index + 1}", *point)
        target_steps = (target.stage1_steps, target.stage2_steps)
        line_start, line_end = edge_for_index(index)
        pulses, margin, deviation = loop.check_boundary_dda(
            current_steps,
            target_steps,
            line_start,
            line_end,
            f"CW/G1_{index + 1}",
        )
        total_pulses += pulses
        minimum_margin = min(minimum_margin, margin)
        maximum_deviation = max(maximum_deviation, deviation)
        current_steps = target_steps

    if current_steps != start_steps:
        raise AssertionError(
            f"integer closure {current_steps}, expected {start_steps}"
        )
    if maximum_deviation > MAX_LINE_DEVIATION_MM:
        raise AssertionError(
            f"line deviation {maximum_deviation:.6f} mm exceeds guard"
        )
    print(
        f"integer_path=PASS ik_targets={len(draw_points)} "
        f"master_pulses={total_pulses} min_margin_deg={minimum_margin:.6f} "
        f"max_line_deviation_mm={maximum_deviation:.6f} closure_steps=0,0"
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
        raise AssertionError("V19 build ID missing from firmware")
    if b"AUTHOR_SAFE_170X120_DRAW_GATED_V18" in image:
        raise AssertionError("stale V18 build ID present in V19 firmware")
    digest = hashlib.sha256(HEX_PATH.read_bytes()).hexdigest().upper()
    print(
        f"intel_hex=PASS records={records} data_bytes={data_bytes} "
        f"build_id=PASS sha256={digest}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()

    if args.write:
        write_gcode()
    check_source_contract()
    draw_points = check_gcode_file()
    check_integer_path(draw_points)
    if not args.source_only:
        check_build_log()
        check_hex()


if __name__ == "__main__":
    main()
