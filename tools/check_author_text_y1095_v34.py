"""Verify the gated V34 text-region local-Y compensation endpoint test."""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import check_author_text_demo_v30 as v30
import check_stage2_long_chord_cal_v25 as common


ROOT = Path(__file__).resolve().parents[1]
MOTION_HEADER = ROOT / "APP" / "Inc" / "app_writer_motion.h"
STEPPER_HEADER = ROOT / "APP" / "stepper" / "Inc" / "app_stepper.h"
SERVO_HEADER = ROOT / "APP" / "Inc" / "app_servo.h"
IK_SOURCE = ROOT / "MID" / "Src" / "mid_scara.c"
TEST_HEADER = ROOT / "TASK" / "writer_test.h"
TEST_SOURCE = ROOT / "TASK" / "writer_test.c"
POINT_HEADER = ROOT / "TASK" / "final_xy_point_test.h"
POINT_SOURCE = ROOT / "TASK" / "final_xy_point_test.c"
MAIN_SOURCE = ROOT / "main.c"
PROJECT_PATH = (
    ROOT / "keil" / "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx"
)
BUILD_LOG = (
    ROOT
    / "keil"
    / "AUTHOR_TEXT_Y1095_5POINT_DOTS_L205_L203_GATED_V34_build.log"
)
KEIL_HTML_LOG = (
    ROOT
    / "keil"
    / "Objects"
    / "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.build_log.htm"
)
HEX_PATH = (
    ROOT / "keil" / "AUTHOR_TEXT_Y1095_5POINT_DOTS_L205_L203_GATED_V34.hex"
)

BUILD_ID = b"AUTHOR_TEXT_Y1095_5POINT_DOTS_L205_L203_GATED_V34"
EXPECTED_HEX_SHA256 = "51711CDD1D1F70C22270F12EC156968C4AF2B94D7457FEF9EAFB1501AA23224D"
MAX_LINE_DEVIATION_MM = 0.12
MAX_ENDPOINT_ERROR_MM = 0.09
MIN_MARKED_TARGET_MARGIN_DEG = 10.0
MIN_PAPER_MARGIN_MM = 15.0


@dataclass(frozen=True)
class PointSpec:
    name: str
    x_mm: float
    y_mm: float


POINTS = (
    PointSpec("O_BASE", 205.0, 65.0),
    PointSpec("W", 185.0, 65.0),
    PointSpec("O_FROM_W", 205.0, 65.0),
    PointSpec("E", 225.0, 65.0),
    PointSpec("O_FROM_E", 205.0, 65.0),
    PointSpec("S", 205.0, 43.1),
    PointSpec("O_FROM_S", 205.0, 65.0),
    PointSpec("N", 205.0, 86.9),
    PointSpec("O_FROM_N", 205.0, 65.0),
)

ALIGN = v30.DemoPoint(1500, 200, False)

GATES = {
    ROOT / "gcode" / "AUTHOR_TEXT_Y1095_ALIGN_RUN_V34.gcode": "M801",
    ROOT / "gcode" / "AUTHOR_TEXT_Y1095_DOTS_RUN_V34.gcode": "M805",
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
    ROOT
    / "backups"
    / "GCODE_HOME0_135_CENTER_ANCHOR_V7_20260718_222427"
    / "gcode"
    / "G_Code.txt.gcode": (
        "901648BF916FBF353F1026387F520284D39FA77782B1BC081496B06B0FA208FD"
    ),
    Path(r"C:\Users\zjl\Desktop\zjl\TI\writer_robot_source\2.0.gcode"): (
        "2F084117B4C1A17A15719B5FBDF36E1960EF3A5BA3DF8F6A7620D98FB69C315C"
    ),
}


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"{label}: missing {needle!r}")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def check_protected_artifacts() -> None:
    for path, expected in PROTECTED_HASHES.items():
        actual = digest(path)
        if actual != expected:
            raise AssertionError(
                f"protected artifact changed: {path} expected={expected} got={actual}"
            )
    print(
        "protected_artifacts=PASS V28=2 V30=2 V31=2 V32=2 V33=2 "
        "V7_source=1 external_2_0=1"
    )


def parse_targets(source: str) -> tuple[PointSpec, ...]:
    pattern = re.compile(
        r'\{"([A-Z0-9_]+)",\s*(-?\d+(?:\.\d+)?)f,\s*'
        r'(-?\d+(?:\.\d+)?)f\},'
    )
    return tuple(
        PointSpec(match.group(1), float(match.group(2)), float(match.group(3)))
        for match in pattern.finditer(source)
    )


