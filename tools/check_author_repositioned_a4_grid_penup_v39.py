#!/usr/bin/env python3
"""Verify the staged, all-pen-up V39 repositioned-A4 grid probe."""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import struct
import zlib
from pathlib import Path

import analyze_diary_repositioned_a4_singularity as singularity
import check_author_text_demo_v30 as v30
import check_stage2_long_chord_cal_v25 as common


ROOT = Path(__file__).resolve().parents[1]
MOTION_HEADER = ROOT / "APP" / "Inc" / "app_writer_motion.h"
TEST_HEADER = ROOT / "TASK" / "writer_test.h"
TEST_SOURCE = ROOT / "TASK" / "writer_test.c"
DEMO_HEADER = ROOT / "TASK" / "author_text_demo.h"
DEMO_SOURCE = ROOT / "TASK" / "author_text_demo.c"
PATH_HEADER = ROOT / "TASK" / "author_text_demo_path.h"
BUILD_LOG = ROOT / "keil" / "AUTHOR_REPOSITIONED_A4_GRID_PENUP_L205_L203_GATED_V39_build.log"
KEIL_HTML_LOG = ROOT / "keil" / "Objects" / "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.build_log.htm"
HEX_PATH = ROOT / "keil" / "AUTHOR_REPOSITIONED_A4_GRID_PENUP_L205_L203_GATED_V39.hex"

BUILD_ID = b"AUTHOR_REPOSITIONED_A4_GRID_PENUP_L205_L203_GATED_V39"
SHIFT = (121.0, -91.0)
ALIGN_PAPER = (29.0, 111.0)
PAPER_INSET = (15.0, 15.0, 282.0, 195.0)
EXPECTED_CRC32 = 0xF5B0377A
EXPECTED_HEX_SHA256 = "08EF93F610B68EF9780EC37FEE3D202020D87717FCF250575203EFC09BB5710A"
EXPECTED_POINTS = (
    v30.DemoPoint(1360, 200, False),
    v30.DemoPoint(1360, -760, False),
    v30.DemoPoint(1360, 140, False),
    v30.DemoPoint(1360, 1040, False),
    v30.DemoPoint(1360, 140, False),
    v30.DemoPoint(2695, 140, False),
    v30.DemoPoint(2695, -760, False),
    v30.DemoPoint(2695, 140, False),
    v30.DemoPoint(2695, 1040, False),
    v30.DemoPoint(2695, 140, False),
    v30.DemoPoint(4030, 140, False),
    v30.DemoPoint(4030, -760, False),
    v30.DemoPoint(4030, 140, False),
    v30.DemoPoint(4030, 1040, False),
    v30.DemoPoint(4030, 140, False),
    v30.DemoPoint(2695, 140, False),
    v30.DemoPoint(1500, 200, False),
)
EXPECTED_STAGE_OFFSETS = (0, 1, 5, 6, 10, 11, 15, 16)
EXPECTED_STAGE_COUNTS = (1, 4, 1, 4, 1, 4, 1, 1)

