#!/usr/bin/env python3
"""Generate page 1 of a DOCX diary as large B-font standard G-code."""

from __future__ import annotations

import hashlib
import json
import math
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

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
)
from kenjoy_gfont import load_gfont, missing_characters


TEST_ID = "PAPER_A4_DIARY_DOCX_BFONT_12MM_PAGE1_GCODE_V73"
FIRMWARE_ID = "PAPER_A4_STANDARD_GCODE_JUNCTION_PLANNER_V32"
DOCX_PATH = Path(r"C:\Users\zjl\Desktop\日记本.docx")
DOCX_SHA256 = (
    "EA36C6DEEF17968A1B18B49750D2A6B5F7CE5ECDD03572A4995E01151EBFAAE9"
)
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"
GUIDE_PATH = ROOT / "gcode" / f"{TEST_ID}_GUIDE.md"

VISIBLE_HEIGHT_MM = 12.0
CHARACTER_GAP_MM = 1.4
SPACE_ADVANCE_MM = 4.8
CONTENT_LEFT_MM = 30.0
CONTENT_RIGHT_MM = 180.0
ROW_TOPS_MM = (230.0, 213.0, 196.0, 179.0, 162.0, 145.0)
TANGENT_APPROACH_MM = 5.0
FEED_MM_MIN = 300
PAPER_X_RANGE_MM = (25.0, 185.0)
PAPER_Y_RANGE_MM = (75.0, 235.0)
PREVIEW_PIXELS_PER_MM = 4.0
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


@dataclass(frozen=True)
class PlacedCharacter:
    character: str
    paragraph_index: int
    source_character_index: int
    row_index: int
    left_mm: float
    width_mm: float


def read_docx_paragraphs() -> tuple[str, ...]:
    actual_hash = hashlib.sha256(DOCX_PATH.read_bytes()).hexdigest().upper()
    if actual_hash != DOCX_SHA256:
        raise AssertionError("日记本.docx changed after it was inspected")
    with zipfile.ZipFile(DOCX_PATH) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    namespace = {"w": WORD_NS}
    paragraphs = []
    for paragraph in root.findall(".//w:body/w:p", namespace):
        parts: list[str] = []
        for node in paragraph.iter():
            if node.tag == f"{{{WORD_NS}}}t":
                parts.append(node.text or "")
            elif node.tag == f"{{{WORD_NS}}}tab":
                parts.append("\t")
            elif node.tag in (
                f"{{{WORD_NS}}}br",
                f"{{{WORD_NS}}}cr",
            ):
                parts.append("\n")
        paragraphs.append("".join(parts))
    if not paragraphs:
        raise AssertionError("DOCX contains no body paragraphs")
    return tuple(paragraphs)


def split_nonempty_strokes(
    character: str,
    points: tuple[tuple[float, float], ...],
    commands: tuple[int, ...],
) -> tuple[tuple[tuple[float, float], ...], ...]:
    """Split original paths while ignoring source zero-length no-op strokes."""
    result: list[list[tuple[float, float]]] = []
    for point, command in zip(points, commands):
        if command == 0:
            result.append([point])
        elif not result:
            raise AssertionError(f"{character!r} begins with a draw command")
        elif math.dist(result[-1][-1], point) > 1.0e-9:
            result[-1].append(point)
    visible = tuple(tuple(stroke) for stroke in result if len(stroke) >= 2)
    if not visible:
        raise AssertionError(f"{character!r} contains no visible stroke")
    return visible


def glyph_metrics(font, paragraphs: tuple[str, ...]):
    supported_characters = tuple(
        character
        for paragraph in paragraphs
        for character in paragraph
        if not character.isspace() and character in font.glyphs
    )
    if not supported_characters:
        raise AssertionError("DOCX contains no supported B-font characters")
    glyphs = [font.glyphs[character] for character in supported_characters]
    global_y_min = min(glyph.bounds[1] for glyph in glyphs)
    global_y_max = max(glyph.bounds[3] for glyph in glyphs)
    scale = VISIBLE_HEIGHT_MM / (global_y_max - global_y_min)
    return global_y_min, global_y_max, scale


