"""Generate the fixed four-line outline path for the staged V30 demo."""

from __future__ import annotations

import argparse
import hashlib
import math
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
HEADER_PATH = ROOT / "TASK" / "author_text_demo_path.h"
PREVIEW_PATH = (
    ROOT
    / "docs"
    / "diagnostics"
    / "AUTHOR_STAGED_TEXT_DEMO_L205_L203_GATED_V30_PREVIEW.png"
)

FONT_PATH = Path(r"C:\Windows\Fonts\simkai.ttf")
FONT_SHA256 = "A6ACF69A7A6E8A4CBA014266036ECA8629560038CC50783F46917748FABEFBE5"
FONT_PIXEL_SIZE = 192
GLYPH_CANVAS_PX = 256
CONTOUR_EPSILON_PX = 1.5
MIN_CONTOUR_AREA_PX2 = 4.0

TEXT_LINES = (
    "\u5199\u5b57\u673a\u5668\u4eba",
    "\u4eca\u5929\u6765\u6d4b\u8bd5",
    "\u6a2a\u5e73\u7ad6\u76f4\u7a33",
    "\u5f20\u4f73\u4e50\u4f5c\u54c1",
)
TEXT_CODEPOINTS = (
    "5199-5B57-673A-5668-4EBA/"
    "4ECA-5929-6765-6D4B-8BD5/"
    "6A2A-5E73-7AD6-76F4-7A33/"
    "5F20-4F73-4E50-4F5C-54C1"
)

A4_WIDTH_MM = 297.0
A4_HEIGHT_MM = 210.0
SAFE_X0_MM = 145.0
SAFE_Y0_MM = 15.0
SAFE_X1_MM = 275.0
SAFE_Y1_MM = 125.0

ALIGN_X_MM = 150.0
ALIGN_Y_MM = 20.0
AXIS_STEP_MM = 20.0
BOX_SIZE_MM = 20.0
BOX_GAP_MM = 10.0

TEXT_X0_MM = 151.0
TEXT_ROW_BOTTOMS_MM = (107.0, 87.0, 67.0, 47.0)
TEXT_CELL_WIDTH_MM = 22.0
TEXT_GLYPH_SIZE_MM = 16.0
TEXT_GLYPH_BOX_HEIGHT_MM = 16.0
MAX_POINT_SPAN_MM = 0.65
COORDINATE_SCALE = 10


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


def lround(value: float) -> int:
    if value >= 0.0:
        return math.floor(value + 0.5)
    return math.ceil(value - 0.5)


def require_font() -> None:
    if not FONT_PATH.is_file():
        raise FileNotFoundError(f"required font not found: {FONT_PATH}")
    digest = hashlib.sha256(FONT_PATH.read_bytes()).hexdigest().upper()
    if digest != FONT_SHA256:
        raise AssertionError(
            f"font SHA-256 changed: expected {FONT_SHA256}, got {digest}"
        )


