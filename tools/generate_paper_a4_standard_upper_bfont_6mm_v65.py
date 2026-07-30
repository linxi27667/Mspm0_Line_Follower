#!/usr/bin/env python3
"""Generate small upper-row B-gfont text in standard paper coordinates."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from check_firmware_right_sbow_v30 import firmware_map
from check_workspace_yshift15_v28 import joint_margin
from generate_paper_a4_full_width_square_spiral_v59 import home_user
from generate_paper_a4_zhang_jia_le_v30 import (
    A4_HEIGHT_MM,
    A4_WIDTH_MM,
    CharacterLayout,
    Layout,
    Stroke,
    label_font,
    preview_xy,
    split_strokes,
)
from kenjoy_gfont import load_gfont, missing_characters


TEST_ID = "PAPER_A4_STANDARD_UPPER_BFONT_6MM_WRITER_TEST_TIMESTAMP_GCODE_V65"
FIRMWARE_ID = (
    "PAPER_A4_STANDARD_GCODE_RIGHT_SBOW_PAPERMAP_YSHIFT15_V30"
)
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"

FONT_PATH = (
    ROOT / "assets" / "kenjoy_gfont" / "AA_GUO_JINGMING_b7c9ccc1.gfont"
)
FONT_SHA256 = (
    "D5D8E41EF24BF380FDAB57B4746795D691CC4E2DF878A394E4FA8C6D594C09F8"
)
FONT_NAME = "aa\u90ed\u656c\u660e\u5b57\u4f53"
FONT_EM_SIZE = 525

REQUESTED_TEXT = (
    "\u5199\u5b57\u673a\u7b2c\u597d\u591a\u6b21\u6d4b\u8bd5"
    "\uff0c7.25  5.23am"
)
# This gfont has no ASCII '.', so use its original U+3002 outline as the
# visible round date separator.  No glyph geometry is synthesized.
RENDERED_TEXT = REQUESTED_TEXT.replace(".", "\u3002")

VISIBLE_HEIGHT_MM = 6.0
CHARACTER_GAP_MM = 0.9
SPACE_ADVANCE_MM = 2.4
CONTENT_LEFT_MM = 30.0
CONTENT_TOP_MM = 230.0
TANGENT_APPROACH_MM = 1.2
FEED_MM_MIN = 300

PAPER_X_MIN_MM = 25.0
PAPER_X_MAX_MM = 185.0
PAPER_Y_MIN_MM = 75.0
PAPER_Y_MAX_MM = 235.0
PREVIEW_PIXELS_PER_MM = 4.0


def build_layout() -> Layout:
    actual_hash = hashlib.sha256(FONT_PATH.read_bytes()).hexdigest().upper()
    if actual_hash != FONT_SHA256:
        raise AssertionError("pinned B gfont hash changed")
    font = load_gfont(FONT_PATH)
    if font.name != FONT_NAME or font.em_size != FONT_EM_SIZE:
        raise AssertionError(
            f"unexpected B gfont metadata: {font.name!r}, {font.em_size}"
        )
    missing = missing_characters(font, RENDERED_TEXT)
    if missing:
        raise AssertionError(f"B gfont is missing: {missing!r}")

    visible_glyphs = [
        font.glyphs[character]
        for character in RENDERED_TEXT
        if not character.isspace()
    ]
    global_y_min = min(glyph.bounds[1] for glyph in visible_glyphs)
    global_y_max = max(glyph.bounds[3] for glyph in visible_glyphs)
    scale = VISIBLE_HEIGHT_MM / (global_y_max - global_y_min)

    cursor_x = CONTENT_LEFT_MM
    characters: list[CharacterLayout] = []
    strokes: list[Stroke] = []
    visible_character_index = 0
    for text_index, character in enumerate(RENDERED_TEXT):
        if character.isspace():
            cursor_x += SPACE_ADVANCE_MM
            continue

        glyph = font.glyphs[character]
        source_x_min, source_y_min, source_x_max, source_y_max = glyph.bounds
        width = (source_x_max - source_x_min) * scale
        points = tuple(
            (
                cursor_x + (source_x - source_x_min) * scale,
                CONTENT_TOP_MM - (source_y - global_y_min) * scale,
            )
            for source_x, source_y in glyph.points
        )
        character_strokes = split_strokes(
            character, points, glyph.commands
        )
        for stroke_index, stroke_points in enumerate(
            character_strokes, start=1
        ):
            first_length = math.dist(stroke_points[0], stroke_points[1])
            if first_length <= 1.0e-9:
                raise AssertionError(
                    f"zero initial direction at text index {text_index}"
                )
            unit_x = (
                stroke_points[1][0] - stroke_points[0][0]
            ) / first_length
            unit_y = (
                stroke_points[1][1] - stroke_points[0][1]
            ) / first_length
            approach = (
                stroke_points[0][0] - unit_x * TANGENT_APPROACH_MM,
                stroke_points[0][1] - unit_y * TANGENT_APPROACH_MM,
            )
            strokes.append(
                Stroke(
                    character,
                    visible_character_index,
                    stroke_index,
                    approach,
                    stroke_points,
                )
            )
        characters.append(
            CharacterLayout(
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
        visible_character_index += 1

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
            raise AssertionError(f"upper B-font layout out of bounds: {point}")
    if bounds[1] < 220.0 or bounds[3] > 232.0:
        raise AssertionError(f"layout leaves validated upper band: {bounds}")

    return Layout(
        font,
        scale,
        tuple(characters),
        tuple(strokes),
        bounds,
    )


def gcode_lines(layout: Layout) -> tuple[str, ...]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware_required={FIRMWARE_ID}",
        "; coordinates=STANDARD_A4_PHYSICAL_PAPER_MM",
        "; offline_mapping=NONE offline_prewarp=NONE",
        f"; source_font={FONT_PATH.name} sha256={FONT_SHA256}",
        "; font_option=B source_geometry=UNMODIFIED_GFONT",
        "; requested_text=WRITER_TEST_COUNT_7.25__5.23am",
        "; ASCII_PERIOD_DISPLAYED_WITH_ORIGINAL_GFONT_U3002=YES",
        "; visible_height=6mm placement=UPPER_VALIDATED_BAND",
        "; firmware_owns=BASE_MAP,RIGHT_HALF_VERTICAL_SBOW,HORIZONTAL_SBOW,YSHIFT15",
        "G21",
        "G90",
        "G94",
        f"F{FEED_MM_MIN}",
        "S1000",
        "M5",
    ]
    for stroke in layout.strokes:
        lines.extend(
            (
                f"; char={stroke.character_index + 1} "
                f"stroke={stroke.stroke_index}",
                f"G0 X{stroke.approach[0]:.3f} "
                f"Y{stroke.approach[1]:.3f}",
                f"G0 X{stroke.points[0][0]:.3f} "
                f"Y{stroke.points[0][1]:.3f}",
                "M3",
            )
        )
        lines.extend(
            f"G1 X{point[0]:.3f} Y{point[1]:.3f}"
            for point in stroke.points[1:]
        )
        lines.append("M5")
    lines.append("M5")
    return tuple(lines)


def user_line_samples(
    start: tuple[float, float],
    end: tuple[float, float],
    max_step_mm: float,
) -> tuple[tuple[float, float], ...]:
    span = max(abs(end[0] - start[0]), abs(end[1] - start[1]))
    count = max(1, math.ceil(span / max_step_mm))
    return tuple(
        (
            start[0] + (end[0] - start[0]) * index / count,
            start[1] + (end[1] - start[1]) * index / count,
        )
        for index in range(1, count + 1)
    )


def paper_line_samples(
    start: tuple[float, float],
    end: tuple[float, float],
) -> tuple[tuple[float, float], ...]:
    length = max(abs(end[0] - start[0]), abs(end[1] - start[1]))
    count = max(1, math.ceil(length))
    return tuple(
        (
            start[0] + (end[0] - start[0]) * index / count,
            start[1] + (end[1] - start[1]) * index / count,
        )
        for index in range(1, count + 1)
    )


def audit(layout: Layout, lines: tuple[str, ...]) -> dict:
    previous_user = home_user()
    worst = (float("inf"), (0.0, 0.0))
    safe_samples = 0

    def check_user(target_user: tuple[float, float]) -> None:
        nonlocal previous_user, worst, safe_samples
        for sample in user_line_samples(previous_user, target_user, 1.0):
            margin, _ = joint_margin(sample)
            if margin < worst[0]:
                worst = (margin, sample)
            safe_samples += 1
        previous_user = target_user

    for stroke in layout.strokes:
        check_user(firmware_map(stroke.approach))
        check_user(firmware_map(stroke.points[0]))
        previous_paper = stroke.points[0]
        for target_paper in stroke.points[1:]:
            for paper_sample in paper_line_samples(
                previous_paper, target_paper
            ):
                check_user(firmware_map(paper_sample))
            previous_paper = target_paper

    if worst[0] < -0.001:
        raise AssertionError(f"V30/V65 path violates joint limits: {worst}")

    motion_lines = [
        line for line in lines if line.startswith(("G0 ", "G1 "))
    ]
    if not motion_lines:
        raise AssertionError("V65 contains no motion")
    if any(len(line) >= 192 for line in lines):
        raise AssertionError("V65 contains an overlong serial line")
    return {
        "safe_samples": safe_samples,
        "min_joint_margin_deg": worst[0],
        "min_margin_user_mm": list(worst[1]),
        "motion_line_count": len(motion_lines),
        "stroke_count": len(layout.strokes),
    }


def write_preview(layout: Layout) -> None:
    width = round(A4_WIDTH_MM * PREVIEW_PIXELS_PER_MM) + 1
    height = round(A4_HEIGHT_MM * PREVIEW_PIXELS_PER_MM) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (0, 0, width - 1, height - 1),
        outline=(30, 30, 30),
        width=3,
    )
    draw.rectangle(
        (
            round(PAPER_X_MIN_MM * PREVIEW_PIXELS_PER_MM),
            round((A4_HEIGHT_MM - 235.0) * PREVIEW_PIXELS_PER_MM),
            round(PAPER_X_MAX_MM * PREVIEW_PIXELS_PER_MM),
            round((A4_HEIGHT_MM - 210.0) * PREVIEW_PIXELS_PER_MM),
        ),
        outline=(90, 160, 220),
        width=2,
    )
    for stroke in layout.strokes:
        draw.line(
            [preview_xy(point) for point in stroke.points],
            fill=(20, 20, 20),
            width=2,
            joint="curve",
        )
    draw.text(
        (20, 18),
        "V65 / B font / 6 mm / standard paper coordinates",
        fill=(25, 25, 25),
        font=label_font(18),
    )
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def main() -> None:
    layout = build_layout()
    lines = gcode_lines(layout)
    text = "\n".join(lines) + "\n"
    safety = audit(layout, lines)
    GCODE_PATH.parent.mkdir(parents=True, exist_ok=True)
    GCODE_PATH.write_text(text, encoding="ascii", newline="\n")
    manifest = {
        "id": TEST_ID,
        "required_firmware": FIRMWARE_ID,
        "requested_text": REQUESTED_TEXT,
        "rendered_text": RENDERED_TEXT,
        "period_substitution": {
            "requested": "ASCII U+002E",
            "rendered": "original B-gfont U+3002",
            "synthesized_geometry": False,
        },
        "font": {
            "option": "B",
            "name": FONT_NAME,
            "file": FONT_PATH.name,
            "sha256": FONT_SHA256,
            "em_size": FONT_EM_SIZE,
            "geometry": "unmodified gfont path points and command order",
            "gfont_y": "positive downward",
        },
        "layout": {
            "visible_height_mm": VISIBLE_HEIGHT_MM,
            "character_gap_mm": CHARACTER_GAP_MM,
            "space_advance_mm": SPACE_ADVANCE_MM,
            "content_left_mm": CONTENT_LEFT_MM,
            "content_top_mm": CONTENT_TOP_MM,
            "bounds_mm": list(layout.bounds_mm),
        },
        "coordinate_contract": {
            "units": "mm",
            "frame": "nominal physical A4 paper",
            "offline_mapping": False,
            "offline_prewarp": False,
            "firmware_mapping": True,
        },
        "motion": {
            "feed_mm_min": FEED_MM_MIN,
            "tangent_approach_mm": TANGENT_APPROACH_MM,
            "firmware_draw_subdivision_max_mm": 1.0,
        },
        "safety": safety,
        "gcode": {
            "file": GCODE_PATH.name,
            "line_count": len(lines),
            "sha256": hashlib.sha256(text.encode("ascii")).hexdigest().upper(),
        },
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_preview(layout)
    print(
        "standard_upper_bfont_6mm_v65=PASS "
        f"bounds={layout.bounds_mm} strokes={len(layout.strokes)} "
        f"motion_lines={safety['motion_line_count']} "
        f"safe_samples={safety['safe_samples']} "
        f"min_joint_margin={safety['min_joint_margin_deg']:.6f}deg"
    )
    print(f"gcode_sha256={manifest['gcode']['sha256']}")
    print(GCODE_PATH)
    print(MANIFEST_PATH)
    print(PREVIEW_PATH)


if __name__ == "__main__":
    main()
