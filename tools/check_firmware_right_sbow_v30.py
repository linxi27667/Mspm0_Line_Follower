#!/usr/bin/env python3
"""Audit V30 right-half-only vertical S-bow firmware mapping."""

from __future__ import annotations

import hashlib
import math
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from check_workspace_yshift15_v28 import SHIFT_X_MM, SHIFT_Y_MM, joint_margin
from generate_paper_a4_3x3_baseonly_direction_v49 import map_base_only
from generate_paper_a4_full_width_square_spiral_v59 import home_user
from generate_paper_a4_measured_bow_correction_lines_v61 import (
    X_SCALE_OBSERVED,
    X_SCALE_REFERENCE_MM,
    measured_errors,
)


FIRMWARE_ID = (
    "PAPER_A4_STANDARD_GCODE_RIGHT_SBOW_PAPERMAP_YSHIFT15_V30"
)
PAPER_MAP_ID = "A4_BASE_QUADRATIC_RIGHT_SBOW_PCHIP_CAL_V7"
PAPER_MAP_HEADER = ROOT / "APP" / "Inc" / "app_writer_paper_map.h"
PAPER_MAP_SOURCE = ROOT / "APP" / "Src" / "app_writer_paper_map.c"
GCODE_HEADER = ROOT / "TASK" / "gcode_serial.h"
GCODE_SOURCE = ROOT / "TASK" / "gcode_serial.c"
BUILD_LOG = ROOT / "keil" / "build_v30_log.txt"
HEX_PATH = ROOT / "keil" / f"{FIRMWARE_ID}.hex"
JFLASH = ROOT / "Jlink.jflash"
SPIRAL_PATH = (
    ROOT
    / "gcode"
    / "PAPER_A4_STANDARD_FULL_WIDTH_160MM_SQUARE_SPIRAL_F300_RIGHT_SBOW_GCODE_V64.gcode"
)

RIGHT_X0_MM = 105.0
RIGHT_X1_MM = 185.0
MOTION_RE = re.compile(
    r"^G(?P<mode>[01])\s+X(?P<x>-?\d+(?:\.\d+)?)"
    r"\s+Y(?P<y>-?\d+(?:\.\d+)?)$"
)


