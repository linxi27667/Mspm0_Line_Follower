#!/usr/bin/env python3
"""Verify the gated, all-pen-up V40 author-layout A4 centerline probe."""

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
    / "AUTHOR_A4_AUTHOR_LAYOUT_CENTERLINE_PENUP_L205_L203_GATED_V40_build.log"
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
    / "AUTHOR_A4_AUTHOR_LAYOUT_CENTERLINE_PENUP_L205_L203_GATED_V40.hex"
)

BUILD_ID = b"AUTHOR_A4_AUTHOR_LAYOUT_CENTERLINE_PENUP_L205_L203_GATED_V40"
SHIFT = (136.0, -38.0)
ALIGN_PAPER = (14.0, 58.0)
PAPER_INSET = (15.0, 15.0, 282.0, 195.0)
AUX_TOGGLE_X_GUARD_MM = 150.0
KNOWN_SAFE_X_MM = 140.0
KNOWN_UNSAFE_TARGET_X_MM = 136.0
EXPECTED_CRC32 = 0x928E55B1
EXPECTED_HEX_SHA256 = "4DBF1A835D668112ABBF62F698ED1EF04CCE126E3632CD249E5B62D00E2B42A3"
EXPECTED_POINTS = (
    v30.DemoPoint(1510, 200, False),
    v30.DemoPoint(2050, 650, False),
    v30.DemoPoint(2845, 670, False),
    v30.DemoPoint(2050, 650, False),
    v30.DemoPoint(1500, 200, False),
)
EXPECTED_STAGE_OFFSETS = (0, 1, 2, 3, 4)
EXPECTED_STAGE_COUNTS = (1, 1, 1, 1, 1)
GATES = (
    ("AUTHOR_A4_AUTHOR_LAYOUT_ALIGN_RUN_V40.gcode", "M801"),
    ("AUTHOR_A4_AUTHOR_LAYOUT_ENTRY_RUN_V40.gcode", "M825"),
    ("AUTHOR_A4_AUTHOR_LAYOUT_VERIFIED_CENTER_RUN_V40.gcode", "M826"),
    ("AUTHOR_A4_AUTHOR_LAYOUT_PAPER_CENTER_RUN_V40.gcode", "M827"),
    ("AUTHOR_A4_AUTHOR_LAYOUT_RETURN_VERIFIED_RUN_V40.gcode", "M828"),
    ("AUTHOR_A4_AUTHOR_LAYOUT_RETURN_ALIGN_RUN_V40.gcode", "M829"),
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
    require(
        test_h,
        "#define WRITER_TEST_MODE             WRITER_TEST_MODE_AUTHOR_TEXT_DEMO",
        "selected mode",
    )
    require(test_h, "V40 author-layout A4 all-pen-up centerline", "task comment")
    require(test_c, "stages=ALIGN_ENTRY_VERIFIED_CENTER_PAPER_CENTER_RETURN", "task")
    require(test_c, "path=AUTHOR_LAYOUT_CENTERLINE_PENUP", "task")
    require(demo_h, BUILD_ID.decode("ascii"), "build ID")
    for needle in (
        "AUTHOR_TEXT_DEMO_PATH_CRC32 == 0x928E55B1u",
        "AUTHOR_TEXT_DEMO_PATH_POINT_COUNT == 5u",
        "AUTHOR_TEXT_DEMO_PATH_DRAW_COUNT == 0u",
        "AUTHOR_TEXT_DEMO_STAGE_COUNT == 5u",
        "AUTHOR_TEXT_DEMO_PAPER_SHIFT_X_X10 == 1360",
        "AUTHOR_TEXT_DEMO_PAPER_SHIFT_Y_X10 == -380",
        "AUTHOR_TEXT_DEMO_ALIGN_PAPER_X_X10 == 140",
        "AUTHOR_TEXT_DEMO_ALIGN_PAPER_Y_X10 == 580",
        "AUTHOR_TEXT_DEMO_AUX_TOGGLE_MIN_X_X10 == 1500",
        "gates=M801_ALIGN,M825..M829_AUTHOR_LAYOUT_CENTERLINE",
        "AuthorTextDemo_Fail(\"aux_toggle_x_guard\")",
        "AuthorTextDemo_Fail(\"pen_down_target_forbidden\")",
    ):
        require(demo_c, needle, "V40 executor")
    for gate in range(825, 830):
        require(demo_c, f'"M{gate}"', "V40 gate table")
    for forbidden in (
        "App_Servo_Pen_Down",
        "GCodeSerial_Start",
        "2.0.gcode",
        '"M817"',
        '"M818"',
        '"M819"',
        '"M820"',
        '"M821"',
        '"M822"',
        '"M823"',
        '"M824"',
    ):
        if forbidden in demo_c:
            raise AssertionError(f"V40 executor contains forbidden {forbidden!r}")

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
    print("source_contract=PASS mode=V40 gcode=DISABLED dircomp=0 preload=0 pen_down_calls=0")
    print(
        f"path_contract=PASS points={len(points)} stages={len(offsets)} "
        f"draw_targets=0 crc32={EXPECTED_CRC32:08X}"
    )
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
    current_steps, _, _ = v30.point_margin(align, "V40_ALIGN_START")
    _, end_steps, stats = v30.simulate_commanded_path(
        align.xy, current_steps, points, "V40_AUTHOR_LAYOUT_CENTERLINE"
    )
    expected_end, _, _ = v30.point_margin(points[-1], "V40_END")
    if end_steps != expected_end or points[-1].xy != align.xy:
        raise AssertionError("V40 did not return to ALIGN")
    if stats["minimum_margin"] < 20.0:
        raise AssertionError(f"centerline joint margin {stats['minimum_margin']:.6f}")
    if stats["maximum_deviation"] > 0.12 or stats["maximum_endpoint_error"] > 0.09:
        raise AssertionError("DDA deviation or endpoint error exceeded")

    previous = align.xy
    maximum_span = 0.0
    for index, point in enumerate(points):
        if point.xy[0] < AUX_TOGGLE_X_GUARD_MM:
            raise AssertionError(f"point {index} crossed the task-local X guard")
        maximum_span = max(maximum_span, math.dist(previous, point.xy))
        previous = point.xy
    if maximum_span > 79.6 + 1.0e-9:
        raise AssertionError(f"target span {maximum_span:.6f}")
    if not all(
        min(a.xy[0], b.xy[0]) >= AUX_TOGGLE_X_GUARD_MM
        for a, b in zip((align,) + points[:-1], points)
    ):
        raise AssertionError("a segment crossed the task-local X guard")

    expected_paper = (
        (15.0, 58.0),
        (69.0, 103.0),
        (148.5, 105.0),
        (69.0, 103.0),
        ALIGN_PAPER,
    )
    actual_paper = tuple(
        (point.xy[0] - SHIFT[0], point.xy[1] - SHIFT[1]) for point in points
    )
    if actual_paper != expected_paper:
        raise AssertionError(f"paper mapping mismatch {actual_paper!r}")

    grid = full_grid_metrics()
    pulse_path = singularity.scan_routed_path(points)
    if grid.pose_margin.minimum < 5.0:
        raise AssertionError(f"full inset model margin {grid.pose_margin.minimum:.6f}")
    if (
        grid.beta_from_zero.minimum <= 0.0
        or grid.beta_from_180.minimum <= 0.0
        or grid.normalized_jacobian.minimum <= 0.0
        or grid.inner_radius_gap.minimum <= 0.0
        or grid.outer_radius_gap.minimum <= 0.0
    ):
        raise AssertionError("full inset model reached a modeled singularity")
    singularity.require_safe(pulse_path, "V40 pulse path")
    print(
        "integer_motion=PASS "
        f"segments={int(stats['segments'])} master_pulses={int(stats['master_pulses'])} "
        f"min_joint_margin_deg={stats['minimum_margin']:.6f} "
        f"max_line_deviation_mm={stats['maximum_deviation']:.6f} "
        f"max_endpoint_error_mm={stats['maximum_endpoint_error']:.6f} "
        f"max_target_span_mm={maximum_span:.6f}"
    )
    print(
        "aux_toggle_empirical_guard=PASS "
        f"path_x_min_mm={min(p.xy[0] for p in points):.1f} "
        f"known_safe_x_mm={KNOWN_SAFE_X_MM:.1f} "
        f"known_unsafe_target_x_mm={KNOWN_UNSAFE_TARGET_X_MM:.1f} "
        "scope=centerline_diagnostic_not_full_mechanical_proof"
    )
    print(
        "full_inset_model=INFORMATIONAL_PASS_NOT_AUTHORIZED_FOR_MOTION "
        f"samples={grid.samples} min_pose_margin_deg={grid.pose_margin.minimum:.6f} "
        f"min_abs_sin_beta={grid.normalized_jacobian.minimum:.9f} "
        f"max_jacobian_condition={grid.jacobian_condition.maximum:.6f}"
    )
    print(
        "pulse_path_model=PASS "
        f"samples={pulse_path.samples} min_pose_margin_deg={pulse_path.pose_margin.minimum:.6f} "
        f"min_abs_sin_beta={pulse_path.normalized_jacobian.minimum:.9f} "
        f"max_jacobian_condition={pulse_path.jacobian_condition.maximum:.6f}"
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
        raise AssertionError("V40 build ID missing from HEX")
    if digest(HEX_PATH) != EXPECTED_HEX_SHA256:
        raise AssertionError("V40 HEX digest mismatch")
    print(
        "firmware=PASS "
        f"records={records} bytes={data_bytes} sha256={EXPECTED_HEX_SHA256} "
        "build_errors=0 build_warnings=0"
    )


def check_protected_hex() -> None:
    for name, expected in PROTECTED_HEX.items():
        actual = digest(ROOT / "keil" / name)
        if actual != expected:
            raise AssertionError(f"protected HEX changed: {name} {actual}")
        print(f"protected_hex=PASS name={name} sha256={actual}")


def main() -> None:
    points = check_source()
    check_gates()
    check_motion(points)
    check_build_and_hex()
    check_protected_hex()
    print("offline_author_a4_author_layout_centerline_v40=PASS motion=NONE")


if __name__ == "__main__":
    main()
