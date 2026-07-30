"""Check the upright V32 Song-gfont 张佳乐 sample."""

from __future__ import annotations

import math

import check_paper_a4_zhang_jia_le_v31 as shared
import generate_paper_a4_zhang_jia_le_v32 as variant


CHECK_VARIANT = "V32"


def check_song_geometry(layout) -> None:
    if tuple(item.character for item in layout.characters) != tuple(
        variant.TEXT
    ):
        raise AssertionError("left-to-right character order changed")
    if tuple(
        item.stroke_count for item in layout.characters
    ) != variant.EXPECTED_STROKE_COUNTS:
        raise AssertionError("Song per-character path counts changed")
    if any(
        left.bounds_mm[2] >= right.bounds_mm[0]
        for left, right in zip(layout.characters, layout.characters[1:])
    ):
        raise AssertionError("character boxes are not left-to-right")

    for character_index, character in enumerate(variant.TEXT):
        glyph = layout.font.glyphs[character]
        character_layout = layout.characters[character_index]
        source_x_min, source_y_min, _, _ = glyph.bounds
        expected_points = tuple(
            (
                character_layout.bounds_mm[0]
                + (source_x - source_x_min) * layout.scale_mm_per_unit,
                character_layout.bounds_mm[3]
                - (source_y - source_y_min) * layout.scale_mm_per_unit,
            )
            for source_x, source_y in glyph.points
        )
        expected_strokes = shared.split_strokes(
            character, expected_points, glyph.commands
        )
        actual_strokes = [
            stroke.points
            for stroke in layout.strokes
            if stroke.character_index == character_index
        ]
        if len(expected_strokes) != len(actual_strokes):
            raise AssertionError(f"{character} source path count changed")
        for expected, actual in zip(expected_strokes, actual_strokes):
            if len(expected) != len(actual):
                raise AssertionError(f"{character} source point count changed")
            for source_point, actual_point in zip(expected, actual):
                if not (
                    math.isclose(
                        source_point[0], actual_point[0], abs_tol=1.0e-10
                    )
                    and math.isclose(
                        source_point[1], actual_point[1], abs_tol=1.0e-10
                    )
                ):
                    raise AssertionError(
                        f"{character} no longer follows original Song path"
                    )

    # Font-specific upright sentinels.  These compare clearly separated
    # top and bottom paths and fail if the gfont Y sign is inverted.
    by_character = {
        character: [
            stroke
            for stroke in layout.strokes
            if stroke.character == character
        ]
        for character in variant.TEXT
    }

    def mean_y(stroke) -> float:
        return sum(point[1] for point in stroke.points) / len(stroke.points)

    zhang = by_character["张"]
    jia = by_character["佳"]
    le = by_character["乐"]
    if not (
        mean_y(zhang[1]) > mean_y(zhang[6])
        and mean_y(jia[8]) > mean_y(jia[0])
        and mean_y(le[3]) > mean_y(le[0])
        and mean_y(le[3]) > mean_y(le[11])
    ):
        raise AssertionError("Song glyphs are vertically reversed")

    # The source Song gfont intentionally contains six tiny cap paths.
    # Preserve and count them instead of silently deleting font geometry.
    stroke_lengths = [
        sum(math.dist(a, b) for a, b in zip(stroke.points, stroke.points[1:]))
        for stroke in layout.strokes
    ]
    micro_paths = [length for length in stroke_lengths if length < 0.20]
    if len(micro_paths) != 6 or min(micro_paths) < 0.10:
        raise AssertionError("unexpected Song micro-path inventory")


def main() -> None:
    shared.GCODE_PATH = variant.GCODE_PATH
    shared.MANIFEST_PATH = variant.MANIFEST_PATH
    shared.PREVIEW_PATH = variant.PREVIEW_PATH
    shared.FONT_SHA256 = variant.FONT_SHA256
    shared.TEXT = variant.TEXT
    shared.EXPECTED_STROKE_COUNTS = variant.EXPECTED_STROKE_COUNTS
    shared.FEED_MM_MIN = variant.FEED_MM_MIN
    shared.TANGENT_APPROACH_MM = variant.TANGENT_APPROACH_MM
    shared.PAPER_X_MIN_MM = variant.PAPER_X_MIN_MM
    shared.PAPER_X_MAX_MM = variant.PAPER_X_MAX_MM
    shared.PAPER_Y_MIN_MM = variant.PAPER_Y_MIN_MM
    shared.PAPER_Y_MAX_MM = variant.PAPER_Y_MAX_MM
    shared.ROOT = variant.GCODE_PATH.parents[1]
    shared.GCODE_HEADER = shared.ROOT / "TASK" / "gcode_serial.h"
    shared.build_layout = variant.build_layout
    shared.gcode_lines = variant.gcode_lines
    shared.check_font_geometry = check_song_geometry
    shared.MIN_DRAW_SEGMENT_MM = 0.10
    shared.MIN_STROKE_LENGTH_MM = 0.10
    shared.CHECK_VARIANT = CHECK_VARIANT
    shared.main()


if __name__ == "__main__":
    main()
