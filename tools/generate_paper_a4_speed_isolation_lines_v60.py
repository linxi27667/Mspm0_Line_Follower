#!/usr/bin/env python3
"""Generate paired F150/F300 full-length XY lines for distortion isolation."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

import generate_paper_a4_top_left_song_12mm_v43 as shared
from check_workspace_yshift15_v28 import (
    BUILD_ID,
    SHIFT_X_MM,
    SHIFT_Y_MM,
    joint_margin,
)
from generate_paper_a4_3x3_baseonly_direction_v49 import map_base_only
from generate_paper_a4_full_width_square_spiral_v59 import (
    home_user,
    subdivide,
    to_logical_paper,
)


ROOT = Path(__file__).resolve().parents[1]
TEST_ID = "PAPER_A4_F150_F300_XY_SPEED_ISOLATION_160MM_GCODE_V60"
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"


STROKES = (
    {
        "id": "H_F150_UPPER",
        "axis": "X",
        "feed_mm_min": 150,
        "physical_start_mm": (25.0, 230.0),
        "physical_end_mm": (185.0, 230.0),
    },
    {
        "id": "H_F300_LOWER",
        "axis": "X",
        "feed_mm_min": 300,
        "physical_start_mm": (25.0, 215.0),
        "physical_end_mm": (185.0, 215.0),
    },
    {
        "id": "V_F150_LEFT",
        "axis": "Y",
        "feed_mm_min": 150,
        "physical_start_mm": (155.0, 235.0),
        "physical_end_mm": (155.0, 75.0),
    },
    {
        "id": "V_F300_RIGHT",
        "axis": "Y",
        "feed_mm_min": 300,
        "physical_start_mm": (170.0, 235.0),
        "physical_end_mm": (170.0, 75.0),
    },
)


def build_plan() -> tuple[dict, ...]:
    records = []
    for source in STROKES:
        logical_vertices = tuple(
            to_logical_paper(point)
            for point in (
                source["physical_start_mm"],
                source["physical_end_mm"],
            )
        )
        logical_points = subdivide(logical_vertices)
        for point in logical_points:
            if not (
                shared.PAPER_X_MIN_MM <= point[0] <= shared.PAPER_X_MAX_MM
                and shared.PAPER_Y_MIN_MM <= point[1] <= shared.PAPER_Y_MAX_MM
            ):
                raise AssertionError(f"{source['id']} out of bounds: {point}")
        records.append(
            {
                **source,
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
        "; purpose=ISOLATE_STATIC_MAPPING_FROM_F300_DYNAMIC_ERROR",
        "; H_UPPER=F150 H_LOWER=F300",
        "; V_LEFT=F150 V_RIGHT=F300",
        "; each_line=160mm direction=LEFT_TO_RIGHT_OR_TOP_TO_BOTTOM",
        "; map=BASE_QUADRATIC_ONLY old_grid4x7_residual=DISABLED",
        "; v51_photo_quadratic=DISABLED",
        "; firmware_paper_map=DISABLED firmware_global_y_shift=+15mm",
        "; paper_subdivision_max=0.5mm",
        "G21",
        "G90",
        "G94",
        "S1000",
        "M5",
    ]
    for record in plan:
        points = record["user_points_mm"]
        lines.extend(
            (
                f"; ===== {record['id']} =====",
                f"F{record['feed_mm_min']}",
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
        raise AssertionError(f"speed isolation violates limits: {worst}")
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
    colors = {150: (35, 95, 185), 300: (205, 45, 35)}
    for record in plan:
        start = shared.preview_xy(record["physical_start_mm"])
        end = shared.preview_xy(record["physical_end_mm"])
        draw.line(
            (start, end),
            fill=colors[record["feed_mm_min"]],
            width=3,
        )
        draw.text(
            (start[0] + 5, start[1] - 24),
            record["id"],
            fill=colors[record["feed_mm_min"]],
            font=shared.label_font(15),
        )
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def write_manifest(
    plan: tuple[dict, ...],
    lines: tuple[str, ...],
    safety: dict,
) -> None:
    text = "\n".join(lines) + "\n"
    manifest = {
        "id": TEST_ID,
        "required_firmware": BUILD_ID,
        "decision_rule": {
            "F150_and_F300_same_slope": (
                "static paper mapping or mechanism geometry error"
            ),
            "F300_materially_worse_than_F150": (
                "dynamic tracking, acceleration, rigidity, or lost-step error"
            ),
        },
        "strokes": [
            {
                key: value
                for key, value in record.items()
                if key not in ("logical_points_mm", "user_points_mm")
            }
            for record in plan
        ],
        "mapping": {
            "base_quadratic_enabled": True,
            "old_grid4x7_residual_enabled": False,
            "v51_photo_quadratic_enabled": False,
            "firmware_global_translation_user_mm": [
                SHIFT_X_MM,
                SHIFT_Y_MM,
            ],
        },
        "motion": {
            "paper_subdivision_max_mm": 0.5,
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
        "speed_isolation_lines_v60=PASS "
        f"strokes={len(plan)} "
        f"G1={sum(len(r['user_points_mm']) - 1 for r in plan)} "
        f"min_joint_margin={safety['minimum_joint_margin_deg']:.6f}deg"
    )
    print(GCODE_PATH)
    print(PREVIEW_PATH)
    print(MANIFEST_PATH)


if __name__ == "__main__":
    main()
