"""Verify the gated V26 Stage2 confirmation firmware."""

from __future__ import annotations

import argparse
import hashlib
import re
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
CHORD_HEADER = ROOT / "TASK" / "stage2_chord_cal_test.h"
CHORD_SOURCE = ROOT / "TASK" / "stage2_chord_cal_test.c"
MAIN_SOURCE = ROOT / "main.c"
PROJECT_PATH = (
    ROOT / "keil" / "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx"
)
GCODE_PATH = ROOT / "gcode" / "AUTHOR_STAGE2_1600P_CONFIRM_RUN_V26.gcode"
COMMAND_SCRIPT = ROOT / "tools" / "stage2_confirm_v26_control.ps1"
BUILD_LOG = ROOT / "keil" / "AUTHOR_STAGE2_1600P_CONFIRM_L203_GATED_V26_build.log"
KEIL_HTML_LOG = (
    ROOT
    / "keil"
    / "Objects"
    / "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.build_log.htm"
)
HEX_PATH = ROOT / "keil" / "AUTHOR_STAGE2_1600P_CONFIRM_L203_GATED_V26.hex"

BUILD_ID = b"AUTHOR_STAGE2_1600P_CONFIRM_L203_GATED_V26"
START_USER = (215.108, 174.387)
EXPECTED_START_STEPS = (2668, 5983)
RAW_PULSES = 1600
STAGE1_NOMINAL_SCALE = 40.099216
STAGE1_SCALE_MIN = 40.007831
STAGE1_SCALE_MAX = 40.190898
STAGE2_NOMINAL_SCALE = 41.058408
STAGE2_SCALE_MIN = 39.0
STAGE2_SCALE_MAX = 43.0
STAGE2_REFERENCE_STEPS = 5543
REQUIRED_PAPER_MARGIN_MM = 30.0
REQUIRED_JOINT_MARGIN_DEG = 10.0
MAX_APPROACH_DEVIATION_MM = 0.12


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"{label}: missing {needle!r}")


def configure_common() -> None:
    common.GCODE_PATH = GCODE_PATH
    common.BUILD_LOG = BUILD_LOG
    common.KEIL_HTML_LOG = KEIL_HTML_LOG
    common.HEX_PATH = HEX_PATH
    common.BUILD_ID = BUILD_ID
    common.START_USER = START_USER
    common.EXPECTED_START_STEPS = EXPECTED_START_STEPS
    common.RAW_PULSES = RAW_PULSES
    common.STAGE1_NOMINAL_SCALE = STAGE1_NOMINAL_SCALE
    common.STAGE1_SCALE_MIN = STAGE1_SCALE_MIN
    common.STAGE1_SCALE_MAX = STAGE1_SCALE_MAX
    common.STAGE2_NOMINAL_SCALE = STAGE2_NOMINAL_SCALE
    common.STAGE2_SCALE_MIN = STAGE2_SCALE_MIN
    common.STAGE2_SCALE_MAX = STAGE2_SCALE_MAX
    common.STAGE2_REFERENCE_STEPS = STAGE2_REFERENCE_STEPS
    common.REQUIRED_PAPER_MARGIN_MM = REQUIRED_PAPER_MARGIN_MM
    common.REQUIRED_JOINT_MARGIN_DEG = REQUIRED_JOINT_MARGIN_DEG
    common.configure_model()


