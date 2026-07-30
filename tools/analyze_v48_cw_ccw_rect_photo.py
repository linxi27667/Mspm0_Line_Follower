#!/usr/bin/env python3
"""Measure the V48 CW/CCW rectangle pairs from one A4 photo."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from analyze_v47_3x3_rect_photo import (
    PX_PER_MM,
    WARP_HEIGHT,
    WARP_PAGE_CORNERS,
    WARP_WIDTH,
    expected_pixel,
    make_ink_mask,
    measure_rectangle,
    strongest_projection_peak,
    trace_horizontal,
    trace_vertical,
)


ROOT = Path(__file__).resolve().parents[1]
PHOTO = (
    ROOT
    / "docs"
    / "diagnostics"
    / "V48_CW_CCW_RECT_PHOTO_20260725.png"
)
OUTPUT_JSON = (
    ROOT / "docs" / "diagnostics" / "V48_CW_CCW_RECT_PHOTO_ANALYSIS.json"
)
OUTPUT_RECTIFIED = (
    ROOT / "docs" / "diagnostics" / "V48_CW_CCW_RECT_RECTIFIED.png"
)
OUTPUT_ANNOTATED = (
    ROOT / "docs" / "diagnostics" / "V48_CW_CCW_RECT_ANALYZED.png"
)

# Main-sheet corners in the submitted PNG.  The lower white strip belongs to
# the sheet underneath and is intentionally excluded.
PHOTO_PAGE_CORNERS = np.float32(
    [
        [138.0, 105.0],
        [1152.0, 124.0],
        [1144.0, 1591.0],
        [98.0, 1558.0],
    ]
)

COLUMNS = (("LEFT", 50.0), ("CENTER", 105.0), ("RIGHT", 160.0))
ROWS = (("TOP", 205.0), ("MIDDLE", 130.0), ("BOTTOM", 55.0))
RECT_WIDTH_MM = 24.0
RECT_HEIGHT_MM = 8.0
PAIR_OFFSET_Y_MM = 7.0


def projection_peaks(
    projection: np.ndarray,
    count: int,
    minimum_separation: int,
) -> list[float]:
    smoothed = np.convolve(
        projection.astype(np.float64),
        np.asarray([0.2, 0.6, 0.2]),
        mode="same",
    )
    candidates = []
    work = smoothed.copy()
    for _ in range(count):
        peak = int(np.argmax(work))
        if work[peak] <= 0.0:
            raise AssertionError("not enough projection peaks")
        lo = max(0, peak - 2)
        hi = min(len(projection), peak + 3)
        weights = projection[lo:hi].astype(np.float64)
        coordinates = np.arange(lo, hi, dtype=np.float64)
        if float(np.sum(weights)) <= 0.0:
            value = float(peak)
        else:
            value = float(
                np.sum(coordinates * weights) / np.sum(weights)
            )
        candidates.append(value)
        suppress_lo = max(0, peak - minimum_separation)
        suppress_hi = min(len(work), peak + minimum_separation + 1)
        work[suppress_lo:suppress_hi] = 0.0
    return sorted(candidates)


def locate_pair(
    ink: np.ndarray,
    expected_center_x: float,
    expected_zone_y: float,
) -> dict[str, dict[str, float]]:
    # The stale V5 map shifts the left-column shapes by more than 10 mm.
    half_width = round(28.0 * PX_PER_MM)
    half_height = round(20.0 * PX_PER_MM)
    x0 = max(0, round(expected_center_x - half_width))
    x1 = min(ink.shape[1], round(expected_center_x + half_width))
    y0 = max(0, round(expected_zone_y - half_height))
    y1 = min(ink.shape[0], round(expected_zone_y + half_height))
    roi = ink[y0:y1, x0:x1]
    horizontal_edges = [
        y0 + value
        for value in projection_peaks(
            roi.sum(axis=1), count=4, minimum_separation=12
        )
    ]
    rectangles = {
        "CCW": {
            "top": horizontal_edges[0],
            "bottom": horizontal_edges[1],
        },
        "CW": {
            "top": horizontal_edges[2],
            "bottom": horizontal_edges[3],
        },
    }
    split_x = max(1, min(x1 - x0 - 1, round(expected_center_x) - x0))
    for edges in rectangles.values():
        top = round(edges["top"] + 6.0)
        bottom = round(edges["bottom"] - 6.0)
        vertical_projection = ink[top:bottom, x0:x1].sum(axis=0)
        edges["left"] = x0 + strongest_projection_peak(
            vertical_projection, 0, split_x
        )
        edges["right"] = x0 + strongest_projection_peak(
            vertical_projection, split_x, x1 - x0
        )
    return rectangles


def motion_direction(rectangle_direction: str, side: str) -> str:
    if rectangle_direction == "CCW":
        return {
            "bottom": "+X",
            "right": "+Y",
            "top": "-X",
            "left": "-Y",
        }[side]
    return {
        "left": "+Y",
        "top": "+X",
        "right": "-Y",
        "bottom": "-X",
    }[side]


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

    records = []
    annotated = rectified.copy()
    colors = {
        "CCW": (220, 80, 30),
        "CW": (30, 60, 220),
    }
    index = 0
    for row_name, center_y_mm in ROWS:
        for column_name, center_x_mm in COLUMNS:
            center_x, zone_y = expected_pixel(
                (center_x_mm, center_y_mm)
            )
            located = locate_pair(ink, center_x, zone_y)
            for direction in ("CCW", "CW"):
                index += 1
                edges = located[direction]
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
                expected_center_y_mm = (
                    center_y_mm + PAIR_OFFSET_Y_MM
                    if direction == "CCW"
                    else center_y_mm - PAIR_OFFSET_Y_MM
                )
                measurement.update(
                    {
                        "index": index,
                        "zone": f"{row_name}_{column_name}",
                        "row": row_name,
                        "column": column_name,
                        "direction": direction,
                        "center_paper_mm": [
                            center_x_mm,
                            expected_center_y_mm,
                        ],
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

    direction_curve_samples = {
        direction: [] for direction in ("+X", "-X", "+Y", "-Y")
    }
    for record in records:
        for side, curve in record["edge_curve95_mm"].items():
            direction_curve_samples[
                motion_direction(record["direction"], side)
            ].append(curve)

    pair_differences = []
    for row_name, _ in ROWS:
        for column_name, _ in COLUMNS:
            zone = f"{row_name}_{column_name}"
            ccw = next(
                item
                for item in records
                if item["zone"] == zone and item["direction"] == "CCW"
            )
            cw = next(
                item
                for item in records
                if item["zone"] == zone and item["direction"] == "CW"
            )
            pair_differences.append(
                {
                    "zone": zone,
                    "cw_minus_ccw_width_mm": (
                        cw["width_mean_mm"] - ccw["width_mean_mm"]
                    ),
                    "cw_minus_ccw_height_mm": (
                        cw["height_mean_mm"] - ccw["height_mean_mm"]
                    ),
                    "cw_minus_ccw_orthogonality_deg": (
                        cw["orthogonality_error_deg"]
                        - ccw["orthogonality_error_deg"]
                    ),
                }
            )

    by_direction = {}
    for direction in ("CCW", "CW"):
        selected = [
            item for item in records if item["direction"] == direction
        ]
        by_direction[direction] = {
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

    summary = {
        "photo": str(PHOTO),
        "photo_page_corners_px": PHOTO_PAGE_CORNERS.tolist(),
        "connection_lines": False,
        "nominal_rectangle_mm": [RECT_WIDTH_MM, RECT_HEIGHT_MM],
        "rectangles": records,
        "pair_differences": pair_differences,
        "summary": {
            "by_rectangle_direction": by_direction,
            "mean_edge_curve95_by_motion_direction_mm": {
                direction: float(np.mean(values))
                for direction, values in direction_curve_samples.items()
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
            "A4 homography removes camera perspective. Pair comparisons are "
            "more reliable than absolute millimetres because the top paper "
            "edge is partly hidden by the clipboard."
        ),
    }
    OUTPUT_JSON.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    cv2.imwrite(str(OUTPUT_ANNOTATED), annotated)
    print(json.dumps(summary["summary"], ensure_ascii=False, indent=2))
    for difference in pair_differences:
        print(
            f"{difference['zone']} "
            f"dW={difference['cw_minus_ccw_width_mm']:+.2f}mm "
            f"dH={difference['cw_minus_ccw_height_mm']:+.2f}mm "
            "dOrth="
            f"{difference['cw_minus_ccw_orthogonality_deg']:+.2f}deg"
        )
    print(OUTPUT_JSON)
    print(OUTPUT_RECTIFIED)
    print(OUTPUT_ANNOTATED)


if __name__ == "__main__":
    main()
