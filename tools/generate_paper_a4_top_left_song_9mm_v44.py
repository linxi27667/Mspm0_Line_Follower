#!/usr/bin/env python3
"""Generate a second-line 9 mm Song-font size comparison sample."""

from __future__ import annotations

import hashlib
import json
import math

from PIL import Image, ImageDraw

import generate_paper_a4_top_left_song_12mm_v43 as base


TEST_ID = "PAPER_A4_TOP_LEFT_SONG_9MM_ZHANG_JIA_LE_ZUO_PIN_GCODE_V44"
BUILD_ID = base.BUILD_ID
GCODE_PATH = base.ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = base.ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = (
    base.ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"
)

TEXT = base.TEXT
SCALE_FROM_V43 = 0.75
VISIBLE_HEIGHT_MM = 9.0
CONTENT_LEFT_MM = 30.0
CONTENT_TOP_MM = 212.0
CHARACTER_GAP_MM = base.CHARACTER_GAP_MM * SCALE_FROM_V43
TANGENT_APPROACH_MM = base.TANGENT_APPROACH_MM * SCALE_FROM_V43
PAPER_SUBDIVISION_MM = 0.4
FEED_MM_MIN = 150


def transform_point(
    point: tuple[float, float],
) -> tuple[float, float]:
    return (
        CONTENT_LEFT_MM
        + (point[0] - base.CONTENT_LEFT_MM) * SCALE_FROM_V43,
        CONTENT_TOP_MM
        + (point[1] - base.CONTENT_TOP_MM) * SCALE_FROM_V43,
    )


def build_layout() -> base.Layout:
    source = base.build_layout()
    characters = tuple(
        base.CharacterLayout(
            character.character,
            (
                transform_point(
                    (character.bounds_mm[0], character.bounds_mm[1])
                )[0],
                transform_point(
                    (character.bounds_mm[0], character.bounds_mm[1])
                )[1],
                transform_point(
                    (character.bounds_mm[2], character.bounds_mm[3])
                )[0],
                transform_point(
                    (character.bounds_mm[2], character.bounds_mm[3])
                )[1],
            ),
            character.stroke_count,
        )
        for character in source.characters
    )
    strokes = tuple(
        base.Stroke(
            stroke.character,
            stroke.character_index,
            stroke.stroke_index,
            transform_point(stroke.approach),
            tuple(transform_point(point) for point in stroke.points),
        )
        for stroke in source.strokes
    )
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
            base.PAPER_X_MIN_MM <= point[0] <= base.PAPER_X_MAX_MM
            and base.PAPER_Y_MIN_MM <= point[1] <= base.PAPER_Y_MAX_MM
        ):
            raise AssertionError(f"9 mm sample out of bounds: {point}")
    return base.Layout(
        source.font,
        source.scale_mm_per_unit * SCALE_FROM_V43,
        characters,
        strokes,
        bounds,
    )


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
    layout: base.Layout,
) -> tuple[
    tuple[
        base.Stroke,
        tuple[tuple[float, float], ...],
        tuple[tuple[float, float], ...],
    ],
    ...,
]:
    return tuple(
        (
            stroke,
            paper_points,
            tuple(base.map_paper(point) for point in paper_points),
        )
        for stroke in layout.strokes
        for paper_points in (subdivide_points(stroke.points),)
    )


def gcode_lines(layout: base.Layout) -> tuple[str, ...]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware={BUILD_ID}",
        f"; source_font={base.FONT_PATH.name} "
        f"font_sha256={base.FONT_SHA256}",
        "; text=ZHANG_JIA_LE_ZUO_PIN font=SONG geometry=UNMODIFIED",
        "; placement=TOP_LEFT_SECOND_LINE left=30mm top=212mm",
        "; visible_height=9mm comparison_to=V43_12mm",
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
        approach = base.map_paper(stroke.approach)
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


def write_preview(layout: base.Layout) -> None:
    width = round(base.A4_WIDTH_MM * 4.0) + 1
    height = round(base.A4_HEIGHT_MM * 4.0) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (0, 0, width - 1, height - 1),
        outline=(25, 25, 25),
        width=3,
    )
    draw.rectangle(
        (
            *base.preview_xy(
                (base.PAPER_X_MIN_MM, base.PAPER_Y_MAX_MM)
            ),
            *base.preview_xy(
                (base.PAPER_X_MAX_MM, base.PAPER_Y_MIN_MM)
            ),
        ),
        outline=(130, 160, 195),
        width=2,
    )
    draw.text(
        (20, 16),
        "V44 左上第二行宋体小字：张佳乐作品（字高约 9 mm）",
        fill=(20, 20, 20),
        font=base.label_font(23),
    )
    draw.text(
        (20, 48),
        "黑线=字库原路径  蓝虚线=抬笔预接近  红点=落笔点",
        fill=(70, 70, 70),
        font=base.label_font(17),
    )
    for character in layout.characters:
        draw.rectangle(
            (
                *base.preview_xy(
                    (character.bounds_mm[0], character.bounds_mm[3])
                ),
                *base.preview_xy(
                    (character.bounds_mm[2], character.bounds_mm[1])
                ),
            ),
            outline=(225, 225, 225),
            width=1,
        )
    for stroke in layout.strokes:
        approach = base.preview_xy(stroke.approach)
        start = base.preview_xy(stroke.points[0])
        base.draw_dashed_line(
            draw, approach, start, (45, 115, 185), width=2
        )
        draw.line(
            [base.preview_xy(point) for point in stroke.points],
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


def write_manifest(layout: base.Layout, lines: tuple[str, ...]) -> None:
    plan = command_plan(layout)
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
        "comparison_to": base.TEST_ID,
        "font": {
            "file": base.FONT_PATH.name,
            "sha256": base.FONT_SHA256,
            "name": base.FONT_NAME,
            "geometry": "unmodified gfont path points and command order",
            "character_path_counts": list(base.EXPECTED_STROKE_COUNTS),
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
            "sampled_paper_segment_mm": [
                min(sampled_lengths),
                max(sampled_lengths),
            ],
        },
        "coordinate_contract": {
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
        "generated_top_left_song_9mm_v44=PASS "
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
