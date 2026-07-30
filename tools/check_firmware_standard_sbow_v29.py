#!/usr/bin/env python3
"""Audit V29 firmware mapping and the unmapped V62 standard G-code."""

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
    prewarp_physical,
)
from generate_paper_a4_standard_xy_lines_v62 import (
    FIRMWARE_ID,
    GCODE_PATH,
    STROKES,
)


PAPER_MAP_HEADER = ROOT / "APP" / "Inc" / "app_writer_paper_map.h"
PAPER_MAP_SOURCE = ROOT / "APP" / "Src" / "app_writer_paper_map.c"
GCODE_HEADER = ROOT / "TASK" / "gcode_serial.h"
GCODE_SOURCE = ROOT / "TASK" / "gcode_serial.c"
BUILD_LOG = ROOT / "keil" / "build_v29_log.txt"
HEX_PATH = ROOT / "keil" / f"{FIRMWARE_ID}.hex"
JFLASH = ROOT / "Jlink.jflash"

MOTION_RE = re.compile(
    r"^G(?P<mode>[01])\s+X(?P<x>-?\d+(?:\.\d+)?)"
    r"\s+Y(?P<y>-?\d+(?:\.\d+)?)$"
)


def firmware_map(
    physical_paper: tuple[float, float],
) -> tuple[float, float]:
    prewarped_physical = prewarp_physical(physical_paper)
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
    count = max(1, math.ceil(span / 1.0))
    return tuple(
        (
            start[0] + (end[0] - start[0]) * index / count,
            start[1] + (end[1] - start[1]) * index / count,
        )
        for index in range(1, count + 1)
    )


def audit_sources() -> None:
    map_header = PAPER_MAP_HEADER.read_text(encoding="utf-8")
    map_source = PAPER_MAP_SOURCE.read_text(encoding="utf-8")
    gcode_header = GCODE_HEADER.read_text(encoding="utf-8")
    gcode_source = GCODE_SOURCE.read_text(encoding="utf-8")
    build = BUILD_LOG.read_text(encoding="utf-8")
    jflash = JFLASH.read_text(encoding="utf-8")

    for token in (
        f'"{FIRMWARE_ID}"',
        "#define GCODE_SERIAL_PAPER_MAP_ENABLE         (1u)",
        "#define GCODE_SERIAL_PAPER_DRAW_SEGMENT_MM    (1.0f)",
        "#define GCODE_SERIAL_WORKSPACE_SHIFT_Y_MM     (15.0f)",
    ):
        if token not in gcode_header:
            raise AssertionError(f"missing G-code firmware token: {token}")
    for token in (
        '"A4_BASE_QUADRATIC_SBOW_PCHIP_CAL_V6"',
        "#define APP_WRITER_PAPER_GRID_CORRECTION_ENABLE (0u)",
        "#define APP_WRITER_PAPER_S_BOW_CORRECTION_ENABLE (1u)",
        "#define APP_WRITER_PAPER_X_SCALE_OBSERVED      (1.03125f)",
        "#define APP_WRITER_PAPER_LEGACY_Y_SHIFT_MM     (15.0f)",
        "#define APP_WRITER_PAPER_Y_MIN_MM             (75.0f)",
        "#define APP_WRITER_PAPER_Y_MAX_MM             (235.0f)",
    ):
        if token not in map_header:
            raise AssertionError(f"missing paper-map token: {token}")
    for token in (
        "0.0f, 7.0f, 55.0f, 125.0f, 160.0f",
        "0.0f, 0.0f, -2.0f, 0.0f, 4.0f",
        "0.0f, 40.0f, 92.5f, 160.0f",
        "0.0f, -2.0f, 0.0f, 4.0f",
        "WriterPaperMap_Pchip",
        "WriterPaperMap_Apply_Measured_Prewarp",
    ):
        if token not in map_source:
            raise AssertionError(f"missing S-bow implementation: {token}")
    for token in (
        "grid4x7=%u sbow=%u",
        "sbow=%u map_enable=%u",
    ):
        if token not in gcode_source:
            raise AssertionError(f"missing V29 status token: {token}")
    if "0 Error(s), 0 Warning(s)." not in build:
        raise AssertionError("V29 Keil build is not clean")
    if str(HEX_PATH) not in jflash:
        raise AssertionError("J-Link project does not select V29 HEX")


