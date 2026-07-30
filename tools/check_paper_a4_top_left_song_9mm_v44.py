#!/usr/bin/env python3
"""Verify the V44 top-left second-line 9 mm Song-font sample."""

from __future__ import annotations

import hashlib
import json
import math

import generate_paper_a4_top_left_song_12mm_v43 as source
import generate_paper_a4_top_left_song_9mm_v44 as variant
from check_circle_diagnostics_v38_v39 import verify_path


def main() -> None:
    source_layout = source.build_layout()
    layout = variant.build_layout()
    assert len(source_layout.strokes) == len(layout.strokes) == 54
    assert tuple(
        character.stroke_count for character in layout.characters
    ) == source.EXPECTED_STROKE_COUNTS
    for source_stroke, target_stroke in zip(
        source_layout.strokes, layout.strokes
    ):
        assert source_stroke.character == target_stroke.character
        assert source_stroke.stroke_index == target_stroke.stroke_index
        expected_points = tuple(
            variant.transform_point(point)
            for point in source_stroke.points
        )
        assert len(expected_points) == len(target_stroke.points)
        assert all(
            math.dist(expected, actual) < 1.0e-10
            for expected, actual in zip(
                expected_points, target_stroke.points
            )
        )
        assert math.dist(
            variant.transform_point(source_stroke.approach),
            target_stroke.approach,
        ) < 1.0e-10

    expected_lines = variant.gcode_lines(layout)
    text = variant.GCODE_PATH.read_text(encoding="ascii")
    actual_lines = tuple(text.splitlines())
    assert actual_lines == expected_lines
    manifest = json.loads(
        variant.MANIFEST_PATH.read_text(encoding="utf-8")
    )
    assert manifest["id"] == variant.TEST_ID
    assert manifest["required_firmware"] == variant.BUILD_ID
    assert manifest["comparison_to"] == source.TEST_ID
    assert manifest["text"] == source.TEXT
    assert manifest["font"]["sha256"] == source.FONT_SHA256
    assert manifest["font"]["geometry"] == (
        "unmodified gfont path points and command order"
    )
    assert manifest["layout"]["visible_height_mm"] == 9.0
    assert manifest["layout"]["content_left_mm"] == 30.0
    assert manifest["layout"]["content_top_mm"] == 212.0
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

    plan = variant.command_plan(layout)
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
    assert g0_count == 108
    assert g1_count == manifest["motion"]["g1_count"]
    assert commands.count("M3") == 54
    assert commands.count("M5") == 55

    safe_samples, quantized_error = verify_path(list(actual_lines))
    assert quantized_error < 0.10
    print(
        "PASS: V44 text=张佳乐作品 font=宋体 source_geometry=EXACT "
        "height=9mm placement=TOP_LEFT_SECOND_LINE "
        f"strokes=54 G0={g0_count} G1={g1_count} "
        "paper_map=OFF offline_pointwise_map=ON "
        f"paper_segment_max={variant.PAPER_SUBDIVISION_MM:.1f}mm "
        f"safe_samples={safe_samples} "
        f"quantized_error_max={quantized_error:.4f}mm"
    )


if __name__ == "__main__":
    main()
