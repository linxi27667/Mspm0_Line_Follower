#!/usr/bin/env python3
"""Generate a centered 32 mm outline plot of Deng Wen Cheng for V33."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from check_firmware_no_sbow_v31 import firmware_map_no_sbow
from check_workspace_yshift15_v28 import joint_margin
from generate_ma_shan_zheng_gcode import (
    EXPECTED_FONT_SHA256,
    FONT_SOURCE_URL,
    outline_paths,
    rasterize_text,
)
from generate_paper_a4_full_width_square_spiral_v59 import home_user
from generate_paper_a4_standard_upper_bfont_6mm_v65 import (
    paper_line_samples,
    user_line_samples,
)


TEST_ID = "PAPER_A4_DENG_WEN_CHENG_MA_SHAN_ZHENG_32MM_OUTLINE_GCODE_V78"
FIRMWARE_ID = "PAPER_A4_STANDARD_GCODE_AMASS_PLANNER_V33"
PAPER_MAP_ID = "A4_BASE_QUADRATIC_XSCALE_NO_SBOW_CAL_V8"
TEXT = "\u9093\u6587\u6210"

FONT_PATH = (
    ROOT / "assets" / "ma_shan_zheng" / "MaShanZheng-Regular.ttf"
)
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"

A4_WIDTH_MM = 210.0
A4_HEIGHT_MM = 297.0
PAPER_X_RANGE_MM = (25.0, 185.0)
PAPER_Y_RANGE_MM = (75.0, 235.0)
ROW_CENTER_MM = (105.0, 155.0)
VISIBLE_HEIGHT_MM = 32.0
MAXIMUM_WIDTH_MM = 135.0
OUTLINE_SIMPLIFY_MM = 0.15
TANGENT_APPROACH_MM = 5.0
FEED_MM_MIN = 300
MIN_WRITING_MARGIN_DEG = 15.0
PREVIEW_PIXELS_PER_MM = 4.0


Point = tuple[float, float]


@dataclass(frozen=True)
class Stroke:
    approach: Point
    points: tuple[Point, ...]


@dataclass(frozen=True)
class Layout:
    font_family: str
    font_style: str
    visible_width_mm: float
    visible_height_mm: float
    strokes: tuple[Stroke, ...]
    drawing_bounds_mm: tuple[float, float, float, float]
    motion_bounds_mm: tuple[float, float, float, float]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def verify_font_coverage(font_path: Path, text: str) -> None:
    font = ImageFont.truetype(str(font_path), 1024)
    missing_mask = bytes(font.getmask(chr(0x10FFFF), mode="L"))
    missing = [
        character
        for character in dict.fromkeys(text)
        if bytes(font.getmask(character, mode="L")) == missing_mask
    ]
    if missing:
        raise AssertionError(f"font missing characters: {missing!r}")


def tangent_approach(points: tuple[Point, ...]) -> Point:
    if len(points) < 2:
        raise AssertionError("outline path contains fewer than two points")
    initial_length = math.dist(points[0], points[1])
    if initial_length <= 1.0e-9:
        raise AssertionError("outline path has no initial direction")
    unit_x = (points[1][0] - points[0][0]) / initial_length
    unit_y = (points[1][1] - points[0][1]) / initial_length
    return (
        points[0][0] - unit_x * TANGENT_APPROACH_MM,
        points[0][1] - unit_y * TANGENT_APPROACH_MM,
    )


def bounds(points: list[Point]) -> tuple[float, float, float, float]:
    return (
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )


def build_layout() -> Layout:
    if digest(FONT_PATH) != EXPECTED_FONT_SHA256:
        raise AssertionError("pinned Ma Shan Zheng font hash changed")
    verify_font_coverage(FONT_PATH, TEXT)

    raster = rasterize_text(
        TEXT,
        FONT_PATH,
        VISIBLE_HEIGHT_MM,
        MAXIMUM_WIDTH_MM,
    )
    left_mm = ROW_CENTER_MM[0] - raster.width_mm / 2.0
    top_mm = ROW_CENTER_MM[1] + raster.height_mm / 2.0
    source_paths = outline_paths(
        raster,
        left_mm,
        top_mm,
        OUTLINE_SIMPLIFY_MM,
    )
    strokes = tuple(
        Stroke(tangent_approach(path.points), path.points)
        for path in source_paths
    )
    if not strokes:
        raise AssertionError("font produced no drawable outlines")

    drawing_points = [point for stroke in strokes for point in stroke.points]
    motion_points = [
        point
        for stroke in strokes
        for point in (stroke.approach, *stroke.points)
    ]
    drawing_bounds = bounds(drawing_points)
    motion_bounds = bounds(motion_points)
    for point in motion_points:
        if not (
            PAPER_X_RANGE_MM[0] <= point[0] <= PAPER_X_RANGE_MM[1]
            and PAPER_Y_RANGE_MM[0] <= point[1] <= PAPER_Y_RANGE_MM[1]
        ):
            raise AssertionError(f"motion point outside paper map: {point}")

    center = (
        (drawing_bounds[0] + drawing_bounds[2]) / 2.0,
        (drawing_bounds[1] + drawing_bounds[3]) / 2.0,
    )
    if not all(
        math.isclose(actual, expected, abs_tol=0.05)
        for actual, expected in zip(center, ROW_CENTER_MM)
    ):
        raise AssertionError(f"text is not centered: {center}")

    return Layout(
        raster.font_family,
        raster.font_style,
        raster.width_mm,
        raster.height_mm,
        strokes,
        drawing_bounds,
        motion_bounds,
    )


def gcode_lines(layout: Layout) -> tuple[str, ...]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware_required={FIRMWARE_ID}",
        f"; paper_map_required={PAPER_MAP_ID}",
        "; coordinates=STANDARD_A4_PHYSICAL_PAPER_MM",
        "; offline_mapping=NONE offline_prewarp=NONE",
        f"; font_file={FONT_PATH.name}",
        f"; font_sha256={EXPECTED_FONT_SHA256}",
        "; text_codepoints=U+9093 U+6587 U+6210",
        "; source_geometry=TTF_FILLED_OUTLINE_CONTOURS",
        "; visible_height=32mm center_x=105mm center_y=155mm",
        "; tangent_approach=5mm",
        "G21",
        "G90",
        "G94",
        f"F{FEED_MM_MIN}",
        "S1000",
        "M5",
    ]
    for index, stroke in enumerate(layout.strokes, start=1):
        lines.extend(
            (
                f"; path={index} kind=outline",
                f"G0 X{stroke.approach[0]:.3f} Y{stroke.approach[1]:.3f}",
                f"G0 X{stroke.points[0][0]:.3f} Y{stroke.points[0][1]:.3f}",
                "M3",
            )
        )
        lines.extend(
            f"G1 X{point[0]:.3f} Y{point[1]:.3f}"
            for point in stroke.points[1:]
        )
        lines.append("M5")
    lines.append("M5")
    return tuple(lines)


def minimum_margin_on_user_line(
    start: Point,
    target: Point,
) -> tuple[float, Point, int]:
    worst = (float("inf"), target)
    samples = user_line_samples(start, target, 1.0)
    for sample in samples:
        margin, _ = joint_margin(sample)
        if margin < worst[0]:
            worst = (margin, sample)
    return worst[0], worst[1], len(samples)


def audit(layout: Layout, lines: tuple[str, ...]) -> dict[str, object]:
    first_approach_user = firmware_map_no_sbow(layout.strokes[0].approach)
    home_exit_margin, home_exit_point, home_exit_samples = (
        minimum_margin_on_user_line(home_user(), first_approach_user)
    )

    previous_user = first_approach_user
    writing_worst = (float("inf"), first_approach_user)
    writing_samples = 0

    def check_user(target: Point) -> None:
        nonlocal previous_user, writing_worst, writing_samples
        margin, point, sample_count = minimum_margin_on_user_line(
            previous_user, target
        )
        if margin < writing_worst[0]:
            writing_worst = (margin, point)
        writing_samples += sample_count
        previous_user = target

    for stroke in layout.strokes:
        check_user(firmware_map_no_sbow(stroke.approach))
        check_user(firmware_map_no_sbow(stroke.points[0]))
        previous_paper = stroke.points[0]
        for target_paper in stroke.points[1:]:
            for sample in paper_line_samples(previous_paper, target_paper):
                check_user(firmware_map_no_sbow(sample))
            previous_paper = target_paper

    if home_exit_margin < -0.001:
        raise AssertionError("initial pen-up departure violates joint limits")
    if writing_worst[0] < MIN_WRITING_MARGIN_DEG:
        raise AssertionError(
            f"writing margin is too small: {writing_worst}"
        )
    if any(len(line) >= 192 for line in lines):
        raise AssertionError("G-code contains an overlong serial line")
    if lines.count("M3") != len(layout.strokes):
        raise AssertionError("pen-down count does not match path count")
    if lines.count("M5") != len(layout.strokes) + 2:
        raise AssertionError("pen-up count does not match path count")

    return {
        "home_exit": {
            "sample_count": home_exit_samples,
            "minimum_joint_margin_deg": home_exit_margin,
            "minimum_margin_user_mm": list(home_exit_point),
        },
        "writing_sequence": {
            "sample_count": writing_samples,
            "minimum_joint_margin_deg": writing_worst[0],
            "minimum_margin_user_mm": list(writing_worst[1]),
            "required_minimum_margin_deg": MIN_WRITING_MARGIN_DEG,
        },
        "path_count": len(layout.strokes),
        "g0_count": sum(line.startswith("G0 ") for line in lines),
        "g1_count": sum(line.startswith("G1 ") for line in lines),
    }


def preview_xy(point: Point) -> tuple[int, int]:
    return (
        round(point[0] * PREVIEW_PIXELS_PER_MM),
        round((A4_HEIGHT_MM - point[1]) * PREVIEW_PIXELS_PER_MM),
    )


def write_preview(layout: Layout) -> None:
    width = round(A4_WIDTH_MM * PREVIEW_PIXELS_PER_MM) + 1
    height = round(A4_HEIGHT_MM * PREVIEW_PIXELS_PER_MM) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, height - 1), outline=(25, 25, 25), width=3)
    draw.rectangle(
        (
            *preview_xy((PAPER_X_RANGE_MM[0], PAPER_Y_RANGE_MM[1])),
            *preview_xy((PAPER_X_RANGE_MM[1], PAPER_Y_RANGE_MM[0])),
        ),
        outline=(80, 145, 105),
        width=2,
    )
    for stroke in layout.strokes:
        draw.line(
            [preview_xy(point) for point in stroke.points],
            fill=(15, 15, 15),
            width=3,
            joint="curve",
        )
        draw.line(
            [preview_xy(stroke.approach), preview_xy(stroke.points[0])],
            fill=(55, 115, 185),
            width=1,
        )
    title_font = ImageFont.truetype(r"C:\Windows\Fonts\simhei.ttf", 22)
    small_font = ImageFont.truetype(r"C:\Windows\Fonts\simhei.ttf", 15)
    draw.text(
        (18, 14),
        f"{TEXT} - 32 mm Ma Shan Zheng outline",
        fill=(20, 20, 20),
        font=title_font,
    )
    draw.text(
        (18, 45),
        "black=pen down  blue=pen-up tangent approach  green=safe paper map",
        fill=(65, 65, 65),
        font=small_font,
    )
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def write_manifest(
    layout: Layout,
    lines: tuple[str, ...],
    safety: dict[str, object],
) -> None:
    content = "\n".join(lines) + "\n"
    manifest = {
        "id": TEST_ID,
        "required_firmware": FIRMWARE_ID,
        "required_paper_map": PAPER_MAP_ID,
        "text": TEXT,
        "font": {
            "family": layout.font_family,
            "style": layout.font_style,
            "file": str(FONT_PATH.relative_to(ROOT)),
            "sha256": EXPECTED_FONT_SHA256,
            "source": FONT_SOURCE_URL,
            "license": "SIL Open Font License 1.1",
        },
        "layout": {
            "visible_width_mm": layout.visible_width_mm,
            "visible_height_mm": layout.visible_height_mm,
            "row_center_mm": list(ROW_CENTER_MM),
            "drawing_bounds_mm": list(layout.drawing_bounds_mm),
            "motion_bounds_mm": list(layout.motion_bounds_mm),
        },
        "coordinate_contract": {
            "units": "mm",
            "frame": "nominal physical A4 paper",
            "offline_mapping": False,
            "offline_prewarp": False,
            "firmware_mapping": True,
        },
        "motion": {
            "feed_mm_min": FEED_MM_MIN,
            "tangent_approach_mm": TANGENT_APPROACH_MM,
            "outline_simplify_mm": OUTLINE_SIMPLIFY_MM,
        },
        "safety": safety,
        "gcode": {
            "file": GCODE_PATH.name,
            "line_count": len(lines),
            "sha256": hashlib.sha256(content.encode("ascii"))
            .hexdigest()
            .upper(),
        },
        "preview": str(PREVIEW_PATH.relative_to(ROOT)),
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def verify_firmware_contract() -> None:
    gcode_header = (ROOT / "TASK" / "gcode_serial.h").read_text(
        encoding="utf-8"
    )
    map_header = (ROOT / "APP" / "Inc" / "app_writer_paper_map.h").read_text(
        encoding="utf-8"
    )
    if f'"{FIRMWARE_ID}"' not in gcode_header:
        raise AssertionError("current firmware build ID does not match V78")
    if f'"{PAPER_MAP_ID}"' not in map_header:
        raise AssertionError("current paper map ID does not match V78")


def main() -> None:
    verify_firmware_contract()
    layout = build_layout()
    lines = gcode_lines(layout)
    safety = audit(layout, lines)
    content = "\n".join(lines) + "\n"
    GCODE_PATH.parent.mkdir(parents=True, exist_ok=True)
    GCODE_PATH.write_text(content, encoding="ascii", newline="\n")
    write_manifest(layout, lines, safety)
    write_preview(layout)
    print(
        f"{TEST_ID}=PASS text={TEXT} paths={len(layout.strokes)} "
        f"G1={safety['g1_count']} "
        f"size={layout.visible_width_mm:.3f}x{layout.visible_height_mm:.3f}mm "
        f"writing_margin="
        f"{safety['writing_sequence']['minimum_joint_margin_deg']:.6f}deg "
        f"sha256={hashlib.sha256(content.encode('ascii')).hexdigest().upper()}"
    )
    print(GCODE_PATH)
    print(MANIFEST_PATH)
    print(PREVIEW_PATH)


if __name__ == "__main__":
    main()
