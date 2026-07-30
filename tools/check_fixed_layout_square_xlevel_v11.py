"""Offline safety check for FIXED_LAYOUT_SQUARE_XLEVEL_20MM_V11."""

from __future__ import annotations

import math
from pathlib import Path


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

SQUARE = (
    (175.213, 72.006),
    (188.690, 94.405),
    (172.022, 106.677),
    (158.546, 84.278),
    (175.213, 72.006),
)
DRAW_PATHS = (SQUARE,)

V10_COMMAND_RIGHT = (11.742193759288054, 23.513874303600972)
V10_COMMAND_UP = (-16.66763755803068, 12.271934581794142)
V10_PAPER_RIGHT = (math.sqrt(20.0 * 20.0 - 2.0 * 2.0), 2.0)
V10_PAPER_UP = (0.0, 20.0)


def command_vector_to_paper(
    command_x: float, command_y: float
) -> tuple[float, float]:
    det = (
        V10_COMMAND_RIGHT[0] * V10_COMMAND_UP[1]
        - V10_COMMAND_UP[0] * V10_COMMAND_RIGHT[1]
    )
    right_weight = (
        command_x * V10_COMMAND_UP[1]
        - V10_COMMAND_UP[0] * command_y
    ) / det
    up_weight = (
        V10_COMMAND_RIGHT[0] * command_y
        - command_x * V10_COMMAND_RIGHT[1]
    ) / det
    return (
        right_weight * V10_PAPER_RIGHT[0]
        + up_weight * V10_PAPER_UP[0],
        right_weight * V10_PAPER_RIGHT[1]
        + up_weight * V10_PAPER_UP[1],
    )


def samples() -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    for path in DRAW_PATHS:
        for start, end in zip(path, path[1:]):
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            count = max(1, math.ceil(math.hypot(dx, dy)))
            for index in range(count + 1):
                ratio = index / count
                result.append(
                    (start[0] + dx * ratio, start[1] + dy * ratio)
                )
    return result


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
            f"unreachable user point ({user_x:.3f},{user_y:.3f})"
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


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    header = HEADER.read_text(encoding="utf-8")
    selector = SELECTOR.read_text(encoding="utf-8")
    pin_config = PIN_CONFIG.read_text(encoding="utf-8")

    required_text = (
        "FIXED_LAYOUT_SQUARE_XLEVEL_20MM_V11",
        "AXIS_MARK_ALIGN_X_MM             (175.213f)",
        "AXIS_MARK_ALIGN_Y_MM             (72.006f)",
        "AXIS_MARK_SQUARE_X_X_MM          (188.690f)",
        "AXIS_MARK_SQUARE_XY_X_MM         (172.022f)",
        "AXIS_MARK_SQUARE_Y_X_MM          (158.546f)",
        "square_mm=(20,20)",
        "paper_x=RIGHT",
        "paper_y=UP",
        "x_rise_fix_x100=200",
        "x_rise_corrected=1",
        "y_unchanged=1",
        "draw_order=RIGHT_UP_LEFT_DOWN",
        "closed=1",
    )
    combined = source + header
    for text in required_text:
        if text not in combined:
            raise AssertionError(f"contract text missing: {text}")
    if (
        "#define WRITER_TEST_MODE             "
        "WRITER_TEST_MODE_FIXED_LAYOUT_AXIS_MARK"
    ) not in selector:
        raise AssertionError("V11 is not the selected writer task")
    if pin_config.count("DL_GPIO_RESISTOR_PULL_UP") < 2:
        raise AssertionError("both limit inputs must retain pull-ups")
    if source.count("App_Servo_Pen_Down();") != 1:
        raise AssertionError("unexpected pen-down implementation count")

    if source.count('"PEN_DOWN_SQUARE"') != 1:
        raise AssertionError("V11 must contain one square pen-down operation")
    if source.count("AXIS_MARK_OP_MOVE_DRAW") != 6:
        raise AssertionError("V11 must contain exactly four draw operations")

    expected_sides = ((20.0, 0.0), (0.0, 20.0),
                      (-20.0, 0.0), (0.0, -20.0))
    paper_sides = []
    for start, end in zip(SQUARE, SQUARE[1:]):
        command_vector = (end[0] - start[0], end[1] - start[1])
        paper_vector = command_vector_to_paper(*command_vector)
        paper_sides.append(paper_vector)
    for index, (actual, expected) in enumerate(
        zip(paper_sides, expected_sides), start=1
    ):
        if math.dist(actual, expected) > 0.01:
            raise AssertionError(
                f"paper side {index} mismatch: {actual} != {expected}"
            )
    closure = math.dist(SQUARE[0], SQUARE[-1])
    if closure != 0.0:
        raise AssertionError(f"command square is not closed: {closure}")

    checked = samples()
    min_margin = (float("inf"), (0.0, 0.0), (0.0, 0.0, 0.0))
    for x_mm, y_mm in checked:
        if x_mm < 150.0:
            raise AssertionError(f"known X>=150 guard violated at {x_mm},{y_mm}")
        theta, psi, beta = inverse(x_mm, y_mm)
        margin = min(
            theta - THETA_MIN_DEG,
            THETA_MAX_DEG - theta,
            psi - PSI_MIN_DEG,
            PSI_MAX_DEG - psi,
            beta - BETA_MIN_DEG,
            BETA_MAX_DEG - beta,
        )
        if margin < min_margin[0]:
            min_margin = (margin, (x_mm, y_mm), (theta, psi, beta))

    if min_margin[0] < 5.0:
        raise AssertionError(
            f"joint margin too small: {min_margin[0]:.6f} deg "
            f"at {min_margin[1]}"
        )

    all_points = [point for path in DRAW_PATHS for point in path]
    xs = [point[0] for point in all_points]
    ys = [point[1] for point in all_points]
    print(
        "fixed_layout_square_xlevel_v11=PASS "
        f"samples={len(checked)} "
        f"command_bounds_x={min(xs):.3f}..{max(xs):.3f} "
        f"command_bounds_y={min(ys):.3f}..{max(ys):.3f}"
    )
    print(
        f"min_joint_margin={min_margin[0]:.6f}deg "
        f"at=({min_margin[1][0]:.3f},{min_margin[1][1]:.3f}) "
        f"theta={min_margin[2][0]:.3f} "
        f"psi={min_margin[2][1]:.3f} beta={min_margin[2][2]:.3f}"
    )
    print(
        "predicted_paper_sides="
        + ",".join(
            f"({side[0]:.6f},{side[1]:.6f})"
            for side in paper_sides
        )
        + f" closure_command={closure:.6f}mm"
    )


if __name__ == "__main__":
    main()
