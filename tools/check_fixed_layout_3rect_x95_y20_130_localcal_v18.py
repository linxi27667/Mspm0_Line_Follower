"""Offline contract, correction, planner, and kinematic checks for V18."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from check_fixed_layout_3rect_x95_y20_130_waypoint_v17 import (
    FIRST_WAYPOINT,
    HOME_USER,
    MIN_REQUIRED_MARGIN_DEG,
    PLAN_MAX_SEGMENTS,
    margin,
    samples,
)
from derive_3rect_measured_localcal_v18 import REGIONS, derive


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "TASK" / "fixed_layout_axis_mark.c"
HEADER = ROOT / "TASK" / "fixed_layout_axis_mark.h"
SELECTOR = ROOT / "TASK" / "writer_test.h"
PIN_CONFIG = ROOT / "ti_msp_dl_config.c"

EXPECTED_COMMAND = {
    "Y20": (
        (399.694, -52.430), (412.111, -34.921),
        (390.903, -24.690), (378.572, -42.392),
    ),
    "Y65": (
        (355.235, -28.417), (370.148, -9.211),
        (353.307, 1.543), (338.532, -17.784),
    ),
    "Y110": (
        (319.165, -3.030), (332.208, 14.116),
        (317.285, 26.326), (304.384, 9.112),
    ),
}


def planner_segments(
    start: tuple[float, float], end: tuple[float, float]
) -> int:
    return math.ceil(
        max(abs(end[0] - start[0]), abs(end[1] - start[1]))
    )


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    header = HEADER.read_text(encoding="utf-8")
    selector = SELECTOR.read_text(encoding="utf-8")
    pin_config = PIN_CONFIG.read_text(encoding="utf-8")
    combined = source + header
    required = (
        "FIXED_LAYOUT_3RECT_X95_Y20_130_LOCALCAL_V18",
        "AXIS_MARK_REGION_COUNT            (3u)",
        "test=Y_RANGE_3RECT regions=3",
        "order=Y20_Y65_Y110",
        "transform=V17_MEASURED_LOCAL_AFFINE_PLUS_GRID9_QUADRATIC",
        "paper_x_mm=95_115 x_unchanged=1",
        "paper_y_limit_mm=20_130",
        "paper_y_starts_mm=20_65_110",
        "calibration=Y_RANGE_3RECT_LOCALCAL_V18",
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
        raise AssertionError("V18 is not selected")
    if pin_config.count("DL_GPIO_RESISTOR_PULL_UP") != 2:
        raise AssertionError("both limit inputs must retain pull-ups")
    if source.count("App_Servo_Pen_Down();") != 1:
        raise AssertionError("unexpected pen-down implementation count")
    if source.count('"PEN_DOWN_SQUARE"') != 1:
        raise AssertionError("one reusable square operation is required")
    if source.count("AXIS_MARK_OP_MOVE_DRAW") != 6:
        raise AssertionError("exactly four reusable draw moves are required")
    if "M802 accepted" in source:
        raise AssertionError("one-file V18 must not require M802")

    derived = derive()
    checked: list[tuple[float, float]] = []
    all_vertices: list[tuple[float, float]] = []
    region_commands: list[tuple[tuple[float, float], ...]] = []
    worst = (float("inf"), (0.0, 0.0), (0.0, 0.0, 0.0))
    observation_fit_max = 0.0
    corrected_prediction_max = 0.0

    for name, target, observed in REGIONS:
        data = derived[name]
        command = tuple(
            (round(float(point[0]), 3), round(float(point[1]), 3))
            for point in data["command"]
        )
        if command != EXPECTED_COMMAND[name]:
            raise AssertionError(
                f"{name} derived command mismatch: {command}"
            )
        for x_mm, y_mm in command:
            if f"{x_mm:.3f}f" not in source:
                raise AssertionError(
                    f"{name} source X token missing: {x_mm:.3f}f"
                )
            if f"{y_mm:.3f}f" not in source:
                raise AssertionError(
                    f"{name} source Y token missing: {y_mm:.3f}f"
                )

        residuals = np.linalg.norm(
            data["observed_fit"] - observed, axis=1
        )
        observation_fit_max = max(
            observation_fit_max, float(residuals.max())
        )
        local = target - target[0]
        design = np.column_stack((local, np.ones(4)))
        local_to_observed, _, _, _ = np.linalg.lstsq(
            design, observed, rcond=None
        )
        corrected_local = data["corrected_paper"] - target[0]
        predicted = (
            np.column_stack(
                (corrected_local, np.ones(4))
            ) @ local_to_observed
        )
        corrected_errors = np.linalg.norm(
            predicted - target, axis=1
        )
        corrected_prediction_max = max(
            corrected_prediction_max,
            float(corrected_errors.max()),
        )
        if corrected_errors.max() > 0.001:
            raise AssertionError(
                f"{name} inverse correction mismatch"
            )
        if target[:, 0].min() != 95.0 or target[:, 0].max() != 115.0:
            raise AssertionError(f"{name} changed physical X target")
        if target[:, 1].min() < 20.0 or target[:, 1].max() > 130.0:
            raise AssertionError(f"{name} violates physical Y range")

        closed = command + (command[0],)
        for start, end in zip(closed, closed[1:]):
            if planner_segments(start, end) > PLAN_MAX_SEGMENTS:
                raise AssertionError(f"{name} draw plan too long")
            checked.extend(samples(start, end))
        all_vertices.extend(command)
        region_commands.append(command)

    approach_legs = (
        (HOME_USER, FIRST_WAYPOINT),
        (FIRST_WAYPOINT, region_commands[0][0]),
    )
    approach_counts: list[int] = []
    for start, end in approach_legs:
        count = planner_segments(start, end)
        approach_counts.append(count)
        if count > PLAN_MAX_SEGMENTS:
            raise AssertionError(
                f"initial approach leg needs {count} segments"
            )
        for point in samples(start, end):
            approach_margin, _ = margin(point)
            if approach_margin < -0.001:
                raise AssertionError(
                    f"initial approach violates joint bounds at {point}"
                )

    transition_counts: list[int] = []
    for previous, current in zip(
        region_commands, region_commands[1:]
    ):
        start = previous[0]
        end = current[0]
        count = planner_segments(start, end)
        transition_counts.append(count)
        if count > PLAN_MAX_SEGMENTS:
            raise AssertionError(
                f"region transition needs {count} segments"
            )
        checked.extend(samples(start, end))

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
    if observation_fit_max > 1.251:
        raise AssertionError("manual observations are too inconsistent")

    xs = [point[0] for point in all_vertices]
    ys = [point[1] for point in all_vertices]
    print(
        "fixed_layout_3rect_x95_y20_130_localcal_v18=PASS "
        f"regions=3 samples={len(checked)} "
        f"command_bounds_x={min(xs):.3f}..{max(xs):.3f} "
        f"command_bounds_y={min(ys):.3f}..{max(ys):.3f}"
    )
    print(
        f"observation_affine_fit_max={observation_fit_max:.6f}mm "
        f"corrected_model_error_max={corrected_prediction_max:.9f}mm"
    )
    print(
        f"min_joint_margin={worst[0]:.6f}deg "
        f"at=({worst[1][0]:.3f},{worst[1][1]:.3f}) "
        f"theta={worst[2][0]:.3f} "
        f"psi={worst[2][1]:.3f} beta={worst[2][2]:.3f}"
    )
    print(
        f"approach_segments={approach_counts[0]},{approach_counts[1]} "
        f"transition_segments={transition_counts[0]},"
        f"{transition_counts[1]} "
        "physical_target_x=95..115 "
        "physical_target_y=20..40,65..85,110..130"
    )


if __name__ == "__main__":
    main()
