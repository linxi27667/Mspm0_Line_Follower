"""Check the V35 six-zone paired circle test."""

from __future__ import annotations

import hashlib
import json
import math

from check_fixed_layout_3rect_x95_y20_130_waypoint_v17 import (
    HOME_USER,
    PLAN_MAX_SEGMENTS,
    inverse,
    margin,
)
from check_paper_a4_3pos_8dir_v28 import (
    FIRMWARE_ID,
    MAP_HEADER,
    MIN_ENDPOINT_JOINT_MARGIN_DEG,
    PAPER_MAP_ID,
    PIN_CONFIG,
    SELECTOR,
)
from check_paper_a4_center_yong_v26 import paper_to_user
from check_paper_a4_font_vs_program_isolation_v34 import check_leg
from derive_grid9_limited_y_v15 import calibration_arrays, fit
from derive_paper_a4_4x7_grid_v25 import derive
import generate_paper_a4_6zone_circle_pairs_v35 as variant


ROOT = variant.GCODE_PATH.parents[1]
GCODE_HEADER = ROOT / "TASK" / "gcode_serial.h"
DRAW_PAPER_SEGMENT_MM = 2.0
RAPID_USER_SEGMENT_MM = 20.0
DIRECTION_EPSILON_DEG = 0.000001


def signed_area(
    points: tuple[tuple[float, float], ...],
) -> float:
    return 0.5 * sum(
        first[0] * second[1] - second[0] * first[1]
        for first, second in zip(points, points[1:])
    )


def check_circle_math(layout) -> None:
    if len(layout.circles) != 12:
        raise AssertionError("expected six CW/CCW circle pairs")
    expected_zone_order = tuple(
        f"{row}{column}"
        for row in ("下", "上")
        for column in ("左", "中", "右")
        for _ in (0, 1)
    )
    if tuple(circle.zone_id for circle in layout.circles) != expected_zone_order:
        raise AssertionError("zone order changed")
    if tuple(circle.direction for circle in layout.circles) != (
        "CW",
        "CCW",
    ) * 6:
        raise AssertionError("pair direction order changed")

    expected_chord = 2.0 * variant.RADIUS_MM * math.sin(
        math.pi / variant.SEGMENTS_PER_CIRCLE
    )
    for circle in layout.circles:
        points = circle.stroke.points
        if len(points) != variant.SEGMENTS_PER_CIRCLE + 1:
            raise AssertionError("circle segment count changed")
        if not math.isclose(
            math.dist(points[0], points[-1]), 0.0, abs_tol=1.0e-10
        ):
            raise AssertionError("circle does not close")
        for point in points:
            radius = math.dist(point, circle.center_mm)
            if not math.isclose(
                radius, variant.RADIUS_MM, abs_tol=1.0e-10
            ):
                raise AssertionError("circle radius changed")
        for first, second in zip(points, points[1:]):
            if not math.isclose(
                math.dist(first, second), expected_chord, abs_tol=1.0e-10
            ):
                raise AssertionError("circle chord length changed")
        area = signed_area(points)
        if circle.direction == "CW" and area >= 0.0:
            raise AssertionError("CW circle orientation changed")
        if circle.direction == "CCW" and area <= 0.0:
            raise AssertionError("CCW circle orientation changed")

    for cw, ccw in zip(layout.circles[0::2], layout.circles[1::2]):
        if cw.zone_id != ccw.zone_id:
            raise AssertionError("circle pair zone mismatch")
        expected_centers = (
            (
                variant.COLUMN_CENTERS_MM[
                    ("左", "中", "右").index(cw.column_name)
                ]
                - variant.PAIR_OFFSET_X_MM,
                variant.ROW_CENTERS_MM[
                    ("下", "上").index(cw.row_name)
                ],
            ),
            (
                variant.COLUMN_CENTERS_MM[
                    ("左", "中", "右").index(ccw.column_name)
                ]
                + variant.PAIR_OFFSET_X_MM,
                variant.ROW_CENTERS_MM[
                    ("下", "上").index(ccw.row_name)
                ],
            ),
        )
        if cw.center_mm != expected_centers[0] or ccw.center_mm != expected_centers[1]:
            raise AssertionError("circle center changed")

    if layout.bounds_mm[1] < 56.0 - 1.0e-9:
        raise AssertionError("lower row moved down unexpectedly")
    if layout.bounds_mm[3] > 229.3:
        raise AssertionError("upper row moved up unexpectedly")
    if (
        variant.ROW_CENTERS_MM[0] + variant.RADIUS_MM >= 114.0
        or variant.ROW_CENTERS_MM[1] - variant.RADIUS_MM <= 201.231
    ):
        raise AssertionError("circle row overlaps existing ink")


