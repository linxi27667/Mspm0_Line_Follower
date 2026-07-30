#!/usr/bin/env python3
"""Verify the independent-gate, all-pen-up V38 physical-axis probe."""

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
BUILD_LOG = ROOT / "keil" / "AUTHOR_PENUP_AXIS_XY10_L205_L203_GATED_V38_build.log"
KEIL_HTML_LOG = ROOT / "keil" / "Objects" / "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.build_log.htm"
HEX_PATH = ROOT / "keil" / "AUTHOR_PENUP_AXIS_XY10_L205_L203_GATED_V38.hex"

BUILD_ID = b"AUTHOR_PENUP_AXIS_XY10_L205_L203_GATED_V38"
EXPECTED_POINTS = (
    v30.DemoPoint(1600, 200, False),
    v30.DemoPoint(1500, 200, False),
    v30.DemoPoint(1400, 200, False),
    v30.DemoPoint(1500, 200, False),
    v30.DemoPoint(1500, 300, False),
    v30.DemoPoint(1500, 200, False),
    v30.DemoPoint(1500, 100, False),
    v30.DemoPoint(1500, 200, False),
)
EXPECTED_CRC32 = 0xF5813CC8
EXPECTED_HEX_SHA256 = "9777B6F4DE143A7426F28F6126C990B392F4BE2EA3822E9DF2FE3408670B4A6A"
PROTECTED_HEX = {
    ROOT / "keil" / "AUTHOR_KAISHU_MEDIAN_16MM_L205_L203_GATED_V36.hex":
        "37506BE659CE6652D8016F8894EBDFA5EFA310FE544D5D3D655B5AAE32BC3054",
    ROOT / "keil" / "AUTHOR_REPOSITIONED_A4_PENUP_SWEEP_L205_L203_GATED_V37.hex":
        "499E33BC5D0705BDC36199776040A0336914156A69CCD2C087BF7F27410F3B38",
}

GATES = (
    ("AUTHOR_PENUP_AXIS_PROBE_ALIGN_RUN_V38.gcode", "M801"),
    ("AUTHOR_PENUP_AXIS_PROBE_X_PLUS_10_RUN_V38.gcode", "M809"),
    ("AUTHOR_PENUP_AXIS_PROBE_X_CENTER_RUN_V38.gcode", "M810"),
    ("AUTHOR_PENUP_AXIS_PROBE_X_MINUS_10_RUN_V38.gcode", "M811"),
    ("AUTHOR_PENUP_AXIS_PROBE_X_RETURN_RUN_V38.gcode", "M812"),
    ("AUTHOR_PENUP_AXIS_PROBE_Y_PLUS_10_RUN_V38.gcode", "M813"),
    ("AUTHOR_PENUP_AXIS_PROBE_Y_CENTER_RUN_V38.gcode", "M814"),
    ("AUTHOR_PENUP_AXIS_PROBE_Y_MINUS_10_RUN_V38.gcode", "M815"),
    ("AUTHOR_PENUP_AXIS_PROBE_Y_RETURN_RUN_V38.gcode", "M816"),
)


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


