#!/usr/bin/env python3
"""Generate a lower-page A/B/C test that separates font data from motion."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

import generate_paper_a4_zhang_jia_le_v31 as aa
import generate_paper_a4_zhang_jia_le_v32 as song


ROOT = Path(__file__).resolve().parents[1]
GCODE_PATH = (
    ROOT
    / "gcode"
    / "PAPER_A4_FONT_VS_PROGRAM_ISOLATION_Y65_TANGENT_GCODE_V34.gcode"
)
MANIFEST_PATH = (
    ROOT
    / "gcode"
    / "PAPER_A4_FONT_VS_PROGRAM_ISOLATION_Y65_TANGENT_GCODE_V34.json"
)
PREVIEW_PATH = (
    ROOT
    / "docs"
    / "diagnostics"
    / "PAPER_A4_FONT_VS_PROGRAM_ISOLATION_Y65_TANGENT_GCODE_V34_PREVIEW.png"
)

TEXT = "张"
VISIBLE_HEIGHT_MM = 32.0
ROW_CENTER_Y_MM = 65.0
CONTROL_CENTER_X_MM = 48.0
AA_CENTER_X_MM = 105.0
SONG_CENTER_X_MM = 160.0
TANGENT_APPROACH_MM = aa.TANGENT_APPROACH_MM
FEED_MM_MIN = aa.FEED_MM_MIN
PAPER_X_MIN_MM = aa.PAPER_X_MIN_MM
PAPER_X_MAX_MM = aa.PAPER_X_MAX_MM
PAPER_Y_MIN_MM = aa.PAPER_Y_MIN_MM
PAPER_Y_MAX_MM = aa.PAPER_Y_MAX_MM


@dataclass(frozen=True)
class Panel:
    panel_id: str
    title: str
    source: str
    bounds_mm: tuple[float, float, float, float]
    stroke_count: int


@dataclass(frozen=True)
class IsolationLayout:
    panels: tuple[Panel, ...]
    strokes: tuple[aa.Stroke, ...]
    bounds_mm: tuple[float, float, float, float]


def make_stroke(
    panel_id: str,
    panel_index: int,
    stroke_index: int,
    points: tuple[tuple[float, float], ...],
) -> aa.Stroke:
    if len(points) < 2:
        raise AssertionError("diagnostic stroke needs at least two points")
    first_length = math.dist(points[0], points[1])
    if first_length <= 1.0e-9:
        raise AssertionError("diagnostic stroke has no initial direction")
    unit = (
        (points[1][0] - points[0][0]) / first_length,
        (points[1][1] - points[0][1]) / first_length,
    )
    approach = (
        points[0][0] - unit[0] * TANGENT_APPROACH_MM,
        points[0][1] - unit[1] * TANGENT_APPROACH_MM,
    )
    return aa.Stroke(
        panel_id,
        panel_index,
        stroke_index,
        approach,
        points,
    )


def control_panel() -> tuple[Panel, list[aa.Stroke]]:
    # Explicit geometry: it does not pass through any font parser.  It contains
    # the same horizontal, vertical, falling-left and falling-right motions
    # implicated by the two photographed Zhang glyphs.
    source_strokes = (
        ((35.0, 81.0), (50.0, 81.0)),
        ((35.0, 81.0), (35.0, 66.0)),
        ((35.0, 66.0), (50.0, 66.0)),
        ((35.0, 66.0), (35.0, 50.0)),
        ((35.0, 50.0), (50.0, 50.0)),
        ((55.0, 81.0), (55.0, 50.0)),
        ((48.0, 66.0), (68.0, 66.0)),
        ((62.0, 81.0), (52.0, 71.0)),
        ((55.0, 66.0), (68.0, 50.0)),
    )
    strokes = [
        make_stroke("A", 0, index, tuple(points))
        for index, points in enumerate(source_strokes, start=1)
    ]
    all_points = [point for stroke in strokes for point in stroke.points]
    bounds = (
        min(point[0] for point in all_points),
        min(point[1] for point in all_points),
        max(point[0] for point in all_points),
        max(point[1] for point in all_points),
    )
    return (
        Panel(
            "A",
            "A 几何控制",
            "explicit paper-space lines; no font parser",
            bounds,
            len(strokes),
        ),
        strokes,
    )


def font_panel(
    panel_id: str,
    panel_index: int,
    center_x_mm: float,
    font_path: Path,
    font_sha256: str,
    font_name: str,
    expected_strokes: int,
) -> tuple[Panel, list[aa.Stroke]]:
    if aa.digest(font_path) != font_sha256:
        raise AssertionError(f"{panel_id} pinned font hash changed")
    font = aa.load_gfont(font_path)
    if font.name != font_name:
        raise AssertionError(f"{panel_id} font name changed")
    glyph = font.glyphs[TEXT]
    if glyph.stroke_count != expected_strokes:
        raise AssertionError(f"{panel_id} path count changed")

    source_x_min, source_y_min, source_x_max, source_y_max = glyph.bounds
    scale = VISIBLE_HEIGHT_MM / (source_y_max - source_y_min)
    source_mid_x = (source_x_min + source_x_max) / 2.0
    source_mid_y = (source_y_min + source_y_max) / 2.0
    translate_x = center_x_mm - source_mid_x * scale
    baseline_y = ROW_CENTER_Y_MM + source_mid_y * scale
    transformed = tuple(
        (
            translate_x + source_x * scale,
            baseline_y - source_y * scale,
        )
        for source_x, source_y in glyph.points
    )
    raw_strokes = aa.split_strokes(TEXT, transformed, glyph.commands)
    strokes = [
        make_stroke(
            panel_id,
            panel_index,
            stroke_index,
            points,
        )
        for stroke_index, points in enumerate(raw_strokes, start=1)
    ]
    bounds = (
        center_x_mm - (source_x_max - source_x_min) * scale / 2.0,
        ROW_CENTER_Y_MM - VISIBLE_HEIGHT_MM / 2.0,
        center_x_mm + (source_x_max - source_x_min) * scale / 2.0,
        ROW_CENTER_Y_MM + VISIBLE_HEIGHT_MM / 2.0,
    )
    return (
        Panel(
            panel_id,
            f"{panel_id} {font_name}张",
            f"{font_path.name}:{font_sha256}",
            bounds,
            len(strokes),
        ),
        strokes,
    )


def build_layout() -> IsolationLayout:
    panel_a, strokes_a = control_panel()
    panel_b, strokes_b = font_panel(
        "B",
        1,
        AA_CENTER_X_MM,
        aa.FONT_PATH,
        aa.FONT_SHA256,
        aa.FONT_NAME,
        7,
    )
    panel_c, strokes_c = font_panel(
        "C",
        2,
        SONG_CENTER_X_MM,
        song.FONT_PATH,
        song.FONT_SHA256,
        song.FONT_NAME,
        15,
    )
    strokes = tuple((*strokes_a, *strokes_b, *strokes_c))
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
            raise AssertionError(f"V34 point outside calibrated paper: {point}")
    if bounds[3] >= 100.0:
        raise AssertionError("V34 must remain below existing writing")
    return IsolationLayout(
        (panel_a, panel_b, panel_c),
        strokes,
        bounds,
    )


def gcode_lines(layout: IsolationLayout) -> tuple[str, ...]:
    lines = ["G21", "G90", "G94", "M5", f"F{FEED_MM_MIN}"]
    for stroke in layout.strokes:
        lines.append(
            f"G0 X{stroke.approach[0]:.6f} Y{stroke.approach[1]:.6f}"
        )
        lines.append(
            f"G0 X{stroke.points[0][0]:.6f} Y{stroke.points[0][1]:.6f}"
        )
        lines.append("M3")
        for point in stroke.points[1:]:
            lines.append(f"G1 X{point[0]:.6f} Y{point[1]:.6f}")
        lines.append("M5")
    return tuple(lines)


def write_preview(layout: IsolationLayout) -> None:
    width = round(aa.A4_WIDTH_MM * aa.PREVIEW_PIXELS_PER_MM) + 1
    height = round(aa.A4_HEIGHT_MM * aa.PREVIEW_PIXELS_PER_MM) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (0, 0, width - 1, height - 1),
        outline=(25, 25, 25),
        width=3,
    )
    draw.rectangle(
        (
            *aa.preview_xy((PAPER_X_MIN_MM, PAPER_Y_MAX_MM)),
            *aa.preview_xy((PAPER_X_MAX_MM, PAPER_Y_MIN_MM)),
        ),
        outline=(130, 160, 195),
        width=2,
    )

    # Existing ink bands are preview-only and never emitted as G-code.
    for low, high, label in (
        (114.0, 150.929, "已有 V31"),
        (158.885, 201.231, "已有 V33"),
    ):
        draw.rectangle(
            (
                *aa.preview_xy((PAPER_X_MIN_MM, high)),
                *aa.preview_xy((PAPER_X_MAX_MM, low)),
            ),
            fill=(247, 247, 247),
            outline=(225, 225, 225),
        )
        draw.text(
            aa.preview_xy((27.0, high - 3.0)),
            label,
            fill=(165, 165, 165),
            font=aa.label_font(14),
        )

    draw.text(
        (20, 16),
        "V34 字形 / 程序隔离测试（纸面下方空白区）",
        fill=(20, 20, 20),
        font=aa.label_font(24),
    )
    draw.text(
        (20, 50),
        "A=无字库几何控制  B=aa郭敬明原始张  C=宋体原始张",
        fill=(70, 70, 70),
        font=aa.label_font(17),
    )

    for panel in layout.panels:
        draw.rectangle(
            (
                *aa.preview_xy(
                    (panel.bounds_mm[0], panel.bounds_mm[3])
                ),
                *aa.preview_xy(
                    (panel.bounds_mm[2], panel.bounds_mm[1])
                ),
            ),
            outline=(225, 225, 225),
            width=1,
        )
        label_x, label_y = aa.preview_xy(
            (
                (panel.bounds_mm[0] + panel.bounds_mm[2]) / 2.0 - 8.0,
                91.0,
            )
        )
        draw.text(
            (label_x, label_y),
            panel.title,
            fill=(40, 40, 40),
            font=aa.label_font(15),
        )

    for stroke in layout.strokes:
        approach_px = aa.preview_xy(stroke.approach)
        start_px = aa.preview_xy(stroke.points[0])
        aa.draw_dashed_line(
            draw, approach_px, start_px, (45, 115, 185), width=2
        )
        draw.line(
            [aa.preview_xy(point) for point in stroke.points],
            fill=(15, 15, 15),
            width=3,
            joint="curve",
        )
        draw.ellipse(
            (
                start_px[0] - 3,
                start_px[1] - 3,
                start_px[0] + 3,
                start_px[1] + 3,
            ),
            fill=(195, 35, 35),
        )

    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def write_manifest(
    layout: IsolationLayout,
    lines: tuple[str, ...],
) -> None:
    gcode_text = "\n".join(lines) + "\n"
    manifest = {
        "id": "PAPER_A4_FONT_VS_PROGRAM_ISOLATION_Y65_TANGENT_GCODE_V34",
        "purpose": "separate font geometry from generator/firmware/mechanics",
        "paper_region": "lower blank area below Y=100 mm",
        "panels": [
            {
                "id": panel.panel_id,
                "title": panel.title,
                "source": panel.source,
                "bounds_mm": list(panel.bounds_mm),
                "stroke_count": panel.stroke_count,
            }
            for panel in layout.panels
        ],
        "layout": {
            "row_center_y_mm": ROW_CENTER_Y_MM,
            "bounds_with_approach_mm": list(layout.bounds_mm),
        },
        "motion": {
            "feed_mm_min": FEED_MM_MIN,
            "tangent_approach_mm": TANGENT_APPROACH_MM,
            "stroke_count": len(layout.strokes),
            "g1_count": sum(
                len(stroke.points) - 1 for stroke in layout.strokes
            ),
        },
        "gcode": {
            "file": GCODE_PATH.name,
            "line_count": len(lines),
            "sha256": hashlib.sha256(
                GCODE_PATH.read_bytes()
            ).hexdigest().upper(),
        },
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    layout = build_layout()
    lines = gcode_lines(layout)
    GCODE_PATH.write_text("\n".join(lines) + "\n", encoding="ascii")
    write_preview(layout)
    write_manifest(layout, lines)
    print(
        "generated_font_vs_program_isolation_v34=PASS "
        f"panels={len(layout.panels)} strokes={len(layout.strokes)} "
        f"G1={sum(len(stroke.points) - 1 for stroke in layout.strokes)} "
        f"bounds_x={layout.bounds_mm[0]:.3f}..{layout.bounds_mm[2]:.3f} "
        f"bounds_y={layout.bounds_mm[1]:.3f}..{layout.bounds_mm[3]:.3f}"
    )
    print(GCODE_PATH)
    print(PREVIEW_PATH)
    print(MANIFEST_PATH)


if __name__ == "__main__":
    main()
