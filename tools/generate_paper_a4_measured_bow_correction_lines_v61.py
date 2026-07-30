#!/usr/bin/env python3
"""Generate V61 lines with temporary measured S-bow compensation."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import generate_paper_a4_top_left_song_12mm_v43 as shared
from check_workspace_yshift15_v28 import (
    BUILD_ID,
    SHIFT_X_MM,
    SHIFT_Y_MM,
    joint_margin,
)
from generate_paper_a4_3x3_baseonly_direction_v49 import map_base_only
from generate_paper_a4_full_width_square_spiral_v59 import home_user


ROOT = Path(__file__).resolve().parents[1]
TEST_ID = "PAPER_A4_MEASURED_S_BOW_CORRECTED_XY_LINES_F300_GCODE_V61"
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"

FEED_MM_MIN = 300
TARGET_SUBDIVISION_MM = 0.5
X_SCALE_OBSERVED = 165.0 / 160.0
X_SCALE_REFERENCE_MM = 105.0

# Distance from the top/start of a 160 mm downward line, followed by observed
# X error. Negative is left of the hand-drawn reference; positive is right.
VERTICAL_DISTANCE_DOWN_MM = np.array((0.0, 7.0, 55.0, 125.0, 160.0))
VERTICAL_X_ERROR_MM = np.array((0.0, 0.0, -2.0, 0.0, 4.0))

# Distance from the left/start of a 160 mm rightward line, followed by
# observed Y error. Negative is below the reference; positive is above.
HORIZONTAL_DISTANCE_RIGHT_MM = np.array((0.0, 40.0, 92.5, 160.0))
HORIZONTAL_Y_ERROR_MM = np.array((0.0, -2.0, 0.0, 4.0))

TARGET_STROKES = (
    ("H_CORRECTED_UPPER", (25.0, 230.0), (185.0, 230.0)),
    ("H_CORRECTED_LOWER", (25.0, 215.0), (185.0, 215.0)),
    ("V_CORRECTED_LEFT", (155.0, 235.0), (155.0, 75.0)),
    ("V_CORRECTED_RIGHT", (170.0, 235.0), (170.0, 75.0)),
)


def pchip_slopes(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Fritsch-Carlson PCHIP slopes without a SciPy dependency."""
    h = np.diff(x)
    delta = np.diff(y) / h
    slopes = np.zeros_like(y)
    for index in range(1, len(y) - 1):
        before = delta[index - 1]
        after = delta[index]
        if before == 0.0 or after == 0.0 or before * after < 0.0:
            slopes[index] = 0.0
        else:
            weight_before = 2.0 * h[index] + h[index - 1]
            weight_after = h[index] + 2.0 * h[index - 1]
            slopes[index] = (
                weight_before + weight_after
            ) / (
                weight_before / before + weight_after / after
            )

    def endpoint(
        h0: float,
        h1: float,
        delta0: float,
        delta1: float,
    ) -> float:
        value = (
            (2.0 * h0 + h1) * delta0 - h0 * delta1
        ) / (h0 + h1)
        if value * delta0 <= 0.0:
            return 0.0
        if delta0 * delta1 < 0.0 and abs(value) > abs(3.0 * delta0):
            return 3.0 * delta0
        return value

    slopes[0] = endpoint(h[0], h[1], delta[0], delta[1])
    slopes[-1] = endpoint(
        h[-1],
        h[-2],
        delta[-1],
        delta[-2],
    )
    return slopes


def pchip_value(
    value: float,
    knots: np.ndarray,
    samples: np.ndarray,
    slopes: np.ndarray,
) -> float:
    value = float(np.clip(value, knots[0], knots[-1]))
    index = min(
        max(int(np.searchsorted(knots, value, side="right")) - 1, 0),
        len(knots) - 2,
    )
    width = knots[index + 1] - knots[index]
    t = (value - knots[index]) / width
    h00 = 2.0 * t**3 - 3.0 * t**2 + 1.0
    h10 = t**3 - 2.0 * t**2 + t
    h01 = -2.0 * t**3 + 3.0 * t**2
    h11 = t**3 - t**2
    return float(
        h00 * samples[index]
        + h10 * width * slopes[index]
        + h01 * samples[index + 1]
        + h11 * width * slopes[index + 1]
    )


VERTICAL_SLOPES = pchip_slopes(
    VERTICAL_DISTANCE_DOWN_MM,
    VERTICAL_X_ERROR_MM,
)
HORIZONTAL_SLOPES = pchip_slopes(
    HORIZONTAL_DISTANCE_RIGHT_MM,
    HORIZONTAL_Y_ERROR_MM,
)


