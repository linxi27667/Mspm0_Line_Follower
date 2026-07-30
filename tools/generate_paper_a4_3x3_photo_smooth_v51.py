#!/usr/bin/env python3
"""Generate V51 validation using the V49 photo-fitted smooth correction."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from derive_v49_photo_smooth_map import (
    MAP_ID,
    OUTPUT as MAP_PATH,
    evaluate,
    fit_smooth_inverse,
)
from generate_paper_a4_3x3_baseonly_direction_v49 import (
    A4_HEIGHT_MM,
    A4_WIDTH_MM,
    BUILD_ID,
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
    map_base_only,
    preview_xy,
    rectangle_paper_points,
)


ROOT = Path(__file__).resolve().parents[1]
TEST_ID = "PAPER_A4_3X3_PHOTO_SMOOTH_CHECKER_CW_CCW_RECT24X8_GCODE_V51"
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"


def direction_placements(
    row_index: int,
    column_index: int,
) -> tuple[tuple[str, float], tuple[str, float]]:
    if (row_index + column_index) % 2 == 0:
        return (
            ("CCW", PAIR_OFFSET_Y_MM),
            ("CW", -PAIR_OFFSET_Y_MM),
        )
    return (
        ("CW", PAIR_OFFSET_Y_MM),
        ("CCW", -PAIR_OFFSET_Y_MM),
    )


def build_plan() -> tuple[dict, ...]:
    coefficients, fit_metrics, _ = fit_smooth_inverse()
    records = []
    for row_index, (row_name, zone_y) in enumerate(ROWS):
        for column_index, (column_name, zone_x) in enumerate(COLUMNS):
            for direction, offset_y in direction_placements(
                row_index, column_index
            ):
                center = (zone_x, zone_y + offset_y)
                desired_points = rectangle_paper_points(center, direction)
                if direction == "CCW":
                    desired_approach = (
                        desired_points[0][0] - TANGENT_APPROACH_MM,
                        desired_points[0][1],
                    )
                else:
                    desired_approach = (
                        desired_points[0][0],
                        desired_points[0][1] - TANGENT_APPROACH_MM,
                    )
                adjusted_approach = evaluate(
                    desired_approach, coefficients
                )
                adjusted_points = tuple(
                    evaluate(point, coefficients)
                    for point in desired_points
                )
                for point in (adjusted_approach, *adjusted_points):
                    if not (
                        PAPER_X_MIN_MM <= point[0] <= PAPER_X_MAX_MM
                        and PAPER_Y_MIN_MM
                        <= point[1]
                        <= PAPER_Y_MAX_MM
                    ):
                        raise AssertionError(
                            f"{row_name}_{column_name}_{direction} "
                            f"corrected source out of bounds: {point}"
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
                        "center_desired_paper_mm": center,
                        "approach_desired_paper_mm": desired_approach,
                        "desired_paper_points_mm": desired_points,
                        "approach_adjusted_source_paper_mm": (
                            adjusted_approach
                        ),
                        "adjusted_source_paper_points_mm": adjusted_points,
                        "approach_user_mm": map_base_only(
                            adjusted_approach
                        ),
                        "user_points_mm": tuple(
                            map_base_only(point)
                            for point in adjusted_points
                        ),
                    }
                )
    return tuple(records), fit_metrics


def gcode_lines(plan: tuple[dict, ...]) -> tuple[str, ...]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware={BUILD_ID}",
        f"; correction_map={MAP_ID}",
        "; old_grid4x7_residual=DISABLED",
        "; direction_placement=CHECKERBOARD",
        "; connection_lines=NONE independent_pen_lift=1",
        f"; rectangle={RECT_WIDTH_MM:.0f}x{RECT_HEIGHT_MM:.0f}mm "
        f"pair_offset_y=+/-{PAIR_OFFSET_Y_MM:.0f}mm",
        f"; desired_paper_step_max={PAPER_STEP_MM:.1f}mm",
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
        center = record["center_desired_paper_mm"]
        lines.extend(
            (
                f"; zone={record['zone']} slot={record['vertical_slot']} "
                f"direction={record['direction']} "
                f"desired_center=({center[0]:.1f},{center[1]:.1f})",
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
        "V51：V49 照片拟合的平滑二次校正验证",
        fill=(20, 20, 20),
        font=label_font(21),
    )
    draw.text(
        (20, 47),
        "蓝=CCW，红=CW；旧 4×7 局部残差保持禁用",
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
                for point in record["desired_paper_points_mm"]
            ],
            fill=color,
            width=3,
        )
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def write_manifest(
    plan: tuple[dict, ...],
    fit_metrics: dict,
    lines: tuple[str, ...],
) -> None:
    text = "\n".join(lines) + "\n"
    manifest = {
        "id": TEST_ID,
        "required_firmware": BUILD_ID,
        "correction_map": {
            "id": MAP_ID,
            "file": str(MAP_PATH),
            "fit": fit_metrics,
            "old_grid4x7_residual_enabled": False,
        },
        "known_limit": (
            "V50 pen-up split is below 1 mm. Pen-down CW/CCW compliance "
            "remains and is averaged, not motor-preloaded."
        ),
        "connection_lines": False,
        "motion": {
            "feed_mm_min": FEED_MM_MIN,
            "pair_count": 9,
            "rectangle_count": len(plan),
            "g1_count": sum(
                len(record["user_points_mm"]) - 1 for record in plan
            ),
        },
        "rectangles": [
            {
                "index": index,
                "zone": record["zone"],
                "vertical_slot": record["vertical_slot"],
                "direction": record["direction"],
                "center_desired_paper_mm": list(
                    record["center_desired_paper_mm"]
                ),
                "desired_paper_points_mm": [
                    list(point)
                    for point in record["desired_paper_points_mm"]
                ],
                "adjusted_source_paper_points_mm": [
                    list(point)
                    for point in record[
                        "adjusted_source_paper_points_mm"
                    ]
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
    plan, fit_metrics = build_plan()
    lines = gcode_lines(plan)
    GCODE_PATH.write_text(
        "\n".join(lines) + "\n",
        encoding="ascii",
        newline="\n",
    )
    write_preview(plan)
    write_manifest(plan, fit_metrics, lines)
    print(
        "generated_paper_a4_3x3_photo_smooth_v51=PASS "
        f"map={MAP_ID} rectangles={len(plan)} "
        f"G1={sum(len(record['user_points_mm']) - 1 for record in plan)} "
        "grid4x7_residual=0 connection_lines=0"
    )
    print(GCODE_PATH)
    print(PREVIEW_PATH)
    print(MANIFEST_PATH)


if __name__ == "__main__":
    main()
