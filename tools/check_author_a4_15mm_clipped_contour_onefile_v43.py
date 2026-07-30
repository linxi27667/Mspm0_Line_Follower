#!/usr/bin/env python3
"""Verify the one-file, all-pen-up V43 A4 clipped-contour probe."""

from __future__ import annotations

import hashlib
import math
import re
import struct
import zlib
from pathlib import Path

import analyze_diary_repositioned_a4_singularity as singularity
import analyze_author_a4_15mm_safe_region_v42 as region
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
    / "AUTHOR_A4_15MM_CLIPPED_CONTOUR_PENUP_L205_L203_ONEFILE_V43_build.log"
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
    / "AUTHOR_A4_15MM_CLIPPED_CONTOUR_PENUP_L205_L203_ONEFILE_V43.hex"
)

BUILD_ID = b"AUTHOR_A4_15MM_CLIPPED_CONTOUR_PENUP_L205_L203_ONEFILE_V43"
SHIFT = (136.0, -38.0)
ALIGN_PAPER = (14.0, 58.0)
AUX_TOGGLE_X_GUARD_MM = 150.0
EXPECTED_CRC32 = 0xF1AAA103
EXPECTED_HEX_SHA256 = "CEDB989DF655F96AA60CFE18E11E832006C121B20306CA1F3045CB7C7A97CC7F"


def p(x_x10: int, y_x10: int) -> v30.DemoPoint:
    return v30.DemoPoint(x_x10, y_x10, False)


EXPECTED_POINTS = (
    p(1500, 200),
    p(1510, 200),
    p(2050, 650),
    p(2845, 670),
    p(2845, 70),
    p(2845, -230),
    p(3560, -230),
    p(4170, -230),
    p(4170, 470),
    p(4170, 1170),
    p(4170, 1240),
    p(3930, 1550),
    p(3260, 1550),
    p(2560, 1550),
    p(2180, 1550),
    p(1860, 1320),
    p(1530, 1070),
    p(1520, 420),
    p(1510, -230),
    p(2110, -230),
    p(2845, -230),
    p(2845, 70),
    p(2845, 670),
    p(2050, 650),
    p(1500, 200),
)
EXPECTED_STAGE_OFFSETS = (0,)
EXPECTED_STAGE_COUNTS = (len(EXPECTED_POINTS),)
EXPECTED_PAPER_POINTS = tuple(
    (point.xy[0] - SHIFT[0], point.xy[1] - SHIFT[1])
    for point in EXPECTED_POINTS
)
SAFE_POLYGON = (
    (15.0, 15.0),
    (281.0, 15.0),
    (281.0, 162.0),
    (257.0, 193.0),
    (82.0, 193.0),
    (17.0, 145.0),
)

