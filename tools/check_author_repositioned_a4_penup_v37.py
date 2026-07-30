#!/usr/bin/env python3
"""Verify the UART-gated V37 repositioned-A4 pen-up envelope sweep."""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import struct
import sys
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
BUILD_LOG = ROOT / "keil" / (
    "AUTHOR_REPOSITIONED_A4_PENUP_SWEEP_L205_L203_GATED_V37_build.log"
)
KEIL_HTML_LOG = ROOT / "keil" / "Objects" / (
    "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.build_log.htm"
)
HEX_PATH = ROOT / "keil" / (
    "AUTHOR_REPOSITIONED_A4_PENUP_SWEEP_L205_L203_GATED_V37.hex"
)

BUILD_ID = b"AUTHOR_REPOSITIONED_A4_PENUP_SWEEP_L205_L203_GATED_V37"
EXPECTED_POINTS = (
    v30.DemoPoint(1540, -530, False),
    v30.DemoPoint(2875, -530, False),
    v30.DemoPoint(4210, -530, False),
    v30.DemoPoint(4210, 370, False),
    v30.DemoPoint(2875, 370, False),
    v30.DemoPoint(1540, 370, False),
    v30.DemoPoint(1540, 1270, False),
    v30.DemoPoint(2875, 1270, False),
    v30.DemoPoint(4210, 1270, False),
    v30.DemoPoint(2875, 370, False),
    v30.DemoPoint(1500, 200, False),
)
EXPECTED_CRC32 = 0xA36AE1A5
EXPECTED_HEX_SHA256 = "499E33BC5D0705BDC36199776040A0336914156A69CCD2C087BF7F27410F3B38"
V36_HEX_SHA256 = "37506BE659CE6652D8016F8894EBDFA5EFA310FE544D5D3D655B5AAE32BC3054"
COMMAND_SHIFT = (139.0, -68.0)
PAPER_INSET = (15.0, 15.0, 282.0, 195.0)
ALIGN_PAPER = (11.0, 88.0)
MAX_TARGET_SPAN_MM = 161.1
MAX_LINE_DEVIATION_MM = 0.12
MAX_ENDPOINT_ERROR_MM = 0.09
MIN_SWEEP_JOINT_MARGIN_DEG = 10.0

