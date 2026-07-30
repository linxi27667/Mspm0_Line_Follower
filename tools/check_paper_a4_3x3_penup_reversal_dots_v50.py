#!/usr/bin/env python3
"""Static checks for the V50 pen-up reversal dot-pair test."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEST_ID = "PAPER_A4_3X3_PENUP_REVERSAL_DOT_PAIRS_GCODE_V50"
GCODE = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST = ROOT / "gcode" / f"{TEST_ID}.json"


def main() -> None:
    lines = GCODE.read_text(encoding="ascii").splitlines()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pen_down = False
    counts = {"G0": 0, "G1": 0, "M3": 0, "M5": 0, "G4": 0}
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
            counts["G1"] += 1
        elif command == "G4":
            assert pen_down, f"dwell while pen up line {line_number}"
            counts["G4"] += 1
    assert not pen_down
    assert counts["G1"] == 0
    assert counts["G0"] == 72
    assert counts["M3"] == 36
    assert counts["M5"] == 37
    assert counts["G4"] == 36
    assert manifest["motion"]["pen_down_travel_count"] == 0
    assert (
        manifest["mapping"]["old_grid4x7_residual_enabled"] is False
    )
    target_groups = {}
    for mark in manifest["marks"]:
        key = (mark["zone"], mark["target_name"])
        target_groups.setdefault(key, []).append(mark)
    assert len(target_groups) == 18
    for marks in target_groups.values():
        assert len(marks) == 2
        assert marks[0]["target_user_mm"] == marks[1]["target_user_mm"]
    print(
        "check_paper_a4_3x3_penup_reversal_dots_v50=PASS "
        "zones=9 targets=18 marks=36 G1=0 pen_down_travel=0"
    )


if __name__ == "__main__":
    main()
