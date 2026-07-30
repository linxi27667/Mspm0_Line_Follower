#!/usr/bin/env python3
"""Verify the V38 direction overlay and V39 local-scale cross tests."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

from generate_paper_a4_map_vs_cartesian_circle_v36 import (
    mapped,
    mapping_model,
)


ROOT = Path(__file__).resolve().parents[1]
BUILD_ID = "PAPER_A4_CONTINUOUS_QUEUE_SAFE_HOME_GCODE_V27"
OVERLAY_ID = "PAPER_A4_SAME_CENTER_CW_CCW_OVERLAY_D18_GCODE_V38"
CROSS_ID = "PAPER_A4_LEFT_MID_RIGHT_CROSS20_GCODE_V39"
PAPER_CROSS_ID = "PAPER_A4_LEFT_MID_RIGHT_PAPER_AXIS_CROSS20_GCODE_V40"
MOVE_RE = re.compile(
    r"^G([01]) X(-?\d+(?:\.\d+)?) Y(-?\d+(?:\.\d+)?)$"
)

L1_MM = 205.0
L2_MM = 203.0
OFFSET_X_MM = -129.0
OFFSET_Y_MM = 128.0
STAGE1_STEPS_PER_DEG = 40.099216
STAGE2_STEPS_PER_DEG = 40.115790
THETA_MIN_DEG = -0.773082 + 1.0
PSI_MIN_DEG = 134.177381 + 1.0
THETA_MAX_DEG = 135.0
PSI_MAX_DEG = 255.0
MAP_COEFFICIENTS, MAP_TOTAL_DELTA = mapping_model()


def load_case(test_id: str) -> tuple[list[str], dict]:
    gcode = ROOT / "gcode" / f"{test_id}.gcode"
    manifest = ROOT / "gcode" / f"{test_id}.json"
    lines = [
        line.strip()
        for line in gcode.read_text(encoding="ascii").splitlines()
        if line.strip()
    ]
    return lines, json.loads(manifest.read_text(encoding="utf-8"))


def groups(lines: list[str]) -> list[list[tuple[float, float]]]:
    result: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] | None = None
    pen_down = False
    for line in lines:
        if line == "M3":
            assert not pen_down
            pen_down = True
            current = []
        elif line == "M5":
            if pen_down:
                assert current is not None
                result.append(current)
            pen_down = False
            current = None
        else:
            match = MOVE_RE.match(line)
            if match and pen_down:
                assert match.group(1) == "1"
                assert current is not None
                current.append(
                    (float(match.group(2)), float(match.group(3)))
                )
    assert not pen_down
    return result


def full_strokes(
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


def signed_area(
    center: tuple[float, float],
    points: list[tuple[float, float]],
) -> float:
    polygon = [
        (
            points[0][0] - center[0],
            points[0][1] - center[1],
        ),
        *[
            (point[0] - center[0], point[1] - center[1])
            for point in points[1:]
        ],
    ]
    return 0.5 * sum(
        x0 * y1 - x1 * y0
        for (x0, y0), (x1, y1) in zip(
            polygon, polygon[1:] + polygon[:1]
        )
    )


def inverse_user(x_mm: float, y_mm: float) -> tuple[float, float]:
    standard_x = -(x_mm + OFFSET_X_MM)
    standard_y = y_mm + OFFSET_Y_MM
    cos_q2 = (
        standard_x * standard_x
        + standard_y * standard_y
        - L1_MM * L1_MM
        - L2_MM * L2_MM
    ) / (2.0 * L1_MM * L2_MM)
    assert -1.0 <= cos_q2 <= 1.0
    sin_q2 = math.sqrt(max(0.0, 1.0 - cos_q2 * cos_q2))
    theta = math.atan2(
        L1_MM + L2_MM * cos_q2,
        L2_MM * sin_q2,
    ) - math.atan2(standard_x, standard_y)
    psi = theta + math.atan2(sin_q2, cos_q2)
    return math.degrees(theta), math.degrees(psi)


def verify_path(lines: list[str]) -> tuple[int, float]:
    points: list[tuple[float, float]] = []
    for line in lines:
        match = MOVE_RE.match(line)
        if match:
            points.append(
                (float(match.group(2)), float(match.group(3)))
            )
    samples = 0
    max_quantized_error = 0.0
    previous: tuple[float, float] | None = None
    for point in points:
        if previous is None:
            path_points = [point]
        else:
            span = max(
                abs(point[0] - previous[0]),
                abs(point[1] - previous[1]),
            )
            count = max(1, math.ceil(span / 1.0))
            path_points = [
                (
                    previous[0]
                    + (point[0] - previous[0]) * index / count,
                    previous[1]
                    + (point[1] - previous[1]) * index / count,
                )
                for index in range(1, count + 1)
            ]
        for sample in path_points:
            theta, psi = inverse_user(*sample)
            assert THETA_MIN_DEG <= theta <= THETA_MAX_DEG
            assert PSI_MIN_DEG <= psi <= PSI_MAX_DEG
            assert 1.0 <= psi - theta <= 179.0
            theta_q = (
                round(theta * STAGE1_STEPS_PER_DEG)
                / STAGE1_STEPS_PER_DEG
            )
            psi_q = (
                round(psi * STAGE2_STEPS_PER_DEG)
                / STAGE2_STEPS_PER_DEG
            )
            machine_x = (
                -L1_MM * math.cos(math.radians(theta_q))
                -L2_MM * math.cos(math.radians(psi_q))
            )
            machine_y = (
                L1_MM * math.sin(math.radians(theta_q))
                + L2_MM * math.sin(math.radians(psi_q))
            )
            user_q = (
                machine_x - OFFSET_X_MM,
                machine_y - OFFSET_Y_MM,
            )
            max_quantized_error = max(
                max_quantized_error,
                math.hypot(
                    user_q[0] - sample[0],
                    user_q[1] - sample[1],
                ),
            )
            samples += 1
        previous = point
    return samples, max_quantized_error


def main() -> None:
    overlay_lines, overlay_manifest = load_case(OVERLAY_ID)
    cross_lines, cross_manifest = load_case(CROSS_ID)
    paper_cross_lines, paper_cross_manifest = load_case(PAPER_CROSS_ID)

    assert overlay_manifest["required_firmware"] == BUILD_ID
    assert cross_manifest["required_firmware"] == BUILD_ID
    assert paper_cross_manifest["required_firmware"] == BUILD_ID
    assert overlay_manifest["paper_map_enabled"] is False
    assert cross_manifest["paper_map_enabled"] is False
    assert (
        paper_cross_manifest["firmware_paper_map_enabled"] is False
    )
    assert (
        paper_cross_manifest[
            "offline_pointwise_paper_to_user_map_enabled"
        ]
        is True
    )

    overlay_groups = groups(overlay_lines)
    assert len(overlay_groups) == 2
    assert all(len(group) == 72 for group in overlay_groups)
    center = tuple(overlay_manifest["command_user_center_mm"])
    for group in overlay_groups:
        radii = [
            math.hypot(point[0] - center[0], point[1] - center[1])
            for point in group
        ]
        assert max(abs(radius - 9.0) for radius in radii) < 0.001
    assert signed_area(center, overlay_groups[0]) < 0.0
    assert signed_area(center, overlay_groups[1]) > 0.0
    assert sorted(overlay_groups[0]) == sorted(overlay_groups[1])

    cross_groups = groups(cross_lines)
    assert len(cross_groups) == 6
    assert all(len(group) == 1 for group in cross_groups)
    for record in cross_manifest["crosses"]:
        horizontal = record["horizontal_user_mm"]
        vertical = record["vertical_user_mm"]
        assert math.isclose(
            math.dist(horizontal[0], horizontal[1]),
            20.0,
            abs_tol=1.0e-9,
        )
        assert math.isclose(
            math.dist(vertical[0], vertical[1]),
            20.0,
            abs_tol=1.0e-9,
        )
        assert math.isclose(
            horizontal[0][1], horizontal[1][1], abs_tol=1.0e-9
        )
        assert math.isclose(
            vertical[0][0], vertical[1][0], abs_tol=1.0e-9
        )

    paper_strokes = full_strokes(paper_cross_lines)
    assert len(paper_strokes) == 6
    assert all(len(stroke) == 21 for stroke in paper_strokes)
    stroke_index = 0
    for record in paper_cross_manifest["crosses"]:
        for stroke_record in record["strokes"]:
            paper_points = stroke_record["paper_points_mm"]
            user_points = stroke_record["command_user_points_mm"]
            assert len(paper_points) == len(user_points) == 21
            if stroke_record["axis"] == "HORIZONTAL":
                assert all(
                    math.isclose(
                        point[1], paper_points[0][1], abs_tol=1.0e-9
                    )
                    for point in paper_points
                )
            else:
                assert stroke_record["axis"] == "VERTICAL"
                assert all(
                    math.isclose(
                        point[0], paper_points[0][0], abs_tol=1.0e-9
                    )
                    for point in paper_points
                )
            assert math.isclose(
                math.dist(paper_points[0], paper_points[-1]),
                20.0,
                abs_tol=1.0e-9,
            )
            for paper_point, user_point, gcode_point in zip(
                paper_points,
                user_points,
                paper_strokes[stroke_index],
            ):
                expected = mapped(
                    tuple(paper_point),
                    MAP_COEFFICIENTS,
                    MAP_TOTAL_DELTA,
                )
                assert math.hypot(
                    float(expected[0]) - user_point[0],
                    float(expected[1]) - user_point[1],
                ) < 1.0e-9
                assert math.hypot(
                    user_point[0] - gcode_point[0],
                    user_point[1] - gcode_point[1],
                ) < 0.001
            stroke_index += 1

    overlay_samples, overlay_error = verify_path(overlay_lines)
    cross_samples, cross_error = verify_path(cross_lines)
    paper_cross_samples, paper_cross_error = verify_path(
        paper_cross_lines
    )
    assert max(
        overlay_error, cross_error, paper_cross_error
    ) < 0.10

    print(
        "PASS: V38 overlay circles=2 directions=CW+CCW "
        "same_center=1 same_start=1 segments=72 "
        f"safe_samples={overlay_samples} "
        f"quantized_error_max={overlay_error:.4f}mm"
    )
    print(
        "PASS: V39 raw-user-basis crosses=3 strokes=6 "
        "raw_user_length=20mm directions=+X,+Y "
        f"safe_samples={cross_samples} "
        f"quantized_error_max={cross_error:.4f}mm"
    )
    print(
        "PASS: V40 paper-axis crosses=3 strokes=6 "
        "paper_length=20mm segments/stroke=20 pointwise_map=ON "
        f"safe_samples={paper_cross_samples} "
        f"quantized_error_max={paper_cross_error:.4f}mm"
    )


if __name__ == "__main__":
    main()
