"""Verify the staged, UART-gated V30 four-line text demo."""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import check_author_point_dots_v21 as v21
import check_author_rect_loop_v17 as loop
import check_stage2_long_chord_cal_v25 as common
import check_stage2_return_takeup_v28 as v28
import generate_author_text_demo_v30 as generator


ROOT = Path(__file__).resolve().parents[1]
MOTION_HEADER = ROOT / "APP" / "Inc" / "app_writer_motion.h"
STEPPER_HEADER = ROOT / "APP" / "stepper" / "Inc" / "app_stepper.h"
SERVO_HEADER = ROOT / "APP" / "Inc" / "app_servo.h"
IK_SOURCE = ROOT / "MID" / "Src" / "mid_scara.c"
TEST_HEADER = ROOT / "TASK" / "writer_test.h"
TEST_SOURCE = ROOT / "TASK" / "writer_test.c"
DEMO_HEADER = ROOT / "TASK" / "author_text_demo.h"
DEMO_SOURCE = ROOT / "TASK" / "author_text_demo.c"
PATH_HEADER = ROOT / "TASK" / "author_text_demo_path.h"
MAIN_SOURCE = ROOT / "main.c"
PROJECT_PATH = (
    ROOT / "keil" / "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx"
)
BUILD_LOG = (
    ROOT / "keil" / "AUTHOR_STAGED_TEXT_DEMO_L205_L203_GATED_V30_build.log"
)
KEIL_HTML_LOG = (
    ROOT
    / "keil"
    / "Objects"
    / "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.build_log.htm"
)
HEX_PATH = (
    ROOT / "keil" / "AUTHOR_STAGED_TEXT_DEMO_L205_L203_GATED_V30.hex"
)

BUILD_ID = b"AUTHOR_STAGED_TEXT_DEMO_L205_L203_GATED_V30"
EXPECTED_PATH_COUNT = 4381
EXPECTED_MOVE_COUNT = 76
EXPECTED_DRAW_COUNT = 4305
EXPECTED_PATH_CRC32 = 0x5D2FEEE0
EXPECTED_PATH_BOUNDS_X10 = (1540, 470, 2579, 1229)
EXPECTED_GLYPH_CODEPOINTS = generator.TEXT_CODEPOINTS
MAX_QUANTIZED_ERROR_MM = 0.09
MAX_LINE_DEVIATION_MM = 0.12
MAX_DRAW_SPAN_MM = 0.8
MIN_TEXT_REGION_MARGIN_DEG = 10.0
MIN_PAPER_MARGIN_MM = 15.0


@dataclass(frozen=True)
class DemoPoint:
    x_x10: int
    y_x10: int
    draw: bool

    @property
    def xy(self) -> tuple[float, float]:
        return self.x_x10 / 10.0, self.y_x10 / 10.0


ALIGN_PATH = (DemoPoint(1500, 200, False),)
AXES_PATH = (
    DemoPoint(1500, 200, False),
    DemoPoint(1500, 200, True),
    DemoPoint(1700, 200, False),
    DemoPoint(1700, 200, True),
    DemoPoint(1500, 200, False),
    DemoPoint(1500, 200, True),
    DemoPoint(1500, 400, False),
    DemoPoint(1500, 400, True),
    DemoPoint(1500, 200, False),
    DemoPoint(1500, 200, True),
)
BOX_PATH = (
    DemoPoint(1500, 200, False),
    DemoPoint(1500, 400, True),
    DemoPoint(1700, 400, True),
    DemoPoint(1700, 200, True),
    DemoPoint(1500, 200, True),
    DemoPoint(1800, 200, False),
    DemoPoint(2000, 200, True),
    DemoPoint(2000, 400, True),
    DemoPoint(1800, 400, True),
    DemoPoint(1800, 200, True),
)

GATES = {
    ROOT / "gcode" / "AUTHOR_TEXT_DEMO_ALIGN_RUN_V30.gcode": "M801",
    ROOT / "gcode" / "AUTHOR_TEXT_DEMO_AXES_RUN_V30.gcode": "M802",
    ROOT / "gcode" / "AUTHOR_TEXT_DEMO_BOX_RUN_V30.gcode": "M803",
    ROOT / "gcode" / "AUTHOR_TEXT_DEMO_TEXT_RUN_V30.gcode": "M804",
}


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"{label}: missing {needle!r}")


def configure_model() -> None:
    v28.configure_model()


