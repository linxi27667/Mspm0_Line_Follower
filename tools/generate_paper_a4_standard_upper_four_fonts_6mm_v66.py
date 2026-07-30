#!/usr/bin/env python3
"""Generate four mixed-font upper rows in standard A4 paper coordinates."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from check_firmware_right_sbow_v30 import firmware_map
from check_workspace_yshift15_v28 import joint_margin
from generate_ma_shan_zheng_gcode import outline_paths, rasterize_text
from generate_paper_a4_full_width_square_spiral_v59 import home_user
from generate_paper_a4_standard_upper_bfont_6mm_v65 import (
    CHARACTER_GAP_MM,
    PAPER_X_MAX_MM,
    PAPER_X_MIN_MM,
    PAPER_Y_MAX_MM,
    PAPER_Y_MIN_MM,
    SPACE_ADVANCE_MM,
    TANGENT_APPROACH_MM,
    paper_line_samples,
    user_line_samples,
)
from generate_paper_a4_zhang_jia_le_v30 import (
    A4_HEIGHT_MM,
    A4_WIDTH_MM,
    label_font,
    preview_xy,
    split_strokes,
)
from kenjoy_gfont import load_gfont, missing_characters


TEST_ID = "PAPER_A4_STANDARD_UPPER_4FONT_6MM_WRITER_TEST_TIMESTAMP_GCODE_V66"
FIRMWARE_ID = (
    "PAPER_A4_STANDARD_GCODE_RIGHT_SBOW_PAPERMAP_YSHIFT15_V30"
)
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"

REQUESTED_TEXT = (
    "\u5199\u5b57\u673a\u7b2c\u597d\u591a\u6b21\u6d4b\u8bd5"
    "\uff0c7.25  5.23am"
)
B_RENDERED_TEXT = REQUESTED_TEXT.replace(".", "\u3002")

VISIBLE_HEIGHT_MM = 6.0
MAXIMUM_WIDTH_MM = 150.0
CONTENT_LEFT_MM = 30.0
ROW_TOPS_MM = (230.0, 216.0, 202.0, 188.0)
TTF_OUTLINE_SIMPLIFY_MM = 0.10
FEED_MM_MIN = 300
PREVIEW_PIXELS_PER_MM = 4.0


@dataclass(frozen=True)
class FontSpec:
    option: str
    label: str
    kind: str
    path: Path
    sha256: str
    top_mm: float


@dataclass(frozen=True)
class RowStroke:
    approach: tuple[float, float]
    points: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class FontRow:
    spec: FontSpec
    family: str
    style: str
    rendered_text: str
    source_geometry: str
    strokes: tuple[RowStroke, ...]
    bounds_mm: tuple[float, float, float, float]
    visible_size_mm: tuple[float, float]


FONT_SPECS = (
    FontSpec(
        "K",
        "ZHENG_KAI_KAITI",
        "ttf",
        Path(r"C:\Windows\Fonts\simkai.ttf"),
        "A6ACF69A7A6E8A4CBA014266036ECA8629560038CC50783F46917748FABEFBE5",
        ROW_TOPS_MM[0],
    ),
    FontSpec(
        "B",
        "B_AA_GUO_JINGMING",
        "gfont",
        ROOT / "assets" / "kenjoy_gfont" / "AA_GUO_JINGMING_b7c9ccc1.gfont",
        "D5D8E41EF24BF380FDAB57B4746795D691CC4E2DF878A394E4FA8C6D594C09F8",
        ROW_TOPS_MM[1],
    ),
    FontSpec(
        "M",
        "MA_SHAN_ZHENG",
        "ttf",
        ROOT / "assets" / "ma_shan_zheng" / "MaShanZheng-Regular.ttf",
        "6D2546BB189C732A8CA29AF9E22457B152387D158AA459E4AC2CE1E51788B7FB",
        ROW_TOPS_MM[2],
    ),
    FontSpec(
        "Y",
        "YOUYUAN",
        "ttf",
        Path(r"C:\Windows\Fonts\SIMYOU.TTF"),
        "E4440E07E02FA6B5A8F497DA52FCAB0AA711B399D43FF28A2BA246C603363930",
        ROW_TOPS_MM[3],
    ),
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def tangent_approach(
    points: tuple[tuple[float, float], ...],
) -> tuple[float, float]:
    if len(points) < 2:
        raise AssertionError("font path has fewer than two points")
    first_length = math.dist(points[0], points[1])
    if first_length <= 1.0e-9:
        raise AssertionError("font path has a zero initial segment")
    unit_x = (points[1][0] - points[0][0]) / first_length
    unit_y = (points[1][1] - points[0][1]) / first_length
    return (
        points[0][0] - unit_x * TANGENT_APPROACH_MM,
        points[0][1] - unit_y * TANGENT_APPROACH_MM,
    )


def verify_ttf_coverage(font_path: Path, text: str) -> None:
    font = ImageFont.truetype(str(font_path), 1024)
    missing_mask = bytes(font.getmask(chr(0x10FFFF), mode="L"))
    missing = [
        character
        for character in dict.fromkeys(text)
        if not character.isspace()
        and bytes(font.getmask(character, mode="L")) == missing_mask
    ]
    if missing:
        raise AssertionError(
            f"{font_path.name} missing characters: {''.join(missing)!r}"
        )


def row_bounds(
    strokes: tuple[RowStroke, ...],
) -> tuple[float, float, float, float]:
    points = [
        point
        for stroke in strokes
        for point in (stroke.approach, *stroke.points)
    ]
    if not points:
        raise AssertionError("font row contains no paths")
    bounds = (
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )
    for point in points:
        if not (
            PAPER_X_MIN_MM <= point[0] <= PAPER_X_MAX_MM
            and PAPER_Y_MIN_MM <= point[1] <= PAPER_Y_MAX_MM
        ):
            raise AssertionError(f"font row point out of bounds: {point}")
    return bounds


def build_ttf_row(spec: FontSpec) -> FontRow:
    verify_ttf_coverage(spec.path, REQUESTED_TEXT)
    raster = rasterize_text(
        REQUESTED_TEXT,
        spec.path,
        VISIBLE_HEIGHT_MM,
        MAXIMUM_WIDTH_MM,
    )
    plot_paths = outline_paths(
        raster,
        CONTENT_LEFT_MM,
        spec.top_mm,
        TTF_OUTLINE_SIMPLIFY_MM,
    )
    strokes = tuple(
        RowStroke(tangent_approach(path.points), path.points)
        for path in plot_paths
    )
    return FontRow(
        spec,
        raster.font_family,
        raster.font_style,
        REQUESTED_TEXT,
        "TTF_FILLED_OUTLINE_CONTOURS",
        strokes,
        row_bounds(strokes),
        (raster.width_mm, raster.height_mm),
    )


def build_b_row(spec: FontSpec) -> FontRow:
    font = load_gfont(spec.path)
    if font.name != "aa\u90ed\u656c\u660e\u5b57\u4f53" or font.em_size != 525:
        raise AssertionError(f"unexpected B metadata: {font.name!r}")
    missing = missing_characters(font, B_RENDERED_TEXT)
    if missing:
        raise AssertionError(f"B gfont missing: {missing!r}")

    glyphs = [
        font.glyphs[character]
        for character in B_RENDERED_TEXT
        if not character.isspace()
    ]
    global_y_min = min(glyph.bounds[1] for glyph in glyphs)
    global_y_max = max(glyph.bounds[3] for glyph in glyphs)
    scale = VISIBLE_HEIGHT_MM / (global_y_max - global_y_min)
    cursor_x = CONTENT_LEFT_MM
    strokes: list[RowStroke] = []
    for character in B_RENDERED_TEXT:
        if character.isspace():
            cursor_x += SPACE_ADVANCE_MM
            continue
        glyph = font.glyphs[character]
        source_x_min, _, source_x_max, _ = glyph.bounds
        width = (source_x_max - source_x_min) * scale
        points = tuple(
            (
                cursor_x + (source_x - source_x_min) * scale,
                spec.top_mm - (source_y - global_y_min) * scale,
            )
            for source_x, source_y in glyph.points
        )
        for stroke_points in split_strokes(
            character, points, glyph.commands
        ):
            strokes.append(
                RowStroke(
                    tangent_approach(stroke_points),
                    stroke_points,
                )
            )
        cursor_x += width + CHARACTER_GAP_MM
    frozen_strokes = tuple(strokes)
    bounds = row_bounds(frozen_strokes)
    return FontRow(
        spec,
        font.name,
        "single-line",
        B_RENDERED_TEXT,
        "UNMODIFIED_GFONT_PATH_POINTS_AND_COMMAND_ORDER",
        frozen_strokes,
        bounds,
        (bounds[2] - CONTENT_LEFT_MM, VISIBLE_HEIGHT_MM),
    )


def build_rows() -> tuple[FontRow, ...]:
    rows = []
    for spec in FONT_SPECS:
        if not spec.path.is_file():
            raise FileNotFoundError(spec.path)
        if digest(spec.path) != spec.sha256:
            raise AssertionError(f"font {spec.option} hash changed")
        rows.append(
            build_b_row(spec) if spec.kind == "gfont"
            else build_ttf_row(spec)
        )
    frozen_rows = tuple(rows)
    for upper, lower in zip(frozen_rows, frozen_rows[1:]):
        clearance = upper.bounds_mm[1] - lower.bounds_mm[3]
        if clearance < 4.0:
            raise AssertionError(
                f"rows {upper.spec.option}/{lower.spec.option} "
                f"too close: {clearance:.3f} mm"
            )
    overall_y_min = min(row.bounds_mm[1] for row in frozen_rows)
    overall_y_max = max(row.bounds_mm[3] for row in frozen_rows)
    if overall_y_min < 180.0 or overall_y_max > 232.0:
        raise AssertionError(
            f"four rows leave upper band: {overall_y_min}..{overall_y_max}"
        )
    return frozen_rows


def gcode_lines(rows: tuple[FontRow, ...]) -> tuple[str, ...]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware_required={FIRMWARE_ID}",
        "; coordinates=STANDARD_A4_PHYSICAL_PAPER_MM",
        "; offline_mapping=NONE offline_prewarp=NONE",
        "; four_fonts=ZHENG_KAI,B,MA_SHAN_ZHENG,YOUYUAN",
        "; one_font_per_row=YES visible_height=6mm",
        "; requested_text=WRITER_TEST_COUNT_7.25__5.23am",
        "; B_ASCII_PERIOD_USES_ORIGINAL_GFONT_U3002=YES",
        "; placement=UPPER_VALIDATED_BAND",
        "; firmware_owns=BASE_MAP,RIGHT_HALF_VERTICAL_SBOW,HORIZONTAL_SBOW,YSHIFT15",
        "G21",
        "G90",
        "G94",
        f"F{FEED_MM_MIN}",
        "S1000",
        "M5",
    ]
    for row in rows:
        lines.extend(
            (
                f"; ===== FONT_{row.spec.option}_BEGIN =====",
                f"; label={row.spec.label} file={row.spec.path.name}",
                f"; sha256={row.spec.sha256}",
                f"; row_top_mm={row.spec.top_mm:.1f} "
                f"source_geometry={row.source_geometry}",
            )
        )
        for path_index, stroke in enumerate(row.strokes, start=1):
            lines.extend(
                (
                    f"; font={row.spec.option} path={path_index}",
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
        lines.append(f"; ===== FONT_{row.spec.option}_END =====")
    lines.append("M5")
    return tuple(lines)


def audit(rows: tuple[FontRow, ...], lines: tuple[str, ...]) -> dict:
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

    for row in rows:
        for stroke in row.strokes:
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
        raise AssertionError(f"V30/V66 path violates joint limits: {worst}")
    if any(len(line) >= 192 for line in lines):
        raise AssertionError("V66 contains an overlong serial line")
    return {
        "safe_samples": safe_samples,
        "min_joint_margin_deg": worst[0],
        "min_margin_user_mm": list(worst[1]),
        "stroke_count": sum(len(row.strokes) for row in rows),
        "stroke_count_by_font": {
            row.spec.option: len(row.strokes) for row in rows
        },
        "motion_line_count": sum(
            line.startswith(("G0 ", "G1 ")) for line in lines
        ),
    }


def write_preview(rows: tuple[FontRow, ...]) -> None:
    width = round(A4_WIDTH_MM * PREVIEW_PIXELS_PER_MM) + 1
    height = round(A4_HEIGHT_MM * PREVIEW_PIXELS_PER_MM) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (0, 0, width - 1, height - 1),
        outline=(30, 30, 30),
        width=3,
    )
    colors = (
        (185, 45, 45),
        (35, 95, 190),
        (30, 145, 75),
        (35, 35, 35),
    )
    for row, color in zip(rows, colors):
        for stroke in row.strokes:
            draw.line(
                [preview_xy(point) for point in stroke.points],
                fill=color,
                width=2,
                joint="curve",
            )
        label_y = round(
            (A4_HEIGHT_MM - row.spec.top_mm) * PREVIEW_PIXELS_PER_MM
        )
        draw.text(
            (10, label_y),
            row.spec.option,
            fill=color,
            font=label_font(17),
        )
    draw.text(
        (20, 18),
        "V66 / K=Zheng Kai, B, M=Ma Shan Zheng, Y=YouYuan",
        fill=(25, 25, 25),
        font=label_font(18),
    )
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def main() -> None:
    rows = build_rows()
    lines = gcode_lines(rows)
    text = "\n".join(lines) + "\n"
    safety = audit(rows, lines)
    GCODE_PATH.parent.mkdir(parents=True, exist_ok=True)
    GCODE_PATH.write_text(text, encoding="ascii", newline="\n")
    manifest = {
        "id": TEST_ID,
        "required_firmware": FIRMWARE_ID,
        "requested_text": REQUESTED_TEXT,
        "fonts": [
            {
                "option": row.spec.option,
                "label": row.spec.label,
                "family": row.family,
                "style": row.style,
                "kind": row.spec.kind,
                "file": str(row.spec.path),
                "sha256": row.spec.sha256,
                "rendered_text": row.rendered_text,
                "source_geometry": row.source_geometry,
                "synthesized_glyphs": False,
                "row_top_mm": row.spec.top_mm,
                "visible_size_mm": list(row.visible_size_mm),
                "bounds_mm": list(row.bounds_mm),
                "stroke_count": len(row.strokes),
            }
            for row in rows
        ],
        "layout": {
            "visible_height_mm": VISIBLE_HEIGHT_MM,
            "content_left_mm": CONTENT_LEFT_MM,
            "row_top_mm": list(ROW_TOPS_MM),
            "upper_validated_band_mm": [180.0, 232.0],
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
    write_preview(rows)
    print(
        "standard_upper_four_fonts_6mm_v66=PASS "
        f"rows={len(rows)} strokes={safety['stroke_count']} "
        f"motion_lines={safety['motion_line_count']} "
        f"safe_samples={safety['safe_samples']} "
        f"min_joint_margin={safety['min_joint_margin_deg']:.6f}deg"
    )
    for row in rows:
        print(
            f"font_{row.spec.option} label={row.spec.label} "
            f"bounds={row.bounds_mm} strokes={len(row.strokes)}"
        )
    print(f"gcode_sha256={manifest['gcode']['sha256']}")
    print(GCODE_PATH)
    print(MANIFEST_PATH)
    print(PREVIEW_PATH)


if __name__ == "__main__":
    main()
