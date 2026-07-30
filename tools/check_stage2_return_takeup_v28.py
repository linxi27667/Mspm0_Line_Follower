"""Verify the gated V28 Stage2 23-pulse return-takeup diagnostic."""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

import check_author_point_dots_v21 as v21
import check_stage2_long_chord_cal_v25 as common


ROOT = Path(__file__).resolve().parents[1]
MOTION_HEADER = ROOT / "APP" / "Inc" / "app_writer_motion.h"
IK_SOURCE = ROOT / "MID" / "Src" / "mid_scara.c"
STEPPER_HEADER = ROOT / "APP" / "stepper" / "Inc" / "app_stepper.h"
TEST_HEADER = ROOT / "TASK" / "writer_test.h"
TEST_SOURCE = ROOT / "TASK" / "writer_test.c"
CAL_HEADER = ROOT / "TASK" / "stage2_chord_cal_test.h"
CAL_SOURCE = ROOT / "TASK" / "stage2_chord_cal_test.c"
MAIN_SOURCE = ROOT / "main.c"
PROJECT_PATH = (
    ROOT / "keil" / "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx"
)
GCODE_PATH = ROOT / "gcode" / "AUTHOR_STAGE2_RETURN_TAKEUP_23_RUN_V28.gcode"
BUILD_LOG = (
    ROOT / "keil" / "AUTHOR_STAGE2_RETURN_TAKEUP_23_L203_GATED_V28_build.log"
)
KEIL_HTML_LOG = (
    ROOT
    / "keil"
    / "Objects"
    / "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.build_log.htm"
)
HEX_PATH = ROOT / "keil" / "AUTHOR_STAGE2_RETURN_TAKEUP_23_L203_GATED_V28.hex"

BUILD_ID = b"AUTHOR_STAGE2_RETURN_TAKEUP_23_L203_GATED_V28"
START_USER = (216.798, 171.867)
EXPECTED_START_STEPS = (2668, 5880)
LOGICAL_POSITIONS = (0, 400, 800, 1200, 1600, 1200, 800, 400, 0)
MOTOR_OFFSETS = (0, 400, 800, 1200, 1600, 1177, 777, 377, -23)
LEG_PULSES = 400
TAKEUP_PULSES = 23
TOTAL_RAW_PULSES = 3223
STAGE1_NOMINAL_SCALE = 40.099216
STAGE2_NOMINAL_SCALE = 40.115790
STAGE1_SCALE_MIN = 40.007831
STAGE1_SCALE_MAX = 40.190898
STAGE2_SCALE_MIN = 39.0
STAGE2_SCALE_MAX = 43.0
STAGE2_REFERENCE_STEPS = 5416
REQUIRED_PAPER_MARGIN_MM = 30.0
REQUIRED_JOINT_MARGIN_DEG = 10.0
EXPECTED_GCODE = ("G21", "G90", "G94", "M5", "M501")
MAX_APPROACH_DEVIATION_MM = 0.12


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"{label}: missing {needle!r}")


def configure_model() -> None:
    common.START_USER = START_USER
    common.EXPECTED_START_STEPS = EXPECTED_START_STEPS
    common.RAW_PULSES = max(MOTOR_OFFSETS)
    common.STAGE1_NOMINAL_SCALE = STAGE1_NOMINAL_SCALE
    common.STAGE2_NOMINAL_SCALE = STAGE2_NOMINAL_SCALE
    common.STAGE1_SCALE_MIN = STAGE1_SCALE_MIN
    common.STAGE1_SCALE_MAX = STAGE1_SCALE_MAX
    common.STAGE2_SCALE_MIN = STAGE2_SCALE_MIN
    common.STAGE2_SCALE_MAX = STAGE2_SCALE_MAX
    common.STAGE2_REFERENCE_STEPS = STAGE2_REFERENCE_STEPS
    common.REQUIRED_PAPER_MARGIN_MM = REQUIRED_PAPER_MARGIN_MM
    common.REQUIRED_JOINT_MARGIN_DEG = REQUIRED_JOINT_MARGIN_DEG
    common.configure_model()

    base = common.base
    base.STAGE1_STEPS_PER_DEG = np.float32(STAGE1_NOMINAL_SCALE)
    base.STAGE2_STEPS_PER_DEG = np.float32(STAGE2_NOMINAL_SCALE)
    base.THETA_LIMIT_DEG = np.float32(-0.773082)
    base.PSI_LIMIT_DEG = np.float32(134.177381)
    base.THETA_MIN_DEG = np.float32(
        base.THETA_LIMIT_DEG + np.float32(1.0)
    )
    base.PSI_MIN_DEG = np.float32(base.PSI_LIMIT_DEG + np.float32(1.0))


