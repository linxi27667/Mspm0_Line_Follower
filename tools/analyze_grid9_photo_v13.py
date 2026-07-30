"""Measure the nine V13 test quadrilaterals from a photographed A4 sheet.

The script rectifies the photographed paper to 210 x 297 mm, detects the two
mostly-horizontal and two mostly-vertical strokes in each region, intersects
their fitted center lines, and reports the observed paper-frame side vectors.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import cv2
import numpy as np


PAPER_WIDTH_MM = 210.0
PAPER_HEIGHT_MM = 297.0
PIXELS_PER_MM = 5.0

# Approximate centers in the rectified photograph. These select each local
# quadrilateral; all final vertices come from detected ink lines.
REGION_CENTERS_IMAGE_MM = {
    "R11": (16.0, 74.0),
    "R12": (80.0, 74.0),
    "R13": (148.0, 67.0),
    "R23": (149.0, 153.0),
    "R22": (80.0, 160.0),
    "R21": (18.0, 168.0),
    "R31": (12.0, 235.0),
    "R32": (79.0, 228.0),
    "R33": (147.0, 220.0),
}
REGION_ORDER = tuple(REGION_CENTERS_IMAGE_MM)


def order_quad(points: np.ndarray) -> np.ndarray:
    """Return top-left, top-right, bottom-right, bottom-left."""
    points = points.astype(np.float32)
    sums = points.sum(axis=1)
    differences = np.diff(points, axis=1).reshape(-1)
    return np.array(
        (
            points[np.argmin(sums)],
            points[np.argmin(differences)],
            points[np.argmax(sums)],
            points[np.argmax(differences)],
        ),
        dtype=np.float32,
    )


def find_paper_quad(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    mask = np.where(gray > 150, 255, 0).astype(np.uint8)
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_CLOSE, np.ones((31, 31), np.uint8)
    )
    contours, _ = cv2.findContours(
        mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        raise RuntimeError("paper contour not found")
    contour = max(contours, key=cv2.contourArea)
    perimeter = cv2.arcLength(contour, True)
    polygon = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
    if polygon.shape[0] != 4:
        raise RuntimeError(
            f"paper contour did not reduce to four corners: {polygon.shape}"
        )
    return order_quad(polygon.reshape(-1, 2))


def rectify(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    source = find_paper_quad(image)
    width = round(PAPER_WIDTH_MM * PIXELS_PER_MM)
    height = round(PAPER_HEIGHT_MM * PIXELS_PER_MM)
    destination = np.array(
        ((0, 0), (width, 0), (width, height), (0, height)),
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(source, destination)
    return (
        cv2.warpPerspective(image, transform, (width, height)),
        source,
    )


def two_clusters(
    records: list[tuple[float, float, float]],
) -> tuple[list[tuple[float, float, float]], ...]:
    """Return the two outer ink-line clusters.

    Region transitions can cross a square and create a third internal line.
    The square boundary is therefore selected from the two outer spatial
    clusters rather than forcing every Hough segment into two k-means groups.
    """
    if len(records) < 2:
        raise RuntimeError("not enough detected line records")
    ordered = sorted(records, key=lambda record: record[0])
    spatial_groups: list[list[tuple[float, float, float]]] = []
    for record in ordered:
        if (
            not spatial_groups
            or record[0] - spatial_groups[-1][-1][0] > 2.5
        ):
            spatial_groups.append([record])
        else:
            spatial_groups[-1].append(record)
    strong_groups = [
        group
        for group in spatial_groups
        if sum(record[2] for record in group) >= 7.0
    ]
    if len(strong_groups) < 2:
        raise RuntimeError("fewer than two strong outer line clusters")
    return strong_groups[0], strong_groups[-1]


def weighted_line(
    records: list[tuple[float, float, float]], center_coordinate: float
) -> tuple[float, float]:
    """Return slope/intercept from intercept-at-center records."""
    weights = np.array([record[2] for record in records])
    positions = np.array([record[0] for record in records])
    slopes = np.array([record[1] for record in records])
    slope = float(np.average(slopes, weights=weights))
    position = float(np.average(positions, weights=weights))
    intercept = position - slope * center_coordinate
    return slope, intercept


def intersect(
    horizontal: tuple[float, float],
    vertical: tuple[float, float],
) -> tuple[float, float]:
    """Intersect y=a*x+b with x=c*y+d in paper coordinates."""
    a, b = horizontal
    c, d = vertical
    denominator = 1.0 - c * a
    if abs(denominator) < 1e-6:
        raise RuntimeError("nearly parallel fitted sides")
    x = (c * b + d) / denominator
    return x, a * x + b


def detect_region(
    rectified: np.ndarray, name: str
) -> tuple[tuple[float, float], ...]:
    center_x, center_image_y = REGION_CENTERS_IMAGE_MM[name]
    half_size_mm = 20.0
    scale = PIXELS_PER_MM
    x0 = max(0, round((center_x - half_size_mm) * scale))
    x1 = min(
        rectified.shape[1], round((center_x + half_size_mm) * scale)
    )
    y0 = max(0, round((center_image_y - half_size_mm) * scale))
    y1 = min(
        rectified.shape[0],
        round((center_image_y + half_size_mm) * scale),
    )
    crop = rectified[y0:y1, x0:x1]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 40, 100)
    detected = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 360.0,
        threshold=25,
        minLineLength=35,
        maxLineGap=12,
    )
    if detected is None:
        raise RuntimeError(f"{name}: no lines detected")

    horizontal_records: list[tuple[float, float, float]] = []
    vertical_records: list[tuple[float, float, float]] = []
    center_paper_y = PAPER_HEIGHT_MM - center_image_y
    for local_x1, local_y1, local_x2, local_y2 in detected.reshape(-1, 4):
        image_x1 = (x0 + int(local_x1)) / scale
        image_x2 = (x0 + int(local_x2)) / scale
        paper_y1 = PAPER_HEIGHT_MM - (y0 + int(local_y1)) / scale
        paper_y2 = PAPER_HEIGHT_MM - (y0 + int(local_y2)) / scale
        dx = image_x2 - image_x1
        dy = paper_y2 - paper_y1
        length = math.hypot(dx, dy)
        if length < 7.0:
            continue
        if abs(dy) <= math.tan(math.radians(20.0)) * abs(dx):
            slope = dy / dx
            intercept_at_center = (
                paper_y1 + slope * (center_x - image_x1)
            )
            horizontal_records.append(
                (intercept_at_center, slope, length)
            )
        elif abs(dx) <= math.tan(math.radians(20.0)) * abs(dy):
            slope = dx / dy
            intercept_at_center = (
                image_x1 + slope * (center_paper_y - paper_y1)
            )
            if (
                name != "R31"
                and (
                    intercept_at_center < 1.5
                    or intercept_at_center > PAPER_WIDTH_MM - 1.5
                )
            ):
                # Exclude the rectified paper edge from left-column ROIs.
                continue
            vertical_records.append((intercept_at_center, slope, length))

    horizontal_groups = two_clusters(horizontal_records)
    vertical_groups = two_clusters(vertical_records)
    horizontals = sorted(
        (
            weighted_line(group, center_x)
            for group in horizontal_groups
        ),
        key=lambda line: line[0] * center_x + line[1],
    )
    verticals = sorted(
        (
            weighted_line(group, center_paper_y)
            for group in vertical_groups
        ),
        key=lambda line: line[0] * center_paper_y + line[1],
    )
    bottom, top = horizontals
    left, right = verticals
    return (
        intersect(bottom, left),
        intersect(bottom, right),
        intersect(top, right),
        intersect(top, left),
    )


def vector(
    start: tuple[float, float], end: tuple[float, float]
) -> tuple[float, float]:
    return end[0] - start[0], end[1] - start[1]


def annotate(
    rectified: np.ndarray,
    measured: dict[str, tuple[tuple[float, float], ...]],
) -> np.ndarray:
    result = rectified.copy()
    scale = PIXELS_PER_MM
    colors = (
        (0, 0, 255),
        (0, 128, 255),
        (0, 255, 0),
        (255, 0, 0),
    )
    for name, vertices in measured.items():
        pixels = [
            (
                round(point[0] * scale),
                round((PAPER_HEIGHT_MM - point[1]) * scale),
            )
            for point in vertices
        ]
        for index, (start, end) in enumerate(
            zip(pixels, pixels[1:] + pixels[:1])
        ):
            cv2.line(result, start, end, colors[index], 2)
        cv2.putText(
            result,
            name,
            pixels[2],
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 0, 255),
            2,
            cv2.LINE_AA,
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("photo", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tmp/grid9_v13_measured.png"),
    )
    args = parser.parse_args()
    image = cv2.imread(str(args.photo))
    if image is None:
        raise FileNotFoundError(args.photo)
    rectified, paper_quad = rectify(image)
    measured = {
        name: detect_region(rectified, name) for name in REGION_ORDER
    }
    print("paper_quad_px=" + repr(paper_quad.tolist()))
    for name, vertices in measured.items():
        closed = vertices + (vertices[0],)
        sides = [
            vector(start, end) for start, end in zip(closed, closed[1:])
        ]
        lengths = [math.hypot(*side) for side in sides]
        print(
            f"{name} vertices="
            + ",".join(f"({x:.3f},{y:.3f})" for x, y in vertices)
        )
        print(
            f"{name} sides="
            + ",".join(f"({x:.3f},{y:.3f})" for x, y in sides)
            + " lengths="
            + ",".join(f"{length:.3f}" for length in lengths)
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(args.output), annotate(rectified, measured))
    print(f"annotated={args.output.resolve()}")


if __name__ == "__main__":
    main()
