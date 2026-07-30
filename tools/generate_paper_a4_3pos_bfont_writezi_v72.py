#!/usr/bin/env python3
"""Generate the same two B-font characters at the three V70 positions."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import generate_paper_a4_standard_upper_bfont_6mm_v65 as source
from check_firmware_no_sbow_v31 import firmware_map_no_sbow
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


TEST_ID = "PAPER_A4_3POS_BFONT_WRITEZI_8MM_APPROACH5_GCODE_V72"
FIRMWARE_ID = "PAPER_A4_STANDARD_GCODE_JUNCTION_PLANNER_V32"
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"
GUIDE_PATH = ROOT / "gcode" / f"{TEST_ID}_GUIDE.md"

TEXT = "\u5199\u5b57"
GROUPS = (("L", 40.0), ("M", 100.0), ("R", 160.0))
VISIBLE_HEIGHT_MM = 8.0
CHARACTER_GAP_MM = 1.0
CONTENT_TOP_MM = 190.0
TANGENT_APPROACH_MM = 5.0
FEED_MM_MIN = 300
PAPER_X_RANGE_MM = (25.0, 185.0)
PAPER_Y_RANGE_MM = (75.0, 235.0)
PREVIEW_PIXELS_PER_MM = 4.0


def build_layout() -> tuple[Layout, tuple[tuple[str, int, int], ...]]:
    actual_hash = hashlib.sha256(source.FONT_PATH.read_bytes()).hexdigest().upper()
    if actual_hash != source.FONT_SHA256:
        raise AssertionError("pinned B gfont hash changed")
    font = load_gfont(source.FONT_PATH)
    if font.name != source.FONT_NAME or font.em_size != source.FONT_EM_SIZE:
        raise AssertionError("unexpected B gfont metadata")
    missing = missing_characters(font, TEXT)
    if missing:
        raise AssertionError(f"B gfont is missing: {missing!r}")

    glyphs = [font.glyphs[character] for character in TEXT]
    global_y_min = min(glyph.bounds[1] for glyph in glyphs)
    global_y_max = max(glyph.bounds[3] for glyph in glyphs)
    scale = VISIBLE_HEIGHT_MM / (global_y_max - global_y_min)
    glyph_widths = [
        (glyph.bounds[2] - glyph.bounds[0]) * scale
        for glyph in glyphs
    ]
    text_width = sum(glyph_widths) + CHARACTER_GAP_MM

    characters: list[CharacterLayout] = []
    strokes: list[Stroke] = []
    stroke_groups: list[tuple[str, int, int]] = []
    visible_character_index = 0
    for group, center_x in GROUPS:
        cursor_x = center_x - text_width / 2.0
        for character, glyph, width in zip(TEXT, glyphs, glyph_widths):
            source_x_min, source_y_min, source_x_max, source_y_max = (
                glyph.bounds
            )
            points = tuple(
                (
                    cursor_x + (source_x - source_x_min) * scale,
                    CONTENT_TOP_MM
                    - (source_y - global_y_min) * scale,
                )
                for source_x, source_y in glyph.points
            )
            character_strokes = split_strokes(
                character, points, glyph.commands
            )
            for stroke_index, stroke_points in enumerate(
                character_strokes, start=1
            ):
                first_length = math.dist(
                    stroke_points[0], stroke_points[1]
                )
                if first_length <= 1.0e-9:
                    raise AssertionError("zero initial stroke direction")
                unit_x = (
                    stroke_points[1][0] - stroke_points[0][0]
                ) / first_length
                unit_y = (
                    stroke_points[1][1] - stroke_points[0][1]
                ) / first_length
                approach = (
                    stroke_points[0][0]
                    - unit_x * TANGENT_APPROACH_MM,
                    stroke_points[0][1]
                    - unit_y * TANGENT_APPROACH_MM,
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
                stroke_groups.append(
                    (group, visible_character_index, stroke_index)
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
            PAPER_X_RANGE_MM[0]
            <= point[0]
            <= PAPER_X_RANGE_MM[1]
            and PAPER_Y_RANGE_MM[0]
            <= point[1]
            <= PAPER_Y_RANGE_MM[1]
        ):
            raise AssertionError(f"V72 point out of bounds: {point}")
    return (
        Layout(
            font,
            scale,
            tuple(characters),
            tuple(strokes),
            bounds,
        ),
        tuple(stroke_groups),
    )


def gcode_lines(
    layout: Layout,
    stroke_groups: tuple[tuple[str, int, int], ...],
) -> tuple[str, ...]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware_required={FIRMWARE_ID}",
        "; coordinates=STANDARD_A4_PHYSICAL_PAPER_MM",
        "; offline_mapping=NONE offline_prewarp=NONE",
        f"; source_font={source.FONT_PATH.name} sha256={source.FONT_SHA256}",
        "; font_option=B source_geometry=UNMODIFIED_GFONT",
        "; requested_text=WRITE_ZI repeated_at_L_M_R",
        "; centers_x=40,100,160mm content_top_y=190mm",
        "; visible_height=8mm tangent_approach=5mm",
        "G21",
        "G90",
        "G94",
        f"F{FEED_MM_MIN}",
        "S1000",
        "M5",
    ]
    active_group = ""
    for stroke, metadata in zip(layout.strokes, stroke_groups):
        group, character_index, stroke_index = metadata
        if group != active_group:
            if active_group:
                lines.append(f"; END_GROUP_{active_group}")
            active_group = group
            lines.append(f"; BEGIN_GROUP_{active_group}")
        lines.extend(
            (
                (
                    f"; group={group} char={character_index + 1} "
                    f"stroke={stroke_index}"
                ),
                (
                    f"G0 X{stroke.approach[0]:.3f} "
                    f"Y{stroke.approach[1]:.3f}"
                ),
                (
                    f"G0 X{stroke.points[0][0]:.3f} "
                    f"Y{stroke.points[0][1]:.3f}"
                ),
                "M3",
            )
        )
        lines.extend(
            f"G1 X{point[0]:.3f} Y{point[1]:.3f}"
            for point in stroke.points[1:]
        )
        lines.append("M5")
    lines.extend((f"; END_GROUP_{active_group}", "M5"))
    return tuple(lines)


def audit(layout: Layout, lines: tuple[str, ...]) -> dict[str, object]:
    previous_user = home_user()
    worst = (float("inf"), (0.0, 0.0))
    safe_samples = 0

    def check_user(target_user: tuple[float, float]) -> None:
        nonlocal previous_user, worst, safe_samples
        for sample in source.user_line_samples(
            previous_user, target_user, 1.0
        ):
            margin, _ = joint_margin(sample)
            if margin < worst[0]:
                worst = (margin, sample)
            safe_samples += 1
        previous_user = target_user

    for stroke in layout.strokes:
        check_user(firmware_map_no_sbow(stroke.approach))
        check_user(firmware_map_no_sbow(stroke.points[0]))
        previous_paper = stroke.points[0]
        for target_paper in stroke.points[1:]:
            for paper_sample in source.paper_line_samples(
                previous_paper, target_paper
            ):
                check_user(firmware_map_no_sbow(paper_sample))
            previous_paper = target_paper

    if worst[0] < -0.001:
        raise AssertionError(f"V72 path violates joint limits: {worst}")
    if any(len(line) >= 192 for line in lines):
        raise AssertionError("V72 contains an overlong serial line")
    if lines.count("M3") != len(layout.strokes):
        raise AssertionError("V72 pen-down count mismatch")
    return {
        "safe_samples": safe_samples,
        "min_joint_margin_deg": worst[0],
        "min_margin_user_mm": list(worst[1]),
        "stroke_count": len(layout.strokes),
        "motion_line_count": sum(
            line.startswith(("G0 ", "G1 ")) for line in lines
        ),
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
    for stroke in layout.strokes:
        draw.line(
            [preview_xy(point) for point in stroke.points],
            fill=(20, 20, 20),
            width=2,
            joint="curve",
        )
    for group, center_x in GROUPS:
        draw.text(
            preview_xy((center_x - 2.0, 196.0)),
            group,
            fill=(20, 20, 20),
            font=label_font(15),
        )
    draw.text(
        (20, 18),
        "V72 / B font / 8 mm / 5 mm tangent approach / V70 L-M-R",
        fill=(25, 25, 25),
        font=label_font(16),
    )
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def write_guide() -> None:
    GUIDE_PATH.write_text(
        f"""# V72 V70 左中右位置 B 类字体写字测试

