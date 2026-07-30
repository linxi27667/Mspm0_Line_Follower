#!/usr/bin/env python3
"""Generate pen-up reversal dot pairs to isolate drag from drivetrain play."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from generate_paper_a4_3x3_baseonly_direction_v49 import (
    A4_HEIGHT_MM,
    A4_WIDTH_MM,
    BUILD_ID,
    COLUMNS,
    PAPER_X_MAX_MM,
    PAPER_X_MIN_MM,
    PAPER_Y_MAX_MM,
    PAPER_Y_MIN_MM,
    ROWS,
    label_font,
    map_base_only,
    preview_xy,
)


ROOT = Path(__file__).resolve().parents[1]
TEST_ID = "PAPER_A4_3X3_PENUP_REVERSAL_DOT_PAIRS_GCODE_V50"
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"

TARGET_OFFSET_X_MM = 6.0
APPROACH_DISTANCE_MM = 10.0
DOT_DWELL_S = 0.25
FEED_MM_MIN = 150


def build_plan() -> tuple[dict, ...]:
    records = []
    for row_name, center_y in ROWS:
        for column_name, center_x in COLUMNS:
            targets = (
                (
                    "H",
                    (center_x - TARGET_OFFSET_X_MM, center_y),
                    (
                        ("+X", (-APPROACH_DISTANCE_MM, 0.0)),
                        ("-X", (APPROACH_DISTANCE_MM, 0.0)),
                    ),
                ),
                (
                    "V",
                    (center_x + TARGET_OFFSET_X_MM, center_y),
                    (
                        ("+Y", (0.0, -APPROACH_DISTANCE_MM)),
                        ("-Y", (0.0, APPROACH_DISTANCE_MM)),
                    ),
                ),
            )
            for target_name, target, approaches in targets:
                for approach_name, delta in approaches:
                    approach = (
                        target[0] + delta[0],
                        target[1] + delta[1],
                    )
                    for point in (approach, target):
                        if not (
                            PAPER_X_MIN_MM <= point[0] <= PAPER_X_MAX_MM
                            and PAPER_Y_MIN_MM
                            <= point[1]
                            <= PAPER_Y_MAX_MM
                        ):
                            raise AssertionError(
                                f"{row_name}_{column_name}_{target_name}_"
                                f"{approach_name} out of bounds: {point}"
                            )
                    records.append(
                        {
                            "zone": f"{row_name}_{column_name}",
                            "row": row_name,
                            "column": column_name,
                            "target_name": target_name,
                            "approach_direction": approach_name,
                            "target_paper_mm": target,
                            "approach_paper_mm": approach,
                            "target_user_mm": map_base_only(target),
                            "approach_user_mm": map_base_only(approach),
                        }
                    )
    return tuple(records)


def gcode_lines(plan: tuple[dict, ...]) -> tuple[str, ...]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware={BUILD_ID}",
        "; purpose=pen_up_reversal_isolation",
        "; map=BASE_QUADRATIC_ONLY old_grid4x7_residual=DISABLED",
        "; layout=3x3 zones=9 logical_targets_per_zone=2",
        "; each_target_marked_twice_from_opposite_directions",
        "; all_approach_motion_pen_up=1 pen_down_travel=0",
        "G21",
        "G90",
        "G94",
        f"F{FEED_MM_MIN}",
        "S1000",
        "M5",
    ]
    for record in plan:
        approach = record["approach_user_mm"]
        target = record["target_user_mm"]
        lines.extend(
            (
                f"; zone={record['zone']} target={record['target_name']} "
                f"approach={record['approach_direction']}",
                f"G0 X{approach[0]:.3f} Y{approach[1]:.3f}",
                f"G0 X{target[0]:.3f} Y{target[1]:.3f}",
                "M3",
                f"G4 P{DOT_DWELL_S:.2f}",
                "M5",
            )
        )
    return tuple(lines)


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
        "V50：全程抬笔换向，只在重复目标点短暂落笔",
        fill=(20, 20, 20),
        font=label_font(21),
    )
    draw.text(
        (20, 47),
        "每区左点测 ±X，右点测 ±Y；两次目标坐标完全相同",
        fill=(70, 70, 70),
        font=label_font(17),
    )
    seen = set()
    for record in plan:
        key = (record["zone"], record["target_name"])
        if key in seen:
            continue
        seen.add(key)
        x, y = preview_xy(record["target_paper_mm"])
        color = (
            (35, 90, 195)
            if record["target_name"] == "H"
            else (195, 65, 35)
        )
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=color)
        draw.text(
            (x + 7, y - 10),
            record["target_name"],
            fill=color,
            font=label_font(14),
        )
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def write_manifest(
    plan: tuple[dict, ...],
    lines: tuple[str, ...],
) -> None:
    text = "\n".join(lines) + "\n"
    manifest = {
        "id": TEST_ID,
        "required_firmware": BUILD_ID,
        "purpose": (
            "If opposite-direction dots split while all travel is pen-up, "
            "the residual is drivetrain/joint hysteresis. If they overlap, "
            "the CW/CCW rectangle split is pen drag or holder compliance."
        ),
        "mapping": {
            "base_quadratic_enabled": True,
            "old_grid4x7_residual_enabled": False,
            "firmware_paper_map_enabled": False,
            "offline_pointwise_map_enabled": True,
        },
        "motion": {
            "zone_count": 9,
            "logical_target_count": 18,
            "mark_count": len(plan),
            "approach_distance_mm": APPROACH_DISTANCE_MM,
            "dot_dwell_s": DOT_DWELL_S,
            "pen_down_travel_count": 0,
        },
        "marks": [
            {
                "index": index,
                "zone": record["zone"],
                "target_name": record["target_name"],
                "approach_direction": record["approach_direction"],
                "target_paper_mm": list(record["target_paper_mm"]),
                "approach_paper_mm": list(record["approach_paper_mm"]),
                "target_user_mm": list(record["target_user_mm"]),
                "approach_user_mm": list(record["approach_user_mm"]),
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
    lines = gcode_lines(plan)
    GCODE_PATH.write_text(
        "\n".join(lines) + "\n",
        encoding="ascii",
        newline="\n",
    )
    write_preview(plan)
    write_manifest(plan, lines)
    print(
        "generated_paper_a4_3x3_penup_reversal_dots_v50=PASS "
        f"zones=9 targets=18 marks={len(plan)} "
        "pen_down_travel=0 grid4x7_residual=0"
    )
    print(GCODE_PATH)
    print(PREVIEW_PATH)
    print(MANIFEST_PATH)


if __name__ == "__main__":
    main()
