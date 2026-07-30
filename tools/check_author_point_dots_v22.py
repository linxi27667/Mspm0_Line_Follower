"""Verify the gated V22 point test with measured unequal link lengths."""

from __future__ import annotations

import argparse
import hashlib
import math
import re
from pathlib import Path

import numpy as np

import check_author_point_dots_v21 as v21
import check_author_rect_loop_v17 as loop
import check_author_safe_probe_v16 as base


ROOT = Path(__file__).resolve().parents[1]
MOTION_HEADER = ROOT / "APP" / "Inc" / "app_writer_motion.h"
IK_SOURCE = ROOT / "MID" / "Src" / "mid_scara.c"
TEST_HEADER = ROOT / "TASK" / "writer_test.h"
TEST_SOURCE = ROOT / "TASK" / "writer_test.c"
DOT_HEADER = ROOT / "TASK" / "workspace_corner_dot_test.h"
DOT_SOURCE = ROOT / "TASK" / "workspace_corner_dot_test.c"
MAIN_SOURCE = ROOT / "main.c"
GCODE_PATH = (
    ROOT / "gcode" / "AUTHOR_SAFE_5POINT_DIR_DOTS_L205_L203_RUN_V22.gcode"
)
COMMAND_SCRIPT = ROOT / "tools" / "point_dots_v22_control.ps1"
BUILD_LOG = (
    ROOT
    / "keil"
    / "AUTHOR_SAFE_5POINT_DIR_DOTS_L205_L203_GATED_V22_build.log"
)
KEIL_HTML_LOG = (
    ROOT
    / "keil"
    / "Objects"
    / "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.build_log.htm"
)
HEX_PATH = (
    ROOT / "keil" / "AUTHOR_SAFE_5POINT_DIR_DOTS_L205_L203_GATED_V22.hex"
)

BUILD_ID = b"AUTHOR_SAFE_5POINT_DIR_DOTS_L205_L203_GATED_V22"
L1_MM = np.float32(205.0)
L2_MM = np.float32(203.0)


def inverse_unequal(
    work_x_mm: float, work_y_mm: float
) -> tuple[np.float32, np.float32]:
    raw_x = np.float32(np.float32(work_x_mm) + base.OFFSET_X_MM)
    raw_y = np.float32(np.float32(work_y_mm) + base.OFFSET_Y_MM)
    standard_x = np.float32(-raw_x)
    standard_y = raw_y
    l1_sq = np.float32(L1_MM * L1_MM)
    l2_sq = np.float32(L2_MM * L2_MM)
    radius_sq = np.float32(
        standard_x * standard_x + standard_y * standard_y
    )
    c2 = np.float32(
        (radius_sq - l1_sq - l2_sq) /
        np.float32(2.0 * L1_MM * L2_MM)
    )
    if c2 < np.float32(-1.0) or c2 > np.float32(1.0):
        raise AssertionError(f"unreachable point ({work_x_mm},{work_y_mm})")
    s2 = np.sqrt(np.float32(1.0) - np.float32(c2 * c2), dtype=np.float32)
    k1 = np.float32(L1_MM + np.float32(L2_MM * c2))
    k2 = np.float32(L2_MM * s2)
    theta = np.float32(
        np.arctan2(k1, k2) - np.arctan2(standard_x, standard_y)
    )
    psi = np.float32(theta + np.arctan2(s2, c2))
    to_deg = np.float32(180.0 / math.pi)
    return np.float32(theta * to_deg), np.float32(psi * to_deg)


def configure_model() -> None:
    base.L1_MM = L1_MM
    base.L2_MM = L2_MM
    base.inverse = inverse_unequal


def parse_source_points(text: str) -> tuple[v21.PointSpec, ...]:
    pattern = re.compile(
        r'\{"([A-Z0-9_]+)",\s*(-?\d+(?:\.\d+)?)f,\s*'
        r'(-?\d+(?:\.\d+)?)f,\s*(true|false)\},'
    )
    return tuple(
        v21.PointSpec(
            match.group(1),
            float(match.group(2)),
            float(match.group(3)),
            match.group(4) == "true",
        )
        for match in pattern.finditer(text)
    )


