#!/usr/bin/env python3
"""Generate a third-line 9 mm sample using the 没有如果 hand font."""

from __future__ import annotations

import hashlib
import json
import math

from PIL import Image, ImageDraw

import generate_paper_a4_top_left_song_12mm_v43 as shared
from kenjoy_gfont import load_gfont, missing_characters


TEST_ID = "PAPER_A4_TOP_LEFT_MEIYOU_RUGUO_9MM_SAMPLE_GCODE_V45"
BUILD_ID = shared.BUILD_ID
GCODE_PATH = shared.ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = shared.ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = (
    shared.ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"
)

FONT_PATH = (
    shared.ROOT
    / "assets"
    / "kenjoy_gfont"
    / "MEIYOU_RUGUO_e31cdaaa.gfont"
)
FONT_SHA256 = (
    "569C56EE629D29E1F1172D66F1FE8205E810801A6437FA8490006FE1CB3DD6D6"
)
FONT_NAME = "没有如果"
FONT_TAG = "MEIYOU_RUGUO"
FONT_EM_SIZE = 600
TEXT = "张佳乐作品"
EXPECTED_STROKE_COUNTS = (7, 8, 4, 7, 9)

VISIBLE_HEIGHT_MM = 9.0
CHARACTER_GAP_MM = 1.875
CONTENT_LEFT_MM = 30.0
CONTENT_TOP_MM = 190.0
TANGENT_APPROACH_MM = 1.875
PAPER_SUBDIVISION_MM = 0.4
FEED_MM_MIN = 150


def build_layout() -> shared.Layout:
    if shared.digest(FONT_PATH) != FONT_SHA256:
        raise AssertionError("pinned hand-font hash changed")
    font = load_gfont(FONT_PATH)
    if font.name != FONT_NAME or font.em_size != FONT_EM_SIZE:
        raise AssertionError("unexpected pinned hand-font metadata")
    missing = missing_characters(font, TEXT)
    if missing:
        raise AssertionError(f"hand font is missing: {missing}")
    glyphs = [font.glyphs[character] for character in TEXT]
    stroke_counts = tuple(glyph.stroke_count for glyph in glyphs)
    if stroke_counts != EXPECTED_STROKE_COUNTS:
        raise AssertionError(f"hand-font path counts changed: {stroke_counts}")

    global_y_min = min(glyph.bounds[1] for glyph in glyphs)
    global_y_max = max(glyph.bounds[3] for glyph in glyphs)
    scale = VISIBLE_HEIGHT_MM / (global_y_max - global_y_min)
    cursor_x = CONTENT_LEFT_MM
    characters: list[shared.CharacterLayout] = []
    strokes: list[shared.Stroke] = []
    for character_index, (character, glyph) in enumerate(zip(TEXT, glyphs)):
        source_x_min, source_y_min, source_x_max, source_y_max = glyph.bounds
        width = (source_x_max - source_x_min) * scale
        points = tuple(
            (
                cursor_x + (source_x - source_x_min) * scale,
                CONTENT_TOP_MM - (source_y - global_y_min) * scale,
            )
            for source_x, source_y in glyph.points
        )
        character_strokes = shared.split_strokes(
            character, points, glyph.commands
        )
        for stroke_index, stroke_points in enumerate(
            character_strokes, start=1
        ):
            first_length = math.dist(stroke_points[0], stroke_points[1])
            if first_length <= 1.0e-9:
                raise AssertionError("hand-font stroke has no direction")
            unit = (
                (stroke_points[1][0] - stroke_points[0][0])
                / first_length,
                (stroke_points[1][1] - stroke_points[0][1])
                / first_length,
            )
            approach = (
                stroke_points[0][0] - unit[0] * TANGENT_APPROACH_MM,
                stroke_points[0][1] - unit[1] * TANGENT_APPROACH_MM,
            )
            strokes.append(
                shared.Stroke(
                    character,
                    character_index,
                    stroke_index,
                    approach,
                    stroke_points,
                )
            )
        characters.append(
            shared.CharacterLayout(
                character,
                (
                    cursor_x,
                    CONTENT_TOP_MM
                    - (source_y_max - global_y_min) * scale,
                    cursor_x + width,
                    CONTENT_TOP_MM
                    - (source_y_min - global_y_min) * scale,
                ),
                len(character_strokes),
            )
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
            shared.PAPER_X_MIN_MM <= point[0] <= shared.PAPER_X_MAX_MM
            and shared.PAPER_Y_MIN_MM <= point[1] <= shared.PAPER_Y_MAX_MM
        ):
            raise AssertionError(f"hand-font sample out of bounds: {point}")
    return shared.Layout(
        font,
        scale,
        tuple(characters),
        tuple(strokes),
        bounds,
    )


def subdivide_points(
    points: tuple[tuple[float, float], ...],
) -> tuple[tuple[float, float], ...]:
    result = [points[0]]
    for start, end in zip(points, points[1:]):
        length = math.dist(start, end)
        if length <= 1.0e-9:
            raise AssertionError("hand-font path contains a zero segment")
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
    layout: shared.Layout,
) -> tuple[
    tuple[
        shared.Stroke,
        tuple[tuple[float, float], ...],
        tuple[tuple[float, float], ...],
    ],
    ...,
]:
    return tuple(
        (
            stroke,
            paper_points,
            tuple(shared.map_paper(point) for point in paper_points),
        )
        for stroke in layout.strokes
        for paper_points in (subdivide_points(stroke.points),)
    )


