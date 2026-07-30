#!/usr/bin/env python3
"""Render the same text from every local Kenjoy .gfont for visual selection."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from kenjoy_gfont import Glyph, load_gfont, missing_characters


CELL_WIDTH = 620
CELL_HEIGHT = 330
COLUMNS = 3
MARGIN = 24
LABEL_HEIGHT = 70
TEXT = "张佳乐"


def label_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in (
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
    ):
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def split_strokes(glyph: Glyph) -> list[tuple[tuple[float, float], ...]]:
    strokes: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for point, command in zip(glyph.points, glyph.commands):
        if command == 0:
            if current:
                strokes.append(current)
            current = [point]
        else:
            current.append(point)
    if current:
        strokes.append(current)
    return [tuple(stroke) for stroke in strokes if len(stroke) >= 2]


def draw_font_cell(
    draw: ImageDraw.ImageDraw,
    cell_x: int,
    cell_y: int,
    font_path: Path,
) -> None:
    font = load_gfont(font_path)
    missing = missing_characters(font, TEXT)
    title = f"{font.name}  em={font.em_size}"
    detail = font_path.name
    draw.rounded_rectangle(
        (
            cell_x,
            cell_y,
            cell_x + CELL_WIDTH - MARGIN,
            cell_y + CELL_HEIGHT - MARGIN,
        ),
        radius=12,
        outline=(165, 180, 200),
        width=2,
    )
    draw.text(
        (cell_x + 16, cell_y + 10),
        title,
        fill=(25, 25, 25),
        font=label_font(24),
    )
    draw.text(
        (cell_x + 16, cell_y + 42),
        detail,
        fill=(90, 90, 90),
        font=label_font(13),
    )
    if missing:
        draw.text(
            (cell_x + 16, cell_y + 100),
            f"缺字：{missing}",
            fill=(190, 35, 35),
            font=label_font(24),
        )
        return

    glyphs = [font.glyphs[character] for character in TEXT]
    x_mins = [glyph.bounds[0] for glyph in glyphs]
    x_maxs = [glyph.bounds[2] for glyph in glyphs]
    y_min = min(glyph.bounds[1] for glyph in glyphs)
    y_max = max(glyph.bounds[3] for glyph in glyphs)
    gap_source = font.em_size * 0.12
    source_width = sum(
        x_max - x_min for x_min, x_max in zip(x_mins, x_maxs)
    ) + gap_source * (len(glyphs) - 1)
    source_height = y_max - y_min
    available_width = CELL_WIDTH - MARGIN - 40
    available_height = CELL_HEIGHT - MARGIN - LABEL_HEIGHT - 30
    scale = min(
        available_width / source_width,
        available_height / source_height,
    )
    content_width = source_width * scale
    content_height = source_height * scale
    cursor_x = (
        cell_x + (CELL_WIDTH - MARGIN - content_width) / 2.0
    )
    top_y = cell_y + LABEL_HEIGHT + (
        CELL_HEIGHT - MARGIN - LABEL_HEIGHT - content_height
    ) / 2.0

    for character, glyph, x_min, x_max in zip(
        TEXT, glyphs, x_mins, x_maxs
    ):
        for stroke in split_strokes(glyph):
            points = [
                (
                    cursor_x + (point[0] - x_min) * scale,
                    top_y + (point[1] - y_min) * scale,
                )
                for point in stroke
            ]
            draw.line(points, fill=(12, 12, 12), width=3, joint="curve")
            start_x, start_y = points[0]
            draw.ellipse(
                (
                    start_x - 2,
                    start_y - 2,
                    start_x + 2,
                    start_y + 2,
                ),
                fill=(210, 35, 35),
            )
        cursor_x += (x_max - x_min + gap_source) * scale

    counts = "/".join(str(glyph.stroke_count) for glyph in glyphs)
    draw.text(
        (cell_x + CELL_WIDTH - MARGIN - 130, cell_y + 14),
        f"路径 {counts}",
        fill=(80, 80, 80),
        font=label_font(15),
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("font_directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    font_paths = sorted(
        args.font_directory.glob("*.gfont"),
        key=lambda item: item.name.lower(),
    )
    rows = (len(font_paths) + COLUMNS - 1) // COLUMNS
    image = Image.new(
        "RGB",
        (CELL_WIDTH * COLUMNS, CELL_HEIGHT * rows),
        (245, 246, 248),
    )
    draw = ImageDraw.Draw(image)
    for index, font_path in enumerate(font_paths):
        draw_font_cell(
            draw,
            (index % COLUMNS) * CELL_WIDTH + MARGIN // 2,
            (index // COLUMNS) * CELL_HEIGHT + MARGIN // 2,
            font_path,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output)
    print(f"fonts={len(font_paths)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