def check_source_contract() -> None:
    motion = MOTION_HEADER.read_text(encoding="ascii")
    ik_source = IK_SOURCE.read_text(encoding="utf-8-sig")
    test_h = TEST_HEADER.read_text(encoding="ascii")
    test_c = TEST_SOURCE.read_text(encoding="ascii")
    dot_h = DOT_HEADER.read_text(encoding="ascii")
    dot_c = DOT_SOURCE.read_text(encoding="ascii")
    main_c = MAIN_SOURCE.read_text(encoding="ascii")
    command = COMMAND_SCRIPT.read_text(encoding="ascii")

    for needle in (
        "#define APP_WRITER_L1_MM                    (205.0f)",
        "#define APP_WRITER_L2_MM                    (203.0f)",
        "#define APP_WRITER_MACHINE_OFFSET_X_MM      (-129.0f)",
        "#define APP_WRITER_MACHINE_OFFSET_Y_MM      (128.0f)",
        "#define APP_WRITER_THETA_LIMIT_DEG          (-0.709247f)",
        "#define APP_WRITER_PSI_LIMIT_DEG            (134.323770f)",
        "#define APP_WRITER_STAGE1_STEPS_PER_DEG     (43.708318f)",
        "#define APP_WRITER_STAGE2_STEPS_PER_DEG     (48.8f)",
        "#define APP_WRITER_DIRECTION_COMP_ENABLE     (0u)",
        "#define APP_WRITER_AUTHOR_LINE_EXECUTION_ENABLE (0u)",
        "#define APP_WRITER_A4_ENVELOPE_PROBE_ENABLE  (1u)",
        "#define APP_WRITER_PLAN_SEGMENT_MM          (1.0f)",
        "#define APP_WRITER_PLAN_MAX_SEGMENTS        (192u)",
    ):
        base.require(motion, needle, "motion contract")
    for needle in (
        "float k1 = cfg->l1_mm + cfg->l2_mm * c2;",
        "float k2 = cfg->l2_mm * s2;",
        "equivalent only when L1 == L2",
    ):
        base.require(ik_source, needle, "unequal-link IK")
    for stale in (
        "float k1 = l1_sq + l2_sq * c2;",
        "float k2 = l2_sq * s2;",
    ):
        if stale in ik_source:
            raise AssertionError(f"stale equal-link-only IK remains: {stale}")
    base.require(
        test_h,
        "#define WRITER_TEST_MODE             WRITER_TEST_MODE_WORKSPACE_CORNER_DOTS",
        "selected mode",
    )
    for needle in (
        "(WRITER_TEST_MODE != WRITER_TEST_MODE_WORKSPACE_CORNER_DOTS)",
        "return WorkspaceCornerDotTest_Process_Frame(frame, len);",
        "targets=13 marks=9 isolated_points=5",
    ):
        base.require(test_c, needle, "task integration")
    for needle in (
        BUILD_ID.decode("ascii"),
        "#define WORKSPACE_CORNER_DOT_TARGET_COUNT      (13u)",
        "#define WORKSPACE_CORNER_DOT_MARK_COUNT        (9u)",
        "WORKSPACE_CORNER_DOT_STATE_WAIT_RUN",
        "WORKSPACE_CORNER_DOT_STATE_STOPPED",
        "WorkspaceCornerDotTest_Process_Frame",
    ):
        base.require(dot_h, needle, "dot header")
    for needle in (
        'elog_i("DOTV22"',
        "no_auto_motion=1",
        "gate=M501_or_RUN",
        "WriterMotion_Start_To(target->x_mm, target->y_mm)",
        "App_Servo_Pen_Down();",
        "App_Servo_Pen_Up();",
        "WriterMotion_Emergency_Stop();",
        '(strcmp(command, "M501") == 0)',
        '(strcmp(command, "RUN") == 0)',
        "s_setup_mask != WORKSPACE_CORNER_DOT_SETUP_ALL",
        'WorkspaceCornerDotTest_Fail("unexpected_uart_while_running")',
        "single_pass=1",
        "center_stamps=5",
    ):
        base.require(dot_c, needle, "dot executor")
    if "DOTV21" in dot_c:
        raise AssertionError("stale DOTV21 log tag remains")
    base.require(
        main_c,
        "if (WriterHome_InitialHome_Task())",
        "automatic homing",
    )
    for needle in (
        '[ValidateSet("STATUS", "START", "STOP")]',
        "-ConfirmPaperFixed",
        BUILD_ID.decode("ascii"),
        '$preflight -notmatch "state=WAIT_RUN"',
        'foreach ($command in @("G21", "G90", "G94", "M5"))',
        'Send-WriterCommand -Command "M501"',
    ):
        base.require(command, needle, "host control")

    source_points = parse_source_points(dot_c)
    if source_points != v21.POINTS:
        raise AssertionError(
            f"embedded point list mismatch\nexpected={v21.POINTS}"
            f"\nactual={source_points}"
        )
    print(
        "source_contract=PASS mode=V22 L1=205 L2=203 "
        "unequal_link_ik=GENERAL gate=G21_G90_G94_M5_M501 "
        "targets=13 marks=9 single_pass=1"
    )


