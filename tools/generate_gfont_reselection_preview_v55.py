#!/usr/bin/env python3
"""Render comparable 9 mm previews for the remaining original gfonts."""

from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageDraw

from generate_paper_a4_zhang_jia_le_v30 import label_font, split_strokes
from kenjoy_gfont import load_gfont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "docs"
    / "diagnostics"
    / "GFONT_RESELECTION_ZHANGJIALE_9MM_V55.png"
)
TEXT = "\u5f20\u4f73\u4e50\u4f5c\u54c1"
VISIBLE_HEIGHT_MM = 9.0
GAP_MM = 1.875
PIXELS_PER_MM = 9.0

OPTIONS = (
    (
        "A",
        "CHEN_HANDWRITING_cf5b1677.gfont",
        "1B1D959A1B75106C8F94D1D95A9930FDF7DD54BA445C6CED0B84E55368F9644B",
    ),
    (
        "B",
        "AA_GUO_JINGMING_b7c9ccc1.gfont",
        "D5D8E41EF24BF380FDAB57B4746795D691CC4E2DF878A394E4FA8C6D594C09F8",
    ),
    (
        "C",
        "MEIYOU_RUGUO_e31cdaaa.gfont",
        "569C56EE629D29E1F1172D66F1FE8205E810801A6437FA8490006FE1CB3DD6D6",
    ),
    (
        "D",
        "SONG_ec900461.gfont",
        "A74332F3F53C77B02DE6637ED8AAF0D5010E61444B1216D3E291A6AEA1419C24",
    ),
)


def render_option(
    draw: ImageDraw.ImageDraw,
    option: str,
    file_name: str,
    expected_hash: str,
    row_top: int,
) -> None:
    path = ROOT / "assets" / "kenjoy_gfont" / file_name
    actual_hash = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    if actual_hash != expected_hash:
        raise AssertionError(f"font hash changed: {file_name}")
    font = load_gfont(path)
    glyphs = [font.glyphs[character] for character in TEXT]
    global_y_min = min(glyph.bounds[1] for glyph in glyphs)
    global_y_max = max(glyph.bounds[3] for glyph in glyphs)
    scale = VISIBLE_HEIGHT_MM / (global_y_max - global_y_min)
    path_count = sum(glyph.stroke_count for glyph in glyphs)

    draw.rounded_rectangle(
        (20, row_top, 1178, row_top + 155),
        radius=12,
        outline=(175, 185, 195),
        width=2,
        fill=(252, 253, 254),
    )
    draw.text(
        (42, row_top + 24),
        f"{option}. {font.name}",
        fill=(25, 25, 25),
        font=label_font(28),
    )
    draw.text(
        (42, row_top + 70),
        f"原始字库路径数：{path_count}",
        fill=(90, 90, 90),
        font=label_font(18),
    )

    cursor_x_mm = 0.0
    origin_x = 420.0
    origin_y = row_top + 38.0
    for character, glyph in zip(TEXT, glyphs):
        x_min, _, x_max, _ = glyph.bounds
        width_mm = (x_max - x_min) * scale
        points = tuple(
            (
                origin_x
                + (cursor_x_mm + (source_x - x_min) * scale)
                * PIXELS_PER_MM,
                origin_y
                + (source_y - global_y_min)
                * scale
                * PIXELS_PER_MM,
            )
            for source_x, source_y in glyph.points
        )
        strokes = split_strokes(character, points, glyph.commands)
        for stroke in strokes:
            if len(stroke) >= 2:
                draw.line(
                    stroke,
                    fill=(15, 15, 15),
                    width=3,
                    joint="curve",
                )
        cursor_x_mm += width_mm + GAP_MM


def main() -> None:
    image = Image.new("RGB", (1200, 740), "white")
    draw = ImageDraw.Draw(image)
    draw.text(
        (24, 18),
        "“张佳乐作品”原始字库 9 mm 等比例对比",
        fill=(20, 20, 20),
        font=label_font(30),
    )
    draw.text(
        (24, 62),
        "当前“吸口雾霾压压惊”已停用；请从 A–D 重新选择",
        fill=(95, 95, 95),
        font=label_font(19),
    )
    for index, option in enumerate(OPTIONS):
        render_option(draw, *option, row_top=105 + index * 158)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT)
    print(f"gfont_reselection_preview_v55=PASS options={len(OPTIONS)}")
    print(OUTPUT)


if __name__ == "__main__":
    main()
