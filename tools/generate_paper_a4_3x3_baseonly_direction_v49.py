#!/usr/bin/env python3
"""Generate a base-only map test with checkerboard CW/CCW placement."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from check_paper_a4_center_yong_v26 import paper_to_user
from generate_paper_a4_3x3_cw_ccw_rect_v48 import (
    A4_HEIGHT_MM,
    A4_WIDTH_MM,
    COLUMNS,
    FEED_MM_MIN,
    PAIR_OFFSET_Y_MM,
    PAPER_STEP_MM,
    PAPER_X_MAX_MM,
    PAPER_X_MIN_MM,
    PAPER_Y_MAX_MM,
    PAPER_Y_MIN_MM,
    RECT_HEIGHT_MM,
    RECT_WIDTH_MM,
    ROWS,
    TANGENT_APPROACH_MM,
    label_font,
    preview_xy,
    rectangle_paper_points,
)
from generate_paper_a4_map_vs_cartesian_circle_v36 import mapping_model


ROOT = Path(__file__).resolve().parents[1]
TEST_ID = "PAPER_A4_3X3_BASEONLY_CHECKER_CW_CCW_RECT24X8_GCODE_V49"
BUILD_ID = "PAPER_A4_CONTINUOUS_QUEUE_SAFE_HOME_GCODE_V27"
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"

BASE_COEFFICIENTS, OLD_GRID_DELTA = mapping_model()
ZERO_GRID_DELTA = np.zeros_like(OLD_GRID_DELTA)


def map_base_only(point: tuple[float, float]) -> tuple[float, float]:
    return paper_to_user(point, BASE_COEFFICIENTS, ZERO_GRID_DELTA)


def build_plan() -> tuple[dict, ...]:
    records = []
    for row_index, (row_name, zone_y) in enumerate(ROWS):
        for column_index, (column_name, zone_x) in enumerate(COLUMNS):
            if (row_index + column_index) % 2 == 0:
                placements = (
                    ("CCW", PAIR_OFFSET_Y_MM),
                    ("CW", -PAIR_OFFSET_Y_MM),
                )
            else:
                placements = (
                    ("CW", PAIR_OFFSET_Y_MM),
                    ("CCW", -PAIR_OFFSET_Y_MM),
                )
            for direction, offset_y in placements:
                center = (zone_x, zone_y + offset_y)
                points = rectangle_paper_points(center, direction)
                if direction == "CCW":
                    approach = (
                        points[0][0] - TANGENT_APPROACH_MM,
                        points[0][1],
                    )
                else:
                    approach = (
                        points[0][0],
                        points[0][1] - TANGENT_APPROACH_MM,
                    )
                for point in (approach, *points):
                    if not (
                        PAPER_X_MIN_MM <= point[0] <= PAPER_X_MAX_MM
                        and PAPER_Y_MIN_MM <= point[1] <= PAPER_Y_MAX_MM
                    ):
                        raise AssertionError(
                            f"{row_name}_{column_name}_{direction} "
                            f"out of bounds: {point}"
                        )
                records.append(
                    {
                        "zone": f"{row_name}_{column_name}",
                        "row": row_name,
                        "column": column_name,
                        "vertical_slot": (
                            "UPPER" if offset_y > 0.0 else "LOWER"
                        ),
                        "direction": direction,
                        "center_paper_mm": center,
                        "approach_paper_mm": approach,
                        "paper_points_mm": points,
                        "approach_user_mm": map_base_only(approach),
                        "user_points_mm": tuple(
                            map_base_only(point) for point in points
                        ),
                    }
                )
    return tuple(records)


def gcode_lines(plan: tuple[dict, ...]) -> tuple[str, ...]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware={BUILD_ID}",
        "; blank_A4_required=1 layout=3x3 pairs=9 rectangles=18",
        "; map=BASE_QUADRATIC_ONLY old_grid4x7_residual=DISABLED",
        "; direction_placement=CHECKERBOARD upper/lower swapped by zone",
        "; connection_lines=NONE independent_pen_lift=1",
        f"; rectangle={RECT_WIDTH_MM:.0f}x{RECT_HEIGHT_MM:.0f}mm "
        f"pair_offset_y=+/-{PAIR_OFFSET_Y_MM:.0f}mm",
        f"; paper_step_max={PAPER_STEP_MM:.1f}mm",
        "G21",
        "G90",
        "G94",
        f"F{FEED_MM_MIN}",
        "S1000",
        "M5",
    ]
    for record in plan:
        approach = record["approach_user_mm"]
        points = record["user_points_mm"]
        center = record["center_paper_mm"]
        lines.extend(
            (
                f"; zone={record['zone']} slot={record['vertical_slot']} "
                f"direction={record['direction']} "
                f"paper_center=({center[0]:.1f},{center[1]:.1f})",
                f"G0 X{approach[0]:.3f} Y{approach[1]:.3f}",
                f"G0 X{points[0][0]:.3f} Y{points[0][1]:.3f}",
                "M3",
            )
        )
        lines.extend(
            f"G1 X{point[0]:.3f} Y{point[1]:.3f}"
            for point in points[1:]
        )
        lines.append("M5")
    return tuple(lines)


def write_preview(plan: tuple[dict, ...]) -> None:
    width = round(A4_WIDTH_MM * 4.0) + 1
    height = round(A4_HEIGHT_MM * 4.0) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (0, 0, width - 1, height - 1),
        outline=(25, 25, 25),
        width=3,
    )
    draw.rectangle(
        (
            *preview_xy((PAPER_X_MIN_MM, PAPER_Y_MAX_MM)),
            *preview_xy((PAPER_X_MAX_MM, PAPER_Y_MIN_MM)),
        ),
        outline=(130, 160, 195),
        width=2,
    )
    draw.text(
        (20, 16),
        "V49：只保留全局二次映射，禁用旧 4×7 局部残差",
        fill=(20, 20, 20),
        font=label_font(21),
    )
    draw.text(
        (20, 47),
        "蓝=CCW，红=CW；上下方向按棋盘格交替",
        fill=(70, 70, 70),
        font=label_font(17),
    )
    for record in plan:
        color = (
            (25, 75, 190)
            if record["direction"] == "CCW"
            else (190, 55, 35)
        )
        draw.line(
            [
                preview_xy(point)
                for point in record["paper_points_mm"]
            ],
            fill=color,
            width=3,
        )
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def write_manifest(
    plan: tuple[dict, ...],
    lines: tuple[str, ...],
) -> None:
    text = "\n".join(lines) + "\n"
    manifest = {
        "id": TEST_ID,
        "required_firmware": BUILD_ID,
        "purpose": (
            "confirm that V48 row-boundary distortions come from the stale "
            "4x7 residual field, while checkerboard placement separates "
            "direction from vertical position"
        ),
        "blank_a4_required": True,
        "mapping": {
            "base_quadratic_enabled": True,
            "old_grid4x7_residual_enabled": False,
            "firmware_paper_map_enabled": False,
            "offline_pointwise_map_enabled": True,
        },
        "connection_lines": False,
        "motion": {
            "feed_mm_min": FEED_MM_MIN,
            "pair_count": 9,
            "rectangle_count": len(plan),
            "g1_count": sum(
                len(record["user_points_mm"]) - 1 for record in plan
            ),
            "independent_pen_lift_per_rectangle": True,
        },
        "rectangles": [
            {
                "index": index,
                "zone": record["zone"],
                "row": record["row"],
                "column": record["column"],
                "vertical_slot": record["vertical_slot"],
                "direction": record["direction"],
                "center_paper_mm": list(record["center_paper_mm"]),
                "paper_points_mm": [
                    list(point) for point in record["paper_points_mm"]
                ],
                "user_points_mm": [
                    list(point) for point in record["user_points_mm"]
                ],
            }
            for index, record in enumerate(plan, start=1)
        ],
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
    lines = gcode_lines(plan)
    GCODE_PATH.write_text(
        "\n".join(lines) + "\n",
        encoding="ascii",
        newline="\n",
    )
    write_preview(plan)
    write_manifest(plan, lines)
    print(
        "generated_paper_a4_3x3_baseonly_direction_v49=PASS "
        f"pairs=9 rectangles={len(plan)} "
        f"G1={sum(len(record['user_points_mm']) - 1 for record in plan)} "
        "grid4x7_residual=0 connection_lines=0"
    )
    print(GCODE_PATH)
    print(PREVIEW_PATH)
    print(MANIFEST_PATH)


if __name__ == "__main__":
    main()
