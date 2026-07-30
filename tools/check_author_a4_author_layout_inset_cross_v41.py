#!/usr/bin/env python3
"""Verify the gated, all-pen-up V41 author-layout A4 inset-cross probe."""

from __future__ import annotations

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
BUILD_LOG = (
    ROOT
    / "keil"
    / "AUTHOR_A4_AUTHOR_LAYOUT_INSET_CROSS_PENUP_L205_L203_GATED_V41_build.log"
)
KEIL_HTML_LOG = (
    ROOT
    / "keil"
    / "Objects"
    / "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.build_log.htm"
)
HEX_PATH = (
    ROOT
    / "keil"
    / "AUTHOR_A4_AUTHOR_LAYOUT_INSET_CROSS_PENUP_L205_L203_GATED_V41.hex"
)

BUILD_ID = b"AUTHOR_A4_AUTHOR_LAYOUT_INSET_CROSS_PENUP_L205_L203_GATED_V41"
SHIFT = (136.0, -38.0)
ALIGN_PAPER = (14.0, 58.0)
AUX_TOGGLE_X_GUARD_MM = 150.0
EXPECTED_CRC32 = 0x3D1BB69D
EXPECTED_HEX_SHA256 = "C0CEA8B20495F9EE739BFD3E82B3FCF653FD444CC5EB728E9731E8C00A1A0897"


def p(x_x10: int, y_x10: int) -> v30.DemoPoint:
    return v30.DemoPoint(x_x10, y_x10, False)


EXPECTED_POINTS = (
    p(1510, 200),
    p(2050, 650),
    p(2845, 670),
    p(3560, 670),
    p(4180, 670),
    p(3560, 670),
    p(2845, 670),
    p(2050, 650),
    p(1660, 670),
    p(1510, 670),
    p(1660, 670),
    p(2050, 650),
    p(2845, 670),
    p(2845, 1270),
    p(2845, 1570),
    p(2845, 1270),
    p(2845, 670),
    p(2845, 70),
    p(2845, -230),
    p(2845, 70),
    p(2845, 670),
    p(2050, 650),
    p(1500, 200),
)
EXPECTED_STAGE_OFFSETS = tuple(range(len(EXPECTED_POINTS)))
EXPECTED_STAGE_COUNTS = (1,) * len(EXPECTED_POINTS)
EXPECTED_PAPER_POINTS = tuple(
    (point.xy[0] - SHIFT[0], point.xy[1] - SHIFT[1])
    for point in EXPECTED_POINTS
)

GATE_NAMES = (
    "01_M801_ALIGN_V41.gcode",
    "02_M830_ENTRY_V41.gcode",
    "03_M831_VERIFIED_CENTER_V41.gcode",
    "04_M832_PAPER_CENTER_V41.gcode",
    "05_M833_X_PLUS_PHOTO_UP_MID_V41.gcode",
    "06_M834_X_PLUS_PHOTO_UP_EDGE_V41.gcode",
    "07_M835_X_PLUS_RETURN_MID_V41.gcode",
    "08_M836_RETURN_PAPER_CENTER_V41.gcode",
    "09_M837_X_MINUS_PHOTO_DOWN_VERIFIED_V41.gcode",
    "10_M838_X_MINUS_PHOTO_DOWN_NEAR_V41.gcode",
    "11_M839_X_MINUS_PHOTO_DOWN_EDGE_V41.gcode",
    "12_M840_X_MINUS_RETURN_NEAR_V41.gcode",
    "13_M841_X_MINUS_RETURN_VERIFIED_V41.gcode",
    "14_M842_RETURN_PAPER_CENTER_V41.gcode",
    "15_M843_Y_PLUS_PHOTO_LEFT_MID_V41.gcode",
    "16_M844_Y_PLUS_PHOTO_LEFT_EDGE_V41.gcode",
    "17_M845_Y_PLUS_RETURN_MID_V41.gcode",
    "18_M846_RETURN_PAPER_CENTER_V41.gcode",
    "19_M847_Y_MINUS_PHOTO_RIGHT_MID_V41.gcode",
    "20_M848_Y_MINUS_PHOTO_RIGHT_EDGE_V41.gcode",
    "21_M849_Y_MINUS_RETURN_MID_V41.gcode",
    "22_M850_RETURN_PAPER_CENTER_V41.gcode",
    "23_M851_FINAL_RETURN_VERIFIED_V41.gcode",
    "24_M852_FINAL_RETURN_ALIGN_V41.gcode",
)
GATES = tuple(
    zip(GATE_NAMES, ("M801",) + tuple(f"M{i}" for i in range(830, 853)))
)

