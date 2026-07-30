"""Derive V25 total corrections from the 28-point V24 verification pass."""

from __future__ import annotations

import numpy as np

from derive_grid9_limited_y_v15 import (
    calibration_arrays,
    evaluate,
    fit,
)
from derive_paper_a4_4x7_grid_v24 import (
    GRID_X,
    GRID_Y,
    bilerp,
    derive as derive_v24,
    outside,
    solve_bilinear,
)


MEASURED_V24 = np.array(
    (
        ((27.3, 14.0), (80.5, 14.8), (133.0, 15.0), (186.0, 14.3)),
        ((25.0, 51.0), (78.5, 51.2), (131.5, 51.2), (184.0, 51.0)),
        ((22.7, 88.0), (70.9, 89.0), (122.5, 88.0), (181.5, 88.0)),
        ((24.0, 125.0), (81.5, 126.0), (131.9, 125.0), (184.0, 125.0)),
        ((23.0, 161.0), (71.0, 162.0), (127.5, 161.0), (181.6, 161.0)),
        ((23.6, 200.0), (81.0, 200.5), (131.0, 200.0), (182.3, 199.0)),
        ((20.1, 233.0), (75.0, 233.4), (128.0, 234.0), (185.0, 236.0)),
    ),
    dtype=float,
)


def inverse_grid(
    measured: np.ndarray, target: np.ndarray
) -> tuple[np.ndarray, tuple[int, int, float, float]]:
    candidates = []
    x_step = float(GRID_X[1] - GRID_X[0])
    y_step = float(GRID_Y[1] - GRID_Y[0])
    for row in range(len(GRID_Y) - 1):
        for column in range(len(GRID_X) - 1):
            corners = np.array(
                (
                    measured[row, column],
                    measured[row, column + 1],
                    measured[row + 1, column],
                    measured[row + 1, column + 1],
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
            candidates.append(
                (score, row, column, u, v, residual)
            )

    _, row, column, u, v, residual = min(candidates)
    if residual > 1.0e-6:
        raise AssertionError(
            f"inverse residual {residual:.9f} mm at {target}"
        )
    return (
        np.array(
            (
                GRID_X[column] + u * (
                    GRID_X[column + 1] - GRID_X[column]
                ),
                GRID_Y[row] + v * (
                    GRID_Y[row + 1] - GRID_Y[row]
                ),
            )
        ),
        (row, column, u, v),
    )


def interpolate_cell(
    grid: np.ndarray,
    row: int,
    column: int,
    u: float,
    v: float,
) -> np.ndarray:
    corners = np.array(
        (
            grid[row, column],
            grid[row, column + 1],
            grid[row + 1, column],
            grid[row + 1, column + 1],
        )
    )
    return bilerp(corners, float(u), float(v))


def derive() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    targets = np.array(
        [[(x, y) for x in GRID_X] for y in GRID_Y],
        dtype=float,
    )
    paper_calibration, command_calibration, _ = calibration_arrays()
    paper_to_user = fit(paper_calibration, command_calibration, 2)
    base_target_user = evaluate(
        targets.reshape(-1, 2), paper_to_user, 2
    ).reshape(targets.shape)
    _, v24_user, v24_delta = derive_v24()

    corrected_request = np.empty_like(targets)
    corrected_user = np.empty_like(targets)
    for row in range(len(GRID_Y)):
        for column in range(len(GRID_X)):
            request, cell = inverse_grid(
                MEASURED_V24, targets[row, column]
            )
            corrected_request[row, column] = request
            corrected_user[row, column] = interpolate_cell(
                v24_user,
                cell[0],
                cell[1],
                cell[2],
                cell[3],
            )
    total_delta = corrected_user - base_target_user
    return (
        corrected_request,
        corrected_user,
        total_delta,
        total_delta - v24_delta,
    )


def main() -> None:
    targets = np.array(
        [[(x, y) for x in GRID_X] for y in GRID_Y],
        dtype=float,
    )
    error = MEASURED_V24 - targets
    corrected_request, corrected_user, total_delta, increment = derive()
    print(
        "v24_error_x="
        f"{error[:, :, 0].min():.3f}.."
        f"{error[:, :, 0].max():.3f}mm "
        f"rmse={np.sqrt(np.mean(error[:, :, 0] ** 2)):.3f}mm "
        "v24_error_y="
        f"{error[:, :, 1].min():.3f}.."
        f"{error[:, :, 1].max():.3f}mm "
        f"rmse={np.sqrt(np.mean(error[:, :, 1] ** 2)):.3f}mm"
    )
    print(
        "corrected_request_bounds_x="
        f"{corrected_request[:, :, 0].min():.3f}.."
        f"{corrected_request[:, :, 0].max():.3f} "
        "corrected_request_bounds_y="
        f"{corrected_request[:, :, 1].min():.3f}.."
        f"{corrected_request[:, :, 1].max():.3f}"
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
        for row in total_delta[:, :, axis]:
            print(
                "    {" + ", ".join(
                    f"{value:.6f}f" for value in row
                ) + "},"
            )
        print("};")
    print(
        "increment_bounds_dx="
        f"{increment[:, :, 0].min():.3f}.."
        f"{increment[:, :, 0].max():.3f} "
        "increment_bounds_dy="
        f"{increment[:, :, 1].min():.3f}.."
        f"{increment[:, :, 1].max():.3f}"
    )


if __name__ == "__main__":
    main()
