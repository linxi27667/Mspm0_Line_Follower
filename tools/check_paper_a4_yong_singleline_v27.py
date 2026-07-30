"""Check the redesigned standard-G-code 18 mm Yong character."""

from __future__ import annotations

import math
from pathlib import Path

from check_fixed_layout_3rect_x95_y20_130_waypoint_v17 import (
    HOME_USER,
    PLAN_MAX_SEGMENTS,
    margin,
    samples,
)
from check_paper_a4_center_yong_v26 import (
    MOTION_PATTERN,
    PAPER_X_MAX,
    PAPER_X_MIN,
    PAPER_Y_MAX,
    PAPER_Y_MIN,
    paper_to_user,
)
from derive_grid9_limited_y_v15 import (
    calibration_arrays,
    fit,
)
from derive_paper_a4_4x7_grid_v25 import derive


ROOT = Path(__file__).resolve().parents[1]
GCODE = (
    ROOT
    / "gcode"
    / "PAPER_A4_YONG_SINGLELINE_18MM_STANDARD_GCODE_V27.gcode"
)


def main() -> None:
    raw_lines = GCODE.read_text(encoding="ascii").splitlines()
    if any(not line.strip() for line in raw_lines):
        raise AssertionError("blank G-code lines are not allowed")
    if any(line.lstrip().startswith(";") for line in raw_lines):
        raise AssertionError("comment-only G-code lines are not allowed")
    lines = [line.strip() for line in raw_lines]
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
    glyph_points = []
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
        if not (motion == 0 and paper == (160.0, 115.0)):
            glyph_points.append(paper)
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
    if (stroke_count, rapid_count, draw_count) != (5, 6, 36):
        raise AssertionError(
            "expected 5 strokes, 6 rapid moves, and 36 drawing moves"
        )
    if rapid_outer_segments_max > PLAN_MAX_SEGMENTS:
        raise AssertionError("rapid segmentation exceeds planner capacity")

    xs = [point[0] for point in glyph_points]
    ys = [point[1] for point in glyph_points]
    print(
        "paper_a4_yong_singleline_v27=PASS "
        f"strokes={stroke_count} G0={rapid_count} G1={draw_count} "
        f"glyph_bounds_x={min(xs):.3f}..{max(xs):.3f} "
        f"glyph_bounds_y={min(ys):.3f}..{max(ys):.3f} "
        f"path_min_joint_margin={path_worst[0]:.6f}deg "
        f"rapid_outer_segments_max={rapid_outer_segments_max}"
    )


if __name__ == "__main__":
    main()
