#!/usr/bin/env python3
"""Verify the selected V46 9 mm 吸口雾霾压压惊 sample."""

from __future__ import annotations

import hashlib
import json
import math

import generate_paper_a4_top_left_xikou_wumai_9mm_v46 as variant
from check_circle_diagnostics_v38_v39 import verify_path


def check_source_geometry(layout) -> None:
    assert tuple(item.character for item in layout.characters) == tuple(
        variant.TEXT
    )
    assert tuple(
        item.stroke_count for item in layout.characters
    ) == variant.EXPECTED_STROKE_COUNTS
    global_y_min = min(
        layout.font.glyphs[character].bounds[1]
        for character in variant.TEXT
    )
    for character_index, character in enumerate(variant.TEXT):
        glyph = layout.font.glyphs[character]
        item = layout.characters[character_index]
        source_x_min = glyph.bounds[0]
        expected_points = tuple(
            (
                item.bounds_mm[0]
                + (source_x - source_x_min) * layout.scale_mm_per_unit,
                variant.CONTENT_TOP_MM
                - (source_y - global_y_min) * layout.scale_mm_per_unit,
            )
            for source_x, source_y in glyph.points
        )
        expected_strokes = variant.engine.shared.split_strokes(
            character, expected_points, glyph.commands
        )
        actual_strokes = [
            stroke.points
            for stroke in layout.strokes
            if stroke.character_index == character_index
        ]
        assert len(expected_strokes) == len(actual_strokes)
        for expected, actual in zip(expected_strokes, actual_strokes):
            assert len(expected) == len(actual)
            assert all(
                math.dist(source, target) < 1.0e-10
                for source, target in zip(expected, actual)
            )


def main() -> None:
    layout = variant.build_layout()
    check_source_geometry(layout)
    expected_lines = variant.gcode_lines(layout)
    text = variant.GCODE_PATH.read_text(encoding="ascii")
    actual_lines = tuple(text.splitlines())
    assert actual_lines == expected_lines
    manifest = json.loads(
        variant.MANIFEST_PATH.read_text(encoding="utf-8")
    )
    assert manifest["id"] == variant.TEST_ID
    assert manifest["required_firmware"] == variant.BUILD_ID
    assert manifest["text"] == variant.TEXT
    assert manifest["font"]["sha256"] == variant.FONT_SHA256
    assert manifest["font"]["name"] == variant.FONT_NAME
    assert manifest["font"]["geometry"] == (
        "unmodified gfont path points and command order"
    )
    assert tuple(manifest["font"]["character_path_counts"]) == (
        10,
        10,
        7,
        5,
        12,
    )
    assert manifest["layout"]["visible_height_mm"] == 9.0
    assert manifest["layout"]["content_left_mm"] == 30.0
    assert manifest["layout"]["content_top_mm"] == 190.0
    assert manifest["motion"]["feed_mm_min"] == 150
    assert manifest["coordinate_contract"][
        "firmware_paper_map_enabled"
    ] is False
    assert manifest["coordinate_contract"][
        "offline_pointwise_paper_to_user_map_enabled"
    ] is True
    assert hashlib.sha256(text.encode("ascii")).hexdigest() == manifest[
        "gcode"
    ]["sha256"]

    serial_header = (
        variant.engine.shared.ROOT / "TASK" / "gcode_serial.h"
    ).read_text(encoding="utf-8")
    motion_header = (
        variant.engine.shared.ROOT
        / "APP"
        / "Inc"
        / "app_writer_motion.h"
    ).read_text(encoding="utf-8")
    assert f'"{variant.BUILD_ID}"' in serial_header
    assert "#define GCODE_SERIAL_PAPER_MAP_ENABLE         (0u)" in (
        serial_header
    )
    assert (
        motion_header.count(
            "#define APP_WRITER_DIRECTION_COMP_ENABLE     (0u)"
        )
        >= 1
    )

    plan = variant.command_plan(layout)
    assert len(plan) == 44
    for stroke, paper_points, user_points in plan:
        assert paper_points[0] == stroke.points[0]
        assert paper_points[-1] == stroke.points[-1]
        assert len(paper_points) == len(user_points)
        assert all(
            math.dist(start, end) <= variant.PAPER_SUBDIVISION_MM + 1.0e-9
            for start, end in zip(paper_points, paper_points[1:])
        )
        assert math.isclose(
            math.dist(stroke.approach, stroke.points[0]),
            variant.TANGENT_APPROACH_MM,
            abs_tol=1.0e-9,
        )

    commands = [
        line for line in actual_lines if line and not line.startswith(";")
    ]
    g0_count = sum(line.startswith("G0 ") for line in commands)
    g1_count = sum(line.startswith("G1 ") for line in commands)
    assert g0_count == 88
    assert g1_count == manifest["motion"]["g1_count"]
    assert commands.count("M3") == 44
    assert commands.count("M5") == 45

    safe_samples, quantized_error = verify_path(list(actual_lines))
    assert quantized_error < 0.10
    print(
        "PASS: V46 text=张佳乐作品 font=吸口雾霾压压惊 "
        "source_geometry=EXACT height=9mm "
        "placement=TOP_LEFT_THIRD_LINE paths=10,10,7,5,12 "
        f"strokes=44 G0={g0_count} G1={g1_count} "
        "paper_map=OFF offline_pointwise_map=ON "
        f"paper_segment_max={variant.PAPER_SUBDIVISION_MM:.1f}mm "
        f"safe_samples={safe_samples} "
        f"quantized_error_max={quantized_error:.4f}mm"
    )


if __name__ == "__main__":
    main()
