#!/usr/bin/env python3
"""Measure the V49 base-only checkerboard direction test photo."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from analyze_v47_3x3_rect_photo import (
    WARP_HEIGHT,
    WARP_PAGE_CORNERS,
    WARP_WIDTH,
    expected_pixel,
    make_ink_mask,
    measure_rectangle,
    trace_horizontal,
    trace_vertical,
)
from analyze_v48_cw_ccw_rect_photo import (
    COLUMNS,
    PAIR_OFFSET_Y_MM,
    RECT_HEIGHT_MM,
    RECT_WIDTH_MM,
    ROWS,
    locate_pair,
    motion_direction,
)


ROOT = Path(__file__).resolve().parents[1]
PHOTO = (
    ROOT
    / "docs"
    / "diagnostics"
    / "V49_BASEONLY_DIRECTION_PHOTO_20260725.jpg"
)
OUTPUT_JSON = (
    ROOT
    / "docs"
    / "diagnostics"
    / "V49_BASEONLY_DIRECTION_PHOTO_ANALYSIS.json"
)
OUTPUT_RECTIFIED = (
    ROOT
    / "docs"
    / "diagnostics"
    / "V49_BASEONLY_DIRECTION_RECTIFIED.png"
)
OUTPUT_ANNOTATED = (
    ROOT
    / "docs"
    / "diagnostics"
    / "V49_BASEONLY_DIRECTION_ANALYZED.png"
)

# The submitted image contains rulers on both sides.  These points follow the
# main white sheet, not the rulers or the extra sheet visible below it.
PHOTO_PAGE_CORNERS = np.float32(
    [
        [62.0, 160.0],
        [1068.0, 80.0],
        [1158.0, 1594.0],
        [63.0, 1594.0],
    ]
)


def placement_directions(
    row_index: int,
    column_index: int,
) -> dict[str, str]:
    if (row_index + column_index) % 2 == 0:
        return {"UPPER": "CCW", "LOWER": "CW"}
    return {"UPPER": "CW", "LOWER": "CCW"}


def main() -> None:
    image = cv2.imread(str(PHOTO))
    if image is None:
        raise FileNotFoundError(PHOTO)
    page_transform = cv2.getPerspectiveTransform(
        PHOTO_PAGE_CORNERS, WARP_PAGE_CORNERS
    )
    rectified = cv2.warpPerspective(
        image, page_transform, (WARP_WIDTH, WARP_HEIGHT)
    )
    cv2.imwrite(str(OUTPUT_RECTIFIED), rectified)
    gray = cv2.cvtColor(rectified, cv2.COLOR_BGR2GRAY)
    ink = make_ink_mask(gray)

    annotated = rectified.copy()
    records = []
    colors = {"CCW": (220, 80, 30), "CW": (30, 60, 220)}
    index = 0
    for row_index, (row_name, center_y_mm) in enumerate(ROWS):
        for column_index, (column_name, center_x_mm) in enumerate(COLUMNS):
            center_x, zone_y = expected_pixel(
                (center_x_mm, center_y_mm)
            )
            # Removing the old residual moves this entire test roughly 21 mm
            # upward on the physical sheet.  The broad localizer follows that
            # common offset; measurements still use the A4 frame itself.
            old_labels = locate_pair(
                ink, center_x, zone_y - 21.0 * 5.0
            )
            located = {
                "UPPER": old_labels["CCW"],
                "LOWER": old_labels["CW"],
            }
            directions = placement_directions(row_index, column_index)
            for slot in ("UPPER", "LOWER"):
                index += 1
                direction = directions[slot]
                edges = located[slot]
                traces = {
                    "top": trace_horizontal(
                        ink,
                        edges["left"],
                        edges["right"],
                        edges["top"],
                    ),
                    "bottom": trace_horizontal(
                        ink,
                        edges["left"],
                        edges["right"],
                        edges["bottom"],
                    ),
                    "left": trace_vertical(
                        ink,
                        edges["left"],
                        edges["top"],
                        edges["bottom"],
                        min_points=10,
                    ),
                    "right": trace_vertical(
                        ink,
                        edges["right"],
                        edges["top"],
                        edges["bottom"],
                        min_points=10,
                    ),
                }
                measurement, _ = measure_rectangle(traces)
                expected_y = (
                    center_y_mm + PAIR_OFFSET_Y_MM
                    if slot == "UPPER"
                    else center_y_mm - PAIR_OFFSET_Y_MM
                )
                measurement.update(
                    {
                        "index": index,
                        "zone": f"{row_name}_{column_name}",
                        "row": row_name,
                        "column": column_name,
                        "vertical_slot": slot,
                        "direction": direction,
                        "center_paper_mm": [center_x_mm, expected_y],
                        "located_edges_rectified_px": edges,
                    }
                )
                records.append(measurement)
                for points in traces.values():
                    for point in points[::3]:
                        cv2.circle(
                            annotated,
                            (round(point[0]), round(point[1])),
                            1,
                            colors[direction],
                            -1,
                        )

    by_direction = {}
    for direction in ("CCW", "CW"):
        selected = [
            item for item in records if item["direction"] == direction
        ]
        by_direction[direction] = {
            "count": len(selected),
            "mean_width_mm": float(
                np.mean([item["width_mean_mm"] for item in selected])
            ),
            "mean_height_mm": float(
                np.mean([item["height_mean_mm"] for item in selected])
            ),
            "mean_orthogonality_error_deg": float(
                np.mean(
                    [
                        item["orthogonality_error_deg"]
                        for item in selected
                    ]
                )
            ),
            "mean_worst_edge_curve95_mm": float(
                np.mean(
                    [
                        item["edge_curve95_worst_mm"]
                        for item in selected
                    ]
                )
            ),
        }

    by_slot = {}
    for slot in ("UPPER", "LOWER"):
        selected = [
            item for item in records if item["vertical_slot"] == slot
        ]
        by_slot[slot] = {
            "mean_width_mm": float(
                np.mean([item["width_mean_mm"] for item in selected])
            ),
            "mean_height_mm": float(
                np.mean([item["height_mean_mm"] for item in selected])
            ),
        }

    motion_curves = {
        direction: [] for direction in ("+X", "-X", "+Y", "-Y")
    }
    for record in records:
        for side, value in record["edge_curve95_mm"].items():
            motion_curves[
                motion_direction(record["direction"], side)
            ].append(value)

    pair_differences = []
    for row_name, _ in ROWS:
        for column_name, _ in COLUMNS:
            zone = f"{row_name}_{column_name}"
            upper = next(
                item
                for item in records
                if item["zone"] == zone
                and item["vertical_slot"] == "UPPER"
            )
            lower = next(
                item
                for item in records
                if item["zone"] == zone
                and item["vertical_slot"] == "LOWER"
            )
            pair_differences.append(
                {
                    "zone": zone,
                    "upper_direction": upper["direction"],
                    "lower_direction": lower["direction"],
                    "lower_minus_upper_width_mm": (
                        lower["width_mean_mm"] - upper["width_mean_mm"]
                    ),
                    "lower_minus_upper_height_mm": (
                        lower["height_mean_mm"] - upper["height_mean_mm"]
                    ),
                }
            )

    summary = {
        "photo": str(PHOTO),
        "photo_page_corners_px": PHOTO_PAGE_CORNERS.tolist(),
        "mapping_under_test": {
            "base_quadratic_enabled": True,
            "old_grid4x7_residual_enabled": False,
        },
        "connection_lines": False,
        "nominal_rectangle_mm": [RECT_WIDTH_MM, RECT_HEIGHT_MM],
        "rectangles": records,
        "pair_differences": pair_differences,
        "summary": {
            "by_direction": by_direction,
            "by_vertical_slot": by_slot,
            "mean_edge_curve95_by_motion_direction_mm": {
                direction: float(np.mean(values))
                for direction, values in motion_curves.items()
            },
            "width_range_mm": [
                min(item["width_mean_mm"] for item in records),
                max(item["width_mean_mm"] for item in records),
            ],
            "height_range_mm": [
                min(item["height_mean_mm"] for item in records),
                max(item["height_mean_mm"] for item in records),
            ],
            "orthogonality_error_max_deg": max(
                item["orthogonality_error_deg"] for item in records
            ),
            "edge_curve95_max_mm": max(
                item["edge_curve95_worst_mm"] for item in records
            ),
        },
        "measurement_note": (
            "The A4 homography excludes both rulers. Checkerboard direction "
            "placement separates direction from upper/lower position."
        ),
    }
    OUTPUT_JSON.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    cv2.imwrite(str(OUTPUT_ANNOTATED), annotated)
    print(json.dumps(summary["summary"], ensure_ascii=False, indent=2))
    for item in pair_differences:
        print(
            f"{item['zone']} "
            f"{item['upper_direction']}/{item['lower_direction']} "
            f"dW={item['lower_minus_upper_width_mm']:+.2f}mm "
            f"dH={item['lower_minus_upper_height_mm']:+.2f}mm"
        )
    print(OUTPUT_JSON)
    print(OUTPUT_RECTIFIED)
    print(OUTPUT_ANNOTATED)


if __name__ == "__main__":
    main()
