"""Verify the gated V27 Stage2 five-position bidirectional diagnostic."""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import check_stage2_confirm_v26 as v26
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
GCODE_PATH = ROOT / "gcode" / "AUTHOR_STAGE2_5POS_BIDIR_RUN_V27.gcode"
COMMAND_SCRIPT = ROOT / "tools" / "stage2_5pos_bidir_v27_control.ps1"
BUILD_LOG = ROOT / "keil" / "AUTHOR_STAGE2_5POS_BIDIR_L203_GATED_V27_build.log"
KEIL_HTML_LOG = (
    ROOT
    / "keil"
    / "Objects"
    / "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.build_log.htm"
)
HEX_PATH = ROOT / "keil" / "AUTHOR_STAGE2_5POS_BIDIR_L203_GATED_V27.hex"

BUILD_ID = b"AUTHOR_STAGE2_5POS_BIDIR_L203_GATED_V27"
START_USER = (215.108, 174.387)
EXPECTED_START_STEPS = (2668, 5983)
POSITIONS = (0, 400, 800, 1200, 1600, 1200, 800, 400, 0)
LEG_PULSES = 400
MAX_POSITION = 1600
TOTAL_RAW_PULSES = 3200
STAGE1_NOMINAL_SCALE = 40.099216
STAGE1_SCALE_MIN = 40.007831
STAGE1_SCALE_MAX = 40.190898
STAGE2_NOMINAL_SCALE = 41.058408
STAGE2_SCALE_MIN = 39.0
STAGE2_SCALE_MAX = 43.0
STAGE2_REFERENCE_STEPS = 5543
REQUIRED_PAPER_MARGIN_MM = 30.0
REQUIRED_JOINT_MARGIN_DEG = 10.0
EXPECTED_GCODE = ("G21", "G90", "G94", "M5", "M501")


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"{label}: missing {needle!r}")


def configure_model() -> None:
    common.GCODE_PATH = GCODE_PATH
    common.BUILD_LOG = BUILD_LOG
    common.KEIL_HTML_LOG = KEIL_HTML_LOG
    common.HEX_PATH = HEX_PATH
    common.BUILD_ID = BUILD_ID
    common.START_USER = START_USER
    common.EXPECTED_START_STEPS = EXPECTED_START_STEPS
    common.RAW_PULSES = MAX_POSITION
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

    v26.START_USER = START_USER
    v26.EXPECTED_START_STEPS = EXPECTED_START_STEPS


def check_source_contract() -> None:
    motion = MOTION_HEADER.read_text(encoding="ascii")
    ik_source = IK_SOURCE.read_text(encoding="utf-8-sig")
    stepper_h = STEPPER_HEADER.read_text(encoding="ascii")
    test_h = TEST_HEADER.read_text(encoding="ascii")
    test_c = TEST_SOURCE.read_text(encoding="ascii")
    cal_h = CAL_HEADER.read_text(encoding="ascii")
    cal_c = CAL_SOURCE.read_text(encoding="ascii")
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
        "stage1=LOCKED positions=%u leg_pulses=%u max_position=%u marks=%u",
    ):
        require(test_c, needle, "task integration")

    for needle in (
        BUILD_ID.decode("ascii"),
        "#define STAGE2_CHORD_CAL_START_X_MM              (215.108f)",
        "#define STAGE2_CHORD_CAL_START_Y_MM              (174.387f)",
        "#define STAGE2_CHORD_CAL_LEG_PULSES              (400u)",
        "#define STAGE2_CHORD_CAL_MAX_POSITION_STEPS       (1600u)",
        "#define STAGE2_CHORD_CAL_TOTAL_RAW_PULSES         (3200u)",
        "#define STAGE2_CHORD_CAL_POSITION_COUNT           (9u)",
        "#define STAGE2_CHORD_CAL_UNIQUE_POSITION_COUNT    (5u)",
        "#define STAGE2_CHORD_CAL_MARK_COUNT               (9u)",
        "#define STAGE2_CHORD_CAL_EXPECTED_STAGE1_STEPS    (2668)",
        "#define STAGE2_CHORD_CAL_EXPECTED_STAGE2_STEPS    (5983)",
        "#define STAGE2_CHORD_CAL_STAGE2_SCALE_MIN         (39.0f)",
        "#define STAGE2_CHORD_CAL_STAGE2_SCALE_MAX         (43.0f)",
        "#define STAGE2_CHORD_CAL_REFERENCE_PSI_STEPS      (5543)",
        "#define STAGE2_CHORD_CAL_CANDIDATE_MARGIN_DEG     (10.0f)",
        "#define STAGE2_CHORD_CAL_PAPER_MARGIN_MM          (30.0f)",
        "STAGE2_CHORD_CAL_STATE_START_LEG",
        "STAGE2_CHORD_CAL_STATE_WAIT_LEG",
    ):
        require(cal_h, needle, "calibration header")

    for needle in (
        "positions=0_400_800_1200_1600_1200_800_400_0",
        "Stage2ChordCal_Sequence_Valid",
        "Stage2ChordCal_Validate_Raw_Path_For_Scales",
        "s_mark_positions[STAGE2_CHORD_CAL_POSITION_COUNT]",
        "s_stage2_raw_start_total",
        "STAGE2_CHORD_CAL_TOTAL_RAW_PULSES",
        "App_Stepper_Stage1_Total_Pulses() != s_stage1_start_total",
        "App_Stepper_Y.step_count !=",
        "STAGE2_CHORD_CAL_LEG_PULSES",
        "s_position_steps = s_leg_target_position_steps",
        "Stage2ChordCal_Start_Mark(s_mark_index + 1u)",
        "App_Servo_Pen_Down();",
        "WriterMotion_Emergency_Stop();",
        'Stage2ChordCal_Fail("unexpected_uart_while_running")',
        "error:reset_required",
        "single_pass=1 rehome=1",
    ):
        require(cal_c, needle, "calibration executor")

    raw_call_pattern = re.compile(
        r"App_Stepper_Dual_Run\(App_Stepper_X\.current_dir,\s*0u,\s*"
        r"direction,\s*leg_steps,\s*STAGE2_CHORD_CAL_FREQ_HZ\)",
        re.MULTILINE,
    )
    if len(raw_call_pattern.findall(cal_c)) != 1:
        raise AssertionError("generic raw Stage2 leg must lock Stage1 to zero")

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
        "source_contract=PASS mode=V27 positions=5 marks=9 legs=8 "
        "leg_pulses=400 max_position=1600 raw_total=3200 "
        "stage1=LOCKED gate=G21_G90_G94_M5_M501 single_pass=1"
    )


