"""Generate the gated V31 path from the archived V7 single-line G-code."""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SOURCE_GCODE = (
    ROOT
    / "backups"
    / "GCODE_HOME0_135_CENTER_ANCHOR_V7_20260718_222427"
    / "gcode"
    / "G_Code.txt.gcode"
)
HEADER_PATH = ROOT / "TASK" / "author_text_demo_path.h"
PREVIEW_PATH = (
    ROOT
    / "docs"
    / "diagnostics"
    / "AUTHOR_STAGED_V7_SINGLELINE_X2_L205_L203_GATED_V31_PREVIEW.png"
)

SOURCE_SHA256 = "901648BF916FBF353F1026387F520284D39FA77782B1BC081496B06B0FA208FD"
SOURCE_ORIGIN_X_MM = 31.800001
SOURCE_ORIGIN_Y_MM = -25.984985
SOURCE_LINE_COUNT = 262
SOURCE_STROKE_COUNT = 27
SOURCE_RAW_G0_COUNT = 29
SOURCE_RAW_G1_COUNT = 119
SOURCE_EFFECTIVE_G0_COUNT = 26
SOURCE_EFFECTIVE_G1_COUNT = 114

A4_WIDTH_MM = 297.0
A4_HEIGHT_MM = 210.0
SAFE_X0_MM = 145.0
SAFE_Y0_MM = 15.0
SAFE_X1_MM = 275.0
SAFE_Y1_MM = 125.0
V30_TEXT_X0_MM = 154.0
V30_TEXT_X1_MM = 257.9
LINE_BASELINES_Y_MM = (67.0, 87.0)

ALIGN_X_MM = 150.0
ALIGN_Y_MM = 20.0
AXIS_STEP_MM = 20.0
BOX_SIZE_MM = 20.0
BOX_GAP_MM = 10.0
COORDINATE_SCALE = 10

WORD_RE = re.compile(
    r"([A-Za-z])([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
)


@dataclass(frozen=True)
class SourcePoint:
    x_mm: float
    y_mm: float
    draw: bool


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


def lround(value: float) -> int:
    if value >= 0.0:
        return math.floor(value + 0.5)
    return math.ceil(value - 0.5)


def parse_words(text: str, line_number: int) -> dict[str, float]:
    words: dict[str, float] = {}
    cursor = 0
    while cursor < len(text):
        if text[cursor].isspace():
            cursor += 1
            continue
        match = WORD_RE.match(text, cursor)
        if match is None:
            raise AssertionError(
                f"line {line_number}: parse error at {text[cursor:]!r}"
            )
        letter = match.group(1).upper()
        if letter not in "GMXYZFSP":
            raise AssertionError(f"line {line_number}: unsupported word {letter}")
        if letter in words:
            raise AssertionError(f"line {line_number}: duplicate word {letter}")
        words[letter] = float(match.group(2))
        cursor = match.end()
    return words


def integer_code(value: float, line_number: int, letter: str) -> int:
    rounded = round(value)
    if abs(value - rounded) > 0.001:
        raise AssertionError(f"line {line_number}: non-integer {letter}{value}")
    return int(rounded)


def verify_source() -> list[str]:
    data = SOURCE_GCODE.read_bytes()
    digest = hashlib.sha256(data).hexdigest().upper()
    if digest != SOURCE_SHA256:
        raise AssertionError(
            f"V7 source hash changed: expected {SOURCE_SHA256}, got {digest}"
        )
    lines = data.decode("ascii").splitlines()
    if len(lines) != SOURCE_LINE_COUNT:
        raise AssertionError(f"V7 source line count changed: {len(lines)}")
    return lines


def parse_source_path() -> tuple[SourcePoint, ...]:
    lines = verify_source()
    source_x = 0.0
    source_y = 0.0
    modal_motion: int | None = None
    absolute_mode = False
    millimeter_mode = False
    pen_down = False
    g0_count = 0
    g1_count = 0
    stroke_count = 0
    home_returns = 0
    points: list[SourcePoint] = []

    for line_number, raw_line in enumerate(lines, start=1):
        text = raw_line.strip()
        if not text:
            continue
        words = parse_words(text, line_number)

        if "G" in words:
            code = integer_code(words["G"], line_number, "G")
            if code == 21:
                millimeter_mode = True
            elif code == 90:
                absolute_mode = True
            elif code in (0, 1):
                modal_motion = code
                if code == 0:
                    g0_count += 1
                else:
                    g1_count += 1
            elif code != 4:
                raise AssertionError(f"line {line_number}: unsupported G{code}")

        if "M" in words:
            code = integer_code(words["M"], line_number, "M")
            if code == 3:
                if pen_down:
                    raise AssertionError(f"line {line_number}: duplicate M3")
                pen_down = True
                stroke_count += 1
            elif code == 5:
                pen_down = False
            else:
                raise AssertionError(f"line {line_number}: unsupported M{code}")

        has_xy = ("X" in words) or ("Y" in words)
        if not has_xy:
            continue
        if not absolute_mode or not millimeter_mode or modal_motion is None:
            raise AssertionError(f"line {line_number}: XY before G21/G90/motion")
        if "X" in words:
            source_x = words["X"]
        if "Y" in words:
            source_y = words["Y"]

        if (
            modal_motion == 0
            and abs(source_x) < 1.0e-9
            and abs(source_y) < 1.0e-9
        ):
            home_returns += 1
            continue
        if modal_motion == 1 and not pen_down:
            raise AssertionError(f"line {line_number}: G1 while pen is up")
        if modal_motion == 0 and pen_down:
            raise AssertionError(f"line {line_number}: G0 while pen is down")

        points.append(
            SourcePoint(
                source_x - SOURCE_ORIGIN_X_MM,
                source_y - SOURCE_ORIGIN_Y_MM,
                modal_motion == 1,
            )
        )

    if (g0_count, g1_count) != (SOURCE_RAW_G0_COUNT, SOURCE_RAW_G1_COUNT):
        raise AssertionError(f"V7 motion counts changed: G0={g0_count} G1={g1_count}")
    if stroke_count != SOURCE_STROKE_COUNT:
        raise AssertionError(f"V7 stroke count changed: {stroke_count}")
    if home_returns != 1:
        raise AssertionError(f"V7 source home-return count changed: {home_returns}")
    if not points or points[0].draw:
        raise AssertionError("V7 extracted path must begin pen-up")
    return tuple(points)


def source_bounds(points: tuple[SourcePoint, ...]) -> tuple[float, float, float, float]:
    return (
        min(point.x_mm for point in points),
        min(point.y_mm for point in points),
        max(point.x_mm for point in points),
        max(point.y_mm for point in points),
    )


def horizontal_offset(points: tuple[SourcePoint, ...]) -> float:
    x0, _, x1, _ = source_bounds(points)
    source_center = (x0 + x1) / 2.0
    target_center = (V30_TEXT_X0_MM + V30_TEXT_X1_MM) / 2.0
    return target_center - source_center


def generate_path() -> tuple[PathPoint, ...]:
    source = parse_source_path()
    offset_x = horizontal_offset(source)
    result: list[PathPoint] = []

    for baseline_y in LINE_BASELINES_Y_MM:
        for source_point in source:
            point = PathPoint(
                lround((source_point.x_mm + offset_x) * COORDINATE_SCALE),
                lround((source_point.y_mm + baseline_y) * COORDINATE_SCALE),
                source_point.draw,
            )
            if (
                result
                and result[-1].x_x10 == point.x_x10
                and result[-1].y_x10 == point.y_x10
                and result[-1].draw == point.draw
            ):
                continue
            result.append(point)

    if not result or result[0].draw:
        raise AssertionError("generated V31 path must begin pen-up")
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
        " * @brief   Generated V7 single-line path repeated twice for gated V31.",
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
        "#define AUTHOR_TEXT_DEMO_PATH_COPY_COUNT  (2u)",
        "#define AUTHOR_TEXT_DEMO_SOURCE_STROKES_PER_COPY (27u)",
        "",
        f"/* V7 G-code SHA-256: {SOURCE_SHA256} */",
        "/* Glyphs: U+5F20 U+4F73 U+4E50 (single-line source trajectory) */",
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
        outline=(25, 25, 25),
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
    draw.rectangle(
        [
            preview_xy(V30_TEXT_X0_MM, 122.9, pixels_per_mm),
            preview_xy(V30_TEXT_X1_MM, 47.0, pixels_per_mm),
        ],
        outline=(190, 190, 190),
        width=1,
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
        if previous is not None:
            color = (15, 15, 15) if point.draw else (220, 220, 220)
            width = 2 if point.draw else 1
            draw.line([previous, current], fill=color, width=width)
        previous = current

    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def report(points: tuple[PathPoint, ...]) -> None:
    source = parse_source_path()
    source_box = source_bounds(source)
    xs = [point.x_mm for point in points]
    ys = [point.y_mm for point in points]
    move_count = sum(not point.draw for point in points)
    max_draw_span = 0.0
    previous: PathPoint | None = None
    for point in points:
        if point.draw and previous is not None:
            max_draw_span = max(
                max_draw_span,
                math.hypot(point.x_mm - previous.x_mm, point.y_mm - previous.y_mm),
            )
        previous = point
    print(f"source_sha256={SOURCE_SHA256}")
    print(
        f"source_lines={SOURCE_LINE_COUNT} strokes={SOURCE_STROKE_COUNT} "
        f"raw_G0={SOURCE_RAW_G0_COUNT} raw_G1={SOURCE_RAW_G1_COUNT} "
        f"V7_effective_motions={SOURCE_EFFECTIVE_G0_COUNT + SOURCE_EFFECTIVE_G1_COUNT} "
        f"effective_G0={SOURCE_EFFECTIVE_G0_COUNT} "
        f"effective_G1={SOURCE_EFFECTIVE_G1_COUNT}"
    )
    print(
        f"source_bounds_mm=({source_box[0]:.6f},{source_box[1]:.6f}).."
        f"({source_box[2]:.6f},{source_box[3]:.6f})"
    )
    print(
        f"path_points={len(points)} move_points={move_count} "
        f"draw_points={len(points) - move_count} copies=2 "
        f"crc32={path_crc32(points):08X}"
    )
    print(
        f"path_bounds_mm=({min(xs):.1f},{min(ys):.1f}).."
        f"({max(xs):.1f},{max(ys):.1f}) max_draw_span_mm={max_draw_span:.6f}"
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