def check_source_contract() -> None:
    motion = MOTION_HEADER.read_text(encoding="ascii")
    ik = IK_SOURCE.read_text(encoding="utf-8-sig")
    stepper = STEPPER_HEADER.read_text(encoding="ascii")
    test_h = TEST_HEADER.read_text(encoding="ascii")
    test_c = TEST_SOURCE.read_text(encoding="ascii")
    cal_h = CAL_HEADER.read_text(encoding="ascii")
    cal_c = CAL_SOURCE.read_text(encoding="ascii")
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
    ):
        require(motion, needle, "motion contract")
    for needle in (
        "float k1 = cfg->l1_mm + cfg->l2_mm * c2;",
        "float k2 = cfg->l2_mm * s2;",
    ):
        require(ik, needle, "unequal-link IK")
    require(stepper, "#define LIMIT_STAGE2_HOME_DIR   (1u)", "Stage2 limit")
    for needle in (
        "#define WRITER_TEST_MODE_STAGE2_CHORD_CAL (24u)",
        "#define WRITER_TEST_MODE             WRITER_TEST_MODE_STAGE2_CHORD_CAL",
    ):
        require(test_h, needle, "selected test mode")
    for needle in (
        '#include "stage2_chord_cal_test.h"',
        "Stage2ChordCal_Start();",
        "Stage2ChordCal_Update();",
        "return Stage2ChordCal_Process_Frame(frame, len);",
        "return_takeup=%u",
    ):
        require(test_c, needle, "test integration")
    for needle in (
        BUILD_ID.decode("ascii"),
        "#define STAGE2_CHORD_CAL_START_X_MM              (216.798f)",
        "#define STAGE2_CHORD_CAL_START_Y_MM              (171.867f)",
        "#define STAGE2_CHORD_CAL_RETURN_TAKEUP_PULSES     (23u)",
        "#define STAGE2_CHORD_CAL_TOTAL_RAW_PULSES         (3223u)",
        "#define STAGE2_CHORD_CAL_FINAL_MOTOR_OFFSET_STEPS (-23)",
        "#define STAGE2_CHORD_CAL_EXPECTED_STAGE1_STEPS    (2668)",
        "#define STAGE2_CHORD_CAL_EXPECTED_STAGE2_STEPS    (5880)",
        "#define STAGE2_CHORD_CAL_REFERENCE_PSI_STEPS      (5416)",
        "#define STAGE2_CHORD_CAL_STAGE2_SCALE_MIN         (39.0f)",
        "#define STAGE2_CHORD_CAL_STAGE2_SCALE_MAX         (43.0f)",
    ):
        require(cal_h, needle, "V28 header")
    for needle in (
        "s_mark_motor_offsets[STAGE2_CHORD_CAL_POSITION_COUNT]",
        "STAGE2_CHORD_CAL_RETURN_TAKEUP_PULSES",
        "s_leg_expected_steps",
        "s_motor_offset_steps = s_leg_target_motor_offset_steps;",
        "STAGE2_CHORD_CAL_FINAL_MOTOR_OFFSET_STEPS",
        "App_Stepper_Stage1_Total_Pulses() != s_stage1_start_total",
        'Stage2ChordCal_Fail("unexpected_uart_while_running")',
        "error:reset_required",
        "single_pass=1 rehome=1",
    ):
        require(cal_c, needle, "V28 executor")
    raw_call = re.compile(
        r"App_Stepper_Dual_Run\(App_Stepper_X\.current_dir,\s*0u,\s*"
        r"direction,\s*leg_steps,\s*STAGE2_CHORD_CAL_FREQ_HZ\)",
        re.MULTILINE,
    )
    if len(raw_call.findall(cal_c)) != 1:
        raise AssertionError("raw V28 motion must lock Stage1 to zero pulses")
    require(main, "if (WriterHome_InitialHome_Task())", "automatic homing")

    tree = ET.parse(PROJECT_PATH)
    names = [node.text for node in tree.findall(".//FileName")]
    for name in ("stage2_chord_cal_test.c", "stage2_chord_cal_test.h"):
        if names.count(name) != 1:
            raise AssertionError(f"correct Keil project must contain {name} once")
    print(
        "source_contract=PASS mode=V28 stage1=LOCKED takeup=23 "
        "dircomp=0 gate=G21_G90_G94_M5_M501 single_pass=1"
    )


