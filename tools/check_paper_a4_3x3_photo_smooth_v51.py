#!/usr/bin/env python3
"""Static checks for the V51 smooth photo-corrected validation."""

from __future__ import annotations

import json
import re
from pathlib import Path

from check_fixed_layout_3rect_x95_y20_130_waypoint_v17 import (
    HOME_USER,
    margin,
    samples,
)


ROOT = Path(__file__).resolve().parents[1]
TEST_ID = "PAPER_A4_3X3_PHOTO_SMOOTH_CHECKER_CW_CCW_RECT24X8_GCODE_V51"
GCODE = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST = ROOT / "gcode" / f"{TEST_ID}.json"


def main() -> None:
    lines = GCODE.read_text(encoding="ascii").splitlines()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pen_down = False
    counts = {"G0": 0, "G1": 0, "M3": 0, "M5": 0}
    targets = []
    for line_number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        command = line.split()[0]
        if command == "M3":
            assert not pen_down, f"double M3 line {line_number}"
            pen_down = True
            counts["M3"] += 1
        elif command == "M5":
            pen_down = False
            counts["M5"] += 1
        elif command == "G0":
            assert not pen_down, f"pen-down G0 line {line_number}"
            counts["G0"] += 1
        elif command == "G1":
            assert pen_down, f"pen-up G1 line {line_number}"
            counts["G1"] += 1
        if command in ("G0", "G1"):
            match = re.fullmatch(
                r"G[01] X(-?\d+(?:\.\d+)?) Y(-?\d+(?:\.\d+)?)",
                line,
            )
            assert match is not None, f"bad motion line {line_number}"
            targets.append(
                (float(match.group(1)), float(match.group(2)))
            )
    assert not pen_down
    assert manifest["connection_lines"] is False
    assert (
        manifest["correction_map"]["old_grid4x7_residual_enabled"]
        is False
    )
    assert manifest["motion"]["rectangle_count"] == 18
    assert counts["M3"] == 18
    assert counts["M5"] == 19
    assert counts["G0"] == 36
    assert counts["G1"] == manifest["motion"]["g1_count"]
    assert (
        manifest["correction_map"]["fit"]["p95_residual_mm"] < 2.5
    )
    previous = HOME_USER
    safety_sample_count = 0
    worst_margin = float("inf")
    for target in targets:
        for point in samples(previous, target):
            joint_margin, _ = margin(point)
            worst_margin = min(worst_margin, joint_margin)
            safety_sample_count += 1
        previous = target
    assert worst_margin >= -0.001
    print(
        "check_paper_a4_3x3_photo_smooth_v51=PASS "
        f"rectangles={counts['M3']} G1={counts['G1']} "
        f"safety_samples={safety_sample_count} "
        f"worst_joint_margin={worst_margin:.6f}deg "
        "pen_down_travel_only=1 connection_lines=0"
    )


if __name__ == "__main__":
    main()
