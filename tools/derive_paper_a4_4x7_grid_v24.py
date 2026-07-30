"""Derive the V24 4x7 user-coordinate correction table from 28 dots."""

from __future__ import annotations

import math

import numpy as np

from derive_grid9_limited_y_v15 import (
    calibration_arrays,
    evaluate,
    fit,
)


GRID_X = np.array((25.0, 78.333, 131.667, 185.0), dtype=float)
GRID_Y = np.array(
    (20.0, 56.667, 93.333, 130.0, 167.0, 203.667, 240.333),
    dtype=float,
)
MEASURED = np.array(
    (
        ((25.0, 42.0), (84.0, 42.0), (140.0, 40.0), (193.0, 40.0)),
        ((26.8, 75.0), (84.2, 77.7), (138.5, 77.0), (189.0, 76.2)),
        ((26.3, 111.0), (72.3, 113.0), (132.0, 114.0), (183.5, 113.0)),
        ((29.0, 149.0), (81.0, 151.0), (133.7, 152.0), (183.5, 151.0)),
        ((28.4, 187.5), (71.0, 185.5), (130.2, 186.7), (182.0, 188.0)),
        ((27.0, 226.0), (80.0, 224.0), (133.7, 224.3), (183.5, 223.9)),
        ((20.5, 255.0), (77.5, 255.0), (133.5, 257.0), (180.6, 260.0)),
    ),
    dtype=float,
)


def bilerp(corners: np.ndarray, u: float, v: float) -> np.ndarray:
    q00, q10, q01, q11 = corners
    return (
        (1.0 - u) * (1.0 - v) * q00
        + u * (1.0 - v) * q10
        + (1.0 - u) * v * q01
        + u * v * q11
    )


def solve_bilinear(
    corners: np.ndarray, target: np.ndarray
) -> tuple[float, float, float]:
    u = 0.5
    v = 0.5
    for _ in range(30):
        value = bilerp(corners, u, v)
        residual = value - target
        q00, q10, q01, q11 = corners
        du = (1.0 - v) * (q10 - q00) + v * (q11 - q01)
        dv = (1.0 - u) * (q01 - q00) + u * (q11 - q10)
        jacobian = np.column_stack((du, dv))
        step = np.linalg.solve(jacobian, residual)
        u -= float(step[0])
        v -= float(step[1])
        if np.linalg.norm(step) < 1.0e-11:
            break
    error = float(np.linalg.norm(bilerp(corners, u, v) - target))
    return u, v, error


def outside(value: float) -> float:
    return max(0.0, -value, value - 1.0)


def inverse_measured_grid(target: np.ndarray) -> np.ndarray:
    candidates = []
    x_step = float(GRID_X[1] - GRID_X[0])
    y_step = float(GRID_Y[1] - GRID_Y[0])
    for row in range(len(GRID_Y) - 1):
        for column in range(len(GRID_X) - 1):
            corners = np.array(
                (
                    MEASURED[row, column],
                    MEASURED[row, column + 1],
                    MEASURED[row + 1, column],
                    MEASURED[row + 1, column + 1],
                )
            )
            u, v, residual = solve_bilinear(corners, target)
            penalty = outside(u) ** 2 + outside(v) ** 2
            center = np.array(
                (
                    (GRID_X[column] + GRID_X[column + 1]) / 2.0,
                    (GRID_Y[row] + GRID_Y[row + 1]) / 2.0,
                )
            )
            proximity = float(np.linalg.norm(
                (center - target) / np.array((x_step, y_step))
            ))
            score = penalty * 100.0 + residual * 1000.0 + proximity * 0.001
            candidates.append((score, row, column, u, v, residual))

    _, row, column, u, v, residual = min(candidates)
    if residual > 1.0e-6:
        raise AssertionError(
            f"inverse residual {residual:.9f} mm at {target}"
        )
    return np.array(
        (
            GRID_X[column] + u * (
                GRID_X[column + 1] - GRID_X[column]
            ),
            GRID_Y[row] + v * (
                GRID_Y[row + 1] - GRID_Y[row]
            ),
        )
    )


def derive() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    targets = np.array(
        [[(x, y) for x in GRID_X] for y in GRID_Y],
        dtype=float,
    )
    corrected_paper = np.empty_like(targets)
    for row in range(len(GRID_Y)):
        for column in range(len(GRID_X)):
            corrected_paper[row, column] = inverse_measured_grid(
                targets[row, column]
            )

    paper_calibration, command_calibration, _ = calibration_arrays()
    paper_to_user = fit(paper_calibration, command_calibration, 2)
    base_user = evaluate(
        targets.reshape(-1, 2), paper_to_user, 2
    ).reshape(targets.shape)
    corrected_user = evaluate(
        corrected_paper.reshape(-1, 2), paper_to_user, 2
    ).reshape(targets.shape)
    return corrected_paper, corrected_user, corrected_user - base_user


def main() -> None:
    corrected_paper, corrected_user, user_delta = derive()
    measured_error = MEASURED - np.array(
        [[(x, y) for x in GRID_X] for y in GRID_Y]
    )
    print(
        "measured_error_x="
        f"{measured_error[:, :, 0].min():.3f}.."
        f"{measured_error[:, :, 0].max():.3f}mm "
        "measured_error_y="
        f"{measured_error[:, :, 1].min():.3f}.."
        f"{measured_error[:, :, 1].max():.3f}mm"
    )
    print(
        "corrected_paper_bounds_x="
        f"{corrected_paper[:, :, 0].min():.3f}.."
        f"{corrected_paper[:, :, 0].max():.3f} "
        "corrected_paper_bounds_y="
        f"{corrected_paper[:, :, 1].min():.3f}.."
        f"{corrected_paper[:, :, 1].max():.3f}"
    )
    print(
        "corrected_user_bounds_x="
        f"{corrected_user[:, :, 0].min():.3f}.."
        f"{corrected_user[:, :, 0].max():.3f} "
        "corrected_user_bounds_y="
        f"{corrected_user[:, :, 1].min():.3f}.."
        f"{corrected_user[:, :, 1].max():.3f}"
    )
    for axis, name in ((0, "s_grid_dx"), (1, "s_grid_dy")):
        print(f"{name} = {{")
        for row in user_delta[:, :, axis]:
            print(
                "    {" + ", ".join(
                    f"{value:.6f}f" for value in row
                ) + "},"
            )
        print("};")
    max_inverse_error = 0.0
    for row, y in enumerate(GRID_Y):
        for column, x in enumerate(GRID_X):
            nominal = corrected_paper[row, column]
            cell_target = np.array((x, y))
            recovered = inverse_measured_grid(cell_target)
            max_inverse_error = max(
                max_inverse_error,
                float(np.linalg.norm(recovered - nominal)),
            )
    print(
        f"inverse_repeat_error_max={max_inverse_error:.9f}mm "
        f"nodes={len(GRID_X) * len(GRID_Y)}"
    )


if __name__ == "__main__":
    main()
