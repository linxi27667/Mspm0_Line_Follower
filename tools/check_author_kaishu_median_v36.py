"""Verify the gated V36 large Kaishu stroke-median build."""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import check_author_text_demo_v30 as v30
import check_stage2_long_chord_cal_v25 as common
import generate_author_kaishu_median_v36 as generator


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
    ROOT
    / "keil"
    / "AUTHOR_KAISHU_MEDIAN_16MM_L205_L203_GATED_V36_build.log"
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
    / "AUTHOR_KAISHU_MEDIAN_16MM_L205_L203_GATED_V36.hex"
)
V7_SOURCE = (
    ROOT
    / "backups"
    / "GCODE_HOME0_135_CENTER_ANCHOR_V7_20260718_222427"
    / "gcode"
    / "G_Code.txt.gcode"
)

BUILD_ID = b"AUTHOR_KAISHU_MEDIAN_16MM_L205_L203_GATED_V36"
EXPECTED_PATH_COUNT = 130
EXPECTED_MOVE_COUNT = 20
EXPECTED_DRAW_COUNT = 110
EXPECTED_PATH_CRC32 = 0xD1D77A40
EXPECTED_PATH_BOUNDS_X10 = (1792, 562, 2297, 738)
EXPECTED_GLYPH_BOUNDS_UNITS = (
    (171, 41, 950, 759),
    (80, 13, 927, 807),
    (194, 48, 858, 754),
)
EXPECTED_DESIRED_BOUNDS_MM = (
    179.151133501259,
    57.0,
    229.690176322418,
    73.0,
)
POSITION_EPS_MM = 0.15
MAX_SOURCE_QUANTIZATION_ERROR_MM = 0.075
MAX_DRAW_TARGET_SPAN_MM = 9.0
MAX_LINE_DEVIATION_MM = 0.12
MAX_ENDPOINT_ERROR_MM = 0.09
MIN_TEXT_REGION_MARGIN_DEG = 10.0
MIN_PAPER_MARGIN_MM = 15.0
EXPECTED_HEX_SHA256 = (
    "37506BE659CE6652D8016F8894EBDFA5EFA310FE544D5D3D655B5AAE32BC3054"
)

GATES = {
    ROOT / "gcode" / "AUTHOR_KAISHU_MEDIAN_16MM_ALIGN_RUN_V36.gcode": "M801",
    ROOT / "gcode" / "AUTHOR_KAISHU_MEDIAN_16MM_TEXT_RUN_V36.gcode": "M807",
}

