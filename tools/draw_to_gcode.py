#!/usr/bin/env python3
"""Convert raster images or SVG artwork to writer-safe standard A4 G-code.

This is a host-side converter only. It never opens a serial port and never
changes firmware. Output coordinates are nominal physical A4 millimetres;
the writer firmware remains responsible for the paper calibration map.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
    from svgelements import Move, Path as SvgPath, SVG, Shape
except ImportError:  # pragma: no cover - exercised by the CLI error path.
    Move = SvgPath = SVG = Shape = None


SOURCE_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path.cwd() if getattr(sys, "frozen", False) else SOURCE_ROOT
TOOL_ID = "WRITER_DRAW_TO_GCODE_V1"
REQUIRED_FIRMWARE_ID = "PAPER_A4_CLOUD_GCODE_DIRECT_V36"
REQUIRED_PAPER_MAP_ID = "A4_BASE_QUADRATIC_XSCALE_NO_SBOW_Y45_265_TRIAL_V9"

A4_WIDTH_MM = 210.0
A4_HEIGHT_MM = 297.0
FIRMWARE_X_MIN_MM = 25.0
FIRMWARE_X_MAX_MM = 185.0
FIRMWARE_Y_MIN_MM = 45.0
FIRMWARE_Y_MAX_MM = 265.0
VERIFIED_Y_MIN_MM = 130.0
VERIFIED_Y_MAX_MM = 235.0

DEFAULT_LEFT_MM = 30.0
DEFAULT_BOTTOM_MM = 135.0
DEFAULT_WIDTH_MM = 150.0
DEFAULT_HEIGHT_MM = 95.0
DEFAULT_FEED_MM_MIN = 300.0
DEFAULT_APPROACH_MM = 5.0
PEN_SETTLE_SECONDS = 0.7
PREVIEW_PIXELS_PER_MM = 4.0

# Current V33/V8 machine profile. verify_repository_contract() prevents this
# host-side audit model from silently running against a different firmware map.
L1_MM = 205.0
L2_MM = 203.0
OFFSET_X_MM = -129.0
OFFSET_Y_MM = 128.0
THETA_MIN_DEG = -0.773082 + 1.0
PSI_MIN_DEG = 134.177381 + 1.0
THETA_MAX_DEG = 135.0
PSI_MAX_DEG = 255.0
BETA_MIN_DEG = 1.0
BETA_MAX_DEG = 179.0
WORKSPACE_SHIFT_X_MM = 0.0
WORKSPACE_SHIFT_Y_MM = 15.0
X_SCALE_OBSERVED = 1.03125
LEGACY_Y_SHIFT_MM = 15.0
BASE_MAP_X = (
    290.945962,
    62.273998,
    -78.732064,
    -3.922490,
    -2.442049,
    5.239680,
)
BASE_MAP_Y = (
    30.887338,
    84.802037,
    52.883179,
    -7.669222,
    3.617273,
    3.846007,
)

Point = tuple[float, float]
Bounds = tuple[float, float, float, float]


class ConversionError(ValueError):
    """A user-facing conversion or safety failure."""


@dataclass(frozen=True)
class PlotPath:
    points: tuple[Point, ...]
    closed: bool
    kind: str


@dataclass(frozen=True)
class PlannedPath:
    points: tuple[Point, ...]
    approach: Point
    kind: str


@dataclass(frozen=True)
class SourceArtwork:
    paths: tuple[PlotPath, ...]
    metadata: dict[str, object]


@dataclass(frozen=True)
class ConversionConfig:
    input_path: Path
    output_path: Path
    preview_path: Path
    vector_path: Path
    manifest_path: Path
    mode: str
    left_mm: float
    bottom_mm: float
    width_mm: float
    height_mm: float
    rotate_deg: float
    threshold: int | None
    invert: bool
    blur_px: int
    canny_low: int
    canny_high: int
    hatch_spacing_mm: float
    simplify_mm: float
    curve_step_mm: float
    min_path_mm: float
    approach_mm: float
    feed_mm_min: float
    optimize: bool
    allow_unverified_area: bool
    minimum_joint_margin_deg: float
    max_paths: int
    max_points: int
    force: bool


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def point_distance(first: Point, second: Point) -> float:
    return math.hypot(second[0] - first[0], second[1] - first[1])


def path_length(points: Sequence[Point]) -> float:
    return sum(point_distance(a, b) for a, b in zip(points, points[1:]))


def points_bounds(paths: Iterable[PlotPath | PlannedPath]) -> Bounds:
    points = [point for path in paths for point in path.points]
    if not points:
        raise ConversionError("no drawable points were generated")
    return (
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )


def verify_repository_contract() -> None:
    """Fail if the checked host audit profile no longer matches the source."""

    if getattr(sys, "frozen", False):
        return
    gcode_header = (SOURCE_ROOT / "TASK" / "gcode_serial.h").read_text(
        encoding="utf-8"
    )
    map_header = (SOURCE_ROOT / "APP" / "Inc" / "app_writer_paper_map.h").read_text(
        encoding="utf-8"
    )
    map_source = (SOURCE_ROOT / "APP" / "Src" / "app_writer_paper_map.c").read_text(
        encoding="utf-8"
    )
    motion_header = (SOURCE_ROOT / "APP" / "Inc" / "app_writer_motion.h").read_text(
        encoding="utf-8"
    )
    gcode_source = (SOURCE_ROOT / "TASK" / "gcode_serial.c").read_text(
        encoding="utf-8"
    )
    required_gcode_tokens = (
        f'"{REQUIRED_FIRMWARE_ID}"',
        "#define GCODE_SERIAL_WORKSPACE_SHIFT_X_MM     (0.0f)",
        "#define GCODE_SERIAL_WORKSPACE_SHIFT_Y_MM     (15.0f)",
        "#define GCODE_SERIAL_PAPER_MAP_ENABLE         (1u)",
    )
    required_map_tokens = (
        f'"{REQUIRED_PAPER_MAP_ID}"',
        "#define APP_WRITER_PAPER_X_MIN_MM             (25.0f)",
        "#define APP_WRITER_PAPER_X_MAX_MM             (185.0f)",
        "#define APP_WRITER_PAPER_Y_MIN_MM             (45.0f)",
        "#define APP_WRITER_PAPER_Y_MAX_MM             (265.0f)",
        "#define APP_WRITER_PAPER_GRID_CORRECTION_ENABLE (0u)",
        "#define APP_WRITER_PAPER_S_BOW_CORRECTION_ENABLE (0u)",
        "#define APP_WRITER_PAPER_X_SCALE_OBSERVED      (1.03125f)",
        "#define APP_WRITER_PAPER_LEGACY_Y_SHIFT_MM     (15.0f)",
    )
    required_source_tokens = (
        "290.945962f, 62.273998f, -78.732064f",
        "30.887338f, 84.802037f, 52.883179f",
    )
    required_motion_tokens = (
        "#define APP_WRITER_L1_MM                    (205.0f)",
        "#define APP_WRITER_L2_MM                    (203.0f)",
        "#define APP_WRITER_AUTHOR_BASELINE_ENABLE    (1u)",
        "#define APP_WRITER_MACHINE_OFFSET_X_MM      (-129.0f)",
        "#define APP_WRITER_MACHINE_OFFSET_Y_MM      (128.0f)",
        "#define APP_WRITER_THETA_LIMIT_DEG          (-0.773082f)",
        "#define APP_WRITER_PSI_LIMIT_DEG            (134.177381f)",
        "#define APP_WRITER_HOMING_PULLOFF_DEG       (1.0f)",
        "#define APP_WRITER_A4_ENVELOPE_PROBE_ENABLE  (1u)",
        "#define APP_WRITER_THETA_MAX_DEG            (135.0f)",
        "#define APP_WRITER_PSI_MAX_DEG              (255.0f)",
        "#define APP_WRITER_BETA_MIN_DEG             (1.0f)",
        "#define APP_WRITER_BETA_MAX_DEG             (179.0f)",
    )
    missing = [
        token for token in required_gcode_tokens if token not in gcode_header
    ]
    missing.extend(token for token in required_map_tokens if token not in map_header)
    missing.extend(token for token in required_source_tokens if token not in map_source)
    missing.extend(token for token in required_motion_tokens if token not in motion_header)
    if "#define GCODE_SERIAL_PEN_SETTLE_MS         (700u)" not in gcode_source:
        missing.append("GCODE_SERIAL_PEN_SETTLE_MS=700")
    if missing:
        raise ConversionError(
            "the local firmware/map contract changed; update and revalidate the "
            f"host converter before generating motion (missing {missing[0]!r})"
        )


def decode_raster(path: Path) -> np.ndarray:
    encoded = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ConversionError(f"OpenCV could not decode {path}")
    if image.ndim == 2:
        return image
    if image.shape[2] == 4:
        color = image[:, :, :3].astype(np.float32)
        alpha = image[:, :, 3:4].astype(np.float32) / 255.0
        composited = color * alpha + 255.0 * (1.0 - alpha)
        return cv2.cvtColor(composited.astype(np.uint8), cv2.COLOR_BGR2GRAY)
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def threshold_mask(
    gray: np.ndarray,
    threshold: int | None,
    invert: bool,
) -> tuple[np.ndarray, int]:
    if threshold is None:
        actual, mask = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU
        )
        actual_threshold = int(round(actual))
    else:
        actual_threshold = threshold
        mask = np.where(gray < threshold, 255, 0).astype(np.uint8)
    if invert:
        mask = cv2.bitwise_not(mask)
    return mask, actual_threshold


def foreground_crop(mask: np.ndarray) -> tuple[np.ndarray, int, int]:
    locations = cv2.findNonZero(mask)
    if locations is None:
        raise ConversionError("the input contains no foreground after processing")
    x, y, width, height = cv2.boundingRect(locations)
    return mask[y : y + height, x : x + width], x, y


def rotated_rectangle_size(width: float, height: float, degrees: float) -> Point:
    radians = math.radians(degrees)
    cosine = abs(math.cos(radians))
    sine = abs(math.sin(radians))
    return width * cosine + height * sine, width * sine + height * cosine


def estimate_source_scale(
    width: int,
    height: int,
    config: ConversionConfig,
) -> float:
    rotated_width, rotated_height = rotated_rectangle_size(
        max(width - 1, 1), max(height - 1, 1), config.rotate_deg
    )
    return min(
        config.width_mm / max(rotated_width, 1.0e-9),
        config.height_mm / max(rotated_height, 1.0e-9),
    )


def contour_paths(
    mask: np.ndarray,
    kind: str,
    simplify_source_units: float,
) -> list[PlotPath]:
    contours, _ = cv2.findContours(
        mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE
    )
    result: list[PlotPath] = []
    epsilon = max(simplify_source_units, 0.25)
    for contour in contours:
        approximate = cv2.approxPolyDP(contour, epsilon, True)
        points = tuple(
            (float(item[0][0]), float(item[0][1])) for item in approximate
        )
        if len(points) < 3:
            continue
        result.append(PlotPath(points + (points[0],), True, kind))
    return result


def row_runs(row: np.ndarray) -> list[tuple[int, int]]:
    indexes = np.flatnonzero(row)
    if indexes.size == 0:
        return []
    breaks = np.flatnonzero(np.diff(indexes) > 1)
    starts = np.concatenate(([indexes[0]], indexes[breaks + 1]))
    ends = np.concatenate((indexes[breaks], [indexes[-1]]))
    return list(zip(starts.tolist(), ends.tolist()))


def hatch_paths(mask: np.ndarray, row_step: int) -> list[PlotPath]:
    result: list[PlotPath] = []
    reverse = False
    for y in range(0, mask.shape[0], max(1, row_step)):
        runs = row_runs(mask[y])
        if reverse:
            runs.reverse()
        for start_x, end_x in runs:
            if end_x <= start_x:
                continue
            points: tuple[Point, Point] = (
                (float(start_x), float(y)),
                (float(end_x), float(y)),
            )
            if reverse:
                points = (points[1], points[0])
            result.append(PlotPath(points, False, "hatch"))
        reverse = not reverse
    return result


def load_raster_artwork(config: ConversionConfig) -> SourceArtwork:
    gray = decode_raster(config.input_path)
    if config.blur_px > 0:
        gray = cv2.GaussianBlur(gray, (config.blur_px, config.blur_px), 0)

    if config.mode == "edge":
        processed = cv2.Canny(gray, config.canny_low, config.canny_high)
        actual_threshold: int | None = None
    else:
        processed, actual_threshold = threshold_mask(
            gray, config.threshold, config.invert
        )
    cropped, crop_x, crop_y = foreground_crop(processed)
    scale_estimate = estimate_source_scale(
        cropped.shape[1], cropped.shape[0], config
    )
    if scale_estimate <= 0.0:
        raise ConversionError("the requested output frame has zero scale")

    if config.mode == "hatch":
        row_step = max(1, round(config.hatch_spacing_mm / scale_estimate))
        paths = hatch_paths(cropped, row_step)
    else:
        paths = contour_paths(
            cropped,
            config.mode,
            config.simplify_mm / scale_estimate,
        )
    if not paths:
        raise ConversionError("image processing produced no drawable paths")
    return SourceArtwork(
        tuple(paths),
        {
            "type": "raster",
            "pixel_size": [int(gray.shape[1]), int(gray.shape[0])],
            "crop_xywh": [
                crop_x,
                crop_y,
                int(cropped.shape[1]),
                int(cropped.shape[0]),
            ],
            "threshold": actual_threshold,
            "invert": config.invert,
            "blur_px": config.blur_px,
            "canny": (
                [config.canny_low, config.canny_high]
                if config.mode == "edge"
                else None
            ),
        },
    )


def svg_shapes(path: Path) -> list[SvgPath]:
    if SVG is None or SvgPath is None or Shape is None:
        raise ConversionError(
            "SVG input requires svgelements; run "
            "'python -m pip install -r tools/draw_to_gcode_requirements.txt'"
        )
    try:
        document = SVG.parse(str(path), reify=True, parse_display_none=False)
    except Exception as exc:
        raise ConversionError(f"could not parse SVG: {exc}") from exc

    paths: list[SvgPath] = []
    for element in document.elements():
        if not isinstance(element, Shape):
            continue
        if str(getattr(element, "fill", "none")).lower() == "none" and str(
            getattr(element, "stroke", "none")
        ).lower() == "none":
            continue
        try:
            svg_path = SvgPath(element)
            svg_path.reify()
        except Exception as exc:
            raise ConversionError(
                f"could not normalize SVG element {type(element).__name__}: {exc}"
            ) from exc
        if svg_path.bbox() is not None and len(svg_path) > 0:
            paths.append(svg_path)
    if not paths:
        raise ConversionError(
            "SVG contains no drawable geometry; convert text and embedded images "
            "to paths first"
        )
    return paths


def union_svg_bounds(paths: Sequence[SvgPath]) -> Bounds:
    bounds = [path.bbox() for path in paths if path.bbox() is not None]
    if not bounds:
        raise ConversionError("SVG has no finite geometry bounds")
    return (
        min(float(item[0]) for item in bounds),
        min(float(item[1]) for item in bounds),
        max(float(item[2]) for item in bounds),
        max(float(item[3]) for item in bounds),
    )


def sample_svg_subpath(
    subpath: Iterable[object],
    scale_estimate: float,
    curve_step_mm: float,
) -> PlotPath | None:
    segments = list(subpath)
    drawable = [segment for segment in segments if not isinstance(segment, Move)]
    if not drawable:
        return None
    points: list[Point] = []
    first_start = drawable[0].start
    if first_start is not None:
        points.append((float(first_start.x), float(first_start.y)))
    for segment in drawable:
        length = float(segment.length(error=1.0e-8))
        count = max(1, math.ceil(length * scale_estimate / curve_step_mm))
        for index in range(1, count + 1):
            point = segment.point(index / count)
            points.append((float(point.x), float(point.y)))
    closed = type(drawable[-1]).__name__ == "Close"
    if closed and points and point_distance(points[0], points[-1]) > 1.0e-8:
        points.append(points[0])
    if len(points) < 2:
        return None
    return PlotPath(tuple(points), closed, "svg")


def load_svg_artwork(config: ConversionConfig) -> SourceArtwork:
    if config.mode != "outline":
        raise ConversionError(
            "SVG currently supports --mode outline; use a PNG export for edge or hatch"
        )
    paths = svg_shapes(config.input_path)
    source_bounds = union_svg_bounds(paths)
    source_width = max(source_bounds[2] - source_bounds[0], 1.0e-9)
    source_height = max(source_bounds[3] - source_bounds[1], 1.0e-9)
    rotated_width, rotated_height = rotated_rectangle_size(
        source_width, source_height, config.rotate_deg
    )
    scale_estimate = min(
        config.width_mm / max(rotated_width, 1.0e-9),
        config.height_mm / max(rotated_height, 1.0e-9),
    )
    sampled: list[PlotPath] = []
    for path in paths:
        for subpath in path.as_subpaths():
            item = sample_svg_subpath(
                subpath, scale_estimate, config.curve_step_mm
            )
            if item is not None:
                sampled.append(item)
    if not sampled:
        raise ConversionError("SVG paths collapsed to no drawable polylines")
    return SourceArtwork(
        tuple(sampled),
        {
            "type": "svg",
            "shape_count": len(paths),
            "source_bounds": list(source_bounds),
            "curve_step_mm": config.curve_step_mm,
            "note": "text and embedded raster images must be converted to paths",
        },
    )


def rotate_paths(paths: Sequence[PlotPath], degrees: float) -> tuple[PlotPath, ...]:
    if abs(degrees) <= 1.0e-12:
        return tuple(paths)
    bounds = points_bounds(paths)
    center_x = (bounds[0] + bounds[2]) / 2.0
    center_y = (bounds[1] + bounds[3]) / 2.0
    radians = math.radians(degrees)
    cosine = math.cos(radians)
    sine = math.sin(radians)

    def rotate(point: Point) -> Point:
        dx = point[0] - center_x
        dy = point[1] - center_y
        return (
            center_x + dx * cosine - dy * sine,
            center_y + dx * sine + dy * cosine,
        )

    return tuple(
        PlotPath(tuple(rotate(point) for point in path.points), path.closed, path.kind)
        for path in paths
    )


def place_paths(paths: Sequence[PlotPath], config: ConversionConfig) -> tuple[PlotPath, ...]:
    rotated = rotate_paths(paths, config.rotate_deg)
    bounds = points_bounds(rotated)
    source_width = bounds[2] - bounds[0]
    source_height = bounds[3] - bounds[1]
    if source_width <= 1.0e-12 and source_height <= 1.0e-12:
        raise ConversionError("artwork has zero width and height")
    width_scale = config.width_mm / max(source_width, 1.0e-12)
    height_scale = config.height_mm / max(source_height, 1.0e-12)
    scale = min(width_scale, height_scale)
    placed_width = source_width * scale
    placed_height = source_height * scale
    x_offset = config.left_mm + (config.width_mm - placed_width) / 2.0
    y_offset = config.bottom_mm + (config.height_mm - placed_height) / 2.0

    def place(point: Point) -> Point:
        return (
            x_offset + (point[0] - bounds[0]) * scale,
            y_offset + (bounds[3] - point[1]) * scale,
        )

    return tuple(
        PlotPath(tuple(place(point) for point in path.points), path.closed, path.kind)
        for path in rotated
    )


def deduplicate_points(points: Sequence[Point]) -> tuple[Point, ...]:
    result: list[Point] = []
    for point in points:
        if not result or point_distance(result[-1], point) > 1.0e-6:
            result.append(point)
    return tuple(result)


def simplify_path(path: PlotPath, tolerance_mm: float) -> PlotPath | None:
    points = deduplicate_points(path.points)
    if path.closed and len(points) > 1 and point_distance(points[0], points[-1]) <= 1.0e-6:
        points = points[:-1]
    if len(points) < (3 if path.closed else 2):
        return None
    array = np.asarray(points, dtype=np.float32).reshape((-1, 1, 2))
    approximate = cv2.approxPolyDP(array, max(tolerance_mm, 0.0), path.closed)
    simplified = tuple(
        (float(item[0][0]), float(item[0][1])) for item in approximate
    )
    if len(simplified) < (3 if path.closed else 2):
        return None
    if path.closed:
        simplified = simplified + (simplified[0],)
    return PlotPath(simplified, path.closed, path.kind)


def clean_paths(paths: Sequence[PlotPath], config: ConversionConfig) -> tuple[PlotPath, ...]:
    cleaned: list[PlotPath] = []
    for path in paths:
        simplified = simplify_path(path, config.simplify_mm)
        if simplified is None:
            continue
        if path_length(simplified.points) < config.min_path_mm:
            continue
        cleaned.append(simplified)
    if not cleaned:
        raise ConversionError(
            "all paths were removed as noise; lower --min-path-mm or --simplify-mm"
        )
    if len(cleaned) > config.max_paths:
        raise ConversionError(
            f"generated {len(cleaned)} paths, above --max-paths {config.max_paths}; "
            "increase filtering or explicitly raise the limit"
        )
    point_count = sum(len(path.points) for path in cleaned)
    if point_count > config.max_points:
        raise ConversionError(
            f"generated {point_count} points, above --max-points {config.max_points}; "
            "increase --simplify-mm or --curve-step-mm"
        )
    return tuple(cleaned)


def rotate_closed_path(path: PlotPath, index: int) -> PlotPath:
    body = path.points[:-1]
    rotated = body[index:] + body[:index]
    return PlotPath(rotated + (rotated[0],), True, path.kind)


def orient_path_near(path: PlotPath, current: Point) -> tuple[PlotPath, float]:
    if path.closed:
        body = path.points[:-1]
        index = min(range(len(body)), key=lambda item: point_distance(current, body[item]))
        oriented = rotate_closed_path(path, index)
        return oriented, point_distance(current, oriented.points[0])
    start_distance = point_distance(current, path.points[0])
    end_distance = point_distance(current, path.points[-1])
    if end_distance < start_distance:
        return (
            PlotPath(tuple(reversed(path.points)), False, path.kind),
            end_distance,
        )
    return path, start_distance


def order_paths(paths: Sequence[PlotPath], start: Point) -> tuple[PlotPath, ...]:
    remaining = list(paths)
    ordered: list[PlotPath] = []
    current = start
    while remaining:
        def route_score(path: PlotPath) -> float:
            start_distance = point_distance(current, path.points[0])
            if path.closed:
                return start_distance
            return min(start_distance, point_distance(current, path.points[-1]))

        best_index = min(range(len(remaining)), key=lambda index: route_score(remaining[index]))
        selected = remaining.pop(best_index)
        best_path, _ = orient_path_near(selected, current)
        ordered.append(best_path)
        current = best_path.points[-1]
    return tuple(ordered)


def allowed_bounds(config: ConversionConfig) -> Bounds:
    minimum_y = FIRMWARE_Y_MIN_MM if config.allow_unverified_area else VERIFIED_Y_MIN_MM
    maximum_y = FIRMWARE_Y_MAX_MM if config.allow_unverified_area else VERIFIED_Y_MAX_MM
    return (
        FIRMWARE_X_MIN_MM,
        minimum_y,
        FIRMWARE_X_MAX_MM,
        maximum_y,
    )


def maximum_approach_length(start: Point, unit: Point, bounds: Bounds) -> float:
    maximum = float("inf")
    if unit[0] > 1.0e-12:
        maximum = min(maximum, (start[0] - bounds[0]) / unit[0])
    elif unit[0] < -1.0e-12:
        maximum = min(maximum, (bounds[2] - start[0]) / -unit[0])
    if unit[1] > 1.0e-12:
        maximum = min(maximum, (start[1] - bounds[1]) / unit[1])
    elif unit[1] < -1.0e-12:
        maximum = min(maximum, (bounds[3] - start[1]) / -unit[1])
    return max(0.0, maximum)


def plan_paths(paths: Sequence[PlotPath], config: ConversionConfig) -> tuple[PlannedPath, ...]:
    bounds = allowed_bounds(config)
    planned: list[PlannedPath] = []
    for path in paths:
        start = path.points[0]
        second = path.points[1]
        length = point_distance(start, second)
        if length <= 1.0e-9:
            approach = start
        else:
            unit = ((second[0] - start[0]) / length, (second[1] - start[1]) / length)
            available = maximum_approach_length(start, unit, bounds)
            amount = min(config.approach_mm, available)
            approach = (start[0] - unit[0] * amount, start[1] - unit[1] * amount)
        planned.append(PlannedPath(path.points, approach, path.kind))
    return tuple(planned)


def map_paper_to_user(point: Point) -> Point:
    calibrated_x = 105.0 + (point[0] - 105.0) / X_SCALE_OBSERVED
    calibrated_y = point[1] - LEGACY_Y_SHIFT_MM
    nx = (calibrated_x - 105.0) / 100.0
    ny = (calibrated_y - 130.0) / 100.0
    basis = (1.0, nx, ny, nx * nx, nx * ny, ny * ny)
    mapped_x = sum(value * coefficient for value, coefficient in zip(basis, BASE_MAP_X))
    mapped_y = sum(value * coefficient for value, coefficient in zip(basis, BASE_MAP_Y))
    return mapped_x + WORKSPACE_SHIFT_X_MM, mapped_y + WORKSPACE_SHIFT_Y_MM


def inverse_user(point: Point) -> tuple[float, float, float]:
    machine_x = point[0] + OFFSET_X_MM
    machine_y = point[1] + OFFSET_Y_MM
    standard_x = -machine_x
    standard_y = machine_y
    cos_q2 = (
        standard_x * standard_x
        + standard_y * standard_y
        - L1_MM * L1_MM
        - L2_MM * L2_MM
    ) / (2.0 * L1_MM * L2_MM)
    if not -1.0 <= cos_q2 <= 1.0:
        raise ConversionError(
            f"mapped point is unreachable: user=({point[0]:.3f},{point[1]:.3f})"
        )
    sin_q2 = math.sqrt(max(0.0, 1.0 - cos_q2 * cos_q2))
    q2 = math.atan2(sin_q2, cos_q2)
    theta = math.atan2(L1_MM + L2_MM * cos_q2, L2_MM * sin_q2) - math.atan2(
        standard_x, standard_y
    )
    psi = theta + q2
    theta_deg = math.degrees(theta)
    psi_deg = math.degrees(psi)
    return theta_deg, psi_deg, psi_deg - theta_deg


def joint_margin(point: Point) -> tuple[float, tuple[float, float, float]]:
    theta, psi, beta = inverse_user(point)
    return (
        min(
            theta - THETA_MIN_DEG,
            THETA_MAX_DEG - theta,
            psi - PSI_MIN_DEG,
            PSI_MAX_DEG - psi,
            beta - BETA_MIN_DEG,
            BETA_MAX_DEG - beta,
        ),
        (theta, psi, beta),
    )


def home_user() -> Point:
    theta = math.radians(THETA_MIN_DEG)
    psi = math.radians(PSI_MIN_DEG)
    machine_x = -L1_MM * math.cos(theta) - L2_MM * math.cos(psi)
    machine_y = L1_MM * math.sin(theta) + L2_MM * math.sin(psi)
    return machine_x - OFFSET_X_MM, machine_y - OFFSET_Y_MM


def line_samples(start: Point, end: Point, maximum_step_mm: float) -> tuple[Point, ...]:
    span = max(abs(end[0] - start[0]), abs(end[1] - start[1]))
    count = max(1, math.ceil(span / maximum_step_mm))
    return tuple(
        (
            start[0] + (end[0] - start[0]) * index / count,
            start[1] + (end[1] - start[1]) * index / count,
        )
        for index in range(1, count + 1)
    )


def ensure_paper_bounds(paths: Sequence[PlannedPath], config: ConversionConfig) -> None:
    bounds = allowed_bounds(config)
    for path_index, path in enumerate(paths, start=1):
        for point in (path.approach, *path.points):
            if not (
                bounds[0] - 1.0e-6 <= point[0] <= bounds[2] + 1.0e-6
                and bounds[1] - 1.0e-6 <= point[1] <= bounds[3] + 1.0e-6
            ):
                region = "firmware" if config.allow_unverified_area else "verified upper"
                raise ConversionError(
                    f"path {path_index} leaves the {region} paper region at "
                    f"({point[0]:.3f},{point[1]:.3f})"
                )


def audit_paths(
    paths: Sequence[PlannedPath],
    config: ConversionConfig,
) -> dict[str, object]:
    ensure_paper_bounds(paths, config)
    drawing_worst = (float("inf"), (0.0, 0.0), (0.0, 0.0, 0.0))
    drawing_samples = 0
    previous_user = map_paper_to_user(paths[0].approach)

    first_user = previous_user
    home_worst = (float("inf"), home_user())
    for sample in line_samples(home_user(), first_user, 1.0):
        margin, _ = joint_margin(sample)
        if margin < home_worst[0]:
            home_worst = (margin, sample)
    if home_worst[0] < -0.001:
        raise ConversionError(
            f"the pen-up move from home violates a joint limit: {home_worst}"
        )

    def check_user_target(target: Point) -> None:
        nonlocal previous_user, drawing_worst, drawing_samples
        for sample in line_samples(previous_user, target, 1.0):
            margin, angles = joint_margin(sample)
            if margin < drawing_worst[0]:
                drawing_worst = (margin, sample, angles)
            drawing_samples += 1
        previous_user = target

    rapid_length = 0.0
    draw_length = 0.0
    previous_paper: Point | None = None
    for path in paths:
        if previous_paper is not None:
            rapid_length += point_distance(previous_paper, path.approach)
            check_user_target(map_paper_to_user(path.approach))
        rapid_length += point_distance(path.approach, path.points[0])
        check_user_target(map_paper_to_user(path.points[0]))
        paper_previous = path.points[0]
        for target in path.points[1:]:
            draw_length += point_distance(paper_previous, target)
            for paper_sample in line_samples(paper_previous, target, 1.0):
                check_user_target(map_paper_to_user(paper_sample))
            paper_previous = target
        previous_paper = path.points[-1]

    if drawing_worst[0] < config.minimum_joint_margin_deg:
        raise ConversionError(
            "drawing sequence has insufficient joint margin: "
            f"{drawing_worst[0]:.3f} deg at user "
            f"({drawing_worst[1][0]:.3f},{drawing_worst[1][1]:.3f}); "
            f"required {config.minimum_joint_margin_deg:.3f} deg"
        )
    paper_points = [point for path in paths for point in path.points]
    paper_points.extend(path.approach for path in paths)
    bounds = (
        min(point[0] for point in paper_points),
        min(point[1] for point in paper_points),
        max(point[0] for point in paper_points),
        max(point[1] for point in paper_points),
    )
    pen_seconds = len(paths) * 2.0 * PEN_SETTLE_SECONDS
    draw_seconds = draw_length / config.feed_mm_min * 60.0
    return {
        "paper_bounds_mm": list(bounds),
        "verified_upper_region_only": not config.allow_unverified_area,
        "home_exit": {
            "minimum_joint_margin_deg": home_worst[0],
            "minimum_margin_user_mm": list(home_worst[1]),
        },
        "drawing_sequence": {
            "sample_count": drawing_samples,
            "minimum_joint_margin_deg": drawing_worst[0],
            "minimum_margin_user_mm": list(drawing_worst[1]),
            "minimum_margin_angles_deg": list(drawing_worst[2]),
            "required_minimum_margin_deg": config.minimum_joint_margin_deg,
        },
        "path_count": len(paths),
        "point_count": sum(len(path.points) for path in paths),
        "draw_length_mm": draw_length,
        "rapid_length_mm": rapid_length,
        "pen_settle_seconds": pen_seconds,
        "draw_seconds_at_commanded_feed": draw_seconds,
        "estimated_minimum_seconds_excluding_rapid": pen_seconds + draw_seconds,
    }


def gcode_lines(
    paths: Sequence[PlannedPath],
    config: ConversionConfig,
    input_hash: str,
) -> tuple[str, ...]:
    lines = [
        f"; {TOOL_ID}",
        f"; firmware_required={REQUIRED_FIRMWARE_ID}",
        f"; paper_map_required={REQUIRED_PAPER_MAP_ID}",
        "; coordinates=STANDARD_A4_PHYSICAL_PAPER_MM",
        "; offline_mapping=NONE offline_prewarp=NONE",
        f"; source_sha256={input_hash}",
        f"; mode={config.mode.upper()} rotation_deg={config.rotate_deg:.3f}",
        "G21",
        "G90",
        "G94",
        f"F{config.feed_mm_min:.3f}",
        "S1000",
        "M5",
    ]
    for index, path in enumerate(paths, start=1):
        lines.append(f"; path={index} kind={path.kind}")
        if point_distance(path.approach, path.points[0]) > 0.001:
            lines.append(f"G0 X{path.approach[0]:.3f} Y{path.approach[1]:.3f}")
        lines.extend(
            (
                f"G0 X{path.points[0][0]:.3f} Y{path.points[0][1]:.3f}",
                "M3",
            )
        )
        lines.extend(
            f"G1 X{point[0]:.3f} Y{point[1]:.3f}"
            for point in path.points[1:]
        )
        lines.append("M5")
    if any(len(line) >= 192 for line in lines):
        raise ConversionError("generated a serial line at or above the 192-byte limit")
    return tuple(lines)


def preview_xy(point: Point) -> tuple[int, int]:
    return (
        round(point[0] * PREVIEW_PIXELS_PER_MM),
        round((A4_HEIGHT_MM - point[1]) * PREVIEW_PIXELS_PER_MM),
    )


def draw_dashed_line(
    draw: ImageDraw.ImageDraw,
    start: Point,
    end: Point,
    fill: tuple[int, int, int],
    width: int = 1,
) -> None:
    first = preview_xy(start)
    second = preview_xy(end)
    length = math.hypot(second[0] - first[0], second[1] - first[1])
    if length <= 1.0:
        return
    dash = 5.0
    count = max(1, math.ceil(length / dash))
    for index in range(0, count, 2):
        t0 = index / count
        t1 = min((index + 1) / count, 1.0)
        a = (
            round(first[0] + (second[0] - first[0]) * t0),
            round(first[1] + (second[1] - first[1]) * t0),
        )
        b = (
            round(first[0] + (second[0] - first[0]) * t1),
            round(first[1] + (second[1] - first[1]) * t1),
        )
        draw.line((a, b), fill=fill, width=width)


def write_preview(
    path: Path,
    paths: Sequence[PlannedPath],
    config: ConversionConfig,
    safety: dict[str, object],
) -> None:
    width = round(A4_WIDTH_MM * PREVIEW_PIXELS_PER_MM) + 1
    height = round(A4_HEIGHT_MM * PREVIEW_PIXELS_PER_MM) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, height - 1), outline=(25, 25, 25), width=3)
    draw.rectangle(
        (
            *preview_xy((FIRMWARE_X_MIN_MM, FIRMWARE_Y_MAX_MM)),
            *preview_xy((FIRMWARE_X_MAX_MM, FIRMWARE_Y_MIN_MM)),
        ),
        outline=(190, 95, 90),
        width=2,
    )
    draw.rectangle(
        (
            *preview_xy((FIRMWARE_X_MIN_MM, VERIFIED_Y_MAX_MM)),
            *preview_xy((FIRMWARE_X_MAX_MM, VERIFIED_Y_MIN_MM)),
        ),
        outline=(60, 145, 85),
        width=2,
    )
    draw.rectangle(
        (
            *preview_xy((config.left_mm, config.bottom_mm + config.height_mm)),
            *preview_xy((config.left_mm + config.width_mm, config.bottom_mm)),
        ),
        outline=(75, 105, 180),
        width=1,
    )

    previous = None
    for item in paths:
        if previous is not None:
            draw_dashed_line(draw, previous, item.approach, (190, 190, 190))
        draw_dashed_line(draw, item.approach, item.points[0], (225, 165, 80))
        draw.line(
            [preview_xy(point) for point in item.points],
            fill=(18, 18, 18),
            width=2,
            joint="curve",
        )
        start = preview_xy(item.points[0])
        draw.ellipse(
            (start[0] - 2, start[1] - 2, start[0] + 2, start[1] + 2),
            fill=(25, 120, 65),
        )
        previous = item.points[-1]

    font = ImageFont.load_default()
    summary = (
        f"{TOOL_ID}  mode={config.mode}  paths={len(paths)}  "
        f"draw={safety['draw_length_mm']:.1f} mm"
    )
    draw.rectangle((10, 10, min(width - 10, 640), 48), fill=(255, 255, 255))
    draw.text((16, 16), summary, fill=(20, 20, 20), font=font)
    draw.text(
        (16, 32),
        "black=pen down  gray=rapid  orange=approach  green=verified region",
        fill=(55, 55, 55),
        font=font,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def vector_svg_bytes(
    paths: Sequence[PlannedPath],
    input_hash: str,
) -> bytes:
    namespace = "http://www.w3.org/2000/svg"
    ET.register_namespace("", namespace)
    root = ET.Element(
        f"{{{namespace}}}svg",
        {
            "width": f"{A4_WIDTH_MM:g}mm",
            "height": f"{A4_HEIGHT_MM:g}mm",
            "viewBox": f"0 0 {A4_WIDTH_MM:g} {A4_HEIGHT_MM:g}",
            "version": "1.1",
        },
    )
    metadata = ET.SubElement(root, f"{{{namespace}}}metadata")
    metadata.text = json.dumps(
        {
            "tool": TOOL_ID,
            "source_sha256": input_hash,
            "coordinate_frame": "standard A4 physical paper millimetres",
            "paper_origin": "lower-left",
            "required_firmware": REQUIRED_FIRMWARE_ID,
            "required_paper_map": REQUIRED_PAPER_MAP_ID,
            "path_count": len(paths),
        },
        ensure_ascii=True,
        separators=(",", ":"),
    )
    group = ET.SubElement(
        root,
        f"{{{namespace}}}g",
        {
            "id": "pen-down-paths",
            "transform": f"translate(0 {A4_HEIGHT_MM:g}) scale(1 -1)",
            "fill": "none",
            "stroke": "#111111",
            "stroke-width": "0.3",
            "stroke-linecap": "round",
            "stroke-linejoin": "round",
            "vector-effect": "non-scaling-stroke",
        },
    )
    for index, path in enumerate(paths, start=1):
        commands = [f"M {path.points[0][0]:.3f} {path.points[0][1]:.3f}"]
        commands.extend(f"L {point[0]:.3f} {point[1]:.3f}" for point in path.points[1:])
        ET.SubElement(
            group,
            f"{{{namespace}}}path",
            {
                "id": f"path-{index}",
                "data-kind": path.kind,
                "d": " ".join(commands),
            },
        )
    ET.indent(root, space="  ")
    buffer = io.BytesIO()
    ET.ElementTree(root).write(buffer, encoding="utf-8", xml_declaration=True)
    return buffer.getvalue()


def output_manifest(
    config: ConversionConfig,
    artwork: SourceArtwork,
    paths: Sequence[PlannedPath],
    safety: dict[str, object],
    gcode: str,
    vector_svg: bytes,
    input_hash: str,
) -> dict[str, object]:
    return {
        "tool": TOOL_ID,
        "input": {
            "file": str(config.input_path),
            "sha256": input_hash,
            **artwork.metadata,
        },
        "machine_contract": {
            "required_firmware": REQUIRED_FIRMWARE_ID,
            "required_paper_map": REQUIRED_PAPER_MAP_ID,
            "coordinate_frame": "nominal physical A4 paper millimetres",
            "offline_mapping": False,
            "firmware_mapping": True,
        },
        "conversion": {
            "mode": config.mode,
            "target_frame_mm": [
                config.left_mm,
                config.bottom_mm,
                config.width_mm,
                config.height_mm,
            ],
            "rotation_deg_clockwise_in_input_view": config.rotate_deg,
            "simplify_mm": config.simplify_mm,
            "minimum_path_mm": config.min_path_mm,
            "hatch_spacing_mm": (
                config.hatch_spacing_mm if config.mode == "hatch" else None
            ),
            "approach_mm_requested": config.approach_mm,
            "route_optimized": config.optimize,
            "feed_mm_min": config.feed_mm_min,
        },
        "safety": safety,
        "outputs": {
            "gcode": str(config.output_path),
            "preview": str(config.preview_path),
            "vector_svg": str(config.vector_path),
            "manifest": str(config.manifest_path),
            "gcode_line_count": len(gcode.splitlines()),
            "gcode_sha256": hashlib.sha256(gcode.encode("ascii")).hexdigest().upper(),
            "vector_svg_sha256": hashlib.sha256(vector_svg).hexdigest().upper(),
        },
        "notes": [
            "This converter does not send commands or modify firmware.",
            "Inspect the preview before using the separate wait-for-ok sender.",
            "The time estimate excludes pen-up rapid travel time.",
        ],
    }


def validate_config(config: ConversionConfig) -> None:
    if not config.input_path.is_file():
        raise ConversionError(f"input file does not exist: {config.input_path}")
    if config.mode not in {"outline", "edge", "hatch"}:
        raise ConversionError(f"unsupported mode: {config.mode}")
    finite_values = {
        "left-mm": config.left_mm,
        "bottom-mm": config.bottom_mm,
        "width-mm": config.width_mm,
        "height-mm": config.height_mm,
        "rotate-deg": config.rotate_deg,
        "hatch-spacing-mm": config.hatch_spacing_mm,
        "simplify-mm": config.simplify_mm,
        "curve-step-mm": config.curve_step_mm,
        "min-path-mm": config.min_path_mm,
        "approach-mm": config.approach_mm,
        "feed-mm-min": config.feed_mm_min,
        "minimum-joint-margin-deg": config.minimum_joint_margin_deg,
    }
    for name, value in finite_values.items():
        if not math.isfinite(value):
            raise ConversionError(f"--{name} must be finite")
    positive_values = {
        "width-mm": config.width_mm,
        "height-mm": config.height_mm,
        "hatch-spacing-mm": config.hatch_spacing_mm,
        "curve-step-mm": config.curve_step_mm,
        "min-path-mm": config.min_path_mm,
        "feed-mm-min": config.feed_mm_min,
    }
    for name, value in positive_values.items():
        if value <= 0.0:
            raise ConversionError(f"--{name} must be positive")
    if config.simplify_mm < 0.0 or config.approach_mm < 0.0:
        raise ConversionError("simplification and approach distances cannot be negative")
    if config.minimum_joint_margin_deg < 0.0:
        raise ConversionError("--minimum-joint-margin-deg cannot be negative")
    if config.blur_px < 0 or (config.blur_px > 0 and config.blur_px % 2 == 0):
        raise ConversionError("--blur-px must be zero or a positive odd integer")
    if not 0 <= config.canny_low < config.canny_high <= 255:
        raise ConversionError("Canny thresholds must satisfy 0 <= low < high <= 255")
    if config.threshold is not None and not 0 <= config.threshold <= 255:
        raise ConversionError("--threshold must be auto or an integer from 0 to 255")
    if config.max_paths <= 0 or config.max_points <= 0:
        raise ConversionError("path and point limits must be positive")
    existing_outputs = [
        path
        for path in (
            config.output_path,
            config.preview_path,
            config.vector_path,
            config.manifest_path,
        )
        if path.exists()
    ]
    if existing_outputs and not config.force:
        raise ConversionError(
            f"output already exists: {existing_outputs[0]}; pass --force to replace outputs"
        )
    output_paths = {
        path.resolve()
        for path in (
            config.output_path,
            config.preview_path,
            config.vector_path,
            config.manifest_path,
        )
    }
    if len(output_paths) != 4:
        raise ConversionError("G-code, preview, vector, and manifest outputs must be different files")

    frame = (
        config.left_mm,
        config.bottom_mm,
        config.left_mm + config.width_mm,
        config.bottom_mm + config.height_mm,
    )
    allowed = allowed_bounds(config)
    if not (
        allowed[0] <= frame[0]
        and frame[2] <= allowed[2]
        and allowed[1] <= frame[1]
        and frame[3] <= allowed[3]
    ):
        region = "firmware" if config.allow_unverified_area else "verified upper"
        raise ConversionError(
            f"target frame {frame} is outside the {region} region {allowed}"
        )


def convert(config: ConversionConfig) -> dict[str, object]:
    validate_config(config)
    verify_repository_contract()
    suffix = config.input_path.suffix.lower()
    if suffix == ".svg":
        artwork = load_svg_artwork(config)
    elif suffix in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}:
        artwork = load_raster_artwork(config)
    else:
        raise ConversionError(
            "unsupported input type; use SVG, PNG, JPG, BMP, TIFF, or WEBP"
        )

    placed = place_paths(artwork.paths, config)
    cleaned = clean_paths(placed, config)
    if config.optimize and config.mode != "hatch":
        route_start = (
            config.left_mm,
            config.bottom_mm + config.height_mm,
        )
        cleaned = order_paths(cleaned, route_start)
    planned = plan_paths(cleaned, config)
    safety = audit_paths(planned, config)
    input_hash = sha256_file(config.input_path)
    lines = gcode_lines(planned, config, input_hash)
    gcode = "\n".join(lines) + "\n"
    vector_svg = vector_svg_bytes(planned, input_hash)
    manifest = output_manifest(
        config, artwork, planned, safety, gcode, vector_svg, input_hash
    )

    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_path.write_text(gcode, encoding="ascii", newline="\n")
    write_preview(config.preview_path, planned, config, safety)
    config.vector_path.parent.mkdir(parents=True, exist_ok=True)
    config.vector_path.write_bytes(vector_svg)
    config.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    config.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def parse_threshold(value: str) -> int | None:
    if value.lower() == "auto":
        return None
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use 'auto' or an integer from 0 to 255") from exc
    if not 0 <= result <= 255:
        raise argparse.ArgumentTypeError("threshold must be from 0 to 255")
    return result


def safe_stem(path: Path) -> str:
    stem = re.sub(r"[^A-Za-z0-9]+", "_", path.stem).strip("_").upper()
    return stem[:48] or "IMAGE"


def arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="SVG, PNG, JPG, BMP, TIFF, or WEBP")
    parser.add_argument("--mode", choices=("outline", "edge", "hatch"), default="outline")
    parser.add_argument("--output", type=Path, help="output .gcode path")
    parser.add_argument("--preview", type=Path, help="output preview PNG path")
    parser.add_argument("--vector", type=Path, help="output paper-aligned vector SVG path")
    parser.add_argument("--manifest", type=Path, help="output audit JSON path")
    parser.add_argument("--left-mm", type=float, default=DEFAULT_LEFT_MM)
    parser.add_argument("--bottom-mm", type=float, default=DEFAULT_BOTTOM_MM)
    parser.add_argument("--width-mm", type=float, default=DEFAULT_WIDTH_MM)
    parser.add_argument("--height-mm", type=float, default=DEFAULT_HEIGHT_MM)
    parser.add_argument("--rotate-deg", type=float, default=0.0)
    parser.add_argument("--threshold", type=parse_threshold, default=None, metavar="auto|0..255")
    parser.add_argument("--invert", action="store_true")
    parser.add_argument("--blur-px", type=int, default=0)
    parser.add_argument("--canny-low", type=int, default=80)
    parser.add_argument("--canny-high", type=int, default=180)
    parser.add_argument("--hatch-spacing-mm", type=float, default=1.0)
    parser.add_argument("--simplify-mm", type=float, default=0.15)
    parser.add_argument("--curve-step-mm", type=float, default=0.5)
    parser.add_argument("--min-path-mm", type=float, default=0.8)
    parser.add_argument("--approach-mm", type=float, default=DEFAULT_APPROACH_MM)
    parser.add_argument("--feed-mm-min", type=float, default=DEFAULT_FEED_MM_MIN)
    parser.add_argument("--no-optimize", action="store_true")
    parser.add_argument(
        "--allow-unverified-area",
        action="store_true",
        help="allow the firmware range below Y=130 mm",
    )
    parser.add_argument("--minimum-joint-margin-deg", type=float, default=15.0)
    parser.add_argument("--max-paths", type=int, default=2000)
    parser.add_argument("--max-points", type=int, default=200000)
    parser.add_argument("--force", action="store_true", help="replace existing output files")
    return parser.parse_args(argv)


def config_from_arguments(args: argparse.Namespace) -> ConversionConfig:
    input_path = args.input.resolve()
    default_stem = f"DRAW_{safe_stem(input_path)}_V1"
    output_path = (args.output or ROOT / "gcode" / f"{default_stem}.gcode").resolve()
    preview_path = (args.preview or output_path.with_suffix(".preview.png")).resolve()
    vector_path = (args.vector or output_path.with_suffix(".vector.svg")).resolve()
    manifest_path = (args.manifest or output_path.with_suffix(".json")).resolve()
    return ConversionConfig(
        input_path=input_path,
        output_path=output_path,
        preview_path=preview_path,
        vector_path=vector_path,
        manifest_path=manifest_path,
        mode=args.mode,
        left_mm=args.left_mm,
        bottom_mm=args.bottom_mm,
        width_mm=args.width_mm,
        height_mm=args.height_mm,
        rotate_deg=args.rotate_deg,
        threshold=args.threshold,
        invert=args.invert,
        blur_px=args.blur_px,
        canny_low=args.canny_low,
        canny_high=args.canny_high,
        hatch_spacing_mm=args.hatch_spacing_mm,
        simplify_mm=args.simplify_mm,
        curve_step_mm=args.curve_step_mm,
        min_path_mm=args.min_path_mm,
        approach_mm=args.approach_mm,
        feed_mm_min=args.feed_mm_min,
        optimize=not args.no_optimize,
        allow_unverified_area=args.allow_unverified_area,
        minimum_joint_margin_deg=args.minimum_joint_margin_deg,
        max_paths=args.max_paths,
        max_points=args.max_points,
        force=args.force,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = arguments(argv)
    try:
        config = config_from_arguments(args)
        manifest = convert(config)
    except (ConversionError, OSError) as exc:
        print(f"conversion_error: {exc}", file=sys.stderr)
        return 2
    safety = manifest["safety"]
    print(
        "drawing_conversion=PASS "
        f"paths={safety['path_count']} points={safety['point_count']} "
        f"draw_mm={safety['draw_length_mm']:.3f} "
        f"min_joint_margin={safety['drawing_sequence']['minimum_joint_margin_deg']:.3f}deg"
    )
    print(config.output_path)
    print(config.preview_path)
    print(config.vector_path)
    print(config.manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
