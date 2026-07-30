#!/usr/bin/env python3
"""Generate a single-variable forward/reversed stroke-direction A/B test."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import generate_paper_a4_standard_bfont_no_sbow_v68 as source
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
)


TEST_ID = "PAPER_A4_BFONT_6MM_STROKE_DIRECTION_AB_GCODE_V69"
FIRMWARE_ID = "PAPER_A4_STANDARD_GCODE_JUNCTION_PLANNER_V32"
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"
GUIDE_PATH = ROOT / "gcode" / f"{TEST_ID}_GUIDE.md"

TEXT = "\u5199\u5b57\u673a\u7b2c\u597d\u591a\u6b21\u6d4b\u8bd5"
CHARACTER_COUNT = len(TEXT)
SOURCE_CONTENT_TOP_MM = source.CONTENT_TOP_MM
SOURCE_CONTENT_LEFT_MM = source.base.CONTENT_LEFT_MM
CONTENT_LEFT_MM = 125.0
ROW_A_CONTENT_TOP_MM = 226.0
ROW_B_CONTENT_TOP_MM = 212.0
ROW_GAP_MM = ROW_A_CONTENT_TOP_MM - ROW_B_CONTENT_TOP_MM
TRANSLATE_X_MM = CONTENT_LEFT_MM - SOURCE_CONTENT_LEFT_MM
PREVIEW_PIXELS_PER_MM = 4.0


def tangent_approach(
    points: tuple[tuple[float, float], ...],
) -> tuple[float, float]:
    if len(points) < 2:
        raise AssertionError("stroke has fewer than two points")
    length = math.dist(points[0], points[1])
    if length <= 1.0e-9:
        raise AssertionError("stroke has a zero initial direction")
    unit_x = (points[1][0] - points[0][0]) / length
    unit_y = (points[1][1] - points[0][1]) / length
    return (
        points[0][0] - unit_x * source.base.TANGENT_APPROACH_MM,
        points[0][1] - unit_y * source.base.TANGENT_APPROACH_MM,
    )


def translated_points(
    stroke: Stroke, content_top_mm: float, reverse: bool
) -> tuple[tuple[float, float], ...]:
    delta_y = content_top_mm - SOURCE_CONTENT_TOP_MM
    points = tuple(
        (x + TRANSLATE_X_MM, y + delta_y)
        for x, y in stroke.points
    )
    return tuple(reversed(points)) if reverse else points


def build_layout() -> tuple[Layout, tuple[Stroke, ...], tuple[Stroke, ...]]:
    source_layout = source.translated_layout()
    source_strokes = tuple(
        stroke
        for stroke in source_layout.strokes
        if stroke.character_index < CHARACTER_COUNT
    )
    if "".join(
        character.character
        for character in source_layout.characters[:CHARACTER_COUNT]
    ) != TEXT:
        raise AssertionError("unexpected source character order")

    row_a: list[Stroke] = []
    row_b: list[Stroke] = []
    for stroke in source_strokes:
        points_a = translated_points(
            stroke, ROW_A_CONTENT_TOP_MM, reverse=False
        )
        points_b = translated_points(
            stroke, ROW_B_CONTENT_TOP_MM, reverse=True
        )
        row_a.append(
            Stroke(
                stroke.character,
                stroke.character_index,
                stroke.stroke_index,
                tangent_approach(points_a),
                points_a,
            )
        )
        row_b.append(
            Stroke(
                stroke.character,
                stroke.character_index + CHARACTER_COUNT,
                stroke.stroke_index,
                tangent_approach(points_b),
                points_b,
            )
        )

    characters: list[CharacterLayout] = []
    for row_index, content_top in enumerate(
        (ROW_A_CONTENT_TOP_MM, ROW_B_CONTENT_TOP_MM)
    ):
        delta_y = content_top - SOURCE_CONTENT_TOP_MM
        for character in source_layout.characters[:CHARACTER_COUNT]:
            characters.append(
                CharacterLayout(
                    character.character,
                    (
                        character.bounds_mm[0] + TRANSLATE_X_MM,
                        character.bounds_mm[1] + delta_y,
                        character.bounds_mm[2] + TRANSLATE_X_MM,
                        character.bounds_mm[3] + delta_y,
                    ),
                    character.stroke_count,
                )
            )

    strokes = tuple(row_a + row_b)
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
            source.base.PAPER_X_MIN_MM
            <= point[0]
            <= source.base.PAPER_X_MAX_MM
            and source.base.PAPER_Y_MIN_MM
            <= point[1]
            <= source.base.PAPER_Y_MAX_MM
        ):
            raise AssertionError(f"V69 point out of bounds: {point}")
    return (
        Layout(
            source_layout.font,
            source_layout.scale_mm_per_unit,
            tuple(characters),
            strokes,
            bounds,
        ),
        tuple(row_a),
        tuple(row_b),
    )


def gcode_lines(
    row_a: tuple[Stroke, ...], row_b: tuple[Stroke, ...]
) -> tuple[str, ...]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware_required={FIRMWARE_ID}",
        "; coordinates=STANDARD_A4_PHYSICAL_PAPER_MM",
        "; offline_mapping=NONE offline_prewarp=NONE",
        (
            f"; source_font={source.base.FONT_PATH.name} "
            f"sha256={source.base.FONT_SHA256}"
        ),
        "; text=9_CHINESE_CHARS_WRITER_TEST",
        "; placement=UPPER_RIGHT_BLANK_BAND left_x=125mm",
        "; row_A=ORIGINAL_GFONT_STROKE_DIRECTION top_y=226mm",
        "; row_B=EVERY_STROKE_POINT_ORDER_REVERSED top_y=212mm",
        "; single_variable=STROKE_DIRECTION_ONLY",
        "; geometry_scale_feed_mapping_identical=YES",
        "G21",
        "G90",
        "G94",
        f"F{source.base.FEED_MM_MIN}",
        "S1000",
        "M5",
    ]
    for row_name, direction, strokes in (
        ("A", "ORIGINAL", row_a),
        ("B", "REVERSED", row_b),
    ):
        lines.append(f"; BEGIN_ROW_{row_name}_{direction}")
        for stroke in strokes:
            visible_index = (
                stroke.character_index
                if row_name == "A"
                else stroke.character_index - CHARACTER_COUNT
            )
            lines.extend(
                (
                    (
                        f"; row={row_name} char={visible_index + 1} "
                        f"stroke={stroke.stroke_index} "
                        f"direction={direction}"
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
        lines.append(f"; END_ROW_{row_name}_{direction}")
    lines.append("M5")
    return tuple(lines)


def audit(
    layout: Layout,
    row_a: tuple[Stroke, ...],
    row_b: tuple[Stroke, ...],
    lines: tuple[str, ...],
) -> dict[str, object]:
    if len(row_a) != len(row_b):
        raise AssertionError("row stroke counts differ")

    max_geometry_delta = 0.0
    for stroke_a, stroke_b in zip(row_a, row_b):
        if (
            stroke_a.character != stroke_b.character
            or stroke_a.stroke_index != stroke_b.stroke_index
        ):
            raise AssertionError("A/B stroke identities differ")
        normalized_b = tuple(
            (x, y + ROW_GAP_MM)
            for x, y in reversed(stroke_b.points)
        )
        if len(stroke_a.points) != len(normalized_b):
            raise AssertionError("A/B stroke point counts differ")
        for point_a, point_b in zip(stroke_a.points, normalized_b):
            max_geometry_delta = max(
                max_geometry_delta, math.dist(point_a, point_b)
            )
    if max_geometry_delta > 1.0e-9:
        raise AssertionError(
            f"A/B geometry changed by {max_geometry_delta} mm"
        )

    previous_user = home_user()
    worst = (float("inf"), (0.0, 0.0))
    safe_samples = 0

    def check_user(target_user: tuple[float, float]) -> None:
        nonlocal previous_user, worst, safe_samples
        for sample in source.base.user_line_samples(
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
            for paper_sample in source.base.paper_line_samples(
                previous_paper, target_paper
            ):
                check_user(firmware_map_no_sbow(paper_sample))
            previous_paper = target_paper

    if worst[0] < -0.001:
        raise AssertionError(f"V32/V69 path violates joint limits: {worst}")
    if any(len(line) >= 192 for line in lines):
        raise AssertionError("V69 contains an overlong serial line")
    return {
        "safe_samples": safe_samples,
        "min_joint_margin_deg": worst[0],
        "min_margin_user_mm": list(worst[1]),
        "ab_max_geometry_delta_mm": max_geometry_delta,
        "row_a_stroke_count": len(row_a),
        "row_b_stroke_count": len(row_b),
        "motion_line_count": sum(
            line.startswith(("G0 ", "G1 ")) for line in lines
        ),
    }


def write_preview(
    layout: Layout, row_a: tuple[Stroke, ...], row_b: tuple[Stroke, ...]
) -> None:
    width = round(A4_WIDTH_MM * PREVIEW_PIXELS_PER_MM) + 1
    height = round(A4_HEIGHT_MM * PREVIEW_PIXELS_PER_MM) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, height - 1), outline=(30, 30, 30), width=3)
    draw.rectangle(
        (
            round(source.base.PAPER_X_MIN_MM * PREVIEW_PIXELS_PER_MM),
            round((A4_HEIGHT_MM - 232.0) * PREVIEW_PIXELS_PER_MM),
            round(source.base.PAPER_X_MAX_MM * PREVIEW_PIXELS_PER_MM),
            round((A4_HEIGHT_MM - 204.0) * PREVIEW_PIXELS_PER_MM),
        ),
        outline=(110, 170, 220),
        width=2,
    )
    for stroke in row_a:
        draw.line(
            [preview_xy(point) for point in stroke.points],
            fill=(20, 20, 20),
            width=2,
            joint="curve",
        )
    for stroke in row_b:
        draw.line(
            [preview_xy(point) for point in stroke.points],
            fill=(30, 90, 190),
            width=2,
            joint="curve",
        )
    draw.text(
        (20, 18),
        "V69 direction A/B: A=original black, B=reversed blue",
        fill=(25, 25, 25),
        font=label_font(17),
    )
    draw.text(
        preview_xy((100.0, ROW_A_CONTENT_TOP_MM - 1.0)),
        "A original",
        fill=(20, 20, 20),
        font=label_font(14),
    )
    draw.text(
        preview_xy((100.0, ROW_B_CONTENT_TOP_MM - 1.0)),
        "B reversed",
        fill=(30, 90, 190),
        font=label_font(14),
    )
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def write_guide() -> None:
    GUIDE_PATH.write_text(
        f"""# V69 B 字体 6 mm 正反笔画方向 A/B 测试

