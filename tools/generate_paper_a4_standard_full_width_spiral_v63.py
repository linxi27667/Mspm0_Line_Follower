#!/usr/bin/env python3
"""Generate a standard-coordinate full-width square spiral for V29."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

import generate_paper_a4_top_left_song_12mm_v43 as shared
from generate_paper_a4_full_width_square_spiral_v59 import (
    OUTER_BOTTOM_PHYSICAL_MM,
    OUTER_LEFT_MM,
    OUTER_RIGHT_MM,
    OUTER_SIZE_MM,
    OUTER_TOP_PHYSICAL_MM,
    PITCH_MM,
    intended_physical_points,
)


ROOT = Path(__file__).resolve().parents[1]
TEST_ID = "PAPER_A4_STANDARD_FULL_WIDTH_160MM_SQUARE_SPIRAL_F300_GCODE_V63"
FIRMWARE_ID = "PAPER_A4_STANDARD_GCODE_SBOW_PAPERMAP_YSHIFT15_V29"
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"

FEED_MM_MIN = 300


def validate_vertices(
    points: tuple[tuple[float, float], ...],
) -> None:
    if points[0] != (OUTER_LEFT_MM, OUTER_TOP_PHYSICAL_MM):
        raise AssertionError("unexpected standard spiral start")
    for point in points:
        if not (
            OUTER_LEFT_MM <= point[0] <= OUTER_RIGHT_MM
            and OUTER_BOTTOM_PHYSICAL_MM
            <= point[1]
            <= OUTER_TOP_PHYSICAL_MM
        ):
            raise AssertionError(f"standard spiral out of bounds: {point}")
    for start, end in zip(points, points[1:]):
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        if (abs(dx) <= 1.0e-9) == (abs(dy) <= 1.0e-9):
            raise AssertionError(
                f"source segment is not axis-aligned: {start}->{end}"
            )


def gcode_lines(
    points: tuple[tuple[float, float], ...],
) -> tuple[str, ...]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware_required={FIRMWARE_ID}",
        "; coordinates=STANDARD_A4_PHYSICAL_PAPER_MM",
        "; offline_mapping=NONE offline_prewarp=NONE",
        "; firmware_owns=BASE_MAP,SBOW_CORRECTION,YSHIFT15",
        f"; outer_size={OUTER_SIZE_MM:.1f}mm pitch={PITCH_MM:.1f}mm",
        f"; bounds=X{OUTER_LEFT_MM:.1f}..{OUTER_RIGHT_MM:.1f} "
        f"Y{OUTER_BOTTOM_PHYSICAL_MM:.1f}..{OUTER_TOP_PHYSICAL_MM:.1f}",
        "; one_continuous_pen_down_stroke=YES",
        "G21",
        "G90",
        "G94",
        f"F{FEED_MM_MIN}",
        "S1000",
        "M5",
        f"G0 X{points[0][0]:.3f} Y{points[0][1]:.3f}",
        "M3",
    ]
    lines.extend(
        f"G1 X{point[0]:.3f} Y{point[1]:.3f}"
        for point in points[1:]
    )
    lines.extend(("M5", "M5"))
    return tuple(lines)


def write_preview(
    points: tuple[tuple[float, float], ...],
) -> None:
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
        [shared.preview_xy(point) for point in points],
        fill=(25, 125, 60),
        width=3,
        joint="curve",
    )
    draw.text(
        (20, 18),
        "V63 standard-coordinate 160 mm square spiral for V29",
        fill=(30, 30, 30),
        font=shared.label_font(18),
    )
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def main() -> None:
    points = intended_physical_points()
    validate_vertices(points)
    lines = gcode_lines(points)
    text = "\n".join(lines) + "\n"
    GCODE_PATH.write_text(text, encoding="ascii", newline="\n")
    lengths = [
        math.dist(start, end)
        for start, end in zip(points, points[1:])
    ]
    manifest = {
        "id": TEST_ID,
        "required_firmware": FIRMWARE_ID,
        "coordinate_contract": {
            "units": "mm",
            "frame": "nominal physical A4 paper",
            "offline_mapping": False,
            "offline_prewarp": False,
            "firmware_mapping": True,
            "firmware_s_bow_correction": True,
        },
        "pattern": {
            "type": "open clockwise inward square spiral",
            "outer_size_mm": OUTER_SIZE_MM,
            "pitch_mm": PITCH_MM,
            "bounds_mm": [
                OUTER_LEFT_MM,
                OUTER_BOTTOM_PHYSICAL_MM,
                OUTER_RIGHT_MM,
                OUTER_TOP_PHYSICAL_MM,
            ],
            "vertex_count": len(points),
            "segment_count": len(points) - 1,
            "segment_length_range_mm": [min(lengths), max(lengths)],
            "all_source_segments_axis_aligned": True,
        },
        "motion": {
            "feed_mm_min": FEED_MM_MIN,
            "stroke_count": 1,
            "g0_count": 1,
            "g1_count": len(points) - 1,
            "firmware_draw_subdivision_max_mm": 1.0,
        },
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
    write_preview(points)
    print(
        "standard_full_width_spiral_v63=PASS "
        f"vertices={len(points)} G0=1 G1={len(points) - 1} "
        f"outer={OUTER_SIZE_MM:.1f}mm pitch={PITCH_MM:.1f}mm"
    )
    print(GCODE_PATH)
    print(PREVIEW_PATH)
    print(MANIFEST_PATH)


if __name__ == "__main__":
    main()
