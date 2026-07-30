"""Offline contract, table, path, and kinematic checks for calibrated V24."""

from __future__ import annotations

import math
from pathlib import Path

from check_fixed_layout_3rect_x95_y20_130_waypoint_v17 import (
    HOME_USER,
    PLAN_MAX_SEGMENTS,
    margin,
    samples,
)
from derive_paper_a4_4x7_grid_v24 import derive


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

MIN_CALIBRATED_ENDPOINT_MARGIN_DEG = 8.0
EXECUTION_INDICES = (
    0, 1, 2, 3, 7, 6, 5, 4,
    8, 9, 10, 11, 15, 14, 13, 12,
    16, 17, 18, 19, 23, 22, 21, 20,
    24, 25, 26, 27,
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
        "PAPER_A4_4X7_GRIDCAL_VERIFY_GCODE_V24",
        "A4_BASE_QUADRATIC_GRID4X7_CAL_V4",
        "APP_WRITER_PAPER_GRID_CORRECTION_ENABLE (1u)",
        "APP_WRITER_PAPER_GRID_COLS             (4u)",
        "APP_WRITER_PAPER_GRID_ROWS             (7u)",
        "grid4x7=%u",
        "WriterPaperMap_To_User",
        "paper_coordinate_out_of_bounds",
        "runtime_limit_active",
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
    if "M801" in gcode:
        raise AssertionError("verification must reuse standard G-code")
    if gcode.count("G0 X") != 28 or gcode.count("G4 P0.3") != 28:
        raise AssertionError("verification G-code is not the V23 28-dot file")

    _, corrected_user, user_delta = derive()
    for axis in range(2):
        for row in user_delta[:, :, axis]:
            for value in row:
                token = f"{float(value):.6f}f"
                if token not in map_source:
                    raise AssertionError(
                        f"correction token missing: {token}"
                    )

    commands = corrected_user.reshape(-1, 2)
    endpoint_worst = (
        float("inf"), (0.0, 0.0), (0.0, 0.0, 0.0)
    )
    for point in commands:
        joint_margin, angles = margin(tuple(point))
        if joint_margin < endpoint_worst[0]:
            endpoint_worst = (joint_margin, tuple(point), angles)
    if endpoint_worst[0] < MIN_CALIBRATED_ENDPOINT_MARGIN_DEG:
        raise AssertionError(
            f"endpoint margin {endpoint_worst[0]:.6f} deg below "
            f"{MIN_CALIBRATED_ENDPOINT_MARGIN_DEG:.1f} deg"
        )

    ordered = [tuple(commands[index]) for index in EXECUTION_INDICES]
    path = [HOME_USER] + ordered
    path_worst = (float("inf"), (0.0, 0.0))
    rapid_outer_segments_max = 0
    for start, end in zip(path, path[1:]):
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
            inner_count = math.ceil(max(
                abs(current[0] - previous[0]),
                abs(current[1] - previous[1]),
            ))
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

    dx = user_delta[:, :, 0]
    dy = user_delta[:, :, 1]
    print(
        "paper_a4_4x7_gridcal_verify_v24=PASS "
        f"nodes={len(commands)} "
        f"user_dx={dx.min():.3f}..{dx.max():.3f} "
        f"user_dy={dy.min():.3f}..{dy.max():.3f}"
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
        "grid4x7=ON reused_gcode=V23"
    )


if __name__ == "__main__":
    main()