def check_gcode() -> str:
    lines = tuple(GCODE_PATH.read_text(encoding="ascii").splitlines())
    if lines != v21.EXPECTED_GCODE:
        raise AssertionError(
            f"gate G-code mismatch expected={v21.EXPECTED_GCODE} actual={lines}"
        )
    if any(re.search(r"[XYZFS]|M3|G0|G1", line) for line in lines):
        raise AssertionError("gate file contains a motion or pen-down word")
    digest = hashlib.sha256(GCODE_PATH.read_bytes()).hexdigest().upper()
    print(
        f"gcode_gate=PASS lines=5 motion_words=0 pen_down=0 final=M501 "
        f"sha256={digest}"
    )
    return digest


def check_round_trip() -> None:
    maximum_error = 0.0
    for point in v21.POINTS:
        theta, psi = inverse_unequal(point.x_mm, point.y_mm)
        theta_rad = np.float32(theta * np.float32(math.pi / 180.0))
        psi_rad = np.float32(psi * np.float32(math.pi / 180.0))
        machine_x = np.float32(
            -np.cos(theta_rad, dtype=np.float32) * L1_MM
            - np.cos(psi_rad, dtype=np.float32) * L2_MM
        )
        machine_y = np.float32(
            np.sin(theta_rad, dtype=np.float32) * L1_MM
            + np.sin(psi_rad, dtype=np.float32) * L2_MM
        )
        expected_x = np.float32(point.x_mm) + base.OFFSET_X_MM
        expected_y = np.float32(point.y_mm) + base.OFFSET_Y_MM
        error = math.hypot(
            float(machine_x - expected_x), float(machine_y - expected_y)
        )
        maximum_error = max(maximum_error, error)
    if maximum_error > 0.001:
        raise AssertionError(f"unequal-link IK/FK error {maximum_error:.9f} mm")
    print(f"ik_fk_round_trip=PASS max_error_mm={maximum_error:.9f}")


def check_build_log() -> None:
    text = BUILD_LOG.read_text(encoding="utf-8", errors="replace")
    html = KEIL_HTML_LOG.read_text(encoding="utf-8", errors="replace")
    base.require(
        html,
        "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx",
        "correct Keil project",
    )
    base.require(text, "0 Error(s), 0 Warning(s).", "clean build")
    if "Target not created" in text:
        raise AssertionError("build log reports target not created")
    print("keil_build=PASS project=CORRECT errors=0 warnings=0")


def check_hex() -> str:
    image, records, data_bytes = base.parse_ihex(HEX_PATH)
    if BUILD_ID not in image:
        raise AssertionError("V22 build ID missing from firmware")
    if b"AUTHOR_SAFE_5POINT_DIR_DOTS_GATED_V21" in image:
        raise AssertionError("stale V21 build ID present in V22 firmware")
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
    check_round_trip()
    v21.check_integer_paths()
    if not args.source_only:
        check_build_log()
        check_hex()


if __name__ == "__main__":
    main()
