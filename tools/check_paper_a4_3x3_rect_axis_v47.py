#!/usr/bin/env python3
"""Verify the V47 nine-zone mapped rectangle test."""

from __future__ import annotations

import hashlib
import json
import math
import re

import generate_paper_a4_3x3_rect_axis_v47 as variant
from check_circle_diagnostics_v38_v39 import verify_path
from generate_paper_a4_map_vs_cartesian_circle_v36 import (
    mapped,
    mapping_model,
)


MOVE_RE = re.compile(
    r"^G([01]) X(-?\d+(?:\.\d+)?) Y(-?\d+(?:\.\d+)?)$"
)
MAP_COEFFICIENTS, MAP_TOTAL_DELTA = mapping_model()


def independent_map(point: tuple[float, float]) -> tuple[float, float]:
    result = mapped(point, MAP_COEFFICIENTS, MAP_TOTAL_DELTA)
    return float(result[0]), float(result[1])


def drawn_strokes(
    lines: tuple[str, ...],
) -> tuple[tuple[tuple[float, float], ...], ...]:
    strokes = []
    rapid = None
    current = None
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
                strokes.append(tuple(current))
            pen_down = False
            current = None
        elif match and pen_down:
            assert match.group(1) == "1"
            assert current is not None
            current.append(
                (float(match.group(2)), float(match.group(3)))
            )
    assert not pen_down
    return tuple(strokes)


def main() -> None:
    plan = variant.build_plan()
    expected_lines = variant.gcode_lines(plan)
    text = variant.GCODE_PATH.read_text(encoding="ascii")
    actual_lines = tuple(text.splitlines())
    assert actual_lines == expected_lines
    manifest = json.loads(
        variant.MANIFEST_PATH.read_text(encoding="utf-8")
    )
    assert manifest["id"] == variant.TEST_ID
    assert manifest["required_firmware"] == variant.BUILD_ID
    assert manifest["blank_a4_required"] is True
    assert manifest["coordinate_contract"][
        "firmware_paper_map_enabled"
    ] is False
    assert manifest["coordinate_contract"][
        "offline_pointwise_paper_to_user_map_enabled"
    ] is True
    assert manifest["rectangle"]["width_mm"] == 30.0
    assert manifest["rectangle"]["height_mm"] == 20.0
    assert manifest["rectangle"]["edge_order"] == [
        "+X",
        "+Y",
        "-X",
        "-Y",
    ]
    assert len(manifest["zones"]) == len(plan) == 9
    assert hashlib.sha256(text.encode("ascii")).hexdigest() == manifest[
        "gcode"
    ]["sha256"]

    serial_header = (
        variant.ROOT / "TASK" / "gcode_serial.h"
    ).read_text(encoding="utf-8")
    motion_header = (
        variant.ROOT / "APP" / "Inc" / "app_writer_motion.h"
    ).read_text(encoding="utf-8")
    assert f'"{variant.BUILD_ID}"' in serial_header
    assert "#define GCODE_SERIAL_PAPER_MAP_ENABLE         (0u)" in (
        serial_header
    )
    assert (
        motion_header.count(
            "#define APP_WRITER_DIRECTION_COMP_ENABLE     (0u)"
        )
        >= 1
    )

    for record in plan:
        paper_points = record["paper_points_mm"]
        user_points = record["user_points_mm"]
        assert len(paper_points) == len(user_points) == 101
        assert math.dist(paper_points[0], paper_points[-1]) < 1.0e-9
        assert all(
            math.dist(start, end) <= variant.PAPER_STEP_MM + 1.0e-9
            for start, end in zip(paper_points, paper_points[1:])
        )
        corners = (
            paper_points[0],
            paper_points[30],
            paper_points[50],
            paper_points[80],
            paper_points[100],
        )
        assert math.dist(corners[0], corners[1]) == 30.0
        assert math.dist(corners[1], corners[2]) == 20.0
        assert math.dist(corners[2], corners[3]) == 30.0
        assert math.dist(corners[3], corners[4]) == 20.0
        assert corners[1][0] > corners[0][0]
        assert corners[2][1] > corners[1][1]
        assert corners[3][0] < corners[2][0]
        assert corners[4][1] < corners[3][1]
        for paper_point, user_point in zip(paper_points, user_points):
            assert math.dist(
                independent_map(paper_point), user_point
            ) < 1.0e-9

    strokes = drawn_strokes(actual_lines)
    assert len(strokes) == 9
    assert all(len(stroke) == 101 for stroke in strokes)
    for stroke, record in zip(strokes, plan):
        assert all(
            math.dist(actual, expected) < 0.001
            for actual, expected in zip(
                stroke, record["user_points_mm"]
            )
        )

    commands = [
        line for line in actual_lines if line and not line.startswith(";")
    ]
    g0_count = sum(line.startswith("G0 ") for line in commands)
    g1_count = sum(line.startswith("G1 ") for line in commands)
    assert g0_count == 18
    assert g1_count == 900
    assert commands.count("M3") == 9
    assert commands.count("M5") == 10

    safe_samples, quantized_error = verify_path(list(actual_lines))
    assert quantized_error < 0.10
    print(
        "PASS: V47 zones=9 layout=3x3 rectangles=9 "
        "paper_size=30x20mm direction=+X,+Y,-X,-Y "
        f"G0={g0_count} G1={g1_count} paper_step_max=1mm "
        "paper_map=OFF offline_pointwise_map=ON "
        f"safe_samples={safe_samples} "
        f"quantized_error_max={quantized_error:.4f}mm"
    )


if __name__ == "__main__":
    main()