def parse_standard_gcode() -> tuple[tuple[int, tuple[float, float]], ...]:
    lines = [
        raw.split(";", 1)[0].strip()
        for raw in GCODE_PATH.read_text(encoding="ascii").splitlines()
    ]
    lines = [line for line in lines if line]
    if lines[:6] != ["G21", "G90", "G94", "F300", "S1000", "M5"]:
        raise AssertionError(f"unexpected V62 preamble: {lines[:6]}")
    motions = []
    pen_down = False
    for line in lines[6:]:
        if line == "M3":
            if pen_down:
                raise AssertionError("duplicate M3")
            pen_down = True
            continue
        if line == "M5":
            pen_down = False
            continue
        match = MOTION_RE.fullmatch(line)
        if match is None:
            raise AssertionError(f"non-standard V62 command: {line}")
        mode = int(match.group("mode"))
        if (mode == 0 and pen_down) or (mode == 1 and not pen_down):
            raise AssertionError(f"bad pen state for {line}")
        point = (float(match.group("x")), float(match.group("y")))
        if not (25.0 <= point[0] <= 185.0 and 75.0 <= point[1] <= 235.0):
            raise AssertionError(f"V62 source point out of bounds: {point}")
        motions.append((mode, point))
    if pen_down:
        raise AssertionError("V62 ends pen-down")
    expected = tuple(
        item
        for _, start, end in STROKES
        for item in ((0, start), (1, end))
    )
    if tuple(motions) != expected:
        raise AssertionError("V62 contains mapped or unexpected coordinates")
    return tuple(motions)


def audit_path(
    motions: tuple[tuple[int, tuple[float, float]], ...],
) -> tuple[int, float, tuple[float, float]]:
    current_user = home_user()
    current_paper: tuple[float, float] | None = None
    worst = (float("inf"), (0.0, 0.0))
    sample_count = 0
    for mode, target_paper in motions:
        if mode == 0:
            paper_samples = (target_paper,)
        else:
            if current_paper is None:
                raise AssertionError("G1 without source position")
            paper_samples = sampled_line(current_paper, target_paper)
        for paper_sample in paper_samples:
            target_user = firmware_map(paper_sample)
            count = max(1, math.ceil(math.dist(current_user, target_user)))
            for index in range(1, count + 1):
                ratio = index / count
                sample = (
                    current_user[0]
                    + (target_user[0] - current_user[0]) * ratio,
                    current_user[1]
                    + (target_user[1] - current_user[1]) * ratio,
                )
                margin, _ = joint_margin(sample)
                if margin < worst[0]:
                    worst = (margin, sample)
                sample_count += 1
            current_user = target_user
        current_paper = target_paper
    if worst[0] < -0.001:
        raise AssertionError(f"V29/V62 path violates limits: {worst}")
    return sample_count, worst[0], worst[1]


def main() -> None:
    audit_sources()
    motions = parse_standard_gcode()
    sample_count, margin, location = audit_path(motions)
    hex_hash = hashlib.sha256(HEX_PATH.read_bytes()).hexdigest().upper()
    gcode_hash = hashlib.sha256(GCODE_PATH.read_bytes()).hexdigest().upper()
    print(
        "firmware_standard_sbow_v29=PASS "
        "paper_map=ON sbow=ON grid4x7=OFF "
        "standard_gcode_unmapped=YES "
        f"motion_commands={len(motions)} "
        f"safe_samples={sample_count} "
        f"min_joint_margin={margin:.6f}deg "
        f"at_user=({location[0]:.3f},{location[1]:.3f})"
    )
    print(f"hex_sha256={hex_hash}")
    print(f"gcode_sha256={gcode_hash}")


if __name__ == "__main__":
    main()