PROTECTED_HASHES = {
    ROOT / "keil" / "AUTHOR_STAGE2_RETURN_TAKEUP_23_L203_GATED_V28.hex": (
        "F944FC50448C75607D0577F397E3CBA0567BF6C53D800EE31887E11FAB6B3F06"
    ),
    ROOT / "backups" / "AUTHOR_STAGE2_RETURN_TAKEUP_23_L203_GATED_V28_20260720.zip": (
        "2BC78026469BE78E28CA312F704A8EF350C00AACDE474352CCD88DB186CB191C"
    ),
    ROOT / "keil" / "AUTHOR_STAGED_TEXT_DEMO_L205_L203_GATED_V30.hex": (
        "E37687122A384C8B090C5B78442B982DFE1C301D53055408B5F8E89B0E30F188"
    ),
    ROOT / "backups" / "AUTHOR_STAGED_TEXT_DEMO_L205_L203_GATED_V30_20260720.zip": (
        "6EFB61596CCB073A25B6D1E48CF9E53468FC71216E3F2BDDBF71D93947F51052"
    ),
    ROOT / "keil" / "AUTHOR_STAGED_V7_SINGLELINE_X2_L205_L203_GATED_V31.hex": (
        "02C5E5B81661D9CEBADFAB901FA10D6EFE52F7AC00E6083920D46EAC17B043A2"
    ),
    ROOT / "backups" / "AUTHOR_STAGED_V7_SINGLELINE_X2_L205_L203_GATED_V31_20260720.zip": (
        "A40AF82D873EA0FB8583D87E4B639E6B21726D66F3EEF3ED04DFAFC4F24998B0"
    ),
    ROOT / "keil" / "AUTHOR_FINAL_XY20_5POINT_DOTS_L205_L203_GATED_V32.hex": (
        "4560544A97F3AB4EF8495277B14C33FFF93929B5806256E6A883C4FD1C037C75"
    ),
    ROOT / "backups" / "AUTHOR_FINAL_XY20_5POINT_DOTS_L205_L203_GATED_V32_20260720.zip": (
        "6402599A8B4697EFE39159B5C0077EA7B56A5D19F544E5901655A585DD76A5A8"
    ),
    ROOT / "keil" / "AUTHOR_BOX_XY10_5POINT_DOTS_L205_L203_GATED_V33.hex": (
        "3F677BEEC71CBC335884114CDD0E6722BB6B2CCD8B648AD7FBB127F81A44E2B7"
    ),
    ROOT / "backups" / "AUTHOR_BOX_XY10_5POINT_DOTS_L205_L203_GATED_V33_20260720.zip": (
        "BA88D42156C699F35184FC109DA0D7B0B0E49AD7B1979D119B45B9F71E176FAE"
    ),
    ROOT / "keil" / "AUTHOR_TEXT_Y1095_5POINT_DOTS_L205_L203_GATED_V34.hex": (
        "51711CDD1D1F70C22270F12EC156968C4AF2B94D7457FEF9EAFB1501AA23224D"
    ),
    ROOT / "backups" / "AUTHOR_TEXT_Y1095_5POINT_DOTS_L205_L203_GATED_V34_20260720.zip": (
        "431169C7EB00C02A85BA62CDC36F324D25EF3F12783AED2C057ECE24877F4FC0"
    ),
    ROOT / "keil" / "AUTHOR_V7_TEXT_Y1095_X2_L205_L203_GATED_V35.hex": (
        "8030AA4211343FD63BB6043CE887A33678EBECB57E730512FBB6DD6E149E109C"
    ),
    ROOT / "backups" / "AUTHOR_V7_TEXT_Y1095_X2_L205_L203_GATED_V35_20260720.zip": (
        "B66E8B8AEA48E3FB9CC875DCE40793861F0F0B99316E69275ABA6DE46EE612D2"
    ),
    V7_SOURCE: (
        "901648BF916FBF353F1026387F520284D39FA77782B1BC081496B06B0FA208FD"
    ),
    Path(r"C:\Users\zjl\Desktop\zjl\TI\writer_robot_source\2.0.gcode"): (
        "2F084117B4C1A17A15719B5FBDF36E1960EF3A5BA3DF8F6A7620D98FB69C315C"
    ),
}

for glyph in generator.GLYPHS:
    PROTECTED_HASHES[generator.DATA_DIR / glyph.filename] = glyph.sha256
PROTECTED_HASHES[generator.DATA_DIR / "ARPHICPL.TXT"] = generator.LICENSE_SHA256


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"{label}: missing {needle!r}")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def parse_generated_header(text: str) -> tuple[generator.PathPoint, ...]:
    points = tuple(
        generator.PathPoint(int(x_value), int(y_value), draw_value == "1")
        for x_value, y_value, draw_value in re.findall(
            r"\{(-?\d+), (-?\d+), ([01])u\},", text
        )
    )
    if len(points) != EXPECTED_PATH_COUNT:
        raise AssertionError(f"generated header has {len(points)} path points")
    return points


def check_protected_artifacts() -> None:
    for path, expected in PROTECTED_HASHES.items():
        actual = digest(path)
        if actual != expected:
            raise AssertionError(
                f"protected artifact changed: {path} expected={expected} got={actual}"
            )
    print(
        "protected_artifacts=PASS V28=2 V30=2 V31=2 V32=2 V33=2 V34=2 "
        "V35=2 V7_source=1 kaishu_data=4 external_2_0=1"
    )