def crc32(points: tuple[v30.DemoPoint, ...]) -> int:
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
    require(test_h, "#define WRITER_TEST_MODE             WRITER_TEST_MODE_AUTHOR_TEXT_DEMO", "selected mode")
    require(test_h, "V38 independent-gate pen-up physical-axis probe", "task comment")
    require(test_c, "stages=ALIGN_XP_X0_XM_X0_YP_Y0_YM_Y0", "task integration")
    require(test_c, "path=PENUP_XY10 gcode=DISABLED dircomp=0 preload=0", "task safety")
    require(demo_h, BUILD_ID.decode("ascii"), "build ID")
    for needle in (
        "AUTHOR_TEXT_DEMO_PATH_CRC32 == 0xF5813CC8u",
        "AUTHOR_TEXT_DEMO_PATH_POINT_COUNT == 8u",
        "AUTHOR_TEXT_DEMO_PATH_DRAW_COUNT == 0u",
        "AuthorTextDemo_Fail(\"pen_down_target_forbidden\")",
        "gates=M801_ALIGN,M809..M816_PENUP_XY10",
        "sequence=XP10_X0_XM10_X0_YP10_Y0_YM10_Y0",
        "&s_author_text_demo_path[s_next_probe_index]",
        "AuthorTextDemo_Probe_Gate_Name(s_next_probe_index)",
    ):
        require(demo_c, needle, "V38 executor")
    for gate in range(809, 817):
        require(demo_c, f'"M{gate}"', "V38 gate table")
    for forbidden in (
        "App_Servo_Pen_Down",
        "GCodeSerial_Start",
        "2.0.gcode",
        '"M808"',
        "PENUP_SERPENTINE",
    ):
        if forbidden in demo_c:
            raise AssertionError(f"V38 executor contains forbidden {forbidden!r}")

    points = parse_path(path_h)
    if points != EXPECTED_POINTS:
        raise AssertionError(f"path mismatch: {points!r}")
    if any(point.draw for point in points):
        raise AssertionError("V38 path contains pen-down target")
    if crc32(points) != EXPECTED_CRC32:
        raise AssertionError("path CRC mismatch")
    print("source_contract=PASS mode=V38 gcode=DISABLED dircomp=0 preload=0 pen_down_calls=0")
    print(f"path_contract=PASS targets={len(points)} independent_gates=8 draw_targets=0 crc32={EXPECTED_CRC32:08X}")
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


def check_motion(points: tuple[v30.DemoPoint, ...]) -> None:
    v30.configure_model()
    align = v30.ALIGN_PATH[-1]
    current_steps, _, _ = v30.point_margin(align, "V38_ALIGN_START")
    _, end_steps, stats = v30.simulate_commanded_path(
        align.xy, current_steps, points, "V38_PENUP_AXIS_PROBE"
    )
    expected_end, _, _ = v30.point_margin(points[-1], "V38_END")
    if end_steps != expected_end or points[-1].xy != align.xy:
        raise AssertionError("V38 did not return to ALIGN")
    if stats["minimum_margin"] < 20.0:
        raise AssertionError(f"probe joint margin {stats['minimum_margin']:.6f}")
    if stats["maximum_deviation"] > 0.12:
        raise AssertionError(f"line deviation {stats['maximum_deviation']:.6f}")
    if stats["maximum_endpoint_error"] > 0.09:
        raise AssertionError(f"endpoint error {stats['maximum_endpoint_error']:.6f}")
    maximum_span = max(
        math.dist(a.xy, b.xy)
        for a, b in zip((align,) + points[:-1], points)
    )
    if maximum_span > 10.0 + 1.0e-9:
        raise AssertionError(f"probe span {maximum_span:.6f}")
    metrics = singularity.scan_routed_path(points)
    singularity.require_safe(metrics, "V38 pulse path")
    print(
        "integer_motion=PASS "
        f"segments={int(stats['segments'])} master_pulses={int(stats['master_pulses'])} "
        f"min_joint_margin_deg={stats['minimum_margin']:.6f} "
        f"max_line_deviation_mm={stats['maximum_deviation']:.6f} "
        f"max_endpoint_error_mm={stats['maximum_endpoint_error']:.6f} "
        f"max_gate_move_mm={maximum_span:.6f}"
    )
    print(
        "singularity=PASS "
        f"pulse_samples={metrics.samples} "
        f"beta_deg={metrics.beta.minimum:.6f}..{metrics.beta.maximum:.6f} "
        f"min_abs_sin_beta={metrics.normalized_jacobian.minimum:.9f} "
        f"max_jacobian_condition={metrics.jacobian_condition.maximum:.6f}"
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
        raise AssertionError("V38 build ID missing from HEX")
    hex_digest = digest(HEX_PATH)
    if EXPECTED_HEX_SHA256 is not None and hex_digest != EXPECTED_HEX_SHA256:
        raise AssertionError(f"V38 HEX hash changed: {hex_digest}")
    for path, expected in PROTECTED_HEX.items():
        if digest(path) != expected:
            raise AssertionError(f"protected HEX changed: {path.name}")
    print("keil_build=PASS project=CORRECT errors=0 warnings=0")
    print(f"intel_hex=PASS records={records} data_bytes={data_bytes} build_id=PASS sha256={hex_digest}")
    print("protected_hex=PASS V36=1 V37=1")
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
