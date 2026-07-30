"""Verify the gated V35 two-line V7 text-region Y1095 build."""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import check_author_text_demo_v30 as v30
import check_stage2_long_chord_cal_v25 as common
import generate_author_v7_text_y1095_v35 as generator


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
    / "AUTHOR_V7_TEXT_Y1095_X2_L205_L203_GATED_V35_build.log"
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
    / "AUTHOR_V7_TEXT_Y1095_X2_L205_L203_GATED_V35.hex"
)
LEGACY_CHECKER = (
    ROOT
    / "backups"
    / "GCODE_HOME0_135_CENTER_ANCHOR_V7_20260718_222427"
    / "tools"
    / "check_gcode_home0_135.py"
)

BUILD_ID = b"AUTHOR_V7_TEXT_Y1095_X2_L205_L203_GATED_V35"
EXPECTED_PATH_COUNT = 292
EXPECTED_MOVE_COUNT = 54
EXPECTED_DRAW_COUNT = 238
EXPECTED_PATH_CRC32 = 0x87F7042F
EXPECTED_PATH_BOUNDS_X10 = (1976, 609, 2143, 869)
EXPECTED_COPY_POINT_COUNT = 146
EXPECTED_COPY_Y_DELTA_X10 = (197, 198)
EXPECTED_SOURCE_STROKES = 27
POSITION_EPS_MM = 0.15
MAX_SOURCE_QUANTIZATION_ERROR_MM = 0.071
MAX_DRAW_TARGET_SPAN_MM = 2.62
MAX_LINE_DEVIATION_MM = 0.12
MAX_ENDPOINT_ERROR_MM = 0.09
MIN_TEXT_REGION_MARGIN_DEG = 10.0
MIN_PAPER_MARGIN_MM = 15.0
EXPECTED_HEX_SHA256 = (
    "8030AA4211343FD63BB6043CE887A33678EBECB57E730512FBB6DD6E149E109C"
)

GATES = {
    ROOT / "gcode" / "AUTHOR_V7_TEXT_Y1095_ALIGN_RUN_V35.gcode": "M801",
    ROOT / "gcode" / "AUTHOR_V7_TEXT_Y1095_TEXT_RUN_V35.gcode": "M806",
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
    generator.SOURCE_GCODE: generator.SOURCE_SHA256,
    Path(r"C:\Users\zjl\Desktop\zjl\TI\writer_robot_source\2.0.gcode"): (
        "2F084117B4C1A17A15719B5FBDF36E1960EF3A5BA3DF8F6A7620D98FB69C315C"
    ),
}


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
        "V7_source=1 external_2_0=1"
    )