GATES = (("V43_ONE_FILE/01_M890_RUN_ALL_ALIGN_CONTOUR_RETURN_V43.gcode", "M890"),)

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
    "AUTHOR_A4_AUTHOR_LAYOUT_INSET_CROSS_PENUP_L205_L203_GATED_V41.hex":
        "C0CEA8B20495F9EE739BFD3E82B3FCF653FD444CC5EB728E9731E8C00A1A0897",
    "AUTHOR_A4_15MM_CLIPPED_CONTOUR_PENUP_L205_L203_GATED_V42.hex":
        "19681E4484B1EE23742D9C9E2A4B2D2FB156C9FDF27CC742D4A194B22712D686",
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
    require(test_h, "V43 one-file A4 all-pen-up clipped-contour", "task comment")
    require(test_c, "source=UART_ONEFILE trigger=M890", "task")
    require(test_c, "stages=AUTO_ALIGN_CLIPPED_CONTOUR_RETURN", "task")
    require(test_c, "path=A4_15MM_CLIPPED_CONTOUR_PENUP", "task")
    require(demo_h, BUILD_ID.decode("ascii"), "build ID")
    for needle in (
        "AUTHOR_TEXT_DEMO_PATH_CRC32 == 0xF1AAA103u",
        "AUTHOR_TEXT_DEMO_PATH_POINT_COUNT == 25u",
        "AUTHOR_TEXT_DEMO_PATH_DRAW_COUNT == 0u",
        "AUTHOR_TEXT_DEMO_STAGE_COUNT == 1u",
        "AUTHOR_TEXT_DEMO_PAPER_SHIFT_X_X10 == 1360",
        "AUTHOR_TEXT_DEMO_PAPER_SHIFT_Y_X10 == -380",
        "AUTHOR_TEXT_DEMO_AUX_TOGGLE_MIN_X_X10 == 1500",
        "AUTHOR_TEXT_DEMO_CONTOUR_MARGIN_MDEG == 15000",
        "AUTHOR_TEXT_DEMO_MOVE_FEED_MM_MIN == 300.0f",
        "AUTHOR_TEXT_DEMO_WAYPOINT_PAUSE_MS == 1500u",
        "trigger=M890_ONEFILE_AUTO_ALIGN_CONTOUR_RETURN",
        "AUTHOR_TEXT_DEMO_EXEC_WAIT_WAYPOINT",
        "s_exec_state = AUTHOR_TEXT_DEMO_EXEC_WAIT_WAYPOINT",
        "AuthorTextDemo_Fail(\"aux_toggle_x_guard\")",
        "AuthorTextDemo_Fail(\"pen_down_target_forbidden\")",
    ):
        require(demo_c, needle, "V43 executor")
    require(demo_c, '"M890"', "V43 trigger")
    for forbidden in (
        "App_Servo_Pen_Down",
        "GCodeSerial_Start",
        "2.0.gcode",
        '"M801"',
        *(f'"M{gate}"' for gate in range(817, 890)),
    ):
        if forbidden in demo_c:
            raise AssertionError(f"V43 executor contains forbidden {forbidden!r}")

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
        f"source_contract=PASS mode=V43 one_file=1 points={len(points)} stages={len(offsets)} "
        f"crc32={EXPECTED_CRC32:08X} gcode=DISABLED dircomp=0 preload=0 pen_down=0"
    )
    return points


def check_gates() -> None:
    if len(GATES) != 1:
        raise AssertionError("gate table length")
    for name, gate in GATES:
        path = ROOT / "gcode" / name
        lines = tuple(path.read_text(encoding="ascii").splitlines())
        if lines != ("G21", "G90", "G94", "M5", gate):
            raise AssertionError(f"{name}: gate mismatch {lines}")
        if any(re.search(r"[XYZFS]|M3|G0|G1", line) for line in lines):
            raise AssertionError(f"{name}: contains motion or pen-down words")
    print("gate_files=PASS count=1 lines=5 trigger=M890 motion_words=0 pen_down=0")


