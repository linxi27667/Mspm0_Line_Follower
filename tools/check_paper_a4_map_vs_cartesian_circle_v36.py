"""Check the V36 paper-map versus Cartesian-circle isolation test."""

from __future__ import annotations

import hashlib
import json
import math

import numpy as np

from check_fixed_layout_3rect_x95_y20_130_waypoint_v17 import (
    HOME_USER,
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
from check_paper_a4_font_vs_program_isolation_v34 import check_leg
import generate_paper_a4_map_vs_cartesian_circle_v36 as variant


ROOT = variant.ROOT
GCODE_HEADER = ROOT / "TASK" / "gcode_serial.h"
STAGE1_STEPS_PER_DEG = 40.099216
STAGE2_STEPS_PER_DEG = 40.115790
L1_MM = 205.0
L2_MM = 203.0
QUANTIZATION_ERROR_LIMIT_MM = 0.1
DIRECTION_EPSILON_DEG = 1.0e-6


def signed_area(
    points: tuple[tuple[float, float], ...],
) -> float:
    return 0.5 * sum(
        first[0] * second[1] - second[0] * first[1]
        for first, second in zip(points, points[1:])
    )


def extent(
    points: tuple[tuple[float, float], ...],
) -> tuple[float, float]:
    data = np.asarray(points, dtype=float)
    return float(np.ptp(data[:, 0])), float(np.ptp(data[:, 1]))


def lround(value: float) -> int:
    return (
        math.floor(value + 0.5)
        if value >= 0.0
        else math.ceil(value - 0.5)
    )


def user_from_steps(
    stage1_steps: int,
    stage2_steps: int,
) -> tuple[float, float]:
    theta = math.radians(stage1_steps / STAGE1_STEPS_PER_DEG)
    psi = math.radians(stage2_steps / STAGE2_STEPS_PER_DEG)
    standard_x = L1_MM * math.cos(theta) + L2_MM * math.cos(psi)
    standard_y = L1_MM * math.sin(theta) + L2_MM * math.sin(psi)
    return 129.0 - standard_x, standard_y - 128.0


def quantization_error(user_point: tuple[float, float]) -> float:
    theta, psi, _ = inverse(*user_point)
    realized = user_from_steps(
        lround(theta * STAGE1_STEPS_PER_DEG),
        lround(psi * STAGE2_STEPS_PER_DEG),
    )
    return math.dist(user_point, realized)


def check_circle_contract(layout: variant.CircleLayout) -> None:
    if len(layout.circles) != 12:
        raise AssertionError("expected six A/B circle pairs")
    if tuple(circle.mode for circle in layout.circles) != (
        variant.MODE_PAPER_CIRCLE,
        variant.MODE_CARTESIAN_CIRCLE,
    ) * 6:
        raise AssertionError("A/B circle order changed")

    expected_chord = 2.0 * variant.RADIUS_MM * math.sin(
        math.pi / variant.SEGMENTS_PER_CIRCLE
    )
    coefficients, total_delta = variant.mapping_model()
    a_anisotropy = []
    b_remap_error_max = 0.0

    for circle in layout.circles:
        source = circle.source_points_mm
        target = circle.target_user_points_mm
        if len(source) != variant.SEGMENTS_PER_CIRCLE + 1:
            raise AssertionError("source segment count changed")
        if len(target) != variant.SEGMENTS_PER_CIRCLE + 1:
            raise AssertionError("target segment count changed")
        if math.dist(source[0], source[-1]) > 1.0e-10:
            raise AssertionError("source circle does not close")
        if math.dist(target[0], target[-1]) > 1.0e-10:
            raise AssertionError("target circle does not close")
        if signed_area(source) >= 0.0 or signed_area(target) >= 0.0:
            raise AssertionError("V36 circles must run clockwise")

        remapped = tuple(
            tuple(
                variant.mapped(point, coefficients, total_delta)
            )
            for point in source
        )
        remap_error = max(
            math.dist(actual, expected)
            for actual, expected in zip(remapped, target)
        )
        b_remap_error_max = max(b_remap_error_max, remap_error)
        if remap_error > variant.INVERSE_TOLERANCE_MM * 2.0:
            raise AssertionError(
                f"{circle.zone_id}/{circle.mode}: remap mismatch "
                f"{remap_error:.12f} mm"
            )

        if circle.mode == variant.MODE_PAPER_CIRCLE:
            for point in source:
                if not math.isclose(
                    math.dist(
                        point, circle.nominal_paper_center_mm
                    ),
                    variant.RADIUS_MM,
                    abs_tol=1.0e-10,
                ):
                    raise AssertionError("A source is not a paper circle")
            width, height = extent(target)
            a_anisotropy.append(max(width, height) / min(width, height))
        else:
            for point in target:
                if not math.isclose(
                    math.dist(
                        point, circle.target_user_center_mm
                    ),
                    variant.RADIUS_MM,
                    abs_tol=1.0e-10,
                ):
                    raise AssertionError(
                        "B target is not a Cartesian circle"
                    )
            width, height = extent(target)
            if not (
                math.isclose(
                    width, variant.DIAMETER_MM, abs_tol=1.0e-10
                )
                and math.isclose(
                    height, variant.DIAMETER_MM, abs_tol=1.0e-10
                )
            ):
                raise AssertionError("B target extent changed")
            for first, second in zip(target, target[1:]):
                if not math.isclose(
                    math.dist(first, second),
                    expected_chord,
                    abs_tol=1.0e-10,
                ):
                    raise AssertionError(
                        "B Cartesian chord length changed"
                    )

    if max(a_anisotropy) < 1.25:
        raise AssertionError(
            "A trajectories no longer expose the mapped anisotropy"
        )
    if b_remap_error_max > 2.0e-9:
        raise AssertionError("inverse-map numerical error is too large")


def check_kinematics(layout: variant.CircleLayout) -> dict[str, float]:
    coefficients, total_delta = variant.mapping_model()
    user_position = HOME_USER
    path_worst = (float("inf"), HOME_USER)
    endpoint_worst = float("inf")
    quantization_error_max = 0.0
    direction_checks = 0
    max_source_component_step = 0.0

    for circle in layout.circles:
        approach_user = tuple(
            variant.mapped(
                circle.source_approach_mm,
                coefficients,
                total_delta,
            )
        )
        start_user = circle.target_user_points_mm[0]
        next_user = circle.target_user_points_mm[1]
        path_worst = check_leg(user_position, approach_user, path_worst)
        path_worst = check_leg(approach_user, start_user, path_worst)

        for approach_angle, start_angle, next_angle in zip(
            inverse(*approach_user)[:2],
            inverse(*start_user)[:2],
            inverse(*next_user)[:2],
        ):
            approach_delta = start_angle - approach_angle
            draw_delta = next_angle - start_angle
            if (
                abs(approach_delta) <= DIRECTION_EPSILON_DEG
                or abs(draw_delta) <= DIRECTION_EPSILON_DEG
                or approach_delta * draw_delta <= 0.0
            ):
                raise AssertionError(
                    f"{circle.zone_id}/{circle.mode}: "
                    "joint reverses at touchdown"
                )
            direction_checks += 1

        for source_first, source_second, user_first, user_second in zip(
            circle.source_points_mm,
            circle.source_points_mm[1:],
            circle.target_user_points_mm,
            circle.target_user_points_mm[1:],
        ):
            max_source_component_step = max(
                max_source_component_step,
                abs(source_second[0] - source_first[0]),
                abs(source_second[1] - source_first[1]),
            )
            path_worst = check_leg(user_first, user_second, path_worst)
        for point in circle.target_user_points_mm:
            endpoint_margin, _ = margin(point)
            endpoint_worst = min(endpoint_worst, endpoint_margin)
            quantization_error_max = max(
                quantization_error_max,
                quantization_error(point),
            )
        user_position = circle.target_user_points_mm[-1]

    if endpoint_worst < MIN_ENDPOINT_JOINT_MARGIN_DEG:
        raise AssertionError("V36 endpoint joint margin below limit")
    if quantization_error_max > QUANTIZATION_ERROR_LIMIT_MM:
        raise AssertionError("V36 joint quantization error too large")
    if max_source_component_step >= 2.0:
        raise AssertionError(
            "a V36 G1 would be subdivided by the outer paper planner"
        )
    return {
        "path_margin_deg": path_worst[0],
        "endpoint_margin_deg": endpoint_worst,
        "quantization_error_max_mm": quantization_error_max,
        "direction_checks": float(direction_checks),
        "max_source_component_step_mm": max_source_component_step,
    }


def main() -> None:
    layout = variant.build_layout()
    expected_lines = variant.gcode_lines(layout)
    actual_lines = tuple(
        variant.GCODE_PATH.read_text(encoding="ascii").splitlines()
    )
    if actual_lines != expected_lines:
        raise AssertionError("V36 G-code differs from generated layout")
    if actual_lines[:5] != (
        "G21",
        "G90",
        "G94",
        "M5",
        f"F{variant.FEED_MM_MIN}",
    ):
        raise AssertionError("V36 standard G-code preamble changed")
    counts = (
        sum(line.startswith("G0 ") for line in actual_lines),
        sum(line.startswith("G1 ") for line in actual_lines),
        actual_lines.count("M3"),
        actual_lines.count("M5"),
    )
    if counts != (24, 864, 12, 13):
        raise AssertionError(f"unexpected V36 command counts: {counts}")

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
        raise AssertionError("4x7 paper correction must remain enabled")
    if pin_config.count("DL_GPIO_RESISTOR_PULL_UP") != 2:
        raise AssertionError("both limit inputs must retain pull-ups")

    check_circle_contract(layout)
    metrics = check_kinematics(layout)
    if not variant.PREVIEW_PATH.is_file():
        raise AssertionError("V36 preview is missing")
    manifest = json.loads(
        variant.MANIFEST_PATH.read_text(encoding="utf-8")
    )
    digest = hashlib.sha256(variant.GCODE_PATH.read_bytes()).hexdigest().upper()
    if manifest["gcode"]["sha256"] != digest:
        raise AssertionError("V36 manifest hash mismatch")

    print(
        "paper_a4_map_vs_cartesian_circle_v36=PASS "
        "zones=6 pairs=6 circles=12 "
        "left=A_PAPER_CIRCLE right=B_CARTESIAN_CIRCLE "
        f"G0={counts[0]} G1={counts[1]} M3={counts[2]} M5={counts[3]}"
    )
    print(
        f"endpoint_min_joint_margin={metrics['endpoint_margin_deg']:.6f}deg "
        f"path_min_joint_margin={metrics['path_margin_deg']:.6f}deg "
        "quantized_ik_fk_error_max="
        f"{metrics['quantization_error_max_mm']:.6f}mm "
        "source_component_step_max="
        f"{metrics['max_source_component_step_mm']:.6f}mm "
        f"touchdown_joint_checks={int(metrics['direction_checks'])}"
    )
    for circle in layout.circles:
        source_width, source_height = extent(circle.source_points_mm)
        target_width, target_height = extent(
            circle.target_user_points_mm
        )
        print(
            f"{circle.zone_id} {circle.mode} "
            f"source={source_width:.3f}x{source_height:.3f}mm "
            f"post_map_target={target_width:.3f}x{target_height:.3f}mm"
        )
    print(f"gcode_sha256={digest}")


if __name__ == "__main__":
    main()
