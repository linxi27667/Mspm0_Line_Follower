#!/usr/bin/env python3
"""Measure the nine V47 rectangles from one perspective photo."""

from __future__ import annotations

import json
import math
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
PHOTO = ROOT / "docs" / "diagnostics" / "V47_3X3_RECT_PHOTO_20260725.jpg"
OUTPUT_JSON = (
    ROOT / "docs" / "diagnostics" / "V47_3X3_RECT_PHOTO_ANALYSIS.json"
)
OUTPUT_RECTIFIED = (
    ROOT / "docs" / "diagnostics" / "V47_3X3_RECT_RECTIFIED.png"
)
OUTPUT_ANNOTATED = (
    ROOT / "docs" / "diagnostics" / "V47_3X3_RECT_ANALYZED.png"
)

PX_PER_MM = 5.0
WARP_WIDTH = round(210.0 * PX_PER_MM)
WARP_HEIGHT = round(297.0 * PX_PER_MM)

# The transparent ruler hides most of the right paper edge.  These four
# endpoints are the visible A4 boundary intersections in this photo.
PHOTO_PAGE_CORNERS = np.float32(
    [
        [105.0, 166.0],
        [1052.0, 166.0],
        [1024.0, 1564.0],
        [81.0, 1564.0],
    ]
)
WARP_PAGE_CORNERS = np.float32(
    [
        [0.0, 0.0],
        [WARP_WIDTH - 1.0, 0.0],
        [WARP_WIDTH - 1.0, WARP_HEIGHT - 1.0],
        [0.0, WARP_HEIGHT - 1.0],
    ]
)

COLUMNS = (("LEFT", 50.0), ("CENTER", 105.0), ("RIGHT", 160.0))
ROWS = (("TOP", 205.0), ("MIDDLE", 130.0), ("BOTTOM", 55.0))
RECT_WIDTH_MM = 30.0
RECT_HEIGHT_MM = 20.0


def expected_pixel(point_mm: tuple[float, float]) -> tuple[float, float]:
    return point_mm[0] * PX_PER_MM, (297.0 - point_mm[1]) * PX_PER_MM


def robust_polyfit(
    independent: np.ndarray,
    dependent: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    keep = np.ones(len(independent), dtype=bool)
    for _ in range(4):
        coefficients = np.polyfit(independent[keep], dependent[keep], 1)
        residual = dependent - np.polyval(coefficients, independent)
        center = np.median(residual[keep])
        deviation = np.median(np.abs(residual[keep] - center))
        limit = max(2.0, 3.5 * 1.4826 * deviation)
        keep = np.abs(residual - center) <= limit
    return coefficients, keep


def make_ink_mask(gray: np.ndarray) -> np.ndarray:
    """Find thin pen strokes while rejecting slow paper/lighting gradients."""
    background = cv2.GaussianBlur(gray, (0, 0), 11.0)
    contrast = background.astype(np.int16) - gray.astype(np.int16)
    return np.logical_and(contrast >= 5, gray <= 205)


def strongest_projection_peak(
    projection: np.ndarray,
    start: int,
    stop: int,
) -> float:
    values = projection[start:stop]
    if len(values) == 0:
        raise AssertionError("empty projection search range")
    peak = start + int(np.argmax(values))
    lo = max(start, peak - 2)
    hi = min(stop, peak + 3)
    weights = projection[lo:hi].astype(np.float64)
    if float(np.sum(weights)) <= 0.0:
        raise AssertionError("no ink in projection search range")
    coordinates = np.arange(lo, hi, dtype=np.float64)
    return float(np.sum(coordinates * weights) / np.sum(weights))


def locate_rectangle(
    ink: np.ndarray,
    expected_center_x: float,
    expected_center_y: float,
) -> dict[str, float]:
    """Locate four edges inside a broad grid-cell ROI.

    The old spatial map shifts some rectangles by several millimetres, so edge
    tracing must not begin at the nominal G-code coordinate.
    """
    half_width = round(26.0 * PX_PER_MM)
    half_height = round(20.0 * PX_PER_MM)
    x0 = max(0, round(expected_center_x - half_width))
    x1 = min(ink.shape[1], round(expected_center_x + half_width))
    y0 = max(0, round(expected_center_y - half_height))
    y1 = min(ink.shape[0], round(expected_center_y + half_height))
    roi = ink[y0:y1, x0:x1]
    row_projection = roi.sum(axis=1)
    column_projection = roi.sum(axis=0)
    split_x = max(1, min(x1 - x0 - 1, round(expected_center_x) - x0))
    split_y = max(1, min(y1 - y0 - 1, round(expected_center_y) - y0))
    return {
        "top": y0
        + strongest_projection_peak(row_projection, 0, split_y),
        "bottom": y0
        + strongest_projection_peak(
            row_projection, split_y, y1 - y0
        ),
        "left": x0
        + strongest_projection_peak(column_projection, 0, split_x),
        "right": x0
        + strongest_projection_peak(
            column_projection, split_x, x1 - x0
        ),
    }


def trace_horizontal(
    ink: np.ndarray,
    left_x: float,
    right_x: float,
    expected_y: float,
) -> np.ndarray:
    # Trim corners so the vertical strokes cannot be selected.  This also
    # excludes the bottom-row travel/connection line outside each rectangle.
    x0 = round(left_x + 8.0)
    x1 = round(right_x - 8.0)
    band = 14
    y0 = max(0, round(expected_y - band))
    y1 = min(ink.shape[0], round(expected_y + band + 1))
    local = ink[y0:y1, x0 : x1 + 1]
    points = []
    for column, x in enumerate(range(x0, x1 + 1)):
        values = local[:, column]
        candidates = np.flatnonzero(values)
        if len(candidates) == 0:
            continue
        y_candidates = y0 + candidates
        closest = int(
            y_candidates[np.argmin(np.abs(y_candidates - expected_y))]
        )
        points.append((float(x), float(closest)))
    result = np.asarray(points, dtype=np.float64)
    if len(result) < 50:
        raise AssertionError(
            "not enough horizontal edge pixels "
            f"left_x={left_x:.1f} right_x={right_x:.1f} "
            f"expected_y={expected_y:.1f} count={len(result)}"
        )
    _, keep = robust_polyfit(result[:, 0], result[:, 1])
    return result[keep]


def trace_vertical(
    ink: np.ndarray,
    expected_x: float,
    top_y: float,
    bottom_y: float,
    min_points: int = 35,
) -> np.ndarray:
    y0 = round(top_y + 8.0)
    y1 = round(bottom_y - 8.0)
    band = 14
    x0 = max(0, round(expected_x - band))
    x1 = min(ink.shape[1], round(expected_x + band + 1))
    local = ink[y0 : y1 + 1, x0:x1]
    points = []
    for row, y in enumerate(range(y0, y1 + 1)):
        values = local[row, :]
        candidates = np.flatnonzero(values)
        if len(candidates) == 0:
            continue
        x_candidates = x0 + candidates
        closest = int(
            x_candidates[np.argmin(np.abs(x_candidates - expected_x))]
        )
        points.append((float(closest), float(y)))
    result = np.asarray(points, dtype=np.float64)
    if len(result) < min_points:
        raise AssertionError(
            "not enough vertical edge pixels "
            f"expected_x={expected_x:.1f} top_y={top_y:.1f} "
            f"bottom_y={bottom_y:.1f} count={len(result)}"
        )
    _, keep = robust_polyfit(result[:, 1], result[:, 0])
    return result[keep]


def transform_points(points: np.ndarray, transform: np.ndarray) -> np.ndarray:
    return cv2.perspectiveTransform(
        points.astype(np.float32)[None, :, :], transform
    )[0].astype(np.float64)


def line_fit(
    points: np.ndarray,
    horizontal: bool,
) -> tuple[np.ndarray, float, float]:
    if horizontal:
        independent = points[:, 0]
        dependent = points[:, 1]
    else:
        independent = points[:, 1]
        dependent = points[:, 0]
    coefficients, keep = robust_polyfit(independent, dependent)
    residual = dependent[keep] - np.polyval(
        coefficients, independent[keep]
    )
    return (
        coefficients,
        float(np.percentile(np.abs(residual), 95.0) / PX_PER_MM),
        float(np.max(np.abs(residual)) / PX_PER_MM),
    )


def intersection(
    horizontal: np.ndarray,
    vertical: np.ndarray,
) -> np.ndarray:
    # y = a*x + b; x = c*y + d
    a, b = horizontal
    c, d = vertical
    denominator = 1.0 - a * c
    y = (a * d + b) / denominator
    x = c * y + d
    return np.asarray((x, y), dtype=np.float64)


def measure_rectangle(
    traces: dict[str, np.ndarray],
) -> tuple[dict, dict[str, np.ndarray]]:
    top_fit, top_curve95, top_curve_max = line_fit(
        traces["top"], horizontal=True
    )
    bottom_fit, bottom_curve95, bottom_curve_max = line_fit(
        traces["bottom"], horizontal=True
    )
    left_fit, left_curve95, left_curve_max = line_fit(
        traces["left"], horizontal=False
    )
    right_fit, right_curve95, right_curve_max = line_fit(
        traces["right"], horizontal=False
    )
    corners = {
        "top_left": intersection(top_fit, left_fit),
        "top_right": intersection(top_fit, right_fit),
        "bottom_right": intersection(bottom_fit, right_fit),
        "bottom_left": intersection(bottom_fit, left_fit),
    }
    width_top = np.linalg.norm(corners["top_right"] - corners["top_left"])
    width_bottom = np.linalg.norm(
        corners["bottom_right"] - corners["bottom_left"]
    )
    height_left = np.linalg.norm(
        corners["bottom_left"] - corners["top_left"]
    )
    height_right = np.linalg.norm(
        corners["bottom_right"] - corners["top_right"]
    )
    horizontal_angle = math.degrees(
        math.atan((top_fit[0] + bottom_fit[0]) / 2.0)
    )
    vertical_angle = math.degrees(
        math.atan((left_fit[0] + right_fit[0]) / 2.0)
    )
    orthogonality_error = abs(horizontal_angle + vertical_angle)
    curve95 = {
        "top": top_curve95,
        "right": right_curve95,
        "bottom": bottom_curve95,
        "left": left_curve95,
    }
    curve_max = {
        "top": top_curve_max,
        "right": right_curve_max,
        "bottom": bottom_curve_max,
        "left": left_curve_max,
    }
    result = {
        "width_top_mm": float(width_top / PX_PER_MM),
        "width_bottom_mm": float(width_bottom / PX_PER_MM),
        "width_mean_mm": float((width_top + width_bottom) / 2.0 / PX_PER_MM),
        "height_left_mm": float(height_left / PX_PER_MM),
        "height_right_mm": float(height_right / PX_PER_MM),
        "height_mean_mm": float(
            (height_left + height_right) / 2.0 / PX_PER_MM
        ),
        "horizontal_angle_deg": horizontal_angle,
        "vertical_shear_deg": vertical_angle,
        "orthogonality_error_deg": orthogonality_error,
        "edge_curve95_mm": curve95,
        "edge_curve_max_mm": curve_max,
        "edge_curve95_worst_mm": max(curve95.values()),
        "edge_curve_max_worst_mm": max(curve_max.values()),
        "corners_rectified_px": {
            name: [float(value) for value in point]
            for name, point in corners.items()
        },
    }
    fits = {
        "top": top_fit,
        "bottom": bottom_fit,
        "left": left_fit,
        "right": right_fit,
    }
    return result, fits


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

    raw_records = []
    measured_centers = []
    expected_centers = []
    for row_name, center_y_mm in ROWS:
        for column_name, center_x_mm in COLUMNS:
            center_x, center_y = expected_pixel(
                (center_x_mm, center_y_mm)
            )
            edges = locate_rectangle(ink, center_x, center_y)
            traces = {
                "top": trace_horizontal(
                    ink, edges["left"], edges["right"], edges["top"]
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
                ),
                "right": trace_vertical(
                    ink,
                    edges["right"],
                    edges["top"],
                    edges["bottom"],
                ),
            }
            provisional, _ = measure_rectangle(traces)
            corners = np.asarray(
                list(provisional["corners_rectified_px"].values()),
                dtype=np.float64,
            )
            measured_centers.append(np.mean(corners, axis=0))
            expected_centers.append((center_x, center_y))
            raw_records.append(
                {
                    "zone": f"{row_name}_{column_name}",
                    "row": row_name,
                    "column": column_name,
                    "center_paper_mm": [center_x_mm, center_y_mm],
                    "located_edges_rectified_px": edges,
                    "traces": traces,
                }
            )

    grid_transform, _ = cv2.findHomography(
        np.asarray(measured_centers, dtype=np.float32),
        np.asarray(expected_centers, dtype=np.float32),
        method=0,
    )
    if grid_transform is None:
        raise AssertionError("grid homography failed")

    annotated = rectified.copy()
    results = []
    colors = {
        "top": (20, 80, 230),
        "right": (40, 170, 40),
        "bottom": (230, 80, 20),
        "left": (190, 40, 190),
    }
    for index, record in enumerate(raw_records, start=1):
        corrected_traces = {
            name: transform_points(points, grid_transform)
            for name, points in record["traces"].items()
        }
        measurement, _ = measure_rectangle(corrected_traces)
        measurement.update(
            {
                "index": index,
                "zone": record["zone"],
                "row": record["row"],
                "column": record["column"],
                "center_paper_mm": record["center_paper_mm"],
            }
        )
        results.append(measurement)
        for side, points in record["traces"].items():
            for point in points[::4]:
                cv2.circle(
                    annotated,
                    (round(point[0]), round(point[1])),
                    1,
                    colors[side],
                    -1,
                )

    summary = {
        "photo": str(PHOTO),
        "photo_page_corners_px": PHOTO_PAGE_CORNERS.tolist(),
        "rectification": (
            "A4 boundary homography followed by nine-center global homography"
        ),
        "connection_line_included": False,
        "connection_line_exclusion": (
            "Each side is sampled only between inset corners; ink outside a "
            "rectangle, including the lower-row connection line, is ignored."
        ),
        "nominal_rectangle_mm": [RECT_WIDTH_MM, RECT_HEIGHT_MM],
        "rectangles": results,
        "summary": {
            "width_mean_range_mm": [
                min(item["width_mean_mm"] for item in results),
                max(item["width_mean_mm"] for item in results),
            ],
            "height_mean_range_mm": [
                min(item["height_mean_mm"] for item in results),
                max(item["height_mean_mm"] for item in results),
            ],
            "orthogonality_error_max_deg": max(
                item["orthogonality_error_deg"] for item in results
            ),
            "edge_curve95_max_mm": max(
                item["edge_curve95_worst_mm"] for item in results
            ),
            "edge_curve_max_mm": max(
                item["edge_curve_max_worst_mm"] for item in results
            ),
            "edge_curve95_mean_by_side_mm": {
                side: float(
                    np.mean(
                        [
                            item["edge_curve95_mm"][side]
                            for item in results
                        ]
                    )
                )
                for side in ("top", "right", "bottom", "left")
            },
            "mean_size_by_row_mm": {
                row: {
                    "width": float(
                        np.mean(
                            [
                                item["width_mean_mm"]
                                for item in results
                                if item["row"] == row
                            ]
                        )
                    ),
                    "height": float(
                        np.mean(
                            [
                                item["height_mean_mm"]
                                for item in results
                                if item["row"] == row
                            ]
                        )
                    ),
                }
                for row in ("TOP", "MIDDLE", "BOTTOM")
            },
        },
    }
    OUTPUT_JSON.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    cv2.imwrite(str(OUTPUT_ANNOTATED), annotated)
    print(json.dumps(summary["summary"], ensure_ascii=False, indent=2))
    for item in results:
        print(
            f"{item['index']} {item['zone']} "
            f"W={item['width_mean_mm']:.2f} "
            f"H={item['height_mean_mm']:.2f} "
            f"orth={item['orthogonality_error_deg']:.2f}deg "
            f"curve95={item['edge_curve95_worst_mm']:.2f}mm"
        )
    print(OUTPUT_JSON)
    print(OUTPUT_RECTIFIED)
    print(OUTPUT_ANNOTATED)


if __name__ == "__main__":
    main()