def place_page(
    font,
    paragraphs: tuple[str, ...],
    scale: float,
) -> tuple[
    tuple[PlacedCharacter, ...],
    tuple[str, ...],
    dict[str, object],
]:
    placements: list[PlacedCharacter] = []
    row_texts = ["" for _ in ROW_TOPS_MM]
    row_index = 0
    cursor_x = CONTENT_LEFT_MM
    consumed_non_newline = 0
    stop_reason = "page_capacity"
    stop_character = ""
    source_flat_index = 0
    stopped = False

    for paragraph_index, paragraph in enumerate(paragraphs):
        if paragraph_index > 0:
            row_index += 1
            cursor_x = CONTENT_LEFT_MM
            if row_index >= len(ROW_TOPS_MM):
                stopped = True
                break
        for character_index, character in enumerate(paragraph):
            if character in ("\n", "\r"):
                row_index += 1
                cursor_x = CONTENT_LEFT_MM
                source_flat_index += 1
                if row_index >= len(ROW_TOPS_MM):
                    stopped = True
                    break
                continue
            if character.isspace():
                advance = (
                    SPACE_ADVANCE_MM
                    if character != "\t"
                    else SPACE_ADVANCE_MM * 2.0
                )
                if cursor_x + advance > CONTENT_RIGHT_MM:
                    row_index += 1
                    cursor_x = CONTENT_LEFT_MM
                    if row_index >= len(ROW_TOPS_MM):
                        stopped = True
                        break
                cursor_x += advance
                row_texts[row_index] += character
                consumed_non_newline += 1
                source_flat_index += 1
                continue
            if character not in font.glyphs:
                stop_reason = "unsupported_glyph"
                stop_character = character
                stopped = True
                break

            glyph = font.glyphs[character]
            width = (glyph.bounds[2] - glyph.bounds[0]) * scale
            if (
                cursor_x > CONTENT_LEFT_MM
                and cursor_x + width > CONTENT_RIGHT_MM
            ):
                row_index += 1
                cursor_x = CONTENT_LEFT_MM
                if row_index >= len(ROW_TOPS_MM):
                    stopped = True
                    break

            placements.append(
                PlacedCharacter(
                    character,
                    paragraph_index,
                    character_index,
                    row_index,
                    cursor_x,
                    width,
                )
            )
            row_texts[row_index] += character
            cursor_x += width + CHARACTER_GAP_MM
            consumed_non_newline += 1
            source_flat_index += 1
        if stopped:
            break

    if not stopped:
        stop_reason = "document_complete"
    return (
        tuple(placements),
        tuple(row_texts),
        {
            "stop_reason": stop_reason,
            "stop_character": stop_character,
            "consumed_character_count": consumed_non_newline,
            "source_flat_index": source_flat_index,
            "used_row_count": 1 + max(
                placement.row_index for placement in placements
            ),
        },
    )


def build_layout() -> tuple[
    Layout,
    tuple[str, ...],
    tuple[str, ...],
    dict[str, object],
]:
    paragraphs = read_docx_paragraphs()
    actual_font_hash = hashlib.sha256(
        source.FONT_PATH.read_bytes()
    ).hexdigest().upper()
    if actual_font_hash != source.FONT_SHA256:
        raise AssertionError("pinned B gfont hash changed")
    font = load_gfont(source.FONT_PATH)
    if font.name != source.FONT_NAME or font.em_size != source.FONT_EM_SIZE:
        raise AssertionError("unexpected B gfont metadata")

    global_y_min, _, scale = glyph_metrics(font, paragraphs)
    placements, row_texts, pagination = place_page(
        font, paragraphs, scale
    )
    if not placements:
        raise AssertionError("page 1 contains no printable characters")

    characters: list[CharacterLayout] = []
    strokes: list[Stroke] = []
    for visible_index, placement in enumerate(placements):
        glyph = font.glyphs[placement.character]
        source_x_min, source_y_min, source_x_max, source_y_max = (
            glyph.bounds
        )
        row_top = ROW_TOPS_MM[placement.row_index]
        points = tuple(
            (
                placement.left_mm + (source_x - source_x_min) * scale,
                row_top - (source_y - global_y_min) * scale,
            )
            for source_x, source_y in glyph.points
        )
        character_strokes = split_nonempty_strokes(
            placement.character, points, glyph.commands
        )
        for stroke_index, stroke_points in enumerate(
            character_strokes, start=1
        ):
            first_length = math.dist(stroke_points[0], stroke_points[1])
            if first_length <= 1.0e-9:
                raise AssertionError("zero initial stroke direction")
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
                    placement.character,
                    visible_index,
                    stroke_index,
                    approach,
                    stroke_points,
                )
            )
        characters.append(
            CharacterLayout(
                placement.character,
                (
                    placement.left_mm,
                    row_top - (source_y_max - global_y_min) * scale,
                    placement.left_mm + placement.width_mm,
                    row_top - (source_y_min - global_y_min) * scale,
                ),
                len(character_strokes),
            )
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
            PAPER_X_RANGE_MM[0]
            <= point[0]
            <= PAPER_X_RANGE_MM[1]
            and PAPER_Y_RANGE_MM[0]
            <= point[1]
            <= PAPER_Y_RANGE_MM[1]
        ):
            raise AssertionError(f"V73 point out of bounds: {point}")
    return (
        Layout(
            font,
            scale,
            tuple(characters),
            tuple(strokes),
            bounds,
        ),
        paragraphs,
        row_texts,
        pagination,
    )