def check_gcode() -> str:
    lines = tuple(GCODE_PATH.read_text(encoding="ascii").splitlines())
    if lines != EXPECTED_GCODE:
        raise AssertionError(
            f"gate G-code mismatch expected={EXPECTED_GCODE} actual={lines}"
        )
    if any(re.search(r"[XYZFS]|M3|G0|G1", line) for line in lines):
        raise AssertionError("gate file contains a motion or pen-down word")
    digest = hashlib.sha256(GCODE_PATH.read_bytes()).hexdigest().upper()
    print(
        "gcode_gate=PASS lines=5 motion_words=0 pen_down=0 final=M501 "
        f"sha256={digest}"
    )
    return digest


def parse_source_positions() -> tuple[int, ...]:
    text = CAL_SOURCE.read_text(encoding="ascii")
    match = re.search(
        r"static const uint32_t s_mark_positions\["
        r"STAGE2_CHORD_CAL_POSITION_COUNT\]\s*=\s*\{(.*?)\};",
        text,
        re.DOTALL,
    )
    if match is None:
        raise AssertionError("position table not found")
    return tuple(int(value) for value in re.findall(r"(\d+)u", match.group(1)))


def check_integer_sequence(start1: int, start2: int) -> None:
    source_positions = parse_source_positions()
    if source_positions != POSITIONS:
        raise AssertionError(
            f"position table mismatch expected={POSITIONS} actual={source_positions}"
        )

    raw_total = 0
    current = POSITIONS[0]
    for index, target in enumerate(POSITIONS[1:], start=1):
        delta = target - current
        if abs(delta) != LEG_PULSES:
            raise AssertionError(f"leg {index} is not {LEG_PULSES} pulses")
        if index <= 4 and delta <= 0:
            raise AssertionError("outbound direction changed")
        if index > 4 and delta >= 0:
            raise AssertionError("return direction changed")
        raw_total += abs(delta)
        current = target
    if current != 0 or raw_total != TOTAL_RAW_PULSES:
        raise AssertionError("integer sequence does not close exactly")

    nominal_chords: list[float] = []
    candidate_ranges: list[tuple[float, float]] = []
    for position in POSITIONS[1:5]:
        nominal = 2.0 * 203.0 * math.sin(
            math.radians(position / STAGE2_NOMINAL_SCALE) / 2.0
        )
        candidates = sorted(
            2.0 * 203.0 * math.sin(math.radians(position / scale) / 2.0)
            for scale in (STAGE2_SCALE_MIN, STAGE2_SCALE_MAX)
        )
        nominal_chords.append(nominal)
        candidate_ranges.append((candidates[0], candidates[1]))

    # Each reverse mark has exactly the same integer joint target as its
    # outbound partner; only mechanics can separate the resulting dot pair.
    paired_indices = ((0, 8), (1, 7), (2, 6), (3, 5))
    for first, second in paired_indices:
        if POSITIONS[first] != POSITIONS[second]:
            raise AssertionError("bidirectional position pair does not match")

    print(
        "integer_sequence=PASS "
        f"positions={','.join(str(value) for value in POSITIONS)} "
        f"start_steps=({start1},{start2}) "
        f"turn_steps=({start1},{start2 + MAX_POSITION}) "
        f"return_steps=({start1},{start2}) raw_total={raw_total} "
        "stage1_delta=0 ideal_pair_separation_mm=0"
    )
    print(
        "nominal_chords_mm="
        + ",".join(
            f"{position}:{chord:.6f}"
            for position, chord in zip(POSITIONS[1:5], nominal_chords)
        )
    )
    print(
        "candidate_chords_mm="
        + ",".join(
            f"{position}:{bounds[0]:.6f}..{bounds[1]:.6f}"
            for position, bounds in zip(POSITIONS[1:5], candidate_ranges)
        )
    )


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
        raise AssertionError("V27 build ID missing from firmware")
    for stale_id in (
        b"AUTHOR_STAGE2_1600P_CONFIRM_L203_GATED_V26",
        b"AUTHOR_STAGE2_2200P_LONG_CHORD_L203_GATED_V25",
        b"AUTHOR_STAGE1_3200P_LONG_CHORD_L205_GATED_V24",
    ):
        if stale_id in image:
            raise AssertionError(f"stale build ID in V27 firmware: {stale_id!r}")
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

    configure_model()
    check_source_contract()
    check_gcode()
    start1, start2 = v26.check_approach_paths()
    common.check_raw_arc(start1, start2)
    check_integer_sequence(start1, start2)
    if not args.source_only:
        check_build_log()
        check_hex()


if __name__ == "__main__":
    main()