def check_source_contract() -> tuple[generator.PathPoint, ...]:
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
        "AuthorTextDemo_Start();",
        "AuthorTextDemo_Update();",
        "return AuthorTextDemo_Process_Frame(frame, len);",
        "stages=ALIGN_TEXT path=KAISHU_MEDIAN_16MM_Y1095 gcode=DISABLED dircomp=0 single_pass=1",
    ):
        require(test_c, needle, "task integration")

    for needle in (
        BUILD_ID.decode("ascii"),
        "AUTHOR_TEXT_DEMO_MOVE_FEED_MM_MIN      (600.0f)",
        "AUTHOR_TEXT_DEMO_DRAW_FEED_MM_MIN      (240.0f)",
        "AUTHOR_TEXT_DEMO_PEN_SETTLE_MS         (500u)",
    ):
        require(demo_h, needle, "demo header")
    for needle in (
        "AUTHOR_TEXT_DEMO_PATH_CRC32 == 0xD1D77A40u",
        "AUTHOR_TEXT_DEMO_PATH_GLYPH_COUNT == 3u",
        "AUTHOR_TEXT_DEMO_PATH_STROKE_COUNT == 20u",
        "AUTHOR_TEXT_DEMO_TARGET_CENTER_X10 == 2050",
        "AUTHOR_TEXT_DEMO_TARGET_CENTER_Y10 == 650",
        "AUTHOR_TEXT_DEMO_TARGET_MAX_GLYPH_HEIGHT_X10 == 160",
        "AUTHOR_TEXT_DEMO_LOCAL_Y_SCALE_X10000 == 10950",
        "AUTHOR_TEXT_DEMO_LOCAL_Y_ANCHOR_X10 == 650",
        "source=HANZI_WRITER_MEDIANS glyphs=3 strokes=20",
        "target_center=(20500,6500) target_max_height=1600",
        "command_bounds=(17920,5620)..(22970,7380)",
        "y_anchor=650 y_scale_x10000=10950",
        "APP_WRITER_DIRECTION_COMP_ENABLE ||",
        "APP_WRITER_DIRECTION_COMP_PRELOAD_ENABLE",
        "gates=M801_ALIGN,M807_TEXT",
        '(strcmp(command, "M807") == 0)',
        'AuthorTextDemo_Fail("unexpected_uart_while_running")',
        '"error:reset_required state=%s pen=UP rehome=1',
        "WriterMotion_Emergency_Stop();",
        "WriterMotion_Start_To_At_Feed(",
    ):
        require(demo_c, needle, "demo executor")
    for stale in (
        "GCodeSerial_Start",
        "2.0.gcode",
        "APP_WRITER_DIR_COMP_PSI_REV",
        "AUTHOR_TEXT_DEMO_STATE_WAIT_AXES",
        "AUTHOR_TEXT_DEMO_STATE_RUNNING_AXES",
        "AUTHOR_TEXT_DEMO_STATE_WAIT_BOX",
        "AUTHOR_TEXT_DEMO_STATE_RUNNING_BOX",
        "AUTHOR_TEXT_DEMO_STAGE_AXES",
        "AUTHOR_TEXT_DEMO_STAGE_BOX",
        'strcmp(command, "M802")',
        'strcmp(command, "M803")',
        'strcmp(command, "M804")',
        'strcmp(command, "M806")',
        "source=V7_SINGLELINE",
    ):
        if stale in demo_c or stale in demo_h:
            raise AssertionError(f"demo executor references prohibited feature {stale}")

    for needle in (
        f"({EXPECTED_PATH_COUNT}u)",
        f"({EXPECTED_MOVE_COUNT}u)",
        f"({EXPECTED_DRAW_COUNT}u)",
        f"(0x{EXPECTED_PATH_CRC32:08X}u)",
        generator.SOURCE_COMMIT,
        "U+5F20 U+4F73 U+4E50",
        "AUTHOR_TEXT_DEMO_PATH_GLYPH_COUNT (3u)",
        "AUTHOR_TEXT_DEMO_PATH_STROKE_COUNT (20u)",
        "AUTHOR_TEXT_DEMO_LOCAL_Y_SCALE_X10000 (10950)",
        "AUTHOR_TEXT_DEMO_LOCAL_Y_ANCHOR_X10 (650)",
        "AUTHOR_TEXT_DEMO_TARGET_CENTER_X10 (2050)",
        "AUTHOR_TEXT_DEMO_TARGET_CENTER_Y10 (650)",
        "AUTHOR_TEXT_DEMO_TARGET_MAX_GLYPH_HEIGHT_X10 (160)",
    ):
        require(path_h, needle, "path header")
    require(main, "if (WriterHome_InitialHome_Task())", "automatic homing")

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
    expected_points = generator.generate_path()
    if header_points != expected_points:
        raise AssertionError("generated V36 path header is stale")
    crc = generator.path_crc32(expected_points)
    if crc != EXPECTED_PATH_CRC32:
        raise AssertionError(f"V36 path CRC changed: {crc:08X}")
    bounds = (
        min(point.x_x10 for point in header_points),
        min(point.y_x10 for point in header_points),
        max(point.x_x10 for point in header_points),
        max(point.y_x10 for point in header_points),
    )
    if bounds != EXPECTED_PATH_BOUNDS_X10:
        raise AssertionError(f"V36 path bounds changed: {bounds}")

    print(
        "source_contract=PASS mode=25 staged=ALIGN_TEXT gates=M801_M807 "
        "path=KAISHU_MEDIAN_16MM_Y1095 gcode_serial=0 direction_comp=0 preload=0 "
        "author_line=0"
    )
    print(
        f"generated_path=PASS points={len(header_points)} "
        f"moves={sum(not point.draw for point in header_points)} "
        f"draws={sum(point.draw for point in header_points)} "
        f"crc32={crc:08X} bounds_x10={bounds}"
    )
    return header_points