def parse_c_path(source: str, name: str) -> tuple[DemoPoint, ...]:
    match = re.search(
        rf"static const author_text_demo_path_point_t\s+{name}\[\]\s*=\s*\{{(.*?)\n\}};",
        source,
        re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing C path array {name}")
    points: list[DemoPoint] = []
    for x_value, y_value, draw_value in re.findall(
        r"\{\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*([01])u\s*\}",
        match.group(1),
    ):
        points.append(DemoPoint(int(x_value), int(y_value), draw_value == "1"))
    return tuple(points)


def parse_generated_header(text: str) -> tuple[DemoPoint, ...]:
    points = tuple(
        DemoPoint(int(x_value), int(y_value), draw_value == "1")
        for x_value, y_value, draw_value in re.findall(
            r"\{(-?\d+), (-?\d+), ([01])u\},", text
        )
    )
    if len(points) != EXPECTED_PATH_COUNT:
        raise AssertionError(f"generated header has {len(points)} path points")
    return points


def generated_points() -> tuple[DemoPoint, ...]:
    points = generator.generate_path()
    return tuple(DemoPoint(point.x_x10, point.y_x10, point.draw) for point in points)


def check_source_contract() -> tuple[DemoPoint, ...]:
    motion = MOTION_HEADER.read_text(encoding="ascii")
    stepper = STEPPER_HEADER.read_text(encoding="ascii")
    servo = SERVO_HEADER.read_text(encoding="ascii")
    ik = IK_SOURCE.read_text(encoding="utf-8-sig")
    test_h = TEST_HEADER.read_text(encoding="ascii")
    test_c = TEST_SOURCE.read_text(encoding="ascii")
    demo_h = DEMO_HEADER.read_text(encoding="ascii")
    demo_c = DEMO_SOURCE.read_text(encoding="ascii")
    path_h = PATH_HEADER.read_text(encoding="ascii")
    main = MAIN_SOURCE.read_text(encoding="ascii")

    for needle in (
        "#define APP_WRITER_L1_MM                    (205.0f)",
        "#define APP_WRITER_L2_MM                    (203.0f)",
        "#define APP_WRITER_MACHINE_OFFSET_X_MM      (-129.0f)",
        "#define APP_WRITER_MACHINE_OFFSET_Y_MM      (128.0f)",
        "#define APP_WRITER_THETA_LIMIT_DEG          (-0.773082f)",
        "#define APP_WRITER_PSI_LIMIT_DEG            (134.177381f)",
        "#define APP_WRITER_STAGE1_STEPS_PER_DEG     (40.099216f)",
        "#define APP_WRITER_STAGE2_STEPS_PER_DEG     (40.115790f)",
        "#define APP_WRITER_DIRECTION_COMP_ENABLE     (0u)",
        "#define APP_WRITER_DIRECTION_COMP_PRELOAD_ENABLE      (0u)",
        "#define APP_WRITER_AUTHOR_LINE_EXECUTION_ENABLE (0u)",
        "#define APP_WRITER_A4_ENVELOPE_PROBE_ENABLE  (1u)",
        "#define APP_WRITER_PLAN_SEGMENT_MM          (1.0f)",
    ):
        require(motion, needle, "motion contract")
    require(stepper, "#define LIMIT_STAGE2_HOME_DIR   (1u)", "Stage2 limit")
    require(servo, "#define APP_SERVO_PEN_DOWN_ANGLE_DEG     (0.0f)", "pen down")
    require(servo, "#define APP_SERVO_PEN_UP_ANGLE_DEG       (90.0f)", "pen up")
    require(ik, "float k1 = cfg->l1_mm + cfg->l2_mm * c2;", "unequal-link IK")
    require(ik, "float k2 = cfg->l2_mm * s2;", "unequal-link IK")

    for needle in (
        "#define WRITER_TEST_MODE_AUTHOR_TEXT_DEMO (25u)",
        "#define WRITER_TEST_MODE             WRITER_TEST_MODE_AUTHOR_TEXT_DEMO",
    ):
        require(test_h, needle, "selected mode")
    for needle in (
        '#include "author_text_demo.h"',
        "(WRITER_TEST_MODE != WRITER_TEST_MODE_AUTHOR_TEXT_DEMO)",
        "AuthorTextDemo_Start();",
        "AuthorTextDemo_Update();",
        "return AuthorTextDemo_Process_Frame(frame, len);",
        "stages=ALIGN_AXES_BOX_TEXT gcode=DISABLED dircomp=0 single_pass=1",
    ):
        require(test_c, needle, "task integration")

    for needle in (
        BUILD_ID.decode("ascii"),
        "AUTHOR_TEXT_DEMO_DRAW_FEED_MM_MIN      (240.0f)",
        "AUTHOR_TEXT_DEMO_PEN_SETTLE_MS         (500u)",
    ):
        require(demo_h, needle, "demo header")
    for needle in (
        "AUTHOR_TEXT_DEMO_PATH_CRC32 == 0x5D2FEEE0u",
        "APP_WRITER_DIRECTION_COMP_ENABLE ||",
        "APP_WRITER_DIRECTION_COMP_PRELOAD_ENABLE",
        "gates=M801_ALIGN,M802_AXES,M803_BOX,M804_TEXT",
        'AuthorTextDemo_Fail("unexpected_uart_while_running")',
        '"error:reset_required state=%s pen=UP rehome=1',
        "WriterMotion_Emergency_Stop();",
        "WriterMotion_Start_To_At_Feed(",
    ):
        require(demo_c, needle, "demo executor")
    for stale in ("GCodeSerial_Start", "2.0.gcode", "APP_WRITER_DIR_COMP_PSI_REV"):
        if stale in demo_c or stale in demo_h:
            raise AssertionError(f"demo executor references prohibited feature {stale}")

    require(path_h, f"({EXPECTED_PATH_COUNT}u)", "path count")
    require(path_h, f"({EXPECTED_MOVE_COUNT}u)", "move count")
    require(path_h, f"({EXPECTED_DRAW_COUNT}u)", "draw count")
    require(path_h, f"(0x{EXPECTED_PATH_CRC32:08X}u)", "path CRC")
    require(path_h, generator.FONT_SHA256, "font hash")
    require(path_h, EXPECTED_GLYPH_CODEPOINTS, "glyph list")
    require(main, "if (WriterHome_InitialHome_Task())", "automatic homing")

    if parse_c_path(demo_c, "s_axes_path") != AXES_PATH:
        raise AssertionError("axes path changed")
    if parse_c_path(demo_c, "s_box_path") != BOX_PATH:
        raise AssertionError("box path changed")
    for needle in (
        "AUTHOR_TEXT_DEMO_ALIGN_X_X10     (1500)",
        "AUTHOR_TEXT_DEMO_ALIGN_Y_X10     (200)",
    ):
        require(demo_c, needle, "alignment path")

    tree = ET.parse(PROJECT_PATH)
    names = [node.text for node in tree.findall(".//FileName")]
    for name in (
        "author_text_demo.c",
        "author_text_demo.h",
        "author_text_demo_path.h",
    ):
        if names.count(name) != 1:
            raise AssertionError(f"correct Keil project must contain {name} once")

    header_points = parse_generated_header(path_h)
    expected_points = generated_points()
    if header_points != expected_points:
        raise AssertionError("generated path header is stale")
    crc = generator.path_crc32(generator.generate_path())
    if crc != EXPECTED_PATH_CRC32:
        raise AssertionError(f"path CRC changed: {crc:08X}")
    move_count = sum(not point.draw for point in header_points)
    if move_count != EXPECTED_MOVE_COUNT:
        raise AssertionError("move-point count changed")
    bounds = (
        min(point.x_x10 for point in header_points),
        min(point.y_x10 for point in header_points),
        max(point.x_x10 for point in header_points),
        max(point.y_x10 for point in header_points),
    )
    if bounds != EXPECTED_PATH_BOUNDS_X10:
        raise AssertionError(f"path bounds changed: {bounds}")

    print(
        "source_contract=PASS mode=25 staged=ALIGN_AXES_BOX_TEXT "
        "gcode_serial=0 direction_comp=0 preload=0 author_line=0"
    )
    print(
        f"generated_path=PASS font_sha256={generator.FONT_SHA256} "
        f"points={len(header_points)} moves={move_count} "
        f"draws={len(header_points) - move_count} crc32={crc:08X} "
        f"bounds_x10={bounds}"
    )
    return header_points


def check_gate_files() -> dict[str, str]:
    digests: dict[str, str] = {}
    for path, gate in GATES.items():
        lines = tuple(path.read_text(encoding="ascii").splitlines())
        expected = ("G21", "G90", "G94", "M5", gate)
        if lines != expected:
            raise AssertionError(f"{path.name}: gate mismatch {lines}")
        if any(re.search(r"[XYZFS]|M3|G0|G1", line) for line in lines):
            raise AssertionError(f"{path.name}: contains trajectory or pen-down words")
        digests[path.name] = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    print("gate_files=PASS count=4 lines_each=5 motion_words=0 pen_down=0")
    for name, digest in sorted(digests.items()):
        print(f"gate_sha256 name={name} sha256={digest}")
    return digests


def point_margin(point: DemoPoint, label: str) -> tuple[tuple[int, int], float, float]:
    stage1, stage2, margin, error = v21.quantized_target(label, *point.xy)
    if error > MAX_QUANTIZED_ERROR_MM:
        raise AssertionError(f"{label}: endpoint error {error:.6f} mm")
    return (stage1, stage2), margin, error


def check_path_shape(points: tuple[DemoPoint, ...]) -> tuple[float, float]:
    maximum_draw_span = 0.0
    maximum_move_span = 0.0
    previous: DemoPoint | None = None
    for index, point in enumerate(points):
        x_mm, y_mm = point.xy
        if not (
            generator.SAFE_X0_MM <= x_mm <= generator.SAFE_X1_MM
            and generator.SAFE_Y0_MM <= y_mm <= generator.SAFE_Y1_MM
        ):
            raise AssertionError(f"text point {index} left safe subregion")
        if previous is not None:
            span = math.hypot(x_mm - previous.xy[0], y_mm - previous.xy[1])
            if point.draw:
                maximum_draw_span = max(maximum_draw_span, span)
            else:
                maximum_move_span = max(maximum_move_span, span)
        previous = point
    if maximum_draw_span > MAX_DRAW_SPAN_MM + 1.0e-9:
        raise AssertionError(f"draw span {maximum_draw_span:.6f} mm")
    print(
        f"path_shape=PASS max_draw_span_mm={maximum_draw_span:.6f} "
        f"max_penup_span_mm={maximum_move_span:.6f}"
    )
    return maximum_draw_span, maximum_move_span


def simulate_commanded_path(
    current_nominal: tuple[float, float],
    current_steps: tuple[int, int],
    points: tuple[DemoPoint, ...],
    label: str,
) -> tuple[tuple[float, float], tuple[int, int], dict[str, float]]:
    minimum_margin = float("inf")
    minimum_paper_margin = float("inf")
    maximum_deviation = 0.0
    maximum_endpoint_error = 0.0
    total_segments = 0
    total_master_pulses = 0

    for point_index, point in enumerate(points):
        target = point.xy
        target_steps, target_margin, endpoint_error = point_margin(
            point, f"{label}/POINT_{point_index}"
        )
        minimum_margin = min(minimum_margin, target_margin)
        minimum_paper_margin = min(
            minimum_paper_margin,
            target[0],
            generator.A4_WIDTH_MM - target[0],
            target[1],
            generator.A4_HEIGHT_MM - target[1],
        )
        maximum_endpoint_error = max(maximum_endpoint_error, endpoint_error)

        if target == current_nominal:
            if target_steps != current_steps:
                raise AssertionError(f"{label}: duplicate coordinate changed steps")
            continue

        planned = v21.plan_line(
            current_nominal, target, f"{label}/MOVE_{point_index}"
        )
        total_segments += len(planned)
        for segment_index, segment_steps in enumerate(planned, start=1):
            master, margin, deviation = v21.check_segment_dda(
                current_steps,
                segment_steps,
                current_nominal,
                target,
                f"{label}/MOVE_{point_index}/SEGMENT_{segment_index}",
            )
            total_master_pulses += master
            minimum_margin = min(minimum_margin, margin)
            maximum_deviation = max(maximum_deviation, deviation)
            current_steps = segment_steps
        if current_steps != target_steps:
            raise AssertionError(f"{label}: endpoint steps mismatch")
        current_nominal = target

    if maximum_deviation > MAX_LINE_DEVIATION_MM:
        raise AssertionError(f"{label}: line deviation {maximum_deviation:.6f} mm")
    return current_nominal, current_steps, {
        "minimum_margin": minimum_margin,
        "minimum_paper_margin": minimum_paper_margin,
        "maximum_deviation": maximum_deviation,
        "maximum_endpoint_error": maximum_endpoint_error,
        "segments": float(total_segments),
        "master_pulses": float(total_master_pulses),
    }


def check_integer_motion(text_points: tuple[DemoPoint, ...]) -> None:
    minimum_approach_margin = float("inf")
    minimum_approach_paper = float("inf")
    maximum_approach_deviation = 0.0
    approach_segment_counts: list[int] = []
    align_target = ALIGN_PATH[0]

    for release1 in range(41, 49):
        for release2 in range(41, 49):
            home_user, home_steps = v21.user_from_home_delta(release1, release2)
            _, end_steps, stats = simulate_commanded_path(
                home_user,
                home_steps,
                ALIGN_PATH,
                f"HOME_{release1}_{release2}_TO_ALIGN",
            )
            expected_steps, _, _ = point_margin(align_target, "ALIGN_TARGET")
            if end_steps != expected_steps:
                raise AssertionError("home approach did not reach alignment target")
            minimum_approach_margin = min(
                minimum_approach_margin, stats["minimum_margin"]
            )
            minimum_approach_paper = min(
                minimum_approach_paper,
                home_user[0],
                generator.A4_WIDTH_MM - home_user[0],
                home_user[1],
                generator.A4_HEIGHT_MM - home_user[1],
                stats["minimum_paper_margin"],
            )
            maximum_approach_deviation = max(
                maximum_approach_deviation, stats["maximum_deviation"]
            )
            approach_segment_counts.append(int(stats["segments"]))

    current_nominal = align_target.xy
    current_steps, _, _ = point_margin(align_target, "ALIGN_START")
    stage_stats: dict[str, dict[str, float]] = {}
    for label, path in (
        ("AXES", AXES_PATH),
        ("BOX", BOX_PATH),
        ("TEXT", text_points),
    ):
        current_nominal, current_steps, stats = simulate_commanded_path(
            current_nominal, current_steps, path, label
        )
        stage_stats[label] = stats

    if minimum_approach_paper < MIN_PAPER_MARGIN_MM:
        raise AssertionError(
            f"home approach paper margin {minimum_approach_paper:.6f} mm"
        )
    if stage_stats["TEXT"]["minimum_margin"] < MIN_TEXT_REGION_MARGIN_DEG:
        raise AssertionError(
            f"text joint margin {stage_stats['TEXT']['minimum_margin']:.6f} deg"
        )

    print(
        "home_approach=PASS release_delta_s1=41..48 release_delta_s2=41..48 "
        f"segments={min(approach_segment_counts)}..{max(approach_segment_counts)} "
        f"min_joint_margin_deg={minimum_approach_margin:.6f} "
        f"min_paper_margin_mm={minimum_approach_paper:.6f} "
        f"max_line_deviation_mm={maximum_approach_deviation:.6f}"
    )
    for label in ("AXES", "BOX", "TEXT"):
        stats = stage_stats[label]
        print(
            f"stage_motion=PASS stage={label} segments={int(stats['segments'])} "
            f"master_pulses={int(stats['master_pulses'])} "
            f"min_joint_margin_deg={stats['minimum_margin']:.6f} "
            f"min_paper_margin_mm={stats['minimum_paper_margin']:.6f} "
            f"max_line_deviation_mm={stats['maximum_deviation']:.6f} "
            f"max_endpoint_error_mm={stats['maximum_endpoint_error']:.6f}"
        )


def check_build_and_hex() -> str:
    build = BUILD_LOG.read_text(encoding="utf-8", errors="replace")
    html = KEIL_HTML_LOG.read_text(encoding="utf-8", errors="replace")
    require(
        html,
        "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx",
        "correct Keil project",
    )
    require(build, "0 Error(s), 0 Warning(s).", "clean build")
    if "Target not created" in build:
        raise AssertionError("build log reports target not created")
    image, records, data_bytes = common.base.parse_ihex(HEX_PATH)
    if BUILD_ID not in image:
        raise AssertionError("V30 build ID missing from HEX")
    digest = hashlib.sha256(HEX_PATH.read_bytes()).hexdigest().upper()
    print("keil_build=PASS project=CORRECT errors=0 warnings=0")
    print(
        f"intel_hex=PASS records={records} data_bytes={data_bytes} "
        f"build_id=PASS sha256={digest}"
    )
    return digest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    configure_model()
    points = check_source_contract()
    check_gate_files()
    check_path_shape(points)
    check_integer_motion(points)
    if not args.source_only:
        check_build_and_hex()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise
