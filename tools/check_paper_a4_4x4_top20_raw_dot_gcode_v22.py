"""Contract and file checks for the top-margin-20 mm V22 dot pass."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GCODE = ROOT / "gcode" / (
    "PAPER_A4_4X4_TOP20_RAW_DOT_GCODE_V22.gcode"
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
YS = (167.0, 203.667, 240.333, 277.0)
EXPECTED_ORDER = (
    (25.0, 167.0), (78.333, 167.0),
    (131.667, 167.0), (185.0, 167.0),
    (185.0, 203.667), (131.667, 203.667),
    (78.333, 203.667), (25.0, 203.667),
    (25.0, 240.333), (78.333, 240.333),
    (131.667, 240.333), (185.0, 240.333),
    (185.0, 277.0), (131.667, 277.0),
    (78.333, 277.0), (25.0, 277.0),
)


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
        "PAPER_A4_4X4_TOP20_RAW_DOT_GCODE_V22",
        "A4_BASE_QUADRATIC_GRID4X4_TOP20_RAW_V2",
        "APP_WRITER_PAPER_Y_MIN_MM             (167.0f)",
        "APP_WRITER_PAPER_Y_MAX_MM             (277.0f)",
        "167.0f, 203.666667f, 240.333333f, 277.0f",
        "APP_WRITER_PAPER_GRID_CORRECTION_ENABLE (0u)",
        "GCODE_SERIAL_RESTRICTED_RECT_ENABLE   (0u)",
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
    if lines.count("M3") != 16 or lines.count("G4 P0.3") != 16:
        raise AssertionError("expected sixteen dot operations")
    if lines.count("M5") != 17:
        raise AssertionError("expected seventeen pen-up commands")
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
    if tuple(moves) != EXPECTED_ORDER:
        raise AssertionError("unexpected snake execution order")
    if set(moves) != {(x, y) for y in YS for x in XS}:
        raise AssertionError("4x4 node set mismatch")
    if sorted(labels) != list(range(1, 17)):
        raise AssertionError("point labels must be P1 through P16")
    if max(y for _, y in moves) != 297.0 - 20.0:
        raise AssertionError("top boundary is not 20 mm below A4 top")

    print(
        "paper_a4_4x4_top20_raw_dot_gcode_v22=PASS "
        f"points={len(moves)} gcode_lines={len(lines)} "
        "paper_x=25..185 paper_y=167..277 "
        "a4_top_margin_mm=20 grid_correction=OFF"
    )


if __name__ == "__main__":
    main()