def gcode_lines(layout: Layout) -> tuple[str, ...]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware_required={FIRMWARE_ID}",
        "; coordinates=STANDARD_A4_PHYSICAL_PAPER_MM",
        "; offline_mapping=NONE offline_prewarp=NONE",
        f"; source_docx_sha256={DOCX_SHA256}",
        f"; source_font={source.FONT_PATH.name} sha256={source.FONT_SHA256}",
        "; font_option=B source_geometry=UNMODIFIED_GFONT",
        "; page=1 visible_height=12mm tangent_approach=5mm",
        "; paragraph_breaks_preserved=YES automatic_line_wrap=YES",
        "G21",
        "G90",
        "G94",
        f"F{FEED_MM_MIN}",
        "S1000",
        "M5",
    ]
    active_row = -1
    for character, stroke in zip(
        (
            character
            for character in layout.characters
            for _ in range(character.stroke_count)
        ),
        layout.strokes,
    ):
        row_index = min(
            range(len(ROW_TOPS_MM)),
            key=lambda index: abs(
                character.bounds_mm[3] - ROW_TOPS_MM[index]
            ),
        )
        if row_index != active_row:
            if active_row >= 0:
                lines.append(f"; END_ROW_{active_row + 1}")
            active_row = row_index
            lines.append(f"; BEGIN_ROW_{active_row + 1}")
        lines.extend(
            (
                (
                    f"; char={stroke.character_index + 1} "
                    f"stroke={stroke.stroke_index}"
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
    lines.extend((f"; END_ROW_{active_row + 1}", "M5"))
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
        raise AssertionError(f"V73 path violates joint limits: {worst}")
    if any(len(line) >= 192 for line in lines):
        raise AssertionError("V73 contains an overlong serial line")
    if lines.count("M3") != len(layout.strokes):
        raise AssertionError("V73 pen-down count mismatch")
    return {
        "safe_samples": safe_samples,
        "min_joint_margin_deg": worst[0],
        "min_margin_user_mm": list(worst[1]),
        "stroke_count": len(layout.strokes),
        "motion_line_count": sum(
            line.startswith(("G0 ", "G1 ")) for line in lines
        ),
    }


def write_preview(layout: Layout, row_texts: tuple[str, ...]) -> None:
    width = round(A4_WIDTH_MM * PREVIEW_PIXELS_PER_MM) + 1
    height = round(A4_HEIGHT_MM * PREVIEW_PIXELS_PER_MM) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (0, 0, width - 1, height - 1),
        outline=(30, 30, 30),
        width=3,
    )
    for row_top in ROW_TOPS_MM:
        y = round((A4_HEIGHT_MM - row_top) * PREVIEW_PIXELS_PER_MM)
        draw.line(
            (
                round(CONTENT_LEFT_MM * PREVIEW_PIXELS_PER_MM),
                y,
                round(CONTENT_RIGHT_MM * PREVIEW_PIXELS_PER_MM),
                y,
            ),
            fill=(225, 235, 245),
            width=1,
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
        "V73 / diary DOCX page 1 / B font / 12 mm / 5 mm approach",
        fill=(25, 25, 25),
        font=label_font(16),
    )
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def write_guide(
    paragraphs: tuple[str, ...],
    row_texts: tuple[str, ...],
    pagination: dict[str, object],
) -> None:
    rendered_rows = "\n".join(
        f"{index + 1}. {text}" for index, text in enumerate(row_texts) if text
    )
    missing = missing_characters(
        load_gfont(source.FONT_PATH), "".join(paragraphs)
    )
    stop_character = pagination["stop_character"] or "无"
    GUIDE_PATH.write_text(
        f"""# V73《日记本》第一页 12 mm 大字测试

- 所需固件：`{FIRMWARE_ID}`
- 来源：`{DOCX_PATH}`
- 来源 SHA-256：`{DOCX_SHA256}`
- 字体：B 类原始 gfont
- 可见字高：{VISIBLE_HEIGHT_MM:.0f} mm
- 落笔前切向预走：{TANGENT_APPROACH_MM:.0f} mm
- 速度：F{FEED_MM_MIN}
- 标准 G-code，无离线坐标补偿
- 保留 DOCX 段落换行，并按 150 mm 可写宽度自动换行

## 本页实际排版

{rendered_rows}

## 分页状态

- 停止原因：`{pagination["stop_reason"]}`
- 停止字符：`{stop_character}`
- 本页已读取字符数：{pagination["consumed_character_count"]}
- B 类字库对全文缺字：`{missing}`

如果停止原因为 `unsupported_glyph`，程序没有猜字、造字或用相似字替换；需要先确定缺字字库方案再生成下一页。
""",
        encoding="utf-8",
    )


def main() -> None:
    layout, paragraphs, row_texts, pagination = build_layout()
    lines = gcode_lines(layout)
    text = "\n".join(lines) + "\n"
    safety = audit(layout, lines)
    GCODE_PATH.parent.mkdir(parents=True, exist_ok=True)
    GCODE_PATH.write_text(text, encoding="ascii", newline="\n")
    manifest = {
        "id": TEST_ID,
        "required_firmware": FIRMWARE_ID,
        "source_docx": {
            "path": str(DOCX_PATH),
            "sha256": DOCX_SHA256,
            "paragraph_count": len(paragraphs),
            "paragraphs": list(paragraphs),
        },
        "font": {
            "option": "B",
            "name": source.FONT_NAME,
            "file": source.FONT_PATH.name,
            "sha256": source.FONT_SHA256,
            "geometry": "unmodified gfont paths",
            "zero_length_source_strokes": "ignored as non-visible no-ops",
            "full_document_missing_characters": missing_characters(
                layout.font, "".join(paragraphs)
            ),
        },
        "layout": {
            "page": 1,
            "visible_height_mm": VISIBLE_HEIGHT_MM,
            "character_gap_mm": CHARACTER_GAP_MM,
            "space_advance_mm": SPACE_ADVANCE_MM,
            "content_x_mm": [CONTENT_LEFT_MM, CONTENT_RIGHT_MM],
            "row_tops_mm": list(ROW_TOPS_MM),
            "rendered_rows": list(row_texts),
            "bounds_mm": list(layout.bounds_mm),
            "pagination": pagination,
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
    write_preview(layout, row_texts)
    write_guide(paragraphs, row_texts, pagination)
    print(
        "diary_docx_bfont_12mm_page1_v73=PASS "
        f"bounds={layout.bounds_mm} "
        f"rows={pagination['used_row_count']} "
        f"chars={pagination['consumed_character_count']} "
        f"stop={pagination['stop_reason']}:"
        f"{pagination['stop_character']!r} "
        f"strokes={safety['stroke_count']} "
        f"min_joint_margin={safety['min_joint_margin_deg']:.6f}deg"
    )
    print("rendered_rows=" + json.dumps(row_texts, ensure_ascii=False))
    print(f"gcode_sha256={manifest['gcode']['sha256']}")
    print(GCODE_PATH)
    print(MANIFEST_PATH)
    print(PREVIEW_PATH)
    print(GUIDE_PATH)


if __name__ == "__main__":
    main()