PROTECTED_HEX = {
    "AUTHOR_KAISHU_MEDIAN_16MM_L205_L203_GATED_V36.hex":
        "37506BE659CE6652D8016F8894EBDFA5EFA310FE544D5D3D655B5AAE32BC3054",
    "AUTHOR_REPOSITIONED_A4_PENUP_SWEEP_L205_L203_GATED_V37.hex":
        "499E33BC5D0705BDC36199776040A0336914156A69CCD2C087BF7F27410F3B38",
    "AUTHOR_PENUP_AXIS_XY10_L205_L203_GATED_V38.hex":
        "9777B6F4DE143A7426F28F6126C990B392F4BE2EA3822E9DF2FE3408670B4A6A",
    "AUTHOR_REPOSITIONED_A4_GRID_PENUP_L205_L203_GATED_V39.hex":
        "08EF93F610B68EF9780EC37FEE3D202020D87717FCF250575203EFC09BB5710A",
    "AUTHOR_A4_AUTHOR_LAYOUT_CENTERLINE_PENUP_L205_L203_GATED_V40.hex":
        "4DBF1A835D668112ABBF62F698ED1EF04CCE126E3632CD249E5B62D00E2B42A3",
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
        struct.pack("<hhB", point.x_x10, point.y_x10, int(point.draw))
        for point in points
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
    require(
        test_h,
        "#define WRITER_TEST_MODE             WRITER_TEST_MODE_AUTHOR_TEXT_DEMO",
        "selected mode",
    )
    require(test_h, "V41 author-layout A4 all-pen-up inset-cross", "task comment")
    require(test_c, "stages=ALIGN_ENTRY_CENTER_XP_XM_YP_YM_RETURN", "task")
    require(test_c, "path=AUTHOR_LAYOUT_INSET_CROSS_PENUP", "task")
    require(demo_h, BUILD_ID.decode("ascii"), "build ID")
    for needle in (
        "AUTHOR_TEXT_DEMO_PATH_CRC32 == 0x3D1BB69Du",
        "AUTHOR_TEXT_DEMO_PATH_POINT_COUNT == 23u",
        "AUTHOR_TEXT_DEMO_PATH_DRAW_COUNT == 0u",
        "AUTHOR_TEXT_DEMO_STAGE_COUNT == 23u",
        "AUTHOR_TEXT_DEMO_PAPER_SHIFT_X_X10 == 1360",
        "AUTHOR_TEXT_DEMO_PAPER_SHIFT_Y_X10 == -380",
        "AUTHOR_TEXT_DEMO_AUX_TOGGLE_MIN_X_X10 == 1500",
        "gates=M801_ALIGN,M830..M852_AUTHOR_LAYOUT_INSET_CROSS",
        "AuthorTextDemo_Fail(\"aux_toggle_x_guard\")",
        "AuthorTextDemo_Fail(\"pen_down_target_forbidden\")",
    ):
        require(demo_c, needle, "V41 executor")
    for gate in range(830, 853):
        require(demo_c, f'"M{gate}"', "V41 gate table")
    for forbidden in (
        "App_Servo_Pen_Down",
        "GCodeSerial_Start",
        "2.0.gcode",
        *(f'"M{gate}"' for gate in range(817, 830)),
    ):
        if forbidden in demo_c:
            raise AssertionError(f"V41 executor contains forbidden {forbidden!r}")

    points = parse_path(path_h)
    if points != EXPECTED_POINTS:
        raise AssertionError(f"path mismatch: {points!r}")
    if path_crc32(points) != EXPECTED_CRC32 or any(point.draw for point in points):
        raise AssertionError("path CRC or pen state mismatch")
    offsets = parse_u8_array(path_h, "s_author_text_demo_stage_offset")
    counts = parse_u8_array(path_h, "s_author_text_demo_stage_count")
    if offsets != EXPECTED_STAGE_OFFSETS or counts != EXPECTED_STAGE_COUNTS:
        raise AssertionError(f"stage table mismatch offsets={offsets} counts={counts}")
    print(
        f"source_contract=PASS mode=V41 points={len(points)} stages={len(offsets)} "
        f"crc32={EXPECTED_CRC32:08X} gcode=DISABLED dircomp=0 preload=0 pen_down=0"
    )
    return points


def check_gates() -> None:
    if len(GATES) != 24:
        raise AssertionError("gate table length")
    for name, gate in GATES:
        path = ROOT / "gcode" / name
        lines = tuple(path.read_text(encoding="ascii").splitlines())
        if lines != ("G21", "G90", "G94", "M5", gate):
            raise AssertionError(f"{name}: gate mismatch {lines}")
        if any(re.search(r"[XYZFS]|M3|G0|G1", line) for line in lines):
            raise AssertionError(f"{name}: contains motion or pen-down words")
    print("gate_files=PASS count=24 lines_each=5 motion_words=0 pen_down=0")


def check_motion(points: tuple[v30.DemoPoint, ...]) -> None:
    v30.configure_model()
    align = v30.ALIGN_PATH[-1]
    current_steps, _, _ = v30.point_margin(align, "V41_ALIGN_START")
    _, end_steps, stats = v30.simulate_commanded_path(
        align.xy, current_steps, points, "V41_AUTHOR_LAYOUT_INSET_CROSS"
    )
    expected_end, _, _ = v30.point_margin(points[-1], "V41_END")
    if end_steps != expected_end or points[-1].xy != align.xy:
        raise AssertionError("V41 did not return to ALIGN")
    if stats["minimum_margin"] < 20.0:
        raise AssertionError(f"inset-cross joint margin {stats['minimum_margin']:.6f}")
    if stats["maximum_deviation"] > 0.12 or stats["maximum_endpoint_error"] > 0.09:
        raise AssertionError("DDA deviation or endpoint error exceeded")

    previous = align.xy
    maximum_span = 0.0
    for index, point in enumerate(points):
        if point.xy[0] < AUX_TOGGLE_X_GUARD_MM:
            raise AssertionError(f"point {index} crossed task-local X guard")
        maximum_span = max(maximum_span, math.dist(previous, point.xy))
        previous = point.xy
    if maximum_span > 79.6 + 1.0e-9:
        raise AssertionError(f"target span {maximum_span:.6f}")
    if EXPECTED_PAPER_POINTS[-1] != ALIGN_PAPER:
        raise AssertionError("paper return does not match ALIGN")
    required_edges = {(282.0, 105.0), (15.0, 105.0), (148.5, 195.0), (148.5, 15.0)}
    if not required_edges.issubset(set(EXPECTED_PAPER_POINTS)):
        raise AssertionError("missing an inset-axis edge")
    for paper_x, paper_y in EXPECTED_PAPER_POINTS[:-1]:
        if not (15.0 <= paper_x <= 282.0 and 15.0 <= paper_y <= 195.0):
            raise AssertionError(f"probe left paper inset: {(paper_x, paper_y)}")

    pulse_path = singularity.scan_routed_path(points)
    singularity.require_safe(pulse_path, "V41 pulse path")
    if pulse_path.pose_margin.minimum < 20.0:
        raise AssertionError(f"pulse path margin {pulse_path.pose_margin.minimum:.6f}")
    print(
        "integer_motion=PASS "
        f"segments={int(stats['segments'])} master_pulses={int(stats['master_pulses'])} "
        f"min_joint_margin_deg={stats['minimum_margin']:.6f} "
        f"max_line_deviation_mm={stats['maximum_deviation']:.6f} "
        f"max_endpoint_error_mm={stats['maximum_endpoint_error']:.6f} "
        f"max_target_span_mm={maximum_span:.6f}"
    )
    print(
        "inset_cross_model=PASS_NOT_FULL_A4_PROOF "
        f"pulse_samples={pulse_path.samples} "
        f"min_pose_margin_deg={pulse_path.pose_margin.minimum:.6f} "
        f"min_abs_sin_beta={pulse_path.normalized_jacobian.minimum:.9f} "
        f"max_jacobian_condition={pulse_path.jacobian_condition.maximum:.6f} "
        "aux_toggle_scope=empirical_x_guard_not_four_bar_model"
    )


def check_build_and_hex() -> None:
    build = BUILD_LOG.read_text(encoding="utf-8", errors="replace")
    html = KEIL_HTML_LOG.read_text(encoding="utf-8", errors="replace")
    require(
        html,
        "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx",
        "correct Keil project",
    )
    require(build, "0 Error(s), 0 Warning(s).", "clean compiler build")
    if "Target not created" in build:
        raise AssertionError("build target was not created")
    image, records, data_bytes = common.base.parse_ihex(HEX_PATH)
    if BUILD_ID not in image:
        raise AssertionError("V41 build ID missing from HEX")
    actual = digest(HEX_PATH)
    if actual != EXPECTED_HEX_SHA256:
        raise AssertionError(f"V41 HEX digest mismatch {actual}")
    print(
        "firmware=PASS "
        f"records={records} bytes={data_bytes} sha256={actual} "
        "build_errors=0 build_warnings=0"
    )


def check_protected_hex() -> None:
    for name, expected in PROTECTED_HEX.items():
        actual = digest(ROOT / "keil" / name)
        if actual != expected:
            raise AssertionError(f"protected HEX changed: {name} {actual}")
    print(f"protected_hex=PASS count={len(PROTECTED_HEX)} versions=V36..V40")


def main() -> None:
    points = check_source()
    check_gates()
    check_motion(points)
    check_build_and_hex()
    check_protected_hex()
    print("offline_author_a4_author_layout_inset_cross_v41=PASS motion=NONE")


if __name__ == "__main__":
    main()