def check_gcode() -> str:
    lines = tuple(GCODE_PATH.read_text(encoding="ascii").splitlines())
    if lines != EXPECTED_GCODE:
        raise AssertionError(f"gate G-code mismatch: {lines}")
    if any(re.search(r"[XYZFS]|M3|G0|G1", line) for line in lines):
        raise AssertionError("gate G-code contains motion or pen-down words")
    digest = hashlib.sha256(GCODE_PATH.read_bytes()).hexdigest().upper()
    print(f"gcode_gate=PASS lines=5 motion_words=0 pen_down=0 sha256={digest}")
    return digest


def check_approach() -> tuple[int, int]:
    expected1, expected2, margin, endpoint_error = v21.quantized_target(
        "V28_START", *START_USER
    )
    if (expected1, expected2) != EXPECTED_START_STEPS:
        raise AssertionError(f"start target changed: {(expected1, expected2)}")
    segment_counts: list[int] = []
    min_margin = float("inf")
    max_deviation = 0.0
    for delta1 in range(41, 49):
        for delta2 in range(41, 49):
            home_user, current = v21.user_from_home_delta(delta1, delta2)
            planned = v21.plan_line(home_user, START_USER, "HOME_TO_V28")
            segment_counts.append(len(planned))
            for index, target in enumerate(planned, start=1):
                _, joint_margin, deviation = v21.check_segment_dda(
                    current,
                    target,
                    home_user,
                    START_USER,
                    f"HOME_{delta1}_{delta2}/SEGMENT_{index}",
                )
                min_margin = min(min_margin, joint_margin)
                max_deviation = max(max_deviation, deviation)
                current = target
            if current != EXPECTED_START_STEPS:
                raise AssertionError("home approach did not reach V28 start")
    if max_deviation > MAX_APPROACH_DEVIATION_MM:
        raise AssertionError(f"approach deviation {max_deviation:.6f} mm")
    print(
        "home_approach=PASS release_delta_s1=41..48 release_delta_s2=41..48 "
        f"segments={min(segment_counts)}..{max(segment_counts)} "
        f"min_joint_margin_deg={min_margin:.6f} "
        f"max_line_deviation_mm={max_deviation:.6f} "
        f"start_margin_deg={margin:.6f} endpoint_error_mm={endpoint_error:.6f}"
    )
    return expected1, expected2


def envelope_at_scales(
    start1: int, start2: int, stage1_scale: float, stage2_scale: float
) -> tuple[float, float]:
    theta, psi_min = common.physical_angles(
        start1, start2 + min(MOTOR_OFFSETS), stage1_scale, stage2_scale
    )
    _, psi_max = common.physical_angles(
        start1, start2 + max(MOTOR_OFFSETS), stage1_scale, stage2_scale
    )
    critical = [psi_min, psi_max]
    for angle in (90.0, 180.0, 270.0):
        if psi_min <= angle <= psi_max:
            critical.append(angle)
    points = [common.user_from_physical_angles(theta, psi) for psi in critical]
    paper_margin = min(
        min(point[0] for point in points),
        297.0 - max(point[0] for point in points),
        min(point[1] for point in points),
        210.0 - max(point[1] for point in points),
    )
    joint_margin = min(
        common.candidate_pose_margin(theta, psi_min, stage1_scale, stage2_scale),
        common.candidate_pose_margin(theta, psi_max, stage1_scale, stage2_scale),
    )
    return paper_margin, joint_margin


