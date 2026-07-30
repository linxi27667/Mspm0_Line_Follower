"""Offline contract, model, planner, and kinematic checks for V17."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from derive_grid9_limited_y_v15 import (
    calibration_arrays,
    evaluate,
    fit,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "TASK" / "fixed_layout_axis_mark.c"
HEADER = ROOT / "TASK" / "fixed_layout_axis_mark.h"
SELECTOR = ROOT / "TASK" / "writer_test.h"
PIN_CONFIG = ROOT / "ti_msp_dl_config.c"

L1_MM = 205.0
L2_MM = 203.0
OFFSET_X_MM = -129.0
OFFSET_Y_MM = 128.0
THETA_MIN_DEG = -0.773082 + 1.0
THETA_MAX_DEG = 135.0
PSI_MIN_DEG = 134.177381 + 1.0
PSI_MAX_DEG = 255.0
BETA_MIN_DEG = 1.0
BETA_MAX_DEG = 179.0
MIN_REQUIRED_MARGIN_DEG = 15.0
PLAN_MAX_SEGMENTS = 192
HOME_USER = (67.987986978, 15.909491597)
FIRST_WAYPOINT = (220.0, 0.0)

REGIONS = (
    ("Y20", (95, 20),
     ((377.356, -30.789), (390.348, -14.625),
      (372.457, -5.514), (359.563, -21.824))),
    ("Y65", (95, 65),
     ((337.910, -10.184), (350.682, 6.307),
      (333.734, 16.109), (321.060, -0.525))),
    ("Y110", (95, 110),
     ((300.586, 11.980), (313.139, 28.796),
      (297.134, 39.291), (284.679, 22.330))),
)


def inverse(user_x: float, user_y: float) -> tuple[float, float, float]:
    machine_x = user_x + OFFSET_X_MM
    machine_y = user_y + OFFSET_Y_MM
    standard_x = -machine_x
    standard_y = machine_y
    radius_sq = standard_x * standard_x + standard_y * standard_y
    c2 = (
        radius_sq - L1_MM * L1_MM - L2_MM * L2_MM
    ) / (2.0 * L1_MM * L2_MM)
    if not -1.0 <= c2 <= 1.0:
        raise AssertionError(
            f"unreachable command point ({user_x:.3f},{user_y:.3f})"
        )
    s2 = math.sqrt(max(0.0, 1.0 - c2 * c2))
    q2 = math.atan2(s2, c2)
    k1 = L1_MM + L2_MM * c2
    k2 = L2_MM * s2
    theta = math.atan2(k1, k2) - math.atan2(standard_x, standard_y)
    psi = theta + q2
    theta_deg = math.degrees(theta)
    psi_deg = math.degrees(psi)
    return theta_deg, psi_deg, psi_deg - theta_deg


def samples(
    start: tuple[float, float], end: tuple[float, float]
) -> list[tuple[float, float]]:
    count = max(1, math.ceil(math.dist(start, end)))
    return [
        (
            start[0] + (end[0] - start[0]) * index / count,
            start[1] + (end[1] - start[1]) * index / count,
        )
        for index in range(count + 1)
    ]


def margin(point: tuple[float, float]) -> tuple[float, tuple[float, ...]]:
    theta, psi, beta = inverse(*point)
    return (
        min(
            theta - THETA_MIN_DEG,
            THETA_MAX_DEG - theta,
            psi - PSI_MIN_DEG,
            PSI_MAX_DEG - psi,
            beta - BETA_MIN_DEG,
            BETA_MAX_DEG - beta,
        ),
        (theta, psi, beta),
    )


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    header = HEADER.read_text(encoding="utf-8")
    selector = SELECTOR.read_text(encoding="utf-8")
    pin_config = PIN_CONFIG.read_text(encoding="utf-8")
    combined = source + header
    required = (
        "FIXED_LAYOUT_3RECT_X95_Y20_130_WAYPOINT_V17",
        "AXIS_MARK_REGION_COUNT            (3u)",
        "test=Y_RANGE_3RECT regions=3",
        "order=Y20_Y65_Y110",
        "paper_x_mm=95_115 x_unchanged=1",
        "paper_y_limit_mm=20_130",
        "paper_y_starts_mm=20_65_110",
        "completed_count=3/3",
        "execution=ONEFILE_AUTO",
        "first_waypoint=(22000,0)",
        "plan_segments_max=192",
    )
    for text in required:
        if text not in combined:
            raise AssertionError(f"contract text missing: {text}")
    if (
        "#define WRITER_TEST_MODE             "
        "WRITER_TEST_MODE_FIXED_LAYOUT_AXIS_MARK"
    ) not in selector:
        raise AssertionError("V17 is not selected")
    if pin_config.count("DL_GPIO_RESISTOR_PULL_UP") != 2:
        raise AssertionError("both limit inputs must retain pull-ups")
    if source.count("App_Servo_Pen_Down();") != 1:
        raise AssertionError("unexpected pen-down implementation count")
    if source.count('"PEN_DOWN_SQUARE"') != 1:
        raise AssertionError("one reusable square operation is required")
    if source.count("AXIS_MARK_OP_MOVE_DRAW") != 6:
        raise AssertionError("exactly four reusable draw moves are required")
    if "M802 accepted" in source:
        raise AssertionError("one-file V17 must not require M802")
    if "s_state = FIXED_LAYOUT_AXIS_MARK_STATE_WAIT_DRAW" in source:
        raise AssertionError("one-file V17 must auto-start each rectangle")

    paper_calibration, command_calibration, _ = calibration_arrays()
    inverse_model = fit(paper_calibration, command_calibration, 2)
    forward_model = fit(command_calibration, paper_calibration, 2)
    checked: list[tuple[float, float]] = []
    all_vertices: list[tuple[float, float]] = []
    worst = (float("inf"), (0.0, 0.0), (0.0, 0.0, 0.0))
    max_forward_error = 0.0

    for name, (x0, y0), vertices in REGIONS:
        target = np.array(
            (
                (x0, y0),
                (x0 + 20.0, y0),
                (x0 + 20.0, y0 + 20.0),
                (x0, y0 + 20.0),
            )
        )
        derived = evaluate(target, inverse_model, 2)
        for actual, expected in zip(vertices, derived):
            if math.dist(actual, expected) > 0.002:
                raise AssertionError(
                    f"{name} source vertex mismatch: {actual} != {expected}"
                )
            if f"{actual[0]:.3f}f" not in source:
                raise AssertionError(
                    f"{name} source token missing: {actual[0]:.3f}f"
                )
        if target[:, 1].min() < 20.0 or target[:, 1].max() > 130.0:
            raise AssertionError(f"{name} violates requested Y range")
        if target[:, 0].min() != 95.0 or target[:, 0].max() != 115.0:
            raise AssertionError(f"{name} changed the X calibration column")
        predicted = evaluate(np.array(vertices), forward_model, 2)
        errors = np.linalg.norm(predicted - target, axis=1)
        max_forward_error = max(max_forward_error, float(errors.max()))
        if errors.max() > 1.5:
            raise AssertionError(f"{name} model error too large: {errors}")

        closed = vertices + (vertices[0],)
        for start, end in zip(closed, closed[1:]):
            checked.extend(samples(start, end))
        all_vertices.extend(vertices)

    for previous, current in zip(REGIONS, REGIONS[1:]):
        checked.extend(samples(previous[2][0], current[2][0]))

    approach_legs = (
        (HOME_USER, FIRST_WAYPOINT),
        (FIRST_WAYPOINT, REGIONS[0][2][0]),
    )
    approach_counts = []
    for start, end in approach_legs:
        segment_count = math.ceil(
            max(abs(end[0] - start[0]), abs(end[1] - start[1]))
        )
        approach_counts.append(segment_count)
        if segment_count > PLAN_MAX_SEGMENTS:
            raise AssertionError(
                f"initial approach leg needs {segment_count} segments"
            )
        for point in samples(start, end):
            approach_margin, _ = margin(point)
            if approach_margin < -0.001:
                raise AssertionError(
                    f"initial approach violates joint bounds at {point}"
                )

    for point in checked:
        if point[0] < 150.0:
            raise AssertionError(f"command X guard violated at {point}")
        joint_margin, angles = margin(point)
        if joint_margin < worst[0]:
            worst = (joint_margin, point, angles)
    if worst[0] < MIN_REQUIRED_MARGIN_DEG:
        raise AssertionError(
            f"joint margin {worst[0]:.6f} deg below "
            f"{MIN_REQUIRED_MARGIN_DEG:.1f} deg at {worst[1]}"
        )

    xs = [point[0] for point in all_vertices]
    ys = [point[1] for point in all_vertices]
    print(
        "fixed_layout_3rect_x95_y20_130_waypoint_v17=PASS "
        f"regions=3 samples={len(checked)} "
        f"command_bounds_x={min(xs):.3f}..{max(xs):.3f} "
        f"command_bounds_y={min(ys):.3f}..{max(ys):.3f}"
    )
    print(
        f"min_joint_margin={worst[0]:.6f}deg "
        f"at=({worst[1][0]:.3f},{worst[1][1]:.3f}) "
        f"theta={worst[2][0]:.3f} "
        f"psi={worst[2][1]:.3f} beta={worst[2][2]:.3f}"
    )
    print(
        f"forward_model_max_target_error={max_forward_error:.6f}mm "
        "paper_x=95..115 paper_y=20..40,65..85,110..130 "
        f"approach_segments={approach_counts[0]},{approach_counts[1]}"
    )


if __name__ == "__main__":
    main()
