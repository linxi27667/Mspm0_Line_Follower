#!/usr/bin/env python3
"""Verify the mixed-font standard-coordinate V66 writing sample."""

from __future__ import annotations

import hashlib
import json

import generate_paper_a4_standard_upper_four_fonts_6mm_v66 as sample


def main() -> None:
    rows = sample.build_rows()
    expected_lines = sample.gcode_lines(rows)
    actual_text = sample.GCODE_PATH.read_text(encoding="ascii")
    actual_lines = tuple(actual_text.splitlines())
    if actual_lines != expected_lines:
        raise AssertionError("V66 no longer matches its pinned font sources")

    manifest = json.loads(
        sample.MANIFEST_PATH.read_text(encoding="utf-8")
    )
    actual_hash = hashlib.sha256(actual_text.encode("ascii")).hexdigest().upper()
    if actual_hash != manifest["gcode"]["sha256"]:
        raise AssertionError("V66 G-code hash mismatch")
    if manifest["coordinate_contract"] != {
        "units": "mm",
        "frame": "nominal physical A4 paper",
        "offline_mapping": False,
        "offline_prewarp": False,
        "firmware_mapping": True,
    }:
        raise AssertionError("V66 is not standard-coordinate G-code")
    if manifest["safety"]["min_joint_margin_deg"] <= 0.0:
        raise AssertionError("V66 joint margin is not positive")

    expected_options = ["K", "B", "M", "Y"]
    if [font["option"] for font in manifest["fonts"]] != expected_options:
        raise AssertionError("V66 font order changed")
    if any(font["synthesized_glyphs"] for font in manifest["fonts"]):
        raise AssertionError("V66 contains synthesized glyphs")
    for row, font_record in zip(rows, manifest["fonts"]):
        if sample.digest(row.spec.path) != font_record["sha256"]:
            raise AssertionError(f"font {row.spec.option} hash mismatch")
        if list(row.bounds_mm) != font_record["bounds_mm"]:
            raise AssertionError(f"font {row.spec.option} bounds changed")

    commands = [
        line
        for line in actual_lines
        if line and not line.startswith(";")
    ]
    if commands[:6] != ["G21", "G90", "G94", "F300", "S1000", "M5"]:
        raise AssertionError(f"unexpected V66 preamble: {commands[:6]}")

    pen_down = False
    g0_count = 0
    g1_count = 0
    m3_count = 0
    m5_count = 0
    for command in commands[6:]:
        if command.startswith("G0 "):
            if pen_down:
                raise AssertionError("V66 rapid move while pen is down")
            g0_count += 1
        elif command.startswith("G1 "):
            if not pen_down:
                raise AssertionError("V66 draw move while pen is up")
            g1_count += 1
        elif command == "M3":
            if pen_down:
                raise AssertionError("duplicate V66 pen down")
            pen_down = True
            m3_count += 1
        elif command == "M5":
            pen_down = False
            m5_count += 1
        else:
            raise AssertionError(f"unexpected V66 command: {command}")
    if pen_down:
        raise AssertionError("V66 ends pen-down")
    expected_strokes = sum(len(row.strokes) for row in rows)
    if g0_count != 2 * expected_strokes or m3_count != expected_strokes:
        raise AssertionError("V66 approach/stroke count changed")

    print(
        "standard_upper_four_fonts_6mm_v66=PASS "
        "fonts=KAI_TI,B,MA_SHAN_ZHENG,YOUYUAN "
        "coordinates=STANDARD_A4 synthesized_glyphs=NO "
        f"strokes={expected_strokes} G0={g0_count} G1={g1_count} "
        f"M3={m3_count} M5={m5_count} "
        f"min_joint_margin={manifest['safety']['min_joint_margin_deg']:.6f}deg"
    )
    print(f"gcode_sha256={actual_hash}")


if __name__ == "__main__":
    main()