def check_source_contract() -> None:
    motion = MOTION_HEADER.read_text(encoding="ascii")
    ik_source = IK_SOURCE.read_text(encoding="utf-8-sig")
    stepper_h = STEPPER_HEADER.read_text(encoding="ascii")
    test_h = TEST_HEADER.read_text(encoding="ascii")
    test_c = TEST_SOURCE.read_text(encoding="ascii")
    chord_h = CHORD_HEADER.read_text(encoding="ascii")
    chord_c = CHORD_SOURCE.read_text(encoding="ascii")
    main_c = MAIN_SOURCE.read_text(encoding="ascii")
    command = COMMAND_SCRIPT.read_text(encoding="ascii")

    for needle in (
        "#define APP_WRITER_L1_MM                    (205.0f)",
        "#define APP_WRITER_L2_MM                    (203.0f)",
        "#define APP_WRITER_MACHINE_OFFSET_X_MM      (-129.0f)",
        "#define APP_WRITER_MACHINE_OFFSET_Y_MM      (128.0f)",
        "#define APP_WRITER_THETA_LIMIT_DEG          (-0.773082f)",
        "#define APP_WRITER_PSI_LIMIT_DEG            (134.196267f)",
        "#define APP_WRITER_STAGE1_STEPS_PER_DEG     (40.099216f)",
        "#define APP_WRITER_STAGE2_STEPS_PER_DEG     (41.058408f)",
        "#define APP_WRITER_DIRECTION_COMP_ENABLE     (0u)",
        "#define APP_WRITER_AUTHOR_LINE_EXECUTION_ENABLE (0u)",
        "#define APP_WRITER_A4_ENVELOPE_PROBE_ENABLE  (1u)",
        "#define APP_WRITER_PLAN_SEGMENT_MM          (1.0f)",
    ):
        require(motion, needle, "motion contract")
    for needle in (
        "float k1 = cfg->l1_mm + cfg->l2_mm * c2;",
        "float k2 = cfg->l2_mm * s2;",
    ):
        require(ik_source, needle, "unequal-link IK")
    require(stepper_h, "#define LIMIT_STAGE2_HOME_DIR   (1u)", "Stage2 limit")

    for needle in (
        "#define WRITER_TEST_MODE_STAGE2_CHORD_CAL (24u)",
        "#define WRITER_TEST_MODE             WRITER_TEST_MODE_STAGE2_CHORD_CAL",
    ):
        require(test_h, needle, "selected mode")
    for needle in (
        '#include "stage2_chord_cal_test.h"',
        "(WRITER_TEST_MODE != WRITER_TEST_MODE_STAGE2_CHORD_CAL)",
        "Stage2ChordCal_Start();",
        "Stage2ChordCal_Update();",
        "return Stage2ChordCal_Process_Frame(frame, len);",
        "stage1=LOCKED stage2_pulses=%u marks=3 single_pass=1",
    ):
        require(test_c, needle, "task integration")

    for needle in (
        BUILD_ID.decode("ascii"),
        "#define STAGE2_CHORD_CAL_START_X_MM              (215.108f)",
        "#define STAGE2_CHORD_CAL_START_Y_MM              (174.387f)",
        "#define STAGE2_CHORD_CAL_PULSES                  (1600u)",
        "#define STAGE2_CHORD_CAL_EXPECTED_STAGE1_STEPS    (2668)",
        "#define STAGE2_CHORD_CAL_EXPECTED_STAGE2_STEPS    (5983)",
        "#define STAGE2_CHORD_CAL_STAGE1_SCALE_MIN         (40.007831f)",
        "#define STAGE2_CHORD_CAL_STAGE1_SCALE_MAX         (40.190898f)",
        "#define STAGE2_CHORD_CAL_STAGE2_SCALE_MIN         (39.0f)",
        "#define STAGE2_CHORD_CAL_STAGE2_SCALE_MAX         (43.0f)",
        "#define STAGE2_CHORD_CAL_REFERENCE_PSI_STEPS      (5543)",
        "#define STAGE2_CHORD_CAL_CANDIDATE_MARGIN_DEG     (10.0f)",
        "#define STAGE2_CHORD_CAL_PAPER_MARGIN_MM          (30.0f)",
    ):
        require(chord_h, needle, "chord header")

    for needle in (
        "no_auto_motion=1",
        "gate=M501_or_RUN",
        "WriterMotion_Start_To(STAGE2_CHORD_CAL_START_X_MM",
        "Stage2ChordCal_Validate_Raw_Path_For_Scales",
        "STAGE2_CHORD_CAL_REFERENCE_PSI_STEPS",
        "STAGE2_CHORD_CAL_CANDIDATE_MARGIN_DEG",
        "STAGE2_CHORD_CAL_PAPER_MARGIN_MM",
        "App_Stepper_Stage1_Total_Pulses() != s_stage1_start_total",
        "App_Stepper_Y.step_count != STAGE2_CHORD_CAL_PULSES",
        "App_Servo_Pen_Down();",
        "WriterMotion_Emergency_Stop();",
        'Stage2ChordCal_Fail("unexpected_uart_while_running")',
        "error:reset_required",
        "single_pass=1 rehome=1",
    ):
        require(chord_c, needle, "chord executor")

    raw_call_pattern = re.compile(
        r"App_Stepper_Dual_Run\(App_Stepper_X\.current_dir,\s*0u,\s*"
        r"STAGE2_CHORD_CAL_(?:AWAY|RETURN)_DIR,\s*"
        r"STAGE2_CHORD_CAL_PULSES,\s*STAGE2_CHORD_CAL_FREQ_HZ\)",
        re.MULTILINE,
    )
    if len(raw_call_pattern.findall(chord_c)) != 2:
        raise AssertionError("both raw Stage2 legs must lock Stage1 to zero")

    require(main_c, "if (WriterHome_InitialHome_Task())", "automatic homing")
    for needle in (
        '[ValidateSet("STATUS", "START", "STOP")]',
        "-ConfirmPaperFixed",
        BUILD_ID.decode("ascii"),
        '$preflight -notmatch "state=WAIT_RUN"',
        'foreach ($command in @("G21", "G90", "G94", "M5"))',
        'Send-WriterCommand -Command "M501"',
    ):
        require(command, needle, "host control")

    tree = ET.parse(PROJECT_PATH)
    file_names = [node.text for node in tree.findall(".//FileName")]
    for filename in ("stage2_chord_cal_test.c", "stage2_chord_cal_test.h"):
        if file_names.count(filename) != 1:
            raise AssertionError(
                f"correct Keil project must contain {filename} exactly once"
            )

    print(
        "source_contract=PASS mode=V26 provisional_stage2=41.058408 "
        "psi_limit=134.196267 stage1=LOCKED stage2_pulses=1600 "
        "gate=G21_G90_G94_M5_M501 single_pass=1"
    )


