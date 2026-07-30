#!/usr/bin/env python3
"""Verify the V41 same-direction repeatability circle diagnostic."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from check_circle_diagnostics_v38_v39 import (
    signed_area,
    verify_path,
)


ROOT = Path(__file__).resolve().parents[1]
TEST_ID = "PAPER_A4_CIRCLE_DIRECTION_REPEAT_D18_GCODE_V41"
BUILD_ID = "PAPER_A4_CONTINUOUS_QUEUE_SAFE_HOME_GCODE_V27"
MOVE_RE = re.compile(
    r"^G([01]) X(-?\d+(?:\.\d+)?) Y(-?\d+(?:\.\d+)?)$"
)


def load() -> tuple[list[str], dict, str]:
    gcode_path = ROOT / "gcode" / f"{TEST_ID}.gcode"
    manifest_path = ROOT / "gcode" / f"{TEST_ID}.json"
    text = gcode_path.read_text(encoding="ascii")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return lines, manifest, text


def strokes(
    lines: list[str],
) -> list[list[tuple[float, float]]]:
    result: list[list[tuple[float, float]]] = []
    rapid: tuple[float, float] | None = None
    current: list[tuple[float, float]] | None = None
    pen_down = False
    for line in lines:
        match = MOVE_RE.match(line)
        if match and match.group(1) == "0":
            rapid = (float(match.group(2)), float(match.group(3)))
        elif line == "M3":
            assert not pen_down and rapid is not None
            pen_down = True
            current = [rapid]
        elif line == "M5":
            if pen_down:
                assert current is not None
                result.append(current)
            pen_down = False
            current = None
        elif match and pen_down:
            assert match.group(1) == "1"
            assert current is not None
            current.append(
                (float(match.group(2)), float(match.group(3)))
            )
    assert not pen_down
    return result


def main() -> None:
    lines, manifest, text = load()
    assert manifest["test_id"] == TEST_ID
    assert manifest["required_firmware"] == BUILD_ID
    assert manifest["firmware_paper_map_enabled"] is False
    assert manifest["diameter_mm"] == 18.0
    assert manifest["segments_per_circle"] == 72
    assert hashlib.sha256(text.encode("ascii")).hexdigest() == manifest[
        "gcode_sha256"
    ]

    circle_strokes = strokes(lines)
    assert len(circle_strokes) == 6
    assert all(len(stroke) == 73 for stroke in circle_strokes)
    expected_directions = ("CW", "CW", "CCW", "CCW", "CW", "CCW")
    stroke_index = 0
    for group in manifest["groups"]:
        center = tuple(group["command_user_center_mm"])
        assert len(group["passes"]) == 2
        group_strokes = circle_strokes[stroke_index : stroke_index + 2]
        for pass_record, stroke, expected_direction in zip(
            group["passes"],
            group_strokes,
            expected_directions[stroke_index : stroke_index + 2],
        ):
            assert pass_record["direction"] == expected_direction
            assert math.dist(stroke[0], stroke[-1]) < 0.001
            radii = [
                math.hypot(point[0] - center[0], point[1] - center[1])
                for point in stroke
            ]
            assert max(abs(radius - 9.0) for radius in radii) < 0.001
            area = signed_area(center, stroke)
            if expected_direction == "CW":
                assert area < 0.0
            else:
                assert area > 0.0
        assert sorted(group_strokes[0]) == sorted(group_strokes[1])
        stroke_index += 2

    safe_samples, quantized_error = verify_path(lines)
    assert quantized_error < 0.10
    assert all(
        25.0 <= group["nominal_paper_center_mm"][0] - 9.0
        and group["nominal_paper_center_mm"][0] + 9.0 <= 185.0
        and 0.0 <= group["nominal_paper_center_mm"][1] - 9.0
        and group["nominal_paper_center_mm"][1] + 9.0 <= 240.333333
        for group in manifest["groups"]
    )
    print(
        "PASS: V41 groups=3 circles=6 "
        "directions=CW,CW,CCW,CCW,CW,CCW "
        "same_direction_repeat_groups=2 overlay_group=1 "
        "segments_per_circle=72 tangent_preload=4mm "
        f"safe_samples={safe_samples} "
        f"quantized_error_max={quantized_error:.4f}mm"
    )


if __name__ == "__main__":
    main()
