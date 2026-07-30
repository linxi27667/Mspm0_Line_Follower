#!/usr/bin/env python3
"""Verify the one-file V44 A4 3x3 20 mm square-and-cross calibration."""

from __future__ import annotations

import hashlib
import math
import re
import struct
import zlib
from pathlib import Path

import analyze_diary_repositioned_a4_singularity as singularity
import check_author_a4_15mm_clipped_contour_onefile_v43 as v43
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
    / "AUTHOR_A4_3X3_20MM_SQUARE_CROSS_DRAW_L205_L203_ONEFILE_V44_build.log"
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
    / "AUTHOR_A4_3X3_20MM_SQUARE_CROSS_DRAW_L205_L203_ONEFILE_V44.hex"
)

BUILD_ID = b"AUTHOR_A4_3X3_20MM_SQUARE_CROSS_DRAW_L205_L203_ONEFILE_V44"
EXPECTED_HEX_SHA256 = "EA9CCB7BAF88D6332B10C1D07B4DD8B25AD15B4A2966B7E1A1989D84A48E25EF"
EXPECTED_CRC32 = 0x058FBC5C
SHIFT = (136.0, -38.0)
ALIGN_PAPER = (14.0, 58.0)
AUX_TOGGLE_X_GUARD_MM = 150.0
MARKER_SIZE_MM = 20.0
RIGHT_BOTTOM_INSET_MM = 30.0
SAFE_POLYGON = v43.SAFE_POLYGON

ZONE_CENTERS_PAPER = (
    (40.0, 40.0),
    (40.0, 105.0),
    (80.0, 170.0),
    (148.5, 170.0),
    (148.5, 105.0),
    (148.5, 40.0),
    (270.0, 40.0),
    (270.0, 105.0),
    (260.0, 165.0),
)


def p_paper(x: float, y: float, draw: bool) -> v30.DemoPoint:
    return v30.DemoPoint(
        int(round((x + SHIFT[0]) * 10.0)),
        int(round((y + SHIFT[1]) * 10.0)),
        draw,
    )


def zone_points(cx: float, cy: float) -> tuple[v30.DemoPoint, ...]:
    half = MARKER_SIZE_MM / 2.0
    return (
        p_paper(cx - half, cy - half, False),
        p_paper(cx + half, cy - half, True),
        p_paper(cx + half, cy + half, True),
        p_paper(cx - half, cy + half, True),
        p_paper(cx - half, cy - half, True),
        p_paper(cx - half, cy, False),
        p_paper(cx + half, cy, True),
        p_paper(cx, cy - half, False),
        p_paper(cx, cy + half, True),
    )


EXPECTED_POINTS = (
    p_paper(14.0, 58.0, False),
    p_paper(15.0, 58.0, False),
    p_paper(69.0, 103.0, False),
    p_paper(148.5, 105.0, False),
    *(point for center in ZONE_CENTERS_PAPER for point in zone_points(*center)),
    p_paper(148.5, 105.0, False),
    p_paper(69.0, 103.0, False),
    p_paper(14.0, 58.0, False),
)

GATE = (
    "V44_ONE_FILE/01_M891_RUN_ALL_9_ZONES_20MM_SQUARE_CROSS_V44.gcode",
    "M891",
)

PROTECTED_HEX = dict(v43.PROTECTED_HEX)
PROTECTED_HEX[
    "AUTHOR_A4_15MM_CLIPPED_CONTOUR_PENUP_L205_L203_ONEFILE_V43.hex"
] = v43.EXPECTED_HEX_SHA256


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


def paper_xy(point: v30.DemoPoint) -> tuple[float, float]:
    return point.xy[0] - SHIFT[0], point.xy[1] - SHIFT[1]