GATES = (
    ("AUTHOR_REPOSITIONED_A4_GRID_ALIGN_RUN_V39.gcode", "M801"),
    ("AUTHOR_REPOSITIONED_A4_GRID_BOTTOM_CENTER_RUN_V39.gcode", "M817"),
    ("AUTHOR_REPOSITIONED_A4_GRID_BOTTOM_ROW_RUN_V39.gcode", "M818"),
    ("AUTHOR_REPOSITIONED_A4_GRID_MIDDLE_CENTER_RUN_V39.gcode", "M819"),
    ("AUTHOR_REPOSITIONED_A4_GRID_MIDDLE_ROW_RUN_V39.gcode", "M820"),
    ("AUTHOR_REPOSITIONED_A4_GRID_TOP_CENTER_RUN_V39.gcode", "M821"),
    ("AUTHOR_REPOSITIONED_A4_GRID_TOP_ROW_RUN_V39.gcode", "M822"),
    ("AUTHOR_REPOSITIONED_A4_GRID_RETURN_MIDDLE_RUN_V39.gcode", "M823"),
    ("AUTHOR_REPOSITIONED_A4_GRID_RETURN_ALIGN_RUN_V39.gcode", "M824"),
)
PROTECTED_HEX = {
    "AUTHOR_KAISHU_MEDIAN_16MM_L205_L203_GATED_V36.hex": "37506BE659CE6652D8016F8894EBDFA5EFA310FE544D5D3D655B5AAE32BC3054",
    "AUTHOR_REPOSITIONED_A4_PENUP_SWEEP_L205_L203_GATED_V37.hex": "499E33BC5D0705BDC36199776040A0336914156A69CCD2C087BF7F27410F3B38",
    "AUTHOR_PENUP_AXIS_XY10_L205_L203_GATED_V38.hex": "9777B6F4DE143A7426F28F6126C990B392F4BE2EA3822E9DF2FE3408670B4A6A",
}


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"{label}: missing {needle!r}")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def parse_path(text: str) -> tuple[v30.DemoPoint, ...]:
    return tuple(
        v30.DemoPoint(int(x), int(y), draw == "1")
        for x, y, draw in re.findall(r"\{(-?\d+), (-?\d+), ([01])u\},", text)
    )


def parse_u8_array(text: str, name: str) -> tuple[int, ...]:
    match = re.search(rf"{name}\[.*?\]\s*=\s*\{{(.*?)\}};", text, re.DOTALL)
    if not match:
        raise AssertionError(f"missing array {name}")
    return tuple(int(value) for value in re.findall(r"(\d+)u", match.group(1)))


def path_crc32(points: tuple[v30.DemoPoint, ...]) -> int:
    data = b"".join(
        struct.pack("<hhB", p.x_x10, p.y_x10, int(p.draw)) for p in points
    )
    return zlib.crc32(data) & 0xFFFFFFFF


def check_source() -> tuple[v30.DemoPoint, ...]:
    motion = MOTION_HEADER.read_text(encoding="ascii")
    test_h = TEST_HEADER.read_text(encoding="ascii")
    test_c = TEST_SOURCE.read_text(encoding="ascii")
    demo_h = DEMO_HEADER.read_text(encoding="ascii")
    demo_c = DEMO_SOURCE.read_text(encoding="ascii")
    path_h = PATH_HEADER.read_text(encoding="ascii")

    for needle in (
        "#define APP_WRITER_L1_MM                    (205.0f)",
        "#define APP_WRITER_L2_MM                    (203.0f)",
        "#define APP_WRITER_DIRECTION_COMP_ENABLE     (0u)",
        "#define APP_WRITER_DIRECTION_COMP_PRELOAD_ENABLE      (0u)",
        "#define APP_WRITER_AUTHOR_LINE_EXECUTION_ENABLE (0u)",
        "#define APP_WRITER_PLAN_SEGMENT_MM          (1.0f)",
    ):
        require(motion, needle, "motion contract")
    require(test_h, "#define WRITER_TEST_MODE             WRITER_TEST_MODE_AUTHOR_TEXT_DEMO", "selected mode")
    require(test_h, "V39 staged repositioned-A4 all-pen-up grid probe", "task comment")
    require(test_c, "stages=ALIGN_BOTTOM_MIDDLE_TOP_RETURN", "task integration")
    require(test_c, "path=REPOSITIONED_A4_GRID_PENUP gcode=DISABLED dircomp=0 preload=0", "task safety")
    require(demo_h, BUILD_ID.decode("ascii"), "build ID")
    for needle in (
        "AUTHOR_TEXT_DEMO_PATH_CRC32 == 0xF5B0377Au",
        "AUTHOR_TEXT_DEMO_PATH_POINT_COUNT == 17u",
        "AUTHOR_TEXT_DEMO_PATH_DRAW_COUNT == 0u",
        "AUTHOR_TEXT_DEMO_STAGE_COUNT == 8u",
        "AUTHOR_TEXT_DEMO_PAPER_SHIFT_X_X10 == 1210",
        "AUTHOR_TEXT_DEMO_PAPER_SHIFT_Y_X10 == -910",
        "AUTHOR_TEXT_DEMO_ALIGN_PAPER_X_X10 == 290",
        "AUTHOR_TEXT_DEMO_ALIGN_PAPER_Y_X10 == 1110",
        "gates=M801_ALIGN,M817..M824_REPOSITIONED_A4_GRID",
        "&s_author_text_demo_path[",
        "s_author_text_demo_stage_offset[s_next_probe_index]",
        "s_author_text_demo_stage_count[s_next_probe_index]",
        "AuthorTextDemo_Fail(\"pen_down_target_forbidden\")",
    ):
        require(demo_c, needle, "V39 executor")
    for gate in range(817, 825):
        require(demo_c, f'"M{gate}"', "V39 gate table")
    for forbidden in ("App_Servo_Pen_Down", "GCodeSerial_Start", "2.0.gcode", '"M808"'):
        if forbidden in demo_c:
            raise AssertionError(f"V39 executor contains forbidden {forbidden!r}")

    points = parse_path(path_h)
    if points != EXPECTED_POINTS:
        raise AssertionError(f"path mismatch: {points!r}")
    if path_crc32(points) != EXPECTED_CRC32 or any(p.draw for p in points):
        raise AssertionError("path CRC or pen state mismatch")
    offsets = parse_u8_array(path_h, "s_author_text_demo_stage_offset")
    counts = parse_u8_array(path_h, "s_author_text_demo_stage_count")
    if offsets != EXPECTED_STAGE_OFFSETS or counts != EXPECTED_STAGE_COUNTS:
        raise AssertionError(f"stage table mismatch offsets={offsets} counts={counts}")
    if offsets[-1] + counts[-1] != len(points):
        raise AssertionError("stage table does not cover path")
    print("source_contract=PASS mode=V39 gcode=DISABLED dircomp=0 preload=0 pen_down_calls=0")
    print(f"path_contract=PASS points={len(points)} stages=8 draw_targets=0 crc32={EXPECTED_CRC32:08X}")
    return points


