#!/usr/bin/env python3
"""Generate the V42 direct-coordinate Song-font 张佳乐 sample."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import generate_paper_a4_zhang_jia_le_v31 as layout_base
import generate_paper_a4_zhang_jia_le_v32 as song
from generate_paper_a4_map_vs_cartesian_circle_v36 import (
    mapped,
    mapping_model,
)


ROOT = Path(__file__).resolve().parents[1]
TEST_ID = "PAPER_A4_ZHANG_JIA_LE_SONG_32MM_DIRECT_MAP_GCODE_V42"
BUILD_ID = "PAPER_A4_CONTINUOUS_QUEUE_SAFE_HOME_GCODE_V27"
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"

ROW_CENTER_Y_MM = 150.0
PAPER_SUBDIVISION_MM = 1.0
FONT_PATH = song.FONT_PATH
FONT_SHA256 = song.FONT_SHA256
FONT_NAME = song.FONT_NAME
FONT_EM_SIZE = song.FONT_EM_SIZE
TEXT = song.TEXT
EXPECTED_STROKE_COUNTS = song.EXPECTED_STROKE_COUNTS
FEED_MM_MIN = song.FEED_MM_MIN
TANGENT_APPROACH_MM = song.TANGENT_APPROACH_MM

MAP_COEFFICIENTS, MAP_TOTAL_DELTA = mapping_model()


def build_layout() -> layout_base.Layout:
    return layout_base.build_layout_from_gfont(
        FONT_PATH,
        FONT_SHA256,
        FONT_NAME,
        FONT_EM_SIZE,
        EXPECTED_STROKE_COUNTS,
        ROW_CENTER_Y_MM,
    )


def map_paper(point: tuple[float, float]) -> tuple[float, float]:
    result = mapped(point, MAP_COEFFICIENTS, MAP_TOTAL_DELTA)
    return float(result[0]), float(result[1])


def subdivide_points(
    points: tuple[tuple[float, float], ...],
) -> tuple[tuple[float, float], ...]:
    result = [points[0]]
    for start, end in zip(points, points[1:]):
        length = math.dist(start, end)
        if length <= 1.0e-9:
            raise AssertionError("Song source path contains a zero segment")
        count = max(1, math.ceil(length / PAPER_SUBDIVISION_MM))
        result.extend(
            (
                start[0] + (end[0] - start[0]) * index / count,
                start[1] + (end[1] - start[1]) * index / count,
            )
            for index in range(1, count + 1)
        )
    return tuple(result)


def command_plan(
    layout: layout_base.Layout,
) -> tuple[
    tuple[
        layout_base.Stroke,
        tuple[tuple[float, float], ...],
        tuple[tuple[float, float], ...],
    ],
    ...,
]:
    plan = []
    for stroke in layout.strokes:
        paper_points = subdivide_points(stroke.points)
        user_points = tuple(map_paper(point) for point in paper_points)
        plan.append((stroke, paper_points, user_points))
    return tuple(plan)


def gcode_lines(layout: layout_base.Layout) -> tuple[str, ...]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware={BUILD_ID}",
        f"; source_font={FONT_PATH.name} font_sha256={FONT_SHA256}",
        "; text=ZHANG_JIA_LE font=SONG source_geometry=UNMODIFIED",
        "; firmware_paper_map=DISABLED offline_pointwise_map=ENABLED",
        f"; paper_center=(105,{ROW_CENTER_Y_MM:.0f}) "
        "visible_height=32mm new_blank_A4=REQUIRED",
        f"; paper_subdivision_max={PAPER_SUBDIVISION_MM:.1f}mm",
        "G21",
        "G90",
        "G94",
        f"F{FEED_MM_MIN}",
        "S1000",
        "M5",
    ]
    for stroke, _, user_points in command_plan(layout):
        approach_user = map_paper(stroke.approach)
        start_user = user_points[0]
        lines.extend(
            (
                f"; char_index={stroke.character_index + 1} "
                f"stroke={stroke.stroke_index}",
                f"G0 X{approach_user[0]:.3f} Y{approach_user[1]:.3f}",
                f"G0 X{start_user[0]:.3f} Y{start_user[1]:.3f}",
                "M3",
            )
        )
        lines.extend(
            f"G1 X{point[0]:.3f} Y{point[1]:.3f}"
            for point in user_points[1:]
        )
        lines.append("M5")
    return tuple(lines)


def write_manifest(
    layout: layout_base.Layout,
    lines: tuple[str, ...],
) -> None:
    plan = command_plan(layout)
    source_lengths = [
        math.dist(start, end)
        for stroke in layout.strokes
        for start, end in zip(stroke.points, stroke.points[1:])
    ]
    sampled_lengths = [
        math.dist(start, end)
        for _, paper_points, _ in plan
        for start, end in zip(paper_points, paper_points[1:])
    ]
    command_points = [
        point
        for stroke, _, user_points in plan
        for point in (map_paper(stroke.approach), *user_points)
    ]
    text = "\n".join(lines) + "\n"
    manifest = {
        "id": TEST_ID,
        "required_firmware": BUILD_ID,
        "text": TEXT,
        "font": {
            "file": FONT_PATH.name,
            "sha256": FONT_SHA256,
            "name": layout.font.name,
            "em_size": layout.font.em_size,
            "glyph_count": len(layout.font.glyphs),
            "geometry": "unmodified gfont path points and command order",
            "character_path_counts": list(EXPECTED_STROKE_COUNTS),
        },
        "coordinate_contract": {
            "gfont_y": "positive downward",
            "paper_y": "positive upward",
            "transform_y": "paper_y = baseline_y - source_y * scale",
            "firmware_paper_map_enabled": False,
            "offline_pointwise_paper_to_user_map_enabled": True,
        },
        "layout": {
            "new_blank_a4_required": True,
            "row_center_mm": [layout_base.ROW_CENTER_X_MM, ROW_CENTER_Y_MM],
            "visible_height_mm": layout_base.VISIBLE_HEIGHT_MM,
            "bounds_with_penup_approaches_paper_mm": list(layout.bounds_mm),
            "characters": [
                {
                    "character": item.character,
                    "bounds_mm": list(item.bounds_mm),
                    "stroke_count": item.stroke_count,
                }
                for item in layout.characters
            ],
        },
        "motion": {
            "feed_mm_min": FEED_MM_MIN,
            "tangent_approach_mm": TANGENT_APPROACH_MM,
            "paper_subdivision_max_mm": PAPER_SUBDIVISION_MM,
            "stroke_count": len(layout.strokes),
            "g1_count": sum(
                len(user_points) - 1 for _, _, user_points in plan
            ),
            "source_segment_mm": [
                min(source_lengths),
                max(source_lengths),
            ],
            "sampled_paper_segment_mm": [
                min(sampled_lengths),
                max(sampled_lengths),
            ],
            "command_user_bounds_mm": [
                min(point[0] for point in command_points),
                min(point[1] for point in command_points),
                max(point[0] for point in command_points),
                max(point[1] for point in command_points),
            ],
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


def main() -> None:
    layout = build_layout()
    lines = gcode_lines(layout)
    GCODE_PATH.write_text(
        "\n".join(lines) + "\n",
        encoding="ascii",
        newline="\n",
    )
    song.write_preview(
        layout,
        preview_path=PREVIEW_PATH,
        version_label="V42 宋体原字：新白纸居中，V27 离线映射",
    )
    write_manifest(layout, lines)
    plan = command_plan(layout)
    print(
        "generated_zhang_jia_le_song_v42=PASS "
        f"font={layout.font.name} text={TEXT} "
        f"strokes={len(layout.strokes)} "
        f"G1={sum(len(points) - 1 for _, _, points in plan)} "
        f"paper_bounds_x={layout.bounds_mm[0]:.3f}.."
        f"{layout.bounds_mm[2]:.3f} "
        f"paper_bounds_y={layout.bounds_mm[1]:.3f}.."
        f"{layout.bounds_mm[3]:.3f}"
    )
    print(GCODE_PATH)
    print(PREVIEW_PATH)
    print(MANIFEST_PATH)


if __name__ == "__main__":
    main()
