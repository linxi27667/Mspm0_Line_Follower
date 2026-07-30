#!/usr/bin/env python3
"""Lay out the complete diary on one A4 sheet inside the modeled safe wedge.

This is an offline comparison artifact, never runnable G-code.  Each text row
starts at a separately calculated X coordinate so the layout follows the
current mechanism's 10-degree joint-margin boundary instead of being confined
to the small V36 rectangular text area.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

import check_author_text_demo_v30 as v30
import generate_diary_notebook_offline_preview as base


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "gcode" / "DIARY_NOTEBOOK_MAX_REACHABLE_ONE_PAGE_20260721.json"
LAYOUT_TEXT_PATH = (
    ROOT
    / "gcode"
    / "DIARY_NOTEBOOK_MAX_REACHABLE_ONE_PAGE_NOT_FOR_ROBOT_20260721.txt"
)
PREVIEW_PATH = (
    ROOT
    / "docs"
    / "diagnostics"
    / "DIARY_NOTEBOOK_MAX_REACHABLE_ONE_PAGE_OFFLINE_PREVIEW_20260721.png"
)

PAPER_MARGIN_MM = 15.0
RIGHT_EDGE_MM = base.A4_WIDTH_MM - PAPER_MARGIN_MM
BOTTOM_EDGE_MM = PAPER_MARGIN_MM
LAYOUT_TOP_REFERENCE_MM = 182.0
LINE_PITCH_MM = 12.0
FONT_SIZE_PERCENT = 95.0
WORD_GAP_MM = 0.6
MIN_JOINT_MARGIN_DEG = 10.0
BOUNDARY_PAD_MM = 1.0
BOUNDARY_SAMPLE_MM = 0.5
X_SEARCH_STEP_MM = 0.5
PIXELS_PER_MM = 4.0


@dataclass(frozen=True)
class RowSpec:
    number: int
    x_start_mm: float
    x_end_mm: float
    y_min_mm: float
    y_max_mm: float
    minimum_boundary_x_mm: float


def quantized_margin(x_mm: float, y_mm: float) -> float | None:
    model = v30.v21.base
    try:
        theta, psi = model.inverse(x_mm, y_mm)
    except AssertionError:
        return None
    stage1 = model.lroundf(theta * model.STAGE1_STEPS_PER_DEG)
    stage2 = model.lroundf(psi * model.STAGE2_STEPS_PER_DEG)
    if stage2 / float(model.STAGE2_STEPS_PER_DEG) <= stage1 / float(
        model.STAGE1_STEPS_PER_DEG
    ):
        return None
    return model.pose_margin(stage1, stage2)


def safe_boundary_x(y_mm: float) -> float | None:
    steps = round((RIGHT_EDGE_MM - PAPER_MARGIN_MM) / X_SEARCH_STEP_MM)
    for index in range(steps + 1):
        x_mm = PAPER_MARGIN_MM + index * X_SEARCH_STEP_MM
        margin = quantized_margin(x_mm, y_mm)
        if margin is not None and margin >= MIN_JOINT_MARGIN_DEG:
            return x_mm
    return None


def safe_x_for_band(y_min_mm: float, y_max_mm: float) -> float:
    required_x = PAPER_MARGIN_MM
    sample_count = math.ceil((y_max_mm - y_min_mm) / BOUNDARY_SAMPLE_MM)
    for index in range(sample_count + 1):
        y_mm = min(y_min_mm + index * BOUNDARY_SAMPLE_MM, y_max_mm)
        boundary = safe_boundary_x(y_mm)
        if boundary is None:
            raise AssertionError(f"no 10-degree safe X at y={y_mm:.3f}")
        required_x = max(required_x, boundary)
    return required_x


def build_rows(
    font: base.GFont,
    glyphs: dict[str, base.Glyph],
    text: str,
) -> tuple[RowSpec, ...]:
    scale = LINE_PITCH_MM / float(font.em_size) * (FONT_SIZE_PERCENT / 100.0)
    used = [glyphs[character] for character in text if not character.isspace()]
    source_y_min = min(glyph.bounds[1] for glyph in used)
    source_y_max = max(glyph.bounds[3] for glyph in used)
    rows: list[RowSpec] = []
    row_index = 0
    while True:
        baseline_down = row_index * LINE_PITCH_MM + LINE_PITCH_MM * 0.75
        y_max = LAYOUT_TOP_REFERENCE_MM - (baseline_down + source_y_min * scale)
        y_min = LAYOUT_TOP_REFERENCE_MM - (baseline_down + source_y_max * scale)
        if y_min < BOTTOM_EDGE_MM:
            break
        boundary = safe_x_for_band(y_min, y_max)
        x_start = math.ceil((boundary + BOUNDARY_PAD_MM) * 10.0) / 10.0
        if x_start >= RIGHT_EDGE_MM:
            break
        rows.append(
            RowSpec(
                number=row_index + 1,
                x_start_mm=x_start,
                x_end_mm=RIGHT_EDGE_MM,
                y_min_mm=y_min,
                y_max_mm=y_max,
                minimum_boundary_x_mm=boundary,
            )
        )
        row_index += 1
    if not rows:
        raise AssertionError("no usable one-page rows")
    return tuple(rows)


def layout_text(
    text: str,
    font: base.GFont,
    glyphs: dict[str, base.Glyph],
    rows: tuple[RowSpec, ...],
) -> base.PageLayout:
    scale = LINE_PITCH_MM / float(font.em_size) * (FONT_SIZE_PERCENT / 100.0)
    page = base.PageLayout(1, [""], [])
    row_index = 0
    x_cursor = rows[0].x_start_mm

    def next_row() -> None:
        nonlocal row_index, x_cursor
        row_index += 1
        if row_index >= len(rows):
            raise AssertionError("full diary did not fit the modeled one-page wedge")
        x_cursor = rows[row_index].x_start_mm
        page.lines.append("")

    for character in text:
        if character in "\r\n":
            if character == "\n":
                next_row()
            continue
        if character.isspace():
            advance = LINE_PITCH_MM * (FONT_SIZE_PERCENT / 100.0) * 0.5
            if x_cursor + advance > RIGHT_EDGE_MM:
                next_row()
            x_cursor += advance
            page.lines[row_index] += character
            continue

        glyph = glyphs[character]
        bounds_x0, _, bounds_x1, _ = glyph.bounds
        scaled_x0 = bounds_x0 * scale
        width_mm = (bounds_x1 - bounds_x0) * scale
        x_correction = -scaled_x0 if scaled_x0 < 0.0 else 0.0
        if x_cursor + width_mm > RIGHT_EDGE_MM + 1.0e-9:
            next_row()

        translate_x = x_cursor + x_correction
        baseline_down = row_index * LINE_PITCH_MM + LINE_PITCH_MM * 0.75
        points = tuple(
            base.PathPoint(
                translate_x + source_x * scale,
                LAYOUT_TOP_REFERENCE_MM - (baseline_down + source_y * scale),
                command == 1,
            )
            for (source_x, source_y), command in zip(glyph.points, glyph.commands)
        )
        if not points or points[0].draw:
            raise AssertionError(f"glyph {character!r} does not begin pen-up")
        for point in points:
            if not (
                PAPER_MARGIN_MM - 1.0e-6 <= point.x_mm <= RIGHT_EDGE_MM + 1.0e-6
                and PAPER_MARGIN_MM - 1.0e-6
                <= point.y_mm
                <= base.A4_HEIGHT_MM - PAPER_MARGIN_MM + 1.0e-6
            ):
                raise AssertionError(
                    f"{character!r} left A4 paper margin at "
                    f"({point.x_mm:.3f},{point.y_mm:.3f})"
                )
            margin = quantized_margin(point.x_mm, point.y_mm)
            if margin is None or margin < MIN_JOINT_MARGIN_DEG:
                raise AssertionError(
                    f"{character!r} left modeled joint margin at "
                    f"({point.x_mm:.3f},{point.y_mm:.3f}) margin={margin}"
                )
        source_kind = "composite" if character in base.COMPOSITE_COMPONENTS else "gfont"
        page.placements.append(
            base.Placement(1, row_index + 1, character, source_kind, points)
        )
        page.lines[row_index] += character
        x_cursor += width_mm + WORD_GAP_MM

    if "".join(page.lines) != text.replace("\n", ""):
        raise AssertionError("one-page wrapping changed source text")
    return page


def preview_xy(x_mm: float, y_mm: float) -> tuple[int, int]:
    return (
        round(x_mm * PIXELS_PER_MM),
        round((base.A4_HEIGHT_MM - y_mm) * PIXELS_PER_MM),
    )


def write_preview(page: base.PageLayout, rows: tuple[RowSpec, ...]) -> None:
    width = round(base.A4_WIDTH_MM * PIXELS_PER_MM) + 1
    height = round(base.A4_HEIGHT_MM * PIXELS_PER_MM) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    label_font = base.load_label_font(22)
    small_font = base.load_label_font(16)
    draw.rectangle((0, 0, width - 1, height - 1), outline=(25, 25, 25), width=3)

    boundary_points: list[tuple[int, int]] = []
    y_value = PAPER_MARGIN_MM
    while y_value <= 192.0:
        boundary = safe_boundary_x(y_value)
        if boundary is not None:
            boundary_points.append(preview_xy(boundary, y_value))
        y_value += 1.0
    if boundary_points:
        polygon = boundary_points + [
            preview_xy(RIGHT_EDGE_MM, 192.0),
            preview_xy(RIGHT_EDGE_MM, PAPER_MARGIN_MM),
        ]
        draw.polygon(polygon, fill=(243, 248, 254))
        draw.line(boundary_points, fill=(55, 115, 190), width=3)

    paper_margin_top_left = preview_xy(PAPER_MARGIN_MM, base.A4_HEIGHT_MM - PAPER_MARGIN_MM)
    paper_margin_bottom_right = preview_xy(RIGHT_EDGE_MM, PAPER_MARGIN_MM)
    base.draw_dashed_rectangle(
        draw,
        (
            paper_margin_top_left[0],
            paper_margin_top_left[1],
            paper_margin_bottom_right[0],
            paper_margin_bottom_right[1],
        ),
        (170, 170, 170),
        width=1,
    )

    for row in rows:
        start = preview_xy(row.x_start_mm, row.y_min_mm)
        end = preview_xy(row.x_start_mm, row.y_max_mm)
        draw.line((start, end), fill=(120, 165, 215), width=2)

    for placement in page.placements:
        previous: tuple[int, int] | None = None
        for point in placement.points:
            current = preview_xy(point.x_mm, point.y_mm)
            if point.draw and previous is not None:
                draw.line((previous, current), fill=(12, 12, 12), width=2)
            previous = current

    draw.text((20, 15), "单页最大可达区预览／不可直接运行", fill=(185, 35, 35), font=label_font)
    draw.text(
        (20, 48),
        "A4横向；蓝线为10°关节余量边界，文字按行阶梯式左移",
        fill=(70, 70, 70),
        font=small_font,
    )
    draw.text(
        (20, 76),
        "左上灰白区域不可强行铺满；全区域写字精度尚未实机标定",
        fill=(100, 100, 100),
        font=small_font,
    )
    draw.text(
        (20, height - 32),
        "全文一页14行；最大字形高度约8.8 mm；右上起点已记录；局部Y×1.095未外推",
        fill=(70, 70, 70),
        font=small_font,
    )
    image.save(PREVIEW_PATH)


def write_reports(
    text: str,
    font: base.GFont,
    missing: str,
    rows: tuple[RowSpec, ...],
    page: base.PageLayout,
) -> None:
    points = base.flattened_points(page)
    glyph_height = max(
        max(point.y_mm for point in placement.points)
        - min(point.y_mm for point in placement.points)
        for placement in page.placements
    )
    report = {
        "artifact": "DIARY_NOTEBOOK_MAX_REACHABLE_ONE_PAGE_20260721",
        "runnable_on_robot": False,
        "source_text_sha256": base.digest(base.SOURCE_TEXT),
        "source_docx_sha256": base.digest(base.SOURCE_DOCX),
        "font_name": font.name,
        "font_sha256": base.digest(base.FONT_PATH),
        "missing_characters_replaced_by_disclosed_composites": missing,
        "unresolved_characters": "",
        "paper": {
            "size_mm": [base.A4_WIDTH_MM, base.A4_HEIGHT_MM],
            "orientation": "landscape",
            "paper_origin": "lower-left",
            "kenjoy_origin": "right-upper",
            "paper_margin_mm": PAPER_MARGIN_MM,
        },
        "layout": {
            "page_count": 1,
            "line_count": len(page.lines),
            "line_pitch_mm": LINE_PITCH_MM,
            "font_size_percent": FONT_SIZE_PERCENT,
            "maximum_actual_glyph_height_mm": round(glyph_height, 6),
            "joint_margin_boundary_deg": MIN_JOINT_MARGIN_DEG,
            "boundary_pad_mm": BOUNDARY_PAD_MM,
            "local_y_correction_applied": False,
            "local_y_correction_reason": "validated only near y=65; not extrapolated",
            "lines": page.lines,
            "rows": [
                {
                    "row": row.number,
                    "x_start_mm": row.x_start_mm,
                    "x_end_mm": row.x_end_mm,
                    "y_min_mm": round(row.y_min_mm, 6),
                    "y_max_mm": round(row.y_max_mm, 6),
                    "raw_boundary_x_mm": row.minimum_boundary_x_mm,
                }
                for row in rows[: len(page.lines)]
            ],
        },
        "path": {
            "glyph_count": len(page.placements),
            "stroke_count": sum(
                sum(not point.draw for point in placement.points)
                for placement in page.placements
            ),
            "point_count": len(points),
            "bounds_mm": [
                round(min(point.x_mm for point in points), 6),
                round(min(point.y_mm for point in points), 6),
                round(max(point.x_mm for point in points), 6),
                round(max(point.y_mm for point in points), 6),
            ],
        },
        "blocking_reasons": [
            "current V36 rejects ordinary G-code",
            "full wedge writing accuracy has not been physically calibrated",
            "single-page glyph height is smaller than the successful 16 mm V36 test",
        ],
        "preview": str(PREVIEW_PATH),
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    lines = [
        "DIARY NOTEBOOK MAX-REACHABLE ONE-PAGE LAYOUT — NOT FOR ROBOT",
        "全文一页预览；当前 V36 不能运行；扩大区域尚未实机标定。",
        f"A4横向，右上起点，行距={LINE_PITCH_MM:.1f} mm，行数={len(page.lines)}",
        "蓝色边界按当前L1/L2、offset、steps/degree和10度关节余量计算。",
        "局部Y×1.095未应用；奎享F3000不得使用。",
        "",
    ]
    lines.extend(f"{index + 1:02d}: {line}" for index, line in enumerate(page.lines))
    LAYOUT_TEXT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def generate() -> tuple[str, base.GFont, str, tuple[RowSpec, ...], base.PageLayout]:
    v30.configure_model()
    text = base.SOURCE_TEXT.read_text(encoding="utf-8").rstrip("\r\n")
    font = base.load_gfont(base.FONT_PATH)
    glyphs, missing = base.glyph_map(font, text)
    rows = build_rows(font, glyphs, text)
    page = layout_text(text, font, glyphs, rows)
    return text, font, missing, rows, page


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    text, font, missing, rows, page = generate()
    points = base.flattened_points(page)
    glyph_height = max(
        max(point.y_mm for point in placement.points)
        - min(point.y_mm for point in placement.points)
        for placement in page.placements
    )
    print(
        f"one_page_layout=PASS rows_available={len(rows)} rows_used={len(page.lines)} "
        f"glyphs={len(page.placements)} points={len(points)} "
        f"max_glyph_height_mm={glyph_height:.6f} missing={missing} "
        "unresolved=0 runnable=0"
    )
    for row, line in zip(rows, page.lines):
        print(
            f"row={row.number:02d} x={row.x_start_mm:.1f}..{row.x_end_mm:.1f} "
            f"y={row.y_min_mm:.3f}..{row.y_max_mm:.3f} text={line}"
        )
    if args.write:
        write_preview(page, rows)
        write_reports(text, font, missing, rows, page)
        print(f"preview={PREVIEW_PATH}")
        print(f"report={REPORT_PATH}")
        print(f"layout_text={LAYOUT_TEXT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
