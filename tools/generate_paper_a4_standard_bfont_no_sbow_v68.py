#!/usr/bin/env python3
"""Generate the single-variable V31 no-S-bow B-font verification row."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import generate_paper_a4_standard_upper_bfont_6mm_v65 as base
from check_firmware_no_sbow_v31 import firmware_map_no_sbow
from check_workspace_yshift15_v28 import joint_margin
from generate_paper_a4_full_width_square_spiral_v59 import home_user
from generate_paper_a4_zhang_jia_le_v30 import (
    A4_HEIGHT_MM,
    A4_WIDTH_MM,
    CharacterLayout,
    Layout,
    Stroke,
    label_font,
    preview_xy,
)


TEST_ID = "PAPER_A4_STANDARD_BFONT_6MM_NO_SBOW_VERIFY_GCODE_V68"
FIRMWARE_ID = "PAPER_A4_STANDARD_GCODE_NO_SBOW_PAPERMAP_YSHIFT15_V31"
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"

CONTENT_TOP_MM = 202.0
SOURCE_TOP_MM = base.CONTENT_TOP_MM
TRANSLATE_Y_MM = CONTENT_TOP_MM - SOURCE_TOP_MM


def translated_layout() -> Layout:
    source = base.build_layout()

    def point_xy(point: tuple[float, float]) -> tuple[float, float]:
        return point[0], point[1] + TRANSLATE_Y_MM

    characters = tuple(
        CharacterLayout(
            character.character,
            (
                character.bounds_mm[0],
                character.bounds_mm[1] + TRANSLATE_Y_MM,
                character.bounds_mm[2],
                character.bounds_mm[3] + TRANSLATE_Y_MM,
            ),
            character.stroke_count,
        )
        for character in source.characters
    )
    strokes = tuple(
        Stroke(
            stroke.character,
            stroke.character_index,
            stroke.stroke_index,
            point_xy(stroke.approach),
            tuple(point_xy(point) for point in stroke.points),
        )
        for stroke in source.strokes
    )
    bounds = (
        source.bounds_mm[0],
        source.bounds_mm[1] + TRANSLATE_Y_MM,
        source.bounds_mm[2],
        source.bounds_mm[3] + TRANSLATE_Y_MM,
    )
    for stroke in strokes:
        for point in (stroke.approach, *stroke.points):
            if not (
                base.PAPER_X_MIN_MM <= point[0] <= base.PAPER_X_MAX_MM
                and base.PAPER_Y_MIN_MM <= point[1] <= base.PAPER_Y_MAX_MM
            ):
                raise AssertionError(f"V68 point out of bounds: {point}")
    return Layout(
        source.font,
        source.scale_mm_per_unit,
        characters,
        strokes,
        bounds,
    )


def gcode_lines(layout: Layout) -> tuple[str, ...]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware_required={FIRMWARE_ID}",
        "; coordinates=STANDARD_A4_PHYSICAL_PAPER_MM",
        "; offline_mapping=NONE offline_prewarp=NONE",
        f"; source_font={base.FONT_PATH.name} sha256={base.FONT_SHA256}",
        "; font_option=B source_geometry=UNMODIFIED_GFONT_TRANSLATED_ONLY",
        "; requested_text=WRITER_TEST_COUNT_7.25__5.23am",
        "; ASCII_PERIOD_DISPLAYED_WITH_ORIGINAL_GFONT_U3002=YES",
        "; visible_height=6mm placement=UPPER_VALIDATED_BAND_ROW_Y202",
        "; single_variable=FIRMWARE_MEASURED_SBOW_OFF",
        "; firmware_owns=BASE_QUADRATIC,X_SCALE,YSHIFT15",
        "G21",
        "G90",
        "G94",
        f"F{base.FEED_MM_MIN}",
        "S1000",
        "M5",
    ]
    for stroke in layout.strokes:
        lines.extend(
            (
                f"; char={stroke.character_index + 1} "
                f"stroke={stroke.stroke_index}",
                f"G0 X{stroke.approach[0]:.3f} "
                f"Y{stroke.approach[1]:.3f}",
                f"G0 X{stroke.points[0][0]:.3f} "
                f"Y{stroke.points[0][1]:.3f}",
                "M3",
            )
        )
        lines.extend(
            f"G1 X{point[0]:.3f} Y{point[1]:.3f}"
            for point in stroke.points[1:]
        )
        lines.append("M5")
    lines.append("M5")
    return tuple(lines)


def audit(layout: Layout, lines: tuple[str, ...]) -> dict[str, object]:
    previous_user = home_user()
    worst = (float("inf"), (0.0, 0.0))
    safe_samples = 0

    def check_user(target_user: tuple[float, float]) -> None:
        nonlocal previous_user, worst, safe_samples
        for sample in base.user_line_samples(previous_user, target_user, 1.0):
            margin, _ = joint_margin(sample)
            if margin < worst[0]:
                worst = (margin, sample)
            safe_samples += 1
        previous_user = target_user

    for stroke in layout.strokes:
        check_user(firmware_map_no_sbow(stroke.approach))
        check_user(firmware_map_no_sbow(stroke.points[0]))
        previous_paper = stroke.points[0]
        for target_paper in stroke.points[1:]:
            for paper_sample in base.paper_line_samples(
                previous_paper, target_paper
            ):
                check_user(firmware_map_no_sbow(paper_sample))
            previous_paper = target_paper

    if worst[0] < -0.001:
        raise AssertionError(f"V31/V68 path violates joint limits: {worst}")
    if any(len(line) >= 192 for line in lines):
        raise AssertionError("V68 contains an overlong serial line")
    return {
        "safe_samples": safe_samples,
        "min_joint_margin_deg": worst[0],
        "min_margin_user_mm": list(worst[1]),
        "motion_line_count": sum(
            line.startswith(("G0 ", "G1 ")) for line in lines
        ),
        "stroke_count": len(layout.strokes),
    }


def write_preview(layout: Layout) -> None:
    pixels_per_mm = base.PREVIEW_PIXELS_PER_MM
    width = round(A4_WIDTH_MM * pixels_per_mm) + 1
    height = round(A4_HEIGHT_MM * pixels_per_mm) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, height - 1), outline=(30, 30, 30), width=3)
    draw.rectangle(
        (
            round(base.PAPER_X_MIN_MM * pixels_per_mm),
            round((A4_HEIGHT_MM - 210.0) * pixels_per_mm),
            round(base.PAPER_X_MAX_MM * pixels_per_mm),
            round((A4_HEIGHT_MM - 188.0) * pixels_per_mm),
        ),
        outline=(90, 160, 220),
        width=2,
    )
    for stroke in layout.strokes:
        draw.line(
            [preview_xy(point) for point in stroke.points],
            fill=(20, 20, 20),
            width=2,
            joint="curve",
        )
    draw.text(
        (20, 18),
        "V68 / B font 6 mm / V31 measured S-bow OFF",
        fill=(25, 25, 25),
        font=label_font(18),
    )
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def main() -> None:
    layout = translated_layout()
    lines = gcode_lines(layout)
    text = "\n".join(lines) + "\n"
    safety = audit(layout, lines)
    GCODE_PATH.parent.mkdir(parents=True, exist_ok=True)
    GCODE_PATH.write_text(text, encoding="ascii", newline="\n")
    manifest = {
        "id": TEST_ID,
        "required_firmware": FIRMWARE_ID,
        "purpose": (
            "single-variable comparison against V30/V66: the font geometry, "
            "size, feed, planner and hardware remain unchanged; only the "
            "measured 160 mm S-bow static prewarp is disabled in V31"
        ),
        "font": {
            "option": "B",
            "name": base.FONT_NAME,
            "file": base.FONT_PATH.name,
            "sha256": base.FONT_SHA256,
            "geometry": "unmodified gfont points; rigid Y translation only",
        },
        "layout": {
            "visible_height_mm": base.VISIBLE_HEIGHT_MM,
            "content_top_mm": CONTENT_TOP_MM,
            "translation_from_v65_mm": [0.0, TRANSLATE_Y_MM],
            "bounds_mm": list(layout.bounds_mm),
        },
        "coordinate_contract": {
            "units": "mm",
            "frame": "nominal physical A4 paper",
            "offline_mapping": False,
            "offline_prewarp": False,
            "firmware_mapping": True,
        },
        "motion": {
            "feed_mm_min": base.FEED_MM_MIN,
            "tangent_approach_mm": base.TANGENT_APPROACH_MM,
            "planner_unchanged_from_v30": True,
        },
        "safety": safety,
        "gcode": {
            "file": GCODE_PATH.name,
            "line_count": len(lines),
            "sha256": hashlib.sha256(text.encode("ascii")).hexdigest().upper(),
        },
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_preview(layout)
    print(
        "standard_bfont_no_sbow_v68=PASS "
        f"bounds={layout.bounds_mm} strokes={len(layout.strokes)} "
        f"safe_samples={safety['safe_samples']} "
        f"min_joint_margin={safety['min_joint_margin_deg']:.6f}deg"
    )
    print(f"gcode_sha256={manifest['gcode']['sha256']}")
    print(GCODE_PATH)
    print(MANIFEST_PATH)
    print(PREVIEW_PATH)


if __name__ == "__main__":
    main()
