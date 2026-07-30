#!/usr/bin/env python3
"""Generate V28-compatible G-code from the bundled Ma Shan Zheng TTF.

TrueType fonts contain filled outlines, not handwriting stroke order.  This
tool therefore offers two plotter-friendly interpretations:

* ``outline`` traces every visible glyph boundary.
* ``hatch`` fills the visible glyph area with closely spaced horizontal lines.

The logical paper coordinates are corrected with the retained base-only paper
map and the current V28 firmware applies the final +15 mm Y translation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from check_workspace_yshift15_v28 import (
    BUILD_ID,
    L1_MM,
    L2_MM,
    OFFSET_X_MM,
    OFFSET_Y_MM,
    PSI_MIN_DEG,
    SHIFT_X_MM,
    SHIFT_Y_MM,
    THETA_MIN_DEG,
    joint_margin,
)
from generate_paper_a4_3x3_baseonly_direction_v49 import map_base_only


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FONT_PATH = (
    ROOT / "assets" / "ma_shan_zheng" / "MaShanZheng-Regular.ttf"
)
EXPECTED_FONT_SHA256 = (
    "6D2546BB189C732A8CA29AF9E22457B152387D158AA459E4AC2CE1E51788B7FB"
)
FONT_SOURCE_URL = (
    "https://github.com/google/fonts/tree/main/ofl/mashanzheng"
)

A4_WIDTH_MM = 210.0
A4_HEIGHT_MM = 297.0
SAFE_X_MIN_MM = 25.0
SAFE_X_MAX_MM = 185.0
SAFE_PHYSICAL_Y_MIN_MM = 110.0
SAFE_PHYSICAL_Y_MAX_MM = 240.0
RENDER_FONT_PX = 1024
PREVIEW_PX_PER_MM = 4.0


Point = tuple[float, float]


@dataclass(frozen=True)
class PlotPath:
    kind: str
    points: tuple[Point, ...]


@dataclass(frozen=True)
class RasterizedText:
    mask: np.ndarray
    mm_per_pixel: float
    width_mm: float
    height_mm: float
    font_family: str
    font_style: str


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def portable_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def unicode_comment_lines(text: str, chunk_size: int = 12) -> list[str]:
    labels = [f"U+{ord(character):04X}" for character in text]
    return [
        f"; text_codepoints_{index // chunk_size + 1}="
        + " ".join(labels[index : index + chunk_size])
        for index in range(0, len(labels), chunk_size)
    ]


def rasterize_text(
    text: str,
    font_path: Path,
    requested_height_mm: float,
    maximum_width_mm: float,
) -> RasterizedText:
    font = ImageFont.truetype(str(font_path), RENDER_FONT_PX)
    scratch = Image.new("L", (1, 1), 0)
    scratch_draw = ImageDraw.Draw(scratch)
    bounds = scratch_draw.textbbox((0, 0), text, font=font)
    width = int(math.ceil(bounds[2] - bounds[0]))
    height = int(math.ceil(bounds[3] - bounds[1]))
    if width <= 0 or height <= 0:
        raise ValueError("text has no visible glyphs")

    padding = 12
    image = Image.new("L", (width + padding * 2, height + padding * 2), 0)
    draw = ImageDraw.Draw(image)
    draw.text(
        (padding - bounds[0], padding - bounds[1]),
        text,
        font=font,
        fill=255,
    )
    raw = np.asarray(image)
    foreground = np.argwhere(raw > 127)
    if foreground.size == 0:
        raise ValueError("text rasterization produced an empty mask")
    y_min, x_min = foreground.min(axis=0)
    y_max, x_max = foreground.max(axis=0)
    mask = (raw[y_min : y_max + 1, x_min : x_max + 1] > 127).astype(
        np.uint8
    )

    pixel_height = max(mask.shape[0] - 1, 1)
    pixel_width = max(mask.shape[1] - 1, 1)
    mm_per_pixel = min(
        requested_height_mm / pixel_height,
        maximum_width_mm / pixel_width,
    )
    family, style = font.getname()
    return RasterizedText(
        mask=mask,
        mm_per_pixel=mm_per_pixel,
        width_mm=pixel_width * mm_per_pixel,
        height_mm=pixel_height * mm_per_pixel,
        font_family=family,
        font_style=style,
    )


def to_paper(
    pixel: tuple[float, float],
    left_mm: float,
    top_mm: float,
    mm_per_pixel: float,
) -> Point:
    return (
        left_mm + pixel[0] * mm_per_pixel,
        top_mm - pixel[1] * mm_per_pixel,
    )


def rotate_closed_path_near(
    points: tuple[Point, ...],
    current: Point,
) -> tuple[Point, ...]:
    body = points[:-1]
    nearest = min(
        range(len(body)),
        key=lambda index: math.dist(current, body[index]),
    )
    rotated = body[nearest:] + body[:nearest]
    return rotated + (rotated[0],)


def outline_paths(
    raster: RasterizedText,
    left_mm: float,
    top_mm: float,
    simplify_mm: float,
) -> list[PlotPath]:
    contours, _ = cv2.findContours(
        raster.mask * 255,
        cv2.RETR_TREE,
        cv2.CHAIN_APPROX_NONE,
    )
    candidates: list[tuple[Point, ...]] = []
    epsilon_px = max(simplify_mm / raster.mm_per_pixel, 0.5)
    for contour in contours:
        approximate = cv2.approxPolyDP(contour, epsilon_px, True)
        pixels = [
            (float(item[0][0]), float(item[0][1]))
            for item in approximate
        ]
        if len(pixels) < 3:
            continue
        paper = tuple(
            to_paper(point, left_mm, top_mm, raster.mm_per_pixel)
            for point in pixels
        )
        paper = paper + (paper[0],)
        perimeter = sum(
            math.dist(start, end)
            for start, end in zip(paper, paper[1:])
        )
        if perimeter >= 0.20:
            candidates.append(paper)

    ordered: list[PlotPath] = []
    current = (left_mm, top_mm)
    remaining = candidates[:]
    while remaining:
        path_index, _ = min(
            enumerate(remaining),
            key=lambda item: min(
                math.dist(current, point) for point in item[1][:-1]
            ),
        )
        chosen = rotate_closed_path_near(remaining.pop(path_index), current)
        ordered.append(PlotPath("outline", chosen))
        current = chosen[-1]
    return ordered


def row_runs(row: np.ndarray) -> list[tuple[int, int]]:
    indexes = np.flatnonzero(row)
    if indexes.size == 0:
        return []
    breaks = np.flatnonzero(np.diff(indexes) > 1)
    starts = np.concatenate(([indexes[0]], indexes[breaks + 1]))
    ends = np.concatenate((indexes[breaks], [indexes[-1]]))
    return list(zip(starts.tolist(), ends.tolist()))


def hatch_paths(
    raster: RasterizedText,
    left_mm: float,
    top_mm: float,
    spacing_mm: float,
) -> list[PlotPath]:
    row_step = max(1, round(spacing_mm / raster.mm_per_pixel))
    paths: list[PlotPath] = []
    reverse = False
    for y_pixel in range(0, raster.mask.shape[0], row_step):
        runs = row_runs(raster.mask[y_pixel])
        if reverse:
            runs = list(reversed(runs))
        for start_x, end_x in runs:
            if end_x == start_x:
                end_x = min(start_x + 1, raster.mask.shape[1] - 1)
            start = to_paper(
                (float(start_x), float(y_pixel)),
                left_mm,
                top_mm,
                raster.mm_per_pixel,
            )
            end = to_paper(
                (float(end_x), float(y_pixel)),
                left_mm,
                top_mm,
                raster.mm_per_pixel,
            )
            points = (end, start) if reverse else (start, end)
            if math.dist(*points) >= 0.10:
                paths.append(PlotPath("hatch", points))
        reverse = not reverse
    return paths


def subdivide(points: tuple[Point, ...], maximum_step_mm: float) -> tuple[Point, ...]:
    result = [points[0]]
    for start, end in zip(points, points[1:]):
        length = math.dist(start, end)
        if length <= 1.0e-9:
            continue
        count = max(1, math.ceil(length / maximum_step_mm))
        result.extend(
            (
                start[0] + (end[0] - start[0]) * index / count,
                start[1] + (end[1] - start[1]) * index / count,
            )
            for index in range(1, count + 1)
        )
    if len(result) < 2:
        raise ValueError("plot path collapsed to fewer than two points")
    return tuple(result)


def mapped_paths(
    paths: Iterable[PlotPath],
    maximum_step_mm: float,
) -> list[tuple[PlotPath, tuple[Point, ...], tuple[Point, ...]]]:
    result = []
    for path in paths:
        paper_points = subdivide(path.points, maximum_step_mm)
        user_points = tuple(
            tuple(map(float, map_base_only(point))) for point in paper_points
        )
        result.append((path, paper_points, user_points))
    return result


def home_user() -> Point:
    theta = math.radians(THETA_MIN_DEG)
    psi = math.radians(PSI_MIN_DEG)
    machine_x = -L1_MM * math.cos(theta) - L2_MM * math.cos(psi)
    machine_y = L1_MM * math.sin(theta) + L2_MM * math.sin(psi)
    return machine_x - OFFSET_X_MM, machine_y - OFFSET_Y_MM


def audit(
    plan: list[tuple[PlotPath, tuple[Point, ...], tuple[Point, ...]]],
) -> dict:
    paper_points = [
        point
        for _, points, _ in plan
        for point in points
    ]
    if not paper_points:
        raise ValueError("no drawable paths were generated")
    physical_points = [
        (point[0] + SHIFT_X_MM, point[1] + SHIFT_Y_MM)
        for point in paper_points
    ]
    physical_bounds = (
        min(point[0] for point in physical_points),
        min(point[1] for point in physical_points),
        max(point[0] for point in physical_points),
        max(point[1] for point in physical_points),
    )
    if not (
        SAFE_X_MIN_MM <= physical_bounds[0]
        and physical_bounds[2] <= SAFE_X_MAX_MM
        and SAFE_PHYSICAL_Y_MIN_MM <= physical_bounds[1]
        and physical_bounds[3] <= SAFE_PHYSICAL_Y_MAX_MM
    ):
        raise ValueError(
            "generated text is outside the retained physical writing area: "
            f"{physical_bounds}"
        )

    ordered_targets = [
        (point[0] + SHIFT_X_MM, point[1] + SHIFT_Y_MM)
        for _, _, points in plan
        for point in points
    ]
    previous = home_user()
    worst = (float("inf"), (0.0, 0.0), (0.0, 0.0, 0.0))
    sample_count = 0
    for target in ordered_targets:
        count = max(1, math.ceil(math.dist(previous, target)))
        for index in range(1, count + 1):
            ratio = index / count
            sample = (
                previous[0] + (target[0] - previous[0]) * ratio,
                previous[1] + (target[1] - previous[1]) * ratio,
            )
            margin, angles = joint_margin(sample)
            if margin < worst[0]:
                worst = (margin, sample, angles)
            sample_count += 1
        previous = target
    if worst[0] < -0.001:
        raise ValueError(f"generated path violates joint limits: {worst}")

    mapped_draw_steps = [
        math.dist(start, end)
        for _, _, points in plan
        for start, end in zip(points, points[1:])
    ]
    return {
        "physical_paper_bounds_mm": list(physical_bounds),
        "path_sample_count": sample_count,
        "minimum_joint_margin_deg": worst[0],
        "minimum_at_shifted_user_mm": list(worst[1]),
        "minimum_at_angles_deg": list(worst[2]),
        "maximum_mapped_draw_step_mm": max(mapped_draw_steps),
    }


def gcode_lines(
    text: str,
    font_path: Path,
    mode: str,
    feed_mm_min: float,
    maximum_step_mm: float,
    plan: list[tuple[PlotPath, tuple[Point, ...], tuple[Point, ...]]],
) -> tuple[str, ...]:
    lines = [
        "; MA_SHAN_ZHENG_TTF_GCODE",
        f"; firmware_required={BUILD_ID}",
        "; WARNING=DO_NOT_SEND_TO_V27_OR_OLDER",
        f"; font_file={font_path.name}",
        f"; font_sha256={digest(font_path)}",
        f"; font_source={FONT_SOURCE_URL}",
    ]
    lines.extend(unicode_comment_lines(text))
    lines.extend(
        (
            f"; mode={mode.upper()} source_geometry=TTF_FILLED_OUTLINE",
            "; map=BASE_QUADRATIC_ONLY firmware_global_y_shift=+15mm",
            f"; paper_subdivision_max={maximum_step_mm:.3f}mm",
            "G21",
            "G90",
            "G94",
            f"F{feed_mm_min:.3f}",
            "S1000",
            "M5",
        )
    )
    for index, (path, _, user_points) in enumerate(plan, start=1):
        lines.extend(
            (
                f"; path={index} kind={path.kind}",
                f"G0 X{user_points[0][0]:.3f} Y{user_points[0][1]:.3f}",
                "M3",
            )
        )
        lines.extend(
            f"G1 X{point[0]:.3f} Y{point[1]:.3f}"
            for point in user_points[1:]
        )
        lines.append("M5")
    return tuple(lines)


def preview_xy(point: Point) -> tuple[int, int]:
    return (
        round(point[0] * PREVIEW_PX_PER_MM),
        round((A4_HEIGHT_MM - point[1]) * PREVIEW_PX_PER_MM),
    )


def write_preview(
    path: Path,
    mode: str,
    text: str,
    raster: RasterizedText,
    paths: list[PlotPath],
) -> None:
    width = round(A4_WIDTH_MM * PREVIEW_PX_PER_MM) + 1
    height = round(A4_HEIGHT_MM * PREVIEW_PX_PER_MM) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, height - 1), outline=(25, 25, 25), width=3)
    draw.rectangle(
        (
            *preview_xy((SAFE_X_MIN_MM, SAFE_PHYSICAL_Y_MAX_MM)),
            *preview_xy((SAFE_X_MAX_MM, SAFE_PHYSICAL_Y_MIN_MM)),
        ),
        outline=(80, 150, 100),
        width=2,
    )
    label_font = ImageFont.truetype(r"C:\Windows\Fonts\simhei.ttf", 19)
    small_font = ImageFont.truetype(r"C:\Windows\Fonts\simhei.ttf", 14)
    draw.text(
        (18, 14),
        f"马善政字体 G-code 预览：{text}",
        fill=(20, 20, 20),
        font=label_font,
    )
    draw.text(
        (18, 42),
        (
            f"{mode}，字形 {raster.width_mm:.1f} × "
            f"{raster.height_mm:.1f} mm；绿色框为当前保留书写区"
        ),
        fill=(65, 65, 65),
        font=small_font,
    )
    for plot_path in paths:
        physical = [
            (point[0] + SHIFT_X_MM, point[1] + SHIFT_Y_MM)
            for point in plot_path.points
        ]
        draw.line(
            [preview_xy(point) for point in physical],
            fill=(15, 15, 15),
            width=2 if plot_path.kind == "outline" else 1,
            joint="curve",
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def write_manifest(
    path: Path,
    text: str,
    mode: str,
    font_path: Path,
    raster: RasterizedText,
    args: argparse.Namespace,
    paths: list[PlotPath],
    plan: list[tuple[PlotPath, tuple[Point, ...], tuple[Point, ...]]],
    safety: dict,
    output_path: Path,
    preview_path: Path,
    lines: tuple[str, ...],
) -> None:
    gcode_text = "\n".join(lines) + "\n"
    manifest = {
        "generator": Path(__file__).name,
        "required_firmware": BUILD_ID,
        "text": text,
        "font": {
            "family": raster.font_family,
            "style": raster.font_style,
            "file": portable_path(font_path),
            "sha256": digest(font_path),
            "source": FONT_SOURCE_URL,
            "license": "SIL Open Font License 1.1",
        },
        "plot": {
            "mode": mode,
            "logical_left_mm": args.left_mm,
            "logical_top_mm": args.top_mm,
            "visible_width_mm": raster.width_mm,
            "visible_height_mm": raster.height_mm,
            "hatch_spacing_mm": (
                args.hatch_spacing_mm if mode == "hatch" else None
            ),
            "outline_simplify_mm": (
                args.outline_simplify_mm if mode == "outline" else None
            ),
            "paper_subdivision_max_mm": args.maximum_step_mm,
            "path_count": len(paths),
            "g1_count": sum(len(points) - 1 for _, _, points in plan),
        },
        "mapping": {
            "base_quadratic_enabled": True,
            "firmware_global_translation_user_mm": [SHIFT_X_MM, SHIFT_Y_MM],
        },
        "safety": safety,
        "gcode": {
            "file": portable_path(output_path),
            "line_count": len(lines),
            "sha256": hashlib.sha256(gcode_text.encode("ascii")).hexdigest(),
        },
        "preview": portable_path(preview_path),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", default="张佳乐作品")
    parser.add_argument("--font", type=Path, default=DEFAULT_FONT_PATH)
    parser.add_argument("--mode", choices=("outline", "hatch"), default="outline")
    parser.add_argument("--height-mm", type=float, default=9.0)
    parser.add_argument("--maximum-width-mm", type=float, default=150.0)
    parser.add_argument("--left-mm", type=float, default=30.0)
    parser.add_argument("--top-mm", type=float, default=220.0)
    parser.add_argument("--hatch-spacing-mm", type=float, default=0.45)
    parser.add_argument("--outline-simplify-mm", type=float, default=0.10)
    parser.add_argument("--maximum-step-mm", type=float, default=0.40)
    parser.add_argument("--feed-mm-min", type=float, default=150.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--preview", type=Path)
    return parser.parse_args()


def resolve_outputs(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    height_tag = f"{args.height_mm:g}".replace(".", "P")
    stem = (
        f"PAPER_A4_MA_SHAN_ZHENG_{height_tag}MM_"
        f"{args.mode.upper()}_V54"
    )
    output = args.output or ROOT / "gcode" / f"{stem}.gcode"
    manifest = args.manifest or ROOT / "gcode" / f"{stem}.json"
    preview = (
        args.preview
        or ROOT / "docs" / "diagnostics" / f"{stem}_PREVIEW.png"
    )
    return output.resolve(), manifest.resolve(), preview.resolve()


def main() -> None:
    args = arguments()
    font_path = args.font.resolve()
    if not font_path.is_file():
        raise FileNotFoundError(font_path)
    if font_path == DEFAULT_FONT_PATH.resolve():
        actual_hash = digest(font_path)
        if actual_hash != EXPECTED_FONT_SHA256:
            raise ValueError(
                "bundled Ma Shan Zheng font hash changed: "
                f"{actual_hash}"
            )
    if args.height_mm <= 0 or args.maximum_width_mm <= 0:
        raise ValueError("font dimensions must be positive")
    if args.maximum_step_mm <= 0 or args.hatch_spacing_mm <= 0:
        raise ValueError("motion sampling values must be positive")

    raster = rasterize_text(
        args.text,
        font_path,
        args.height_mm,
        args.maximum_width_mm,
    )
    if args.mode == "outline":
        paths = outline_paths(
            raster,
            args.left_mm,
            args.top_mm,
            args.outline_simplify_mm,
        )
    else:
        paths = hatch_paths(
            raster,
            args.left_mm,
            args.top_mm,
            args.hatch_spacing_mm,
        )
    plan = mapped_paths(paths, args.maximum_step_mm)
    safety = audit(plan)
    lines = gcode_lines(
        args.text,
        font_path,
        args.mode,
        args.feed_mm_min,
        args.maximum_step_mm,
        plan,
    )
    output_path, manifest_path, preview_path = resolve_outputs(args)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "\n".join(lines) + "\n",
        encoding="ascii",
        newline="\n",
    )
    write_preview(
        preview_path,
        args.mode,
        args.text,
        raster,
        paths,
    )
    write_manifest(
        manifest_path,
        args.text,
        args.mode,
        font_path,
        raster,
        args,
        paths,
        plan,
        safety,
        output_path,
        preview_path,
        lines,
    )
    print(
        "generated_ma_shan_zheng_gcode=PASS "
        f"mode={args.mode} paths={len(paths)} "
        f"G1={sum(len(points) - 1 for _, _, points in plan)} "
        f"size={raster.width_mm:.3f}x{raster.height_mm:.3f}mm "
        f"physical_bounds={safety['physical_paper_bounds_mm']} "
        f"min_joint_margin={safety['minimum_joint_margin_deg']:.6f}deg"
    )
    print(output_path)
    print(preview_path)
    print(manifest_path)


if __name__ == "__main__":
    main()
