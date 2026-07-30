#!/usr/bin/env python3
"""Generate the V33 three-position 8 mm writing test at F450."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import generate_paper_a4_3pos_bfont_writezi_v72 as base
import generate_writezi_calibration_v77 as v77


TEST_ID = "PAPER_A4_3POS_BFONT_WRITEZI_8MM_F450_V33_GCODE_V80"
FIRMWARE_ID = "PAPER_A4_STANDARD_GCODE_AMASS_PLANNER_V33"
PAPER_MAP_ID = "A4_BASE_QUADRATIC_XSCALE_NO_SBOW_CAL_V8"
REFERENCE_TEST_ID = "PAPER_A4_3POS_BFONT_WRITEZI_8MM_V33_CAL_GCODE_V77"
REFERENCE_GCODE_PATH = ROOT / "gcode" / f"{REFERENCE_TEST_ID}.gcode"
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
GUIDE_PATH = ROOT / "gcode" / f"{TEST_ID}_GUIDE.md"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"
FEED_MM_MIN = 450


def configure_base() -> None:
    base.TEST_ID = TEST_ID
    base.FIRMWARE_ID = FIRMWARE_ID
    base.VISIBLE_HEIGHT_MM = 8.0
    base.CONTENT_TOP_MM = 190.0
    base.GROUPS = (("L", 40.0), ("M", 100.0), ("R", 160.0))
    base.TANGENT_APPROACH_MM = 5.0
    base.FEED_MM_MIN = FEED_MM_MIN


def comparable_commands(lines: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        line
        for line in lines
        if line.startswith(("G0 ", "G1 ")) or line in ("M3", "M5")
    )


def verify_reference_geometry(lines: tuple[str, ...]) -> dict[str, object]:
    if not REFERENCE_GCODE_PATH.exists():
        raise AssertionError(f"missing V77 reference: {REFERENCE_GCODE_PATH}")
    reference_text = REFERENCE_GCODE_PATH.read_text(encoding="ascii")
    reference_lines = tuple(reference_text.splitlines())
    if comparable_commands(lines) != comparable_commands(reference_lines):
        raise AssertionError("V80 geometry or pen commands differ from V77")
    if f"F{FEED_MM_MIN}" not in lines or "F300" not in reference_lines:
        raise AssertionError("V80/V77 feed-rate comparison is invalid")
    return {
        "id": REFERENCE_TEST_ID,
        "gcode_file": REFERENCE_GCODE_PATH.name,
        "gcode_sha256": hashlib.sha256(
            REFERENCE_GCODE_PATH.read_bytes()
        ).hexdigest().upper(),
        "reference_feed_mm_min": 300,
        "geometry_and_pen_commands_identical": True,
        "only_intended_motion_change": "feed F300 to F450",
    }


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
    for stroke in layout.strokes:
        draw.line(
            [base.preview_xy(point) for point in stroke.points],
            fill=(20, 20, 20),
            width=2,
            joint="curve",
        )
    for group, center_x in base.GROUPS:
        draw.text(
            base.preview_xy((center_x - 2.0, 196.0)),
            group,
            fill=(20, 20, 20),
            font=base.label_font(15),
        )
    draw.text(
        (20, 18),
        "V80 / V33 / B FONT / WRITE ZI / 8 mm / F450 / L-M-R",
        fill=(25, 25, 25),
        font=base.label_font(16),
    )
    draw.text(
        (20, 42),
        "Same geometry and pen commands as V77 F300; feed only changed",
        fill=(55, 55, 55),
        font=base.label_font(14),
    )
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def write_guide(manifest: dict[str, object]) -> None:
    safety = manifest["safety"]
    GUIDE_PATH.write_text(
        f"""# V80 8 mm writing speed test at F450

- Firmware: `{FIRMWARE_ID}`
- Paper map: `{PAPER_MAP_ID}`
- Content: three copies of WRITE ZI at left, middle, and right
- Font: pinned B gfont with unmodified source paths
- Visible height: 8 mm
- Feed: F{FEED_MM_MIN}
- Pen-up tangent approach: {base.TANGENT_APPROACH_MM:.0f} mm
- Reference: `{REFERENCE_TEST_ID}` at F300
- Geometry and pen commands: byte-for-byte equivalent after filtering comments and feed

Safety audit:

- Writing-sequence minimum joint margin: `{safety['writing_sequence']['minimum_joint_margin_deg']:.6f} deg`
- Required minimum margin: `{safety['writing_sequence']['required_minimum_margin_deg']:.1f} deg`

Compare against the V77 result for corner overshoot, open joins, missing strokes,
position drift, and any difference between the left, middle, and right copies.
""",
        encoding="utf-8",
    )


def main() -> None:
    configure_base()
    layout, stroke_groups = base.build_layout()
    generated_lines = list(base.gcode_lines(layout, stroke_groups))
    generated_lines.insert(2, f"; paper_map_required={PAPER_MAP_ID}")
    lines = tuple(generated_lines)
    content = "\n".join(lines) + "\n"
    reference = verify_reference_geometry(lines)
    safety = v77.audit(layout, lines)

    if lines.count("M3") != 30 or lines.count("M5") != 32:
        raise AssertionError("V80 stroke or pen-up count mismatch")
    if any(line.startswith("F") and line != "F450" for line in lines):
        raise AssertionError("V80 contains an unexpected feed command")

    GCODE_PATH.parent.mkdir(parents=True, exist_ok=True)
    GCODE_PATH.write_text(content, encoding="ascii", newline="\n")
    manifest = {
        "id": TEST_ID,
        "required_firmware": FIRMWARE_ID,
        "required_paper_map": PAPER_MAP_ID,
        "text": base.TEXT,
        "repetitions": 3,
        "font": {
            "option": "B",
            "name": base.source.FONT_NAME,
            "file": base.source.FONT_PATH.name,
            "sha256": base.source.FONT_SHA256,
            "geometry": "unmodified gfont paths; rigid translation only",
        },
        "layout": {
            "visible_height_mm": base.VISIBLE_HEIGHT_MM,
            "character_gap_mm": base.CHARACTER_GAP_MM,
            "content_top_mm": base.CONTENT_TOP_MM,
            "group_centers_x_mm": [center for _, center in base.GROUPS],
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
            "feed_mm_min": FEED_MM_MIN,
            "tangent_approach_mm": base.TANGENT_APPROACH_MM,
        },
        "reference_comparison": reference,
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
        f"{TEST_ID}=PASS strokes={safety['stroke_count']} "
        f"writing_margin="
        f"{safety['writing_sequence']['minimum_joint_margin_deg']:.6f}deg "
        f"reference_geometry=IDENTICAL "
        f"sha256={manifest['gcode']['sha256']}"
    )
    print(GCODE_PATH)
    print(MANIFEST_PATH)
    print(PREVIEW_PATH)
    print(GUIDE_PATH)


if __name__ == "__main__":
    main()