def vertical_sbow_weight(paper_x_mm: float) -> float:
    t = (paper_x_mm - RIGHT_X0_MM) / (RIGHT_X1_MM - RIGHT_X0_MM)
    t = min(max(t, 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def firmware_prewarp(
    physical_paper: tuple[float, float],
) -> tuple[float, float]:
    x_error, y_error = measured_errors(physical_paper)
    scaled_x = X_SCALE_REFERENCE_MM + (
        physical_paper[0] - X_SCALE_REFERENCE_MM
    ) / X_SCALE_OBSERVED
    return (
        scaled_x
        - vertical_sbow_weight(physical_paper[0]) * x_error,
        physical_paper[1] - y_error,
    )


def firmware_map(
    physical_paper: tuple[float, float],
) -> tuple[float, float]:
    prewarped_physical = firmware_prewarp(physical_paper)
    legacy_logical = (
        prewarped_physical[0],
        prewarped_physical[1] - SHIFT_Y_MM,
    )
    base_user = map_base_only(legacy_logical)
    return (
        base_user[0] + SHIFT_X_MM,
        base_user[1] + SHIFT_Y_MM,
    )


def sampled_line(
    start: tuple[float, float],
    end: tuple[float, float],
) -> tuple[tuple[float, float], ...]:
    span = max(abs(end[0] - start[0]), abs(end[1] - start[1]))
    count = max(1, math.ceil(span))
    return tuple(
        (
            start[0] + (end[0] - start[0]) * index / count,
            start[1] + (end[1] - start[1]) * index / count,
        )
        for index in range(1, count + 1)
    )


def audit_source_contract() -> None:
    map_header = PAPER_MAP_HEADER.read_text(encoding="utf-8")
    map_source = PAPER_MAP_SOURCE.read_text(encoding="utf-8")
    gcode_header = GCODE_HEADER.read_text(encoding="utf-8")
    gcode_source = GCODE_SOURCE.read_text(encoding="utf-8")
    build_log = BUILD_LOG.read_text(encoding="utf-8")
    jflash = JFLASH.read_text(encoding="utf-8")

    for token in (
        f'"{FIRMWARE_ID}"',
        "#define GCODE_SERIAL_PAPER_MAP_ENABLE         (1u)",
        "#define GCODE_SERIAL_PAPER_DRAW_SEGMENT_MM    (1.0f)",
    ):
        if token not in gcode_header:
            raise AssertionError(f"missing G-code token: {token}")
    for token in (
        f'"{PAPER_MAP_ID}"',
        "#define APP_WRITER_PAPER_GRID_CORRECTION_ENABLE (0u)",
        "#define APP_WRITER_PAPER_S_BOW_CORRECTION_ENABLE (1u)",
        "#define APP_WRITER_PAPER_VERTICAL_SBOW_RIGHT_ONLY_ENABLE (1u)",
        "#define APP_WRITER_PAPER_VERTICAL_SBOW_RIGHT_X0_MM (105.0f)",
        "#define APP_WRITER_PAPER_VERTICAL_SBOW_RIGHT_X1_MM (185.0f)",
    ):
        if token not in map_header:
            raise AssertionError(f"missing paper-map token: {token}")
    for token in (
        "WriterPaperMap_Vertical_Sbow_Weight",
        "vertical_sbow_weight * x_error_mm",
        "t * t * (3.0f - 2.0f * t)",
    ):
        if token not in map_source:
            raise AssertionError(f"missing right-side implementation: {token}")
    for token in ("vsbow_right=%u", "vsbow_x0=%d", "vsbow_x1=%d"):
        if token not in gcode_source:
            raise AssertionError(f"missing status token: {token}")
    if "0 Error(s), 0 Warning(s)." not in build_log:
        raise AssertionError("V30 Keil build is not clean")
    if str(HEX_PATH) not in jflash:
        raise AssertionError("J-Link project does not select V30 HEX")


def audit_weighting() -> None:
    expected = {
        25.0: 0.0,
        105.0: 0.0,
        125.0: 0.15625,
        145.0: 0.5,
        165.0: 0.84375,
        185.0: 1.0,
    }
    for paper_x, expected_weight in expected.items():
        actual = vertical_sbow_weight(paper_x)
        if not math.isclose(actual, expected_weight, abs_tol=1.0e-9):
            raise AssertionError(
                f"bad right-side weight at X={paper_x}: {actual}"
            )

    for paper_x in (25.0, 65.0, 105.0):
        top_x = firmware_prewarp((paper_x, 235.0))[0]
        bottom_x = firmware_prewarp((paper_x, 75.0))[0]
        if not math.isclose(top_x, bottom_x, abs_tol=1.0e-9):
            raise AssertionError(
                f"left half received vertical S-bow at X={paper_x}"
            )

    right_top_x = firmware_prewarp((185.0, 235.0))[0]
    right_bottom_x = firmware_prewarp((185.0, 75.0))[0]
    if not math.isclose(
        right_top_x - right_bottom_x, 4.0, abs_tol=1.0e-6
    ):
        raise AssertionError("right edge did not receive full correction")


def parse_spiral() -> tuple[tuple[int, tuple[float, float]], ...]:
    lines = [
        raw.split(";", 1)[0].strip()
        for raw in SPIRAL_PATH.read_text(encoding="ascii").splitlines()
    ]
    motions: list[tuple[int, tuple[float, float]]] = []
    pen_down = False
    for line in lines:
        if not line or line in ("G21", "G90", "G94", "F300", "S1000"):
            continue
        if line == "M3":
            pen_down = True
            continue
        if line == "M5":
            pen_down = False
            continue
        match = MOTION_RE.fullmatch(line)
        if match is None:
            raise AssertionError(f"unexpected V64 command: {line}")
        mode = int(match.group("mode"))
        if (mode == 0 and pen_down) or (mode == 1 and not pen_down):
            raise AssertionError(f"bad pen state for {line}")
        point = (float(match.group("x")), float(match.group("y")))
        if not (25.0 <= point[0] <= 185.0 and 75.0 <= point[1] <= 235.0):
            raise AssertionError(f"spiral point out of bounds: {point}")
        motions.append((mode, point))
    return tuple(motions)


def audit_spiral_path(
    motions: tuple[tuple[int, tuple[float, float]], ...],
) -> tuple[int, float, tuple[float, float]]:
    current_user = home_user()
    current_paper: tuple[float, float] | None = None
    worst = (float("inf"), (0.0, 0.0))
    sample_count = 0
    for mode, target_paper in motions:
        if mode == 0:
            target_user = firmware_map(target_paper)
            span = max(
                abs(target_user[0] - current_user[0]),
                abs(target_user[1] - current_user[1]),
            )
            count = max(1, math.ceil(span / 20.0))
            user_samples = tuple(
                (
                    current_user[0]
                    + (target_user[0] - current_user[0]) * index / count,
                    current_user[1]
                    + (target_user[1] - current_user[1]) * index / count,
                )
                for index in range(1, count + 1)
            )
        else:
            if current_paper is None:
                raise AssertionError("G1 without source position")
            user_samples = tuple(
                firmware_map(sample)
                for sample in sampled_line(current_paper, target_paper)
            )

        for user_sample in user_samples:
            margin, _ = joint_margin(user_sample)
            if margin < worst[0]:
                worst = (margin, user_sample)
            sample_count += 1
        current_user = firmware_map(target_paper)
        current_paper = target_paper

    if worst[0] < -0.001:
        raise AssertionError(f"V30/V63 path violates limits: {worst}")
    return sample_count, worst[0], worst[1]


def main() -> None:
    audit_source_contract()
    audit_weighting()
    samples, margin, location = audit_spiral_path(parse_spiral())
    hex_hash = hashlib.sha256(HEX_PATH.read_bytes()).hexdigest().upper()
    print(
        "firmware_right_sbow_v30=PASS "
        "left_half_vertical_sbow=OFF right_edge_vertical_sbow=FULL "
        f"safe_samples={samples} min_joint_margin={margin:.6f}deg "
        f"at_user=({location[0]:.3f},{location[1]:.3f})"
    )
    print(f"hex_sha256={hex_hash}")


if __name__ == "__main__":
    main()