- 固件：`{FIRMWARE_ID}`
- G-code：`{GCODE_PATH.name}`
- 字体：`{source.base.FONT_PATH.name}`
- 字体 SHA-256：`{source.base.FONT_SHA256}`
- 内容：`{TEXT}`
- 左边界：X={CONTENT_LEFT_MM:.0f} mm（右上空白区域）
- A 行：原始字库笔画方向，顶部 Y={ROW_A_CONTENT_TOP_MM:.0f} mm
- B 行：每一笔的点序完全反转，顶部 Y={ROW_B_CONTENT_TOP_MM:.0f} mm
- 字高：6 mm
- 速度：F{source.base.FEED_MM_MIN}

两行只有笔画运行方向不同；字形点集、缩放、字符间距、速度、固件坐标映射均相同。

## 观察重点

1. 若短横、撇捺或交接处的缺口在 B 行换到相反一端，主因是方向回差或受力弹性。
2. 若 A/B 两行形状几乎相同，但都与预览同方向偏离，主因偏向静态坐标映射或运动学标定。
3. 若同一行内部出现随机缺笔且重复位置不一致，才考虑丢步、电气脉冲或队列异常。

拍照时请保持纸张四边尽量完整，并在文字旁放毫米尺；不要手动画辅助线覆盖笔画。
""",
        encoding="utf-8",
    )


def main() -> None:
    layout, row_a, row_b = build_layout()
    lines = gcode_lines(row_a, row_b)
    text = "\n".join(lines) + "\n"
    safety = audit(layout, row_a, row_b, lines)
    GCODE_PATH.parent.mkdir(parents=True, exist_ok=True)
    GCODE_PATH.write_text(text, encoding="ascii", newline="\n")
    manifest = {
        "id": TEST_ID,
        "required_firmware": FIRMWARE_ID,
        "purpose": (
            "single-variable isolation of direction-dependent mechanical "
            "hysteresis/compliance from static mapping and font geometry"
        ),
        "font": {
            "option": "B",
            "name": source.base.FONT_NAME,
            "file": source.base.FONT_PATH.name,
            "sha256": source.base.FONT_SHA256,
            "geometry": "unmodified original gfont point sets",
        },
        "text": TEXT,
        "rows": {
            "A": {
                "content_left_mm": CONTENT_LEFT_MM,
                "content_top_mm": ROW_A_CONTENT_TOP_MM,
                "stroke_direction": "original",
            },
            "B": {
                "content_left_mm": CONTENT_LEFT_MM,
                "content_top_mm": ROW_B_CONTENT_TOP_MM,
                "stroke_direction": "every stroke point order reversed",
            },
            "vertical_translation_mm": ROW_GAP_MM,
        },
        "layout": {
            "visible_height_mm": source.base.VISIBLE_HEIGHT_MM,
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
            "feed_mm_min": source.base.FEED_MM_MIN,
            "tangent_approach_mm": source.base.TANGENT_APPROACH_MM,
            "single_variable": "stroke point order",
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
    write_preview(layout, row_a, row_b)
    write_guide()
    print(
        "bfont_direction_ab_v69=PASS "
        f"bounds={layout.bounds_mm} "
        f"strokes={len(row_a)}+{len(row_b)} "
        f"ab_delta={safety['ab_max_geometry_delta_mm']:.12f}mm "
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