GATES = {
    ROOT / "gcode" / "AUTHOR_REPOSITIONED_A4_PENUP_ALIGN_RUN_V37.gcode": "M801",
    ROOT / "gcode" / "AUTHOR_REPOSITIONED_A4_PENUP_SWEEP_RUN_V37.gcode": "M808",
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


def path_crc32(points: tuple[v30.DemoPoint, ...]) -> int:
    payload = b"".join(
        struct.pack("<hhB", point.x_x10, point.y_x10, int(point.draw))
        for point in points
    )
    return zlib.crc32(payload) & 0xFFFFFFFF


def check_source_contract() -> tuple[v30.DemoPoint, ...]:
    motion = MOTION_HEADER.read_text(encoding="ascii")
    test_h = TEST_HEADER.read_text(encoding="ascii")
    test_c = TEST_SOURCE.read_text(encoding="ascii")
    demo_h = DEMO_HEADER.read_text(encoding="ascii")
    demo_c = DEMO_SOURCE.read_text(encoding="ascii")
    path_h = PATH_HEADER.read_text(encoding="ascii")

    for needle in (
        "#define APP_WRITER_L1_MM                    (205.0f)",
        "#define APP_WRITER_L2_MM                    (203.0f)",
        "#define APP_WRITER_MACHINE_OFFSET_X_MM      (-129.0f)",
        "#define APP_WRITER_MACHINE_OFFSET_Y_MM      (128.0f)",
        "#define APP_WRITER_DIRECTION_COMP_ENABLE     (0u)",
        "#define APP_WRITER_DIRECTION_COMP_PRELOAD_ENABLE      (0u)",
        "#define APP_WRITER_AUTHOR_LINE_EXECUTION_ENABLE (0u)",
        "#define APP_WRITER_A4_ENVELOPE_PROBE_ENABLE  (1u)",
        "#define APP_WRITER_PLAN_SEGMENT_MM          (1.0f)",
    ):
        require(motion, needle, "motion contract")
    require(test_h, "#define WRITER_TEST_MODE             WRITER_TEST_MODE_AUTHOR_TEXT_DEMO", "selected mode")
    require(test_h, "V37 repositioned-A4 pen-up envelope sweep", "task comment")
    require(test_c, "stages=ALIGN_PENUP_SWEEP path=REPOSITIONED_A4_15MM_INSET", "task integration")
    require(test_c, "gcode=DISABLED dircomp=0 preload=0", "task safety")
    require(demo_h, BUILD_ID.decode("ascii"), "build ID")
    require(demo_h, "AUTHOR_TEXT_DEMO_MOVE_FEED_MM_MIN      (600.0f)", "move feed")

    for needle in (
        "AUTHOR_TEXT_DEMO_PATH_CRC32 == 0xA36AE1A5u",
        "AUTHOR_TEXT_DEMO_PATH_DRAW_COUNT == 0u",
        "AUTHOR_TEXT_DEMO_PATH_ALL_PEN_UP == 1u",
        "AuthorTextDemo_Fail(\"pen_down_target_forbidden\")",
        "gates=M801_ALIGN,M808_PENUP_SWEEP",
        '(strcmp(command, "M801") == 0)',
        '(strcmp(command, "M808") == 0)',
        "gcode=DISABLED dircomp=0 preload=0 pen=UP",
        "WriterMotion_Emergency_Stop();",
    ):
        require(demo_c, needle, "V37 executor")
    for forbidden in (
        "App_Servo_Pen_Down",
        "GCodeSerial_Start",
        "2.0.gcode",
        'strcmp(command, "M807")',
    ):
        if forbidden in demo_c:
            raise AssertionError(f"V37 executor contains forbidden {forbidden!r}")

    for needle in (
        "AUTHOR_TEXT_DEMO_PATH_POINT_COUNT (11u)",
        "AUTHOR_TEXT_DEMO_PATH_MOVE_COUNT  (11u)",
        "AUTHOR_TEXT_DEMO_PATH_DRAW_COUNT  (0u)",
        "AUTHOR_TEXT_DEMO_PATH_CRC32       (0xA36AE1A5u)",
        "AUTHOR_TEXT_DEMO_PATH_ALL_PEN_UP  (1u)",
        "AUTHOR_TEXT_DEMO_PAPER_SHIFT_X_X10 (1390)",
        "AUTHOR_TEXT_DEMO_PAPER_SHIFT_Y_X10 (-680)",
        "AUTHOR_TEXT_DEMO_ALIGN_PAPER_X_X10 (110)",
        "AUTHOR_TEXT_DEMO_ALIGN_PAPER_Y_X10 (880)",
    ):
        require(path_h, needle, "generated path")

    points = parse_path(path_h)
    if points != EXPECTED_POINTS:
        raise AssertionError(f"V37 path mismatch: {points!r}")
    if any(point.draw for point in points):
        raise AssertionError("V37 path contains a pen-down target")
    if path_crc32(points) != EXPECTED_CRC32:
        raise AssertionError("V37 path CRC mismatch")
    print("source_contract=PASS mode=V37 gcode=DISABLED dircomp=0 preload=0 pen_down_calls=0")
    print(f"path_contract=PASS targets={len(points)} draw_targets=0 crc32={EXPECTED_CRC32:08X}")
    return points


def check_gate_files() -> None:
    for path, gate in GATES.items():
        lines = tuple(path.read_text(encoding="ascii").splitlines())
        if lines != ("G21", "G90", "G94", "M5", gate):
            raise AssertionError(f"{path.name}: gate mismatch {lines}")
        if any(re.search(r"[XYZFS]|M3|G0|G1", line) for line in lines):
            raise AssertionError(f"{path.name}: contains motion or pen-down words")
        print(f"gate=PASS name={path.name} sha256={digest(path)}")


def check_motion(points: tuple[v30.DemoPoint, ...]) -> None:
    v30.configure_model()
    align = v30.ALIGN_PATH[-1]

    minimum_home_margin = float("inf")
    maximum_home_deviation = 0.0
    home_segment_counts: list[int] = []
    for release1 in range(41, 49):
        for release2 in range(41, 49):
            home_user, home_steps = v30.v21.user_from_home_delta(release1, release2)
            _, home_end_steps, home_stats = v30.simulate_commanded_path(
                home_user,
                home_steps,
                v30.ALIGN_PATH,
                f"V37_HOME_{release1}_{release2}_TO_ALIGN",
            )
            expected_align_steps, _, _ = v30.point_margin(align, "V37_ALIGN_TARGET")
            if home_end_steps != expected_align_steps:
                raise AssertionError("home approach did not reach ALIGN")
            minimum_home_margin = min(minimum_home_margin, home_stats["minimum_margin"])
            maximum_home_deviation = max(maximum_home_deviation, home_stats["maximum_deviation"])
            home_segment_counts.append(int(home_stats["segments"]))

    current_steps, _, _ = v30.point_margin(align, "V37_ALIGN_START")
    _, end_steps, stats = v30.simulate_commanded_path(
        align.xy, current_steps, points, "V37_PENUP_SWEEP"
    )
    expected_end, _, _ = v30.point_margin(points[-1], "V37_SWEEP_END")
    if end_steps != expected_end:
        raise AssertionError("V37 sweep did not end at ALIGN")
    if stats["minimum_margin"] < MIN_SWEEP_JOINT_MARGIN_DEG:
        raise AssertionError(f"joint margin {stats['minimum_margin']:.6f} deg")
    if stats["maximum_deviation"] > MAX_LINE_DEVIATION_MM:
        raise AssertionError(f"line deviation {stats['maximum_deviation']:.6f} mm")
    if stats["maximum_endpoint_error"] > MAX_ENDPOINT_ERROR_MM:
        raise AssertionError(f"endpoint error {stats['maximum_endpoint_error']:.6f} mm")

    previous = align.xy
    maximum_span = 0.0
    for index, point in enumerate(points):
        paper = (point.xy[0] - COMMAND_SHIFT[0], point.xy[1] - COMMAND_SHIFT[1])
        if index == len(points) - 1:
            if paper != ALIGN_PAPER:
                raise AssertionError(f"final ALIGN paper point {paper}")
        else:
            x0, y0, x1, y1 = PAPER_INSET
            if not (x0 <= paper[0] <= x1 and y0 <= paper[1] <= y1):
                raise AssertionError(f"sweep point {index} left paper inset: {paper}")
        maximum_span = max(maximum_span, math.dist(previous, point.xy))
        previous = point.xy
    if maximum_span > MAX_TARGET_SPAN_MM + 0.01:
        raise AssertionError(f"target span {maximum_span:.6f} mm")

    metrics = singularity.scan_routed_path(points)
    singularity.require_safe(metrics, "V37 pulse path")
    conservative_inset = 15.0 - stats["maximum_deviation"]
    print(
        "home_to_align=PASS release_delta_s1=41..48 release_delta_s2=41..48 "
        f"segments={min(home_segment_counts)}..{max(home_segment_counts)} "
        f"min_joint_margin_deg={minimum_home_margin:.6f} "
        f"max_line_deviation_mm={maximum_home_deviation:.6f}"
    )
    print(
        "integer_motion=PASS "
        f"segments={int(stats['segments'])} master_pulses={int(stats['master_pulses'])} "
        f"min_joint_margin_deg={stats['minimum_margin']:.6f} "
        f"max_line_deviation_mm={stats['maximum_deviation']:.6f} "
        f"max_endpoint_error_mm={stats['maximum_endpoint_error']:.6f} "
        f"max_target_span_mm={maximum_span:.6f} "
        f"conservative_edge_inset_mm={conservative_inset:.6f}"
    )
    print(
        "singularity=PASS "
        f"pulse_samples={metrics.samples} "
        f"beta_deg={metrics.beta.minimum:.6f}..{metrics.beta.maximum:.6f} "
        f"min_abs_sin_beta={metrics.normalized_jacobian.minimum:.9f} "
        f"max_jacobian_condition={metrics.jacobian_condition.maximum:.6f} "
        f"inner_gap_mm={metrics.inner_radius_gap.minimum:.6f} "
        f"outer_gap_mm={metrics.outer_radius_gap.minimum:.6f}"
    )


def check_build_and_hex() -> str:
    build = BUILD_LOG.read_text(encoding="utf-8", errors="replace")
    html = KEIL_HTML_LOG.read_text(encoding="utf-8", errors="replace")
    require(html, "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx", "correct Keil project")
    require(build, "0 Error(s), 0 Warning(s).", "clean build")
    if "Target not created" in build:
        raise AssertionError("build log reports target not created")
    image, records, data_bytes = common.base.parse_ihex(HEX_PATH)
    if BUILD_ID not in image:
        raise AssertionError("V37 build ID missing from HEX")
    hex_digest = digest(HEX_PATH)
    if EXPECTED_HEX_SHA256 is not None and hex_digest != EXPECTED_HEX_SHA256:
        raise AssertionError(f"V37 HEX hash changed: {hex_digest}")
    v36_path = ROOT / "keil" / "AUTHOR_KAISHU_MEDIAN_16MM_L205_L203_GATED_V36.hex"
    if digest(v36_path) != V36_HEX_SHA256:
        raise AssertionError("protected V36 HEX changed")
    print("keil_build=PASS project=CORRECT errors=0 warnings=0")
    print(f"intel_hex=PASS records={records} data_bytes={data_bytes} build_id=PASS sha256={hex_digest}")
    print("protected_v36_hex=PASS")
    return hex_digest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    points = check_source_contract()
    check_gate_files()
    check_motion(points)
    if not args.source_only:
        check_build_and_hex()


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
