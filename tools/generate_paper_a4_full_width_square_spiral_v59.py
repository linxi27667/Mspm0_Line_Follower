#!/usr/bin/env python3
"""Generate one full-width, top-aligned square spiral for V28 calibration."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

import generate_paper_a4_top_left_song_12mm_v43 as shared
from check_workspace_yshift15_v28 import (
    BUILD_ID,
    L1_MM,
    L2_MM,
    OFFSET_X_MM,
    OFFSET_Y_MM,
    PSI_MIN_DEG,
    SHIFT_X_MM,
    SHIFT_Y_MM,
    THETA_MIN_DEG,
    joint_margin,
)
from generate_paper_a4_3x3_baseonly_direction_v49 import map_base_only


ROOT = Path(__file__).resolve().parents[1]
TEST_ID = (
    "PAPER_A4_FULL_WIDTH_160MM_TOP_SQUARE_SPIRAL_"
    "F300_CALIBRATION_GCODE_V59"
)
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"

FEED_MM_MIN = 300
OUTER_SIZE_MM = 160.0
PITCH_MM = 15.0
PAPER_SUBDIVISION_MM = 0.5

# Existing calibrated X range is 25..185 mm, exactly 160 mm wide.
OUTER_LEFT_MM = 25.0
OUTER_RIGHT_MM = 185.0
# Nominal physical paper Y. The top stays 5 mm below the 240 mm retained
# boundary. A 160 mm square therefore ends at Y=75 mm.
OUTER_TOP_PHYSICAL_MM = 235.0
OUTER_BOTTOM_PHYSICAL_MM = OUTER_TOP_PHYSICAL_MM - OUTER_SIZE_MM


def intended_physical_points() -> tuple[tuple[float, float], ...]:
    """Build an axis-aligned clockwise-inward open square spiral."""
    left = OUTER_LEFT_MM
    right = OUTER_RIGHT_MM
    top = OUTER_TOP_PHYSICAL_MM
    bottom = OUTER_BOTTOM_PHYSICAL_MM
    points = [(left, top)]
    while right - left > PITCH_MM and top - bottom > PITCH_MM:
        points.extend(
            (
                (right, top),
                (right, bottom),
                (left, bottom),
            )
        )
        next_top = top - PITCH_MM
        points.append((left, next_top))
        left += PITCH_MM
        top = next_top
        right -= PITCH_MM
        bottom += PITCH_MM
    # Finish with the small inner hook. Every source segment remains exactly
    # horizontal or vertical so the pattern can diagnose XY distortion.
    if points[-1] != (right, top):
        points.append((right, top))
    if points[-1] != (right, bottom):
        points.append((right, bottom))
    return tuple(points)


def to_logical_paper(
    physical_point: tuple[float, float],
) -> tuple[float, float]:
    # V28 applies this translation to every emitted Cartesian target.
    return (
        physical_point[0] - SHIFT_X_MM,
        physical_point[1] - SHIFT_Y_MM,
    )


def subdivide(
    points: tuple[tuple[float, float], ...],
) -> tuple[tuple[float, float], ...]:
    result = [points[0]]
    for start, end in zip(points, points[1:]):
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        if abs(dx) > 1.0e-9 and abs(dy) > 1.0e-9:
            raise AssertionError(f"diagonal source segment: {start} -> {end}")
        length = math.dist(start, end)
        if length <= 1.0e-9:
            raise AssertionError("square spiral contains a zero segment")
        count = max(1, math.ceil(length / PAPER_SUBDIVISION_MM))
        result.extend(
            (
                start[0] + dx * index / count,
                start[1] + dy * index / count,
            )
            for index in range(1, count + 1)
        )
    return tuple(result)


def build_plan() -> dict:
    physical_points = intended_physical_points()
    logical_points = tuple(to_logical_paper(p) for p in physical_points)
    sampled_logical_points = subdivide(logical_points)
    for point in sampled_logical_points:
        if not (
            shared.PAPER_X_MIN_MM <= point[0] <= shared.PAPER_X_MAX_MM
            and shared.PAPER_Y_MIN_MM <= point[1] <= shared.PAPER_Y_MAX_MM
        ):
            raise AssertionError(f"full-width spiral out of bounds: {point}")
    return {
        "physical_points_mm": physical_points,
        "logical_points_mm": logical_points,
        "sampled_logical_points_mm": sampled_logical_points,
        "user_points_mm": tuple(
            map_base_only(point) for point in sampled_logical_points
        ),
    }


def gcode_lines(plan: dict) -> tuple[str, ...]:
    user_points = plan["user_points_mm"]
    lines = [
        f"; {TEST_ID}",
        f"; firmware_required={BUILD_ID}",
        "; WARNING=DO_NOT_SEND_TO_V27_OR_OLDER",
        "; calibration_only=YES",
        "; pattern=ONE_FULL_WIDTH_CLOCKWISE_INWARD_SQUARE_SPIRAL",
        f"; outer_size={OUTER_SIZE_MM:.1f}mm pitch={PITCH_MM:.1f}mm",
        f"; intended_physical_bounds=X{OUTER_LEFT_MM:.1f}.."
        f"{OUTER_RIGHT_MM:.1f} Y{OUTER_BOTTOM_PHYSICAL_MM:.1f}.."
        f"{OUTER_TOP_PHYSICAL_MM:.1f}",
        "; source_segments=HORIZONTAL_OR_VERTICAL_ONLY",
        "; start=OUTER_TOP_LEFT direction=RIGHT_THEN_DOWN",
        "; map=BASE_QUADRATIC_ONLY old_grid4x7_residual=DISABLED",
        "; v51_photo_quadratic=DISABLED",
        "; firmware_paper_map=DISABLED firmware_global_y_shift=+15mm",
        f"; paper_subdivision_max={PAPER_SUBDIVISION_MM:.1f}mm",
        "G21",
        "G90",
        "G94",
        f"F{FEED_MM_MIN}",
        "S1000",
        "M5",
        f"G0 X{user_points[0][0]:.3f} Y{user_points[0][1]:.3f}",
        "M3",
    ]
    lines.extend(
        f"G1 X{point[0]:.3f} Y{point[1]:.3f}"
        for point in user_points[1:]
    )
    lines.extend(("M5", "M5"))
    return tuple(lines)


def home_user() -> tuple[float, float]:
    theta = math.radians(THETA_MIN_DEG)
    psi = math.radians(PSI_MIN_DEG)
    machine_x = -L1_MM * math.cos(theta) - L2_MM * math.cos(psi)
    machine_y = L1_MM * math.sin(theta) + L2_MM * math.sin(psi)
    return machine_x - OFFSET_X_MM, machine_y - OFFSET_Y_MM


def audit(plan: dict) -> dict:
    ordered_targets = [
        (point[0] + SHIFT_X_MM, point[1] + SHIFT_Y_MM)
        for point in plan["user_points_mm"]
    ]
    previous = home_user()
    worst = (float("inf"), (0.0, 0.0), (0.0, 0.0, 0.0))
    sample_count = 0
    for target in ordered_targets:
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
        raise AssertionError(f"spiral violates joint limits: {worst}")

    physical = plan["physical_points_mm"]
    return {
        "path_sample_count": sample_count,
        "minimum_joint_margin_deg": worst[0],
        "minimum_at_shifted_user_mm": list(worst[1]),
        "minimum_at_angles_deg": list(worst[2]),
        "intended_physical_paper_bounds_mm": [
            min(point[0] for point in physical),
            min(point[1] for point in physical),
            max(point[0] for point in physical),
            max(point[1] for point in physical),
        ],
    }


def write_preview(plan: dict) -> None:
    width = round(shared.A4_WIDTH_MM * 4.0) + 1
    height = round(shared.A4_HEIGHT_MM * 4.0) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (0, 0, width - 1, height - 1),
        outline=(25, 25, 25),
        width=3,
    )
    draw.line(
        [
            shared.preview_xy(point)
            for point in plan["physical_points_mm"]
        ],
        fill=(190, 30, 30),
        width=3,
        joint="curve",
    )
    draw.text(
        (20, 18),
        "V59 full-width 160 mm square spiral, F300",
        fill=(30, 30, 30),
        font=shared.label_font(20),
    )
    draw.text(
        (20, 48),
        "X 25..185 mm, physical Y 75..235 mm, pitch 15 mm",
        fill=(75, 75, 75),
        font=shared.label_font(16),
    )
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def write_manifest(
    plan: dict,
    lines: tuple[str, ...],
    safety: dict,
) -> None:
    physical = plan["physical_points_mm"]
    source_segments = [
        {
            "index": index,
            "start_mm": list(start),
            "end_mm": list(end),
            "axis": "X" if abs(end[0] - start[0]) > 1.0e-9 else "Y",
            "length_mm": math.dist(start, end),
        }
        for index, (start, end) in enumerate(
            zip(physical, physical[1:]), start=1
        )
    ]
    text = "\n".join(lines) + "\n"
    manifest = {
        "id": TEST_ID,
        "required_firmware": BUILD_ID,
        "purpose": (
            "use one continuous full-width path to locate the height or "
            "side where regional XY distortion begins"
        ),
        "pattern": {
            "type": "open clockwise inward square spiral",
            "outer_size_mm": OUTER_SIZE_MM,
            "pitch_mm": PITCH_MM,
            "physical_bounds_mm": [
                OUTER_LEFT_MM,
                OUTER_BOTTOM_PHYSICAL_MM,
                OUTER_RIGHT_MM,
                OUTER_TOP_PHYSICAL_MM,
            ],
            "source_vertex_count": len(physical),
            "source_segments": source_segments,
            "all_source_segments_axis_aligned": True,
        },
        "mapping": {
            "base_quadratic_enabled": True,
            "old_grid4x7_residual_enabled": False,
            "v51_photo_quadratic_enabled": False,
            "firmware_paper_map_enabled": False,
            "firmware_global_translation_user_mm": [
                SHIFT_X_MM,
                SHIFT_Y_MM,
            ],
        },
        "motion": {
            "feed_mm_min": FEED_MM_MIN,
            "paper_subdivision_max_mm": PAPER_SUBDIVISION_MM,
            "stroke_count": 1,
            "g1_count": len(plan["user_points_mm"]) - 1,
            "pen_down_is_continuous": True,
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
    if not math.isclose(
        OUTER_RIGHT_MM - OUTER_LEFT_MM,
        OUTER_SIZE_MM,
        abs_tol=1.0e-9,
    ):
        raise AssertionError("outer square no longer matches workspace width")
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
        "full_width_square_spiral_v59=PASS "
        f"outer={OUTER_SIZE_MM:.1f}mm pitch={PITCH_MM:.1f}mm "
        f"vertices={len(plan['physical_points_mm'])} "
        f"G1={len(plan['user_points_mm']) - 1} "
        f"bounds={safety['intended_physical_paper_bounds_mm']} "
        f"min_joint_margin={safety['minimum_joint_margin_deg']:.6f}deg"
    )
    print(GCODE_PATH)
    print(PREVIEW_PATH)
    print(MANIFEST_PATH)


if __name__ == "__main__":
    main()
