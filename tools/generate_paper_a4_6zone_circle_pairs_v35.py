#!/usr/bin/env python3
"""Generate six paper zones with paired CW/CCW 18 mm circles."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

import generate_paper_a4_zhang_jia_le_v31 as base


ROOT = Path(__file__).resolve().parents[1]
GCODE_PATH = (
    ROOT
    / "gcode"
    / "PAPER_A4_6ZONE_CW_CCW_CIRCLE_D18_TANGENT_GCODE_V35.gcode"
)
MANIFEST_PATH = (
    ROOT
    / "gcode"
    / "PAPER_A4_6ZONE_CW_CCW_CIRCLE_D18_TANGENT_GCODE_V35.json"
)
PREVIEW_PATH = (
    ROOT
    / "docs"
    / "diagnostics"
    / "PAPER_A4_6ZONE_CW_CCW_CIRCLE_D18_TANGENT_GCODE_V35_PREVIEW.png"
)

RADIUS_MM = 9.0
DIAMETER_MM = RADIUS_MM * 2.0
SEGMENTS_PER_CIRCLE = 72
COLUMN_CENTERS_MM = (52.0, 105.0, 158.0)
ROW_CENTERS_MM = (65.0, 220.0)
PAIR_OFFSET_X_MM = 11.0
TANGENT_APPROACH_MM = base.TANGENT_APPROACH_MM
FEED_MM_MIN = base.FEED_MM_MIN
PAPER_X_MIN_MM = base.PAPER_X_MIN_MM
PAPER_X_MAX_MM = base.PAPER_X_MAX_MM
PAPER_Y_MIN_MM = base.PAPER_Y_MIN_MM
PAPER_Y_MAX_MM = base.PAPER_Y_MAX_MM


@dataclass(frozen=True)
class CircleRecord:
    zone_id: str
    row_name: str
    column_name: str
    direction: str
    center_mm: tuple[float, float]
    radius_mm: float
    stroke: base.Stroke


@dataclass(frozen=True)
class CircleLayout:
    circles: tuple[CircleRecord, ...]
    bounds_mm: tuple[float, float, float, float]

    @property
    def strokes(self) -> tuple[base.Stroke, ...]:
        return tuple(circle.stroke for circle in self.circles)


def circle_points(
    center: tuple[float, float],
    direction: str,
) -> tuple[tuple[float, float], ...]:
    sign = -1.0 if direction == "CW" else 1.0
    return tuple(
        (
            center[0]
            + RADIUS_MM
            * math.cos(
                math.pi / 2.0
                + sign * 2.0 * math.pi * index / SEGMENTS_PER_CIRCLE
            ),
            center[1]
            + RADIUS_MM
            * math.sin(
                math.pi / 2.0
                + sign * 2.0 * math.pi * index / SEGMENTS_PER_CIRCLE
            ),
        )
        for index in range(SEGMENTS_PER_CIRCLE + 1)
    )


def make_circle(
    zone_id: str,
    circle_index: int,
    row_name: str,
    column_name: str,
    direction: str,
    center: tuple[float, float],
) -> CircleRecord:
    points = circle_points(center, direction)
    first_length = math.dist(points[0], points[1])
    unit = (
        (points[1][0] - points[0][0]) / first_length,
        (points[1][1] - points[0][1]) / first_length,
    )
    approach = (
        points[0][0] - unit[0] * TANGENT_APPROACH_MM,
        points[0][1] - unit[1] * TANGENT_APPROACH_MM,
    )
    stroke = base.Stroke(
        f"{zone_id}-{direction}",
        circle_index,
        1,
        approach,
        points,
    )
    return CircleRecord(
        zone_id,
        row_name,
        column_name,
        direction,
        center,
        RADIUS_MM,
        stroke,
    )


def build_layout() -> CircleLayout:
    circles: list[CircleRecord] = []
    row_names = ("下", "上")
    column_names = ("左", "中", "右")
    for row_index, (row_name, center_y) in enumerate(
        zip(row_names, ROW_CENTERS_MM)
    ):
        for column_index, (column_name, zone_center_x) in enumerate(
            zip(column_names, COLUMN_CENTERS_MM)
        ):
            zone_id = f"{row_name}{column_name}"
            for direction_index, direction in enumerate(("CW", "CCW")):
                center_x = zone_center_x + (
                    -PAIR_OFFSET_X_MM
                    if direction == "CW"
                    else PAIR_OFFSET_X_MM
                )
                circles.append(
                    make_circle(
                        zone_id,
                        len(circles),
                        row_name,
                        column_name,
                        direction,
                        (center_x, center_y),
                    )
                )

    all_points = [
        point
        for circle in circles
        for point in (circle.stroke.approach, *circle.stroke.points)
    ]
    bounds = (
        min(point[0] for point in all_points),
        min(point[1] for point in all_points),
        max(point[0] for point in all_points),
        max(point[1] for point in all_points),
    )
    for point in all_points:
        if not (
            PAPER_X_MIN_MM <= point[0] <= PAPER_X_MAX_MM
            and PAPER_Y_MIN_MM <= point[1] <= PAPER_Y_MAX_MM
        ):
            raise AssertionError(f"circle point outside calibrated paper: {point}")

    # Both new rows must stay clear of the photographed V31/V33 ink bands.
    lower_circle_top = ROW_CENTERS_MM[0] + RADIUS_MM
    upper_circle_bottom = ROW_CENTERS_MM[1] - RADIUS_MM
    if lower_circle_top >= 114.0 or upper_circle_bottom <= 201.231:
        raise AssertionError("circle rows overlap existing ink")
    return CircleLayout(tuple(circles), bounds)


def gcode_lines(layout: CircleLayout) -> tuple[str, ...]:
    lines = ["G21", "G90", "G94", "M5", f"F{FEED_MM_MIN}"]
    for stroke in layout.strokes:
        lines.append(
            f"G0 X{stroke.approach[0]:.6f} Y{stroke.approach[1]:.6f}"
        )
        lines.append(
            f"G0 X{stroke.points[0][0]:.6f} Y{stroke.points[0][1]:.6f}"
        )
        lines.append("M3")
        for point in stroke.points[1:]:
            lines.append(f"G1 X{point[0]:.6f} Y{point[1]:.6f}")
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

    for low, high, label in (
        (114.0, 150.929, "已有 V31"),
        (158.885, 201.231, "已有 V33"),
    ):
        draw.rectangle(
            (
                *base.preview_xy((PAPER_X_MIN_MM, high)),
                *base.preview_xy((PAPER_X_MAX_MM, low)),
            ),
            fill=(247, 247, 247),
            outline=(225, 225, 225),
        )
        draw.text(
            base.preview_xy((27.0, high - 3.0)),
            label,
            fill=(165, 165, 165),
            font=base.label_font(14),
        )

    draw.text(
        (20, 16),
        "V35 六区域圆测试：每区左 CW / 右 CCW，直径 18 mm",
        fill=(20, 20, 20),
        font=base.label_font(23),
    )
    draw.text(
        (20, 50),
        "黑线=落笔圆  蓝虚线=6 mm切线预接近  红点=闭合起点",
        fill=(70, 70, 70),
        font=base.label_font(17),
    )

    for row_name, center_y in zip(("下", "上"), ROW_CENTERS_MM):
        for column_name, zone_center_x in zip(
            ("左", "中", "右"), COLUMN_CENTERS_MM
        ):
            zone_left = zone_center_x - 26.0
            zone_right = zone_center_x + 26.0
            zone_bottom = center_y - 17.0
            zone_top = center_y + 17.0
            draw.rectangle(
                (
                    *base.preview_xy((zone_left, zone_top)),
                    *base.preview_xy((zone_right, zone_bottom)),
                ),
                outline=(225, 225, 225),
                width=1,
            )
            label_point = base.preview_xy(
                (zone_center_x - 9.0, zone_top + 4.0)
            )
            draw.text(
                label_point,
                f"{row_name}{column_name}",
                fill=(70, 70, 70),
                font=base.label_font(14),
            )

    for circle in layout.circles:
        stroke = circle.stroke
        approach_px = base.preview_xy(stroke.approach)
        start_px = base.preview_xy(stroke.points[0])
        base.draw_dashed_line(
            draw, approach_px, start_px, (45, 115, 185), width=2
        )
        draw.line(
            [base.preview_xy(point) for point in stroke.points],
            fill=(15, 15, 15),
            width=3,
            joint="curve",
        )
        center_px = base.preview_xy(circle.center_mm)
        draw.line(
            (
                center_px[0] - 3,
                center_px[1],
                center_px[0] + 3,
                center_px[1],
            ),
            fill=(175, 175, 175),
            width=1,
        )
        draw.line(
            (
                center_px[0],
                center_px[1] - 3,
                center_px[0],
                center_px[1] + 3,
            ),
            fill=(175, 175, 175),
            width=1,
        )
        draw.ellipse(
            (
                start_px[0] - 3,
                start_px[1] - 3,
                start_px[0] + 3,
                start_px[1] + 3,
            ),
            fill=(195, 35, 35),
        )
        direction_x = circle.center_mm[0] - 5.0
        direction_y = circle.center_mm[1] - 13.0
        draw.text(
            base.preview_xy((direction_x, direction_y)),
            circle.direction,
            fill=(75, 75, 75),
            font=base.label_font(11),
        )

    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def write_manifest(
    layout: CircleLayout,
    lines: tuple[str, ...],
) -> None:
    manifest = {
        "id": "PAPER_A4_6ZONE_CW_CCW_CIRCLE_D18_TANGENT_GCODE_V35",
        "purpose": "measure circle scale, roundness, closure, direction and position",
        "circle_contract": {
            "radius_mm": RADIUS_MM,
            "diameter_mm": DIAMETER_MM,
            "segments_per_circle": SEGMENTS_PER_CIRCLE,
            "start_angle_deg": 90.0,
            "pair_order": ["CW", "CCW"],
            "pair_offset_x_mm": PAIR_OFFSET_X_MM,
        },
        "zones": [
            {
                "zone_id": circle.zone_id,
                "row": circle.row_name,
                "column": circle.column_name,
                "direction": circle.direction,
                "center_mm": list(circle.center_mm),
            }
            for circle in layout.circles
        ],
        "layout": {
            "column_centers_mm": list(COLUMN_CENTERS_MM),
            "row_centers_mm": list(ROW_CENTERS_MM),
            "bounds_with_approach_mm": list(layout.bounds_mm),
            "existing_ink_bands_mm": [
                [114.0, 150.929],
                [158.885, 201.231],
            ],
        },
        "motion": {
            "feed_mm_min": FEED_MM_MIN,
            "tangent_approach_mm": TANGENT_APPROACH_MM,
            "circle_count": len(layout.circles),
            "stroke_count": len(layout.strokes),
            "g1_count": sum(
                len(stroke.points) - 1 for stroke in layout.strokes
            ),
        },
        "gcode": {
            "file": GCODE_PATH.name,
            "line_count": len(lines),
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
        "generated_6zone_circle_pairs_v35=PASS "
        f"zones={len(layout.circles) // 2} circles={len(layout.circles)} "
        f"segments_per_circle={SEGMENTS_PER_CIRCLE} "
        f"G1={sum(len(stroke.points) - 1 for stroke in layout.strokes)} "
        f"bounds_x={layout.bounds_mm[0]:.3f}..{layout.bounds_mm[2]:.3f} "
        f"bounds_y={layout.bounds_mm[1]:.3f}..{layout.bounds_mm[3]:.3f}"
    )
    print(GCODE_PATH)
    print(PREVIEW_PATH)
    print(MANIFEST_PATH)


if __name__ == "__main__":
    main()