def check_motion(points: tuple[v30.DemoPoint, ...]) -> None:
    v30.configure_model()
    align = v30.ALIGN_PATH[-1]
    expected_end, _, _ = v30.point_margin(points[-1], "V43_END")
    if points[0].xy != align.xy or points[-1].xy != align.xy:
        raise AssertionError("V43 path must start and finish at ALIGN")
    minimum_home_approach_margin = float("inf")
    maximum_deviation = 0.0
    maximum_endpoint_error = 0.0
    segment_counts: list[int] = []
    pulse_counts: list[int] = []
    for release1 in range(41, 49):
        for release2 in range(41, 49):
            home_user, home_steps = v30.v21.user_from_home_delta(release1, release2)
            _, end_steps, stats = v30.simulate_commanded_path(
                home_user,
                home_steps,
                points,
                f"V43_HOME_{release1}_{release2}_ONEFILE_CONTOUR",
            )
            if end_steps != expected_end:
                raise AssertionError("V43 did not return to ALIGN")
            _, _, approach_stats = v30.simulate_commanded_path(
                home_user,
                home_steps,
                points[:1],
                f"V43_HOME_{release1}_{release2}_TO_ALIGN",
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
    align_steps, _, _ = v30.point_margin(align, "V43_ALIGN_START")
    _, contour_end_steps, contour_stats = v30.simulate_commanded_path(
        align.xy,
        align_steps,
        points[1:],
        "V43_CONTOUR_AFTER_ALIGN",
    )
    if contour_end_steps != expected_end:
        raise AssertionError("V43 contour did not return to ALIGN")
    if minimum_home_approach_margin <= 0.0:
        raise AssertionError(
            f"home approach crossed a modeled limit {minimum_home_approach_margin:.6f}"
        )
    if contour_stats["minimum_margin"] < 15.5:
        raise AssertionError(
            f"clipped-contour joint margin {contour_stats['minimum_margin']:.6f}"
        )
    if maximum_deviation > 0.12 or maximum_endpoint_error > 0.09:
        raise AssertionError("DDA deviation or endpoint error exceeded")

    previous = points[0].xy
    maximum_span = 0.0
    for index, point in enumerate(points[1:], start=1):
        if point.xy[0] < AUX_TOGGLE_X_GUARD_MM:
            raise AssertionError(f"point {index} crossed task-local X guard")
        maximum_span = max(maximum_span, math.dist(previous, point.xy))
        previous = point.xy
    if maximum_span > 79.6 + 1.0e-9:
        raise AssertionError(f"target span {maximum_span:.6f}")
    if EXPECTED_PAPER_POINTS[0] != ALIGN_PAPER or EXPECTED_PAPER_POINTS[-1] != ALIGN_PAPER:
        raise AssertionError("paper start/return does not match ALIGN")
    if not set(SAFE_POLYGON).issubset(set(EXPECTED_PAPER_POINTS)):
        raise AssertionError("missing a clipped-contour vertex")
    for paper_x, paper_y in EXPECTED_PAPER_POINTS[1:-1]:
        if not (15.0 <= paper_x <= 282.0 and 15.0 <= paper_y <= 195.0):
            raise AssertionError(f"probe left paper inset: {(paper_x, paper_y)}")

    polygon_area = abs(sum(
        x1 * y2 - x2 * y1
        for (x1, y1), (x2, y2) in zip(SAFE_POLYGON, SAFE_POLYGON[1:] + SAFE_POLYGON[:1])
    )) / 2.0
    continuous_minimum = float("inf")
    for p0, p1 in zip(SAFE_POLYGON, SAFE_POLYGON[1:] + SAFE_POLYGON[:1]):
        sample_count = max(1, math.ceil(math.dist(p0, p1) / 0.25))
        for sample in range(sample_count + 1):
            ratio = sample / sample_count
            paper_x = p0[0] + (p1[0] - p0[0]) * ratio
            paper_y = p0[1] + (p1[1] - p0[1]) * ratio
            continuous_minimum = min(
                continuous_minimum,
                region.quantized_metrics(paper_x, paper_y)[2],
            )
    if continuous_minimum < 15.5 or polygon_area / (267.0 * 180.0) < 0.94:
        raise AssertionError(
            f"polygon margin/area failed {continuous_minimum:.6f} {polygon_area:.3f}"
        )

    pulse_path = singularity.scan_routed_path(points)
    singularity.require_safe(pulse_path, "V43 pulse path after ALIGN")
    if pulse_path.pose_margin.minimum < 15.5:
        raise AssertionError(f"pulse path margin {pulse_path.pose_margin.minimum:.6f}")
    print(
        "integer_motion=PASS "
        f"home_release_cases=64 segments={min(segment_counts)}..{max(segment_counts)} "
        f"master_pulses={min(pulse_counts)}..{max(pulse_counts)} "
        f"min_home_approach_margin_deg={minimum_home_approach_margin:.6f} "
        f"min_contour_margin_deg={contour_stats['minimum_margin']:.6f} "
        f"max_line_deviation_mm={maximum_deviation:.6f} "
        f"max_endpoint_error_mm={maximum_endpoint_error:.6f} "
        f"max_target_span_mm={maximum_span:.6f}"
    )
    print(
        "clipped_contour_model=PASS_NOT_FULL_15MM_RECTANGLE "
        f"pulse_samples={pulse_path.samples} "
        f"min_pose_margin_deg={pulse_path.pose_margin.minimum:.6f} "
        f"min_abs_sin_beta={pulse_path.normalized_jacobian.minimum:.9f} "
        f"max_jacobian_condition={pulse_path.jacobian_condition.maximum:.6f} "
        f"polygon_area_fraction={polygon_area / (267.0 * 180.0):.9f} "
        f"continuous_polygon_min_margin_deg={continuous_minimum:.6f} "
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
        raise AssertionError("V43 build ID missing from HEX")
    actual = digest(HEX_PATH)
    if actual != EXPECTED_HEX_SHA256:
        raise AssertionError(f"V43 HEX digest mismatch {actual}")
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
    print(f"protected_hex=PASS count={len(PROTECTED_HEX)} versions=V36..V42")


def main() -> None:
    points = check_source()
    check_gates()
    check_motion(points)
    check_build_and_hex()
    check_protected_hex()
    print("offline_author_a4_15mm_clipped_contour_onefile_v43=PASS motion=NONE")


if __name__ == "__main__":
    main()
