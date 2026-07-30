#!/usr/bin/env python3
"""Generate the first direct-coordinate continuous-queue circle test."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw
from generate_paper_a4_map_vs_cartesian_circle_v36 import (
    mapped,
    mapping_model,
)


ROOT = Path(__file__).resolve().parents[1]
GCODE_PATH = (
    ROOT
    / "gcode"
    / "PAPER_A4_CONTINUOUS_QUEUE_DIRECT_6CIRCLE_D18_GCODE_V37.gcode"
)
MANIFEST_PATH = (
    ROOT
    / "gcode"
    / "PAPER_A4_CONTINUOUS_QUEUE_DIRECT_6CIRCLE_D18_GCODE_V37.json"
)
PREVIEW_PATH = (
    ROOT
    / "docs"
    / "diagnostics"
    / "PAPER_A4_CONTINUOUS_QUEUE_DIRECT_6CIRCLE_D18_GCODE_V37_PREVIEW.png"
)

BUILD_ID = "PAPER_A4_CONTINUOUS_QUEUE_SAFE_HOME_GCODE_V27"
TEST_ID = "PAPER_A4_CONTINUOUS_QUEUE_DIRECT_6CIRCLE_D18_GCODE_V37"
RADIUS_MM = 9.0
SEGMENTS = 72
FEED_MM_MIN = 180
ROW_Y_MM = 140.0
CIRCLES = (
    ("LEFT_CW", 41.0, True),
    ("LEFT_CCW", 63.0, False),
    ("MIDDLE_CW", 94.0, True),
    ("MIDDLE_CCW", 116.0, False),
    ("RIGHT_CW", 147.0, True),
    ("RIGHT_CCW", 169.0, False),
)
MAP_COEFFICIENTS, MAP_TOTAL_DELTA = mapping_model()


def circle_points(
    center_x: float, center_y: float, clockwise: bool
) -> list[tuple[float, float]]:
    direction = -1.0 if clockwise else 1.0
    return [
        (
            center_x
            + RADIUS_MM
            * math.cos(math.pi / 2.0 + direction * 2.0 * math.pi * i / SEGMENTS),
            center_y
            + RADIUS_MM
            * math.sin(math.pi / 2.0 + direction * 2.0 * math.pi * i / SEGMENTS),
        )
        for i in range(SEGMENTS + 1)
    ]


def command_center(
    nominal_paper_x: float,
) -> tuple[float, float]:
    center = mapped(
        (nominal_paper_x, ROW_Y_MM),
        MAP_COEFFICIENTS,
        MAP_TOTAL_DELTA,
    )
    return float(center[0]), float(center[1])


def generate_gcode() -> str:
    lines = [
        f"; {TEST_ID}",
        f"; firmware={BUILD_ID}",
        "; paper_map=DISABLED direct_user_coordinates=1",
        "; placement=MIDDLE_ROW y=140mm",
        "; purpose=continuous_queue_vs_old_stop_go",
        "G21",
        "G90",
        "G94",
        f"F{FEED_MM_MIN}",
        "S1000",
        "M5",
    ]

    for name, nominal_x, clockwise in CIRCLES:
        center_x, center_y = command_center(nominal_x)
        points = circle_points(center_x, center_y, clockwise)
        start_x, start_y = points[0]
        lines.extend(
            (
                f"; {name} nominal_paper_center=({nominal_x:.3f},"
                f"{ROW_Y_MM:.3f}) command_user_center="
                f"({center_x:.3f},{center_y:.3f}) "
                f"direction={'CW' if clockwise else 'CCW'}",
                f"G0 X{start_x:.3f} Y{start_y:.3f}",
                "M3",
            )
        )
        lines.extend(
            f"G1 X{x:.3f} Y{y:.3f}" for x, y in points[1:]
        )
        lines.append("M5")

    return "\n".join(lines) + "\n"


def draw_preview() -> None:
    scale = 4
    margin = 24
    paper_w = 210
    paper_h = 297
    image = Image.new(
        "RGB",
        (paper_w * scale + 2 * margin, paper_h * scale + 2 * margin),
        "white",
    )
    draw = ImageDraw.Draw(image)

    def pixel(point: tuple[float, float]) -> tuple[int, int]:
        x, y = point
        return (
            int(round(margin + x * scale)),
            int(round(margin + (paper_h - y) * scale)),
        )

    draw.rectangle(
        (margin, margin, margin + paper_w * scale, margin + paper_h * scale),
        outline=(80, 80, 80),
        width=2,
    )
    draw.line(
        (pixel((20.0, ROW_Y_MM)), pixel((190.0, ROW_Y_MM))),
        fill=(220, 220, 220),
        width=1,
    )
    for name, nominal_x, clockwise in CIRCLES:
        points = circle_points(nominal_x, ROW_Y_MM, clockwise)
        draw.line(
            [pixel(point) for point in points],
            fill=(0, 0, 0),
            width=2,
        )
        draw.text(
            pixel((nominal_x - 7.0, ROW_Y_MM - 14.0)),
            "CW" if clockwise else "CCW",
            fill=(0, 80, 160),
        )
        draw.text(
            pixel((nominal_x - 9.0, ROW_Y_MM + 15.0)),
            name.split("_")[0],
            fill=(90, 90, 90),
        )

    image.save(PREVIEW_PATH)


def main() -> None:
    gcode = generate_gcode()
    GCODE_PATH.write_text(gcode, encoding="ascii", newline="\n")
    manifest = {
        "test_id": TEST_ID,
        "required_firmware": BUILD_ID,
        "paper_map_enabled": False,
        "row_y_mm": ROW_Y_MM,
        "radius_mm": RADIUS_MM,
        "segments_per_circle": SEGMENTS,
        "feed_mm_min": FEED_MM_MIN,
        "circles": [
            {
                "name": name,
                "nominal_paper_center_mm": [
                    nominal_x, ROW_Y_MM
                ],
                "command_user_center_mm": list(
                    command_center(nominal_x)
                ),
                "direction": "CW" if clockwise else "CCW",
            }
            for name, nominal_x, clockwise in CIRCLES
        ],
        "gcode_sha256": hashlib.sha256(gcode.encode("ascii")).hexdigest(),
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    draw_preview()
    print(GCODE_PATH)
    print(MANIFEST_PATH)
    print(PREVIEW_PATH)


if __name__ == "__main__":
    main()
