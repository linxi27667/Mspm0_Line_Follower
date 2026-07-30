#!/usr/bin/env python3
"""Generate one V28-compatible G-code file comparing four original gfonts."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

import generate_paper_a4_top_left_song_12mm_v43 as shared
from check_workspace_yshift15_v28 import (
    BUILD_ID,
    L1_MM,
    L2_MM,
    OFFSET_X_MM,
    OFFSET_Y_MM,
    PSI_MIN_DEG,
    SHIFT_X_MM,
    SHIFT_Y_MM,
    THETA_MIN_DEG,
    joint_margin,
)
from generate_paper_a4_3x3_baseonly_direction_v49 import map_base_only
from kenjoy_gfont import load_gfont, missing_characters


ROOT = Path(__file__).resolve().parents[1]
TEST_ID = "PAPER_A4_FOUR_FONT_9MM_ZHANGJIALE_COMPARISON_GCODE_V56"
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"

TEXT = "\u5f20\u4f73\u4e50\u4f5c\u54c1"
VISIBLE_HEIGHT_MM = 9.0
CHARACTER_GAP_MM = 1.875
TANGENT_APPROACH_MM = 1.875
PAPER_SUBDIVISION_MM = 0.4
FEED_MM_MIN = 150

# V28 moves every G0/G1 target by +15 mm in Cartesian Y. These are logical
# paper coordinates; do not add the shift to emitted G-code a second time.
NOMINAL_PHYSICAL_WRITING_Y_MIN_MM = 110.0
NOMINAL_PHYSICAL_WRITING_Y_MAX_MM = 240.0


@dataclass(frozen=True)
class FontSpec:
    option: str
    display_name: str
    file_name: str
    sha256: str
    em_size: int
    stroke_counts: tuple[int, ...]
    left_mm: float
    top_logical_mm: float


@dataclass(frozen=True)
class Group:
    spec: FontSpec
    layout: shared.Layout


FONT_SPECS = (
    FontSpec(
        "A",
        "\u9648\u624b\u5199",
        "CHEN_HANDWRITING_cf5b1677.gfont",
        "1B1D959A1B75106C8F94D1D95A9930FDF7DD54BA445C6CED0B84E55368F9644B",
        400,
        (7, 7, 5, 7, 9),
        30.0,
        220.0,
    ),
    FontSpec(
        "B",
        "aa\u90ed\u656c\u660e\u5b57\u4f53",
        "AA_GUO_JINGMING_b7c9ccc1.gfont",
        "D5D8E41EF24BF380FDAB57B4746795D691CC4E2DF878A394E4FA8C6D594C09F8",
        525,
        (7, 8, 5, 7, 9),
        115.0,
        220.0,
    ),
    FontSpec(
        "C",
        "\u6ca1\u6709\u5982\u679c",
        "MEIYOU_RUGUO_e31cdaaa.gfont",
        "569C56EE629D29E1F1172D66F1FE8205E810801A6437FA8490006FE1CB3DD6D6",
        600,
        (7, 8, 4, 7, 9),
        30.0,
        155.0,
    ),
    FontSpec(
        "D",
        "\u5b8b\u4f53",
        "SONG_ec900461.gfont",
        "A74332F3F53C77B02DE6637ED8AAF0D5010E61444B1216D3E291A6AEA1419C24",
        600,
        (15, 9, 13, 11, 6),
        115.0,
        155.0,
    ),
)


def build_group(spec: FontSpec) -> Group:
    path = ROOT / "assets" / "kenjoy_gfont" / spec.file_name
    actual_hash = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    if actual_hash != spec.sha256:
        raise AssertionError(f"{spec.option} font hash changed: {path.name}")
    font = load_gfont(path)
    if font.name != spec.display_name or font.em_size != spec.em_size:
        raise AssertionError(
            f"{spec.option} font metadata changed: {font.name!r}, {font.em_size}"
        )
    missing = missing_characters(font, TEXT)
    if missing:
        raise AssertionError(f"{spec.option} missing characters: {missing}")

    glyphs = [font.glyphs[character] for character in TEXT]
    stroke_counts = tuple(glyph.stroke_count for glyph in glyphs)
    if stroke_counts != spec.stroke_counts:
        raise AssertionError(
            f"{spec.option} path counts changed: {stroke_counts}"
        )
    global_y_min = min(glyph.bounds[1] for glyph in glyphs)
    global_y_max = max(glyph.bounds[3] for glyph in glyphs)
    scale = VISIBLE_HEIGHT_MM / (global_y_max - global_y_min)

    cursor_x = spec.left_mm
    characters: list[shared.CharacterLayout] = []
    strokes: list[shared.Stroke] = []
    for character_index, (character, glyph) in enumerate(zip(TEXT, glyphs)):
        source_x_min, source_y_min, source_x_max, source_y_max = glyph.bounds
        width = (source_x_max - source_x_min) * scale
        points = tuple(
            (
                cursor_x + (source_x - source_x_min) * scale,
                spec.top_logical_mm - (source_y - global_y_min) * scale,
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
                raise AssertionError(
                    f"{spec.option} stroke has no initial direction"
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
                    spec.top_logical_mm
                    - (source_y_max - global_y_min) * scale,
                    cursor_x + width,
                    spec.top_logical_mm
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
            raise AssertionError(f"{spec.option} layout out of bounds: {point}")
    return Group(
        spec,
        shared.Layout(
            font,
            scale,
            tuple(characters),
            tuple(strokes),
            bounds,
        ),
    )


def subdivide(
    points: tuple[tuple[float, float], ...],
) -> tuple[tuple[float, float], ...]:
    result = [points[0]]
    for start, end in zip(points, points[1:]):
        length = math.dist(start, end)
        if length <= 1.0e-9:
            raise AssertionError("gfont path contains a zero segment")
        count = max(1, math.ceil(length / PAPER_SUBDIVISION_MM))
        result.extend(
            (
                start[0] + (end[0] - start[0]) * index / count,
                start[1] + (end[1] - start[1]) * index / count,
            )
            for index in range(1, count + 1)
        )
    return tuple(result)


def group_plan(group: Group) -> tuple[tuple[shared.Stroke, tuple, tuple], ...]:
    return tuple(
        (
            stroke,
            paper_points,
            tuple(map_base_only(point) for point in paper_points),
        )
        for stroke in group.layout.strokes
        for paper_points in (subdivide(stroke.points),)
    )


def gcode_lines(groups: tuple[Group, ...]) -> tuple[str, ...]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware_required={BUILD_ID}",
        "; WARNING=DO_NOT_SEND_TO_V27_OR_OLDER",
        "; one_file=four_fonts each_font_text=ZHANG_JIA_LE_ZUO_PIN",
        "; order=A_TOP_LEFT,B_TOP_RIGHT,C_MIDDLE_LEFT,D_MIDDLE_RIGHT",
        "; A=CHEN_HANDWRITING B=AA_GUO_JINGMING",
        "; C=MEIYOU_RUGUO D=SONG",
        "; source_geometry=UNMODIFIED_GFONT visible_height=9mm",
        "; production_rows=UPPER_AND_MIDDLE third_row=DISCARDED",
        "; map=BASE_QUADRATIC_ONLY old_grid4x7_residual=DISABLED",
        "; v51_photo_quadratic=DISABLED",
        "; firmware_paper_map=DISABLED firmware_global_y_shift=+15mm",
        f"; paper_subdivision_max={PAPER_SUBDIVISION_MM:.1f}mm",
        "G21",
        "G90",
        "G94",
        f"F{FEED_MM_MIN}",
        "S1000",
        "M5",
    ]
    for group in groups:
        spec = group.spec
        lines.extend(
            (
                f"; ===== FONT_{spec.option}_BEGIN =====",
                f"; font={spec.file_name} sha256={spec.sha256}",
                f"; logical_left={spec.left_mm:.1f} "
                f"logical_top={spec.top_logical_mm:.1f}",
            )
        )
        for stroke, _, user_points in group_plan(group):
            approach = map_base_only(stroke.approach)
            lines.extend(
                (
                    f"; font={spec.option} "
                    f"char_index={stroke.character_index + 1} "
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
        lines.append(f"; ===== FONT_{spec.option}_END =====")
    lines.append("M5")
    return tuple(lines)


def home_user() -> tuple[float, float]:
    theta = math.radians(THETA_MIN_DEG)
    psi = math.radians(PSI_MIN_DEG)
    machine_x = -L1_MM * math.cos(theta) - L2_MM * math.cos(psi)
    machine_y = L1_MM * math.sin(theta) + L2_MM * math.sin(psi)
    return machine_x - OFFSET_X_MM, machine_y - OFFSET_Y_MM


def audit(groups: tuple[Group, ...]) -> dict:
    ordered_targets: list[tuple[float, float]] = []
    physical_points: list[tuple[float, float]] = []
    for group in groups:
        for stroke, paper_points, user_points in group_plan(group):
            approach_user = map_base_only(stroke.approach)
            ordered_targets.append(
                (
                    approach_user[0] + SHIFT_X_MM,
                    approach_user[1] + SHIFT_Y_MM,
                )
            )
            ordered_targets.extend(
                (point[0] + SHIFT_X_MM, point[1] + SHIFT_Y_MM)
                for point in user_points
            )
            physical_points.extend(
                (point[0], point[1] + SHIFT_Y_MM) for point in paper_points
            )
            physical_points.append(
                (stroke.approach[0], stroke.approach[1] + SHIFT_Y_MM)
            )

    physical_y = [point[1] for point in physical_points]
    if not (
        NOMINAL_PHYSICAL_WRITING_Y_MIN_MM <= min(physical_y)
        and max(physical_y) <= NOMINAL_PHYSICAL_WRITING_Y_MAX_MM
    ):
        raise AssertionError(
            f"comparison leaves retained rows: "
            f"{min(physical_y):.3f}..{max(physical_y):.3f}"
        )

    previous = home_user()
    worst = (float("inf"), (0.0, 0.0), (0.0, 0.0, 0.0))
    sample_count = 0
    for target in ordered_targets:
        count = max(1, math.ceil(math.dist(previous, target)))
        for index in range(1, count + 1):
            ratio = index / count
            sample = (
                previous[0] + (target[0] - previous[0]) * ratio,
                previous[1] + (target[1] - previous[1]) * ratio,
            )
            margin, angles = joint_margin(sample)
            if margin < worst[0]:
                worst = (margin, sample, angles)
            sample_count += 1
        previous = target
    if worst[0] < -0.001:
        raise AssertionError(f"path violates joint limits: {worst}")
    return {
        "path_sample_count": sample_count,
        "minimum_joint_margin_deg": worst[0],
        "minimum_at_shifted_user_mm": list(worst[1]),
        "minimum_at_angles_deg": list(worst[2]),
        "nominal_physical_paper_y_bounds_mm": [
            min(physical_y),
            max(physical_y),
        ],
    }


def write_preview(groups: tuple[Group, ...]) -> None:
    width = round(shared.A4_WIDTH_MM * 4.0) + 1
    height = round(shared.A4_HEIGHT_MM * 4.0) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (0, 0, width - 1, height - 1),
        outline=(25, 25, 25),
        width=3,
    )
    for group in groups:
        spec = group.spec
        label_point = shared.preview_xy(
            (
                spec.left_mm,
                spec.top_logical_mm + SHIFT_Y_MM + 5.0,
            )
        )
        draw.text(
            label_point,
            f"{spec.option}: {spec.file_name.split('_')[0]}",
            fill=(70, 95, 135),
            font=shared.label_font(15),
        )
        for stroke in group.layout.strokes:
            approach = shared.preview_xy(
                (stroke.approach[0], stroke.approach[1] + SHIFT_Y_MM)
            )
            start = shared.preview_xy(
                (stroke.points[0][0], stroke.points[0][1] + SHIFT_Y_MM)
            )
            shared.draw_dashed_line(
                draw, approach, start, (125, 170, 205), width=1
            )
            draw.line(
                [
                    shared.preview_xy((point[0], point[1] + SHIFT_Y_MM))
                    for point in stroke.points
                ],
                fill=(15, 15, 15),
                width=2,
                joint="curve",
            )
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def write_manifest(
    groups: tuple[Group, ...],
    lines: tuple[str, ...],
    safety: dict,
) -> None:
    text = "\n".join(lines) + "\n"
    group_records = []
    total_strokes = 0
    total_g1 = 0
    for group in groups:
        plan = group_plan(group)
        stroke_count = len(group.layout.strokes)
        g1_count = sum(len(points) - 1 for _, _, points in plan)
        total_strokes += stroke_count
        total_g1 += g1_count
        group_records.append(
            {
                "option": group.spec.option,
                "font_name": group.spec.display_name,
                "font_file": group.spec.file_name,
                "font_sha256": group.spec.sha256,
                "character_path_counts": list(group.spec.stroke_counts),
                "logical_left_mm": group.spec.left_mm,
                "logical_top_mm": group.spec.top_logical_mm,
                "nominal_physical_top_mm": (
                    group.spec.top_logical_mm + SHIFT_Y_MM
                ),
                "logical_bounds_with_approaches_mm": list(
                    group.layout.bounds_mm
                ),
                "stroke_count": stroke_count,
                "g1_count": g1_count,
            }
        )
    manifest = {
        "id": TEST_ID,
        "required_firmware": BUILD_ID,
        "text_per_font": TEXT,
        "visible_height_mm": VISIBLE_HEIGHT_MM,
        "order": [
            "A_TOP_LEFT",
            "B_TOP_RIGHT",
            "C_MIDDLE_LEFT",
            "D_MIDDLE_RIGHT",
        ],
        "groups": group_records,
        "workspace_policy": {
            "retained_rows": ["UPPER", "MIDDLE"],
            "discarded_rows": ["LOWER"],
            "nominal_physical_y_mm": [
                NOMINAL_PHYSICAL_WRITING_Y_MIN_MM,
                NOMINAL_PHYSICAL_WRITING_Y_MAX_MM,
            ],
        },
        "mapping": {
            "base_quadratic_enabled": True,
            "old_grid4x7_residual_enabled": False,
            "v51_photo_quadratic_enabled": False,
            "firmware_paper_map_enabled": False,
            "firmware_global_translation_user_mm": [
                SHIFT_X_MM,
                SHIFT_Y_MM,
            ],
        },
        "motion": {
            "feed_mm_min": FEED_MM_MIN,
            "tangent_approach_mm": TANGENT_APPROACH_MM,
            "paper_subdivision_max_mm": PAPER_SUBDIVISION_MM,
            "stroke_count": total_strokes,
            "g1_count": total_g1,
        },
        "safety": safety,
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
    groups = tuple(build_group(spec) for spec in FONT_SPECS)
    safety = audit(groups)
    lines = gcode_lines(groups)
    GCODE_PATH.write_text(
        "\n".join(lines) + "\n",
        encoding="ascii",
        newline="\n",
    )
    write_preview(groups)
    write_manifest(groups, lines, safety)
    print(
        "four_font_comparison_v56=PASS "
        f"groups={len(groups)} characters={len(groups) * len(TEXT)} "
        f"strokes={sum(len(group.layout.strokes) for group in groups)} "
        f"G1={sum(sum(len(points) - 1 for _, _, points in group_plan(group)) for group in groups)} "
        f"physical_y={safety['nominal_physical_paper_y_bounds_mm'][0]:.3f}"
        f"..{safety['nominal_physical_paper_y_bounds_mm'][1]:.3f} "
        f"min_joint_margin={safety['minimum_joint_margin_deg']:.6f}deg"
    )
    for group in groups:
        print(
            f"{group.spec.option}={group.spec.display_name} "
            f"bounds={group.layout.bounds_mm}"
        )
    print(GCODE_PATH)
    print(PREVIEW_PATH)
    print(MANIFEST_PATH)


if __name__ == "__main__":
    main()
