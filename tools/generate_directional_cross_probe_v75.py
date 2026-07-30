#!/usr/bin/env python3
"""Generate exact crosses that isolate horizontal/vertical traversal direction."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from generate_bfont_8_direction_junction_v74 import Stroke, audit, preview_xy


ROOT = Path(__file__).resolve().parents[1]
TEST_ID = "PAPER_A4_DIRECTIONAL_CROSS_PROBE_GCODE_V75"
FIRMWARE_MINIMUM = "PAPER_A4_STANDARD_GCODE_AMASS_PLANNER_V33"
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"
FEED_MM_MIN = 300


def stroke(
    group: str,
    direction: str,
    start: tuple[float, float],
    end: tuple[float, float],
) -> Stroke:
    return Stroke(group, direction, (start, end))


def cross(
    group: str,
    center_x: float,
    center_y: float,
    horizontal_forward: bool,
    vertical_forward: bool,
) -> tuple[Stroke, Stroke]:
    half = 8.0
    left = (center_x - half, center_y)
    right = (center_x + half, center_y)
    bottom = (center_x, center_y - half)
    top = (center_x, center_y + half)
    return (
        stroke(
            group,
            "H_LR" if horizontal_forward else "H_RL",
            left if horizontal_forward else right,
            right if horizontal_forward else left,
        ),
        stroke(
            group,
            "V_BT" if vertical_forward else "V_TB",
            bottom if vertical_forward else top,
            top if vertical_forward else bottom,
        ),
    )


def build_plan() -> tuple[Stroke, ...]:
    result: list[Stroke] = []
    # A/B differ only in horizontal direction. A/C differ only in vertical.
    result.extend(cross("A_HLR_VBT", 42.0, 190.0, True, True))
    result.extend(cross("B_HRL_VBT", 83.0, 190.0, False, True))
    result.extend(cross("C_HLR_VTB", 124.0, 190.0, True, False))
    result.extend(cross("D_HRL_VTB", 165.0, 190.0, False, False))

    # Exact same-locus overlays distinguish direction hysteresis from scale.
    result.append(stroke("E_HORIZONTAL_OVERLAY", "H_LR", (45.0, 145.0), (65.0, 145.0)))
    result.append(stroke("E_HORIZONTAL_OVERLAY", "H_RL", (65.0, 145.0), (45.0, 145.0)))
    result.append(stroke("F_VERTICAL_OVERLAY", "V_BT", (105.0, 135.0), (105.0, 155.0)))
    result.append(stroke("F_VERTICAL_OVERLAY", "V_TB", (105.0, 155.0), (105.0, 135.0)))
    result.append(stroke("G_DIAGONAL_OVERLAY", "D_BLTR", (157.0, 137.0), (173.0, 153.0)))
    result.append(stroke("G_DIAGONAL_OVERLAY", "D_TRBL", (173.0, 153.0), (157.0, 137.0)))
    return tuple(result)


def gcode_lines(plan: tuple[Stroke, ...]) -> tuple[str, ...]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware_minimum={FIRMWARE_MINIMUM}",
        "; coordinates=STANDARD_A4_PHYSICAL_PAPER_MM",
        "; offline_mapping=NONE offline_prewarp=NONE",
        "; row1=A(H_LR,V_BT) B(H_RL,V_BT) C(H_LR,V_TB) D(H_RL,V_TB)",
        "; every_cross=16x16mm expected_arms=8,8,8,8mm",
        "; row2=E_horizontal_FWD_REV_overlay F_vertical_FWD_REV_overlay G_diagonal_overlay",
        "; approach=5mm feed=300mm_min",
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
        "H_LR": (20, 95, 205),
        "H_RL": (215, 45, 35),
        "V_BT": (20, 145, 75),
        "V_TB": (195, 90, 20),
        "D_BLTR": (115, 55, 175),
        "D_TRBL": (20, 20, 20),
    }
    for item in plan:
        draw.line(
            [preview_xy(point) for point in item.points],
            fill=colors[item.direction],
            width=3,
        )
    for label, x in zip(("A", "B", "C", "D"), (42.0, 83.0, 124.0, 165.0)):
        px, py = preview_xy((x, 204.0))
        draw.text((px - 4, py), label, fill=(20, 20, 20))
    for label, point in (
        ("E H overlay", (55.0, 160.0)),
        ("F V overlay", (105.0, 160.0)),
        ("G D overlay", (165.0, 160.0)),
    ):
        px, py = preview_xy(point)
        draw.text((px - 28, py), label, fill=(20, 20, 20))
    draw.text((18, 16), "V75 exact directional cross probe", fill=(20, 20, 20))
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
        "expected": {
            "cross_total_mm": 16.0,
            "cross_arm_mm": 8.0,
            "overlay_total_mm": 20.0,
        },
        "comparison": {
            "A_vs_B": "horizontal traversal direction only",
            "A_vs_C": "vertical traversal direction only",
            "B_vs_D": "vertical traversal direction only",
            "C_vs_D": "horizontal traversal direction only",
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
