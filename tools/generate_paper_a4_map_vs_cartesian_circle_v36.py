#!/usr/bin/env python3
"""Generate the V36 paper-map versus Cartesian-circle isolation test."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from check_paper_a4_center_yong_v26 import paper_to_user
from derive_grid9_limited_y_v15 import calibration_arrays, fit
from derive_paper_a4_4x7_grid_v25 import derive
import generate_paper_a4_zhang_jia_le_v31 as base


ROOT = Path(__file__).resolve().parents[1]
GCODE_PATH = (
    ROOT
    / "gcode"
    / "PAPER_A4_MAP_VS_CARTESIAN_CIRCLE_D18_CW_GCODE_V36.gcode"
)
MANIFEST_PATH = (
    ROOT
    / "gcode"
    / "PAPER_A4_MAP_VS_CARTESIAN_CIRCLE_D18_CW_GCODE_V36.json"
)
PREVIEW_PATH = (
    ROOT
    / "docs"
    / "diagnostics"
    / "PAPER_A4_MAP_VS_CARTESIAN_CIRCLE_D18_CW_GCODE_V36_PREVIEW.png"
)

RADIUS_MM = 9.0
DIAMETER_MM = 2.0 * RADIUS_MM
SEGMENTS_PER_CIRCLE = 72
COLUMN_CENTERS_MM = (52.0, 105.0, 158.0)
ROW_CENTERS_MM = (65.0, 220.0)
PAIR_OFFSET_X_MM = 11.0
TANGENT_APPROACH_USER_MM = 6.0
FEED_MM_MIN = 180
PAPER_X_MIN_MM = 25.0
PAPER_X_MAX_MM = 185.0
PAPER_Y_MIN_MM = 20.0
PAPER_Y_MAX_MM = 240.333
INVERSE_TOLERANCE_MM = 1.0e-9
INVERSE_MAX_ITERATIONS = 20
JACOBIAN_STEP_MM = 0.001

MODE_PAPER_CIRCLE = "A_PAPER_CIRCLE"
MODE_CARTESIAN_CIRCLE = "B_CARTESIAN_CIRCLE"


@dataclass(frozen=True)
class CircleRecord:
    zone_id: str
    row_name: str
    column_name: str
    mode: str
    nominal_paper_center_mm: tuple[float, float]
    target_user_center_mm: tuple[float, float]
    source_approach_mm: tuple[float, float]
    source_points_mm: tuple[tuple[float, float], ...]
    target_user_points_mm: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class CircleLayout:
    circles: tuple[CircleRecord, ...]
    source_bounds_mm: tuple[float, float, float, float]


def mapping_model():
    paper_calibration, command_calibration, _ = calibration_arrays()
    coefficients = fit(paper_calibration, command_calibration, 2)
    _, _, total_delta, _ = derive()
    return coefficients, total_delta


def mapped(
    paper_point: tuple[float, float],
    coefficients: np.ndarray,
    total_delta: np.ndarray,
) -> np.ndarray:
    return np.asarray(
        paper_to_user(paper_point, coefficients, total_delta),
        dtype=float,
    )


def inverse_map(
    target_user: np.ndarray,
    initial_paper: np.ndarray,
    coefficients: np.ndarray,
    total_delta: np.ndarray,
) -> tuple[float, float]:
    paper = np.asarray(initial_paper, dtype=float).copy()
    for _ in range(INVERSE_MAX_ITERATIONS):
        residual = mapped(tuple(paper), coefficients, total_delta) - target_user
        if float(np.linalg.norm(residual)) <= INVERSE_TOLERANCE_MM:
            break
        dx = np.array((JACOBIAN_STEP_MM, 0.0))
        dy = np.array((0.0, JACOBIAN_STEP_MM))
        jacobian = np.column_stack(
            (
                (
                    mapped(tuple(paper + dx), coefficients, total_delta)
                    - mapped(tuple(paper - dx), coefficients, total_delta)
                )
                / (2.0 * JACOBIAN_STEP_MM),
                (
                    mapped(tuple(paper + dy), coefficients, total_delta)
                    - mapped(tuple(paper - dy), coefficients, total_delta)
                )
                / (2.0 * JACOBIAN_STEP_MM),
            )
        )
        paper -= np.linalg.solve(jacobian, residual)
    final_error = float(
        np.linalg.norm(
            mapped(tuple(paper), coefficients, total_delta) - target_user
        )
    )
    if final_error > INVERSE_TOLERANCE_MM:
        raise AssertionError(
            f"paper-map inverse failed: residual={final_error:.12f} mm"
        )
    if not (
        PAPER_X_MIN_MM <= paper[0] <= PAPER_X_MAX_MM
        and PAPER_Y_MIN_MM <= paper[1] <= PAPER_Y_MAX_MM
    ):
        raise AssertionError(
            f"paper-map inverse left calibrated bounds: {tuple(paper)}"
        )
    return float(paper[0]), float(paper[1])


def cw_circle(
    center: tuple[float, float],
) -> tuple[tuple[float, float], ...]:
    return tuple(
        (
            center[0]
            + RADIUS_MM
            * math.cos(
                math.pi / 2.0
                - 2.0 * math.pi * index / SEGMENTS_PER_CIRCLE
            ),
            center[1]
            + RADIUS_MM
            * math.sin(
                math.pi / 2.0
                - 2.0 * math.pi * index / SEGMENTS_PER_CIRCLE
            ),
        )
        for index in range(SEGMENTS_PER_CIRCLE + 1)
    )


def tangent_approach_user(
    points: tuple[tuple[float, float], ...],
) -> np.ndarray:
    start = np.asarray(points[0], dtype=float)
    next_point = np.asarray(points[1], dtype=float)
    direction = next_point - start
    direction /= np.linalg.norm(direction)
    return start - direction * TANGENT_APPROACH_USER_MM


def paper_circle(
    zone_id: str,
    row_name: str,
    column_name: str,
    center: tuple[float, float],
    coefficients: np.ndarray,
    total_delta: np.ndarray,
) -> CircleRecord:
    source_points = cw_circle(center)
    target_points = tuple(
        tuple(mapped(point, coefficients, total_delta))
        for point in source_points
    )
    target_approach = tangent_approach_user(target_points)
    source_approach = inverse_map(
        target_approach,
        np.asarray(source_points[0], dtype=float),
        coefficients,
        total_delta,
    )
    return CircleRecord(
        zone_id,
        row_name,
        column_name,
        MODE_PAPER_CIRCLE,
        center,
        tuple(mapped(center, coefficients, total_delta)),
        source_approach,
        source_points,
        target_points,
    )


def cartesian_circle(
    zone_id: str,
    row_name: str,
    column_name: str,
    nominal_center: tuple[float, float],
    coefficients: np.ndarray,
    total_delta: np.ndarray,
) -> CircleRecord:
    target_center = tuple(
        mapped(nominal_center, coefficients, total_delta)
    )
    target_points = cw_circle(target_center)
    source_points = tuple(
        inverse_map(
            np.asarray(target_point, dtype=float),
            np.asarray(nominal_center, dtype=float),
            coefficients,
            total_delta,
        )
        for target_point in target_points
    )
    target_approach = tangent_approach_user(target_points)
    source_approach = inverse_map(
        target_approach,
        np.asarray(source_points[0], dtype=float),
        coefficients,
        total_delta,
    )
    return CircleRecord(
        zone_id,
        row_name,
        column_name,
        MODE_CARTESIAN_CIRCLE,
        nominal_center,
        target_center,
        source_approach,
        source_points,
        target_points,
    )


def build_layout() -> CircleLayout:
    coefficients, total_delta = mapping_model()
    circles: list[CircleRecord] = []
    for row_name, center_y in zip(("LOWER", "UPPER"), ROW_CENTERS_MM):
        for column_name, zone_center_x in zip(
            ("LEFT", "MIDDLE", "RIGHT"), COLUMN_CENTERS_MM
        ):
            zone_id = f"{row_name}_{column_name}"
            a_center = (zone_center_x - PAIR_OFFSET_X_MM, center_y)
            b_center = (zone_center_x + PAIR_OFFSET_X_MM, center_y)
            circles.append(
                paper_circle(
                    zone_id,
                    row_name,
                    column_name,
                    a_center,
                    coefficients,
                    total_delta,
                )
            )
            circles.append(
                cartesian_circle(
                    zone_id,
                    row_name,
                    column_name,
                    b_center,
                    coefficients,
                    total_delta,
                )
            )

    source_points = [
        point
        for circle in circles
        for point in (circle.source_approach_mm, *circle.source_points_mm)
    ]
    bounds = (
        min(point[0] for point in source_points),
        min(point[1] for point in source_points),
        max(point[0] for point in source_points),
        max(point[1] for point in source_points),
    )
    if not (
        PAPER_X_MIN_MM <= bounds[0] <= bounds[2] <= PAPER_X_MAX_MM
        and PAPER_Y_MIN_MM <= bounds[1] <= bounds[3] <= PAPER_Y_MAX_MM
    ):
        raise AssertionError(f"V36 source bounds invalid: {bounds}")
    return CircleLayout(tuple(circles), bounds)


def gcode_lines(layout: CircleLayout) -> tuple[str, ...]:
    lines = ["G21", "G90", "G94", "M5", f"F{FEED_MM_MIN}"]
    for circle in layout.circles:
        lines.append(
            "G0 "
            f"X{circle.source_approach_mm[0]:.6f} "
            f"Y{circle.source_approach_mm[1]:.6f}"
        )
        lines.append(
            "G0 "
            f"X{circle.source_points_mm[0][0]:.6f} "
            f"Y{circle.source_points_mm[0][1]:.6f}"
        )
        lines.append("M3")
        lines.extend(
            f"G1 X{point[0]:.6f} Y{point[1]:.6f}"
            for point in circle.source_points_mm[1:]
        )
        lines.append("M5")
    return tuple(lines)


def write_preview(layout: CircleLayout) -> None:
    width = round(base.A4_WIDTH_MM * base.PREVIEW_PIXELS_PER_MM) + 1
    height = round(base.A4_HEIGHT_MM * base.PREVIEW_PIXELS_PER_MM) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (0, 0, width - 1, height - 1),
        outline=(25, 25, 25),
        width=3,
    )
    draw.rectangle(
        (
            *base.preview_xy((PAPER_X_MIN_MM, PAPER_Y_MAX_MM)),
            *base.preview_xy((PAPER_X_MAX_MM, PAPER_Y_MIN_MM)),
        ),
        outline=(130, 160, 195),
        width=2,
    )
    draw.text(
        (20, 16),
        "V36 MAP A/B: LEFT=A PAPER CIRCLE, RIGHT=B CARTESIAN CIRCLE",
        fill=(20, 20, 20),
        font=base.label_font(20),
    )
    draw.text(
        (20, 47),
        "Both: D18 mm, CW, 72 chords, F180. Preview shows G-code source paths.",
        fill=(70, 70, 70),
        font=base.label_font(14),
    )

    for circle in layout.circles:
        color = (
            (195, 55, 45)
            if circle.mode == MODE_PAPER_CIRCLE
            else (30, 105, 190)
        )
        draw.line(
            [base.preview_xy(point) for point in circle.source_points_mm],
            fill=color,
            width=3,
            joint="curve",
        )
        base.draw_dashed_line(
            draw,
            base.preview_xy(circle.source_approach_mm),
            base.preview_xy(circle.source_points_mm[0]),
            (90, 90, 90),
            width=2,
        )
        center_px = base.preview_xy(circle.nominal_paper_center_mm)
        draw.text(
            (center_px[0] - 6, center_px[1] + 29),
            "A" if circle.mode == MODE_PAPER_CIRCLE else "B",
            fill=color,
            font=base.label_font(15),
        )
        start_px = base.preview_xy(circle.source_points_mm[0])
        draw.ellipse(
            (
                start_px[0] - 3,
                start_px[1] - 3,
                start_px[0] + 3,
                start_px[1] + 3,
            ),
            fill=(35, 35, 35),
        )

    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def extent(
    points: tuple[tuple[float, float], ...],
) -> tuple[float, float]:
    data = np.asarray(points, dtype=float)
    return float(np.ptp(data[:, 0])), float(np.ptp(data[:, 1]))


def write_manifest(
    layout: CircleLayout,
    lines: tuple[str, ...],
) -> None:
    records = []
    for circle in layout.circles:
        source_width, source_height = extent(circle.source_points_mm)
        target_width, target_height = extent(circle.target_user_points_mm)
        records.append(
            {
                "zone_id": circle.zone_id,
                "mode": circle.mode,
                "nominal_paper_center_mm": list(
                    circle.nominal_paper_center_mm
                ),
                "target_user_center_mm": list(
                    circle.target_user_center_mm
                ),
                "source_extent_mm": [source_width, source_height],
                "target_user_extent_mm": [
                    target_width,
                    target_height,
                ],
            }
        )
    manifest = {
        "id": "PAPER_A4_MAP_VS_CARTESIAN_CIRCLE_D18_CW_GCODE_V36",
        "purpose": (
            "isolate paper-coordinate mapping from Cartesian "
            "kinematics and joint execution"
        ),
        "pair_contract": {
            "left": MODE_PAPER_CIRCLE,
            "right": MODE_CARTESIAN_CIRCLE,
            "direction": "CW",
            "radius_mm": RADIUS_MM,
            "diameter_mm": DIAMETER_MM,
            "segments_per_circle": SEGMENTS_PER_CIRCLE,
            "feed_mm_min": FEED_MM_MIN,
            "tangent_approach_user_mm": TANGENT_APPROACH_USER_MM,
        },
        "layout": {
            "column_centers_mm": list(COLUMN_CENTERS_MM),
            "row_centers_mm": list(ROW_CENTERS_MM),
            "pair_offset_x_mm": PAIR_OFFSET_X_MM,
            "source_bounds_mm": list(layout.source_bounds_mm),
        },
        "circles": records,
        "gcode": {
            "file": GCODE_PATH.name,
            "line_count": len(lines),
            "g0_count": sum(line.startswith("G0 ") for line in lines),
            "g1_count": sum(line.startswith("G1 ") for line in lines),
            "m3_count": lines.count("M3"),
            "m5_count": lines.count("M5"),
            "sha256": hashlib.sha256(
                GCODE_PATH.read_bytes()
            ).hexdigest().upper(),
        },
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    layout = build_layout()
    lines = gcode_lines(layout)
    GCODE_PATH.write_text("\n".join(lines) + "\n", encoding="ascii")
    write_preview(layout)
    write_manifest(layout, lines)
    print(
        "generated_map_vs_cartesian_circle_v36=PASS "
        f"zones={len(layout.circles) // 2} "
        f"circles={len(layout.circles)} "
        f"G1={sum(line.startswith('G1 ') for line in lines)} "
        f"bounds_x={layout.source_bounds_mm[0]:.3f}.."
        f"{layout.source_bounds_mm[2]:.3f} "
        f"bounds_y={layout.source_bounds_mm[1]:.3f}.."
        f"{layout.source_bounds_mm[3]:.3f}"
    )
    print(GCODE_PATH)
    print(PREVIEW_PATH)
    print(MANIFEST_PATH)


if __name__ == "__main__":
    main()
