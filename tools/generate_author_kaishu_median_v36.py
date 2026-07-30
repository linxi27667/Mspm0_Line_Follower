"""Generate the gated V36 large single-line Kaishu median path."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "assets" / "hanzi_writer_data_68d10a4"
HEADER_PATH = ROOT / "TASK" / "author_text_demo_path.h"
PREVIEW_PATH = (
    ROOT
    / "docs"
    / "diagnostics"
    / "AUTHOR_KAISHU_MEDIAN_16MM_L205_L203_GATED_V36_PREVIEW.png"
)
DETAIL_PREVIEW_PATH = (
    ROOT
    / "docs"
    / "diagnostics"
    / "AUTHOR_KAISHU_MEDIAN_16MM_L205_L203_GATED_V36_DETAIL.png"
)

SOURCE_COMMIT = "68d10a4b21150cae5e1ebbd223eed289cf32d90c"
LICENSE_SHA256 = "5590533436C70F10F2F524EE61456238C290175C6662FBE1C700B5F038A6D328"

A4_WIDTH_MM = 297.0
A4_HEIGHT_MM = 210.0
SAFE_X0_MM = 145.0
SAFE_Y0_MM = 15.0
SAFE_X1_MM = 275.0
SAFE_Y1_MM = 125.0

ALIGN_X_MM = 150.0
ALIGN_Y_MM = 20.0
TEXT_CENTER_X_MM = 205.0
TEXT_CENTER_Y_MM = 65.0
CELL_WIDTH_MM = 18.0
MAX_GLYPH_HEIGHT_MM = 16.0
LOCAL_Y_ANCHOR_MM = 65.0
LOCAL_Y_SCALE = 1.095
COORDINATE_SCALE = 10


@dataclass(frozen=True)
class GlyphSource:
    character: str
    codepoint: str
    filename: str
    sha256: str
    stroke_count: int
    median_point_count: int


GLYPHS = (
    GlyphSource(
        "\u5f20",
        "U+5F20",
        "u5f20.json",
        "2B7ABF0BE39617AC5B3F68917DAC2E6520C926AA2F7B0F2AF6C2B50C19CB682D",
        7,
        53,
    ),
    GlyphSource(
        "\u4f73",
        "U+4F73",
        "u4f73.json",
        "C830BB19E18D515D4992E2D8B464BE7AEFD14D318C36A7A292ED34A0D5D59C20",
        8,
        44,
    ),
    GlyphSource(
        "\u4e50",
        "U+4E50",
        "u4e50.json",
        "E5B3D2904512D9B0AC920FABE82E7C5CF1BE5BC8B1931F0FEE5D59398284CD75",
        5,
        33,
    ),
)


@dataclass(frozen=True)
class PathPoint:
    x_x10: int
    y_x10: int
    draw: bool

    @property
    def x_mm(self) -> float:
        return self.x_x10 / COORDINATE_SCALE

    @property
    def y_mm(self) -> float:
        return self.y_x10 / COORDINATE_SCALE

    @property
    def xy(self) -> tuple[float, float]:
        return self.x_mm, self.y_mm


@dataclass(frozen=True)
class DesiredPoint:
    x_mm: float
    y_mm: float
    draw: bool


@dataclass(frozen=True)
class GeneratedPath:
    command_points: tuple[PathPoint, ...]
    desired_points: tuple[DesiredPoint, ...]
    glyph_bounds_units: tuple[tuple[int, int, int, int], ...]
    common_scale_mm_per_unit: float


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def lround(value: float) -> int:
    if value >= 0.0:
        return math.floor(value + 0.5)
    return math.ceil(value - 0.5)


def load_medians(
    source: GlyphSource,
) -> tuple[tuple[tuple[int, int], ...], ...]:
    path = DATA_DIR / source.filename
    actual_digest = digest(path)
    if actual_digest != source.sha256:
        raise AssertionError(
            f"{source.filename} hash changed: {actual_digest}"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    strokes = data.get("strokes")
    medians = data.get("medians")
    if not isinstance(strokes, list) or not isinstance(medians, list):
        raise AssertionError(f"{source.filename}: missing stroke data")
    if len(strokes) != source.stroke_count or len(medians) != source.stroke_count:
        raise AssertionError(f"{source.filename}: stroke count changed")

    result: list[tuple[tuple[int, int], ...]] = []
    for stroke_index, raw_stroke in enumerate(medians):
        if not isinstance(raw_stroke, list) or len(raw_stroke) < 2:
            raise AssertionError(
                f"{source.filename}: invalid median {stroke_index}"
            )
        stroke: list[tuple[int, int]] = []
        for raw_point in raw_stroke:
            if (
                not isinstance(raw_point, list)
                or len(raw_point) != 2
                or not all(isinstance(value, int) for value in raw_point)
            ):
                raise AssertionError(
                    f"{source.filename}: invalid median point"
                )
            x_value, y_value = raw_point
            if not (-128 <= x_value <= 1152 and -128 <= y_value <= 1024):
                raise AssertionError(
                    f"{source.filename}: median point left design box"
                )
            stroke.append((x_value, y_value))
        result.append(tuple(stroke))

    if sum(len(stroke) for stroke in result) != source.median_point_count:
        raise AssertionError(f"{source.filename}: median point count changed")
    return tuple(result)


def stroke_bounds(
    strokes: tuple[tuple[tuple[int, int], ...], ...]
) -> tuple[int, int, int, int]:
    points = [point for stroke in strokes for point in stroke]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def generate() -> GeneratedPath:
    if digest(DATA_DIR / "ARPHICPL.TXT") != LICENSE_SHA256:
        raise AssertionError("Arphic license copy changed")

    glyph_strokes = tuple(load_medians(source) for source in GLYPHS)
    bounds = tuple(stroke_bounds(strokes) for strokes in glyph_strokes)
    maximum_height_units = max(y1 - y0 for _, y0, _, y1 in bounds)
    common_scale = MAX_GLYPH_HEIGHT_MM / maximum_height_units
    total_width = CELL_WIDTH_MM * len(GLYPHS)
    text_left = TEXT_CENTER_X_MM - total_width / 2.0

    command_points: list[PathPoint] = []
    desired_points: list[DesiredPoint] = []
    for glyph_index, strokes in enumerate(glyph_strokes):
        x0, y0, x1, y1 = bounds[glyph_index]
        glyph_width = (x1 - x0) * common_scale
        cell_left = text_left + glyph_index * CELL_WIDTH_MM
        x_offset = cell_left + (CELL_WIDTH_MM - glyph_width) / 2.0
        y_center_units = (y0 + y1) / 2.0

        for stroke in strokes:
            for point_index, (source_x, source_y) in enumerate(stroke):
                desired_x = x_offset + (source_x - x0) * common_scale
                desired_y = (
                    TEXT_CENTER_Y_MM
                    + (source_y - y_center_units) * common_scale
                )
                command_y = LOCAL_Y_ANCHOR_MM + (
                    desired_y - LOCAL_Y_ANCHOR_MM
                ) * LOCAL_Y_SCALE
                command_point = PathPoint(
                    lround(desired_x * COORDINATE_SCALE),
                    lround(command_y * COORDINATE_SCALE),
                    point_index != 0,
                )
                desired_point = DesiredPoint(
                    desired_x, desired_y, point_index != 0
                )
                if (
                    command_points
                    and point_index != 0
                    and command_points[-1] == command_point
                ):
                    continue
                command_points.append(command_point)
                desired_points.append(desired_point)

    if not command_points or command_points[0].draw:
        raise AssertionError("generated V36 path must begin pen-up")
    return GeneratedPath(
        tuple(command_points),
        tuple(desired_points),
        bounds,
        common_scale,
    )


def generate_path() -> tuple[PathPoint, ...]:
    return generate().command_points


def path_crc32(points: tuple[PathPoint, ...]) -> int:
    payload = bytearray()
    for point in points:
        payload.extend(
            struct.pack("<hhB", point.x_x10, point.y_x10, int(point.draw))
        )
    return zlib.crc32(payload) & 0xFFFFFFFF


def write_header(generated: GeneratedPath) -> None:
    points = generated.command_points
    xs = [point.x_x10 for point in points]
    ys = [point.y_x10 for point in points]
    move_count = sum(not point.draw for point in points)
    draw_count = len(points) - move_count
    crc = path_crc32(points)
    lines = [
        "/**",
        " * @file    author_text_demo_path.h",
        " * @brief   Generated large Kaishu stroke-median path for gated V36.",
        " */",
        "#ifndef AUTHOR_TEXT_DEMO_PATH_H",
        "#define AUTHOR_TEXT_DEMO_PATH_H",
        "",
        "#include <stdint.h>",
        "",
        "typedef struct {",
        "    int16_t x_x10;",
        "    int16_t y_x10;",
        "    uint8_t draw;",
        "} author_text_demo_path_point_t;",
        "",
        f"#define AUTHOR_TEXT_DEMO_PATH_POINT_COUNT ({len(points)}u)",
        f"#define AUTHOR_TEXT_DEMO_PATH_MOVE_COUNT  ({move_count}u)",
        f"#define AUTHOR_TEXT_DEMO_PATH_DRAW_COUNT  ({draw_count}u)",
        f"#define AUTHOR_TEXT_DEMO_PATH_CRC32       (0x{crc:08X}u)",
        f"#define AUTHOR_TEXT_DEMO_PATH_X_MIN_X10   ({min(xs)})",
        f"#define AUTHOR_TEXT_DEMO_PATH_X_MAX_X10   ({max(xs)})",
        f"#define AUTHOR_TEXT_DEMO_PATH_Y_MIN_X10   ({min(ys)})",
        f"#define AUTHOR_TEXT_DEMO_PATH_Y_MAX_X10   ({max(ys)})",
        f"#define AUTHOR_TEXT_DEMO_PATH_GLYPH_COUNT ({len(GLYPHS)}u)",
        f"#define AUTHOR_TEXT_DEMO_PATH_STROKE_COUNT ({move_count}u)",
        "#define AUTHOR_TEXT_DEMO_LOCAL_Y_SCALE_X10000 (10950)",
        "#define AUTHOR_TEXT_DEMO_LOCAL_Y_ANCHOR_X10 (650)",
        "#define AUTHOR_TEXT_DEMO_TARGET_CENTER_X10 (2050)",
        "#define AUTHOR_TEXT_DEMO_TARGET_CENTER_Y10 (650)",
        "#define AUTHOR_TEXT_DEMO_TARGET_MAX_GLYPH_HEIGHT_X10 (160)",
        "",
        f"/* Hanzi Writer Data commit: {SOURCE_COMMIT} */",
        "/* Glyphs: U+5F20 U+4F73 U+4E50; ordered medians only. */",
        "static const author_text_demo_path_point_t",
        "    s_author_text_demo_path[AUTHOR_TEXT_DEMO_PATH_POINT_COUNT] = {",
    ]
    lines.extend(
        f"    {{{point.x_x10}, {point.y_x10}, {1 if point.draw else 0}u}},"
        for point in points
    )
    lines.extend(
        [
            "};",
            "",
            "#endif /* AUTHOR_TEXT_DEMO_PATH_H */",
            "",
        ]
    )
    HEADER_PATH.write_text("\n".join(lines), encoding="ascii", newline="\n")


def preview_xy(
    x_mm: float,
    y_mm: float,
    pixels_per_mm: float,
    x0_mm: float = 0.0,
    y1_mm: float = A4_HEIGHT_MM,
) -> tuple[int, int]:
    return (
        lround((x_mm - x0_mm) * pixels_per_mm),
        lround((y1_mm - y_mm) * pixels_per_mm),
    )


def draw_path(
    draw: ImageDraw.ImageDraw,
    points: tuple[DesiredPoint, ...],
    pixels_per_mm: float,
    x0_mm: float,
    y1_mm: float,
    start_xy: tuple[float, float],
    draw_width: int,
) -> None:
    previous = preview_xy(
        start_xy[0], start_xy[1], pixels_per_mm, x0_mm, y1_mm
    )
    for point in points:
        current = preview_xy(
            point.x_mm, point.y_mm, pixels_per_mm, x0_mm, y1_mm
        )
        color = (15, 15, 15) if point.draw else (218, 218, 218)
        width = draw_width if point.draw else 1
        draw.line([previous, current], fill=color, width=width)
        previous = current


def write_previews(generated: GeneratedPath) -> None:
    full_scale = 4
    image = Image.new(
        "RGB",
        (
            lround(A4_WIDTH_MM * full_scale) + 1,
            lround(A4_HEIGHT_MM * full_scale) + 1,
        ),
        "white",
    )
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        [
            preview_xy(0.0, A4_HEIGHT_MM, full_scale),
            preview_xy(A4_WIDTH_MM, 0.0, full_scale),
        ],
        outline=(25, 25, 25),
        width=3,
    )
    draw.rectangle(
        [
            preview_xy(SAFE_X0_MM, SAFE_Y1_MM, full_scale),
            preview_xy(SAFE_X1_MM, SAFE_Y0_MM, full_scale),
        ],
        outline=(160, 160, 160),
        width=2,
    )
    align = preview_xy(ALIGN_X_MM, ALIGN_Y_MM, full_scale)
    draw.ellipse(
        [align[0] - 5, align[1] - 5, align[0] + 5, align[1] + 5],
        fill=(180, 20, 20),
    )
    draw_path(
        draw,
        generated.desired_points,
        full_scale,
        0.0,
        A4_HEIGHT_MM,
        (ALIGN_X_MM, ALIGN_Y_MM),
        2,
    )
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)

    detail_x0 = 174.0
    detail_x1 = 236.0
    detail_y0 = 53.0
    detail_y1 = 77.0
    detail_scale = 20
    detail = Image.new(
        "RGB",
        (
            lround((detail_x1 - detail_x0) * detail_scale) + 1,
            lround((detail_y1 - detail_y0) * detail_scale) + 1,
        ),
        "white",
    )
    detail_draw = ImageDraw.Draw(detail)
    for x_value in range(math.ceil(detail_x0), math.floor(detail_x1) + 1):
        x_pixel = preview_xy(
            float(x_value), detail_y0, detail_scale, detail_x0, detail_y1
        )[0]
        shade = 215 if x_value % 5 == 0 else 238
        detail_draw.line(
            [(x_pixel, 0), (x_pixel, detail.height - 1)],
            fill=(shade, shade, shade),
            width=1,
        )
    for y_value in range(math.ceil(detail_y0), math.floor(detail_y1) + 1):
        y_pixel = preview_xy(
            detail_x0, float(y_value), detail_scale, detail_x0, detail_y1
        )[1]
        shade = 215 if y_value % 5 == 0 else 238
        detail_draw.line(
            [(0, y_pixel), (detail.width - 1, y_pixel)],
            fill=(shade, shade, shade),
            width=1,
        )
    draw_path(
        detail_draw,
        generated.desired_points,
        detail_scale,
        detail_x0,
        detail_y1,
        (
            generated.desired_points[0].x_mm,
            generated.desired_points[0].y_mm,
        ),
        4,
    )
    DETAIL_PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    detail.save(DETAIL_PREVIEW_PATH)


def maximum_span(points: tuple[DesiredPoint, ...]) -> tuple[float, float]:
    maximum_draw = 0.0
    maximum_move = 0.0
    previous: DesiredPoint | None = None
    for point in points:
        if previous is not None:
            span = math.hypot(
                point.x_mm - previous.x_mm, point.y_mm - previous.y_mm
            )
            if point.draw:
                maximum_draw = max(maximum_draw, span)
            else:
                maximum_move = max(maximum_move, span)
        previous = point
    return maximum_draw, maximum_move


def report(generated: GeneratedPath) -> None:
    command = generated.command_points
    desired = generated.desired_points
    command_xs = [point.x_mm for point in command]
    command_ys = [point.y_mm for point in command]
    desired_xs = [point.x_mm for point in desired]
    desired_ys = [point.y_mm for point in desired]
    maximum_draw, maximum_move = maximum_span(desired)
    print(f"source_commit={SOURCE_COMMIT}")
    for source in GLYPHS:
        print(
            f"glyph={source.codepoint} strokes={source.stroke_count} "
            f"median_points={source.median_point_count} sha256={source.sha256}"
        )
    print(
        f"path_points={len(command)} move_points="
        f"{sum(not point.draw for point in command)} draw_points="
        f"{sum(point.draw for point in command)} crc32={path_crc32(command):08X}"
    )
    print(
        f"desired_bounds_mm=({min(desired_xs):.3f},{min(desired_ys):.3f}).."
        f"({max(desired_xs):.3f},{max(desired_ys):.3f}) "
        f"command_bounds_mm=({min(command_xs):.1f},{min(command_ys):.1f}).."
        f"({max(command_xs):.1f},{max(command_ys):.1f})"
    )
    print(
        f"common_scale_mm_per_unit={generated.common_scale_mm_per_unit:.9f} "
        f"max_draw_source_span_mm={maximum_draw:.6f} "
        f"max_penup_source_span_mm={maximum_move:.6f}"
    )
    print(f"header={HEADER_PATH}")
    print(f"preview={PREVIEW_PATH}")
    print(f"detail_preview={DETAIL_PREVIEW_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generated = generate()
    if not args.check:
        write_header(generated)
        write_previews(generated)
    report(generated)


if __name__ == "__main__":
    main()