def render_glyph_mask(
    font: ImageFont.FreeTypeFont, character: str
) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    image = Image.new("L", (GLYPH_CANVAS_PX, GLYPH_CANVAS_PX), 0)
    draw = ImageDraw.Draw(image)
    bbox = draw.textbbox((0, 0), character, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    if width <= 0 or height <= 0:
        raise AssertionError(f"empty glyph U+{ord(character):04X}")
    draw.text(
        (
            (GLYPH_CANVAS_PX - width) // 2 - bbox[0],
            (GLYPH_CANVAS_PX - height) // 2 - bbox[1],
        ),
        character,
        font=font,
        fill=255,
    )
    mask = np.asarray(image)
    nonzero = cv2.findNonZero(mask)
    if nonzero is None:
        raise AssertionError(f"font has no glyph U+{ord(character):04X}")
    x, y, width, height = cv2.boundingRect(nonzero)
    return mask, (x, y, width, height)


def contour_to_mm(
    contour: np.ndarray,
    mask_bounds: tuple[int, int, int, int],
    cell_x_mm: float,
    row_bottom_mm: float,
) -> list[tuple[float, float]]:
    x0, y0, width, height = mask_bounds
    scale = TEXT_GLYPH_SIZE_MM / max(width, height)
    glyph_width_mm = width * scale
    glyph_height_mm = height * scale
    glyph_x_mm = cell_x_mm + (TEXT_CELL_WIDTH_MM - glyph_width_mm) / 2.0
    glyph_y_mm = row_bottom_mm + (
        TEXT_GLYPH_BOX_HEIGHT_MM - glyph_height_mm
    ) / 2.0
    simplified = cv2.approxPolyDP(
        contour, CONTOUR_EPSILON_PX, True
    ).reshape(-1, 2)
    if len(simplified) < 3:
        return []

    result: list[tuple[float, float]] = []
    for px, py in simplified:
        result.append(
            (
                glyph_x_mm + (float(px) - x0) * scale,
                glyph_y_mm + (float(y0 + height - 1) - float(py)) * scale,
            )
        )
    return result


def append_contour(
    result: list[PathPoint], contour: list[tuple[float, float]]
) -> None:
    if len(contour) < 3:
        return

    start = contour[0]
    start_point = PathPoint(
        lround(start[0] * COORDINATE_SCALE),
        lround(start[1] * COORDINATE_SCALE),
        False,
    )
    result.append(start_point)

    closed = contour[1:] + [start]
    previous = start
    for target in closed:
        distance = math.hypot(target[0] - previous[0], target[1] - previous[1])
        subdivisions = max(1, math.ceil(distance / MAX_POINT_SPAN_MM))
        for index in range(1, subdivisions + 1):
            ratio = index / subdivisions
            point = PathPoint(
                lround(
                    (previous[0] + (target[0] - previous[0]) * ratio)
                    * COORDINATE_SCALE
                ),
                lround(
                    (previous[1] + (target[1] - previous[1]) * ratio)
                    * COORDINATE_SCALE
                ),
                True,
            )
            if result[-1].x_x10 != point.x_x10 or result[-1].y_x10 != point.y_x10:
                result.append(point)
        previous = target


def generate_path() -> tuple[PathPoint, ...]:
    require_font()
    font = ImageFont.truetype(str(FONT_PATH), FONT_PIXEL_SIZE)
    result: list[PathPoint] = []
    glyph_digests: set[str] = set()

    for line_index, text in enumerate(TEXT_LINES):
        row_bottom = TEXT_ROW_BOTTOMS_MM[line_index]
        for column_index, character in enumerate(text):
            mask, bounds = render_glyph_mask(font, character)
            glyph_digests.add(hashlib.sha256(mask.tobytes()).hexdigest())
            contours, _ = cv2.findContours(
                mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE
            )
            cell_x = TEXT_X0_MM + column_index * TEXT_CELL_WIDTH_MM
            for contour in contours:
                if abs(cv2.contourArea(contour)) < MIN_CONTOUR_AREA_PX2:
                    continue
                append_contour(
                    result,
                    contour_to_mm(contour, bounds, cell_x, row_bottom),
                )

    if len(glyph_digests) != sum(len(line) for line in TEXT_LINES):
        raise AssertionError("one or more Chinese glyphs rendered identically")
    if not result:
        raise AssertionError("generated path is empty")
    if result[0].draw:
        raise AssertionError("path must begin pen-up")
    return tuple(result)


def path_crc32(points: tuple[PathPoint, ...]) -> int:
    payload = bytearray()
    for point in points:
        payload.extend(
            struct.pack("<hhB", point.x_x10, point.y_x10, int(point.draw))
        )
    return zlib.crc32(payload) & 0xFFFFFFFF


def write_header(points: tuple[PathPoint, ...]) -> None:
    crc = path_crc32(points)
    xs = [point.x_x10 for point in points]
    ys = [point.y_x10 for point in points]
    move_count = sum(not point.draw for point in points)
    draw_count = len(points) - move_count
    lines = [
        "/**",
        " * @file    author_text_demo_path.h",
        " * @brief   Generated 0.1 mm outline path for the staged V30 text demo.",
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
        "",
        f"/* SimKai SHA-256: {FONT_SHA256} */",
        f"/* Glyphs: {TEXT_CODEPOINTS} */",
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


def preview_xy(x_mm: float, y_mm: float, pixels_per_mm: int) -> tuple[int, int]:
    return (
        lround(x_mm * pixels_per_mm),
        lround((A4_HEIGHT_MM - y_mm) * pixels_per_mm),
    )


def write_preview(points: tuple[PathPoint, ...]) -> None:
    pixels_per_mm = 4
    image = Image.new(
        "RGB",
        (
            lround(A4_WIDTH_MM * pixels_per_mm) + 1,
            lround(A4_HEIGHT_MM * pixels_per_mm) + 1,
        ),
        "white",
    )
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        [
            preview_xy(0.0, A4_HEIGHT_MM, pixels_per_mm),
            preview_xy(A4_WIDTH_MM, 0.0, pixels_per_mm),
        ],
        outline=(30, 30, 30),
        width=3,
    )
    draw.rectangle(
        [
            preview_xy(SAFE_X0_MM, SAFE_Y1_MM, pixels_per_mm),
            preview_xy(SAFE_X1_MM, SAFE_Y0_MM, pixels_per_mm),
        ],
        outline=(130, 130, 130),
        width=2,
    )

    anchor = preview_xy(ALIGN_X_MM, ALIGN_Y_MM, pixels_per_mm)
    x_point = preview_xy(ALIGN_X_MM + AXIS_STEP_MM, ALIGN_Y_MM, pixels_per_mm)
    y_point = preview_xy(ALIGN_X_MM, ALIGN_Y_MM + AXIS_STEP_MM, pixels_per_mm)
    for point, color in (
        (anchor, (180, 20, 20)),
        (x_point, (20, 110, 200)),
        (y_point, (30, 150, 70)),
    ):
        draw.ellipse(
            [point[0] - 5, point[1] - 5, point[0] + 5, point[1] + 5],
            fill=color,
        )

    first_box = (
        ALIGN_X_MM,
        ALIGN_Y_MM,
        ALIGN_X_MM + BOX_SIZE_MM,
        ALIGN_Y_MM + BOX_SIZE_MM,
    )
    second_x0 = ALIGN_X_MM + BOX_SIZE_MM + BOX_GAP_MM
    second_box = (
        second_x0,
        ALIGN_Y_MM,
        second_x0 + BOX_SIZE_MM,
        ALIGN_Y_MM + BOX_SIZE_MM,
    )
    for box, color in ((first_box, (20, 110, 200)), (second_box, (30, 150, 70))):
        draw.rectangle(
            [
                preview_xy(box[0], box[3], pixels_per_mm),
                preview_xy(box[2], box[1], pixels_per_mm),
            ],
            outline=color,
            width=3,
        )

    previous: tuple[int, int] | None = None
    for point in points:
        current = preview_xy(point.x_mm, point.y_mm, pixels_per_mm)
        if point.draw and previous is not None:
            draw.line([previous, current], fill=(15, 15, 15), width=2)
        previous = current

    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def report(points: tuple[PathPoint, ...]) -> None:
    xs = [point.x_mm for point in points]
    ys = [point.y_mm for point in points]
    move_count = sum(not point.draw for point in points)
    maximum_span = 0.0
    previous: PathPoint | None = None
    for point in points:
        if point.draw and previous is not None:
            maximum_span = max(
                maximum_span,
                math.hypot(point.x_mm - previous.x_mm, point.y_mm - previous.y_mm),
            )
        previous = point
    print(f"font_sha256={FONT_SHA256}")
    print(f"glyph_codepoints={TEXT_CODEPOINTS}")
    print(
        f"path_points={len(points)} move_points={move_count} "
        f"draw_points={len(points) - move_count} crc32={path_crc32(points):08X}"
    )
    print(
        f"path_bounds_mm=({min(xs):.1f},{min(ys):.1f}).."
        f"({max(xs):.1f},{max(ys):.1f}) max_draw_span_mm={maximum_span:.6f}"
    )
    print(f"header={HEADER_PATH}")
    print(f"preview={PREVIEW_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    points = generate_path()
    if not args.check:
        write_header(points)
        write_preview(points)
    report(points)


if __name__ == "__main__":
    main()
