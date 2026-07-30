#!/usr/bin/env python3
"""Generate four unmapped standard-paper-coordinate XY verification lines."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

import generate_paper_a4_top_left_song_12mm_v43 as shared


ROOT = Path(__file__).resolve().parents[1]
TEST_ID = "PAPER_A4_STANDARD_XY_LINES_F300_FIRMWARE_SBOW_GCODE_V62"
FIRMWARE_ID = "PAPER_A4_STANDARD_GCODE_SBOW_PAPERMAP_YSHIFT15_V29"
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"

STROKES = (
    ("H_UPPER", (25.0, 230.0), (185.0, 230.0)),
    ("H_LOWER", (25.0, 215.0), (185.0, 215.0)),
    ("V_LEFT", (155.0, 235.0), (155.0, 75.0)),
    ("V_RIGHT", (170.0, 235.0), (170.0, 75.0)),
)


def gcode_lines() -> tuple[str, ...]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware_required={FIRMWARE_ID}",
        "; coordinates=STANDARD_A4_PHYSICAL_PAPER_MM",
        "; offline_mapping=NONE offline_prewarp=NONE",
        "; firmware_owns=BASE_MAP,SBOW_CORRECTION,YSHIFT15",
        "G21",
        "G90",
        "G94",
        "F300",
        "S1000",
        "M5",
    ]
    for stroke_id, start, end in STROKES:
        lines.extend(
            (
                f"; ===== {stroke_id} =====",
                f"G0 X{start[0]:.3f} Y{start[1]:.3f}",
                "M3",
                f"G1 X{end[0]:.3f} Y{end[1]:.3f}",
                "M5",
            )
        )
    lines.append("M5")
    return tuple(lines)


def write_preview() -> None:
    width = round(shared.A4_WIDTH_MM * 4.0) + 1
    height = round(shared.A4_HEIGHT_MM * 4.0) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (0, 0, width - 1, height - 1),
        outline=(25, 25, 25),
        width=3,
    )
    for stroke_id, start, end in STROKES:
        start_px = shared.preview_xy(start)
        end_px = shared.preview_xy(end)
        draw.line((start_px, end_px), fill=(25, 125, 60), width=3)
        draw.text(
            (start_px[0] + 5, start_px[1] - 23),
            stroke_id,
            fill=(25, 105, 50),
            font=shared.label_font(15),
        )
    draw.text(
        (20, 18),
        "V62 standard G-code: no host-side map or prewarp",
        fill=(30, 30, 30),
        font=shared.label_font(18),
    )
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def main() -> None:
    lines = gcode_lines()
    text = "\n".join(lines) + "\n"
    GCODE_PATH.write_text(text, encoding="ascii", newline="\n")
    manifest = {
        "id": TEST_ID,
        "required_firmware": FIRMWARE_ID,
        "coordinate_contract": {
            "units": "mm",
            "frame": "nominal physical A4 paper",
            "offline_mapping": False,
            "offline_prewarp": False,
            "firmware_mapping": True,
            "firmware_s_bow_correction": True,
        },
        "strokes": [
            {
                "id": stroke_id,
                "start_mm": list(start),
                "end_mm": list(end),
            }
            for stroke_id, start, end in STROKES
        ],
        "motion": {
            "feed_mm_min": 300,
            "stroke_count": len(STROKES),
            "g0_count": len(STROKES),
            "g1_count": len(STROKES),
        },
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
    write_preview()
    print(
        "standard_xy_lines_v62=PASS "
        "offline_mapping=NONE offline_prewarp=NONE "
        f"G0={len(STROKES)} G1={len(STROKES)}"
    )
    print(GCODE_PATH)
    print(PREVIEW_PATH)
    print(MANIFEST_PATH)


if __name__ == "__main__":
    main()
