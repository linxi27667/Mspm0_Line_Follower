"""Check the standard-G-code 18 mm Yong character test."""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np

from check_fixed_layout_3rect_x95_y20_130_waypoint_v17 import (
    HOME_USER,
    PLAN_MAX_SEGMENTS,
    margin,
    samples,
)
from derive_grid9_limited_y_v15 import (
    calibration_arrays,
    evaluate,
    fit,
)
from derive_paper_a4_4x7_grid_v24 import GRID_X, GRID_Y
from derive_paper_a4_4x7_grid_v25 import derive


ROOT = Path(__file__).resolve().parents[1]
GCODE = (
    ROOT
    / "gcode"
    / "PAPER_A4_CENTER_YONG_18MM_STANDARD_GCODE_V26.gcode"
)
PAPER_X_MIN = 25.0
PAPER_X_MAX = 185.0
PAPER_Y_MIN = 20.0
PAPER_Y_MAX = 240.333
MOTION_PATTERN = re.compile(
    r"^G([01])\s+X(-?\d+(?:\.\d+)?)\s+Y(-?\d+(?:\.\d+)?)$"
)


def paper_to_user(
    paper: tuple[float, float],
    coefficients: np.ndarray,
    total_delta: np.ndarray,
) -> tuple[float, float]:
    point = np.array((paper,), dtype=float)
    base = evaluate(point, coefficients, 2)[0]
    column = min(
        max(int(np.searchsorted(GRID_X, paper[0], side="right")) - 1, 0),
        len(GRID_X) - 2,
    )
    row = min(
        max(int(np.searchsorted(GRID_Y, paper[1], side="right")) - 1, 0),
        len(GRID_Y) - 2,
    )
    tx = (
        (paper[0] - GRID_X[column])
        / (GRID_X[column + 1] - GRID_X[column])
    )
    ty = (
        (paper[1] - GRID_Y[row])
        / (GRID_Y[row + 1] - GRID_Y[row])
    )
    lower = (
        total_delta[row, column]
        + (total_delta[row, column + 1] - total_delta[row, column]) * tx
    )
    upper = (
        total_delta[row + 1, column]
        + (
            total_delta[row + 1, column + 1]
            - total_delta[row + 1, column]
        ) * tx
    )
    corrected = base + lower + (upper - lower) * ty
    return float(corrected[0]), float(corrected[1])


def main() -> None:
    lines = []
    for raw_line in GCODE.read_text(encoding="utf-8").splitlines():
        command = raw_line.split(";", 1)[0].strip()
        if command:
            lines.append(command)

    if lines[:5] != ["G21", "G90", "G94", "M5", "F180"]:
        raise AssertionError("standard setup preamble changed")

    paper_calibration, command_calibration, _ = calibration_arrays()
    coefficients = fit(paper_calibration, command_calibration, 2)
    _, _, total_delta, _ = derive()

    position = None
    user_position = HOME_USER
    pen_down = False
    stroke_count = 0
    rapid_count = 0
    draw_count = 0
    paper_points = []
    path_worst = (float("inf"), (0.0, 0.0))
    rapid_outer_segments_max = 0

    for command in lines:
        if command in ("G21", "G90", "G94", "F180"):
            continue
        if command == "M3":
            if pen_down or position is None:
                raise AssertionError("invalid M3 placement")
            pen_down = True
            stroke_count += 1
            continue
        if command == "M5":
            pen_down = False
            continue

        match = MOTION_PATTERN.fullmatch(command)
        if match is None:
            raise AssertionError(f"unsupported command: {command}")
        motion = int(match.group(1))
        paper = (float(match.group(2)), float(match.group(3)))
        if not (
            PAPER_X_MIN <= paper[0] <= PAPER_X_MAX
            and PAPER_Y_MIN <= paper[1] <= PAPER_Y_MAX
        ):
            raise AssertionError(f"paper point out of bounds: {paper}")
        if motion == 0 and pen_down:
            raise AssertionError("G0 attempted with pen down")
        if motion == 1 and not pen_down:
            raise AssertionError("G1 attempted with pen up")

        user = paper_to_user(paper, coefficients, total_delta)
        paper_points.append(paper)
        if motion == 0:
            rapid_count += 1
            span = max(
                abs(user[0] - user_position[0]),
                abs(user[1] - user_position[1]),
            )
            rapid_outer_segments_max = max(
                rapid_outer_segments_max,
                max(1, math.ceil(span / 20.0)),
            )
        else:
            draw_count += 1

        for sample in samples(user_position, user):
            joint_margin, _ = margin(sample)
            if joint_margin < path_worst[0]:
                path_worst = (joint_margin, sample)
            if joint_margin < -0.001:
                raise AssertionError(
                    f"mapped path violates joint bounds at {sample}"
                )
        user_position = user
        position = paper

    if pen_down:
        raise AssertionError("file ends with pen down")
    if (stroke_count, rapid_count, draw_count) != (5, 6, 32):
        raise AssertionError(
            "expected 5 strokes, 6 rapid moves, and 32 drawing moves"
        )
    if rapid_outer_segments_max > PLAN_MAX_SEGMENTS:
        raise AssertionError("rapid segmentation exceeds planner capacity")

    xs = [point[0] for point in paper_points[:-1]]
    ys = [point[1] for point in paper_points[:-1]]
    print(
        "paper_a4_center_yong_v26=PASS "
        f"strokes={stroke_count} G0={rapid_count} G1={draw_count} "
        f"glyph_bounds_x={min(xs):.3f}..{max(xs):.3f} "
        f"glyph_bounds_y={min(ys):.3f}..{max(ys):.3f} "
        f"path_min_joint_margin={path_worst[0]:.6f}deg "
        f"rapid_outer_segments_max={rapid_outer_segments_max}"
    )


if __name__ == "__main__":
    main()
