#!/usr/bin/env python3
"""Generate multi-direction endpoint convergence probes at three paper columns."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

from generate_bfont_8_direction_junction_v74 import Stroke, audit, preview_xy


ROOT = Path(__file__).resolve().parents[1]
TEST_ID = "PAPER_A4_ENDPOINT_CONVERGENCE_PROBE_GCODE_V76"
FIRMWARE_MINIMUM = "PAPER_A4_STANDARD_GCODE_AMASS_PLANNER_V33"
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"
FEED_MM_MIN = 300
RADIUS_MM = 10.0
DIRECTIONS_DEG = tuple(range(0, 360, 45))


def point_on_ring(
    center: tuple[float, float],
    angle_deg: int,
) -> tuple[float, float]:
    angle = math.radians(angle_deg)
    return (
        center[0] + RADIUS_MM * math.cos(angle),
        center[1] + RADIUS_MM * math.sin(angle),
    )


def star(
    group: str,
    center: tuple[float, float],
    inbound: bool,
) -> tuple[Stroke, ...]:
    result = []
    for angle_deg in DIRECTIONS_DEG:
        outer = point_on_ring(center, angle_deg)
        points = (outer, center) if inbound else (center, outer)
        result.append(
            Stroke(
                group,
                f"{'IN' if inbound else 'OUT'}_{angle_deg:03d}",
                points,
            )
        )
    return tuple(result)


def build_plan() -> tuple[Stroke, ...]:
    result: list[Stroke] = []
    for column, center_x in enumerate((45.0, 105.0, 165.0), start=1):
        result.extend(star(f"ROW1_INBOUND_C{column}", (center_x, 190.0), True))
    for column, center_x in enumerate((45.0, 105.0, 165.0), start=1):
        result.extend(star(f"ROW2_OUTBOUND_C{column}", (center_x, 145.0), False))
    return tuple(result)


def gcode_lines(plan: tuple[Stroke, ...]) -> tuple[str, ...]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware_minimum={FIRMWARE_MINIMUM}",
        "; coordinates=STANDARD_A4_PHYSICAL_PAPER_MM",
        "; offline_mapping=NONE offline_prewarp=NONE",
        "; row1=8_direction_INBOUND_all_end_at_exact_same_center",
        "; row2=8_direction_OUTBOUND_all_start_at_exact_same_center",
        "; columns=paper_x_45_105_165mm radius=10mm approach=5mm",
        "; endpoint_spread_is_direction_dependent_physical_pose_error",
        "G21",
        "G90",
        "G94",
        f"F{FEED_MM_MIN}",
        "S1000",
        "M5",
    ]
    previous_group = ""
    for index, item in enumerate(plan, start=1):
        if item.group != previous_group:
            lines.append(f"; GROUP={item.group}")
            previous_group = item.group
        lines.extend(
            (
                f"; stroke={index} DIRECTION={item.direction}",
                f"G0 X{item.approach[0]:.3f} Y{item.approach[1]:.3f}",
                f"G0 X{item.points[0][0]:.3f} Y{item.points[0][1]:.3f}",
                "M3",
                f"G1 X{item.points[1][0]:.3f} Y{item.points[1][1]:.3f}",
                "M5",
            )
        )
    lines.append("M5")
    return tuple(lines)


def write_preview(plan: tuple[Stroke, ...]) -> None:
    image = Image.new("RGB", (841, 1189), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 840, 1188), outline=(20, 20, 20), width=3)
    colors = {
        "ROW1": (25, 90, 200),
        "ROW2": (205, 55, 35),
    }
    for item in plan:
        color = colors["ROW1" if item.group.startswith("ROW1") else "ROW2"]
        draw.line(
            [preview_xy(point) for point in item.points],
            fill=color,
            width=3,
        )
    for row_name, y in (("IN", 190.0), ("OUT", 145.0)):
        for column, x in enumerate((45.0, 105.0, 165.0), start=1):
            px, py = preview_xy((x, y + 16.0))
            draw.text((px - 13, py), f"{row_name}{column}", fill=(20, 20, 20))
    draw.text((18, 16), "V76 endpoint convergence: IN / OUT x 3 columns", fill=(20, 20, 20))
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def main() -> None:
    plan = build_plan()
    safety = audit(plan)
    lines = gcode_lines(plan)
    content = "\n".join(lines) + "\n"
    GCODE_PATH.parent.mkdir(parents=True, exist_ok=True)
    GCODE_PATH.write_text(content, encoding="ascii", newline="\n")
    manifest = {
        "id": TEST_ID,
        "firmware_minimum": FIRMWARE_MINIMUM,
        "geometry": {
            "radius_mm": RADIUS_MM,
            "directions_deg": list(DIRECTIONS_DEG),
            "inbound_centers_mm": [[x, 190.0] for x in (45.0, 105.0, 165.0)],
            "outbound_centers_mm": [[x, 145.0] for x in (45.0, 105.0, 165.0)],
        },
        "interpretation": {
            "inbound": "all eight physical endpoints should converge",
            "outbound": "all eight physical starts should share one center",
            "column_difference": "pose dependence, not a global constant deadband",
        },
        "motion": {
            "feed_mm_min": FEED_MM_MIN,
            "tangent_approach_mm": 5.0,
            "stroke_count": len(plan),
        },
        "safety": safety,
        "gcode": {
            "file": GCODE_PATH.name,
            "line_count": len(lines),
            "sha256": hashlib.sha256(content.encode("ascii")).hexdigest().upper(),
        },
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_preview(plan)
    print(
        f"{TEST_ID}=PASS strokes={len(plan)} "
        f"min_joint_margin={safety['minimum_joint_margin_deg']:.6f}deg "
        f"gcode_sha256={manifest['gcode']['sha256']}"
    )
    print(GCODE_PATH)
    print(MANIFEST_PATH)
    print(PREVIEW_PATH)


if __name__ == "__main__":
    main()