def gcode_lines(layout: shared.Layout) -> tuple[str, ...]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware={BUILD_ID}",
        f"; source_font={FONT_PATH.name} font_sha256={FONT_SHA256}",
        f"; text=ZHANG_JIA_LE_ZUO_PIN font={FONT_TAG}",
        "; source_geometry=UNMODIFIED",
        "; placement=TOP_LEFT_THIRD_LINE left=30mm top=190mm",
        "; visible_height=9mm comparison_to=V44_SONG_9mm",
        f"; gap={CHARACTER_GAP_MM:.3f}mm "
        f"tangent_approach={TANGENT_APPROACH_MM:.3f}mm",
        "; firmware_paper_map=DISABLED offline_pointwise_map=ENABLED",
        f"; paper_subdivision_max={PAPER_SUBDIVISION_MM:.1f}mm",
        "G21",
        "G90",
        "G94",
        f"F{FEED_MM_MIN}",
        "S1000",
        "M5",
    ]
    for stroke, _, user_points in command_plan(layout):
        approach = shared.map_paper(stroke.approach)
        lines.extend(
            (
                f"; char_index={stroke.character_index + 1} "
                f"stroke={stroke.stroke_index}",
                f"G0 X{approach[0]:.3f} Y{approach[1]:.3f}",
                f"G0 X{user_points[0][0]:.3f} "
                f"Y{user_points[0][1]:.3f}",
                "M3",
            )
        )
        lines.extend(
            f"G1 X{point[0]:.3f} Y{point[1]:.3f}"
            for point in user_points[1:]
        )
        lines.append("M5")
    return tuple(lines)


def write_preview(layout: shared.Layout) -> None:
    width = round(shared.A4_WIDTH_MM * 4.0) + 1
    height = round(shared.A4_HEIGHT_MM * 4.0) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (0, 0, width - 1, height - 1),
        outline=(25, 25, 25),
        width=3,
    )
    draw.rectangle(
        (
            *shared.preview_xy(
                (shared.PAPER_X_MIN_MM, shared.PAPER_Y_MAX_MM)
            ),
            *shared.preview_xy(
                (shared.PAPER_X_MAX_MM, shared.PAPER_Y_MIN_MM)
            ),
        ),
        outline=(130, 160, 195),
        width=2,
    )
    draw.text(
        (20, 16),
        f"V{TEST_ID.rsplit('_V', 1)[-1]} 左上第三行"
        f"“{FONT_NAME}”手写体：张佳乐作品（9 mm）",
        fill=(20, 20, 20),
        font=shared.label_font(21),
    )
    draw.text(
        (20, 48),
        "黑线=字库原路径  蓝虚线=抬笔预接近  红点=落笔点",
        fill=(70, 70, 70),
        font=shared.label_font(17),
    )
    for stroke in layout.strokes:
        approach = shared.preview_xy(stroke.approach)
        start = shared.preview_xy(stroke.points[0])
        shared.draw_dashed_line(
            draw, approach, start, (45, 115, 185), width=2
        )
        draw.line(
            [shared.preview_xy(point) for point in stroke.points],
            fill=(15, 15, 15),
            width=2,
            joint="curve",
        )
        draw.ellipse(
            (
                start[0] - 2,
                start[1] - 2,
                start[0] + 2,
                start[1] + 2,
            ),
            fill=(195, 35, 35),
        )
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def write_manifest(layout: shared.Layout, lines: tuple[str, ...]) -> None:
    plan = command_plan(layout)
    stroke_lengths = [
        sum(
            math.dist(start, end)
            for start, end in zip(stroke.points, stroke.points[1:])
        )
        for stroke in layout.strokes
    ]
    sampled_lengths = [
        math.dist(start, end)
        for _, paper_points, _ in plan
        for start, end in zip(paper_points, paper_points[1:])
    ]
    text = "\n".join(lines) + "\n"
    manifest = {
        "id": TEST_ID,
        "required_firmware": BUILD_ID,
        "text": TEXT,
        "comparison_to": (
            "PAPER_A4_TOP_LEFT_SONG_9MM_"
            "ZHANG_JIA_LE_ZUO_PIN_GCODE_V44"
        ),
        "font": {
            "file": FONT_PATH.name,
            "sha256": FONT_SHA256,
            "name": FONT_NAME,
            "em_size": FONT_EM_SIZE,
            "geometry": "unmodified gfont path points and command order",
            "character_path_counts": list(EXPECTED_STROKE_COUNTS),
        },
        "layout": {
            "content_left_mm": CONTENT_LEFT_MM,
            "content_top_mm": CONTENT_TOP_MM,
            "visible_height_mm": VISIBLE_HEIGHT_MM,
            "character_gap_mm": CHARACTER_GAP_MM,
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
            "stroke_length_mm": [
                min(stroke_lengths),
                max(stroke_lengths),
            ],
            "sampled_paper_segment_mm": [
                min(sampled_lengths),
                max(sampled_lengths),
            ],
        },
        "coordinate_contract": {
            "gfont_y": "positive downward",
            "paper_y": "positive upward",
            "firmware_paper_map_enabled": False,
            "offline_pointwise_paper_to_user_map_enabled": True,
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
    write_preview(layout)
    write_manifest(layout, lines)
    plan = command_plan(layout)
    print(
        "generated_top_left_meiyou_ruguo_9mm_v45=PASS "
        f"characters={len(TEXT)} strokes={len(layout.strokes)} "
        f"G1={sum(len(points) - 1 for _, _, points in plan)} "
        f"bounds_x={layout.bounds_mm[0]:.3f}..{layout.bounds_mm[2]:.3f} "
        f"bounds_y={layout.bounds_mm[1]:.3f}..{layout.bounds_mm[3]:.3f}"
    )
    print(GCODE_PATH)
    print(PREVIEW_PATH)
    print(MANIFEST_PATH)


if __name__ == "__main__":
    main()
