"""Check the V28 three-position, eight-direction standard G-code."""

from __future__ import annotations

import math
import re
from pathlib import Path

from check_fixed_layout_3rect_x95_y20_130_waypoint_v17 import (
    HOME_USER,
    PLAN_MAX_SEGMENTS,
    margin,
    samples,
)
from check_paper_a4_center_yong_v26 import paper_to_user
from derive_grid9_limited_y_v15 import calibration_arrays, fit
from derive_paper_a4_4x7_grid_v25 import derive


ROOT = Path(__file__).resolve().parents[1]
GCODE = (
    ROOT
    / "gcode"
    / "PAPER_A4_3POS_8DIR_20MM_STANDARD_GCODE_V28.gcode"
)
SELECTOR = ROOT / "TASK" / "writer_test.h"
GCODE_HEADER = ROOT / "TASK" / "gcode_serial.h"
MAP_HEADER = ROOT / "APP" / "Inc" / "app_writer_paper_map.h"
PIN_CONFIG = ROOT / "ti_msp_dl_config.c"

FIRMWARE_ID = "PAPER_A4_4X7_GRIDCAL_VERIFY_GCODE_V25"
PAPER_MAP_ID = "A4_BASE_QUADRATIC_GRID4X7_CAL_V5"
PAPER_X_MIN = 25.0
PAPER_X_MAX = 185.0
PAPER_Y_MIN = 20.0
PAPER_Y_MAX = 240.333333
LINE_LENGTH_MM = 20.0
DRAW_PAPER_SEGMENT_MM = 2.0
COORDINATE_TOLERANCE_MM = 0.000002
LENGTH_TOLERANCE_MM = 0.000002
MIN_ENDPOINT_JOINT_MARGIN_DEG = 8.0
PREAMBLE = ("G21", "G90", "G94", "M5", "F180")
MOTION_PATTERN = re.compile(
    r"^G([01])\s+X(-?\d+(?:\.\d+)?)\s+Y(-?\d+(?:\.\d+)?)$"
)

REGION_CENTERS = (
    ("LOWER", (105.0, 56.667)),
    ("MIDDLE", (105.0, 130.0)),
    ("UPPER", (105.0, 203.667)),
)

# Each item is (name, start offset, end offset). The row order is deliberately
# identical in all three regions so a rectified photo can compare like-for-like
# paths without first classifying Chinese-character strokes.
SQRT_50 = 7.071068
PATTERN = (
    ("H_POS_X", (-35.0, 24.0), (-15.0, 24.0)),
    ("H_NEG_X", (35.0, 24.0), (15.0, 24.0)),
    ("V_POS_Y", (-25.0, -2.0), (-25.0, 18.0)),
    ("V_NEG_Y", (25.0, 18.0), (25.0, -2.0)),
    (
        "SLASH_POS_X_POS_Y",
        (-25.0 - SQRT_50, -8.0 - SQRT_50),
        (-25.0 + SQRT_50, -8.0 + SQRT_50),
    ),
    (
        "SLASH_NEG_X_NEG_Y",
        (25.0 + SQRT_50, -8.0 + SQRT_50),
        (25.0 - SQRT_50, -8.0 - SQRT_50),
    ),
    (
        "BACKSLASH_POS_X_NEG_Y",
        (-25.0 - SQRT_50, -24.0 + SQRT_50),
        (-25.0 + SQRT_50, -24.0 - SQRT_50),
    ),
    (
        "BACKSLASH_NEG_X_POS_Y",
        (25.0 + SQRT_50, -24.0 - SQRT_50),
        (25.0 - SQRT_50, -24.0 + SQRT_50),
    ),
)


def close_point(
    actual: tuple[float, float],
    expected: tuple[float, float],
) -> bool:
    return (
        abs(actual[0] - expected[0]) <= COORDINATE_TOLERANCE_MM
        and abs(actual[1] - expected[1]) <= COORDINATE_TOLERANCE_MM
    )


def parse_motion(command: str, expected_code: int) -> tuple[float, float]:
    match = MOTION_PATTERN.fullmatch(command)
    if match is None or int(match.group(1)) != expected_code:
        raise AssertionError(
            f"expected G{expected_code} X... Y..., got: {command}"
        )
    return float(match.group(2)), float(match.group(3))


def check_mapped_leg(
    start: tuple[float, float],
    end: tuple[float, float],
    path_worst: tuple[float, tuple[float, float]],
) -> tuple[float, tuple[float, float]]:
    for point in samples(start, end):
        joint_margin, _ = margin(point)
        if joint_margin < path_worst[0]:
            path_worst = (joint_margin, point)
        if joint_margin < -0.001:
            raise AssertionError(
                f"mapped path violates joint bounds at {point}"
            )
    return path_worst


def main() -> None:
    raw_lines = GCODE.read_text(encoding="ascii").splitlines()
    if any(not line.strip() for line in raw_lines):
        raise AssertionError("blank G-code lines are not allowed")
    if any(";" in line for line in raw_lines):
        raise AssertionError("V28 G-code must remain comment-free")
    lines = tuple(line.strip() for line in raw_lines)
    if lines[: len(PREAMBLE)] != PREAMBLE:
        raise AssertionError("standard setup preamble changed")
    if len(lines) != len(PREAMBLE) + len(REGION_CENTERS) * len(PATTERN) * 4:
        raise AssertionError("unexpected V28 command count")

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
    if any(command.startswith("M8") for command in lines):
        raise AssertionError("legacy gated commands are forbidden")

    body = lines[len(PREAMBLE) :]
    strokes: list[
        tuple[str, str, tuple[float, float], tuple[float, float]]
    ] = []
    for stroke_index in range(len(REGION_CENTERS) * len(PATTERN)):
        chunk = body[stroke_index * 4 : stroke_index * 4 + 4]
        start = parse_motion(chunk[0], 0)
        if chunk[1] != "M3":
            raise AssertionError(f"stroke {stroke_index + 1}: missing M3")
        end = parse_motion(chunk[2], 1)
        if chunk[3] != "M5":
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
                f"{region_name}/{direction_name} start mismatch: "
                f"{start} != {expected_start}"
            )
        if not close_point(end, expected_end):
            raise AssertionError(
                f"{region_name}/{direction_name} end mismatch: "
                f"{end} != {expected_end}"
            )
        if not math.isclose(
            math.dist(start, end),
            LINE_LENGTH_MM,
            abs_tol=LENGTH_TOLERANCE_MM,
        ):
            raise AssertionError(
                f"{region_name}/{direction_name} is not 20 mm"
            )
        for point in (start, end):
            if not (
                PAPER_X_MIN <= point[0] <= PAPER_X_MAX
                and PAPER_Y_MIN <= point[1] <= PAPER_Y_MAX
            ):
                raise AssertionError(
                    f"{region_name}/{direction_name} out of bounds: {point}"
                )
        strokes.append((region_name, direction_name, start, end))

    # Explicitly prove that the lower, middle, and upper groups are congruent.
    reference = strokes[: len(PATTERN)]
    for region_index, (_, center) in enumerate(REGION_CENTERS):
        group = strokes[
            region_index * len(PATTERN) : (region_index + 1) * len(PATTERN)
        ]
        for ref_stroke, stroke in zip(reference, group):
            _, ref_name, ref_start, ref_end = ref_stroke
            _, name, start, end = stroke
            reference_center = REGION_CENTERS[0][1]
            normalized_reference = (
                (
                    ref_start[0] - reference_center[0],
                    ref_start[1] - reference_center[1],
                ),
                (
                    ref_end[0] - reference_center[0],
                    ref_end[1] - reference_center[1],
                ),
            )
            normalized_actual = (
                (start[0] - center[0], start[1] - center[1]),
                (end[0] - center[0], end[1] - center[1]),
            )
            if name != ref_name or not all(
                close_point(actual, expected)
                for actual, expected in zip(
                    normalized_actual, normalized_reference
                )
            ):
                raise AssertionError(
                    f"region {REGION_CENTERS[region_index][0]} "
                    f"is not congruent at {name}"
                )

    paper_calibration, command_calibration, _ = calibration_arrays()
    coefficients = fit(paper_calibration, command_calibration, 2)
    _, _, total_delta, _ = derive()
    user_position = HOME_USER
    path_worst = (float("inf"), HOME_USER)
    endpoint_worst = (float("inf"), (0.0, 0.0), (0.0, 0.0))
    rapid_outer_segments_max = 0
    draw_paper_segments_max = 0

    for _, _, start, end in strokes:
        mapped_start = paper_to_user(start, coefficients, total_delta)
        for paper_point, mapped_point in (
            (start, mapped_start),
            (end, paper_to_user(end, coefficients, total_delta)),
        ):
            endpoint_margin, _ = margin(mapped_point)
            if endpoint_margin < endpoint_worst[0]:
                endpoint_worst = (
                    endpoint_margin,
                    paper_point,
                    mapped_point,
                )
        rapid_span = max(
            abs(mapped_start[0] - user_position[0]),
            abs(mapped_start[1] - user_position[1]),
        )
        rapid_outer_segments = max(1, math.ceil(rapid_span / 20.0))
        rapid_outer_segments_max = max(
            rapid_outer_segments_max, rapid_outer_segments
        )
        if rapid_outer_segments > PLAN_MAX_SEGMENTS:
            raise AssertionError("rapid segmentation exceeds planner capacity")
        path_worst = check_mapped_leg(
            user_position, mapped_start, path_worst
        )

        source_span = max(
            abs(end[0] - start[0]),
            abs(end[1] - start[1]),
        )
        draw_segments = max(
            1, math.ceil(source_span / DRAW_PAPER_SEGMENT_MM)
        )
        draw_paper_segments_max = max(draw_paper_segments_max, draw_segments)
        previous_user = mapped_start
        for segment_index in range(1, draw_segments + 1):
            ratio = segment_index / draw_segments
            paper_point = (
                start[0] + (end[0] - start[0]) * ratio,
                start[1] + (end[1] - start[1]) * ratio,
            )
            mapped_point = paper_to_user(
                paper_point, coefficients, total_delta
            )
            path_worst = check_mapped_leg(
                previous_user, mapped_point, path_worst
            )
            previous_user = mapped_point
        user_position = previous_user

    if endpoint_worst[0] < MIN_ENDPOINT_JOINT_MARGIN_DEG:
        raise AssertionError(
            f"endpoint joint margin {endpoint_worst[0]:.6f} deg below "
            f"{MIN_ENDPOINT_JOINT_MARGIN_DEG:.1f} deg"
        )

    all_points = [
        point for _, _, start, end in strokes for point in (start, end)
    ]
    print(
        "paper_a4_3pos_8dir_v28=PASS "
        f"regions={len(REGION_CENTERS)} strokes={len(strokes)} "
        f"G0={len(strokes)} G1={len(strokes)} length_mm=20.000 F=180 "
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
