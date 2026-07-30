#!/usr/bin/env python3
"""Verify the V42 direct-coordinate Song-font 张佳乐 sample."""

from __future__ import annotations

import hashlib
import json
import math

import check_paper_a4_zhang_jia_le_v32 as song_check
import generate_paper_a4_zhang_jia_le_song_v42 as variant
from check_circle_diagnostics_v38_v39 import verify_path
from generate_paper_a4_map_vs_cartesian_circle_v36 import (
    mapped,
    mapping_model,
)


MAP_COEFFICIENTS, MAP_TOTAL_DELTA = mapping_model()


def independent_map(point: tuple[float, float]) -> tuple[float, float]:
    result = mapped(point, MAP_COEFFICIENTS, MAP_TOTAL_DELTA)
    return float(result[0]), float(result[1])


def main() -> None:
    layout = variant.build_layout()
    song_check.check_song_geometry(layout)
    expected_lines = variant.gcode_lines(layout)
    text = variant.GCODE_PATH.read_text(encoding="ascii")
    actual_lines = tuple(text.splitlines())
    assert actual_lines == expected_lines

    manifest = json.loads(
        variant.MANIFEST_PATH.read_text(encoding="utf-8")
    )
    assert manifest["id"] == variant.TEST_ID
    assert manifest["required_firmware"] == variant.BUILD_ID
    assert manifest["font"]["sha256"] == variant.FONT_SHA256
    assert manifest["font"]["name"] == "宋体"
    assert manifest["font"]["geometry"] == (
        "unmodified gfont path points and command order"
    )
    assert tuple(manifest["font"]["character_path_counts"]) == (15, 9, 13)
    assert manifest["layout"]["new_blank_a4_required"] is True
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
        variant.ROOT / "TASK" / "gcode_serial.h"
    ).read_text(encoding="utf-8")
    motion_header = (
        variant.ROOT / "APP" / "Inc" / "app_writer_motion.h"
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
    assert len(plan) == 37
    for stroke, paper_points, user_points in plan:
        assert paper_points[0] == stroke.points[0]
        assert paper_points[-1] == stroke.points[-1]
        assert len(paper_points) == len(user_points)
        assert all(
            math.dist(start, end) <= variant.PAPER_SUBDIVISION_MM + 1.0e-9
            for start, end in zip(paper_points, paper_points[1:])
        )
        for paper_point, user_point in zip(paper_points, user_points):
            assert math.dist(
                independent_map(paper_point), user_point
            ) < 1.0e-9

    commands = [
        line for line in actual_lines if line and not line.startswith(";")
    ]
    assert commands[:6] == [
        "G21",
        "G90",
        "G94",
        f"F{variant.FEED_MM_MIN}",
        "S1000",
        "M5",
    ]
    g0_count = sum(line.startswith("G0 ") for line in commands)
    g1_count = sum(line.startswith("G1 ") for line in commands)
    assert g0_count == 74
    assert g1_count == manifest["motion"]["g1_count"]
    assert commands.count("M3") == 37
    assert commands.count("M5") == 38

    safe_samples, quantized_error = verify_path(list(actual_lines))
    assert quantized_error < 0.10
    print(
        "PASS: V42 text=张佳乐 font=宋体 source_geometry=EXACT "
        "upright_y=PASS character_paths=15,9,13 "
        f"strokes=37 G0={g0_count} G1={g1_count} "
        "paper_map=OFF offline_pointwise_map=ON "
        f"paper_segment_max={variant.PAPER_SUBDIVISION_MM:.1f}mm "
        f"safe_samples={safe_samples} "
        f"quantized_error_max={quantized_error:.4f}mm"
    )


if __name__ == "__main__":
    main()