def check_raw_sequence(start1: int, start2: int) -> None:
    raw_total = 0
    for index in range(1, len(LOGICAL_POSITIONS)):
        logical_delta = LOGICAL_POSITIONS[index] - LOGICAL_POSITIONS[index - 1]
        motor_delta = MOTOR_OFFSETS[index] - MOTOR_OFFSETS[index - 1]
        expected_motor = LEG_PULSES + (TAKEUP_PULSES if index == 5 else 0)
        if abs(logical_delta) != LEG_PULSES or abs(motor_delta) != expected_motor:
            raise AssertionError(f"invalid V28 leg {index}")
        if (index <= 4 and motor_delta <= 0) or (index > 4 and motor_delta >= 0):
            raise AssertionError(f"wrong direction on V28 leg {index}")
        raw_total += abs(motor_delta)
    if raw_total != TOTAL_RAW_PULSES or MOTOR_OFFSETS[-1] != -TAKEUP_PULSES:
        raise AssertionError("V28 terminal pulse invariant failed")

    min_paper = float("inf")
    min_joint = float("inf")
    for s1 in np.linspace(STAGE1_SCALE_MIN, STAGE1_SCALE_MAX, 185):
        for s2 in np.linspace(STAGE2_SCALE_MIN, STAGE2_SCALE_MAX, 501):
            paper, joint = envelope_at_scales(start1, start2, float(s1), float(s2))
            min_paper = min(min_paper, paper)
            min_joint = min(min_joint, joint)
    if min_paper < REQUIRED_PAPER_MARGIN_MM - 1.0e-6:
        raise AssertionError(f"candidate paper margin {min_paper:.6f} mm")
    if min_joint < REQUIRED_JOINT_MARGIN_DEG - 1.0e-6:
        raise AssertionError(f"candidate joint margin {min_joint:.6f} deg")

    takeup_angle = TAKEUP_PULSES / STAGE2_NOMINAL_SCALE
    rigid_shift = 2.0 * 203.0 * math.sin(math.radians(takeup_angle) / 2.0)
    measured_angle = math.degrees(2.0 * math.asin(2.0 / (2.0 * 203.0)))
    measured_pulses = measured_angle * STAGE2_NOMINAL_SCALE
    predicted_residual = abs(rigid_shift - 2.0)
    print(
        "integer_sequence=PASS logical=0,400,800,1200,1600,1200,800,400,0 "
        "motor=0,400,800,1200,1600,1177,777,377,-23 "
        f"raw_total={raw_total} final_motor_steps={start2 - TAKEUP_PULSES} "
        "stage1_delta=0"
    )
    print(
        f"takeup_model=PASS measured_offset_mm=2.000000 "
        f"measured_equivalent_pulses={measured_pulses:.6f} "
        f"test_pulses={TAKEUP_PULSES} test_angle_deg={takeup_angle:.6f} "
        f"rigid_shift_mm={rigid_shift:.6f} predicted_residual_mm={predicted_residual:.6f} "
        f"candidate_paper_margin_mm={min_paper:.6f} "
        f"candidate_joint_margin_deg={min_joint:.6f}"
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
        raise AssertionError("V28 build ID missing from HEX")
    if b"AUTHOR_STAGE2_5POS_BIDIR_L203_GATED_V27" in image:
        raise AssertionError("stale V27 build ID present in V28 HEX")
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
    check_source_contract()
    check_gcode()
    start1, start2 = check_approach()
    check_raw_sequence(start1, start2)
    if not args.source_only:
        check_build_and_hex()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise
