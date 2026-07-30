"""Contract and file checks for the combined 4x7 V23 dot pass."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GCODE = ROOT / "gcode" / (
    "PAPER_A4_4X7_REACH_RAW_DOT_GCODE_V23.gcode"
)
GCODE_SOURCE = ROOT / "TASK" / "gcode_serial.c"
GCODE_HEADER = ROOT / "TASK" / "gcode_serial.h"
MAP_SOURCE = ROOT / "APP" / "Src" / "app_writer_paper_map.c"
MAP_HEADER = ROOT / "APP" / "Inc" / "app_writer_paper_map.h"
SELECTOR = ROOT / "TASK" / "writer_test.h"
PROJECT = ROOT / "keil" / (
    "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx"
)
PIN_CONFIG = ROOT / "ti_msp_dl_config.c"

XS = (25.0, 78.333, 131.667, 185.0)
YS = (
    20.0, 56.667, 93.333, 130.0,
    167.0, 203.667, 240.333,
)


def snake_order() -> tuple[tuple[float, float], ...]:
    result = []
    for row, y_mm in enumerate(YS):
        row_x = XS if row % 2 == 0 else tuple(reversed(XS))
        result.extend((x_mm, y_mm) for x_mm in row_x)
    return tuple(result)


def main() -> None:
    gcode = GCODE.read_text(encoding="utf-8")
    source = GCODE_SOURCE.read_text(encoding="utf-8")
    header = GCODE_HEADER.read_text(encoding="utf-8")
    map_source = MAP_SOURCE.read_text(encoding="utf-8")
    map_header = MAP_HEADER.read_text(encoding="utf-8")
    selector = SELECTOR.read_text(encoding="utf-8")
    project = PROJECT.read_text(encoding="utf-8")
    pin_config = PIN_CONFIG.read_text(encoding="utf-8")
    combined = source + header + map_source + map_header

    required = (
        "PAPER_A4_4X7_REACH_RAW_DOT_GCODE_V23",
        "A4_BASE_QUADRATIC_GRID4X7_REACH_RAW_V3",
        "APP_WRITER_PAPER_Y_MIN_MM             (20.0f)",
        "APP_WRITER_PAPER_Y_MAX_MM             (240.333333f)",
        "APP_WRITER_PAPER_GRID_COLS             (4u)",
        "APP_WRITER_PAPER_GRID_ROWS             (7u)",
        "20.0f, 56.666667f, 93.333333f, 130.0f",
        "167.0f, 203.666667f, 240.333333f",
        "APP_WRITER_PAPER_GRID_CORRECTION_ENABLE (0u)",
        "GCODE_SERIAL_RESTRICTED_RECT_ENABLE   (0u)",
        "grid4x7=%u",
        "WriterPaperMap_To_User",
    )
    for text in required:
        if text not in combined:
            raise AssertionError(f"contract text missing: {text}")
    if (
        "#define WRITER_TEST_MODE             "
        "WRITER_TEST_MODE_GCODE_SERIAL"
    ) not in selector:
        raise AssertionError("standard G-code mode is not selected")
    if "app_writer_paper_map.c" not in project:
        raise AssertionError("paper map source is absent from Keil project")
    if pin_config.count("DL_GPIO_RESISTOR_PULL_UP") != 2:
        raise AssertionError("both limit inputs must retain pull-ups")

    lines = [line.strip() for line in gcode.splitlines() if line.strip()]
    if lines[:5] != ["G21", "G90", "G94", "M5", "F180"]:
        raise AssertionError("G-code preamble mismatch")
    if lines.count("M3") != 28 or lines.count("G4 P0.3") != 28:
        raise AssertionError("expected twenty-eight dot operations")
    if lines.count("M5") != 29:
        raise AssertionError("expected twenty-nine pen-up commands")
    if "M801" in gcode:
        raise AssertionError("standard G-code must not use M801")

    pattern = re.compile(
        r"^G0 X(-?\d+(?:\.\d+)?) Y(-?\d+(?:\.\d+)?) ; P(\d+)$"
    )
    moves = []
    labels = []
    for line in lines:
        match = pattern.match(line)
        if match is not None:
            moves.append(
                (float(match.group(1)), float(match.group(2)))
            )
            labels.append(int(match.group(3)))
    if tuple(moves) != snake_order():
        raise AssertionError("unexpected 4x7 snake execution order")
    if set(moves) != {(x, y) for y in YS for x in XS}:
        raise AssertionError("4x7 node set mismatch")
    if sorted(labels) != list(range(1, 29)):
        raise AssertionError("point labels must be P1 through P28")

    print(
        "paper_a4_4x7_reach_raw_dot_gcode_v23=PASS "
        f"points={len(moves)} gcode_lines={len(lines)} "
        "paper_x=25..185 paper_y=20..240.333 "
        "grid_correction=OFF standard_gcode=1"
    )


if __name__ == "__main__":
    main()
