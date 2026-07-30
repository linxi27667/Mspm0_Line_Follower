"""Offline contract, model, and kinematic checks for V15."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from derive_grid9_limited_y_v15 import (
    REGION_ORDER,
    TARGET_START,
    calibration_arrays,
    derive,
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
PAPER_Y_MIN_MM = 20.0
PAPER_Y_MAX_MM = 130.0

# Serpentine firmware order.
REGIONS = (
    ("R11", (25, 100),
     ((262.121, -56.513), (275.821, -37.623),
      (259.949, -27.788), (246.347, -46.823))),
    ("R12", (95, 100),
     ((308.697, 6.920), (321.299, 23.664),
      (305.084, 34.005), (292.581, 17.117))),
    ("R13", (165, 100),
     ((351.429, 62.838), (362.932, 77.434),
      (346.376, 88.281), (334.970, 73.541))),
    ("R23", (165, 65),
     ((381.240, 44.848), (392.914, 59.191),
      (375.624, 69.500), (364.048, 55.012))),
    ("R22", (95, 65),
     ((337.910, -10.184), (350.682, 6.307),
      (333.734, 16.109), (321.060, -0.525))),
    ("R21", (25, 65),
     ((290.736, -72.731), (304.607, -54.093),
      (288.001, -44.797), (274.228, -63.579))),
    ("R31", (25, 30),
     ((320.634, -88.006), (334.676, -69.622),
      (317.336, -60.864), (303.393, -79.393))),
    ("R32", (95, 30),
     ((368.407, -26.345), (381.350, -10.108),
      (363.669, -0.844), (350.823, -17.225))),
    ("R33", (165, 30),
     ((412.335, 27.800), (424.180, 41.890),
      (406.157, 51.661), (394.409, 37.426))),
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


def segment_samples(
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


def joint_margin(point: tuple[float, float]) -> tuple[float, tuple[float, ...]]:
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
    required_text = (
        "FIXED_LAYOUT_A4_GRID9_Y20_130_ONEFILE_V15",
        "AXIS_MARK_REGION_COUNT            (9u)",
        "order=R11_R12_R13_R23_R22_R21_R31_R32_R33",
        "transform=GRID9_QUADRATIC_FROM_V13_36PTS",
        "paper_x_starts_mm=25_95_165",
        "paper_y_limit_mm=20_130",
        "paper_y_starts_mm=100_65_30",
        "x_unchanged=1",
        "execution=ONEFILE_AUTO",
        "automatic=1",
        "completed_count=9/9",
    )
    for text in required_text:
        if text not in combined:
            raise AssertionError(f"contract text missing: {text}")
    if (
        "#define WRITER_TEST_MODE             "
        "WRITER_TEST_MODE_FIXED_LAYOUT_AXIS_MARK"
    ) not in selector:
        raise AssertionError("V15 is not the selected writer task")
    if pin_config.count("DL_GPIO_RESISTOR_PULL_UP") != 2:
        raise AssertionError("both limit inputs must retain pull-ups")
    if source.count("App_Servo_Pen_Down();") != 1:
        raise AssertionError("unexpected pen-down implementation count")
    if source.count('"PEN_DOWN_SQUARE"') != 1:
        raise AssertionError("one reusable square operation is required")
    if source.count("AXIS_MARK_OP_MOVE_DRAW") != 6:
        raise AssertionError("exactly four reusable draw moves are required")
    if "M802 accepted" in source:
        raise AssertionError("one-file V15 must not require M802")
    if "s_state = FIXED_LAYOUT_AXIS_MARK_STATE_WAIT_DRAW" in source:
        raise AssertionError("one-file V15 must auto-start each square")

    derived = derive(2)
    paper_calibration, command_calibration, _ = calibration_arrays()
    forward_model = fit(command_calibration, paper_calibration, 2)
    checked: list[tuple[float, float]] = []
    all_vertices: list[tuple[float, float]] = []
    worst = (float("inf"), (0.0, 0.0), (0.0, 0.0, 0.0))
    max_forward_error = 0.0

    if tuple(name for name, _, _ in REGIONS) != REGION_ORDER:
        raise AssertionError("firmware region order changed")
    for name, paper_start, vertices in REGIONS:
        for actual, expected in zip(vertices, derived[name]):
            if math.dist(actual, expected) > 0.002:
                raise AssertionError(
                    f"{name} source vertex differs from derivation: "
                    f"{actual} != {expected}"
                )
            if f"{actual[0]:.3f}f" not in source:
                raise AssertionError(
                    f"{name} source token missing: {actual[0]:.3f}f"
                )

        if TARGET_START[name] != tuple(float(value) for value in paper_start):
            raise AssertionError(f"{name} paper target changed")
        x0, y0 = TARGET_START[name]
        target_paper = np.array(
            (
                (x0, y0),
                (x0 + 20.0, y0),
                (x0 + 20.0, y0 + 20.0),
                (x0, y0 + 20.0),
            )
        )
        if (
            float(target_paper[:, 1].min()) < PAPER_Y_MIN_MM
            or float(target_paper[:, 1].max()) > PAPER_Y_MAX_MM
        ):
            raise AssertionError(f"{name} violates paper Y limit")
        predicted_paper = evaluate(np.array(vertices), forward_model, 2)
        errors = np.linalg.norm(predicted_paper - target_paper, axis=1)
        max_forward_error = max(max_forward_error, float(errors.max()))
        if errors.max() > 1.5:
            raise AssertionError(
                f"{name} forward model error too large: {errors}"
            )

        closed = vertices + (vertices[0],)
        for start, end in zip(closed, closed[1:]):
            checked.extend(segment_samples(start, end))
        all_vertices.extend(vertices)

    for previous, current in zip(REGIONS, REGIONS[1:]):
        checked.extend(segment_samples(previous[2][0], current[2][0]))

    for point in checked:
        if point[0] < 150.0:
            raise AssertionError(
                f"known command X>=150 guard violated at {point}"
            )
        margin, angles = joint_margin(point)
        if margin < worst[0]:
            worst = (margin, point, angles)
    if worst[0] < MIN_REQUIRED_MARGIN_DEG:
        raise AssertionError(
            f"joint margin {worst[0]:.6f} deg below "
            f"{MIN_REQUIRED_MARGIN_DEG:.1f} deg at {worst[1]}"
        )

    xs = [point[0] for point in all_vertices]
    ys = [point[1] for point in all_vertices]
    print(
        "fixed_layout_a4_grid9_y20_130_onefile_v15=PASS "
        f"regions={len(REGIONS)} samples={len(checked)} "
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
        "paper_x_starts=25,95,165 paper_y_rows=30,65,100 "
        "paper_y_limit=20..130"
    )


if __name__ == "__main__":
    main()