def check_gates() -> None:
    for name, gate in GATES:
        path = ROOT / "gcode" / name
        lines = tuple(path.read_text(encoding="ascii").splitlines())
        if lines != ("G21", "G90", "G94", "M5", gate):
            raise AssertionError(f"{name}: gate mismatch {lines}")
        if any(re.search(r"[XYZFS]|M3|G0|G1", line) for line in lines):
            raise AssertionError(f"{name}: contains motion or pen-down words")
        print(f"gate=PASS command={gate} name={name} sha256={digest(path)}")


def full_grid_metrics() -> singularity.Metrics:
    metrics = singularity.Metrics()
    model = v30.v21.base
    for paper_x in range(15, 283):
        for paper_y in range(15, 196):
            command_x = paper_x + SHIFT[0]
            command_y = paper_y + SHIFT[1]
            theta, psi = model.inverse(command_x, command_y)
            s1 = model.lroundf(theta * model.STAGE1_STEPS_PER_DEG)
            s2 = model.lroundf(psi * model.STAGE2_STEPS_PER_DEG)
            metrics.add_angles(
                s1 / float(model.STAGE1_STEPS_PER_DEG),
                s2 / float(model.STAGE2_STEPS_PER_DEG),
                (float(paper_x), float(paper_y)),
            )
    return metrics


