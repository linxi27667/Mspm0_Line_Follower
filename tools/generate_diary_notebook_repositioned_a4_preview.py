#!/usr/bin/env python3
"""Generate a full-sheet diary preview using a translated paper alignment.

The existing M801 machine target remains (150,20).  The paper is translated so
that its (11,88) cross in the left margin is placed under that pen position.
Paper coordinates then map to motion-command coordinates as
``command = paper + (139,-68)``.

This file produces offline PNG/JSON/TXT evidence only, never runnable G-code.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

import generate_diary_notebook_offline_preview as base


ROOT = Path(__file__).resolve().parents[1]
PREVIEW_PATH = (
    ROOT
    / "docs"
    / "diagnostics"
    / "DIARY_NOTEBOOK_REPOSITIONED_A4_ONE_PAGE_OFFLINE_PREVIEW_20260721.png"
)
REPORT_PATH = (
    ROOT / "gcode" / "DIARY_NOTEBOOK_REPOSITIONED_A4_ONE_PAGE_20260721.json"
)
LAYOUT_TEXT_PATH = (
    ROOT
    / "gcode"
    / "DIARY_NOTEBOOK_REPOSITIONED_A4_ONE_PAGE_NOT_FOR_ROBOT_20260721.txt"
)

PAPER_MARGIN_MM = 15.0
PAPER_X0_MM = PAPER_MARGIN_MM
PAPER_X1_MM = base.A4_WIDTH_MM - PAPER_MARGIN_MM
PAPER_Y0_MM = PAPER_MARGIN_MM
PAPER_Y1_MM = base.A4_HEIGHT_MM - PAPER_MARGIN_MM

COMMAND_SHIFT_X_MM = 139.0
COMMAND_SHIFT_Y_MM = -68.0
ALIGN_COMMAND_X_MM = 150.0
ALIGN_COMMAND_Y_MM = 20.0
ALIGN_PAPER_X_MM = ALIGN_COMMAND_X_MM - COMMAND_SHIFT_X_MM
ALIGN_PAPER_Y_MM = ALIGN_COMMAND_Y_MM - COMMAND_SHIFT_Y_MM

LINE_PITCH_MM = 16.0
FONT_SIZE_PERCENT = 95.0
WORD_GAP_MM = 0.6
PIXELS_PER_MM = 4.0


def paper_to_command(x_mm: float, y_mm: float) -> tuple[float, float]:
    return x_mm + COMMAND_SHIFT_X_MM, y_mm + COMMAND_SHIFT_Y_MM


def command_to_paper(x_mm: float, y_mm: float) -> tuple[float, float]:
    return x_mm - COMMAND_SHIFT_X_MM, y_mm - COMMAND_SHIFT_Y_MM


def layout_text(
    text: str,
    font: base.GFont,
    glyphs: dict[str, base.Glyph],
) -> base.PageLayout:
    scale = LINE_PITCH_MM / float(font.em_size) * (FONT_SIZE_PERCENT / 100.0)
    page = base.PageLayout(1, [""], [])
    row_index = 0
    x_cursor = PAPER_X0_MM

    def next_row() -> None:
        nonlocal row_index, x_cursor
        row_index += 1
        x_cursor = PAPER_X0_MM
        page.lines.append("")

    for character in text:
        if character in "\r\n":
            if character == "\n":
                next_row()
            continue
        if character.isspace():
            advance = LINE_PITCH_MM * (FONT_SIZE_PERCENT / 100.0) * 0.5
            if x_cursor + advance > PAPER_X1_MM:
                next_row()
            x_cursor += advance
            page.lines[row_index] += character
            continue

        glyph = glyphs[character]
        bounds_x0, _, bounds_x1, _ = glyph.bounds
        scaled_x0 = bounds_x0 * scale
        scaled_x1 = bounds_x1 * scale
        width_mm = (bounds_x1 - bounds_x0) * scale
        x_correction = -scaled_x0 if scaled_x0 < 0.0 else 0.0
        right_extent = x_correction + scaled_x1
        if x_cursor + right_extent > PAPER_X1_MM + 1.0e-9:
            next_row()

        translate_x = x_cursor + x_correction
        baseline_down = row_index * LINE_PITCH_MM + LINE_PITCH_MM * 0.75
        points = tuple(
            base.PathPoint(
                translate_x + source_x * scale,
                PAPER_Y1_MM - (baseline_down + source_y * scale),
                command == 1,
            )
            for (source_x, source_y), command in zip(glyph.points, glyph.commands)
        )
        if not points or points[0].draw:
            raise AssertionError(f"glyph {character!r} does not begin pen-up")
        for point in points:
            if not (
                PAPER_X0_MM - 1.0e-6 <= point.x_mm <= PAPER_X1_MM + 1.0e-6
                and PAPER_Y0_MM - 1.0e-6 <= point.y_mm <= PAPER_Y1_MM + 1.0e-6
            ):
                raise AssertionError(
                    f"{character!r} left 15 mm paper margin at "
                    f"({point.x_mm:.3f},{point.y_mm:.3f})"
                )
        source_kind = "composite" if character in base.COMPOSITE_COMPONENTS else "gfont"
        page.placements.append(
            base.Placement(1, row_index + 1, character, source_kind, points)
        )
        page.lines[row_index] += character
        x_cursor += width_mm + WORD_GAP_MM

    if "".join(page.lines) != text.replace("\n", ""):
        raise AssertionError("repositioned A4 wrapping changed source text")
    if len(page.lines) != 11:
        raise AssertionError(f"expected 11 full-page lines, got {len(page.lines)}")
    return page


def preview_xy(x_mm: float, y_mm: float) -> tuple[int, int]:
    return (
        round(x_mm * PIXELS_PER_MM),
        round((base.A4_HEIGHT_MM - y_mm) * PIXELS_PER_MM),
    )


def write_preview(page: base.PageLayout) -> None:
    width = round(base.A4_WIDTH_MM * PIXELS_PER_MM) + 1
    height = round(base.A4_HEIGHT_MM * PIXELS_PER_MM) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    label_font = base.load_label_font(22)
    small_font = base.load_label_font(16)
    draw.rectangle((0, 0, width - 1, height - 1), outline=(25, 25, 25), width=3)

    margin_top_left = preview_xy(PAPER_X0_MM, PAPER_Y1_MM)
    margin_bottom_right = preview_xy(PAPER_X1_MM, PAPER_Y0_MM)
    base.draw_dashed_rectangle(
        draw,
        (
            margin_top_left[0],
            margin_top_left[1],
            margin_bottom_right[0],
            margin_bottom_right[1],
        ),
        (70, 125, 190),
        width=2,
    )

    for placement in page.placements:
        previous: tuple[int, int] | None = None
        for point in placement.points:
            current = preview_xy(point.x_mm, point.y_mm)
            if point.draw and previous is not None:
                draw.line((previous, current), fill=(12, 12, 12), width=2)
            previous = current

    cross = preview_xy(ALIGN_PAPER_X_MM, ALIGN_PAPER_Y_MM)
    arm = round(3.0 * PIXELS_PER_MM)
    draw.line((cross[0] - arm, cross[1], cross[0] + arm, cross[1]), fill=(205, 40, 40), width=3)
    draw.line((cross[0], cross[1] - arm, cross[0], cross[1] + arm), fill=(205, 40, 40), width=3)

    draw.text((20, 8), "重新摆纸整页预览／不可直接运行", fill=(185, 35, 35), font=label_font)
    draw.text(
        (20, 36),
        "四周15 mm；全文一页11行；红十字(11,88)位于左页边距",
        fill=(65, 65, 65),
        font=small_font,
    )
    draw.text(
        (20, height - 32),
        "命令=纸面+(139,-68)；M801仍到(150,20)；需先确认摆放空间并做全域标定",
        fill=(70, 70, 70),
        font=small_font,
    )
    image.save(PREVIEW_PATH)


def write_reports(text: str, font: base.GFont, missing: str, page: base.PageLayout) -> None:
    points = base.flattened_points(page)
    command_points = [paper_to_command(point.x_mm, point.y_mm) for point in points]
    maximum_glyph_height = max(
        max(point.y_mm for point in placement.points)
        - min(point.y_mm for point in placement.points)
        for placement in page.placements
    )
    report = {
        "artifact": "DIARY_NOTEBOOK_REPOSITIONED_A4_ONE_PAGE_20260721",
        "runnable_on_robot": False,
        "source_docx_sha256": base.digest(base.SOURCE_DOCX),
        "source_text_sha256": base.digest(base.SOURCE_TEXT),
        "font_name": font.name,
        "font_sha256": base.digest(base.FONT_PATH),
        "missing_characters_replaced_by_disclosed_composites": missing,
        "unresolved_characters": "",
        "paper": {
            "orientation": "A4 landscape",
            "size_mm": [base.A4_WIDTH_MM, base.A4_HEIGHT_MM],
            "origin": "lower-left",
            "usable_rectangle_mm": [PAPER_X0_MM, PAPER_Y0_MM, PAPER_X1_MM, PAPER_Y1_MM],
            "kenjoy_origin": "right-upper",
        },
        "alignment": {
            "existing_m801_machine_target_mm": [ALIGN_COMMAND_X_MM, ALIGN_COMMAND_Y_MM],
            "new_cross_on_paper_mm": [ALIGN_PAPER_X_MM, ALIGN_PAPER_Y_MM],
            "command_from_paper": "command_xy = paper_xy + (139,-68)",
            "command_shift_mm": [COMMAND_SHIFT_X_MM, COMMAND_SHIFT_Y_MM],
            "machine_origin_direction_changed": False,
            "motor_direction_changed": False,
        },
        "layout": {
            "page_count": 1,
            "line_count": len(page.lines),
            "line_pitch_mm": LINE_PITCH_MM,
            "font_size_percent": FONT_SIZE_PERCENT,
            "maximum_actual_glyph_height_mm": round(maximum_glyph_height, 6),
            "lines": page.lines,
            "local_y_correction_applied": False,
            "local_y_correction_reason": "validated only near old machine y=65; not extrapolated",
        },
        "path": {
            "glyph_count": len(page.placements),
            "stroke_count": sum(
                sum(not point.draw for point in placement.points)
                for placement in page.placements
            ),
            "point_count_before_penup_routing": len(points),
            "paper_bounds_mm": [
                round(min(point.x_mm for point in points), 6),
                round(min(point.y_mm for point in points), 6),
                round(max(point.x_mm for point in points), 6),
                round(max(point.y_mm for point in points), 6),
            ],
            "command_bounds_mm": [
                round(min(point[0] for point in command_points), 6),
                round(min(point[1] for point in command_points), 6),
                round(max(point[0] for point in command_points), 6),
                round(max(point[1] for point in command_points), 6),
            ],
        },
        "blocking_reasons": [
            "user must confirm the repositioned A4 sheet physically fits without collision",
            "the translated full-sheet region has not been physically calibrated",
            "current V36 rejects ordinary G-code",
        ],
        "preview": str(PREVIEW_PATH),
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    lines = [
        "DIARY NOTEBOOK REPOSITIONED A4 ONE-PAGE LAYOUT — NOT FOR ROBOT",
        "全文一页整页预览；当前V36不能运行；必须先确认纸张摆放和做全域标定。",
        "A4横向，纸面四周15 mm，右上起点。",
        "现有M801机器目标=(150,20)；纸上新十字=(11,88)，位于左侧页边距。",
        "命令坐标=纸面坐标+(139,-68)；电机方向、机械原点均未改变。",
        f"行距={LINE_PITCH_MM:.1f} mm；行数={len(page.lines)}；局部Y×1.095未外推。",
        "",
    ]
    lines.extend(f"{index + 1:02d}: {line}" for index, line in enumerate(page.lines))
    LAYOUT_TEXT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def generate() -> tuple[str, base.GFont, str, base.PageLayout]:
    text = base.SOURCE_TEXT.read_text(encoding="utf-8").rstrip("\r\n")
    font = base.load_gfont(base.FONT_PATH)
    glyphs, missing = base.glyph_map(font, text)
    page = layout_text(text, font, glyphs)
    return text, font, missing, page


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    text, font, missing, page = generate()
    points = base.flattened_points(page)
    maximum_glyph_height = max(
        max(point.y_mm for point in placement.points)
        - min(point.y_mm for point in placement.points)
        for placement in page.placements
    )
    print(
        f"repositioned_layout=PASS pages=1 lines={len(page.lines)} "
        f"glyphs={len(page.placements)} points={len(points)} "
        f"max_glyph_height_mm={maximum_glyph_height:.6f} missing={missing} "
        f"align_paper=({ALIGN_PAPER_X_MM:.1f},{ALIGN_PAPER_Y_MM:.1f}) "
        f"command_shift=({COMMAND_SHIFT_X_MM:.1f},{COMMAND_SHIFT_Y_MM:.1f}) "
        "unresolved=0 runnable=0"
    )
    for index, line in enumerate(page.lines, start=1):
        print(f"line={index:02d} text={line}")
    if args.write:
        write_preview(page)
        write_reports(text, font, missing, page)
        print(f"preview={PREVIEW_PATH}")
        print(f"report={REPORT_PATH}")
        print(f"layout_text={LAYOUT_TEXT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