def check_layout_contract(points: tuple[generator.PathPoint, ...]) -> None:
    generated = generator.generate()
    if generated.command_points != points:
        raise AssertionError("V36 generated command path mismatch")
    if generated.glyph_bounds_units != EXPECTED_GLYPH_BOUNDS_UNITS:
        raise AssertionError(
            f"glyph median bounds changed: {generated.glyph_bounds_units}"
        )
    if len(generated.desired_points) != len(points):
        raise AssertionError("desired and command path lengths differ")

    desired_xs = [point.x_mm for point in generated.desired_points]
    desired_ys = [point.y_mm for point in generated.desired_points]
    desired_bounds = (
        min(desired_xs),
        min(desired_ys),
        max(desired_xs),
        max(desired_ys),
    )
    for actual, expected in zip(desired_bounds, EXPECTED_DESIRED_BOUNDS_MM):
        if abs(actual - expected) > 1.0e-9:
            raise AssertionError(f"desired bounds changed: {desired_bounds}")

    expected_scale = generator.MAX_GLYPH_HEIGHT_MM / 794.0
    if abs(generated.common_scale_mm_per_unit - expected_scale) > 1.0e-12:
        raise AssertionError("common glyph scale changed")

    maximum_error = 0.0
    for command, desired in zip(points, generated.desired_points):
        recovered_y = generator.LOCAL_Y_ANCHOR_MM + (
            command.y_mm - generator.LOCAL_Y_ANCHOR_MM
        ) / generator.LOCAL_Y_SCALE
        error = math.hypot(
            command.x_mm - desired.x_mm,
            recovered_y - desired.y_mm,
        )
        maximum_error = max(maximum_error, error)
    if maximum_error > MAX_SOURCE_QUANTIZATION_ERROR_MM:
        raise AssertionError(
            f"local transform quantization error {maximum_error:.6f} mm"
        )

    glyph_heights = tuple(
        (bounds[3] - bounds[1]) * generated.common_scale_mm_per_unit
        for bounds in generated.glyph_bounds_units
    )
    if max(glyph_heights) > generator.MAX_GLYPH_HEIGHT_MM + 1.0e-9:
        raise AssertionError(f"glyph height exceeds target: {glyph_heights}")
    print(
        "layout_contract=PASS glyphs=3 strokes=7_8_5 total_strokes=20 "
        f"desired_bounds_mm=({desired_bounds[0]:.3f},{desired_bounds[1]:.3f}).."
        f"({desired_bounds[2]:.3f},{desired_bounds[3]:.3f}) "
        f"glyph_heights_mm={'_'.join(f'{value:.3f}' for value in glyph_heights)} "
        f"max_local_transform_quantization_error_mm={maximum_error:.6f}"
    )


