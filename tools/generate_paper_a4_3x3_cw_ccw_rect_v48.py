#!/usr/bin/env python3
"""Generate nine pairs of independently lifted CW/CCW rectangles."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

from generate_paper_a4_top_left_song_12mm_v43 import (
    A4_HEIGHT_MM,
    A4_WIDTH_MM,
    PAPER_X_MAX_MM,
    PAPER_X_MIN_MM,
    PAPER_Y_MAX_MM,
    PAPER_Y_MIN_MM,
    label_font,
    map_paper,
    preview_xy,
)


ROOT = Path(__file__).resolve().parents[1]
TEST_ID = "PAPER_A4_3X3_CW_CCW_RECT24X8_DIRECTION_GCODE_V48"
BUILD_ID = "PAPER_A4_CONTINUOUS_QUEUE_SAFE_HOME_GCODE_V27"
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"

RECT_WIDTH_MM = 24.0
RECT_HEIGHT_MM = 8.0
PAIR_OFFSET_Y_MM = 7.0
PAPER_STEP_MM = 1.0
TANGENT_APPROACH_MM = 5.0
FEED_MM_MIN = 150

COLUMNS = (
    ("LEFT", 50.0),
    ("CENTER", 105.0),
    ("RIGHT", 160.0),
)
ROWS = (
    ("TOP", 205.0),
    ("MIDDLE", 130.0),
    ("BOTTOM", 55.0),
)


def edge_points(
    start: tuple[float, float],
    end: tuple[float, float],
) -> tuple[tuple[float, float], ...]:
    distance = math.dist(start, end)
    count = max(1, math.ceil(distance / PAPER_STEP_MM))
    return tuple(
        (
            start[0] + (end[0] - start[0]) * index / count,
            start[1] + (end[1] - start[1]) * index / count,
        )
        for index in range(1, count + 1)
    )


def rectangle_paper_points(
    center: tuple[float, float],
    direction: str,
) -> tuple[tuple[float, float], ...]:
    half_width = RECT_WIDTH_MM / 2.0
    half_height = RECT_HEIGHT_MM / 2.0
    lower_left = (center[0] - half_width, center[1] - half_height)
    lower_right = (center[0] + half_width, center[1] - half_height)
    upper_right = (center[0] + half_width, center[1] + half_height)
    upper_left = (center[0] - half_width, center[1] + half_height)
    if direction == "CCW":
        vertices = (
            lower_left,
            lower_right,
            upper_right,
            upper_left,
            lower_left,
        )
    elif direction == "CW":
        vertices = (
            lower_left,
            upper_left,
            upper_right,
            lower_right,
            lower_left,
        )
    else:
        raise ValueError(direction)
    points = [vertices[0]]
    for start, end in zip(vertices, vertices[1:]):
        points.extend(edge_points(start, end))
    return tuple(points)


def build_plan() -> tuple[dict, ...]:
    records = []
    for row_name, zone_y in ROWS:
        for column_name, zone_x in COLUMNS:
            for direction, offset_y in (
                ("CCW", PAIR_OFFSET_Y_MM),
                ("CW", -PAIR_OFFSET_Y_MM),
            ):
                center = (zone_x, zone_y + offset_y)
                paper_points = rectangle_paper_points(center, direction)
                if direction == "CCW":
                    approach_paper = (
                        paper_points[0][0] - TANGENT_APPROACH_MM,
                        paper_points[0][1],
                    )
                else:
                    approach_paper = (
                        paper_points[0][0],
                        paper_points[0][1] - TANGENT_APPROACH_MM,
                    )
                for point in (approach_paper, *paper_points):
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
                        "direction": direction,
                        "center_paper_mm": center,
                        "approach_paper_mm": approach_paper,
                        "paper_points_mm": paper_points,
                        "approach_user_mm": map_paper(approach_paper),
                        "user_points_mm": tuple(
                            map_paper(point) for point in paper_points
                        ),
                    }
                )
    return tuple(records)


def gcode_lines(plan: tuple[dict, ...]) -> tuple[str, ...]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware={BUILD_ID}",
        "; blank_A4_required=1 layout=3x3 pairs=9 rectangles=18",
        "; pair=upper_CCW,lower_CW independent_pen_lift=1",
        f"; each_rectangle_paper_size={RECT_WIDTH_MM:.0f}x"
        f"{RECT_HEIGHT_MM:.0f}mm pair_offset_y=+/-{PAIR_OFFSET_Y_MM:.0f}mm",
        "; CCW_edges=+X,+Y,-X,-Y",
        "; CW_edges=+Y,+X,-Y,-X",
        "; connection_lines=NONE",
        "; firmware_paper_map=DISABLED offline_pointwise_map=ENABLED",
        f"; paper_step_max={PAPER_STEP_MM:.1f}mm "
        f"tangent_approach={TANGENT_APPROACH_MM:.1f}mm",
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
                f"; zone={record['zone']} direction={record['direction']} "
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
        "V48 九区正反方向：上框 CCW，下框 CW",
        fill=(20, 20, 20),
        font=label_font(23),
    )
    draw.text(
        (20, 48),
        "18 个矩形全部独立抬落笔；不存在连接线",
        fill=(70, 70, 70),
        font=label_font(17),
    )
    for record in plan:
        points = record["paper_points_mm"]
        color = (
            (25, 75, 190)
            if record["direction"] == "CCW"
            else (190, 55, 35)
        )
        draw.line(
            [preview_xy(point) for point in points],
            fill=color,
            width=3,
        )
        start = preview_xy(points[0])
        draw.ellipse(
            (
                start[0] - 3,
                start[1] - 3,
                start[0] + 3,
                start[1] + 3,
            ),
            fill=color,
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
            "separate position-dependent paper-map error from "
            "direction-dependent motion error"
        ),
        "blank_a4_required": True,
        "connection_lines": False,
        "coordinate_contract": {
            "paper_origin": "lower_left",
            "paper_positive_x": "right",
            "paper_positive_y": "up",
            "firmware_paper_map_enabled": False,
            "offline_pointwise_paper_to_user_map_enabled": True,
        },
        "rectangle": {
            "width_mm": RECT_WIDTH_MM,
            "height_mm": RECT_HEIGHT_MM,
            "pair_offset_y_mm": PAIR_OFFSET_Y_MM,
            "paper_step_max_mm": PAPER_STEP_MM,
            "tangent_approach_mm": TANGENT_APPROACH_MM,
        },
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
                "direction": record["direction"],
                "center_paper_mm": list(record["center_paper_mm"]),
                "approach_paper_mm": list(record["approach_paper_mm"]),
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
        "generated_paper_a4_3x3_cw_ccw_rect_v48=PASS "
        f"pairs=9 rectangles={len(plan)} "
        f"size={RECT_WIDTH_MM:.0f}x{RECT_HEIGHT_MM:.0f}mm "
        f"G1={sum(len(record['user_points_mm']) - 1 for record in plan)} "
        "connection_lines=0"
    )
    print(GCODE_PATH)
    print(PREVIEW_PATH)
    print(MANIFEST_PATH)


if __name__ == "__main__":
    main()
