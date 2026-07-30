#!/usr/bin/env python3
"""Generate the first checkerboard test for the V28 global +15 mm shift."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from generate_paper_a4_3x3_baseonly_direction_v49 import (
    A4_HEIGHT_MM,
    A4_WIDTH_MM,
    FEED_MM_MIN,
    PAIR_OFFSET_Y_MM,
    PAPER_STEP_MM,
    PAPER_X_MAX_MM,
    PAPER_X_MIN_MM,
    PAPER_Y_MAX_MM,
    PAPER_Y_MIN_MM,
    RECT_HEIGHT_MM,
    RECT_WIDTH_MM,
    build_plan,
    label_font,
    preview_xy,
)
from check_workspace_yshift15_v28 import (
    BUILD_ID,
    SHIFT_X_MM,
    SHIFT_Y_MM,
    joint_margin,
)


ROOT = Path(__file__).resolve().parents[1]
TEST_ID = (
    "PAPER_A4_3X3_GLOBAL_YSHIFT15_BASEONLY_CHECKER_"
    "CW_CCW_RECT24X8_GCODE_V52"
)
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"


def shifted(point: tuple[float, float]) -> tuple[float, float]:
    return point[0] + SHIFT_X_MM, point[1] + SHIFT_Y_MM


def gcode_lines(plan: tuple[dict, ...]) -> tuple[str, ...]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware_required={BUILD_ID}",
        "; WARNING=DO_NOT_SEND_TO_V27_OR_OLDER",
        "; global_workspace_translation_user_mm=(0,+15) APPLIED_BY_FIRMWARE",
        "; map=BASE_QUADRATIC_ONLY old_grid4x7_residual=DISABLED",
        "; v51_photo_quadratic=DISABLED",
        "; direction_placement=CHECKERBOARD upper/lower swapped_by_zone",
        "; connection_lines=NONE independent_pen_lift=1",
        f"; rectangle={RECT_WIDTH_MM:.0f}x{RECT_HEIGHT_MM:.0f}mm "
        f"pair_offset_y=+/-{PAIR_OFFSET_Y_MM:.0f}mm",
        f"; paper_step_max={PAPER_STEP_MM:.1f}mm",
        "G21",
        "G90",
        "G94",
        f"F{FEED_MM_MIN}",
        "S1000",
        "M5",
    ]
    for record in plan:
        approach = record["approach_user_mm"]
        points = record["user_points_mm"]
        center = record["center_paper_mm"]
        expected = shifted(center)
        lines.extend(
            (
                f"; zone={record['zone']} slot={record['vertical_slot']} "
                f"direction={record['direction']} "
                f"logical_center=({center[0]:.1f},{center[1]:.1f}) "
                f"nominal_shifted_center=({expected[0]:.1f},{expected[1]:.1f})",
                f"G0 X{approach[0]:.3f} Y{approach[1]:.3f}",
                f"G0 X{points[0][0]:.3f} Y{points[0][1]:.3f}",
                "M3",
            )
        )
        lines.extend(
            f"G1 X{point[0]:.3f} Y{point[1]:.3f}"
            for point in points[1:]
        )
        lines.append("M5")
    return tuple(lines)


def audit(plan: tuple[dict, ...]) -> dict:
    worst = (float("inf"), (0.0, 0.0), (0.0, 0.0, 0.0))
    sample_count = 0
    for record in plan:
        for raw_user in (
            record["approach_user_mm"],
            *record["user_points_mm"],
        ):
            shifted_user = shifted(raw_user)
            margin, angles = joint_margin(shifted_user)
            if margin < worst[0]:
                worst = (margin, shifted_user, angles)
            sample_count += 1
    if worst[0] < 10.0:
        raise AssertionError(
            f"V52 shifted point margin too small: {worst[0]:.3f} deg"
        )
    return {
        "sample_count": sample_count,
        "minimum_joint_margin_deg": worst[0],
        "minimum_at_shifted_user_mm": list(worst[1]),
        "minimum_at_angles_deg": list(worst[2]),
    }


def write_preview(plan: tuple[dict, ...]) -> None:
    width = round(A4_WIDTH_MM * 4.0) + 1
    height = round(A4_HEIGHT_MM * 4.0) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (0, 0, width - 1, height - 1),
        outline=(25, 25, 25),
        width=3,
    )
    draw.rectangle(
        (
            *preview_xy((PAPER_X_MIN_MM, PAPER_Y_MAX_MM)),
            *preview_xy((PAPER_X_MAX_MM, PAPER_Y_MIN_MM)),
        ),
        outline=(130, 160, 195),
        width=2,
    )
    draw.text(
        (20, 16),
        "V52: firmware-global +15 mm Y shift; V51 quadratic disabled",
        fill=(20, 20, 20),
        font=label_font(19),
    )
    draw.text(
        (20, 47),
        "Blue=CCW, red=CW; preview shows nominal shifted paper position",
        fill=(70, 70, 70),
        font=label_font(15),
    )
    for record in plan:
        color = (
            (25, 75, 190)
            if record["direction"] == "CCW"
            else (190, 55, 35)
        )
        draw.line(
            [
                preview_xy(shifted(point))
                for point in record["paper_points_mm"]
            ],
            fill=color,
            width=3,
        )
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def write_manifest(
    plan: tuple[dict, ...],
    lines: tuple[str, ...],
    safety: dict,
) -> None:
    text = "\n".join(lines) + "\n"
    manifest = {
        "id": TEST_ID,
        "required_firmware": BUILD_ID,
        "purpose": (
            "validate the firmware-global +15 mm Cartesian workspace "
            "translation without the V51 photo-fitted quadratic extrapolation"
        ),
        "workspace_translation_user_mm": [SHIFT_X_MM, SHIFT_Y_MM],
        "mapping": {
            "base_quadratic_enabled": True,
            "old_grid4x7_residual_enabled": False,
            "v51_photo_quadratic_enabled": False,
            "firmware_paper_map_enabled": False,
            "firmware_global_translation_enabled": True,
        },
        "nominal_shifted_paper_y_bounds_mm": [59.0, 231.0],
        "connection_lines": False,
        "safety": safety,
        "motion": {
            "feed_mm_min": FEED_MM_MIN,
            "pair_count": 9,
            "rectangle_count": len(plan),
            "g1_count": sum(
                len(record["user_points_mm"]) - 1 for record in plan
            ),
            "independent_pen_lift_per_rectangle": True,
        },
        "rectangles": [
            {
                "index": index,
                "zone": record["zone"],
                "vertical_slot": record["vertical_slot"],
                "direction": record["direction"],
                "logical_center_paper_mm": list(
                    record["center_paper_mm"]
                ),
                "nominal_shifted_center_paper_mm": list(
                    shifted(record["center_paper_mm"])
                ),
                "logical_paper_points_mm": [
                    list(point) for point in record["paper_points_mm"]
                ],
                "gcode_user_points_before_firmware_shift_mm": [
                    list(point) for point in record["user_points_mm"]
                ],
            }
            for index, record in enumerate(plan, start=1)
        ],
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
    plan = build_plan()
    safety = audit(plan)
    lines = gcode_lines(plan)
    GCODE_PATH.write_text(
        "\n".join(lines) + "\n",
        encoding="ascii",
        newline="\n",
    )
    write_preview(plan)
    write_manifest(plan, lines, safety)
    print(
        "generated_paper_a4_3x3_global_yshift15_v52=PASS "
        f"firmware={BUILD_ID} rectangles={len(plan)} "
        f"G1={sum(len(record['user_points_mm']) - 1 for record in plan)} "
        f"min_joint_margin={safety['minimum_joint_margin_deg']:.6f}deg "
        "v51_quadratic=0 grid4x7_residual=0 connection_lines=0"
    )
    print(GCODE_PATH)
    print(PREVIEW_PATH)
    print(MANIFEST_PATH)


if __name__ == "__main__":
    main()
