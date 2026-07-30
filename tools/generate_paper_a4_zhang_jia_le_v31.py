#!/usr/bin/env python3
"""Generate upright 张佳乐 from an unmodified Kenjoy single-line font."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

from generate_paper_a4_zhang_jia_le_v30 import (
    A4_HEIGHT_MM,
    A4_WIDTH_MM,
    CHARACTER_GAP_MM,
    FEED_MM_MIN,
    PAPER_X_MAX_MM,
    PAPER_X_MIN_MM,
    PAPER_Y_MAX_MM,
    PAPER_Y_MIN_MM,
    PREVIEW_PIXELS_PER_MM,
    ROW_CENTER_X_MM,
    ROW_CENTER_Y_MM,
    TANGENT_APPROACH_MM,
    VISIBLE_HEIGHT_MM,
    CharacterLayout,
    Layout,
    Stroke,
    digest,
    draw_dashed_line,
    label_font,
    split_strokes,
)
from kenjoy_gfont import load_gfont, missing_characters


ROOT = Path(__file__).resolve().parents[1]
FONT_PATH = (
    ROOT
    / "assets"
    / "kenjoy_gfont"
    / "AA_GUO_JINGMING_b7c9ccc1.gfont"
)
GCODE_PATH = (
    ROOT
    / "gcode"
    / "PAPER_A4_ZHANG_JIA_LE_AA_GUO_32MM_TANGENT_GCODE_V31.gcode"
)
MANIFEST_PATH = (
    ROOT
    / "gcode"
    / "PAPER_A4_ZHANG_JIA_LE_AA_GUO_32MM_TANGENT_GCODE_V31.json"
)
PREVIEW_PATH = (
    ROOT
    / "docs"
    / "diagnostics"
    / "PAPER_A4_ZHANG_JIA_LE_AA_GUO_32MM_TANGENT_GCODE_V31_PREVIEW.png"
)

FONT_SHA256 = (
    "D5D8E41EF24BF380FDAB57B4746795D691CC4E2DF878A394E4FA8C6D594C09F8"
)
FONT_NAME = "aa郭敬明字体"
FONT_EM_SIZE = 525
TEXT = "张佳乐"
EXPECTED_STROKE_COUNTS = (7, 8, 5)


def build_layout_from_gfont(
    font_path: Path,
    font_sha256: str,
    font_name: str,
    font_em_size: int,
    expected_stroke_counts: tuple[int, ...],
    row_center_y_mm: float = ROW_CENTER_Y_MM,
) -> Layout:
    if digest(font_path) != font_sha256:
        raise AssertionError("pinned gfont hash changed")
    font = load_gfont(font_path)
    if font.name != font_name or font.em_size != font_em_size:
        raise AssertionError("unexpected pinned font metadata")
    missing = missing_characters(font, TEXT)
    if missing:
        raise AssertionError(f"font is missing: {missing}")

    glyphs = [font.glyphs[character] for character in TEXT]
    stroke_counts = tuple(glyph.stroke_count for glyph in glyphs)
    if stroke_counts != expected_stroke_counts:
        raise AssertionError(
            f"font stroke counts changed: {stroke_counts}"
        )

    global_y_min = min(glyph.bounds[1] for glyph in glyphs)
    global_y_max = max(glyph.bounds[3] for glyph in glyphs)
    source_height = global_y_max - global_y_min
    if source_height <= 0.0:
        raise AssertionError("empty text height")
    scale = VISIBLE_HEIGHT_MM / source_height

    widths = [
        (glyph.bounds[2] - glyph.bounds[0]) * scale for glyph in glyphs
    ]
    total_width = sum(widths) + CHARACTER_GAP_MM * (len(glyphs) - 1)
    cursor_x = ROW_CENTER_X_MM - total_width / 2.0

    # Kenjoy gfont uses +Y down.  The calibrated paper contract uses +Y up.
    # This sign inversion is mandatory; V30 omitted it and wrote upside-down.
    source_mid_y = (global_y_min + global_y_max) / 2.0
    baseline_y = row_center_y_mm + source_mid_y * scale

    characters: list[CharacterLayout] = []
    strokes: list[Stroke] = []
    for character_index, (character, glyph, width) in enumerate(
        zip(TEXT, glyphs, widths)
    ):
        source_x_min, source_y_min, source_x_max, source_y_max = glyph.bounds
        translate_x = cursor_x - source_x_min * scale
        transformed_points = tuple(
            (
                translate_x + source_x * scale,
                baseline_y - source_y * scale,
            )
            for source_x, source_y in glyph.points
        )
        transformed_strokes = split_strokes(
            character, transformed_points, glyph.commands
        )
        for stroke_index, points in enumerate(
            transformed_strokes, start=1
        ):
            first_length = math.dist(points[0], points[1])
            if first_length <= 1.0e-6:
                raise AssertionError(
                    f"{character!r} stroke {stroke_index} has no direction"
                )
            unit = (
                (points[1][0] - points[0][0]) / first_length,
                (points[1][1] - points[0][1]) / first_length,
            )
            approach = (
                points[0][0] - unit[0] * TANGENT_APPROACH_MM,
                points[0][1] - unit[1] * TANGENT_APPROACH_MM,
            )
            strokes.append(
                Stroke(
                    character,
                    character_index,
                    stroke_index,
                    approach,
                    points,
                )
            )

        bounds_mm = (
            cursor_x,
            baseline_y - source_y_max * scale,
            cursor_x + width,
            baseline_y - source_y_min * scale,
        )
        characters.append(
            CharacterLayout(character, bounds_mm, len(transformed_strokes))
        )
        cursor_x += width + CHARACTER_GAP_MM

    all_points = [
        point
        for stroke in strokes
        for point in (stroke.approach, *stroke.points)
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
            raise AssertionError(f"layout point out of bounds: {point}")

    return Layout(
        font,
        scale,
        tuple(characters),
        tuple(strokes),
        bounds,
    )


def build_layout() -> Layout:
    return build_layout_from_gfont(
        FONT_PATH,
        FONT_SHA256,
        FONT_NAME,
        FONT_EM_SIZE,
        EXPECTED_STROKE_COUNTS,
    )


def gcode_lines(layout: Layout) -> tuple[str, ...]:
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


def preview_xy(point: tuple[float, float]) -> tuple[int, int]:
    return (
        round(point[0] * PREVIEW_PIXELS_PER_MM),
        round((A4_HEIGHT_MM - point[1]) * PREVIEW_PIXELS_PER_MM),
    )


def write_preview(layout: Layout) -> None:
    width = round(A4_WIDTH_MM * PREVIEW_PIXELS_PER_MM) + 1
    height = round(A4_HEIGHT_MM * PREVIEW_PIXELS_PER_MM) + 1
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
        "V31 字库原字试写：张佳乐（aa郭敬明字体，约 32 mm）",
        fill=(20, 20, 20),
        font=label_font(24),
    )
    draw.text(
        (20, 50),
        "黑线=字库原始落笔轨迹  蓝虚线=6 mm抬笔预接近  红点=字库起点",
        fill=(70, 70, 70),
        font=label_font(17),
    )

    for character in layout.characters:
        draw.rectangle(
            (
                *preview_xy(
                    (character.bounds_mm[0], character.bounds_mm[3])
                ),
                *preview_xy(
                    (character.bounds_mm[2], character.bounds_mm[1])
                ),
            ),
            outline=(225, 225, 225),
            width=1,
        )

    for stroke in layout.strokes:
        approach_px = preview_xy(stroke.approach)
        start_px = preview_xy(stroke.points[0])
        draw_dashed_line(
            draw, approach_px, start_px, (45, 115, 185), width=2
        )
        points_px = [preview_xy(point) for point in stroke.points]
        draw.line(points_px, fill=(15, 15, 15), width=3, joint="curve")
        draw.ellipse(
            (
                start_px[0] - 3,
                start_px[1] - 3,
                start_px[0] + 3,
                start_px[1] + 3,
            ),
            fill=(195, 35, 35),
        )
        draw.text(
            (start_px[0] + 4, start_px[1] - 11),
            str(stroke.stroke_index),
            fill=(170, 35, 35),
            font=label_font(11),
        )

    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def write_manifest(layout: Layout, lines: tuple[str, ...]) -> None:
    gcode_text = "\n".join(lines) + "\n"
    manifest = {
        "id": "PAPER_A4_ZHANG_JIA_LE_AA_GUO_32MM_TANGENT_GCODE_V31",
        "supersedes": {
            "id": "PAPER_A4_ZHANG_JIA_LE_CHEN_HAND_32MM_TANGENT_GCODE_V30",
            "reason": "V30 interpreted gfont +Y in the wrong direction",
        },
        "text": TEXT,
        "font": {
            "file": FONT_PATH.name,
            "sha256": FONT_SHA256,
            "name": layout.font.name,
            "em_size": layout.font.em_size,
            "glyph_count": len(layout.font.glyphs),
            "geometry": "unmodified gfont path points and command order",
        },
        "coordinate_contract": {
            "gfont_y": "positive downward",
            "paper_y": "positive upward",
            "transform_y": "paper_y = baseline_y - source_y * scale",
        },
        "layout": {
            "visible_height_mm": VISIBLE_HEIGHT_MM,
            "character_gap_mm": CHARACTER_GAP_MM,
            "row_center_mm": [ROW_CENTER_X_MM, ROW_CENTER_Y_MM],
            "scale_mm_per_font_unit": layout.scale_mm_per_unit,
            "bounds_mm": list(layout.bounds_mm),
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
        "generated_zhang_jia_le_v31=PASS "
        f"font={layout.font.name} text={TEXT} "
        f"strokes={len(layout.strokes)} "
        f"G1={sum(len(stroke.points) - 1 for stroke in layout.strokes)} "
        f"bounds_x={layout.bounds_mm[0]:.3f}..{layout.bounds_mm[2]:.3f} "
        f"bounds_y={layout.bounds_mm[1]:.3f}..{layout.bounds_mm[3]:.3f}"
    )
    print(GCODE_PATH)
    print(PREVIEW_PATH)
    print(MANIFEST_PATH)


if __name__ == "__main__":
    main()