def inside_convex_polygon(point: tuple[float, float]) -> bool:
    x, y = point
    cross_products = []
    for (x1, y1), (x2, y2) in zip(
        SAFE_POLYGON, SAFE_POLYGON[1:] + SAFE_POLYGON[:1]
    ):
        cross_products.append((x2 - x1) * (y - y1) - (y2 - y1) * (x - x1))
    return min(cross_products) >= -1.0e-8


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
    require(test_h, "V44 one-file A4 3x3 20 mm square-and-cross", "task comment")
    require(test_c, "source=UART_ONEFILE trigger=M891", "task")
    require(test_c, "stages=AUTO_ALIGN_3X3_CALIBRATION_RETURN", "task")
    require(test_c, "path=A4_3X3_20MM_SQUARE_CROSS_DRAW", "task")
    require(demo_h, BUILD_ID.decode("ascii"), "build ID")
    for needle in (
        "AUTHOR_TEXT_DEMO_PATH_CRC32 == 0x058FBC5Cu",
        "AUTHOR_TEXT_DEMO_PATH_POINT_COUNT == 88u",
        "AUTHOR_TEXT_DEMO_PATH_MOVE_COUNT == 34u",
        "AUTHOR_TEXT_DEMO_PATH_DRAW_COUNT == 54u",
        "AUTHOR_TEXT_DEMO_ZONE_COUNT == 9u",
        "AUTHOR_TEXT_DEMO_STROKE_COUNT == 27u",
        "AUTHOR_TEXT_DEMO_MARKER_SIZE_X10 == 200",
        "AUTHOR_TEXT_DEMO_RIGHT_BOTTOM_INSET_X10 == 300",
        "AUTHOR_TEXT_DEMO_AUX_TOGGLE_MIN_X_X10 == 1500",
        "AUTHOR_TEXT_DEMO_PATH_MAX_SPAN_X10 == 1403",
        "AUTHOR_TEXT_DEMO_MOVE_FEED_MM_MIN == 300.0f",
        "AUTHOR_TEXT_DEMO_DRAW_FEED_MM_MIN == 240.0f",
        "AUTHOR_TEXT_DEMO_ALIGN_PAUSE_MS == 3000u",
        "trigger=M891_ONEFILE_AUTO_ALIGN_3X3_CALIBRATION_RETURN",
        "AUTHOR_TEXT_DEMO_EXEC_WAIT_PEN_DOWN",
        "AUTHOR_TEXT_DEMO_EXEC_WAIT_ALIGN_PAUSE",
        "App_Servo_Pen_Down();",
        "AuthorTextDemo_Fail(\"aux_toggle_x_guard\")",
    ):
        require(demo_c, needle, "V44 executor")
    require(demo_c, '"M891"', "V44 trigger")
    for forbidden in (
        "GCodeSerial_Start",
        "2.0.gcode",
        '"M890"',
        '"M801"',
        *(f'"M{gate}"' for gate in range(817, 890)),
    ):
        if forbidden in demo_c:
            raise AssertionError(f"V44 executor contains forbidden {forbidden!r}")

    points = parse_path(path_h)
    if points != EXPECTED_POINTS:
        raise AssertionError("V44 generated path does not match the reviewed 3x3 layout")
    if path_crc32(points) != EXPECTED_CRC32:
        raise AssertionError("V44 path CRC mismatch")
    if sum(point.draw for point in points) != 54 or len(points) != 88:
        raise AssertionError("V44 move/draw count mismatch")
    offsets = parse_u8_array(path_h, "s_author_text_demo_stage_offset")
    counts = parse_u8_array(path_h, "s_author_text_demo_stage_count")
    if offsets != (0,) or counts != (88,):
        raise AssertionError(f"stage table mismatch offsets={offsets} counts={counts}")
    print(
        "source_contract=PASS mode=V44 one_file=1 "
        f"points={len(points)} moves=34 draws=54 zones=9 strokes=27 "
        f"crc32={EXPECTED_CRC32:08X} gcode=DISABLED dircomp=0 preload=0"
    )
    return points


def check_gate() -> None:
    name, gate = GATE
    path = ROOT / "gcode" / name
    lines = tuple(path.read_text(encoding="ascii").splitlines())
    if lines != ("G21", "G90", "G94", "M5", gate):
        raise AssertionError(f"{name}: gate mismatch {lines}")
    if any(re.search(r"[XYZFS]|M3|G0|G1", line) for line in lines):
        raise AssertionError(f"{name}: contains host motion or pen-down words")
    siblings = tuple((ROOT / "gcode" / "V44_ONE_FILE").glob("*.gcode"))
    if siblings != (path,):
        raise AssertionError(f"V44 must expose exactly one gcode file: {siblings}")
    print("gate_file=PASS count=1 lines=5 trigger=M891 host_motion_words=0")


def check_layout(points: tuple[v30.DemoPoint, ...]) -> None:
    if paper_xy(points[0]) != ALIGN_PAPER or paper_xy(points[-1]) != ALIGN_PAPER:
        raise AssertionError("V44 must start and return at ALIGN")
    if points[:4] != EXPECTED_POINTS[:4] or points[-3:] != EXPECTED_POINTS[-3:]:
        raise AssertionError("V44 ingress or return route changed")
    for index, point in enumerate(points):
        if point.x_x10 < int(AUX_TOGGLE_X_GUARD_MM * 10.0):
            raise AssertionError(f"point {index} crossed empirical X guard")
        if point.draw and not inside_convex_polygon(paper_xy(point)):
            raise AssertionError(f"draw point {index} left safe polygon")
    zone_data = points[4:4 + 9 * 9]
    stroke_count = 0
    previous_draw = False
    for point in zone_data:
        if point.draw and not previous_draw:
            stroke_count += 1
        previous_draw = point.draw
    if stroke_count != 27:
        raise AssertionError(f"expected 27 strokes, got {stroke_count}")
    draw_length = sum(
        math.dist(previous.xy, point.xy)
        for previous, point in zip(points, points[1:])
        if point.draw
    )
    if abs(draw_length - 1080.0) > 1.0e-6:
        raise AssertionError(f"draw length mismatch {draw_length:.6f}")
    draw_paper = [paper_xy(point) for point in points if point.draw]
    bounds = (
        min(x for x, _ in draw_paper),
        max(x for x, _ in draw_paper),
        min(y for _, y in draw_paper),
        max(y for _, y in draw_paper),
    )
    if bounds != (30.0, 280.0, 30.0, 180.0):
        raise AssertionError(f"unexpected draw bounds {bounds}")
    zone1 = tuple(paper_xy(point) for point in points[4:13])
    if min(x for x, _ in zone1) != RIGHT_BOTTOM_INSET_MM:
        raise AssertionError("photo-bottom inset is not 30 mm")
    if min(y for _, y in zone1) != RIGHT_BOTTOM_INSET_MM:
        raise AssertionError("photo-right inset is not 30 mm")
    print(
        "layout=PASS zones=9 marker_mm=20x20 strokes=27 "
        f"draw_length_mm={draw_length:.3f} draw_paper_bounds={bounds} "
        "photo_bottom_right_inset_mm=30 clipped_corner_zones=2"
    )