def check_legacy_source_contract() -> None:
    result = subprocess.run(
        [sys.executable, str(LEGACY_CHECKER), str(generator.SOURCE_GCODE)],
        check=True,
        capture_output=True,
        text=True,
    )
    require(result.stdout, "PASS:", "V7 checker")
    require(
        result.stdout,
        "lines=262 strokes=27 motions=140 G0=26 G1=114 source_zero_returns=1",
        "V7 checker",
    )
    require(result.stdout, "final pen=UP", "V7 checker")
    print(
        "legacy_v7_source=PASS lines=262 strokes=27 motions=140 "
        "G0=26 G1=114 final_pen=UP"
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
        "stages=ALIGN_TEXT path=V7_SINGLELINE_X2_Y1095 gcode=DISABLED dircomp=0 single_pass=1",
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
        "AUTHOR_TEXT_DEMO_PATH_CRC32 == 0x87F7042Fu",
        "AUTHOR_TEXT_DEMO_LOCAL_Y_SCALE_X10000 == 10950",
        "AUTHOR_TEXT_DEMO_LOCAL_Y_ANCHOR_X10 == 650",
        "source=V7_SINGLELINE copies=2 strokes_per_copy=27",
        "command_bounds=(19760,6090)..(21430,8690)",
        "desired_baselines=(670,850) y_anchor=650 y_scale_x10000=10950",
        "APP_WRITER_DIRECTION_COMP_ENABLE ||",
        "APP_WRITER_DIRECTION_COMP_PRELOAD_ENABLE",
        "gates=M801_ALIGN,M806_TEXT",
        '(strcmp(command, "M806") == 0)',
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
    ):
        if stale in demo_c or stale in demo_h:
            raise AssertionError(f"demo executor references prohibited feature {stale}")

    for needle in (
        f"({EXPECTED_PATH_COUNT}u)",
        f"({EXPECTED_MOVE_COUNT}u)",
        f"({EXPECTED_DRAW_COUNT}u)",
        f"(0x{EXPECTED_PATH_CRC32:08X}u)",
        generator.SOURCE_SHA256,
        "U+5F20 U+4F73 U+4E50",
        "AUTHOR_TEXT_DEMO_LOCAL_Y_SCALE_X10000 (10950)",
        "AUTHOR_TEXT_DEMO_LOCAL_Y_ANCHOR_X10 (650)",
        "AUTHOR_TEXT_DEMO_DESIRED_BASELINE1_X10 (670)",
        "AUTHOR_TEXT_DEMO_DESIRED_BASELINE2_X10 (850)",
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
        raise AssertionError("generated V35 path header is stale")
    crc = generator.path_crc32(expected_points)
    if crc != EXPECTED_PATH_CRC32:
        raise AssertionError(f"V35 path CRC changed: {crc:08X}")
    bounds = (
        min(point.x_x10 for point in header_points),
        min(point.y_x10 for point in header_points),
        max(point.x_x10 for point in header_points),
        max(point.y_x10 for point in header_points),
    )
    if bounds != EXPECTED_PATH_BOUNDS_X10:
        raise AssertionError(f"V35 path bounds changed: {bounds}")

    print(
        "source_contract=PASS mode=25 staged=ALIGN_TEXT gates=M801_M806 "
        "path=V7_SINGLELINE_X2_Y1095 gcode_serial=0 direction_comp=0 preload=0 "
        "author_line=0"
    )
    print(
        f"generated_path=PASS points={len(header_points)} "
        f"moves={sum(not point.draw for point in header_points)} "
        f"draws={sum(point.draw for point in header_points)} "
        f"crc32={crc:08X} bounds_x10={bounds}"
    )
    return header_points


def check_copy_contract(points: tuple[generator.PathPoint, ...]) -> None:
    if len(points) != EXPECTED_COPY_POINT_COUNT * 2:
        raise AssertionError("V35 copy split changed")
    first = points[:EXPECTED_COPY_POINT_COUNT]
    second = points[EXPECTED_COPY_POINT_COUNT:]
    for index, (a, b) in enumerate(zip(first, second)):
        if (
            a.x_x10 != b.x_x10
            or (b.y_x10 - a.y_x10) not in EXPECTED_COPY_Y_DELTA_X10
            or a.draw != b.draw
        ):
            raise AssertionError(f"copy mismatch at point {index}")

    source = generator.parse_source_path()
    if len(source) != EXPECTED_COPY_POINT_COUNT:
        raise AssertionError(f"V7 extracted source point count changed: {len(source)}")
    offset_x = generator.horizontal_offset(source)
    max_error = 0.0
    for copy_index, (copy, baseline) in enumerate(
        zip((first, second), generator.LINE_BASELINES_Y_MM)
    ):
        move_count = sum(not point.draw for point in copy)
        if move_count != EXPECTED_SOURCE_STROKES:
            raise AssertionError(
                f"copy {copy_index}: pen-up starts {move_count} != {EXPECTED_SOURCE_STROKES}"
            )
        for point, source_point in zip(copy, source):
            expected_x = source_point.x_mm + offset_x
            desired_y = source_point.y_mm + baseline
            expected_y = generator.LOCAL_Y_ANCHOR_MM + (
                desired_y - generator.LOCAL_Y_ANCHOR_MM
            ) * generator.LOCAL_Y_SCALE
            error = ((point.x_mm - expected_x) ** 2 + (point.y_mm - expected_y) ** 2) ** 0.5
            max_error = max(max_error, error)
    if max_error > MAX_SOURCE_QUANTIZATION_ERROR_MM:
        raise AssertionError(f"source translation error {max_error:.6f} mm")
    print(
        f"copy_contract=PASS copies=2 points_each={EXPECTED_COPY_POINT_COUNT} "
        f"strokes_each={EXPECTED_SOURCE_STROKES} desired_y_delta_mm=18.0 "
        f"command_y_delta_x10={EXPECTED_COPY_Y_DELTA_X10} "
        f"max_local_transform_quantization_error_mm={max_error:.6f}"
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
            raise AssertionError(f"V35 point {index} left safe subregion")
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
        raise AssertionError("all V35 path targets were skipped")
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
        raise AssertionError("V35 build ID missing from HEX")
    hex_digest = digest(HEX_PATH)
    if EXPECTED_HEX_SHA256 is not None and hex_digest != EXPECTED_HEX_SHA256:
        raise AssertionError(
            f"V35 HEX hash changed: expected {EXPECTED_HEX_SHA256}, got {hex_digest}"
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
    check_legacy_source_contract()
    points = check_source_contract()
    check_copy_contract(points)
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
