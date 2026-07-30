#!/usr/bin/env python3
"""Render every complete local gfont with simulated physical pen width."""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from generate_paper_a4_zhang_jia_le_v30 import split_strokes
from kenjoy_gfont import GFont, load_gfont, missing_characters


OUTPUT = (
    ROOT / "docs" / "diagnostics"
    / "FULL_GFONT_WRITER_TEST_8MM_PENWIDTH_CANDIDATES_V67.png"
)
REQUESTED_TEXT = (
    "\u5199\u5b57\u673a\u7b2c\u597d\u591a\u6b21\u6d4b\u8bd5"
    "\uff0c7.25  5.23am"
)
RENDERED_TEXT = REQUESTED_TEXT.replace(".", "\u3002")

VISIBLE_HEIGHT_MM = 8.0
CHARACTER_GAP_MM = 1.1
SPACE_ADVANCE_MM = 2.8
PIXELS_PER_MM = 12.0
SIMULATED_PEN_WIDTH_MM = 0.45
LABEL_WIDTH_PX = 330
ROW_HEIGHT_PX = 150
MARGIN_PX = 18


@dataclass(frozen=True)
class Candidate:
    path: Path
    font: GFont
    sha256: str
    strokes: int
    points: int


def label_font(size: int) -> ImageFont.ImageFont:
    for path in (
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
    ):
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def candidates() -> tuple[Candidate, ...]:
    result = []
    seen_hashes: set[str] = set()
    for path in sorted((Path.home() / "Downloads").rglob("*.gfont")):
        sha256 = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        if sha256 in seen_hashes:
            continue
        seen_hashes.add(sha256)
        font = load_gfont(path)
        if missing_characters(font, RENDERED_TEXT):
            continue
        visible = [
            font.glyphs[character]
            for character in RENDERED_TEXT
            if not character.isspace()
        ]
        result.append(
            Candidate(
                path,
                font,
                sha256,
                sum(glyph.stroke_count for glyph in visible),
                sum(len(glyph.points) for glyph in visible),
            )
        )
    return tuple(result)


def draw_candidate(
    draw: ImageDraw.ImageDraw,
    candidate: Candidate,
    row_index: int,
) -> tuple[float, float]:
    top_px = MARGIN_PX + row_index * ROW_HEIGHT_PX
    font = candidate.font
    glyphs = [
        font.glyphs[character]
        for character in RENDERED_TEXT
        if not character.isspace()
    ]
    global_y_min = min(glyph.bounds[1] for glyph in glyphs)
    global_y_max = max(glyph.bounds[3] for glyph in glyphs)
    scale = VISIBLE_HEIGHT_MM / (global_y_max - global_y_min)

    draw.text(
        (MARGIN_PX, top_px + 12),
        font.name,
        fill=(20, 20, 20),
        font=label_font(23),
    )
    draw.text(
        (MARGIN_PX, top_px + 47),
        f"strokes={candidate.strokes} points={candidate.points}",
        fill=(75, 75, 75),
        font=label_font(15),
    )
    draw.text(
        (MARGIN_PX, top_px + 72),
        candidate.path.name[:34],
        fill=(105, 105, 105),
        font=label_font(12),
    )

    cursor_x_mm = 0.0
    origin_x = LABEL_WIDTH_PX
    origin_y = top_px + 25
    line_width = max(
        1, round(SIMULATED_PEN_WIDTH_MM * PIXELS_PER_MM)
    )
    for character in RENDERED_TEXT:
        if character.isspace():
            cursor_x_mm += SPACE_ADVANCE_MM
            continue
        glyph = font.glyphs[character]
        source_x_min, _, source_x_max, _ = glyph.bounds
        width_mm = (source_x_max - source_x_min) * scale
        points = tuple(
            (
                origin_x
                + (
                    cursor_x_mm
                    + (source_x - source_x_min) * scale
                ) * PIXELS_PER_MM,
                origin_y
                + (source_y - global_y_min)
                * scale * PIXELS_PER_MM,
            )
            for source_x, source_y in glyph.points
        )
        for stroke in split_strokes(
            character, points, glyph.commands
        ):
            draw.line(
                stroke,
                fill=(12, 12, 12),
                width=line_width,
                joint="curve",
            )
        cursor_x_mm += width_mm + CHARACTER_GAP_MM
    return cursor_x_mm, VISIBLE_HEIGHT_MM


def main() -> None:
    rows = candidates()
    if not rows:
        raise AssertionError("no complete local gfonts")
    width = 1900
    height = MARGIN_PX * 2 + ROW_HEIGHT_PX * len(rows)
    image = Image.new("RGB", (width, height), (248, 249, 251))
    draw = ImageDraw.Draw(image)
    draw.text(
        (MARGIN_PX, 2),
        "8 mm single-line gfont candidates / simulated 0.45 mm pen",
        fill=(35, 35, 35),
        font=label_font(14),
    )
    for index, candidate in enumerate(rows):
        draw_candidate(draw, candidate, index)
        y = MARGIN_PX + (index + 1) * ROW_HEIGHT_PX - 6
        draw.line((MARGIN_PX, y, width - MARGIN_PX, y),
                  fill=(205, 210, 218), width=1)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT)
    print(
        f"full_gfont_candidates_v67=PASS candidates={len(rows)} "
        f"height_mm={VISIBLE_HEIGHT_MM} "
        f"pen_width_mm={SIMULATED_PEN_WIDTH_MM}"
    )
    for index, candidate in enumerate(rows, start=1):
        print(
            f"{index:02d} "
            f"name={candidate.font.name.encode('unicode_escape').decode()} "
            f"strokes={candidate.strokes} points={candidate.points} "
            f"file={candidate.path.name} sha256={candidate.sha256}"
        )
    print(OUTPUT)


if __name__ == "__main__":
    main()