def check_motion(points: tuple[v30.DemoPoint, ...]) -> None:
    v30.configure_model()
    align = points[0]
    expected_end, _, _ = v30.point_margin(points[-1], "V44_END")
    minimum_home_approach_margin = float("inf")
    maximum_deviation = 0.0
    maximum_endpoint_error = 0.0
    segment_counts: list[int] = []
    pulse_counts: list[int] = []
    for release1 in range(41, 49):
        for release2 in range(41, 49):
            home_user, home_steps = v30.v21.user_from_home_delta(release1, release2)
            _, end_steps, stats = v30.simulate_commanded_path(
                home_user, home_steps, points, f"V44_HOME_{release1}_{release2}"
            )
            if end_steps != expected_end:
                raise AssertionError("V44 did not return to ALIGN")
            _, _, approach_stats = v30.simulate_commanded_path(
                home_user, home_steps, points[:1], f"V44_ALIGN_{release1}_{release2}"
            )
            minimum_home_approach_margin = min(
                minimum_home_approach_margin, approach_stats["minimum_margin"]
            )
            maximum_deviation = max(maximum_deviation, stats["maximum_deviation"])
            maximum_endpoint_error = max(
                maximum_endpoint_error, stats["maximum_endpoint_error"]
            )
            segment_counts.append(int(stats["segments"]))
            pulse_counts.append(int(stats["master_pulses"]))
    align_steps, _, _ = v30.point_margin(align, "V44_ALIGN_START")
    _, contour_end, after_align = v30.simulate_commanded_path(
        align.xy, align_steps, points[1:], "V44_AFTER_ALIGN"
    )
    if contour_end != expected_end:
        raise AssertionError("V44 post-ALIGN path did not return")
    if minimum_home_approach_margin <= 0.0 or after_align["minimum_margin"] < 17.5:
        raise AssertionError("V44 crossed a modeled joint limit")
    if maximum_deviation > 0.12 or maximum_endpoint_error > 0.09:
        raise AssertionError("V44 DDA deviation or endpoint error exceeded")
    maximum_span = max(
        math.dist(previous.xy, point.xy)
        for previous, point in zip(points, points[1:])
    )
    if maximum_span > 140.3:
        raise AssertionError(f"V44 target span {maximum_span:.6f}")
    pulse_path = singularity.scan_routed_path(points)
    singularity.require_safe(pulse_path, "V44 pulse path after ALIGN")
    if pulse_path.pose_margin.minimum < 17.5:
        raise AssertionError(f"V44 pulse path margin {pulse_path.pose_margin.minimum:.6f}")
    penup_length = sum(
        math.dist(previous.xy, point.xy)
        for previous, point in zip(points, points[1:])
        if not point.draw
    )
    draw_length = sum(
        math.dist(previous.xy, point.xy)
        for previous, point in zip(points, points[1:])
        if point.draw
    )
    runtime_minutes = (
        penup_length / 300.0 + draw_length / 240.0 + 27.0 / 60.0 + 3.0 / 60.0
    )
    print(
        "integer_motion=PASS "
        f"home_release_cases=64 segments={min(segment_counts)}..{max(segment_counts)} "
        f"master_pulses={min(pulse_counts)}..{max(pulse_counts)} "
        f"min_home_approach_margin_deg={minimum_home_approach_margin:.6f} "
        f"min_after_align_margin_deg={after_align['minimum_margin']:.6f} "
        f"max_line_deviation_mm={maximum_deviation:.6f} "
        f"max_endpoint_error_mm={maximum_endpoint_error:.6f} "
        f"max_target_span_mm={maximum_span:.6f} runtime_estimate_min={runtime_minutes:.2f}"
    )
    print(
        "singularity_model=PASS "
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
        raise AssertionError("V44 build ID missing from HEX")
    actual = digest(HEX_PATH)
    if actual != EXPECTED_HEX_SHA256:
        raise AssertionError(f"V44 HEX digest mismatch {actual}")
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
    print(f"protected_hex=PASS count={len(PROTECTED_HEX)} versions=V36..V43")


def main() -> None:
    points = check_source()
    check_gate()
    check_layout(points)
    check_motion(points)
    check_build_and_hex()
    check_protected_hex()
    print("offline_author_a4_3x3_calibration_onefile_v44=PASS motion=NONE")


if __name__ == "__main__":
    main()
