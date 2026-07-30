#!/usr/bin/env python3
"""Generate the V38 direction overlay and V39 local-scale cross tests."""

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
BUILD_ID = "PAPER_A4_CONTINUOUS_QUEUE_SAFE_HOME_GCODE_V27"
FEED_MM_MIN = 180

OVERLAY_ID = "PAPER_A4_SAME_CENTER_CW_CCW_OVERLAY_D18_GCODE_V38"
OVERLAY_GCODE = ROOT / "gcode" / f"{OVERLAY_ID}.gcode"
OVERLAY_MANIFEST = ROOT / "gcode" / f"{OVERLAY_ID}.json"
OVERLAY_PREVIEW = (
    ROOT / "docs" / "diagnostics" / f"{OVERLAY_ID}_PREVIEW.png"
)
OVERLAY_PAPER_CENTER = (175.0, 215.0)
OVERLAY_RADIUS_MM = 9.0
OVERLAY_SEGMENTS = 72

CROSS_ID = "PAPER_A4_LEFT_MID_RIGHT_CROSS20_GCODE_V39"
CROSS_GCODE = ROOT / "gcode" / f"{CROSS_ID}.gcode"
CROSS_MANIFEST = ROOT / "gcode" / f"{CROSS_ID}.json"
CROSS_PREVIEW = (
    ROOT / "docs" / "diagnostics" / f"{CROSS_ID}_PREVIEW.png"
)
CROSS_PAPER_CENTERS = (
    ("LEFT", 45.0, 185.0),
    ("MIDDLE", 105.0, 185.0),
    ("RIGHT", 165.0, 185.0),
)
CROSS_LENGTH_MM = 20.0

PAPER_CROSS_ID = "PAPER_A4_LEFT_MID_RIGHT_PAPER_AXIS_CROSS20_GCODE_V40"
PAPER_CROSS_GCODE = ROOT / "gcode" / f"{PAPER_CROSS_ID}.gcode"
PAPER_CROSS_MANIFEST = ROOT / "gcode" / f"{PAPER_CROSS_ID}.json"
PAPER_CROSS_PREVIEW = (
    ROOT / "docs" / "diagnostics" / f"{PAPER_CROSS_ID}_PREVIEW.png"
)
PAPER_CROSS_POINT_STEP_MM = 1.0
PAPER_CROSS_CENTERS = (
    ("LEFT", 35.0, 215.0),
    ("MIDDLE", 90.0, 215.0),
    ("RIGHT", 145.0, 215.0),
)

MAP_COEFFICIENTS, MAP_TOTAL_DELTA = mapping_model()


def command_center(
    paper_center: tuple[float, float],
) -> tuple[float, float]:
    result = mapped(
        paper_center,
        MAP_COEFFICIENTS,
        MAP_TOTAL_DELTA,
    )
    return float(result[0]), float(result[1])


def circle_points(
    center: tuple[float, float],
    clockwise: bool,
) -> list[tuple[float, float]]:
    direction = -1.0 if clockwise else 1.0
    center_x, center_y = center
    return [
        (
            center_x
            + OVERLAY_RADIUS_MM
            * math.cos(
                math.pi / 2.0
                + direction * 2.0 * math.pi * index
                / OVERLAY_SEGMENTS
            ),
            center_y
            + OVERLAY_RADIUS_MM
            * math.sin(
                math.pi / 2.0
                + direction * 2.0 * math.pi * index
                / OVERLAY_SEGMENTS
            ),
        )
        for index in range(OVERLAY_SEGMENTS + 1)
    ]


