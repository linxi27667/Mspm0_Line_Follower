#!/usr/bin/env python3
"""Generate V53 text in the retained upper writing rows for V28."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

import generate_paper_a4_top_left_meiyou_ruguo_9mm_v45 as engine
from check_workspace_yshift15_v28 import (
    BUILD_ID,
    L1_MM,
    L2_MM,
    OFFSET_X_MM,
    OFFSET_Y_MM,
    PSI_MIN_DEG,
    SHIFT_X_MM,
    SHIFT_Y_MM,
    THETA_MIN_DEG,
    joint_margin,
)
from generate_paper_a4_3x3_baseonly_direction_v49 import map_base_only


ROOT = Path(__file__).resolve().parents[1]
TEST_ID = "PAPER_A4_UPPER_ROW_XIKOU_WUMAI_9MM_ZHANGJIALE_V53"
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"

FONT_PATH = (
    ROOT
    / "assets"
    / "kenjoy_gfont"
    / "XIKOU_WUMAI_YAYA_JING_1d6c6baa.gfont"
)
FONT_SHA256 = (
    "9377ADD7793C0B7965E21E6B7660DD6E1B6A90EE455DA076E36FB8D483C14B3A"
)
FONT_NAME = "\u5438\u53e3\u96fe\u973e\u538b\u538b\u60ca"
FONT_TAG = "XIKOU_WUMAI_YAYA_JING"
FONT_EM_SIZE = 400
TEXT = "\u5f20\u4f73\u4e50\u4f5c\u54c1"
EXPECTED_STROKE_COUNTS = (10, 10, 7, 5, 12)

VISIBLE_HEIGHT_MM = 9.0
CHARACTER_GAP_MM = 1.875
CONTENT_LEFT_MM = 30.0
CONTENT_TOP_LOGICAL_MM = 220.0
TANGENT_APPROACH_MM = 1.875
PAPER_SUBDIVISION_MM = 0.4
FEED_MM_MIN = 150

# The former third row is intentionally excluded from production writing.
NOMINAL_PHYSICAL_WRITING_Y_MIN_MM = 110.0
NOMINAL_PHYSICAL_WRITING_Y_MAX_MM = 240.0


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
    engine.VISIBLE_HEIGHT_MM = VISIBLE_HEIGHT_MM
    engine.CHARACTER_GAP_MM = CHARACTER_GAP_MM
    engine.CONTENT_LEFT_MM = CONTENT_LEFT_MM
    engine.CONTENT_TOP_MM = CONTENT_TOP_LOGICAL_MM
    engine.TANGENT_APPROACH_MM = TANGENT_APPROACH_MM
    engine.PAPER_SUBDIVISION_MM = PAPER_SUBDIVISION_MM
    engine.FEED_MM_MIN = FEED_MM_MIN


def nominal_physical_paper(
    point: tuple[float, float],
) -> tuple[float, float]:
    return point[0], point[1] + SHIFT_Y_MM


def command_plan(
    layout: engine.shared.Layout,
) -> tuple[
    tuple[
        engine.shared.Stroke,
        tuple[tuple[float, float], ...],
        tuple[tuple[float, float], ...],
    ],
    ...,
]:
    return tuple(
        (
            stroke,
            paper_points,
            tuple(map_base_only(point) for point in paper_points),
        )
        for stroke in layout.strokes
        for paper_points in (engine.subdivide_points(stroke.points),)
    )


def gcode_lines(layout: engine.shared.Layout) -> tuple[str, ...]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware_required={BUILD_ID}",
        "; WARNING=DO_NOT_SEND_TO_V27_OR_OLDER",
        f"; source_font={FONT_PATH.name} font_sha256={FONT_SHA256}",
        f"; text=ZHANG_JIA_LE_ZUO_PIN font={FONT_TAG}",
        "; source_geometry=UNMODIFIED_GFONT",
        "; production_rows=UPPER_AND_MIDDLE third_row=DISCARDED",
        f"; placement=UPPER_LEFT logical_top={CONTENT_TOP_LOGICAL_MM:.1f}mm "
        f"nominal_physical_top={CONTENT_TOP_LOGICAL_MM + SHIFT_Y_MM:.1f}mm",
        f"; visible_height={VISIBLE_HEIGHT_MM:.1f}mm "
        f"gap={CHARACTER_GAP_MM:.3f}mm",
        "; map=BASE_QUADRATIC_ONLY old_grid4x7_residual=DISABLED",
        "; v51_photo_quadratic=DISABLED",
        "; firmware_paper_map=DISABLED firmware_global_y_shift=+15mm",
        f"; paper_subdivision_max={PAPER_SUBDIVISION_MM:.1f}mm",
        "G21",
        "G90",
        "G94",
        f"F{FEED_MM_MIN}",
        "S1000",
        "M5",
    ]
    for stroke, _, user_points in command_plan(layout):
        approach = map_base_only(stroke.approach)
        lines.extend(
            (
                f"; char_index={stroke.character_index + 1} "
                f"stroke={stroke.stroke_index}",
                f"G0 X{approach[0]:.3f} Y{approach[1]:.3f}",
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
    return tuple(lines)


def home_user() -> tuple[float, float]:
    theta = math.radians(THETA_MIN_DEG)
    psi = math.radians(PSI_MIN_DEG)
    machine_x = -L1_MM * math.cos(theta) - L2_MM * math.cos(psi)
    machine_y = L1_MM * math.sin(theta) + L2_MM * math.sin(psi)
    return machine_x - OFFSET_X_MM, machine_y - OFFSET_Y_MM


def audit(
    layout: engine.shared.Layout,
) -> dict:
    ordered_targets: list[tuple[float, float]] = []
    physical_paper_points: list[tuple[float, float]] = []
    for stroke, paper_points, user_points in command_plan(layout):
        ordered_targets.append(
            (
                map_base_only(stroke.approach)[0] + SHIFT_X_MM,
                map_base_only(stroke.approach)[1] + SHIFT_Y_MM,
            )
        )
        ordered_targets.extend(
            (point[0] + SHIFT_X_MM, point[1] + SHIFT_Y_MM)
            for point in user_points
        )
        physical_paper_points.extend(
            nominal_physical_paper(point) for point in paper_points
        )
        physical_paper_points.append(
            nominal_physical_paper(stroke.approach)
        )

    min_physical_y = min(point[1] for point in physical_paper_points)
    max_physical_y = max(point[1] for point in physical_paper_points)
    if not (
        NOMINAL_PHYSICAL_WRITING_Y_MIN_MM <= min_physical_y
        and max_physical_y <= NOMINAL_PHYSICAL_WRITING_Y_MAX_MM
    ):
        raise AssertionError(
            f"V53 left upper/middle writing rows: "
            f"{min_physical_y:.3f}..{max_physical_y:.3f}"
        )

    previous = home_user()
    worst = (float("inf"), (0.0, 0.0), (0.0, 0.0, 0.0))
    sample_count = 0
    for target in ordered_targets:
        count = max(1, math.ceil(math.dist(previous, target)))
        for index in range(1, count + 1):
            ratio = index / count
            sample = (
                previous[0] + (target[0] - previous[0]) * ratio,
                previous[1] + (target[1] - previous[1]) * ratio,
            )
            margin, angles = joint_margin(sample)
            if margin < worst[0]:
                worst = (margin, sample, angles)
            sample_count += 1
        previous = target
    if worst[0] < -0.001:
        raise AssertionError(
            f"V53 path violates joint limits: {worst}"
        )
    return {
        "path_sample_count": sample_count,
        "minimum_joint_margin_deg": worst[0],
        "minimum_at_shifted_user_mm": list(worst[1]),
        "minimum_at_angles_deg": list(worst[2]),
        "nominal_physical_paper_y_bounds_mm": [
            min_physical_y,
            max_physical_y,
        ],
    }


def write_preview(layout: engine.shared.Layout) -> None:
    width = round(engine.shared.A4_WIDTH_MM * 4.0) + 1
    height = round(engine.shared.A4_HEIGHT_MM * 4.0) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (0, 0, width - 1, height - 1),
        outline=(25, 25, 25),
        width=3,
    )
    # Retained upper/middle writing area.
    draw.rectangle(
        (
            *engine.shared.preview_xy(
                (25.0, NOMINAL_PHYSICAL_WRITING_Y_MAX_MM)
            ),
            *engine.shared.preview_xy(
                (185.0, NOMINAL_PHYSICAL_WRITING_Y_MIN_MM)
            ),
        ),
        outline=(75, 145, 95),
        width=2,
    )
    draw.text(
        (20, 16),
        "V53 upper-row 9 mm original-gfont writing sample",
        fill=(20, 20, 20),
        font=engine.shared.label_font(20),
    )
    draw.text(
        (20, 47),
        "V28 +15 mm global shift; lower third row excluded",
        fill=(70, 70, 70),
        font=engine.shared.label_font(16),
    )
    for stroke in layout.strokes:
        approach = engine.shared.preview_xy(
            nominal_physical_paper(stroke.approach)
        )
        start = engine.shared.preview_xy(
            nominal_physical_paper(stroke.points[0])
        )
        engine.shared.draw_dashed_line(
            draw, approach, start, (45, 115, 185), width=2
        )
        draw.line(
            [
                engine.shared.preview_xy(
                    nominal_physical_paper(point)
                )
                for point in stroke.points
            ],
            fill=(15, 15, 15),
            width=2,
            joint="curve",
        )
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def write_manifest(
    layout: engine.shared.Layout,
    lines: tuple[str, ...],
    safety: dict,
) -> None:
    plan = command_plan(layout)
    text = "\n".join(lines) + "\n"
    manifest = {
        "id": TEST_ID,
        "required_firmware": BUILD_ID,
        "text": TEXT,
        "font": {
            "file": FONT_PATH.name,
            "sha256": FONT_SHA256,
            "name": FONT_NAME,
            "em_size": FONT_EM_SIZE,
            "geometry": "unmodified gfont path points and command order",
            "character_path_counts": list(EXPECTED_STROKE_COUNTS),
        },
        "workspace_policy": {
            "retained_rows": ["UPPER", "MIDDLE"],
            "discarded_rows": ["LOWER"],
            "nominal_physical_y_mm": [
                NOMINAL_PHYSICAL_WRITING_Y_MIN_MM,
                NOMINAL_PHYSICAL_WRITING_Y_MAX_MM,
            ],
        },
        "layout": {
            "logical_content_left_mm": CONTENT_LEFT_MM,
            "logical_content_top_mm": CONTENT_TOP_LOGICAL_MM,
            "nominal_physical_content_top_mm": (
                CONTENT_TOP_LOGICAL_MM + SHIFT_Y_MM
            ),
            "visible_height_mm": VISIBLE_HEIGHT_MM,
            "character_gap_mm": CHARACTER_GAP_MM,
            "logical_bounds_with_approaches_mm": list(layout.bounds_mm),
            "nominal_physical_bounds_with_approaches_mm": [
                layout.bounds_mm[0],
                layout.bounds_mm[1] + SHIFT_Y_MM,
                layout.bounds_mm[2],
                layout.bounds_mm[3] + SHIFT_Y_MM,
            ],
        },
        "mapping": {
            "base_quadratic_enabled": True,
            "old_grid4x7_residual_enabled": False,
            "v51_photo_quadratic_enabled": False,
            "firmware_paper_map_enabled": False,
            "firmware_global_translation_user_mm": [
                SHIFT_X_MM,
                SHIFT_Y_MM,
            ],
        },
        "motion": {
            "feed_mm_min": FEED_MM_MIN,
            "tangent_approach_mm": TANGENT_APPROACH_MM,
            "paper_subdivision_max_mm": PAPER_SUBDIVISION_MM,
            "stroke_count": len(layout.strokes),
            "g1_count": sum(
                len(user_points) - 1 for _, _, user_points in plan
            ),
        },
        "safety": safety,
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


def main() -> None:
    configure_engine()
    layout = engine.build_layout()
    safety = audit(layout)
    lines = gcode_lines(layout)
    GCODE_PATH.write_text(
        "\n".join(lines) + "\n",
        encoding="ascii",
        newline="\n",
    )
    write_preview(layout)
    write_manifest(layout, lines, safety)
    plan = command_plan(layout)
    print(
        "generated_paper_a4_upper_rows_xikou_9mm_v53=PASS "
        f"characters={len(TEXT)} strokes={len(layout.strokes)} "
        f"G1={sum(len(points) - 1 for _, _, points in plan)} "
        f"logical_bounds=({layout.bounds_mm[0]:.3f},"
        f"{layout.bounds_mm[1]:.3f}).."
        f"({layout.bounds_mm[2]:.3f},{layout.bounds_mm[3]:.3f}) "
        f"physical_y={safety['nominal_physical_paper_y_bounds_mm'][0]:.3f}"
        f"..{safety['nominal_physical_paper_y_bounds_mm'][1]:.3f} "
        f"min_joint_margin={safety['minimum_joint_margin_deg']:.6f}deg"
    )
    print(GCODE_PATH)
    print(PREVIEW_PATH)
    print(MANIFEST_PATH)


if __name__ == "__main__":
    main()
