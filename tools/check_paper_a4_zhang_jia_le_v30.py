"""Check the calibrated V30 Chen-handwriting Chinese text sample."""

from __future__ import annotations

import math

from check_fixed_layout_3rect_x95_y20_130_waypoint_v17 import (
    HOME_USER,
    PLAN_MAX_SEGMENTS,
    inverse,
    margin,
    samples,
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
from derive_grid9_limited_y_v15 import calibration_arrays, fit
from derive_paper_a4_4x7_grid_v25 import derive
from generate_paper_a4_zhang_jia_le_v30 import (
    FEED_MM_MIN,
    FONT_SHA256,
    GCODE_PATH,
    MANIFEST_PATH,
    PAPER_X_MAX_MM,
    PAPER_X_MIN_MM,
    PAPER_Y_MAX_MM,
    PAPER_Y_MIN_MM,
    PREVIEW_PATH,
    TANGENT_APPROACH_MM,
    TEXT,
    build_layout,
    digest,
    gcode_lines,
)


ROOT = GCODE_PATH.parents[1]
GCODE_HEADER = ROOT / "TASK" / "gcode_serial.h"
DRAW_PAPER_SEGMENT_MM = 2.0
RAPID_USER_SEGMENT_MM = 20.0
MIN_DRAW_SEGMENT_MM = 0.5
MIN_STROKE_LENGTH_MM = 8.0
DIRECTION_EPSILON_DEG = 0.000001


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
    layout = build_layout()
    expected_lines = gcode_lines(layout)
    raw_lines = GCODE_PATH.read_text(encoding="ascii").splitlines()
    if tuple(raw_lines) != expected_lines:
        raise AssertionError("V30 G-code does not match pinned font layout")
    if any(not line.strip() or ";" in line for line in raw_lines):
        raise AssertionError("blank/commented G-code line is not allowed")
    if raw_lines[:5] != ["G21", "G90", "G94", "M5", f"F{FEED_MM_MIN}"]:
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
    if not PREVIEW_PATH.is_file() or not MANIFEST_PATH.is_file():
        raise AssertionError("V30 preview/manifest is missing")
    if digest(layout.font.path) != FONT_SHA256:
        raise AssertionError("font hash changed after layout")

    if tuple(item.character for item in layout.characters) != tuple(TEXT):
        raise AssertionError("character order changed")
    expected_strokes = (7, 7, 5)
    actual_strokes = tuple(
        item.stroke_count for item in layout.characters
    )
    if actual_strokes != expected_strokes:
        raise AssertionError(
            f"unexpected per-character strokes: {actual_strokes}"
        )

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
            PAPER_X_MIN_MM <= point[0] <= PAPER_X_MAX_MM
            and PAPER_Y_MIN_MM <= point[1] <= PAPER_Y_MAX_MM
        ):
            raise AssertionError(f"paper point out of bounds: {point}")
        mapped = paper_to_user(point, coefficients, total_delta)
        endpoint_margin, _ = margin(mapped)
        if endpoint_margin < endpoint_worst[0]:
            endpoint_worst = (endpoint_margin, point)
        return mapped

    def rapid_to(point: tuple[float, float]) -> None:
        nonlocal user_position
        nonlocal paper_position
        nonlocal path_worst
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
        nonlocal user_position
        nonlocal paper_position
        nonlocal path_worst
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
        first_segment_length = math.dist(
            stroke.points[0], stroke.points[1]
        )
        unit = (
            (stroke.points[1][0] - stroke.points[0][0])
            / first_segment_length,
            (stroke.points[1][1] - stroke.points[0][1])
            / first_segment_length,
        )
        approach_length = math.dist(stroke.approach, stroke.points[0])
        if not math.isclose(
            approach_length, TANGENT_APPROACH_MM, abs_tol=0.000002
        ):
            raise AssertionError("tangent approach is not 6 mm")

        initial_point = (
            stroke.points[0][0] + unit[0] * min(1.0, first_segment_length),
            stroke.points[0][1] + unit[1] * min(1.0, first_segment_length),
        )
        approach_user = mapped_target(stroke.approach)
        start_user = mapped_target(stroke.points[0])
        initial_user = mapped_target(initial_point)
        approach_user_span = math.dist(approach_user, start_user)
        draw_user_span = math.dist(start_user, initial_user)
        if approach_user_span <= 0.0 or draw_user_span <= 0.0:
            raise AssertionError("zero-length mapped touchdown direction")

        # G0 is internally a straight user-space path. Compare its final
        # 1 mm with the first 1 mm of the mapped G1 path; these are the two
        # motor directions that meet while the pen is touching the paper.
        approach_probe_ratio = max(
            0.0, (approach_user_span - 1.0) / approach_user_span
        )
        draw_probe_ratio = min(1.0, 1.0 / draw_user_span)
        approach_probe = (
            approach_user[0]
            + (start_user[0] - approach_user[0]) * approach_probe_ratio,
            approach_user[1]
            + (start_user[1] - approach_user[1]) * approach_probe_ratio,
        )
        draw_probe = (
            start_user[0]
            + (initial_user[0] - start_user[0]) * draw_probe_ratio,
            start_user[1]
            + (initial_user[1] - start_user[1]) * draw_probe_ratio,
        )
        approach_angles = inverse(*approach_probe)[:2]
        start_angles = inverse(*start_user)[:2]
        initial_angles = inverse(*draw_probe)[:2]
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
                    f"{stroke.character} stroke {stroke.stroke_index} "
                    f"joint {joint_index} reverses at touchdown"
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

    if min_draw_segment < MIN_DRAW_SEGMENT_MM:
        raise AssertionError(
            f"draw segment {min_draw_segment:.6f} mm is too short"
        )
    if min_stroke_length < MIN_STROKE_LENGTH_MM:
        raise AssertionError(
            f"stroke {min_stroke_length:.6f} mm is too short"
        )
    if endpoint_worst[0] < MIN_ENDPOINT_JOINT_MARGIN_DEG:
        raise AssertionError(
            f"endpoint joint margin {endpoint_worst[0]:.6f} deg below "
            f"{MIN_ENDPOINT_JOINT_MARGIN_DEG:.1f} deg"
        )

    g0_count = sum(line.startswith("G0 ") for line in raw_lines)
    g1_count = sum(line.startswith("G1 ") for line in raw_lines)
    m3_count = raw_lines.count("M3")
    m5_count = raw_lines.count("M5")
    if (g0_count, g1_count, m3_count, m5_count) != (38, 55, 19, 20):
        raise AssertionError("unexpected V30 command counts")

    print(
        "paper_a4_zhang_jia_le_v30=PASS "
        f"text={TEXT} font={layout.font.name} "
        f"strokes={len(layout.strokes)} G0={g0_count} G1={g1_count} "
        f"character_strokes={actual_strokes} "
        f"joint_direction_checks={direction_checks} "
        f"bounds_x={layout.bounds_mm[0]:.3f}..{layout.bounds_mm[2]:.3f} "
        f"bounds_y={layout.bounds_mm[1]:.3f}..{layout.bounds_mm[3]:.3f}"
    )
    print(
        f"draw_segment_mm={min_draw_segment:.3f}..{max_draw_segment:.3f} "
        f"stroke_length_mm={min_stroke_length:.3f}.."
        f"{max_stroke_length:.3f} "
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