def overlay_gcode() -> tuple[str, dict]:
    center = command_center(OVERLAY_PAPER_CENTER)
    lines = [
        f"; {OVERLAY_ID}",
        f"; firmware={BUILD_ID}",
        "; paper_map=DISABLED direct_user_coordinates=1",
        "; placement=UPPER_RIGHT nominal_paper_center=(175,215)",
        "; purpose=same_center_same_start_CW_vs_CCW_overlay",
        "G21",
        "G90",
        "G94",
        f"F{FEED_MM_MIN}",
        "S1000",
        "M5",
    ]
    records = []
    for name, clockwise in (("PASS1_CW", True), ("PASS2_CCW", False)):
        points = circle_points(center, clockwise)
        start_x, start_y = points[0]
        lines.extend(
            (
                f"; {name} center=({center[0]:.3f},{center[1]:.3f}) "
                f"direction={'CW' if clockwise else 'CCW'}",
                f"G0 X{start_x:.3f} Y{start_y:.3f}",
                "M3",
            )
        )
        lines.extend(
            f"G1 X{x:.3f} Y{y:.3f}" for x, y in points[1:]
        )
        lines.append("M5")
        records.append(
            {
                "name": name,
                "direction": "CW" if clockwise else "CCW",
                "command_user_center_mm": list(center),
                "start_user_mm": list(points[0]),
            }
        )
    text = "\n".join(lines) + "\n"
    manifest = {
        "test_id": OVERLAY_ID,
        "required_firmware": BUILD_ID,
        "paper_map_enabled": False,
        "nominal_paper_center_mm": list(OVERLAY_PAPER_CENTER),
        "command_user_center_mm": list(center),
        "diameter_mm": 2.0 * OVERLAY_RADIUS_MM,
        "segments_per_circle": OVERLAY_SEGMENTS,
        "feed_mm_min": FEED_MM_MIN,
        "passes": records,
        "decision": {
            "two_traces_split": "direction_backlash_drag_or_step_loss",
            "two_traces_overlap_but_oval": "kinematic_calibration_error",
        },
        "gcode_sha256": hashlib.sha256(text.encode("ascii")).hexdigest(),
    }
    return text, manifest


def cross_gcode() -> tuple[str, dict]:
    half = CROSS_LENGTH_MM / 2.0
    lines = [
        f"; {CROSS_ID}",
        f"; firmware={BUILD_ID}",
        "; paper_map=DISABLED direct_user_coordinates=1",
        "; placement=UPPER_BLANK nominal_paper_row_y=185",
        "; purpose=raw_user_basis_not_paper_XY_or_paper_20mm",
        "; horizontal=LEFT_TO_RIGHT vertical=BOTTOM_TO_TOP",
        "G21",
        "G90",
        "G94",
        f"F{FEED_MM_MIN}",
        "S1000",
        "M5",
    ]
    records = []
    for name, paper_x, paper_y in CROSS_PAPER_CENTERS:
        center_x, center_y = command_center((paper_x, paper_y))
        strokes = (
            (
                "HORIZONTAL",
                (center_x - half, center_y),
                (center_x + half, center_y),
            ),
            (
                "VERTICAL",
                (center_x, center_y - half),
                (center_x, center_y + half),
            ),
        )
        for axis, start, end in strokes:
            lines.extend(
                (
                    f"; {name}_{axis} nominal_paper_center="
                    f"({paper_x:.3f},{paper_y:.3f}) "
                    f"command_user_center=({center_x:.3f},{center_y:.3f})",
                    f"G0 X{start[0]:.3f} Y{start[1]:.3f}",
                    "M3",
                    f"G1 X{end[0]:.3f} Y{end[1]:.3f}",
                    "M5",
                )
            )
        records.append(
            {
                "name": name,
                "nominal_paper_center_mm": [paper_x, paper_y],
                "command_user_center_mm": [center_x, center_y],
                "horizontal_user_mm": [
                    list(strokes[0][1]),
                    list(strokes[0][2]),
                ],
                "vertical_user_mm": [
                    list(strokes[1][1]),
                    list(strokes[1][2]),
                ],
            }
        )
    text = "\n".join(lines) + "\n"
    manifest = {
        "test_id": CROSS_ID,
        "required_firmware": BUILD_ID,
        "paper_map_enabled": False,
        "coordinate_contract": "raw_user_basis_not_paper_axes",
        "nominal_paper_row_y_mm": CROSS_PAPER_CENTERS[0][2],
        "raw_user_stroke_length_mm": CROSS_LENGTH_MM,
        "feed_mm_min": FEED_MM_MIN,
        "crosses": records,
        "decision": {
            "length_changes_by_position": "kinematic_jacobian_error",
            "fixed_scale_error_everywhere": "global_steps_per_degree_error",
            "forward_reverse_length_diff": "mechanical_backlash",
        },
        "gcode_sha256": hashlib.sha256(text.encode("ascii")).hexdigest(),
    }
    return text, manifest