def target_points(
    start: tuple[float, float],
    end: tuple[float, float],
) -> tuple[tuple[float, float], ...]:
    length = math.dist(start, end)
    count = max(1, math.ceil(length / TARGET_SUBDIVISION_MM))
    return tuple(
        (
            start[0] + (end[0] - start[0]) * index / count,
            start[1] + (end[1] - start[1]) * index / count,
        )
        for index in range(count + 1)
    )


def measured_errors(
    target: tuple[float, float],
) -> tuple[float, float]:
    distance_down = 235.0 - target[1]
    distance_right = target[0] - 25.0
    x_error = pchip_value(
        distance_down,
        VERTICAL_DISTANCE_DOWN_MM,
        VERTICAL_X_ERROR_MM,
        VERTICAL_SLOPES,
    )
    y_error = pchip_value(
        distance_right,
        HORIZONTAL_DISTANCE_RIGHT_MM,
        HORIZONTAL_Y_ERROR_MM,
        HORIZONTAL_SLOPES,
    )
    return x_error, y_error


def prewarp_physical(
    target: tuple[float, float],
) -> tuple[float, float]:
    x_error, y_error = measured_errors(target)
    scaled_x = X_SCALE_REFERENCE_MM + (
        target[0] - X_SCALE_REFERENCE_MM
    ) / X_SCALE_OBSERVED
    return scaled_x - x_error, target[1] - y_error


def build_plan() -> tuple[dict, ...]:
    records = []
    for stroke_id, start, end in TARGET_STROKES:
        targets = target_points(start, end)
        prewarped_physical = tuple(prewarp_physical(p) for p in targets)
        logical_points = tuple(
            (point[0] - SHIFT_X_MM, point[1] - SHIFT_Y_MM)
            for point in prewarped_physical
        )
        for point in logical_points:
            if not (
                20.0 <= point[0] <= 190.0
                and shared.PAPER_Y_MIN_MM
                <= point[1]
                <= shared.PAPER_Y_MAX_MM
            ):
                raise AssertionError(f"{stroke_id} out of bounds: {point}")
        records.append(
            {
                "id": stroke_id,
                "target_start_physical_mm": start,
                "target_end_physical_mm": end,
                "target_points_physical_mm": targets,
                "prewarped_points_physical_mm": prewarped_physical,
                "logical_points_mm": logical_points,
                "user_points_mm": tuple(
                    map_base_only(point) for point in logical_points
                ),
            }
        )
    return tuple(records)


def gcode_lines(plan: tuple[dict, ...]) -> tuple[str, ...]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware_required={BUILD_ID}",
        "; WARNING=DO_NOT_SEND_TO_V27_OR_OLDER",
        "; temporary_validation_only=YES firmware_mapping_unchanged=YES",
        "; correction=MEASURED_SEPARABLE_PCHIP_S_BOW_PLUS_X_SCALE",
        "; vertical_error_knots_down_mm=0,7,55,125,160",
        "; vertical_x_error_mm=0,0,-2,0,+4",
        "; horizontal_error_knots_right_mm=0,40,92.5,160",
        "; horizontal_y_error_mm=0,-2,0,+4",
        "; observed_x_scale=165/160",
        "; map=BASE_QUADRATIC_ONLY_THEN_TEMPORARY_PREWARP",
        "; firmware_paper_map=DISABLED firmware_global_y_shift=+15mm",
        "G21",
        "G90",
        "G94",
        f"F{FEED_MM_MIN}",
        "S1000",
        "M5",
    ]
    for record in plan:
        points = record["user_points_mm"]
        lines.extend(
            (
                f"; ===== {record['id']} =====",
                f"G0 X{points[0][0]:.3f} Y{points[0][1]:.3f}",
                "M3",
            )
        )
        lines.extend(
            f"G1 X{point[0]:.3f} Y{point[1]:.3f}"
            for point in points[1:]
        )
        lines.append("M5")
    lines.append("M5")
    return tuple(lines)


def audit(plan: tuple[dict, ...]) -> dict:
    previous = home_user()
    worst = (float("inf"), (0.0, 0.0), (0.0, 0.0, 0.0))
    sample_count = 0
    for record in plan:
        for point in record["user_points_mm"]:
            target = (
                point[0] + SHIFT_X_MM,
                point[1] + SHIFT_Y_MM,
            )
            count = max(1, math.ceil(math.dist(previous, target)))
            for index in range(1, count + 1):
                ratio = index / count
                sample = (
                    previous[0] + (target[0] - previous[0]) * ratio,
                    previous[1] + (target[1] - previous[1]) * ratio,
                )
                margin, angles = joint_margin(sample)
                if margin < worst[0]:
                    worst = (margin, sample, angles)
                sample_count += 1
            previous = target
    if worst[0] < -0.001:
        raise AssertionError(f"V61 violates joint limits: {worst}")
    return {
        "path_sample_count": sample_count,
        "minimum_joint_margin_deg": worst[0],
        "minimum_at_shifted_user_mm": list(worst[1]),
        "minimum_at_angles_deg": list(worst[2]),
    }