- 所需固件：`{FIRMWARE_ID}`
- 内容：左、中、右三个位置各写一次“写字”
- 字体：B 类原始 gfont
- 可见字高：{VISIBLE_HEIGHT_MM:.0f} mm
- 落笔前切向预走：{TANGENT_APPROACH_MM:.0f} mm
- 三组中心 X：40、100、160 mm
- 字形顶部 Y：{CONTENT_TOP_MM:.0f} mm
- 标准 G-code，无离线坐标补偿

这三个“写字”使用完全相同的原始字库点序，只做刚性平移。可以直接比较左、中、右位置是否出现不同的缺笔或错位。
""",
        encoding="utf-8",
    )


def main() -> None:
    layout, stroke_groups = build_layout()
    lines = gcode_lines(layout, stroke_groups)
    text = "\n".join(lines) + "\n"
    safety = audit(layout, lines)
    GCODE_PATH.parent.mkdir(parents=True, exist_ok=True)
    GCODE_PATH.write_text(text, encoding="ascii", newline="\n")
    manifest = {
        "id": TEST_ID,
        "required_firmware": FIRMWARE_ID,
        "text": TEXT,
        "repetitions": 3,
        "font": {
            "option": "B",
            "name": source.FONT_NAME,
            "file": source.FONT_PATH.name,
            "sha256": source.FONT_SHA256,
            "geometry": "unmodified gfont paths; rigid translation only",
        },
        "layout": {
            "visible_height_mm": VISIBLE_HEIGHT_MM,
            "character_gap_mm": CHARACTER_GAP_MM,
            "content_top_mm": CONTENT_TOP_MM,
            "group_centers_x_mm": [center for _, center in GROUPS],
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
    write_guide()
    print(
        "bfont_writezi_3pos_v72=PASS "
        f"bounds={layout.bounds_mm} "
        f"strokes={safety['stroke_count']} "
        f"safe_samples={safety['safe_samples']} "
        f"min_joint_margin={safety['min_joint_margin_deg']:.6f}deg"
    )
    print(f"gcode_sha256={manifest['gcode']['sha256']}")
    print(GCODE_PATH)
    print(MANIFEST_PATH)
    print(PREVIEW_PATH)
    print(GUIDE_PATH)


if __name__ == "__main__":
    main()