def check_approach_paths() -> tuple[int, int]:
    expected1, expected2, target_margin, endpoint_error = v21.quantized_target(
        "CONFIRM_START", START_USER[0], START_USER[1]
    )
    if (expected1, expected2) != EXPECTED_START_STEPS:
        raise AssertionError(f"start target changed: {(expected1, expected2)}")

    segment_counts: list[int] = []
    minimum_margin = float("inf")
    maximum_deviation = 0.0
    minimum_master_pulses = 2**31 - 1
    maximum_master_pulses = 0

    # One to eight final release pulses plus rounded 1-degree clearances:
    # Stage1 40 pulses and provisional Stage2 41 pulses.
    for delta1 in range(41, 49):
        for delta2 in range(42, 50):
            home_user, current_steps = v21.user_from_home_delta(delta1, delta2)
            planned = v21.plan_line(home_user, START_USER, "HOME_TO_CONFIRM")
            segment_counts.append(len(planned))
            master_pulses = 0
            for index, target_steps in enumerate(planned, start=1):
                pulses, margin, deviation = v21.check_segment_dda(
                    current_steps,
                    target_steps,
                    home_user,
                    START_USER,
                    f"HOME_{delta1}_{delta2}/SEGMENT_{index}",
                )
                master_pulses += pulses
                minimum_margin = min(minimum_margin, margin)
                maximum_deviation = max(maximum_deviation, deviation)
                current_steps = target_steps
            if current_steps != EXPECTED_START_STEPS:
                raise AssertionError("home approach did not reach integer start")
            minimum_master_pulses = min(minimum_master_pulses, master_pulses)
            maximum_master_pulses = max(maximum_master_pulses, master_pulses)

    if maximum_deviation > MAX_APPROACH_DEVIATION_MM:
        raise AssertionError(
            f"home approach line deviation {maximum_deviation:.6f} mm"
        )
    print(
        "home_approach=PASS release_delta_s1=41..48 release_delta_s2=42..49 "
        f"segments={min(segment_counts)}..{max(segment_counts)} "
        f"master_pulses={minimum_master_pulses}..{maximum_master_pulses} "
        f"min_joint_margin_deg={minimum_margin:.6f} "
        f"max_line_deviation_mm={maximum_deviation:.6f} "
        f"start_target_margin_deg={target_margin:.6f} "
        f"start_endpoint_error_mm={endpoint_error:.6f}"
    )
    return expected1, expected2


def check_build_log() -> None:
    text = BUILD_LOG.read_text(encoding="utf-8", errors="replace")
    html = KEIL_HTML_LOG.read_text(encoding="utf-8", errors="replace")
    require(
        html,
        "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx",
        "correct Keil project",
    )
    require(text, "0 Error(s), 0 Warning(s).", "clean build")
    if "Target not created" in text:
        raise AssertionError("build log reports target not created")
    print("keil_build=PASS project=CORRECT errors=0 warnings=0")


def check_hex() -> str:
    image, records, data_bytes = common.base.parse_ihex(HEX_PATH)
    if BUILD_ID not in image:
        raise AssertionError("V26 build ID missing from firmware")
    for stale_id in (
        b"AUTHOR_STAGE2_2200P_LONG_CHORD_L203_GATED_V25",
        b"AUTHOR_STAGE1_3200P_LONG_CHORD_L205_GATED_V24",
        b"AUTHOR_STAGE1_976P_CHORD_L205_GATED_V23",
    ):
        if stale_id in image:
            raise AssertionError(f"stale build ID in V26 firmware: {stale_id!r}")
    digest = hashlib.sha256(HEX_PATH.read_bytes()).hexdigest().upper()
    print(
        f"intel_hex=PASS records={records} data_bytes={data_bytes} "
        f"build_id=PASS sha256={digest}"
    )
    return digest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()

    configure_common()
    check_source_contract()
    common.check_gcode()
    start1, start2 = check_approach_paths()
    common.check_raw_arc(start1, start2)
    if not args.source_only:
        check_build_log()
        check_hex()


if __name__ == "__main__":
    main()