def main() -> None:
    layout = variant.build_layout()
    expected_lines = variant.gcode_lines(layout)
    raw_lines = variant.GCODE_PATH.read_text(
        encoding="ascii"
    ).splitlines()
    if tuple(raw_lines) != expected_lines:
        raise AssertionError("V35 G-code differs from circle layout")
    if any(not line.strip() or ";" in line for line in raw_lines):
        raise AssertionError("blank/commented G-code line is not allowed")
    if raw_lines[:5] != [
        "G21",
        "G90",
        "G94",
        "M5",
        f"F{variant.FEED_MM_MIN}",
    ]:
        raise AssertionError("standard setup preamble changed")

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
    if not variant.PREVIEW_PATH.is_file() or not variant.MANIFEST_PATH.is_file():
        raise AssertionError("V35 preview/manifest missing")

    manifest = json.loads(
        variant.MANIFEST_PATH.read_text(encoding="utf-8")
    )
    if manifest["circle_contract"] != {
        "radius_mm": 9.0,
        "diameter_mm": 18.0,
        "segments_per_circle": 72,
        "start_angle_deg": 90.0,
        "pair_order": ["CW", "CCW"],
        "pair_offset_x_mm": 11.0,
    }:
        raise AssertionError("circle manifest contract changed")
    if manifest["gcode"]["sha256"] != hashlib.sha256(
        variant.GCODE_PATH.read_bytes()
    ).hexdigest().upper():
        raise AssertionError("V35 manifest G-code hash mismatch")
    check_circle_math(layout)

    paper_calibration, command_calibration, _ = calibration_arrays()
    coefficients = fit(paper_calibration, command_calibration, 2)
    _, _, total_delta, _ = derive()
    user_position = HOME_USER
    paper_position: tuple[float, float] | None = None
    path_worst = (float("inf"), HOME_USER)
    endpoint_worst = (float("inf"), (0.0, 0.0))
    rapid_outer_segments_max = 0
    draw_paper_segments_max = 0
    min_draw_segment = float("inf")
    max_draw_segment = 0.0
    min_stroke_length = float("inf")
    max_stroke_length = 0.0
    direction_checks = 0

    def mapped_target(point: tuple[float, float]) -> tuple[float, float]:
        nonlocal endpoint_worst
        if not (
            variant.PAPER_X_MIN_MM <= point[0] <= variant.PAPER_X_MAX_MM
            and variant.PAPER_Y_MIN_MM <= point[1] <= variant.PAPER_Y_MAX_MM
        ):
            raise AssertionError(f"paper point out of bounds: {point}")
        mapped = paper_to_user(point, coefficients, total_delta)
        endpoint_margin, _ = margin(mapped)
        if endpoint_margin < endpoint_worst[0]:
            endpoint_worst = (endpoint_margin, point)
        return mapped

    def rapid_to(point: tuple[float, float]) -> None:
        nonlocal user_position, paper_position, path_worst
        nonlocal rapid_outer_segments_max
        target = mapped_target(point)
        span = max(
            abs(target[0] - user_position[0]),
            abs(target[1] - user_position[1]),
        )
        outer_segments = max(
            1, math.ceil(span / RAPID_USER_SEGMENT_MM)
        )
        rapid_outer_segments_max = max(
            rapid_outer_segments_max, outer_segments
        )
        if outer_segments > PLAN_MAX_SEGMENTS:
            raise AssertionError("rapid segmentation exceeds planner")
        path_worst = check_leg(user_position, target, path_worst)
        user_position = target
        paper_position = point

    def draw_to(point: tuple[float, float]) -> None:
        nonlocal user_position, paper_position, path_worst
        nonlocal draw_paper_segments_max
        if paper_position is None:
            raise AssertionError("G1 has no paper-space start")
        source_span = max(
            abs(point[0] - paper_position[0]),
            abs(point[1] - paper_position[1]),
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
            paper_sample = (
                paper_position[0]
                + (point[0] - paper_position[0]) * ratio,
                paper_position[1]
                + (point[1] - paper_position[1]) * ratio,
            )
            mapped_sample = mapped_target(paper_sample)
            path_worst = check_leg(
                previous_user, mapped_sample, path_worst
            )
            previous_user = mapped_sample
        user_position = previous_user
        paper_position = point

    for stroke in layout.strokes:
        first_length = math.dist(stroke.points[0], stroke.points[1])
        unit = (
            (stroke.points[1][0] - stroke.points[0][0]) / first_length,
            (stroke.points[1][1] - stroke.points[0][1]) / first_length,
        )
        if not math.isclose(
            math.dist(stroke.approach, stroke.points[0]),
            variant.TANGENT_APPROACH_MM,
            abs_tol=0.000002,
        ):
            raise AssertionError("circle tangent approach changed")

        initial_point = (
            stroke.points[0][0] + unit[0] * min(1.0, first_length),
            stroke.points[0][1] + unit[1] * min(1.0, first_length),
        )
        approach_user = mapped_target(stroke.approach)
        start_user = mapped_target(stroke.points[0])
        initial_user = mapped_target(initial_point)
        approach_span = math.dist(approach_user, start_user)
        draw_span = math.dist(start_user, initial_user)
        approach_ratio = max(0.0, (approach_span - 1.0) / approach_span)
        draw_ratio = min(1.0, 1.0 / draw_span)
        approach_probe = (
            approach_user[0]
            + (start_user[0] - approach_user[0]) * approach_ratio,
            approach_user[1]
            + (start_user[1] - approach_user[1]) * approach_ratio,
        )
        draw_probe = (
            start_user[0]
            + (initial_user[0] - start_user[0]) * draw_ratio,
            start_user[1]
            + (initial_user[1] - start_user[1]) * draw_ratio,
        )
        for approach_angle, start_angle, initial_angle in zip(
            inverse(*approach_probe)[:2],
            inverse(*start_user)[:2],
            inverse(*draw_probe)[:2],
        ):
            approach_delta = start_angle - approach_angle
            draw_delta = initial_angle - start_angle
            if (
                abs(approach_delta) <= DIRECTION_EPSILON_DEG
                or abs(draw_delta) <= DIRECTION_EPSILON_DEG
                or approach_delta * draw_delta <= 0.0
            ):
                raise AssertionError(
                    f"{stroke.character} reverses a joint at touchdown"
                )
            direction_checks += 1

        rapid_to(stroke.approach)
        rapid_to(stroke.points[0])
        stroke_length = 0.0
        for point in stroke.points[1:]:
            segment_length = math.dist(paper_position, point)
            min_draw_segment = min(min_draw_segment, segment_length)
            max_draw_segment = max(max_draw_segment, segment_length)
            stroke_length += segment_length
            draw_to(point)
        min_stroke_length = min(min_stroke_length, stroke_length)
        max_stroke_length = max(max_stroke_length, stroke_length)

    expected_chord = 2.0 * variant.RADIUS_MM * math.sin(
        math.pi / variant.SEGMENTS_PER_CIRCLE
    )
    expected_circumference = expected_chord * variant.SEGMENTS_PER_CIRCLE
    if not math.isclose(
        min_draw_segment, expected_chord, abs_tol=1.0e-10
    ) or not math.isclose(
        max_draw_segment, expected_chord, abs_tol=1.0e-10
    ):
        raise AssertionError("circle G1 chord lengths differ")
    if not math.isclose(
        min_stroke_length, expected_circumference, abs_tol=1.0e-9
    ) or not math.isclose(
        max_stroke_length, expected_circumference, abs_tol=1.0e-9
    ):
        raise AssertionError("circle circumference differs by zone/direction")
    if endpoint_worst[0] < MIN_ENDPOINT_JOINT_MARGIN_DEG:
        raise AssertionError("endpoint joint margin below limit")

    counts = (
        sum(line.startswith("G0 ") for line in raw_lines),
        sum(line.startswith("G1 ") for line in raw_lines),
        raw_lines.count("M3"),
        raw_lines.count("M5"),
    )
    if counts != (24, 864, 12, 13):
        raise AssertionError(f"unexpected command counts: {counts}")

    print(
        "paper_a4_6zone_circle_pairs_v35=PASS "
        f"zones=6 circles={len(layout.circles)} "
        f"diameter_mm={variant.DIAMETER_MM:.1f} "
        f"segments_per_circle={variant.SEGMENTS_PER_CIRCLE} "
        f"G0={counts[0]} G1={counts[1]} "
        f"joint_direction_checks={direction_checks} "
        f"bounds_x={layout.bounds_mm[0]:.3f}..{layout.bounds_mm[2]:.3f} "
        f"bounds_y={layout.bounds_mm[1]:.3f}..{layout.bounds_mm[3]:.3f}"
    )
    print(
        f"chord_mm={expected_chord:.6f} "
        f"polygon_circumference_mm={expected_circumference:.6f} "
        f"endpoint_min_joint_margin={endpoint_worst[0]:.6f}deg "
        f"path_min_joint_margin={path_worst[0]:.6f}deg "
        f"rapid_outer_segments_max={rapid_outer_segments_max} "
        f"draw_paper_segments_max={draw_paper_segments_max} "
        f"firmware={FIRMWARE_ID} paper_map={PAPER_MAP_ID} grid4x7=ON"
    )


if __name__ == "__main__":
    main()