def check_path_shape(
    points: tuple[generator.PathPoint, ...]
) -> tuple[v30.DemoPoint, ...]:
    maximum_draw_span = 0.0
    previous: generator.PathPoint | None = None
    for index, point in enumerate(points):
        if not (
            generator.SAFE_X0_MM <= point.x_mm <= generator.SAFE_X1_MM
            and generator.SAFE_Y0_MM <= point.y_mm <= generator.SAFE_Y1_MM
        ):
            raise AssertionError(f"V36 point {index} left safe subregion")
        if previous is not None and point.draw:
            span = (
                (point.x_mm - previous.x_mm) ** 2
                + (point.y_mm - previous.y_mm) ** 2
            ) ** 0.5
            maximum_draw_span = max(maximum_draw_span, span)
        previous = point
    if maximum_draw_span > MAX_DRAW_TARGET_SPAN_MM:
        raise AssertionError(f"draw target span {maximum_draw_span:.6f} mm")

    current = v30.ALIGN_PATH[-1].xy
    effective: list[v30.DemoPoint] = []
    skipped = 0
    for point in points:
        if (
            abs(point.x_mm - current[0]) <= POSITION_EPS_MM
            and abs(point.y_mm - current[1]) <= POSITION_EPS_MM
        ):
            skipped += 1
            continue
        effective.append(v30.DemoPoint(point.x_x10, point.y_x10, point.draw))
        current = point.xy
    if not effective:
        raise AssertionError("all V36 path targets were skipped")
    print(
        f"path_shape=PASS max_draw_target_span_mm={maximum_draw_span:.6f} "
        f"executor_targets={len(effective)} epsilon_skips={skipped}"
    )
    return tuple(effective)


def check_gate_files() -> dict[str, str]:
    digests: dict[str, str] = {}
    for path, gate in GATES.items():
        lines = tuple(path.read_text(encoding="ascii").splitlines())
        expected = ("G21", "G90", "G94", "M5", gate)
        if lines != expected:
            raise AssertionError(f"{path.name}: gate mismatch {lines}")
        if any(re.search(r"[XYZFS]|M3|G0|G1", line) for line in lines):
            raise AssertionError(f"{path.name}: contains trajectory or pen-down words")
        digests[path.name] = digest(path)
    print("gate_files=PASS count=2 lines_each=5 motion_words=0 pen_down=0")
    for name, file_digest in sorted(digests.items()):
        print(f"gate_sha256 name={name} sha256={file_digest}")
    return digests


