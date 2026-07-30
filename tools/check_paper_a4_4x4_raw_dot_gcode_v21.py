"""Offline contract, G-code, mapping, planner, and kinematic checks for V21."""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np

from check_fixed_layout_3rect_x95_y20_130_waypoint_v17 import (
    HOME_USER,
    MIN_REQUIRED_MARGIN_DEG,
    PLAN_MAX_SEGMENTS,
    margin,
    samples,
)
from derive_grid9_limited_y_v15 import (
    calibration_arrays,
    evaluate,
    fit,
)


ROOT = Path(__file__).resolve().parents[1]
GCODE = ROOT / "gcode" / "PAPER_A4_4X4_RAW_DOT_GCODE_V21.gcode"
GCODE_SOURCE = ROOT / "TASK" / "gcode_serial.c"
GCODE_HEADER = ROOT / "TASK" / "gcode_serial.h"
SELECTOR = ROOT / "TASK" / "writer_test.h"
MAP_SOURCE = ROOT / "APP" / "Src" / "app_writer_paper_map.c"
MAP_HEADER = ROOT / "APP" / "Inc" / "app_writer_paper_map.h"
PIN_CONFIG = ROOT / "ti_msp_dl_config.c"
PROJECT = ROOT / "keil" / (
    "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx"
)

XS = (25.0, 78.333, 131.667, 185.0)
YS = (20.0, 56.667, 93.333, 130.0)
ROW_MAJOR = tuple((x, y) for y in YS for x in XS)
EXECUTION_ORDER = (
    (25.0, 20.0), (78.333, 20.0),
    (131.667, 20.0), (185.0, 20.0),
    (185.0, 56.667), (131.667, 56.667),
    (78.333, 56.667), (25.0, 56.667),
    (25.0, 93.333), (78.333, 93.333),
    (131.667, 93.333), (185.0, 93.333),
    (185.0, 130.0), (131.667, 130.0),
    (78.333, 130.0), (25.0, 130.0),
)


def main() -> None:
    gcode = GCODE.read_text(encoding="utf-8")
    gcode_source = GCODE_SOURCE.read_text(encoding="utf-8")
    gcode_header = GCODE_HEADER.read_text(encoding="utf-8")
    selector = SELECTOR.read_text(encoding="utf-8")
    map_source = MAP_SOURCE.read_text(encoding="utf-8")
    map_header = MAP_HEADER.read_text(encoding="utf-8")
    pin_config = PIN_CONFIG.read_text(encoding="utf-8")
    project = PROJECT.read_text(encoding="utf-8")
    combined = gcode_source + gcode_header + map_source + map_header

    required = (
        "PAPER_A4_4X4_RAW_DOT_GCODE_V21",
        "A4_BASE_QUADRATIC_GRID4X4_RAW_V1",
        "GCODE_SERIAL_PAPER_CALIBRATION_ENABLE (1u)",
        "GCODE_SERIAL_RESTRICTED_RECT_ENABLE   (0u)",
        "APP_WRITER_PAPER_GRID_CORRECTION_ENABLE (0u)",
        "APP_WRITER_PAPER_X_MIN_MM             (25.0f)",
        "APP_WRITER_PAPER_X_MAX_MM             (185.0f)",
        "APP_WRITER_PAPER_Y_MIN_MM             (20.0f)",
        "APP_WRITER_PAPER_Y_MAX_MM             (130.0f)",
        "WriterPaperMap_To_User",
        "paper_coordinate_out_of_bounds",
        "runtime_limit_active",
        "paper_map=%s grid4x4=%u",
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

    lines = [
        line.strip() for line in gcode.splitlines()
        if line.strip()
    ]
    if lines[:5] != ["G21", "G90", "G94", "M5", "F180"]:
        raise AssertionError("standard G-code preamble mismatch")
    if lines.count("M3") != 16:
        raise AssertionError("expected sixteen pen-down events")
    if lines.count("G4 P0.3") != 16:
        raise AssertionError("expected sixteen dot dwells")
    if lines.count("M5") != 17:
        raise AssertionError("expected preflight plus sixteen pen-up events")
    if any(line.startswith("M801") for line in lines):
        raise AssertionError("raw calibration must not use a private trigger")
    if any(line.startswith("G1") for line in lines):
        raise AssertionError("raw point pass must not draw connecting lines")

    pattern = re.compile(
        r"^G0 X(-?\d+(?:\.\d+)?) Y(-?\d+(?:\.\d+)?) ; P(\d+)$"
    )
    moves: list[tuple[float, float]] = []
    point_numbers: list[int] = []
    for line in lines:
        match = pattern.match(line)
        if match is None:
            continue
        moves.append((float(match.group(1)), float(match.group(2))))
        point_numbers.append(int(match.group(3)))
    if tuple(moves) != EXECUTION_ORDER:
        raise AssertionError(f"unexpected execution order: {moves}")
    if sorted(point_numbers) != list(range(1, 17)):
        raise AssertionError("point labels must contain P1 through P16")
    if set(moves) != set(ROW_MAJOR):
        raise AssertionError("4x4 point set mismatch")

    paper_calibration, command_calibration, _ = calibration_arrays()
    paper_to_user = fit(paper_calibration, command_calibration, 2)
    commands = evaluate(np.array(moves, dtype=float), paper_to_user, 2)
    endpoint_worst = (
        float("inf"), (0.0, 0.0), (0.0, 0.0, 0.0)
    )
    for point in commands:
        joint_margin, angles = margin(tuple(point))
        if joint_margin < endpoint_worst[0]:
            endpoint_worst = (joint_margin, tuple(point), angles)
    if endpoint_worst[0] < MIN_REQUIRED_MARGIN_DEG:
        raise AssertionError(
            f"grid endpoint margin {endpoint_worst[0]:.6f} deg below "
            f"{MIN_REQUIRED_MARGIN_DEG:.1f} deg"
        )

    path_worst = (float("inf"), (0.0, 0.0))
    rapid_outer_segments_max = 0
    path = np.vstack((np.array(HOME_USER), commands))
    for start_array, end_array in zip(path, path[1:]):
        start = tuple(float(value) for value in start_array)
        end = tuple(float(value) for value in end_array)
        span = max(
            abs(end[0] - start[0]), abs(end[1] - start[1])
        )
        outer_count = max(1, math.ceil(span / 20.0))
        rapid_outer_segments_max = max(
            rapid_outer_segments_max, outer_count
        )
        previous = start
        for index in range(1, outer_count + 1):
            ratio = index / outer_count
            current = (
                start[0] + (end[0] - start[0]) * ratio,
                start[1] + (end[1] - start[1]) * ratio,
            )
            inner_count = math.ceil(
                max(
                    abs(current[0] - previous[0]),
                    abs(current[1] - previous[1]),
                )
            )
            if inner_count > PLAN_MAX_SEGMENTS:
                raise AssertionError(
                    f"inner planner needs {inner_count} segments"
                )
            previous = current
        for point in samples(start, end):
            joint_margin, _ = margin(point)
            if joint_margin < path_worst[0]:
                path_worst = (joint_margin, point)
            if joint_margin < -0.001:
                raise AssertionError(
                    f"rapid path violates joint bounds at {point}"
                )

    if "290.945962f" not in map_source:
        raise AssertionError("paper baseline coefficient mismatch")
    if "84.802037f" not in map_source:
        raise AssertionError("paper baseline coefficient mismatch")

    xs = commands[:, 0]
    ys = commands[:, 1]
    print(
        "paper_a4_4x4_raw_dot_gcode_v21=PASS "
        f"points={len(moves)} gcode_lines={len(lines)} "
        f"user_bounds_x={xs.min():.3f}..{xs.max():.3f} "
        f"user_bounds_y={ys.min():.3f}..{ys.max():.3f}"
    )
    print(
        f"endpoint_min_joint_margin={endpoint_worst[0]:.6f}deg "
        f"at=({endpoint_worst[1][0]:.3f},"
        f"{endpoint_worst[1][1]:.3f}) "
        f"theta={endpoint_worst[2][0]:.3f} "
        f"psi={endpoint_worst[2][1]:.3f} "
        f"beta={endpoint_worst[2][2]:.3f}"
    )
    print(
        f"rapid_path_min_joint_margin={path_worst[0]:.9f}deg "
        f"rapid_outer_segments_max={rapid_outer_segments_max} "
        "grid_correction=OFF paper_bounds_x=25..185 "
        "paper_bounds_y=20..130"
    )


if __name__ == "__main__":
    main()
