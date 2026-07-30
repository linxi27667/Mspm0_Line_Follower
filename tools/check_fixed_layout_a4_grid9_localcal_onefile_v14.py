"""Offline checks for the V14 photo-derived local nine-region calibration."""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np

from derive_grid9_local_correction_v14 import (
    NOMINAL,
    ORIGINAL_COMMAND,
    TARGET_PAPER_X_MM,
    correct_region,
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

# Photo-rectified V13 quadrilaterals in paper coordinates. R31's hidden left
# edge is reconstructed from its visible right edge and horizontal response.
OBSERVED = {
    "R11": ((10.315, 212.672), (26.839, 210.651),
            (25.325, 232.706), (5.049, 234.852)),
    "R12": ((68.002, 212.345), (90.563, 214.041),
            (90.301, 235.338), (67.372, 233.904)),
    "R13": ((135.506, 218.712), (160.474, 221.155),
            (160.578, 241.948), (135.611, 239.440)),
    "R23": ((135.010, 132.141), (160.698, 134.329),
            (161.658, 154.489), (135.532, 152.834)),
    "R22": ((67.599, 125.376), (90.952, 127.648),
            (91.785, 148.025), (68.658, 146.671)),
    "R21": ((9.229, 116.350), (28.124, 120.067),
            (30.198, 141.841), (13.032, 139.248)),
    "R31": ((-1.426, 51.604), (20.974, 54.789),
            (23.798, 73.434), (1.398, 70.249)),
    "R32": ((63.927, 60.418), (88.652, 62.892),
            (90.004, 81.942), (65.389, 79.770)),
    "R33": ((133.500, 67.274), (159.393, 69.768),
            (160.523, 89.225), (134.637, 86.771)),
}

# name, reported target paper start, cell x, cell y, V14 command vertices
REGIONS = (
    ("R11", (25, 213), (0, 70), (198, 297),
     ((179.929, 3.868), (193.218, 31.004),
      (177.610, 38.955), (166.101, 16.785))),
    ("R12", (95, 212), (70, 140), (198, 297),
     ((224.305, 69.768), (237.884, 89.371),
      (221.842, 101.004), (208.669, 81.538))),
    ("R13", (165, 219), (140, 210), (198, 297),
     ((261.818, 130.454), (274.104, 147.135),
      (258.061, 158.822), (245.734, 142.168))),
    ("R23", (165, 132), (140, 210), (99, 198),
     ((327.476, 82.018), (340.237, 99.545),
      (322.294, 110.891), (310.180, 93.425))),
    ("R22", (95, 125), (70, 140), (99, 198),
     ((290.552, 20.610), (305.063, 40.541),
      (287.502, 52.458), (273.569, 31.950))),
    ("R21", (25, 116), (0, 70), (99, 198),
     ((248.900, -48.591), (267.007, -25.446),
      (251.322, -15.091), (232.240, -40.378))),
    ("R31", (25, 52), (0, 70), (0, 99),
     ((304.988, -78.305), (319.883, -59.778),
      (299.748, -49.422), (284.852, -67.948))),
    ("R32", (95, 60), (70, 140), (0, 99),
     ((342.233, -14.739), (355.423, 2.822),
      (336.782, 14.720), (323.782, -3.038))),
    ("R33", (165, 67), (140, 210), (0, 99),
     ((378.537, 45.900), (390.720, 62.151),
      (372.847, 73.849), (360.692, 57.578))),
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


def predict_paper(
    name: str, command_vertices: tuple[tuple[float, float], ...]
) -> np.ndarray:
    old_command = np.array(ORIGINAL_COMMAND[name], dtype=float)
    command_basis = np.column_stack(
        (
            (old_command[1] - old_command[0]) / 20.0,
            (old_command[3] - old_command[0]) / 20.0,
        )
    )
    nominal_points = []
    for point in command_vertices:
        nominal_points.append(
            np.linalg.solve(
                command_basis,
                np.array(point, dtype=float) - old_command[0],
            )
        )
    paper_from_nominal = cv2.getPerspectiveTransform(
        NOMINAL,
        np.array(OBSERVED[name], dtype=np.float32),
    )
    return cv2.perspectiveTransform(
        np.array(nominal_points, dtype=np.float32).reshape(1, -1, 2),
        paper_from_nominal,
    ).reshape(-1, 2)


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    header = HEADER.read_text(encoding="utf-8")
    selector = SELECTOR.read_text(encoding="utf-8")
    pin_config = PIN_CONFIG.read_text(encoding="utf-8")
    combined = source + header
    required_text = (
        "FIXED_LAYOUT_A4_GRID9_LOCALCAL_ONEFILE_V14",
        "AXIS_MARK_REGION_COUNT            (9u)",
        "order=R11_R12_R13_R23_R22_R21_R31_R32_R33",
        "transform=GRID9_LOCAL_PROJECTIVE_FROM_V13_PHOTO",
        "paper_x_starts_mm=25_95_165",
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
        raise AssertionError("V14 is not the selected writer task")
    if pin_config.count("DL_GPIO_RESISTOR_PULL_UP") != 2:
        raise AssertionError("both limit inputs must retain pull-ups")
    if source.count("App_Servo_Pen_Down();") != 1:
        raise AssertionError("unexpected pen-down implementation count")
    if source.count('"PEN_DOWN_SQUARE"') != 1:
        raise AssertionError("one reusable square operation is required")
    if source.count("AXIS_MARK_OP_MOVE_DRAW") != 6:
        raise AssertionError("exactly four reusable draw moves are required")
    if "M802 accepted" in source:
        raise AssertionError("one-file V14 must not require M802")
    if "s_state = FIXED_LAYOUT_AXIS_MARK_STATE_WAIT_DRAW" in source:
        raise AssertionError("one-file V14 must auto-start each square")

    checked: list[tuple[float, float]] = []
    all_vertices: list[tuple[float, float]] = []
    worst = (float("inf"), (0.0, 0.0), (0.0, 0.0, 0.0))
    max_prediction_error = 0.0

    for name, paper_start, cell_x, cell_y, vertices in REGIONS:
        shift = TARGET_PAPER_X_MM[name] - OBSERVED[name][0][0]
        derived = correct_region(
            ORIGINAL_COMMAND[name], OBSERVED[name], (shift, 0.0)
        )
        for actual, expected in zip(vertices, derived):
            if math.dist(actual, expected) > 0.02:
                raise AssertionError(
                    f"{name} source vertex differs from derivation: "
                    f"{actual} != {expected}"
                )
            source_token = f"{actual[0]:.3f}f"
            if source_token not in source:
                raise AssertionError(
                    f"{name} command token absent from source: {source_token}"
                )

        predicted = predict_paper(name, vertices)
        desired = np.array(
            (
                (paper_start[0], OBSERVED[name][0][1]),
                (paper_start[0] + 20.0, OBSERVED[name][0][1]),
                (paper_start[0] + 20.0, OBSERVED[name][0][1] + 20.0),
                (paper_start[0], OBSERVED[name][0][1] + 20.0),
            )
        )
        errors = np.linalg.norm(predicted - desired, axis=1)
        max_prediction_error = max(max_prediction_error, float(errors.max()))
        if errors.max() > 0.02:
            raise AssertionError(
                f"{name} predicted paper target error: {errors}"
            )
        center_x = paper_start[0] + 10.0
        center_y = OBSERVED[name][0][1] + 10.0
        if not (
            cell_x[0] <= center_x <= cell_x[1]
            and cell_y[0] <= center_y <= cell_y[1]
        ):
            raise AssertionError(f"{name} center is outside its A4 cell")

        closed = vertices + (vertices[0],)
        for start, end in zip(closed, closed[1:]):
            checked.extend(segment_samples(start, end))
        all_vertices.extend(vertices)

    for previous, current in zip(REGIONS, REGIONS[1:]):
        checked.extend(segment_samples(previous[4][0], current[4][0]))

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
        "fixed_layout_a4_grid9_localcal_onefile_v14=PASS "
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
        f"photo_model_max_target_error={max_prediction_error:.6f}mm "
        "paper_x_starts=25,95,165 square=20x20"
    )


if __name__ == "__main__":
    main()
