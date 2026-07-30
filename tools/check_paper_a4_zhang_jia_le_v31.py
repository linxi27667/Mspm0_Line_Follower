"""Check the upright V31 gfont-based 张佳乐 sample."""

from __future__ import annotations

import json
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
from generate_paper_a4_zhang_jia_le_v30 import split_strokes
from generate_paper_a4_zhang_jia_le_v31 import (
    EXPECTED_STROKE_COUNTS,
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
MIN_DRAW_SEGMENT_MM = 0.20
MIN_STROKE_LENGTH_MM = 2.0
DIRECTION_EPSILON_DEG = 0.000001
CHECK_VARIANT = "V31"


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


def check_font_geometry(layout) -> None:
    if tuple(item.character for item in layout.characters) != tuple(TEXT):
        raise AssertionError("left-to-right character order changed")
    if tuple(
        item.stroke_count for item in layout.characters
    ) != EXPECTED_STROKE_COUNTS:
        raise AssertionError("per-character stroke counts changed")
    if any(
        left.bounds_mm[2] >= right.bounds_mm[0]
        for left, right in zip(layout.characters, layout.characters[1:])
    ):
        raise AssertionError("character boxes are not left-to-right")

    for character_index, character in enumerate(TEXT):
        glyph = layout.font.glyphs[character]
        character_layout = layout.characters[character_index]
        source_x_min, source_y_min, _, _ = glyph.bounds
        expected_points = tuple(
            (
                character_layout.bounds_mm[0]
                + (source_x - source_x_min) * layout.scale_mm_per_unit,
                character_layout.bounds_mm[3]
                - (source_y - source_y_min) * layout.scale_mm_per_unit,
            )
            for source_x, source_y in glyph.points
        )
        expected_strokes = split_strokes(
            character, expected_points, glyph.commands
        )
        actual_strokes = [
            stroke.points
            for stroke in layout.strokes
            if stroke.character_index == character_index
        ]
        if len(expected_strokes) != len(actual_strokes):
            raise AssertionError(f"{character} source stroke count changed")
        for expected, actual in zip(expected_strokes, actual_strokes):
            if len(expected) != len(actual):
                raise AssertionError(f"{character} source point count changed")
            for source_point, actual_point in zip(expected, actual):
                if not (
                    math.isclose(
                        source_point[0], actual_point[0], abs_tol=1.0e-10
                    )
                    and math.isclose(
                        source_point[1], actual_point[1], abs_tol=1.0e-10
                    )
                ):
                    raise AssertionError(
                        f"{character} no longer follows original gfont path"
                    )

    # Upright sentinels: in 乐, the first/top stroke must be above both
    # lower diagonal strokes.  This assertion fails under V30's Y transform.
    le_strokes = [
        stroke for stroke in layout.strokes if stroke.character == "乐"
    ]
    mean_y = [
        sum(point[1] for point in stroke.points) / len(stroke.points)
        for stroke in le_strokes
    ]
    if not (mean_y[0] > mean_y[3] and mean_y[0] > mean_y[4]):
        raise AssertionError("乐 is vertically reversed")
    if not (
        le_strokes[0].points[0][1] > le_strokes[0].points[-1][1]
        and le_strokes[3].points[0][1] > le_strokes[3].points[-1][1]
        and le_strokes[4].points[0][1] > le_strokes[4].points[-1][1]
    ):
        raise AssertionError("乐 stroke direction/order is reversed")


def main() -> None:
    layout = build_layout()
    expected_lines = gcode_lines(layout)
    raw_lines = GCODE_PATH.read_text(encoding="ascii").splitlines()
    if tuple(raw_lines) != expected_lines:
        raise AssertionError(
            f"{CHECK_VARIANT} G-code does not match pinned font layout"
        )
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
        raise AssertionError(f"{CHECK_VARIANT} preview/manifest is missing")
    if digest(layout.font.path) != FONT_SHA256:
        raise AssertionError("font hash changed after layout")

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if (
        manifest["coordinate_contract"]["transform_y"]
        != "paper_y = baseline_y - source_y * scale"
    ):
        raise AssertionError("manifest lost the upright Y transform")
    if manifest["font"]["geometry"] != (
        "unmodified gfont path points and command order"
    ):
        raise AssertionError("manifest lost font provenance")
    check_font_geometry(layout)

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
        if not math.isclose(
            math.dist(stroke.approach, stroke.points[0]),
            TANGENT_APPROACH_MM,
            abs_tol=0.000002,
        ):
            raise AssertionError("tangent approach is not 6 mm")

        initial_point = (
            stroke.points[0][0]
            + unit[0] * min(1.0, first_segment_length),
            stroke.points[0][1]
            + unit[1] * min(1.0, first_segment_length),
        )
        approach_user = mapped_target(stroke.approach)
        start_user = mapped_target(stroke.points[0])
        initial_user = mapped_target(initial_point)
        approach_user_span = math.dist(approach_user, start_user)
        draw_user_span = math.dist(start_user, initial_user)
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
                    f"{stroke.character} stroke {stroke.stroke_index} "
                    "reverses a joint at touchdown"
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
    expected_counts = (
        len(layout.strokes) * 2,
        sum(len(stroke.points) - 1 for stroke in layout.strokes),
        len(layout.strokes),
        len(layout.strokes) + 1,
    )
    if (g0_count, g1_count, m3_count, m5_count) != expected_counts:
        raise AssertionError(
            f"unexpected {CHECK_VARIANT} command counts"
        )

    print(
        f"paper_a4_zhang_jia_le_{CHECK_VARIANT.lower()}=PASS "
        f"text={TEXT} font={layout.font.name} "
        f"strokes={len(layout.strokes)} G0={g0_count} G1={g1_count} "
        f"character_strokes={EXPECTED_STROKE_COUNTS} "
        f"source_geometry=EXACT upright_y=PASS "
        f"joint_direction_checks={direction_checks} "
        f"bounds_x={layout.bounds_mm[0]:.3f}..{layout.bounds_mm[2]:.3f} "
        f"bounds_y={layout.bounds_mm[1]:.3f}..{layout.bounds_mm[3]:.3f}"
    )
    print(
        f"draw_segment_mm={min_draw_segment:.3f}..{max_draw_segment:.3f} "
        f"stroke_length_mm={min_stroke_length:.3f}.."
        f"{max_stroke_length:.3f} "
        f"endpoint_min_joint_margin={endpoint_worst[0]:.6f}deg "
        f"path_min_joint_margin={path_worst[0]:.6f}deg "
        f"rapid_outer_segments_max={rapid_outer_segments_max} "
        f"draw_paper_segments_max={draw_paper_segments_max} "
        f"firmware={FIRMWARE_ID} paper_map={PAPER_MAP_ID} grid4x7=ON"
    )


if __name__ == "__main__":
    main()
