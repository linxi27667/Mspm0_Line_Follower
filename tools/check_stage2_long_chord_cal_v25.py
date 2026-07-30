"""Verify the gated V25 Stage2 long-chord calibration firmware."""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

import check_author_point_dots_v21 as v21
import check_author_point_dots_v22 as v22
import check_author_rect_loop_v17 as loop
import check_author_safe_probe_v16 as base


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
GCODE_PATH = ROOT / "gcode" / "AUTHOR_STAGE2_2200P_LONG_CHORD_RUN_V25.gcode"
COMMAND_SCRIPT = ROOT / "tools" / "stage2_long_chord_v25_control.ps1"
BUILD_LOG = (
    ROOT / "keil" / "AUTHOR_STAGE2_2200P_LONG_CHORD_L203_GATED_V25_build.log"
)
KEIL_HTML_LOG = (
    ROOT
    / "keil"
    / "Objects"
    / "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.build_log.htm"
)
HEX_PATH = (
    ROOT / "keil" / "AUTHOR_STAGE2_2200P_LONG_CHORD_L203_GATED_V25.hex"
)

BUILD_ID = b"AUTHOR_STAGE2_2200P_LONG_CHORD_L203_GATED_V25"
START_USER = (196.452, 184.639)
EXPECTED_START_STEPS = (2567, 6870)
RAW_PULSES = 2200
STAGE1_NOMINAL_SCALE = 40.099216
STAGE1_SCALE_MIN = 40.007831
STAGE1_SCALE_MAX = 40.190898
STAGE2_NOMINAL_SCALE = 48.8
STAGE2_SCALE_MIN = 46.0
STAGE2_SCALE_MAX = 51.0
STAGE2_REFERENCE_PSI_DEG = 135.0
STAGE2_REFERENCE_STEPS = 6588
PAPER_BOUNDS = (0.0, 297.0, 0.0, 210.0)
REQUIRED_PAPER_MARGIN_MM = 20.0
REQUIRED_JOINT_MARGIN_DEG = 5.0
EXPECTED_GCODE = ("G21", "G90", "G94", "M5", "M501")
MAX_APPROACH_DEVIATION_MM = 0.10


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"{label}: missing {needle!r}")


def configure_model() -> None:
    v22.configure_model()
    base.STAGE1_STEPS_PER_DEG = np.float32(STAGE1_NOMINAL_SCALE)
    base.STAGE2_STEPS_PER_DEG = np.float32(STAGE2_NOMINAL_SCALE)
    base.THETA_LIMIT_DEG = np.float32(-0.773082)
    base.PSI_LIMIT_DEG = np.float32(134.323770)
    base.THETA_MIN_DEG = np.float32(
        base.THETA_LIMIT_DEG + np.float32(1.0)
    )
    base.PSI_MIN_DEG = np.float32(base.PSI_LIMIT_DEG + np.float32(1.0))


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
        "#define APP_WRITER_PSI_LIMIT_DEG            (134.323770f)",
        "#define APP_WRITER_STAGE1_STEPS_PER_DEG     (40.099216f)",
        "#define APP_WRITER_STAGE2_STEPS_PER_DEG     (48.8f)",
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
        "#define STAGE2_CHORD_CAL_START_X_MM              (196.452f)",
        "#define STAGE2_CHORD_CAL_START_Y_MM              (184.639f)",
        "#define STAGE2_CHORD_CAL_PULSES                  (2200u)",
        "#define STAGE2_CHORD_CAL_FREQ_HZ                 (100u)",
        "#define STAGE2_CHORD_CAL_EXPECTED_STAGE1_STEPS    (2567)",
        "#define STAGE2_CHORD_CAL_EXPECTED_STAGE2_STEPS    (6870)",
        "#define STAGE2_CHORD_CAL_STAGE1_SCALE_MIN         (40.007831f)",
        "#define STAGE2_CHORD_CAL_STAGE1_SCALE_MAX         (40.190898f)",
        "#define STAGE2_CHORD_CAL_STAGE2_SCALE_MIN         (46.0f)",
        "#define STAGE2_CHORD_CAL_STAGE2_SCALE_MAX         (51.0f)",
        "#define STAGE2_CHORD_CAL_REFERENCE_PSI_STEPS      (6588)",
        "#define STAGE2_CHORD_CAL_CANDIDATE_MARGIN_DEG     (5.0f)",
        "#define STAGE2_CHORD_CAL_PAPER_MARGIN_MM          (20.0f)",
    ):
        require(chord_h, needle, "chord header")

    for needle in (
        "no_auto_motion=1",
        "gate=M501_or_RUN",
        "WriterMotion_Start_To(STAGE2_CHORD_CAL_START_X_MM",
        "approach_cmd->stage1_target_steps",
        "approach_cmd->stage2_motor_target_steps",
        "approach_cmd->stage2_comp_bias_steps != 0",
        "Stage2ChordCal_Validate_Raw_Path_For_Scales",
        "STAGE2_CHORD_CAL_REFERENCE_PSI_STEPS",
        "STAGE2_CHORD_CAL_STAGE1_SCALE_MIN",
        "STAGE2_CHORD_CAL_STAGE1_SCALE_MAX",
        "STAGE2_CHORD_CAL_STAGE2_SCALE_MIN",
        "STAGE2_CHORD_CAL_STAGE2_SCALE_MAX",
        "pulse <= STAGE2_CHORD_CAL_PULSES",
        "STAGE2_CHORD_CAL_CANDIDATE_MARGIN_DEG",
        "STAGE2_CHORD_CAL_PAPER_MARGIN_MM",
        "App_Stepper_Stage1_Total_Pulses() != s_stage1_start_total",
        "App_Stepper_Y.step_count != STAGE2_CHORD_CAL_PULSES",
        "s_position_steps != 0u",
        "s_mark_count != 3u",
        "App_Servo_Pen_Down();",
        "App_Servo_Pen_Up();",
        "WriterMotion_Emergency_Stop();",
        'Stage2ChordCal_Fail("unexpected_uart_while_running")',
        "error:reset_required",
        "single_pass=1 rehome=1",
        '(strcmp(command, "M501") == 0)',
        '(strcmp(command, "RUN") == 0)',
        "s_setup_mask != STAGE2_CHORD_CAL_SETUP_ALL",
    ):
        require(chord_c, needle, "chord executor")

    raw_call_pattern = re.compile(
        r"App_Stepper_Dual_Run\(App_Stepper_X\.current_dir,\s*0u,\s*"
        r"STAGE2_CHORD_CAL_(?:AWAY|RETURN)_DIR,\s*"
        r"STAGE2_CHORD_CAL_PULSES,\s*STAGE2_CHORD_CAL_FREQ_HZ\)",
        re.MULTILINE,
    )
    if len(raw_call_pattern.findall(chord_c)) != 2:
        raise AssertionError("raw Stage2 legs do not both lock Stage1 to zero pulses")

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
        "source_contract=PASS mode=V25 L1=205 L2=203 offset=-129,128 "
        "stage1=LOCKED stage2_pulses=2200 candidate_guard=1 "
        "gate=G21_G90_G94_M5_M501 single_pass=1"
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


def check_approach_paths() -> tuple[int, int]:
    expected1, expected2, target_margin, endpoint_error = v21.quantized_target(
        "CHORD_START", START_USER[0], START_USER[1]
    )
    if (expected1, expected2) != EXPECTED_START_STEPS:
        raise AssertionError(
            f"start target changed: {(expected1, expected2)}"
        )

    segment_counts: list[int] = []
    minimum_margin = float("inf")
    maximum_deviation = 0.0
    minimum_master_pulses = 2**31 - 1
    maximum_master_pulses = 0

    # One to eight final release pulses plus the rounded 1-degree clearance:
    # Stage1 40 pulses and Stage2 49 pulses.
    for delta1 in range(41, 49):
        for delta2 in range(50, 58):
            home_user, current_steps = v21.user_from_home_delta(delta1, delta2)
            planned = v21.plan_line(home_user, START_USER, "HOME_TO_CHORD")
            segment_counts.append(len(planned))
            master_pulses = 0
            for segment_index, target_steps in enumerate(planned, start=1):
                pulses, margin, deviation = v21.check_segment_dda(
                    current_steps,
                    target_steps,
                    home_user,
                    START_USER,
                    f"HOME_{delta1}_{delta2}/SEGMENT_{segment_index}",
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
        "home_approach=PASS release_delta_s1=41..48 release_delta_s2=50..57 "
        f"segments={min(segment_counts)}..{max(segment_counts)} "
        f"master_pulses={minimum_master_pulses}..{maximum_master_pulses} "
        f"min_joint_margin_deg={minimum_margin:.6f} "
        f"max_line_deviation_mm={maximum_deviation:.6f} "
        f"start_target_margin_deg={target_margin:.6f} "
        f"start_endpoint_error_mm={endpoint_error:.6f}"
    )
    return expected1, expected2


def physical_angles(
    stage1_steps: int,
    stage2_steps: int,
    stage1_scale: float,
    stage2_scale: float,
) -> tuple[float, float]:
    theta = stage1_steps / stage1_scale
    psi = STAGE2_REFERENCE_PSI_DEG + (
        (stage2_steps - STAGE2_REFERENCE_STEPS) / stage2_scale
    )
    return theta, psi


def user_from_physical_angles(theta: float, psi: float) -> tuple[float, float]:
    return (
        129.0
        - 205.0 * math.cos(math.radians(theta))
        - 203.0 * math.cos(math.radians(psi)),
        205.0 * math.sin(math.radians(theta))
        + 203.0 * math.sin(math.radians(psi))
        - 128.0,
    )


def candidate_pose_margin(
    theta: float, psi: float, stage1_scale: float, stage2_scale: float
) -> float:
    theta_min = 1.0 - 31.0 / stage1_scale
    psi_min = 136.0 - 33.0 / stage2_scale
    beta = psi - theta
    return min(
        theta - theta_min,
        135.0 - theta,
        psi - psi_min,
        255.0 - psi,
        beta - 1.0,
        179.0 - beta,
    )


def arc_extrema(
    start1: int, start2: int, stage1_scale: float, stage2_scale: float
) -> dict[str, object]:
    theta, psi_start = physical_angles(
        start1, start2, stage1_scale, stage2_scale
    )
    _, psi_end = physical_angles(
        start1, start2 + RAW_PULSES, stage1_scale, stage2_scale
    )
    critical_psi = [psi_start, psi_end]
    for angle in (90.0, 180.0, 270.0):
        if psi_start <= angle <= psi_end:
            critical_psi.append(angle)
    points = [user_from_physical_angles(theta, psi) for psi in critical_psi]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    xmin, xmax, ymin, ymax = PAPER_BOUNDS
    paper_margin = min(
        min(xs) - xmin,
        xmax - max(xs),
        min(ys) - ymin,
        ymax - max(ys),
    )
    joint_margin = min(
        candidate_pose_margin(theta, psi_start, stage1_scale, stage2_scale),
        candidate_pose_margin(theta, psi_end, stage1_scale, stage2_scale),
    )
    start = user_from_physical_angles(theta, psi_start)
    end = user_from_physical_angles(theta, psi_end)
    return {
        "theta": theta,
        "psi_start": psi_start,
        "psi_end": psi_end,
        "start": start,
        "end": end,
        "bbox": (min(xs), max(xs), min(ys), max(ys)),
        "paper_margin": paper_margin,
        "joint_margin": joint_margin,
        "chord": math.hypot(end[0] - start[0], end[1] - start[1]),
    }


def check_integer_arc_at_scales(
    start1: int,
    start2: int,
    stage1_scale: float,
    stage2_scale: float,
    label: str,
) -> dict[str, object]:
    minimum_joint_margin = float("inf")
    minimum_paper_margin = float("inf")
    points: list[tuple[float, float]] = []
    xmin, xmax, ymin, ymax = PAPER_BOUNDS

    for pulse in range(RAW_PULSES + 1):
        theta, psi = physical_angles(
            start1, start2 + pulse, stage1_scale, stage2_scale
        )
        margin = candidate_pose_margin(theta, psi, stage1_scale, stage2_scale)
        point = user_from_physical_angles(theta, psi)
        paper_margin = min(
            point[0] - xmin,
            xmax - point[0],
            point[1] - ymin,
            ymax - point[1],
        )
        if margin < REQUIRED_JOINT_MARGIN_DEG - 1.0e-6:
            raise AssertionError(
                f"{label}: joint margin {margin:.9f} at pulse={pulse}"
            )
        if paper_margin < REQUIRED_PAPER_MARGIN_MM - 1.0e-6:
            raise AssertionError(
                f"{label}: paper margin {paper_margin:.9f} at pulse={pulse}"
            )
        minimum_joint_margin = min(minimum_joint_margin, margin)
        minimum_paper_margin = min(minimum_paper_margin, paper_margin)
        points.append(point)

    chord = math.hypot(
        points[-1][0] - points[0][0], points[-1][1] - points[0][1]
    )
    formula = 2.0 * 203.0 * math.sin(
        math.radians(RAW_PULSES / stage2_scale) / 2.0
    )
    if abs(chord - formula) > 1.0e-6:
        raise AssertionError(f"{label}: chord formula mismatch")
    analytic = arc_extrema(start1, start2, stage1_scale, stage2_scale)
    if abs(float(analytic["chord"]) - chord) > 1.0e-6:
        raise AssertionError(f"{label}: analytic arc mismatch")
    return {
        **analytic,
        "paper_margin": minimum_paper_margin,
        "joint_margin": minimum_joint_margin,
        "chord": chord,
    }


def check_raw_arc(start1: int, start2: int) -> None:
    scale_cases = (
        (STAGE1_NOMINAL_SCALE, STAGE2_NOMINAL_SCALE, "NOMINAL"),
        (STAGE1_SCALE_MIN, STAGE2_SCALE_MIN, "CANDIDATE_00"),
        (STAGE1_SCALE_MIN, STAGE2_SCALE_MAX, "CANDIDATE_01"),
        (STAGE1_SCALE_MAX, STAGE2_SCALE_MIN, "CANDIDATE_10"),
        (STAGE1_SCALE_MAX, STAGE2_SCALE_MAX, "CANDIDATE_11"),
    )
    results = [
        check_integer_arc_at_scales(start1, start2, s1, s2, label)
        for s1, s2, label in scale_cases
    ]
    nominal = results[0]

    # Check the continuous uncertainty rectangle using analytic arc extrema.
    dense_paper_margin = float("inf")
    dense_joint_margin = float("inf")
    for stage1_scale in np.linspace(
        STAGE1_SCALE_MIN, STAGE1_SCALE_MAX, 185
    ):
        for stage2_scale in np.linspace(
            STAGE2_SCALE_MIN, STAGE2_SCALE_MAX, 501
        ):
            dense = arc_extrema(
                start1, start2, float(stage1_scale), float(stage2_scale)
            )
            dense_paper_margin = min(
                dense_paper_margin, float(dense["paper_margin"])
            )
            dense_joint_margin = min(
                dense_joint_margin, float(dense["joint_margin"])
            )
    if dense_paper_margin < REQUIRED_PAPER_MARGIN_MM - 1.0e-6:
        raise AssertionError("continuous candidate paper margin failed")
    if dense_joint_margin < REQUIRED_JOINT_MARGIN_DEG - 1.0e-6:
        raise AssertionError("continuous candidate joint margin failed")

    returned1 = start1
    returned2 = start2 + RAW_PULSES - RAW_PULSES
    if (returned1, returned2) != (start1, start2):
        raise AssertionError("integer return does not close at the start")

    candidate_chords = sorted(
        2.0 * 203.0 * math.sin(math.radians(RAW_PULSES / scale) / 2.0)
        for scale in (STAGE2_SCALE_MIN, STAGE2_SCALE_MAX)
    )
    nominal_start = nominal["start"]
    nominal_end = nominal["end"]
    nominal_bbox = nominal["bbox"]
    assert isinstance(nominal_start, tuple)
    assert isinstance(nominal_end, tuple)
    assert isinstance(nominal_bbox, tuple)

    print(
        f"raw_integer_arc=PASS start_steps=({start1},{start2}) "
        f"end_steps=({start1},{start2 + RAW_PULSES}) "
        f"return_steps=({returned1},{returned2}) stage1_delta=0 "
        f"nominal_psi_delta_deg={RAW_PULSES / STAGE2_NOMINAL_SCALE:.9f} "
        f"nominal_chord_mm={float(nominal['chord']):.6f} "
        f"nominal_start_mm=({nominal_start[0]:.6f},{nominal_start[1]:.6f}) "
        f"nominal_end_mm=({nominal_end[0]:.6f},{nominal_end[1]:.6f}) "
        f"nominal_bbox_mm=({nominal_bbox[0]:.6f}..{nominal_bbox[1]:.6f},"
        f"{nominal_bbox[2]:.6f}..{nominal_bbox[3]:.6f}) "
        f"candidate_stage1_scale={STAGE1_SCALE_MIN:.6f}..{STAGE1_SCALE_MAX:.6f} "
        f"candidate_stage2_scale={STAGE2_SCALE_MIN:.6f}..{STAGE2_SCALE_MAX:.6f} "
        f"candidate_chord_mm={candidate_chords[0]:.6f}.."
        f"{candidate_chords[1]:.6f} "
        f"candidate_paper_min_margin_mm={dense_paper_margin:.6f} "
        f"candidate_joint_min_margin_deg={dense_joint_margin:.6f} "
        "ideal_closure_mm=0"
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
    image, records, data_bytes = base.parse_ihex(HEX_PATH)
    if BUILD_ID not in image:
        raise AssertionError("V25 build ID missing from firmware")
    for stale_id in (
        b"AUTHOR_STAGE1_3200P_LONG_CHORD_L205_GATED_V24",
        b"AUTHOR_STAGE1_976P_CHORD_L205_GATED_V23",
        b"AUTHOR_SAFE_5POINT_DIR_DOTS_L205_L203_GATED_V22",
    ):
        if stale_id in image:
            raise AssertionError(f"stale build ID in V25 firmware: {stale_id!r}")
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
    start1, start2 = check_approach_paths()
    check_raw_arc(start1, start2)
    if not args.source_only:
        check_build_log()
        check_hex()


if __name__ == "__main__":
    main()
