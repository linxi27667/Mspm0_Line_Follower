#!/usr/bin/env python3
"""Generate upright 张佳乐 from the unmodified Kenjoy Song gfont."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

import generate_paper_a4_zhang_jia_le_v31 as base


ROOT = Path(__file__).resolve().parents[1]
FONT_PATH = (
    ROOT / "assets" / "kenjoy_gfont" / "SONG_ec900461.gfont"
)
GCODE_PATH = (
    ROOT
    / "gcode"
    / "PAPER_A4_ZHANG_JIA_LE_SONG_32MM_TANGENT_GCODE_V32.gcode"
)
MANIFEST_PATH = (
    ROOT
    / "gcode"
    / "PAPER_A4_ZHANG_JIA_LE_SONG_32MM_TANGENT_GCODE_V32.json"
)
PREVIEW_PATH = (
    ROOT
    / "docs"
    / "diagnostics"
    / "PAPER_A4_ZHANG_JIA_LE_SONG_32MM_TANGENT_GCODE_V32_PREVIEW.png"
)

FONT_SHA256 = (
    "A74332F3F53C77B02DE6637ED8AAF0D5010E61444B1216D3E291A6AEA1419C24"
)
FONT_NAME = "宋体"
FONT_EM_SIZE = 600
TEXT = base.TEXT
EXPECTED_STROKE_COUNTS = (15, 9, 13)
ARTIFACT_ID = "PAPER_A4_ZHANG_JIA_LE_SONG_32MM_TANGENT_GCODE_V32"
VERSION_LABEL = "V32"
ROW_CENTER_Y_MM = base.ROW_CENTER_Y_MM
FEED_MM_MIN = base.FEED_MM_MIN
TANGENT_APPROACH_MM = base.TANGENT_APPROACH_MM
PAPER_X_MIN_MM = base.PAPER_X_MIN_MM
PAPER_X_MAX_MM = base.PAPER_X_MAX_MM
PAPER_Y_MIN_MM = base.PAPER_Y_MIN_MM
PAPER_Y_MAX_MM = base.PAPER_Y_MAX_MM


def build_layout() -> base.Layout:
    return base.build_layout_from_gfont(
        FONT_PATH,
        FONT_SHA256,
        FONT_NAME,
        FONT_EM_SIZE,
        EXPECTED_STROKE_COUNTS,
        ROW_CENTER_Y_MM,
    )


def gcode_lines(layout: base.Layout) -> tuple[str, ...]:
    return base.gcode_lines(layout)


def write_preview(
    layout: base.Layout,
    preview_path: Path = PREVIEW_PATH,
    version_label: str = VERSION_LABEL,
) -> None:
    width = round(base.A4_WIDTH_MM * base.PREVIEW_PIXELS_PER_MM) + 1
    height = round(base.A4_HEIGHT_MM * base.PREVIEW_PIXELS_PER_MM) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (0, 0, width - 1, height - 1),
        outline=(25, 25, 25),
        width=3,
    )
    draw.rectangle(
        (
            *base.preview_xy(
                (base.PAPER_X_MIN_MM, base.PAPER_Y_MAX_MM)
            ),
            *base.preview_xy(
                (base.PAPER_X_MAX_MM, base.PAPER_Y_MIN_MM)
            ),
        ),
        outline=(130, 160, 195),
        width=2,
    )
    draw.text(
        (20, 16),
        f"{version_label} 字库原字试写：张佳乐（宋体，约 32 mm）",
        fill=(20, 20, 20),
        font=base.label_font(24),
    )
    draw.text(
        (20, 50),
        "黑线=宋体原始路径  蓝虚线=6 mm抬笔预接近  红点=字库起点",
        fill=(70, 70, 70),
        font=base.label_font(17),
    )

    for character in layout.characters:
        draw.rectangle(
            (
                *base.preview_xy(
                    (character.bounds_mm[0], character.bounds_mm[3])
                ),
                *base.preview_xy(
                    (character.bounds_mm[2], character.bounds_mm[1])
                ),
            ),
            outline=(225, 225, 225),
            width=1,
        )

    for stroke in layout.strokes:
        approach_px = base.preview_xy(stroke.approach)
        start_px = base.preview_xy(stroke.points[0])
        base.draw_dashed_line(
            draw, approach_px, start_px, (45, 115, 185), width=2
        )
        draw.line(
            [base.preview_xy(point) for point in stroke.points],
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

    preview_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(preview_path)


def write_manifest(
    layout: base.Layout,
    lines: tuple[str, ...],
    *,
    gcode_path: Path = GCODE_PATH,
    manifest_path: Path = MANIFEST_PATH,
    artifact_id: str = ARTIFACT_ID,
    row_center_y_mm: float = ROW_CENTER_Y_MM,
    trial_after: dict[str, str] | None = None,
) -> None:
    gcode_text = "\n".join(lines) + "\n"
    if trial_after is None:
        trial_after = {
            "id": "PAPER_A4_ZHANG_JIA_LE_AA_GUO_32MM_TANGENT_GCODE_V31",
            "reason": (
                "V31 Zhang glyph showed an unwanted lower bow vertical "
                "and a short vertical lead near the lower-right stroke"
            ),
        }
    manifest = {
        "id": artifact_id,
        "trial_after": trial_after,
        "text": TEXT,
        "font": {
            "file": FONT_PATH.name,
            "sha256": FONT_SHA256,
            "name": layout.font.name,
            "em_size": layout.font.em_size,
            "glyph_count": len(layout.font.glyphs),
            "geometry": "unmodified gfont path points and command order",
        },
        "coordinate_contract": {
            "gfont_y": "positive downward",
            "paper_y": "positive upward",
            "transform_y": "paper_y = baseline_y - source_y * scale",
        },
        "layout": {
            "visible_height_mm": base.VISIBLE_HEIGHT_MM,
            "character_gap_mm": base.CHARACTER_GAP_MM,
            "row_center_mm": [
                base.ROW_CENTER_X_MM,
                row_center_y_mm,
            ],
            "scale_mm_per_font_unit": layout.scale_mm_per_unit,
            "bounds_mm": list(layout.bounds_mm),
            "characters": [
                {
                    "character": item.character,
                    "bounds_mm": list(item.bounds_mm),
                    "stroke_count": item.stroke_count,
                }
                for item in layout.characters
            ],
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
            "file": gcode_path.name,
            "line_count": len(lines),
            "sha256": hashlib.sha256(
                gcode_path.read_bytes()
            ).hexdigest().upper(),
        },
    }
    manifest_path.write_text(
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
        "generated_zhang_jia_le_v32=PASS "
        f"font={layout.font.name} text={TEXT} "
        f"strokes={len(layout.strokes)} "
        f"G1={sum(len(stroke.points) - 1 for stroke in layout.strokes)} "
        f"bounds_x={layout.bounds_mm[0]:.3f}..{layout.bounds_mm[2]:.3f} "
        f"bounds_y={layout.bounds_mm[1]:.3f}..{layout.bounds_mm[3]:.3f}"
    )
    print(GCODE_PATH)
    print(PREVIEW_PATH)
    print(MANIFEST_PATH)


if __name__ == "__main__":
    main()
