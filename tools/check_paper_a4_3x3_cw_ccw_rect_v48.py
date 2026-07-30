#!/usr/bin/env python3
"""Static checks for the V48 paired-direction G-code."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEST_ID = "PAPER_A4_3X3_CW_CCW_RECT24X8_DIRECTION_GCODE_V48"
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"


def main() -> None:
    lines = GCODE_PATH.read_text(encoding="ascii").splitlines()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    pen_down = False
    g1_count = 0
    m3_count = 0
    m5_count = 0
    for line_number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        command = line.split()[0]
        if command == "M3":
            assert not pen_down, f"double M3 at line {line_number}"
            pen_down = True
            m3_count += 1
        elif command == "M5":
            pen_down = False
            m5_count += 1
        elif command == "G0":
            assert not pen_down, (
                f"connection/travel G0 while pen down at line {line_number}"
            )
        elif command == "G1":
            assert pen_down, f"G1 while pen up at line {line_number}"
            g1_count += 1
    assert not pen_down, "file ends with pen down"
    assert manifest["connection_lines"] is False
    assert manifest["motion"]["pair_count"] == 9
    assert manifest["motion"]["rectangle_count"] == 18
    assert m3_count == 18
    assert m5_count == 19
    assert g1_count == manifest["motion"]["g1_count"]
    directions = [
        item["direction"] for item in manifest["rectangles"]
    ]
    assert directions.count("CW") == 9
    assert directions.count("CCW") == 9
    print(
        "check_paper_a4_3x3_cw_ccw_rect_v48=PASS "
        f"rectangles={m3_count} G1={g1_count} "
        "pen_down_travel=0 connection_lines=0"
    )


if __name__ == "__main__":
    main()
