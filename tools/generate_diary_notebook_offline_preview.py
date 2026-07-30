#!/usr/bin/env python3
"""Generate a non-runnable, safety-bounded preview for ``日记本.docx``.

This reproduces Kenjoy Note-mode's glyph scale, baseline, width-based wrapping,
and spacing with the locally selected Song single-line ``.gfont``.  It then
places the text in the conservative V36 rectangle on landscape A4 sheets.

The output is deliberately JSON/PNG/TXT rather than ``.gcode``.  It is an
offline layout proof only; current V36 rejects ordinary G-code and the full
rectangle has not been physically calibrated for continuous handwriting.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from kenjoy_gfont import GFont, Glyph, load_gfont, missing_characters


ROOT = Path(__file__).resolve().parents[1]
SOURCE_TEXT = ROOT / "gcode" / "DIARY_NOTEBOOK_SOURCE_20260721.txt"
FONT_PATH = Path(
    r"C:\Users\zjl\Downloads\25.11.11drawbot完整资料包"
    r"\生成gcode\奎享雕刻软件（绿色版）（生成gcode）"
    r"\奎享雕刻软件（绿色版）\gcodeFonts"
    r"\ec900461-6461-471a-9236-3309b1bd18b8_download.gfont"
)
SOURCE_DOCX = Path(r"C:\Users\zjl\Desktop\日记本.docx")

REPORT_PATH = ROOT / "gcode" / "DIARY_NOTEBOOK_OFFLINE_LAYOUT_20260721.json"
LAYOUT_TEXT_PATH = (
    ROOT / "gcode" / "DIARY_NOTEBOOK_OFFLINE_LAYOUT_NOT_FOR_ROBOT_20260721.txt"
)
PREVIEW_DIR = ROOT / "docs" / "diagnostics"
PREVIEW_STEM = "DIARY_NOTEBOOK_OFFLINE_PREVIEW_20260721"

A4_WIDTH_MM = 297.0
A4_HEIGHT_MM = 210.0

# This is the existing V36 offline-safe rectangle, not a claim that all points
# have been validated by full-area handwriting on the physical machine.
SAFE_X0_MM = 150.0
SAFE_X1_MM = 275.0
SAFE_Y0_MM = 15.0
SAFE_Y1_MM = 125.0

LINE_PITCH_MM = 15.0
FONT_SIZE_PERCENT = 95.0
WORD_GAP_MM = 0.6
PREVIEW_PIXELS_PER_MM = 4.0

COMPOSITE_COMPONENTS = {
    "粿": (("米", (-200.0, -390.0, -20.0, 30.0)), ("果", (-5.0, -390.0, 250.0, 30.0))),
    # The Song gfont also lacks the standalone right component 粦.  Rebuild it
    # visibly as 米 above an approximate 舛 made from 夕 and 牛.
    "麟": (
        ("鹿", (-200.0, -390.0, -10.0, 30.0)),
        ("米", (5.0, -390.0, 250.0, -165.0)),
        ("夕", (5.0, -150.0, 135.0, 30.0)),
        ("牛", (120.0, -150.0, 250.0, 30.0)),
    ),
    "婷": (("女", (-200.0, -390.0, -35.0, 30.0)), ("亭", (-20.0, -390.0, 250.0, 30.0))),
    "鹏": (("朋", (-200.0, -390.0, 15.0, 30.0)), ("鸟", (30.0, -390.0, 250.0, 30.0))),
}


@dataclass(frozen=True)
class PathPoint:
    x_mm: float
    y_mm: float
    draw: bool


@dataclass(frozen=True)
class Placement:
    page: int
    line: int
    character: str
    source_kind: str
    points: tuple[PathPoint, ...]


@dataclass
class PageLayout:
    number: int
    lines: list[str]
    placements: list[Placement]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def transform_component(
    component: Glyph,
    box: tuple[float, float, float, float],
) -> tuple[tuple[float, float], ...]:
    source_x0, source_y0, source_x1, source_y1 = component.bounds
    target_x0, target_y0, target_x1, target_y1 = box
    if source_x1 <= source_x0 or source_y1 <= source_y0:
        raise AssertionError(f"component {component.character!r} has empty bounds")
    scale_x = (target_x1 - target_x0) / (source_x1 - source_x0)
    scale_y = (target_y1 - target_y0) / (source_y1 - source_y0)
    return tuple(
        (
            target_x0 + (x_value - source_x0) * scale_x,
            target_y0 + (y_value - source_y0) * scale_y,
        )
        for x_value, y_value in component.points
    )


def composite_glyph(font: GFont, character: str) -> Glyph:
    pieces = COMPOSITE_COMPONENTS[character]
    points: list[tuple[float, float]] = []
    commands: list[int] = []
    for component_character, box in pieces:
        component = font.glyphs.get(component_character)
        if component is None:
            raise AssertionError(
                f"component {component_character!r} for {character!r} is missing"
            )
        points.extend(transform_component(component, box))
        commands.extend(component.commands)
    return Glyph(character, tuple(points), tuple(commands))


def glyph_map(font: GFont, text: str) -> tuple[dict[str, Glyph], str]:
    missing = missing_characters(font, text)
    unsupported = "".join(
        character for character in missing if character not in COMPOSITE_COMPONENTS
    )
    if unsupported:
        raise AssertionError(f"unresolved font characters: {unsupported}")
    result = dict(font.glyphs)
    for character in missing:
        result[character] = composite_glyph(font, character)
    return result, missing


def new_page(pages: list[PageLayout]) -> PageLayout:
    page = PageLayout(len(pages) + 1, [""], [])
    pages.append(page)
    return page


def layout_text(
    text: str,
    font: GFont,
    glyphs: dict[str, Glyph],
) -> list[PageLayout]:
    scale = LINE_PITCH_MM / float(font.em_size) * (FONT_SIZE_PERCENT / 100.0)
    safe_height = SAFE_Y1_MM - SAFE_Y0_MM
    pages: list[PageLayout] = []
    page = new_page(pages)
    line_index = 0
    line_top_mm = 0.0
    x_cursor_mm = SAFE_X0_MM

    def next_line() -> None:
        nonlocal page, line_index, line_top_mm, x_cursor_mm
        line_index += 1
        line_top_mm = line_index * LINE_PITCH_MM
        x_cursor_mm = SAFE_X0_MM
        if line_top_mm >= safe_height - LINE_PITCH_MM + 1.0e-9:
            page = new_page(pages)
            line_index = 0
            line_top_mm = 0.0
        elif len(page.lines) <= line_index:
            page.lines.append("")

    for character in text:
        if character in "\r\n":
            if character == "\n":
                next_line()
            continue
        if character.isspace():
            advance = LINE_PITCH_MM * (FONT_SIZE_PERCENT / 100.0) * 0.5
            if x_cursor_mm + advance > SAFE_X1_MM:
                next_line()
            x_cursor_mm += advance
            page.lines[line_index] += character
            continue

        glyph = glyphs[character]
        bounds_x0, _, bounds_x1, _ = glyph.bounds
        scaled_x0 = bounds_x0 * scale
        width_mm = (bounds_x1 - bounds_x0) * scale
        x_correction_mm = -scaled_x0 if scaled_x0 < 0.0 else 0.0
        if x_cursor_mm + width_mm > SAFE_X1_MM + 1.0e-9:
            next_line()

        translate_x_mm = x_cursor_mm + x_correction_mm
        baseline_down_mm = line_top_mm + LINE_PITCH_MM * 0.75
        points = tuple(
            PathPoint(
                translate_x_mm + x_value * scale,
                SAFE_Y1_MM - (baseline_down_mm + y_value * scale),
                command == 1,
            )
            for (x_value, y_value), command in zip(glyph.points, glyph.commands)
        )
        if not points or points[0].draw:
            raise AssertionError(f"glyph {character!r} does not begin with a move")
        for point in points:
            if not (
                SAFE_X0_MM - 1.0e-6 <= point.x_mm <= SAFE_X1_MM + 1.0e-6
                and SAFE_Y0_MM - 1.0e-6 <= point.y_mm <= SAFE_Y1_MM + 1.0e-6
            ):
                raise AssertionError(
                    f"{character!r} point left safe rectangle: "
                    f"({point.x_mm:.3f},{point.y_mm:.3f})"
                )
        source_kind = "composite" if character in COMPOSITE_COMPONENTS else "gfont"
        page.placements.append(
            Placement(page.number, line_index + 1, character, source_kind, points)
        )
        page.lines[line_index] += character
        x_cursor_mm += width_mm + WORD_GAP_MM

    while pages and not pages[-1].placements:
        pages.pop()
    return pages


def preview_xy(x_mm: float, y_mm: float) -> tuple[int, int]:
    return (
        round(x_mm * PREVIEW_PIXELS_PER_MM),
        round((A4_HEIGHT_MM - y_mm) * PREVIEW_PIXELS_PER_MM),
    )


def load_label_font(size: int) -> ImageFont.ImageFont:
    candidates = (
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
    )
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def draw_dashed_rectangle(
    draw: ImageDraw.ImageDraw,
    bounds: tuple[int, int, int, int],
    fill: tuple[int, int, int],
    width: int = 2,
    dash: int = 14,
) -> None:
    x0, y0, x1, y1 = bounds
    for start in range(x0, x1, dash * 2):
        draw.line((start, y0, min(start + dash, x1), y0), fill=fill, width=width)
        draw.line((start, y1, min(start + dash, x1), y1), fill=fill, width=width)
    for start in range(y0, y1, dash * 2):
        draw.line((x0, start, x0, min(start + dash, y1)), fill=fill, width=width)
        draw.line((x1, start, x1, min(start + dash, y1)), fill=fill, width=width)


def write_page_previews(pages: list[PageLayout]) -> list[Path]:
    width = round(A4_WIDTH_MM * PREVIEW_PIXELS_PER_MM) + 1
    height = round(A4_HEIGHT_MM * PREVIEW_PIXELS_PER_MM) + 1
    label_font = load_label_font(22)
    small_font = load_label_font(16)
    output_paths: list[Path] = []
    rendered_pages: list[Image.Image] = []

    safe_top_left = preview_xy(SAFE_X0_MM, SAFE_Y1_MM)
    safe_bottom_right = preview_xy(SAFE_X1_MM, SAFE_Y0_MM)
    safe_bounds = (
        safe_top_left[0],
        safe_top_left[1],
        safe_bottom_right[0],
        safe_bottom_right[1],
    )

    for page in pages:
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, width - 1, height - 1), outline=(25, 25, 25), width=3)
        draw_dashed_rectangle(draw, safe_bounds, (60, 115, 185), width=2)
        draw.text((20, 16), "离线预览／不可直接运行", fill=(185, 40, 40), font=label_font)
        draw.text(
            (20, 48),
            f"第 {page.number}/{len(pages)} 页  A4横向  安全框150..275 × 15..125 mm",
            fill=(75, 75, 75),
            font=small_font,
        )
        draw.text(
            (20, height - 32),
            "右上起点已记录；图中黑线仅为单线路径，蓝框不是实机全域验证结论",
            fill=(75, 75, 75),
            font=small_font,
        )

        for placement in page.placements:
            previous: tuple[int, int] | None = None
            for point in placement.points:
                current = preview_xy(point.x_mm, point.y_mm)
                if point.draw and previous is not None:
                    draw.line((previous, current), fill=(15, 15, 15), width=2)
                previous = current

        output = PREVIEW_DIR / f"{PREVIEW_STEM}_PAGE_{page.number:02d}.png"
        image.save(output)
        output_paths.append(output)
        rendered_pages.append(image)

    contact_width = max(image.width for image in rendered_pages)
    contact_height = sum(image.height for image in rendered_pages)
    contact = Image.new("RGB", (contact_width, contact_height), (230, 230, 230))
    y_offset = 0
    for image in rendered_pages:
        contact.paste(image, (0, y_offset))
        y_offset += image.height
    contact_path = PREVIEW_DIR / f"{PREVIEW_STEM}_CONTACT_SHEET.png"
    contact.save(contact_path)
    output_paths.append(contact_path)

    composite_path = write_composite_preview(pages)
    output_paths.append(composite_path)
    return output_paths


def write_composite_preview(pages: list[PageLayout]) -> Path:
    first_placements: dict[str, Placement] = {}
    for page in pages:
        for placement in page.placements:
            if placement.source_kind == "composite":
                first_placements.setdefault(placement.character, placement)
    expected = tuple(COMPOSITE_COMPONENTS)
    if tuple(character for character in expected if character in first_placements) != expected:
        raise AssertionError("not every composite fallback appears in the diary")

    image = Image.new("RGB", (1000, 680), "white")
    draw = ImageDraw.Draw(image)
    title_font = load_label_font(30)
    label_font = load_label_font(24)
    note_font = load_label_font(18)
    draw.text((30, 20), "组合补字单线路径放大检查（仍不可上机）", fill=(180, 35, 35), font=title_font)

    component_labels = {
        "粿": "米 + 果",
        "麟": "鹿 + 米 + 夕 + 牛（近似粦）",
        "婷": "女 + 亭",
        "鹏": "朋 + 鸟",
    }
    cell_width = 470
    cell_height = 280
    for index, character in enumerate(expected):
        column = index % 2
        row = index // 2
        cell_x = 30 + column * cell_width
        cell_y = 90 + row * cell_height
        draw.rounded_rectangle(
            (cell_x, cell_y, cell_x + 440, cell_y + 250),
            radius=14,
            outline=(170, 185, 205),
            width=2,
        )
        draw.text(
            (cell_x + 18, cell_y + 12),
            f"{character}  =  {component_labels[character]}",
            fill=(45, 45, 45),
            font=label_font,
        )
        placement = first_placements[character]
        xs = [point.x_mm for point in placement.points]
        ys = [point.y_mm for point in placement.points]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        available_width = 360.0
        available_height = 165.0
        scale = min(available_width / (x1 - x0), available_height / (y1 - y0))
        origin_x = cell_x + 40 + (available_width - (x1 - x0) * scale) / 2.0
        origin_y = cell_y + 68 + (available_height - (y1 - y0) * scale) / 2.0
        previous: tuple[float, float] | None = None
        for point in placement.points:
            current = (
                origin_x + (point.x_mm - x0) * scale,
                origin_y + (y1 - point.y_mm) * scale,
            )
            if point.draw and previous is not None:
                draw.line((previous, current), fill=(10, 10, 10), width=4)
            previous = current
    draw.text(
        (30, 650),
        "用途：确认缺字没有被静默丢弃；最终实机前仍应先做单字门控试写。",
        fill=(80, 80, 80),
        font=note_font,
    )
    output = PREVIEW_DIR / f"{PREVIEW_STEM}_COMPOSITE_GLYPHS.png"
    image.save(output)
    return output


def flattened_points(page: PageLayout) -> list[PathPoint]:
    return [point for placement in page.placements for point in placement.points]


def page_record(page: PageLayout) -> dict[str, object]:
    points = flattened_points(page)
    return {
        "page": page.number,
        "lines": page.lines,
        "glyph_count": len(page.placements),
        "stroke_count": sum(
            sum(not point.draw for point in placement.points)
            for placement in page.placements
        ),
        "path_point_count": len(points),
        "path_bounds_mm": [
            round(min(point.x_mm for point in points), 6),
            round(min(point.y_mm for point in points), 6),
            round(max(point.x_mm for point in points), 6),
            round(max(point.y_mm for point in points), 6),
        ],
        "composite_characters": "".join(
            placement.character
            for placement in page.placements
            if placement.source_kind == "composite"
        ),
    }


def write_reports(
    text: str,
    font: GFont,
    missing: str,
    pages: list[PageLayout],
    preview_paths: list[Path],
) -> None:
    unique_nonspace = "".join(dict.fromkeys(c for c in text if not c.isspace()))
    report = {
        "artifact": "DIARY_NOTEBOOK_OFFLINE_LAYOUT_20260721",
        "runnable_on_robot": False,
        "blocking_reasons": [
            "V36 only accepts M801 ALIGN and M807 TEXT; ordinary G-code is disabled",
            "continuous handwriting over this rectangle has not been physically calibrated",
            "four glyphs use disclosed composite single-line fallbacks",
        ],
        "source": {
            "docx": str(SOURCE_DOCX),
            "docx_sha256": digest(SOURCE_DOCX),
            "fixed_text_file": str(SOURCE_TEXT),
            "fixed_text_sha256": digest(SOURCE_TEXT),
            "characters_including_newline": len(text),
            "characters_excluding_whitespace": sum(not c.isspace() for c in text),
            "unique_nonspace_characters": len(unique_nonspace),
        },
        "kenjoy": {
            "mode": "笔记",
            "selected_origin": "右上",
            "origin_id_from_decompiled_logic": 1,
            "origin_internal_offset": [0.0, 0.0],
            "font_file": str(FONT_PATH),
            "font_sha256": digest(FONT_PATH),
            "font_name": font.name,
            "font_em_size": font.em_size,
            "original_missing_characters": missing,
            "composite_fallbacks": {
                character: [piece[0] for piece in pieces]
                for character, pieces in COMPOSITE_COMPONENTS.items()
                if character in missing
            },
            "unresolved_characters": "",
        },
        "layout": {
            "paper": "A4 landscape",
            "paper_origin": "lower-left",
            "paper_size_mm": [A4_WIDTH_MM, A4_HEIGHT_MM],
            "safe_rectangle_mm": [SAFE_X0_MM, SAFE_Y0_MM, SAFE_X1_MM, SAFE_Y1_MM],
            "line_pitch_mm": LINE_PITCH_MM,
            "font_size_percent": FONT_SIZE_PERCENT,
            "word_gap_mm": WORD_GAP_MM,
            "page_count": len(pages),
            "local_y_correction_applied": False,
            "local_y_correction_reason": (
                "V34's 1.095 factor is validated only around y=65 and must not be "
                "extrapolated across multi-line pages"
            ),
        },
        "pages": [page_record(page) for page in pages],
        "preview_files": [str(path) for path in preview_paths],
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    lines = [
        "DIARY NOTEBOOK OFFLINE LAYOUT — NOT FOR ROBOT",
        "当前 V36 不能运行此文件；这只是逐字排版和字库覆盖预览。",
        f"纸张=A4横向  纸面坐标原点=左下  奎享起点=右上(id=1)",
        f"安全框=X{SAFE_X0_MM:.1f}..{SAFE_X1_MM:.1f} mm, "
        f"Y{SAFE_Y0_MM:.1f}..{SAFE_Y1_MM:.1f} mm",
        f"行距={LINE_PITCH_MM:.1f} mm  字号={FONT_SIZE_PERCENT:.1f}%  "
        f"页数={len(pages)}",
        f"宋体原缺字={missing}  组合补字=粿(米+果),麟(鹿+米+夕+牛),婷(女+亭),鹏(朋+鸟)",
        "局部Y×1.095=未应用（只在y=65附近验证，不能跨页外推）",
        "",
    ]
    for page in pages:
        lines.append(f"=== 第 {page.number}/{len(pages)} 页 ===")
        lines.extend(f"{index + 1:02d}: {line}" for index, line in enumerate(page.lines))
        lines.append("")
    LAYOUT_TEXT_PATH.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="write JSON/TXT/PNG offline preview artifacts",
    )
    args = parser.parse_args()

    text = SOURCE_TEXT.read_text(encoding="utf-8").rstrip("\r\n")
    font = load_gfont(FONT_PATH)
    glyphs, missing = glyph_map(font, text)
    pages = layout_text(text, font, glyphs)
    preview_paths: list[Path] = []
    if args.write:
        preview_paths = write_page_previews(pages)
        write_reports(text, font, missing, pages, preview_paths)

    print(
        f"layout=PASS pages={len(pages)} chars={sum(not c.isspace() for c in text)} "
        f"font={font.name} missing={missing} unresolved=0 runnable=0"
    )
    for page in pages:
        record = page_record(page)
        print(
            f"page={page.number} glyphs={record['glyph_count']} "
            f"strokes={record['stroke_count']} points={record['path_point_count']} "
            f"bounds_mm={record['path_bounds_mm']}"
        )
        for line_number, line in enumerate(page.lines, start=1):
            print(f"  line={line_number:02d} text={line}")
    if args.write:
        print(f"report={REPORT_PATH}")
        print(f"layout_text={LAYOUT_TEXT_PATH}")
        for path in preview_paths:
            print(f"preview={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