def check_source_contract() -> None:
    motion = MOTION_HEADER.read_text(encoding="ascii")
    stepper = STEPPER_HEADER.read_text(encoding="ascii")
    servo = SERVO_HEADER.read_text(encoding="ascii")
    ik = IK_SOURCE.read_text(encoding="utf-8-sig")
    test_h = TEST_HEADER.read_text(encoding="ascii")
    test_c = TEST_SOURCE.read_text(encoding="ascii")
    point_h = POINT_HEADER.read_text(encoding="ascii")
    point_c = POINT_SOURCE.read_text(encoding="ascii")
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
        "#define WRITER_TEST_MODE_FINAL_XY_POINT_DOTS (26u)",
        "#define WRITER_TEST_MODE             WRITER_TEST_MODE_FINAL_XY_POINT_DOTS",
    ):
        require(test_h, needle, "selected mode")
    for needle in (
        '#include "final_xy_point_test.h"',
        "FinalXYPointTest_Start();",
        "FinalXYPointTest_Update();",
        "return FinalXYPointTest_Process_Frame(frame, len);",
        "stages=ALIGN_DOTS unique_points=5 marks=9 gcode=DISABLED dircomp=0",
    ):
        require(test_c, needle, "task integration")

    for needle in (
        BUILD_ID.decode("ascii"),
        "#define FINAL_XY_POINT_TEST_TARGET_COUNT       (9u)",
        "#define FINAL_XY_POINT_TEST_MARK_COUNT         (9u)",
        "#define FINAL_XY_POINT_TEST_UNIQUE_POINT_COUNT (5u)",
        "#define FINAL_XY_POINT_TEST_CENTER_STAMP_COUNT (5u)",
        "#define FINAL_XY_POINT_TEST_POSITION_EPS_MM    (0.08f)",
        "#define FINAL_XY_POINT_TEST_ALIGN_FEED_MM_MIN  (600.0f)",
        "#define FINAL_XY_POINT_TEST_MOVE_FEED_MM_MIN   (240.0f)",
    ):
        require(point_h, needle, "point header")
    for needle in (
        "FinalXYPointTest_Config_Matches",
        '"DOTV34"',
        "gates=M801_ALIGN,M805_DOTS gcode=DISABLED dircomp=0",
        "O=(20500,6500) W=(18500,6500) E=(22500,6500) S=(20500,4310) N=(20500,8690)",
        "y_scale_x10000=10950",
        "order=O,W,O,E,O,S,O,N,O",
        "WriterMotion_Start_To_At_Feed(",
        "App_Servo_Pen_Down();",
        "App_Servo_Pen_Up();",
        "WriterMotion_Emergency_Stop();",
        '(strcmp(command, "M801") == 0)',
        '(strcmp(command, "M805") == 0)',
        'FinalXYPointTest_Fail("unexpected_uart_while_running")',
        "unique_points=5 center_stamps=5",
        "gcode=DISABLED",
    ):
        require(point_c, needle, "point executor")
    for prohibited in (
        "M501",
        "GCodeSerial_Start",
        "2.0.gcode",
        "APP_WRITER_DIR_COMP_PSI_REV",
    ):
        if prohibited in point_c or prohibited in point_h:
            raise AssertionError(f"point executor references prohibited feature {prohibited}")

    actual_points = parse_targets(point_c)
    if actual_points != POINTS:
        raise AssertionError(
            f"embedded V34 point list changed\nexpected={POINTS}\nactual={actual_points}"
        )
    if len({(point.x_mm, point.y_mm) for point in actual_points}) != 5:
        raise AssertionError("V34 unique point count is not five")
    if sum(point.name.startswith("O_") for point in actual_points) != 5:
        raise AssertionError("V34 center stamp count is not five")

    tree = ET.parse(PROJECT_PATH)
    names = [node.text for node in tree.findall(".//FileName")]
    for name in ("final_xy_point_test.c", "final_xy_point_test.h"):
        if names.count(name) != 1:
            raise AssertionError(f"correct Keil project must contain {name} once")
    require(main, "if (WriterHome_InitialHome_Task())", "automatic homing")

    print(
        "source_contract=PASS mode=26 stages=ALIGN_DOTS gates=M801_M805 "
        "targets=9 marks=9 unique_points=5 center_stamps=5 "
        "move_feed=240 gcode_serial=0 direction_comp=0 preload=0 author_line=0"
    )


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


def check_geometry_contract() -> None:
    center = (205.0, 65.0)
    cardinals = {
        "W": (185.0, 65.0),
        "E": (225.0, 65.0),
        "S": (205.0, 43.1),
        "N": (205.0, 86.9),
    }
    expected_radius = {"W": 20.0, "E": 20.0, "S": 21.9, "N": 21.9}
    for name, point in cardinals.items():
        distance = math.hypot(point[0] - center[0], point[1] - center[1])
        if abs(distance - expected_radius[name]) > 1.0e-9:
            raise AssertionError(f"{name}: center distance changed: {distance}")
    if math.dist(cardinals["W"], cardinals["E"]) != 40.0:
        raise AssertionError("W-E span changed")
    if abs(math.dist(cardinals["S"], cardinals["N"]) - 43.8) > 1.0e-9:
        raise AssertionError("S-N span changed")

    for previous, target in zip(POINTS, POINTS[1:]):
        distance = math.hypot(
            target.x_mm - previous.x_mm, target.y_mm - previous.y_mm
        )
        expected = 20.0 if previous.name in {"O_BASE", "W", "O_FROM_W", "E"} else 21.9
        if abs(distance - expected) > 1.0e-9:
            raise AssertionError(
                f"{previous.name}->{target.name}: move is {distance} mm"
            )
    print(
        "geometry_contract=PASS O_to_WE_mm=20 O_to_SN_mm=21.9 "
        "W_to_E_mm=40 S_to_N_mm=43.8 y_scale=1.095"
    )