def write_preview(plan: tuple[dict, ...]) -> None:
    width = round(shared.A4_WIDTH_MM * 4.0) + 1
    height = round(shared.A4_HEIGHT_MM * 4.0) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (0, 0, width - 1, height - 1),
        outline=(25, 25, 25),
        width=3,
    )
    for record in plan:
        draw.line(
            [
                shared.preview_xy(point)
                for point in record["target_points_physical_mm"]
            ],
            fill=(35, 125, 65),
            width=3,
        )
        draw.line(
            [
                shared.preview_xy(point)
                for point in record["prewarped_points_physical_mm"]
            ],
            fill=(205, 55, 45),
            width=2,
        )
    draw.text(
        (20, 18),
        "V61 green=desired straight output, red=temporary prewarp",
        fill=(30, 30, 30),
        font=shared.label_font(17),
    )
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def write_manifest(
    plan: tuple[dict, ...],
    lines: tuple[str, ...],
    safety: dict,
) -> None:
    text = "\n".join(lines) + "\n"
    dense_down = np.linspace(0.0, 160.0, 641)
    dense_right = np.linspace(0.0, 160.0, 641)
    vertical_curve = [
        pchip_value(
            value,
            VERTICAL_DISTANCE_DOWN_MM,
            VERTICAL_X_ERROR_MM,
            VERTICAL_SLOPES,
        )
        for value in dense_down
    ]
    horizontal_curve = [
        pchip_value(
            value,
            HORIZONTAL_DISTANCE_RIGHT_MM,
            HORIZONTAL_Y_ERROR_MM,
            HORIZONTAL_SLOPES,
        )
        for value in dense_right
    ]
    manifest = {
        "id": TEST_ID,
        "required_firmware": BUILD_ID,
        "temporary_validation_only": True,
        "measurement_model": {
            "vertical": {
                "distance_down_mm": VERTICAL_DISTANCE_DOWN_MM.tolist(),
                "observed_x_error_mm": VERTICAL_X_ERROR_MM.tolist(),
                "interpolation": "PCHIP",
                "dense_error_range_mm": [
                    min(vertical_curve),
                    max(vertical_curve),
                ],
            },
            "horizontal": {
                "distance_right_mm": (
                    HORIZONTAL_DISTANCE_RIGHT_MM.tolist()
                ),
                "observed_y_error_mm": HORIZONTAL_Y_ERROR_MM.tolist(),
                "interpolation": "PCHIP",
                "dense_error_range_mm": [
                    min(horizontal_curve),
                    max(horizontal_curve),
                ],
            },
            "observed_x_scale": X_SCALE_OBSERVED,
            "x_scale_reference_mm": X_SCALE_REFERENCE_MM,
        },
        "strokes": [
            {
                "id": record["id"],
                "target_start_physical_mm": list(
                    record["target_start_physical_mm"]
                ),
                "target_end_physical_mm": list(
                    record["target_end_physical_mm"]
                ),
                "prewarped_physical_bounds_mm": [
                    min(p[0] for p in record["prewarped_points_physical_mm"]),
                    min(p[1] for p in record["prewarped_points_physical_mm"]),
                    max(p[0] for p in record["prewarped_points_physical_mm"]),
                    max(p[1] for p in record["prewarped_points_physical_mm"]),
                ],
            }
            for record in plan
        ],
        "motion": {
            "feed_mm_min": FEED_MM_MIN,
            "target_subdivision_max_mm": TARGET_SUBDIVISION_MM,
            "stroke_count": len(plan),
            "g1_count": sum(
                len(record["user_points_mm"]) - 1 for record in plan
            ),
        },
        "safety": safety,
        "gcode": {
            "file": GCODE_PATH.name,
            "line_count": len(lines),
            "sha256": hashlib.sha256(text.encode("ascii")).hexdigest(),
        },
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    plan = build_plan()
    safety = audit(plan)
    lines = gcode_lines(plan)
    GCODE_PATH.write_text(
        "\n".join(lines) + "\n",
        encoding="ascii",
        newline="\n",
    )
    write_preview(plan)
    write_manifest(plan, lines, safety)
    print(
        "measured_bow_correction_lines_v61=PASS "
        f"strokes={len(plan)} "
        f"G1={sum(len(r['user_points_mm']) - 1 for r in plan)} "
        f"min_joint_margin={safety['minimum_joint_margin_deg']:.6f}deg"
    )
    print(GCODE_PATH)
    print(PREVIEW_PATH)
    print(MANIFEST_PATH)


if __name__ == "__main__":
    main()