def check_integer_motion(effective_points: tuple[v30.DemoPoint, ...]) -> None:
    v30.configure_model()
    minimum_home_margin = float("inf")
    minimum_home_paper = float("inf")
    maximum_home_deviation = 0.0
    approach_segments: list[int] = []
    align_target = v30.ALIGN_PATH[-1]

    for release1 in range(41, 49):
        for release2 in range(41, 49):
            home_user, home_steps = v30.v21.user_from_home_delta(
                release1, release2
            )
            _, end_steps, stats = v30.simulate_commanded_path(
                home_user,
                home_steps,
                v30.ALIGN_PATH,
                f"HOME_{release1}_{release2}_TO_ALIGN",
            )
            expected_steps, _, _ = v30.point_margin(
                align_target, "ALIGN_TARGET"
            )
            if end_steps != expected_steps:
                raise AssertionError("home approach did not reach ALIGN")
            minimum_home_margin = min(
                minimum_home_margin, stats["minimum_margin"]
            )
            minimum_home_paper = min(
                minimum_home_paper,
                home_user[0],
                generator.A4_WIDTH_MM - home_user[0],
                home_user[1],
                generator.A4_HEIGHT_MM - home_user[1],
                stats["minimum_paper_margin"],
            )
            maximum_home_deviation = max(
                maximum_home_deviation, stats["maximum_deviation"]
            )
            approach_segments.append(int(stats["segments"]))

    if minimum_home_paper < MIN_PAPER_MARGIN_MM:
        raise AssertionError(
            f"home approach paper margin {minimum_home_paper:.6f} mm"
        )

    current_steps, _, _ = v30.point_margin(align_target, "ALIGN_START")
    _, end_steps, stats = v30.simulate_commanded_path(
        align_target.xy,
        current_steps,
        effective_points,
        "TEXT",
    )
    expected_end, _, _ = v30.point_margin(
        effective_points[-1], "TEXT_END"
    )
    if end_steps != expected_end:
        raise AssertionError("text path endpoint mismatch")
    if stats["minimum_margin"] < MIN_TEXT_REGION_MARGIN_DEG:
        raise AssertionError(
            f"text joint margin {stats['minimum_margin']:.6f} deg"
        )
    if stats["minimum_paper_margin"] < MIN_PAPER_MARGIN_MM:
        raise AssertionError(
            f"text paper margin {stats['minimum_paper_margin']:.6f} mm"
        )
    if stats["maximum_deviation"] > MAX_LINE_DEVIATION_MM:
        raise AssertionError(
            f"text line deviation {stats['maximum_deviation']:.6f} mm"
        )
    if stats["maximum_endpoint_error"] > MAX_ENDPOINT_ERROR_MM:
        raise AssertionError(
            f"text endpoint error {stats['maximum_endpoint_error']:.6f} mm"
        )

    print(
        "home_approach=PASS combinations=64 "
        "release_delta_s1=41..48 release_delta_s2=41..48 "
        f"segments={min(approach_segments)}..{max(approach_segments)} "
        f"min_joint_margin_deg={minimum_home_margin:.6f} "
        f"min_paper_margin_mm={minimum_home_paper:.6f} "
        f"max_line_deviation_mm={maximum_home_deviation:.6f}"
    )
    print(
        f"text_motion=PASS targets={len(effective_points)} "
        f"segments={int(stats['segments'])} "
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
        raise AssertionError("V36 build ID missing from HEX")
    hex_digest = digest(HEX_PATH)
    if EXPECTED_HEX_SHA256 is not None and hex_digest != EXPECTED_HEX_SHA256:
        raise AssertionError(
            f"V36 HEX hash changed: expected {EXPECTED_HEX_SHA256}, got {hex_digest}"
        )
    print("keil_build=PASS project=CORRECT errors=0 warnings=0")
    print(
        f"intel_hex=PASS records={records} data_bytes={data_bytes} "
        f"build_id=PASS sha256={hex_digest}"
    )
    return hex_digest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    check_protected_artifacts()
    points = check_source_contract()
    check_layout_contract(points)
    effective_points = check_path_shape(points)
    check_gate_files()
    check_integer_motion(effective_points)
    if not args.source_only:
        check_build_and_hex()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise
