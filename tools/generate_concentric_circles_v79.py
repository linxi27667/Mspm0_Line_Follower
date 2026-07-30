#!/usr/bin/env python3
"""Generate the V33 A4-center concentric-circle test."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import generate_paper_a4_3pos_bfont_writezi_v72 as base
import generate_writezi_calibration_v77 as v77


TEST_ID = "PAPER_A4_CENTER_CONCENTRIC_CIRCLES_D20_D40_D60_D80_V33_GCODE_V79"
FIRMWARE_ID = "PAPER_A4_STANDARD_GCODE_AMASS_PLANNER_V33"
PAPER_MAP_ID = "A4_BASE_QUADRATIC_XSCALE_NO_SBOW_CAL_V8"
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
GUIDE_PATH = ROOT / "gcode" / f"{TEST_ID}_GUIDE.md"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"

CENTER_MM = (105.0, 148.5)
DIAMETERS_MM = (20.0, 40.0, 60.0, 80.0)
FEED_MM_MIN = 300
MAX_CHORD_MM = 0.75
TANGENT_APPROACH_MM = 5.0
PAPER_SAFE_BOUNDS_MM = (25.0, 75.0, 185.0, 235.0)


def segment_count(radius_mm: float) -> int:
    required = math.ceil(2.0 * math.pi * radius_mm / MAX_CHORD_MM)
    return 4 * math.ceil(required / 4)


def circle_points(
    radius_mm: float,
) -> tuple[tuple[float, float], ...]:
    segments = segment_count(radius_mm)
    return tuple(
        (
            CENTER_MM[0]
            + radius_mm * math.cos(math.pi / 2.0 + 2.0 * math.pi * i / segments),
            CENTER_MM[1]
            + radius_mm * math.sin(math.pi / 2.0 + 2.0 * math.pi * i / segments),
        )
        for i in range(segments + 1)
    )


def tangent_approach(
    points: tuple[tuple[float, float], ...],
) -> tuple[float, float]:
    start = points[0]
    next_point = points[1]
    dx = next_point[0] - start[0]
    dy = next_point[1] - start[1]
    length = math.hypot(dx, dy)
    return (
        start[0] - TANGENT_APPROACH_MM * dx / length,
        start[1] - TANGENT_APPROACH_MM * dy / length,
    )


def validate_stroke(stroke, diameter_mm: float) -> dict[str, object]:
    radius_mm = diameter_mm / 2.0
    points = stroke.points
    if math.dist(points[0], points[-1]) > 1.0e-9:
        raise AssertionError(f"D{diameter_mm:g} circle is not closed")

    radial_errors = (
        abs(math.dist(CENTER_MM, point) - radius_mm) for point in points
    )
    maximum_radial_error = max(radial_errors)
    chord_lengths = tuple(
        math.dist(start, end) for start, end in zip(points, points[1:])
    )
    maximum_chord = max(chord_lengths)
    if maximum_radial_error > 1.0e-9:
        raise AssertionError(
            f"D{diameter_mm:g} radial error: {maximum_radial_error}"
        )
    if maximum_chord > MAX_CHORD_MM + 1.0e-9:
        raise AssertionError(
            f"D{diameter_mm:g} chord too long: {maximum_chord}"
        )

    x_min, y_min, x_max, y_max = PAPER_SAFE_BOUNDS_MM
    for point in (stroke.approach, *points):
        if not (x_min <= point[0] <= x_max and y_min <= point[1] <= y_max):
            raise AssertionError(
                f"D{diameter_mm:g} leaves safe paper bounds: {point}"
            )

    return {
        "diameter_mm": diameter_mm,
        "radius_mm": radius_mm,
        "direction": "CCW",
        "start": "TOP",
        "segment_count": len(points) - 1,
        "maximum_chord_mm": maximum_chord,
        "maximum_radial_error_mm": maximum_radial_error,
        "approach_mm": list(stroke.approach),
    }


def build_layout():
    strokes = []
    records = []
    for diameter_mm in DIAMETERS_MM:
        points = circle_points(diameter_mm / 2.0)
        stroke = SimpleNamespace(
            approach=tangent_approach(points),
            points=points,
        )
        strokes.append(stroke)
        records.append(validate_stroke(stroke, diameter_mm))
    return SimpleNamespace(strokes=tuple(strokes)), tuple(records)


def gcode_lines(layout) -> tuple[str, ...]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware_required={FIRMWARE_ID}",
        f"; paper_map_required={PAPER_MAP_ID}",
        "; coordinates=STANDARD_A4_PHYSICAL_PAPER_MM",
        "; offline_mapping=NONE offline_prewarp=NONE",
        "; pattern=CONCENTRIC_CIRCLES center=(105,148.5)mm",
        "; diameters=20,40,60,80mm direction=CCW start=TOP",
        f"; maximum_chord={MAX_CHORD_MM:.2f}mm",
        f"; tangent_approach={TANGENT_APPROACH_MM:.0f}mm",
        "G21",
        "G90",
        "G94",
        f"F{FEED_MM_MIN}",
        "S1000",
        "M5",
    ]
    for diameter_mm, stroke in zip(DIAMETERS_MM, layout.strokes):
        lines.extend(
            (
                f"; BEGIN_CIRCLE_D{int(diameter_mm)}_CCW",
                f"G0 X{stroke.approach[0]:.3f} Y{stroke.approach[1]:.3f}",
                f"G0 X{stroke.points[0][0]:.3f} Y{stroke.points[0][1]:.3f}",
                "M3",
            )
        )
        lines.extend(
            f"G1 X{point[0]:.3f} Y{point[1]:.3f}"
            for point in stroke.points[1:]
        )
        lines.extend(("M5", f"; END_CIRCLE_D{int(diameter_mm)}_CCW"))
    lines.append("M5")
    return tuple(lines)


def write_preview(layout) -> None:
    scale = base.PREVIEW_PIXELS_PER_MM
    width = round(base.A4_WIDTH_MM * scale) + 1
    height = round(base.A4_HEIGHT_MM * scale) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (0, 0, width - 1, height - 1),
        outline=(30, 30, 30),
        width=3,
    )

    colors = (
        (25, 90, 160),
        (35, 130, 75),
        (185, 85, 35),
        (80, 65, 125),
    )
    for diameter_mm, stroke, color in zip(
        DIAMETERS_MM, layout.strokes, colors
    ):
        draw.line(
            [base.preview_xy(point) for point in stroke.points],
            fill=color,
            width=3,
            joint="curve",
        )

    draw.text(
        (20, 18),
        "V79 / V33 / CONCENTRIC CIRCLES / D20 D40 D60 D80 / F300",
        fill=(25, 25, 25),
        font=base.label_font(16),
    )
    draw.text(
        (20, 42),
        "Center X105 Y148.5 mm / CCW / pen lifts between circles",
        fill=(55, 55, 55),
        font=base.label_font(14),
    )
    legend_x = 20
    for diameter_mm, color in zip(DIAMETERS_MM, colors):
        draw.line(
            (legend_x, 73, legend_x + 24, 73),
            fill=color,
            width=4,
        )
        draw.text(
            (legend_x + 30, 64),
            f"D{int(diameter_mm)}",
            fill=color,
            font=base.label_font(14),
        )
        legend_x += 100
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def write_guide(manifest: dict[str, object]) -> None:
    safety = manifest["safety"]
    GUIDE_PATH.write_text(
        f"""# V79 concentric-circle test

- Firmware: `{FIRMWARE_ID}`
- Paper map: `{PAPER_MAP_ID}`
- A4 center: X={CENTER_MM[0]:.1f} mm, Y={CENTER_MM[1]:.1f} mm
- Diameters, inner to outer: 20, 40, 60, 80 mm
- Direction: CCW; start point: top
- Feed: F{FEED_MM_MIN}
- Pen-up tangent approach: {TANGENT_APPROACH_MM:.0f} mm per circle
- Coordinate frame: standard physical A4 paper; no offline prewarp

Safety audit:

- Drawing-sequence minimum joint margin: `{safety['writing_sequence']['minimum_joint_margin_deg']:.6f} deg`
- Required minimum margin: `{safety['writing_sequence']['required_minimum_margin_deg']:.1f} deg`

Inspect whether all rings share one center, remain circular, close at the top,
and keep uniform radial spacing. Measure the horizontal and vertical diameters
of the D80 ring if it appears oval.
""",
        encoding="utf-8",
    )


def main() -> None:
    layout, circle_records = build_layout()
    lines = gcode_lines(layout)
    content = "\n".join(lines) + "\n"
    safety = v77.audit(layout, lines)

    if lines.count("M3") != len(DIAMETERS_MM):
        raise AssertionError("V79 pen-down count mismatch")
    if lines.count("M5") != len(DIAMETERS_MM) + 2:
        raise AssertionError("V79 pen-up count mismatch")
    if len(content.encode("ascii")) > 65535:
        raise AssertionError("V79 G-code exceeds the intended serial test size")

    GCODE_PATH.parent.mkdir(parents=True, exist_ok=True)
    GCODE_PATH.write_text(content, encoding="ascii", newline="\n")
    manifest = {
        "id": TEST_ID,
        "required_firmware": FIRMWARE_ID,
        "required_paper_map": PAPER_MAP_ID,
        "coordinate_contract": {
            "units": "mm",
            "frame": "nominal physical A4 paper",
            "offline_mapping": False,
            "offline_prewarp": False,
            "firmware_mapping": True,
        },
        "pattern": {
            "type": "concentric circles",
            "center_mm": list(CENTER_MM),
            "diameters_mm": list(DIAMETERS_MM),
            "sequence": "inner_to_outer",
            "circles": list(circle_records),
        },
        "motion": {
            "feed_mm_min": FEED_MM_MIN,
            "tangent_approach_mm": TANGENT_APPROACH_MM,
            "stroke_count": len(DIAMETERS_MM),
        },
        "safety": safety,
        "gcode": {
            "file": GCODE_PATH.name,
            "line_count": len(lines),
            "sha256": hashlib.sha256(content.encode("ascii"))
            .hexdigest()
            .upper(),
        },
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_preview(layout)
    write_guide(manifest)
    print(
        f"{TEST_ID}=PASS circles={len(DIAMETERS_MM)} "
        f"segments={sum(item['segment_count'] for item in circle_records)} "
        f"writing_margin="
        f"{safety['writing_sequence']['minimum_joint_margin_deg']:.6f}deg "
        f"sha256={manifest['gcode']['sha256']}"
    )
    print(GCODE_PATH)
    print(MANIFEST_PATH)
    print(PREVIEW_PATH)
    print(GUIDE_PATH)


if __name__ == "__main__":
    main()
