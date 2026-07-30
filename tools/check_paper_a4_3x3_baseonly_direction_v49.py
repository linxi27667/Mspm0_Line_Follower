#!/usr/bin/env python3
"""Static checks for the V49 base-only direction test."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEST_ID = "PAPER_A4_3X3_BASEONLY_CHECKER_CW_CCW_RECT24X8_GCODE_V49"
GCODE = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST = ROOT / "gcode" / f"{TEST_ID}.json"


def main() -> None:
    lines = GCODE.read_text(encoding="ascii").splitlines()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pen_down = False
    counts = {"M3": 0, "M5": 0, "G1": 0}
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
        elif command == "G1":
            assert pen_down, f"pen-up G1 line {line_number}"
            counts["G1"] += 1
    assert not pen_down
    assert manifest["mapping"]["old_grid4x7_residual_enabled"] is False
    assert manifest["connection_lines"] is False
    assert counts["M3"] == 18
    assert counts["M5"] == 19
    assert counts["G1"] == manifest["motion"]["g1_count"]
    upper = [
        item["direction"]
        for item in manifest["rectangles"]
        if item["vertical_slot"] == "UPPER"
    ]
    lower = [
        item["direction"]
        for item in manifest["rectangles"]
        if item["vertical_slot"] == "LOWER"
    ]
    assert upper.count("CW") == 4 and upper.count("CCW") == 5
    assert lower.count("CW") == 5 and lower.count("CCW") == 4
    print(
        "check_paper_a4_3x3_baseonly_direction_v49=PASS "
        f"rectangles={counts['M3']} G1={counts['G1']} "
        "pen_down_travel=0 grid4x7_residual=0"
    )


if __name__ == "__main__":
    main()
