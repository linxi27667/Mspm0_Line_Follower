#!/usr/bin/env python3
"""Generate the first calibrated production-style Chinese text sample."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from kenjoy_gfont import GFont, load_gfont, missing_characters


ROOT = Path(__file__).resolve().parents[1]
FONT_PATH = (
    ROOT / "assets" / "kenjoy_gfont" / "CHEN_HANDWRITING_cf5b1677.gfont"
)
GCODE_PATH = (
    ROOT
    / "gcode"
    / "PAPER_A4_ZHANG_JIA_LE_CHEN_HAND_32MM_TANGENT_GCODE_V30.gcode"
)
MANIFEST_PATH = (
    ROOT
    / "gcode"
    / "PAPER_A4_ZHANG_JIA_LE_CHEN_HAND_32MM_TANGENT_GCODE_V30.json"
)
PREVIEW_PATH = (
    ROOT
    / "docs"
    / "diagnostics"
    / "PAPER_A4_ZHANG_JIA_LE_CHEN_HAND_32MM_TANGENT_GCODE_V30_PREVIEW.png"
)

FONT_SHA256 = (
    "1B1D959A1B75106C8F94D1D95A9930FDF7DD54BA445C6CED0B84E55368F9644B"
)
TEXT = "张佳乐"
VISIBLE_HEIGHT_MM = 32.0
CHARACTER_GAP_MM = 7.0
ROW_CENTER_X_MM = 105.0
ROW_CENTER_Y_MM = 130.0
TANGENT_APPROACH_MM = 6.0
FEED_MM_MIN = 180

A4_WIDTH_MM = 210.0
A4_HEIGHT_MM = 297.0
PAPER_X_MIN_MM = 25.0
PAPER_X_MAX_MM = 185.0
PAPER_Y_MIN_MM = 20.0
PAPER_Y_MAX_MM = 240.333333
PREVIEW_PIXELS_PER_MM = 4.0


@dataclass(frozen=True)
class CharacterLayout:
    character: str
    bounds_mm: tuple[float, float, float, float]
    stroke_count: int


@dataclass(frozen=True)
class Stroke:
    character: str
    character_index: int
    stroke_index: int
    approach: tuple[float, float]
    points: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class Layout:
    font: GFont
    scale_mm_per_unit: float
    characters: tuple[CharacterLayout, ...]
    strokes: tuple[Stroke, ...]
    bounds_mm: tuple[float, float, float, float]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def label_font(size: int) -> ImageFont.ImageFont:
    candidates = (
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
    )
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def split_strokes(
    character: str,
    points: tuple[tuple[float, float], ...],
    commands: tuple[int, ...],
) -> list[tuple[tuple[float, float], ...]]:
    result: list[list[tuple[float, float]]] = []
    for point, command in zip(points, commands):
        if command == 0:
            result.append([point])
        elif not result:
            raise AssertionError(f"{character!r} begins with a draw command")
        elif math.dist(result[-1][-1], point) > 1.0e-9:
            result[-1].append(point)
    if any(len(stroke) < 2 for stroke in result):
        raise AssertionError(f"{character!r} contains an empty stroke")
    return [tuple(stroke) for stroke in result]


def build_layout() -> Layout:
    if digest(FONT_PATH) != FONT_SHA256:
        raise AssertionError("pinned Chen handwriting font hash changed")
    font = load_gfont(FONT_PATH)
    if font.name != "陈手写" or font.em_size != 400:
        raise AssertionError("unexpected pinned font metadata")
    missing = missing_characters(font, TEXT)
    if missing:
        raise AssertionError(f"font is missing: {missing}")

    glyphs = [font.glyphs[character] for character in TEXT]
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
    source_mid_y = (global_y_min + global_y_max) / 2.0
    baseline_y = ROW_CENTER_Y_MM - source_mid_y * scale

    characters: list[CharacterLayout] = []
    strokes: list[Stroke] = []
    for character_index, (character, glyph, width) in enumerate(
        zip(TEXT, glyphs, widths)
    ):
        source_x_min, source_y_min, source_x_max, source_y_max = glyph.bounds
        translate_x = cursor_x - source_x_min * scale

        transformed_points = tuple(
            (
                translate_x + x_value * scale,
                baseline_y + y_value * scale,
            )
            for x_value, y_value in glyph.points
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
            baseline_y + source_y_min * scale,
            cursor_x + width,
            baseline_y + source_y_max * scale,
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
        round(
            (A4_HEIGHT_MM - point[1]) * PREVIEW_PIXELS_PER_MM
        ),
    )


def draw_dashed_line(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    fill: tuple[int, int, int],
    width: int,
    dash_px: int = 8,
) -> None:
    distance = math.dist(start, end)
    if distance <= 0.0:
        return
    ux = (end[0] - start[0]) / distance
    uy = (end[1] - start[1]) / distance
    position = 0.0
    while position < distance:
        segment_end = min(position + dash_px, distance)
        draw.line(
            (
                start[0] + ux * position,
                start[1] + uy * position,
                start[0] + ux * segment_end,
                start[1] + uy * segment_end,
            ),
            fill=fill,
            width=width,
        )
        position += dash_px * 2


def write_preview(layout: Layout) -> None:
    width = round(A4_WIDTH_MM * PREVIEW_PIXELS_PER_MM) + 1
    height = round(A4_HEIGHT_MM * PREVIEW_PIXELS_PER_MM) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, height - 1), outline=(25, 25, 25), width=3)

    calibrated_top_left = preview_xy(
        (PAPER_X_MIN_MM, PAPER_Y_MAX_MM)
    )
    calibrated_bottom_right = preview_xy(
        (PAPER_X_MAX_MM, PAPER_Y_MIN_MM)
    )
    draw.rectangle(
        (
            calibrated_top_left[0],
            calibrated_top_left[1],
            calibrated_bottom_right[0],
            calibrated_bottom_right[1],
        ),
        outline=(130, 160, 195),
        width=2,
    )

    title = label_font(24)
    small = label_font(17)
    draw.text(
        (20, 16),
        "V30 正式单线试写：张佳乐（陈手写，约 32 mm）",
        fill=(20, 20, 20),
        font=title,
    )
    draw.text(
        (20, 50),
        "黑线=落笔轨迹  蓝虚线=6 mm 抬笔切线预接近  红点=落笔起点",
        fill=(70, 70, 70),
        font=small,
    )

    for character in layout.characters:
        top_left = preview_xy(
            (character.bounds_mm[0], character.bounds_mm[3])
        )
        bottom_right = preview_xy(
            (character.bounds_mm[2], character.bounds_mm[1])
        )
        draw.rectangle(
            (
                top_left[0],
                top_left[1],
                bottom_right[0],
                bottom_right[1],
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
        previous = start_px
        for point in stroke.points[1:]:
            current = preview_xy(point)
            draw.line((*previous, *current), fill=(15, 15, 15), width=3)
            previous = current
        draw.ellipse(
            (
                start_px[0] - 3,
                start_px[1] - 3,
                start_px[0] + 3,
                start_px[1] + 3,
            ),
            fill=(195, 35, 35),
        )

    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def write_manifest(layout: Layout, lines: tuple[str, ...]) -> None:
    gcode_text = "\n".join(lines) + "\n"
    manifest = {
        "id": "PAPER_A4_ZHANG_JIA_LE_CHEN_HAND_32MM_TANGENT_GCODE_V30",
        "text": TEXT,
        "font": {
            "file": FONT_PATH.name,
            "sha256": FONT_SHA256,
            "name": layout.font.name,
            "em_size": layout.font.em_size,
            "glyph_count": len(layout.font.glyphs),
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
            "g1_count": sum(len(stroke.points) - 1 for stroke in layout.strokes),
        },
        "gcode": {
            "file": GCODE_PATH.name,
            "line_count": len(lines),
            "sha256": hashlib.sha256(
                gcode_text.encode("ascii")
            ).hexdigest().upper(),
        },
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    raise RuntimeError(
        "V30 is invalid: gfont Y was reversed. Generate V31 instead."
    )
    layout = build_layout()
    lines = gcode_lines(layout)
    gcode_text = "\n".join(lines) + "\n"
    GCODE_PATH.write_text(gcode_text, encoding="ascii")
    write_preview(layout)
    write_manifest(layout, lines)
    print(
        "generated_zhang_jia_le_v30=PASS "
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