def paper_axis_cross_gcode() -> tuple[str, dict]:
    half = CROSS_LENGTH_MM / 2.0
    point_count = int(round(CROSS_LENGTH_MM / PAPER_CROSS_POINT_STEP_MM)) + 1
    lines = [
        f"; {PAPER_CROSS_ID}",
        f"; firmware={BUILD_ID}",
        "; firmware_paper_map=DISABLED",
        "; offline_pointwise_paper_to_user_map=ENABLED",
        "; placement=UPPER_BLANK nominal_paper_row_y=215",
        "; purpose=true_paper_XY_axis_and_20mm_length",
        "; each_20mm_stroke=20_segments point_step=1mm",
        "; horizontal=paper_left_to_right vertical=paper_bottom_to_top",
        "G21",
        "G90",
        "G94",
        f"F{FEED_MM_MIN}",
        "S1000",
        "M5",
    ]
    records = []
    for name, paper_x, paper_y in PAPER_CROSS_CENTERS:
        paper_strokes = (
            (
                "HORIZONTAL",
                [
                    (
                        paper_x - half
                        + index * PAPER_CROSS_POINT_STEP_MM,
                        paper_y,
                    )
                    for index in range(point_count)
                ],
            ),
            (
                "VERTICAL",
                [
                    (
                        paper_x,
                        paper_y - half
                        + index * PAPER_CROSS_POINT_STEP_MM,
                    )
                    for index in range(point_count)
                ],
            ),
        )
        stroke_records = []
        for axis, paper_points in paper_strokes:
            user_points = [
                command_center(point) for point in paper_points
            ]
            lines.extend(
                (
                    f"; {name}_{axis} nominal_paper_center="
                    f"({paper_x:.3f},{paper_y:.3f}) "
                    f"paper_length={CROSS_LENGTH_MM:.3f}",
                    f"G0 X{user_points[0][0]:.3f} "
                    f"Y{user_points[0][1]:.3f}",
                    "M3",
                )
            )
            lines.extend(
                f"G1 X{point[0]:.3f} Y{point[1]:.3f}"
                for point in user_points[1:]
            )
            lines.append("M5")
            stroke_records.append(
                {
                    "axis": axis,
                    "paper_points_mm": [
                        list(point) for point in paper_points
                    ],
                    "command_user_points_mm": [
                        list(point) for point in user_points
                    ],
                }
            )
        records.append(
            {
                "name": name,
                "nominal_paper_center_mm": [paper_x, paper_y],
                "strokes": stroke_records,
            }
        )
    text = "\n".join(lines) + "\n"
    manifest = {
        "test_id": PAPER_CROSS_ID,
        "required_firmware": BUILD_ID,
        "firmware_paper_map_enabled": False,
        "offline_pointwise_paper_to_user_map_enabled": True,
        "nominal_paper_row_y_mm": PAPER_CROSS_CENTERS[0][2],
        "stroke_length_mm": CROSS_LENGTH_MM,
        "paper_point_step_mm": PAPER_CROSS_POINT_STEP_MM,
        "segments_per_stroke": point_count - 1,
        "feed_mm_min": FEED_MM_MIN,
        "crosses": records,
        "gcode_sha256": hashlib.sha256(text.encode("ascii")).hexdigest(),
    }
    return text, manifest


def write_case(path: Path, manifest_path: Path, text: str, data: dict) -> None:
    path.write_text(text, encoding="ascii", newline="\n")
    manifest_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def preview_base() -> tuple[Image.Image, ImageDraw.ImageDraw]:
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
    return image, draw


def preview_pixel(point: tuple[float, float]) -> tuple[int, int]:
    scale = 4
    margin = 24
    return (
        int(round(margin + point[0] * scale)),
        int(round(margin + (297.0 - point[1]) * scale)),
    )


def draw_previews() -> None:
    image, draw = preview_base()
    center = OVERLAY_PAPER_CENTER
    for clockwise, color in ((True, (0, 70, 190)), (False, (210, 40, 30))):
        points = [
            (
                center[0]
                + OVERLAY_RADIUS_MM
                * math.cos(
                    math.pi / 2.0
                    + (-1.0 if clockwise else 1.0)
                    * 2.0 * math.pi * index / OVERLAY_SEGMENTS
                ),
                center[1]
                + OVERLAY_RADIUS_MM
                * math.sin(
                    math.pi / 2.0
                    + (-1.0 if clockwise else 1.0)
                    * 2.0 * math.pi * index / OVERLAY_SEGMENTS
                ),
            )
            for index in range(OVERLAY_SEGMENTS + 1)
        ]
        draw.line(
            [preview_pixel(point) for point in points],
            fill=color,
            width=2,
        )
    draw.text(
        preview_pixel((82.0, 50.0)),
        "same center: blue=CW red=CCW",
        fill=(20, 20, 20),
    )
    image.save(OVERLAY_PREVIEW)

    image, draw = preview_base()
    half = CROSS_LENGTH_MM / 2.0
    for name, x, y in CROSS_PAPER_CENTERS:
        draw.line(
            (preview_pixel((x - half, y)), preview_pixel((x + half, y))),
            fill=(0, 0, 0),
            width=2,
        )
        draw.line(
            (preview_pixel((x, y - half)), preview_pixel((x, y + half))),
            fill=(0, 0, 0),
            width=2,
        )
        draw.text(preview_pixel((x - 9.0, y - 16.0)), name, fill=(0, 70, 160))
    image.save(CROSS_PREVIEW)

    image, draw = preview_base()
    half = CROSS_LENGTH_MM / 2.0
    for name, x, y in PAPER_CROSS_CENTERS:
        draw.line(
            (preview_pixel((x - half, y)), preview_pixel((x + half, y))),
            fill=(0, 0, 0),
            width=2,
        )
        draw.line(
            (preview_pixel((x, y - half)), preview_pixel((x, y + half))),
            fill=(0, 0, 0),
            width=2,
        )
        draw.text(
            preview_pixel((x - 15.0, y - 16.0)),
            f"{name} PAPER XY",
            fill=(0, 70, 160),
        )
    image.save(PAPER_CROSS_PREVIEW)


def main() -> None:
    overlay_text, overlay_manifest = overlay_gcode()
    cross_text, cross_manifest = cross_gcode()
    paper_cross_text, paper_cross_manifest = paper_axis_cross_gcode()
    write_case(
        OVERLAY_GCODE,
        OVERLAY_MANIFEST,
        overlay_text,
        overlay_manifest,
    )
    write_case(CROSS_GCODE, CROSS_MANIFEST, cross_text, cross_manifest)
    write_case(
        PAPER_CROSS_GCODE,
        PAPER_CROSS_MANIFEST,
        paper_cross_text,
        paper_cross_manifest,
    )
    draw_previews()
    for path in (
        OVERLAY_GCODE,
        OVERLAY_MANIFEST,
        OVERLAY_PREVIEW,
        CROSS_GCODE,
        CROSS_MANIFEST,
        CROSS_PREVIEW,
        PAPER_CROSS_GCODE,
        PAPER_CROSS_MANIFEST,
        PAPER_CROSS_PREVIEW,
    ):
        print(path)


if __name__ == "__main__":
    main()
