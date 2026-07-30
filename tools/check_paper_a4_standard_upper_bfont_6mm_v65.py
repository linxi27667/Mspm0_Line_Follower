#!/usr/bin/env python3
"""Verify the standard-coordinate V65 B-gfont writing sample."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import generate_paper_a4_standard_upper_bfont_6mm_v65 as sample


def main() -> None:
    layout = sample.build_layout()
    expected_lines = sample.gcode_lines(layout)
    actual_text = sample.GCODE_PATH.read_text(encoding="ascii")
    actual_lines = tuple(actual_text.splitlines())
    if actual_lines != expected_lines:
        raise AssertionError(
            "V65 no longer matches original B-gfont standard coordinates"
        )

    manifest = json.loads(
        sample.MANIFEST_PATH.read_text(encoding="utf-8")
    )
    actual_hash = hashlib.sha256(actual_text.encode("ascii")).hexdigest().upper()
    if actual_hash != manifest["gcode"]["sha256"]:
        raise AssertionError("V65 G-code hash mismatch")
    if manifest["font"]["sha256"] != sample.FONT_SHA256:
        raise AssertionError("V65 font hash mismatch")
    if manifest["font"]["geometry"] != (
        "unmodified gfont path points and command order"
    ):
        raise AssertionError("V65 source geometry contract changed")
    if manifest["coordinate_contract"] != {
        "units": "mm",
        "frame": "nominal physical A4 paper",
        "offline_mapping": False,
        "offline_prewarp": False,
        "firmware_mapping": True,
    }:
        raise AssertionError("V65 is not standard-coordinate G-code")
    if manifest["period_substitution"]["synthesized_geometry"]:
        raise AssertionError("V65 synthesized date punctuation")
    if manifest["safety"]["min_joint_margin_deg"] <= 0.0:
        raise AssertionError("V65 joint margin is not positive")

    commands = [
        line
        for line in actual_lines
        if line and not line.startswith(";")
    ]
    if commands[:6] != ["G21", "G90", "G94", "F300", "S1000", "M5"]:
        raise AssertionError(f"unexpected V65 preamble: {commands[:6]}")

    pen_down = False
    g0_count = 0
    g1_count = 0
    m3_count = 0
    m5_count = 0
    for command in commands[6:]:
        if command.startswith("G0 "):
            if pen_down:
                raise AssertionError("V65 rapid move while pen is down")
            g0_count += 1
        elif command.startswith("G1 "):
            if not pen_down:
                raise AssertionError("V65 draw move while pen is up")
            g1_count += 1
        elif command == "M3":
            if pen_down:
                raise AssertionError("duplicate V65 pen down")
            pen_down = True
            m3_count += 1
        elif command == "M5":
            pen_down = False
            m5_count += 1
        else:
            raise AssertionError(f"unexpected V65 command: {command}")
    if pen_down:
        raise AssertionError("V65 ends pen-down")
    if g0_count != 2 * len(layout.strokes):
        raise AssertionError("V65 tangent approach count changed")
    if m3_count != len(layout.strokes):
        raise AssertionError("V65 stroke count changed")

    print(
        "standard_upper_bfont_6mm_v65=PASS "
        "font=B geometry=UNMODIFIED_GFONT "
        "coordinates=STANDARD_A4 "
        f"bounds={layout.bounds_mm} strokes={len(layout.strokes)} "
        f"G0={g0_count} G1={g1_count} M3={m3_count} M5={m5_count} "
        f"min_joint_margin={manifest['safety']['min_joint_margin_deg']:.6f}deg"
    )
    print(f"gcode_sha256={actual_hash}")


if __name__ == "__main__":
    main()