def check_motion(points: tuple[v30.DemoPoint, ...]) -> None:
    v30.configure_model()
    align = v30.ALIGN_PATH[-1]
    current_steps, _, _ = v30.point_margin(align, "V39_ALIGN_START")
    _, end_steps, stats = v30.simulate_commanded_path(
        align.xy, current_steps, points, "V39_REPOSITIONED_A4_GRID"
    )
    expected_end, _, _ = v30.point_margin(points[-1], "V39_END")
    if end_steps != expected_end or points[-1].xy != align.xy:
        raise AssertionError("V39 did not return to ALIGN")
    if stats["minimum_margin"] < 12.0:
        raise AssertionError(f"path joint margin {stats['minimum_margin']:.6f}")
    if stats["maximum_deviation"] > 0.12 or stats["maximum_endpoint_error"] > 0.09:
        raise AssertionError("DDA deviation or endpoint error exceeded")
    maximum_span = max(
        math.dist(a.xy, b.xy) for a, b in zip((align,) + points[:-1], points)
    )
    if maximum_span > 133.5 + 1.0e-9:
        raise AssertionError(f"target span {maximum_span:.6f}")
    for index, point in enumerate(points):
        paper = (point.xy[0] - SHIFT[0], point.xy[1] - SHIFT[1])
        if index == len(points) - 1:
            if paper != ALIGN_PAPER:
                raise AssertionError(f"return ALIGN paper coordinate {paper}")
        else:
            x0, y0, x1, y1 = PAPER_INSET
            if not (x0 <= paper[0] <= x1 and y0 <= paper[1] <= y1):
                raise AssertionError(f"point {index} left paper inset: {paper}")

    grid = full_grid_metrics()
    pulse_path = singularity.scan_routed_path(points)
    singularity.require_safe(grid, "V39 full grid")
    singularity.require_safe(pulse_path, "V39 pulse path")
    if grid.pose_margin.minimum < 12.0:
        raise AssertionError(f"full grid margin {grid.pose_margin.minimum:.6f}")
    print(
        "integer_motion=PASS "
        f"segments={int(stats['segments'])} master_pulses={int(stats['master_pulses'])} "
        f"min_joint_margin_deg={stats['minimum_margin']:.6f} "
        f"max_line_deviation_mm={stats['maximum_deviation']:.6f} "
        f"max_endpoint_error_mm={stats['maximum_endpoint_error']:.6f} "
        f"max_target_span_mm={maximum_span:.6f}"
    )
    print(
        "full_grid=PASS "
        f"samples={grid.samples} min_pose_margin_deg={grid.pose_margin.minimum:.6f} "
        f"min_abs_sin_beta={grid.normalized_jacobian.minimum:.9f} "
        f"max_jacobian_condition={grid.jacobian_condition.maximum:.6f} "
        f"outer_radial_gap_mm={grid.outer_radius_gap.minimum:.6f}"
    )
    print(
        "pulse_path_singularity=PASS "
        f"samples={pulse_path.samples} min_pose_margin_deg={pulse_path.pose_margin.minimum:.6f} "
        f"min_abs_sin_beta={pulse_path.normalized_jacobian.minimum:.9f} "
        f"max_jacobian_condition={pulse_path.jacobian_condition.maximum:.6f}"
    )


def check_build_and_hex() -> str:
    build = BUILD_LOG.read_text(encoding="utf-8", errors="replace")
    html = KEIL_HTML_LOG.read_text(encoding="utf-8", errors="replace")
    require(html, "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx", "correct Keil project")
    require(build, "0 Error(s), 0 Warning(s).", "clean build")
    if "Target not created" in build:
        raise AssertionError("build target was not created")
    image, records, data_bytes = common.base.parse_ihex(HEX_PATH)
    if BUILD_ID not in image:
        raise AssertionError("V39 build ID missing from HEX")
    hex_digest = digest(HEX_PATH)
    if EXPECTED_HEX_SHA256 is not None and hex_digest != EXPECTED_HEX_SHA256:
        raise AssertionError(f"V39 HEX hash changed: {hex_digest}")
    for name, expected in PROTECTED_HEX.items():
        if digest(ROOT / "keil" / name) != expected:
            raise AssertionError(f"protected HEX changed: {name}")
    print("keil_build=PASS project=CORRECT errors=0 warnings=0")
    print(f"intel_hex=PASS records={records} data_bytes={data_bytes} build_id=PASS sha256={hex_digest}")
    print("protected_hex=PASS V36=1 V37=1 V38=1")
    return hex_digest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    points = check_source()
    check_gates()
    check_motion(points)
    if not args.source_only:
        check_build_and_hex()


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
