#!/usr/bin/env python3
"""Generate the V41 same-direction repeatability circle diagnostic."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

from generate_paper_a4_map_vs_cartesian_circle_v36 import (
    mapped,
    mapping_model,
)


ROOT = Path(__file__).resolve().parents[1]
TEST_ID = "PAPER_A4_CIRCLE_DIRECTION_REPEAT_D18_GCODE_V41"
BUILD_ID = "PAPER_A4_CONTINUOUS_QUEUE_SAFE_HOME_GCODE_V27"
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"

FEED_MM_MIN = 180
RADIUS_MM = 9.0
SEGMENTS = 72
TANGENT_PRELOAD_MM = 4.0
NOMINAL_GROUPS = (
    ("LEFT_CW_REPEAT", (50.0, 230.0), ("CW", "CW")),
    ("MIDDLE_CCW_REPEAT", (105.0, 230.0), ("CCW", "CCW")),
    ("RIGHT_CW_CCW_OVERLAY", (160.0, 230.0), ("CW", "CCW")),
)

MAP_COEFFICIENTS, MAP_TOTAL_DELTA = mapping_model()


def map_center(paper_center: tuple[float, float]) -> tuple[float, float]:
    result = mapped(paper_center, MAP_COEFFICIENTS, MAP_TOTAL_DELTA)
    return float(result[0]), float(result[1])


def circle_points(
    center: tuple[float, float],
    direction: str,
) -> list[tuple[float, float]]:
    sign = -1.0 if direction == "CW" else 1.0
    center_x, center_y = center
    return [
        (
            center_x
            + RADIUS_MM
            * math.cos(
                math.pi / 2.0
                + sign * 2.0 * math.pi * index / SEGMENTS
            ),
            center_y
            + RADIUS_MM
            * math.sin(
                math.pi / 2.0
                + sign * 2.0 * math.pi * index / SEGMENTS
            ),
        )
        for index in range(SEGMENTS + 1)
    ]


def tangent_preload(
    start: tuple[float, float],
    direction: str,
) -> tuple[tuple[float, float], tuple[float, float]]:
    tangent_x = 1.0 if direction == "CW" else -1.0
    far = (
        start[0] - tangent_x * 2.0 * TANGENT_PRELOAD_MM,
        start[1],
    )
    near = (
        start[0] - tangent_x * TANGENT_PRELOAD_MM,
        start[1],
    )
    return far, near


def generate() -> tuple[str, dict]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware={BUILD_ID}",
        "; firmware_paper_map=DISABLED direct_user_coordinates=1",
        "; placement=TOP_BLANK nominal_paper_row_y=230",
        "; circle=D18 segments=72 start=TOP feed=F180",
        "; every_pass_has_same_direction_tangent_penup_preload",
        "; LEFT=CW_x2 MIDDLE=CCW_x2 RIGHT=CW_then_CCW",
        "G21",
        "G90",
        "G94",
        f"F{FEED_MM_MIN}",
        "S1000",
        "M5",
    ]
    groups: list[dict] = []
    for group_name, paper_center, directions in NOMINAL_GROUPS:
        center = map_center(paper_center)
        pass_records: list[dict] = []
        for pass_index, direction in enumerate(directions, start=1):
            points = circle_points(center, direction)
            far, near = tangent_preload(points[0], direction)
            lines.extend(
                (
                    f"; {group_name}_PASS{pass_index}_{direction} "
                    f"paper_center=({paper_center[0]:.3f},"
                    f"{paper_center[1]:.3f}) "
                    f"user_center=({center[0]:.3f},{center[1]:.3f})",
                    "M5",
                    f"G0 X{far[0]:.3f} Y{far[1]:.3f}",
                    f"G0 X{near[0]:.3f} Y{near[1]:.3f}",
                    f"G0 X{points[0][0]:.3f} Y{points[0][1]:.3f}",
                    "M3",
                )
            )
            lines.extend(
                f"G1 X{x:.3f} Y{y:.3f}" for x, y in points[1:]
            )
            lines.append("M5")
            pass_records.append(
                {
                    "pass": pass_index,
                    "direction": direction,
                    "tangent_preload_user_mm": [list(far), list(near)],
                    "start_user_mm": list(points[0]),
                }
            )
        groups.append(
            {
                "name": group_name,
                "nominal_paper_center_mm": list(paper_center),
                "command_user_center_mm": list(center),
                "directions": list(directions),
                "passes": pass_records,
            }
        )
    text = "\n".join(lines) + "\n"
    manifest = {
        "test_id": TEST_ID,
        "required_firmware": BUILD_ID,
        "firmware_paper_map_enabled": False,
        "coordinate_contract": "mapped_center_then_direct_user_circle",
        "diameter_mm": 2.0 * RADIUS_MM,
        "segments_per_circle": SEGMENTS,
        "feed_mm_min": FEED_MM_MIN,
        "start_location": "TOP",
        "tangent_penup_preload_mm": TANGENT_PRELOAD_MM,
        "groups": groups,
        "decision": {
            "same_direction_overlaps_but_cw_ccw_splits": (
                "deterministic_direction_dependent_hysteresis_or_compliance"
            ),
            "same_direction_also_splits": (
                "random_step_loss_loose_mechanics_or_repeatability_fault"
            ),
            "all_six_traces_overlap_but_shape_is_oval": (
                "direction_effect_not_primary_check_kinematics_or_mapping"
            ),
        },
        "gcode_sha256": hashlib.sha256(text.encode("ascii")).hexdigest(),
    }
    return text, manifest


def preview() -> None:
    scale = 4
    margin = 24
    image = Image.new(
        "RGB",
        (210 * scale + 2 * margin, 297 * scale + 2 * margin),
        "white",
    )
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (margin, margin, margin + 210 * scale, margin + 297 * scale),
        outline=(80, 80, 80),
        width=2,
    )

    def pixel(point: tuple[float, float]) -> tuple[int, int]:
        return (
            int(round(margin + point[0] * scale)),
            int(round(margin + (297.0 - point[1]) * scale)),
        )

    colors = ((0, 80, 210), (215, 45, 35))
    for group_name, center, directions in NOMINAL_GROUPS:
        for pass_index, direction in enumerate(directions):
            sign = -1.0 if direction == "CW" else 1.0
            points = [
                (
                    center[0]
                    + RADIUS_MM
                    * math.cos(
                        math.pi / 2.0
                        + sign * 2.0 * math.pi * index / SEGMENTS
                    ),
                    center[1]
                    + RADIUS_MM
                    * math.sin(
                        math.pi / 2.0
                        + sign * 2.0 * math.pi * index / SEGMENTS
                    ),
                )
                for index in range(SEGMENTS + 1)
            ]
            draw.line(
                [pixel(point) for point in points],
                fill=colors[pass_index],
                width=2,
            )
        draw.text(
            pixel((center[0] - 15.0, center[1] - 16.0)),
            group_name,
            fill=(20, 20, 20),
        )
    image.save(PREVIEW_PATH)


def main() -> None:
    text, manifest = generate()
    GCODE_PATH.write_text(text, encoding="ascii", newline="\n")
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    preview()
    print(GCODE_PATH)
    print(MANIFEST_PATH)
    print(PREVIEW_PATH)


if __name__ == "__main__":
    main()
