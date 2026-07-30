#!/usr/bin/env python3
"""Generate the V32 Song sample 50 mm higher to avoid prior writing."""

from __future__ import annotations

from pathlib import Path

import generate_paper_a4_zhang_jia_le_v31 as layout_base
import generate_paper_a4_zhang_jia_le_v32 as song


ROOT = Path(__file__).resolve().parents[1]
GCODE_PATH = (
    ROOT
    / "gcode"
    / "PAPER_A4_ZHANG_JIA_LE_SONG_32MM_Y180_TANGENT_GCODE_V33.gcode"
)
MANIFEST_PATH = (
    ROOT
    / "gcode"
    / "PAPER_A4_ZHANG_JIA_LE_SONG_32MM_Y180_TANGENT_GCODE_V33.json"
)
PREVIEW_PATH = (
    ROOT
    / "docs"
    / "diagnostics"
    / "PAPER_A4_ZHANG_JIA_LE_SONG_32MM_Y180_TANGENT_GCODE_V33_PREVIEW.png"
)

ARTIFACT_ID = "PAPER_A4_ZHANG_JIA_LE_SONG_32MM_Y180_TANGENT_GCODE_V33"
VERSION_LABEL = "V33 上移 50 mm"
ROW_CENTER_Y_MM = 180.0

FONT_PATH = song.FONT_PATH
FONT_SHA256 = song.FONT_SHA256
FONT_NAME = song.FONT_NAME
FONT_EM_SIZE = song.FONT_EM_SIZE
TEXT = song.TEXT
EXPECTED_STROKE_COUNTS = song.EXPECTED_STROKE_COUNTS
FEED_MM_MIN = song.FEED_MM_MIN
TANGENT_APPROACH_MM = song.TANGENT_APPROACH_MM
PAPER_X_MIN_MM = song.PAPER_X_MIN_MM
PAPER_X_MAX_MM = song.PAPER_X_MAX_MM
PAPER_Y_MIN_MM = song.PAPER_Y_MIN_MM
PAPER_Y_MAX_MM = song.PAPER_Y_MAX_MM


def build_layout() -> layout_base.Layout:
    return layout_base.build_layout_from_gfont(
        FONT_PATH,
        FONT_SHA256,
        FONT_NAME,
        FONT_EM_SIZE,
        EXPECTED_STROKE_COUNTS,
        ROW_CENTER_Y_MM,
    )


def gcode_lines(layout: layout_base.Layout) -> tuple[str, ...]:
    return song.gcode_lines(layout)


def main() -> None:
    layout = build_layout()
    lines = gcode_lines(layout)
    GCODE_PATH.write_text("\n".join(lines) + "\n", encoding="ascii")
    song.write_preview(
        layout,
        preview_path=PREVIEW_PATH,
        version_label=VERSION_LABEL,
    )
    song.write_manifest(
        layout,
        lines,
        gcode_path=GCODE_PATH,
        manifest_path=MANIFEST_PATH,
        artifact_id=ARTIFACT_ID,
        row_center_y_mm=ROW_CENTER_Y_MM,
        trial_after={
            "id": song.ARTIFACT_ID,
            "reason": "same Song paths shifted 50 mm upward to avoid V31 ink",
        },
    )
    print(
        "generated_zhang_jia_le_v33=PASS "
        f"font={layout.font.name} text={TEXT} "
        f"row_center_y={ROW_CENTER_Y_MM:.1f} "
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