def check_integer_motion() -> None:
    v30.configure_model()
    minimum_home_margin = float("inf")
    minimum_home_paper = float("inf")
    maximum_home_deviation = 0.0
    approach_segments: list[int] = []

    for release1 in range(41, 49):
        for release2 in range(41, 49):
            home_user, home_steps = v30.v21.user_from_home_delta(release1, release2)
            _, end_steps, stats = v30.simulate_commanded_path(
                home_user,
                home_steps,
                (ALIGN,),
                f"HOME_{release1}_{release2}_TO_ALIGN",
            )
            expected_steps, _, _ = v30.point_margin(ALIGN, "ALIGN_TARGET")
            if end_steps != expected_steps:
                raise AssertionError("home approach did not reach ALIGN")
            minimum_home_margin = min(minimum_home_margin, stats["minimum_margin"])
            minimum_home_paper = min(
                minimum_home_paper,
                home_user[0],
                generator_a4_width() - home_user[0],
                home_user[1],
                generator_a4_height() - home_user[1],
                stats["minimum_paper_margin"],
            )
            maximum_home_deviation = max(
                maximum_home_deviation, stats["maximum_deviation"]
            )
            approach_segments.append(int(stats["segments"]))

    current_steps, _, _ = v30.point_margin(ALIGN, "ALIGN_START")
    dot_path = tuple(
        v30.DemoPoint(round(point.x_mm * 10), round(point.y_mm * 10), False)
        for point in POINTS
    )
    _, end_steps, stats = v30.simulate_commanded_path(
        ALIGN.xy, current_steps, dot_path, "DOTS"
    )
    expected_end, _, _ = v30.point_margin(dot_path[-1], "DOTS_END")
    if end_steps != expected_end:
        raise AssertionError("dot sequence endpoint mismatch")
    if stats["minimum_margin"] < MIN_MARKED_TARGET_MARGIN_DEG:
        raise AssertionError(
            f"dot path joint margin {stats['minimum_margin']:.6f} deg"
        )
    if stats["minimum_paper_margin"] < MIN_PAPER_MARGIN_MM:
        raise AssertionError(
            f"dot path paper margin {stats['minimum_paper_margin']:.6f} mm"
        )
    if stats["maximum_deviation"] > MAX_LINE_DEVIATION_MM:
        raise AssertionError(
            f"dot path line deviation {stats['maximum_deviation']:.6f} mm"
        )
    if stats["maximum_endpoint_error"] > MAX_ENDPOINT_ERROR_MM:
        raise AssertionError(
            f"dot endpoint error {stats['maximum_endpoint_error']:.6f} mm"
        )

    print(
        "home_approach=PASS release_delta_s1=41..48 release_delta_s2=41..48 "
        f"segments={min(approach_segments)}..{max(approach_segments)} "
        f"min_joint_margin_deg={minimum_home_margin:.6f} "
        f"min_paper_margin_mm={minimum_home_paper:.6f} "
        f"max_line_deviation_mm={maximum_home_deviation:.6f}"
    )
    print(
        f"dot_motion=PASS targets=9 segments={int(stats['segments'])} "
        f"master_pulses={int(stats['master_pulses'])} "
        f"min_joint_margin_deg={stats['minimum_margin']:.6f} "
        f"min_paper_margin_mm={stats['minimum_paper_margin']:.6f} "
        f"max_line_deviation_mm={stats['maximum_deviation']:.6f} "
        f"max_endpoint_error_mm={stats['maximum_endpoint_error']:.6f}"
    )


def generator_a4_width() -> float:
    return v30.generator.A4_WIDTH_MM


def generator_a4_height() -> float:
    return v30.generator.A4_HEIGHT_MM


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
        raise AssertionError("V34 build ID missing from HEX")
    hex_digest = digest(HEX_PATH)
    if EXPECTED_HEX_SHA256 is not None and hex_digest != EXPECTED_HEX_SHA256:
        raise AssertionError(
            f"V34 HEX hash changed: expected {EXPECTED_HEX_SHA256}, got {hex_digest}"
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
    check_source_contract()
    check_gate_files()
    check_geometry_contract()
    check_integer_motion()
    if not args.source_only:
        check_build_and_hex()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise
