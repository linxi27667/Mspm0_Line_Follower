"""Check the V29 tangent-approach trajectory and touchdown controls."""

from __future__ import annotations

import math
from pathlib import Path

from check_fixed_layout_3rect_x95_y20_130_waypoint_v17 import (
    HOME_USER,
    PLAN_MAX_SEGMENTS,
    inverse,
    margin,
    samples,
)
from check_paper_a4_3pos_8dir_v28 import (
    DRAW_PAPER_SEGMENT_MM,
    FIRMWARE_ID,
    LENGTH_TOLERANCE_MM,
    LINE_LENGTH_MM,
    MAP_HEADER,
    MIN_ENDPOINT_JOINT_MARGIN_DEG,
    PAPER_MAP_ID,
    PAPER_X_MAX,
    PAPER_X_MIN,
    PAPER_Y_MAX,
    PAPER_Y_MIN,
    PATTERN,
    PIN_CONFIG,
    PREAMBLE,
    REGION_CENTERS,
    SELECTOR,
    close_point,
    parse_motion,
)
from check_paper_a4_center_yong_v26 import paper_to_user
from derive_grid9_limited_y_v15 import calibration_arrays, fit
from derive_paper_a4_4x7_grid_v25 import derive


ROOT = Path(__file__).resolve().parents[1]
GCODE = (
    ROOT
    / "gcode"
    / "PAPER_A4_3POS_8DIR_20MM_TANGENT_APPROACH_GCODE_V29.gcode"
)
GCODE_HEADER = ROOT / "TASK" / "gcode_serial.h"
APPROACH_MM = 6.0
INITIAL_DIRECTION_SAMPLE_MM = 1.0
DIRECTION_EPSILON_DEG = 0.000001
CONTROL_DOTS = (
    ("LOWER", (165.0, 56.667)),
    ("MIDDLE", (165.0, 130.0)),
    ("UPPER", (165.0, 203.667)),
)


def check_leg(
    start: tuple[float, float],
    end: tuple[float, float],
    worst: tuple[float, tuple[float, float]],
) -> tuple[float, tuple[float, float]]:
    for point in samples(start, end):
        joint_margin, _ = margin(point)
        if joint_margin < worst[0]:
            worst = (joint_margin, point)
        if joint_margin < -0.001:
            raise AssertionError(
                f"mapped path violates joint bounds at {point}"
            )
    return worst


def main() -> None:
    raw_lines = GCODE.read_text(encoding="ascii").splitlines()
    if any(not line.strip() for line in raw_lines):
        raise AssertionError("blank G-code lines are not allowed")
    if any(";" in line for line in raw_lines):
        raise AssertionError("V29 G-code must remain comment-free")
    lines = tuple(line.strip() for line in raw_lines)
    if lines[: len(PREAMBLE)] != PREAMBLE:
        raise AssertionError("standard setup preamble changed")

    expected_count = (
        len(PREAMBLE)
        + len(REGION_CENTERS) * len(PATTERN) * 5
        + len(CONTROL_DOTS) * 4
    )
    if len(lines) != expected_count:
        raise AssertionError("unexpected V29 command count")

    selector = SELECTOR.read_text(encoding="utf-8")
    gcode_header = GCODE_HEADER.read_text(encoding="utf-8")
    map_header = MAP_HEADER.read_text(encoding="utf-8")
    pin_config = PIN_CONFIG.read_text(encoding="utf-8")
    if (
        "#define WRITER_TEST_MODE             "
        "WRITER_TEST_MODE_GCODE_SERIAL"
    ) not in selector:
        raise AssertionError("standard G-code mode is not selected")
    if FIRMWARE_ID not in gcode_header:
        raise AssertionError("unexpected active firmware ID")
    if PAPER_MAP_ID not in map_header:
        raise AssertionError("unexpected active paper-map ID")
    if "APP_WRITER_PAPER_GRID_CORRECTION_ENABLE (1u)" not in map_header:
        raise AssertionError("4x7 paper correction is not enabled")
    if pin_config.count("DL_GPIO_RESISTOR_PULL_UP") != 2:
        raise AssertionError("both limit inputs must retain pull-ups")

    paper_calibration, command_calibration, _ = calibration_arrays()
    coefficients = fit(paper_calibration, command_calibration, 2)
    _, _, total_delta, _ = derive()

    body = lines[len(PREAMBLE) :]
    line_command_count = len(REGION_CENTERS) * len(PATTERN) * 5
    line_body = body[:line_command_count]
    control_body = body[line_command_count:]
    strokes: list[
        tuple[
            str,
            str,
            tuple[float, float],
            tuple[float, float],
            tuple[float, float],
        ]
    ] = []
    motion_commands: list[tuple[int, tuple[float, float]]] = []
    direction_checks = 0

    for stroke_index in range(len(REGION_CENTERS) * len(PATTERN)):
        chunk = line_body[stroke_index * 5 : stroke_index * 5 + 5]
        approach = parse_motion(chunk[0], 0)
        start = parse_motion(chunk[1], 0)
        if chunk[2] != "M3":
            raise AssertionError(f"stroke {stroke_index + 1}: missing M3")
        end = parse_motion(chunk[3], 1)
        if chunk[4] != "M5":
            raise AssertionError(f"stroke {stroke_index + 1}: missing M5")

        region_index, direction_index = divmod(stroke_index, len(PATTERN))
        region_name, center = REGION_CENTERS[region_index]
        direction_name, local_start, local_end = PATTERN[direction_index]
        expected_start = (
            center[0] + local_start[0],
            center[1] + local_start[1],
        )
        expected_end = (
            center[0] + local_end[0],
            center[1] + local_end[1],
        )
        if not close_point(start, expected_start):
            raise AssertionError(
                f"{region_name}/{direction_name} start mismatch"
            )
        if not close_point(end, expected_end):
            raise AssertionError(
                f"{region_name}/{direction_name} end mismatch"
            )

        length = math.dist(start, end)
        if not math.isclose(
            length,
            LINE_LENGTH_MM,
            abs_tol=LENGTH_TOLERANCE_MM,
        ):
            raise AssertionError(
                f"{region_name}/{direction_name} is not 20 mm"
            )
        unit = (
            (end[0] - start[0]) / length,
            (end[1] - start[1]) / length,
        )
        expected_approach = (
            start[0] - unit[0] * APPROACH_MM,
            start[1] - unit[1] * APPROACH_MM,
        )
        if not close_point(approach, expected_approach):
            raise AssertionError(
                f"{region_name}/{direction_name} approach mismatch: "
                f"{approach} != {expected_approach}"
            )

        initial_draw_point = (
            start[0] + unit[0] * INITIAL_DIRECTION_SAMPLE_MM,
            start[1] + unit[1] * INITIAL_DIRECTION_SAMPLE_MM,
        )
        approach_angles = inverse(
            *paper_to_user(approach, coefficients, total_delta)
        )[:2]
        start_angles = inverse(
            *paper_to_user(start, coefficients, total_delta)
        )[:2]
        initial_angles = inverse(
            *paper_to_user(initial_draw_point, coefficients, total_delta)
        )[:2]
        for joint_index, (
            approach_angle,
            start_angle,
            initial_angle,
        ) in enumerate(
            zip(approach_angles, start_angles, initial_angles),
            start=1,
        ):
            approach_delta = start_angle - approach_angle
            draw_delta = initial_angle - start_angle
            if (
                abs(approach_delta) <= DIRECTION_EPSILON_DEG
                or abs(draw_delta) <= DIRECTION_EPSILON_DEG
                or approach_delta * draw_delta <= 0.0
            ):
                raise AssertionError(
                    f"{region_name}/{direction_name} joint {joint_index} "
                    "reverses at touchdown"
                )
            direction_checks += 1

        for point in (approach, start, end):
            if not (
                PAPER_X_MIN <= point[0] <= PAPER_X_MAX
                and PAPER_Y_MIN <= point[1] <= PAPER_Y_MAX
            ):
                raise AssertionError(
                    f"{region_name}/{direction_name} out of bounds: {point}"
                )
        strokes.append(
            (region_name, direction_name, approach, start, end)
        )
        motion_commands.extend(((0, approach), (0, start), (1, end)))

    for dot_index, (name, expected_dot) in enumerate(CONTROL_DOTS):
        chunk = control_body[dot_index * 4 : dot_index * 4 + 4]
        dot = parse_motion(chunk[0], 0)
        if not close_point(dot, expected_dot):
            raise AssertionError(f"{name} touchdown-control mismatch")
        if chunk[1:] != ("M3", "G4 P0.3", "M5"):
            raise AssertionError(f"{name} touchdown-control sequence changed")
        if not (
            PAPER_X_MIN <= dot[0] <= PAPER_X_MAX
            and PAPER_Y_MIN <= dot[1] <= PAPER_Y_MAX
        ):
            raise AssertionError(f"{name} touchdown control out of bounds")
        motion_commands.append((0, dot))

    user_position = HOME_USER
    paper_position: tuple[float, float] | None = None
    path_worst = (float("inf"), HOME_USER)
    endpoint_worst = (float("inf"), (0.0, 0.0))
    rapid_outer_segments_max = 0
    draw_paper_segments_max = 0

    for motion, paper_target in motion_commands:
        mapped_target = paper_to_user(
            paper_target, coefficients, total_delta
        )
        endpoint_margin, _ = margin(mapped_target)
        if endpoint_margin < endpoint_worst[0]:
            endpoint_worst = (endpoint_margin, paper_target)

        if motion == 0:
            span = max(
                abs(mapped_target[0] - user_position[0]),
                abs(mapped_target[1] - user_position[1]),
            )
            outer_segments = max(1, math.ceil(span / 20.0))
            rapid_outer_segments_max = max(
                rapid_outer_segments_max, outer_segments
            )
            if outer_segments > PLAN_MAX_SEGMENTS:
                raise AssertionError(
                    "rapid segmentation exceeds planner capacity"
                )
            path_worst = check_leg(
                user_position, mapped_target, path_worst
            )
        else:
            if paper_position is None:
                raise AssertionError("G1 has no paper-space start")
            source_span = max(
                abs(paper_target[0] - paper_position[0]),
                abs(paper_target[1] - paper_position[1]),
            )
            draw_segments = max(
                1, math.ceil(source_span / DRAW_PAPER_SEGMENT_MM)
            )
            draw_paper_segments_max = max(
                draw_paper_segments_max, draw_segments
            )
            previous_user = user_position
            for segment_index in range(1, draw_segments + 1):
                ratio = segment_index / draw_segments
                paper_point = (
                    paper_position[0]
                    + (paper_target[0] - paper_position[0]) * ratio,
                    paper_position[1]
                    + (paper_target[1] - paper_position[1]) * ratio,
                )
                mapped_point = paper_to_user(
                    paper_point, coefficients, total_delta
                )
                path_worst = check_leg(
                    previous_user, mapped_point, path_worst
                )
                previous_user = mapped_point
        user_position = mapped_target
        paper_position = paper_target

    if endpoint_worst[0] < MIN_ENDPOINT_JOINT_MARGIN_DEG:
        raise AssertionError(
            f"endpoint joint margin {endpoint_worst[0]:.6f} deg below "
            f"{MIN_ENDPOINT_JOINT_MARGIN_DEG:.1f} deg"
        )

    all_points = [
        point
        for _, _, approach, start, end in strokes
        for point in (approach, start, end)
    ] + [point for _, point in CONTROL_DOTS]
    print(
        "paper_a4_3pos_8dir_tangent_v29=PASS "
        f"regions={len(REGION_CENTERS)} strokes={len(strokes)} "
        f"touchdown_controls={len(CONTROL_DOTS)} "
        f"approach_mm={APPROACH_MM:.1f} "
        f"joint_direction_checks={direction_checks} "
        f"paper_x={min(point[0] for point in all_points):.3f}.."
        f"{max(point[0] for point in all_points):.3f} "
        f"paper_y={min(point[1] for point in all_points):.3f}.."
        f"{max(point[1] for point in all_points):.3f}"
    )
    print(
        f"endpoint_min_joint_margin={endpoint_worst[0]:.6f}deg "
        f"at_paper=({endpoint_worst[1][0]:.3f},"
        f"{endpoint_worst[1][1]:.3f}) "
        f"path_min_joint_margin={path_worst[0]:.6f}deg "
        f"rapid_outer_segments_max={rapid_outer_segments_max} "
        f"draw_paper_segments_max={draw_paper_segments_max} "
        f"firmware={FIRMWARE_ID} paper_map={PAPER_MAP_ID} grid4x7=ON"
    )


if __name__ == "__main__":
    main()
