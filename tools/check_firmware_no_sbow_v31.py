#!/usr/bin/env python3
"""Audit the V31 single-variable no-S-bow firmware build."""

from __future__ import annotations

import hashlib
import math
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from check_workspace_yshift15_v28 import SHIFT_X_MM, SHIFT_Y_MM, joint_margin
from generate_paper_a4_3x3_baseonly_direction_v49 import map_base_only
from generate_paper_a4_measured_bow_correction_lines_v61 import (
    X_SCALE_OBSERVED,
    X_SCALE_REFERENCE_MM,
)


FIRMWARE_ID = "PAPER_A4_STANDARD_GCODE_NO_SBOW_PAPERMAP_YSHIFT15_V31"
PAPER_MAP_ID = "A4_BASE_QUADRATIC_XSCALE_NO_SBOW_CAL_V8"
PAPER_MAP_HEADER = ROOT / "APP" / "Inc" / "app_writer_paper_map.h"
PAPER_MAP_SOURCE = ROOT / "APP" / "Src" / "app_writer_paper_map.c"
GCODE_HEADER = ROOT / "TASK" / "gcode_serial.h"
BUILD_LOG = ROOT / "keil" / "build_v31_log.txt"
HEX_PATH = ROOT / "keil" / f"{FIRMWARE_ID}.hex"
JFLASH = ROOT / "Jlink.jflash"
PIN_CONFIG = ROOT / "ti_msp_dl_config.c"


def firmware_prewarp_no_sbow(
    paper: tuple[float, float],
) -> tuple[float, float]:
    return (
        X_SCALE_REFERENCE_MM
        + (paper[0] - X_SCALE_REFERENCE_MM) / X_SCALE_OBSERVED,
        paper[1] - SHIFT_Y_MM,
    )


def firmware_map_no_sbow(
    paper: tuple[float, float],
) -> tuple[float, float]:
    base_user = map_base_only(firmware_prewarp_no_sbow(paper))
    return base_user[0] + SHIFT_X_MM, base_user[1] + SHIFT_Y_MM


def audit_contract() -> None:
    header = GCODE_HEADER.read_text(encoding="utf-8")
    map_header = PAPER_MAP_HEADER.read_text(encoding="utf-8")
    map_source = PAPER_MAP_SOURCE.read_text(encoding="utf-8")
    build_log = BUILD_LOG.read_text(encoding="utf-8")
    jflash = JFLASH.read_text(encoding="utf-8")
    pins = PIN_CONFIG.read_text(encoding="utf-8")

    for token in (
        f'"{FIRMWARE_ID}"',
        "#define GCODE_SERIAL_PAPER_MAP_ENABLE         (1u)",
        "#define GCODE_SERIAL_WORKSPACE_SHIFT_Y_MM     (15.0f)",
    ):
        if token not in header:
            raise AssertionError(f"missing G-code contract token: {token}")
    for token in (
        f'"{PAPER_MAP_ID}"',
        "#define APP_WRITER_PAPER_GRID_CORRECTION_ENABLE (0u)",
        "#define APP_WRITER_PAPER_S_BOW_CORRECTION_ENABLE (0u)",
        "#define APP_WRITER_PAPER_X_SCALE_OBSERVED      (1.03125f)",
        "#define APP_WRITER_PAPER_LEGACY_Y_SHIFT_MM     (15.0f)",
    ):
        if token not in map_header:
            raise AssertionError(f"missing paper-map contract token: {token}")
    for token in (
        "(paper_x_mm - 105.0f) /",
        "APP_WRITER_PAPER_X_SCALE_OBSERVED",
        "APP_WRITER_PAPER_LEGACY_Y_SHIFT_MM",
        "do not turn the direction-dependent 160 mm line residual",
    ):
        if token not in map_source:
            raise AssertionError(f"missing V31 no-S-bow source token: {token}")
    if "0 Error(s), 0 Warning(s)." not in build_log:
        raise AssertionError("V31 Keil build is not clean")
    if str(HEX_PATH) not in jflash:
        raise AssertionError("J-Link project does not select V31 HEX")
    if pins.count("DL_GPIO_RESISTOR_PULL_UP") != 2:
        raise AssertionError("both NC limit inputs must retain pull-ups")


def audit_local_geometry() -> None:
    for center_x in (30.0, 60.0, 90.0, 120.0, 150.0):
        horizontal_start = firmware_prewarp_no_sbow((center_x - 3.0, 220.0))
        horizontal_end = firmware_prewarp_no_sbow((center_x + 3.0, 220.0))
        vertical_start = firmware_prewarp_no_sbow((center_x, 217.0))
        vertical_end = firmware_prewarp_no_sbow((center_x, 223.0))
        if not math.isclose(
            horizontal_start[1], horizontal_end[1], abs_tol=1.0e-12
        ):
            raise AssertionError("V31 prewarp tilts a horizontal short stroke")
        if not math.isclose(
            vertical_start[0], vertical_end[0], abs_tol=1.0e-12
        ):
            raise AssertionError("V31 prewarp tilts a vertical short stroke")


def audit_workspace() -> tuple[int, float, tuple[float, float]]:
    samples = 0
    worst = (float("inf"), (0.0, 0.0))
    for paper_y in range(75, 236):
        for paper_x in range(25, 186):
            user = firmware_map_no_sbow((float(paper_x), float(paper_y)))
            margin, _ = joint_margin(user)
            if margin < worst[0]:
                worst = (margin, user)
            samples += 1
    if worst[0] < -0.001:
        raise AssertionError(f"V31 mapped workspace violates limits: {worst}")
    return samples, worst[0], worst[1]


def main() -> None:
    audit_contract()
    audit_local_geometry()
    samples, margin, location = audit_workspace()
    digest = hashlib.sha256(HEX_PATH.read_bytes()).hexdigest().upper()
    print(
        "firmware_no_sbow_v31=PASS "
        "base_quadratic=ON xscale=ON yshift15=ON "
        "measured_sbow=OFF grid4x7=OFF "
        f"safe_samples={samples} min_joint_margin={margin:.6f}deg "
        f"at_user=({location[0]:.3f},{location[1]:.3f})"
    )
    print(f"hex_sha256={digest}")


if __name__ == "__main__":
    main()
