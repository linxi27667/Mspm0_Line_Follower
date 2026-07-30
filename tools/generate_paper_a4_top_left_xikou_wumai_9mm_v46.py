#!/usr/bin/env python3
"""Generate the selected third-line 9 mm 吸口雾霾压压惊 sample."""

from __future__ import annotations

import generate_paper_a4_top_left_meiyou_ruguo_9mm_v45 as engine


TEST_ID = "PAPER_A4_TOP_LEFT_XIKOU_WUMAI_9MM_SAMPLE_GCODE_V46"
BUILD_ID = engine.BUILD_ID
GCODE_PATH = engine.shared.ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = engine.shared.ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = (
    engine.shared.ROOT
    / "docs"
    / "diagnostics"
    / f"{TEST_ID}_PREVIEW.png"
)
FONT_PATH = (
    engine.shared.ROOT
    / "assets"
    / "kenjoy_gfont"
    / "XIKOU_WUMAI_YAYA_JING_1d6c6baa.gfont"
)
FONT_SHA256 = (
    "9377ADD7793C0B7965E21E6B7660DD6E1B6A90EE455DA076E36FB8D483C14B3A"
)
FONT_NAME = "吸口雾霾压压惊"
FONT_TAG = "XIKOU_WUMAI_YAYA_JING"
FONT_EM_SIZE = 400
TEXT = "张佳乐作品"
EXPECTED_STROKE_COUNTS = (10, 10, 7, 5, 12)


def configure_engine() -> None:
    engine.TEST_ID = TEST_ID
    engine.BUILD_ID = BUILD_ID
    engine.GCODE_PATH = GCODE_PATH
    engine.MANIFEST_PATH = MANIFEST_PATH
    engine.PREVIEW_PATH = PREVIEW_PATH
    engine.FONT_PATH = FONT_PATH
    engine.FONT_SHA256 = FONT_SHA256
    engine.FONT_NAME = FONT_NAME
    engine.FONT_TAG = FONT_TAG
    engine.FONT_EM_SIZE = FONT_EM_SIZE
    engine.TEXT = TEXT
    engine.EXPECTED_STROKE_COUNTS = EXPECTED_STROKE_COUNTS


configure_engine()

build_layout = engine.build_layout
subdivide_points = engine.subdivide_points
command_plan = engine.command_plan
gcode_lines = engine.gcode_lines
write_preview = engine.write_preview
write_manifest = engine.write_manifest

VISIBLE_HEIGHT_MM = engine.VISIBLE_HEIGHT_MM
CHARACTER_GAP_MM = engine.CHARACTER_GAP_MM
CONTENT_LEFT_MM = engine.CONTENT_LEFT_MM
CONTENT_TOP_MM = engine.CONTENT_TOP_MM
TANGENT_APPROACH_MM = engine.TANGENT_APPROACH_MM
PAPER_SUBDIVISION_MM = engine.PAPER_SUBDIVISION_MM
FEED_MM_MIN = engine.FEED_MM_MIN


def main() -> None:
    layout = build_layout()
    lines = gcode_lines(layout)
    GCODE_PATH.write_text(
        "\n".join(lines) + "\n",
        encoding="ascii",
        newline="\n",
    )
    write_preview(layout)
    write_manifest(layout, lines)
    plan = command_plan(layout)
    print(
        "generated_top_left_xikou_wumai_9mm_v46=PASS "
        f"characters={len(TEXT)} strokes={len(layout.strokes)} "
        f"G1={sum(len(points) - 1 for _, _, points in plan)} "
        f"bounds_x={layout.bounds_mm[0]:.3f}..{layout.bounds_mm[2]:.3f} "
        f"bounds_y={layout.bounds_mm[1]:.3f}..{layout.bounds_mm[3]:.3f}"
    )
    print(GCODE_PATH)
    print(PREVIEW_PATH)
    print(MANIFEST_PATH)


if __name__ == "__main__":
    main()
