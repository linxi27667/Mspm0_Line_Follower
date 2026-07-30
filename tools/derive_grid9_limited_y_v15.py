"""Fit the V13 photo data and derive a grid inside paper Y=20..130 mm."""

from __future__ import annotations

import math

import numpy as np

from check_fixed_layout_a4_grid9_localcal_onefile_v14 import OBSERVED
from derive_grid9_local_correction_v14 import ORIGINAL_COMMAND


REGION_ORDER = (
    "R11", "R12", "R13", "R23", "R22", "R21", "R31", "R32", "R33"
)
TARGET_START = {
    "R11": (25.0, 100.0),
    "R12": (95.0, 100.0),
    "R13": (165.0, 100.0),
    "R23": (165.0, 65.0),
    "R22": (95.0, 65.0),
    "R21": (25.0, 65.0),
    "R31": (25.0, 30.0),
    "R32": (95.0, 30.0),
    "R33": (165.0, 30.0),
}


def normalized(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return (points[:, 0] - 105.0) / 100.0, (
        points[:, 1] - 130.0
    ) / 100.0


def basis(points: np.ndarray, degree: int) -> np.ndarray:
    x, y = normalized(points)
    columns = (
        np.ones_like(x),
        x,
        y,
        x * x,
        x * y,
        y * y,
    )
    if degree == 2:
        return np.column_stack(columns)
    if degree == 3:
        return np.column_stack(
            columns
            + (
                x * x * x,
                x * x * y,
                x * y * y,
                y * y * y,
            )
        )
    raise ValueError(degree)


def fit(
    input_points: np.ndarray, output_points: np.ndarray, degree: int
) -> np.ndarray:
    coefficients, _, _, _ = np.linalg.lstsq(
        basis(input_points, degree), output_points, rcond=None
    )
    return coefficients


def evaluate(
    input_points: np.ndarray, coefficients: np.ndarray, degree: int
) -> np.ndarray:
    return basis(input_points, degree) @ coefficients


def calibration_arrays() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    paper_points = []
    command_points = []
    region_indices = []
    for region_index, name in enumerate(REGION_ORDER):
        paper_points.extend(OBSERVED[name])
        command_points.extend(ORIGINAL_COMMAND[name])
        region_indices.extend([region_index] * 4)
    return (
        np.array(paper_points, dtype=float),
        np.array(command_points, dtype=float),
        np.array(region_indices, dtype=int),
    )


def model_diagnostics(degree: int) -> None:
    paper, command, region_indices = calibration_arrays()
    inverse_model = fit(paper, command, degree)
    forward_model = fit(command, paper, degree)
    command_residual = np.linalg.norm(
        evaluate(paper, inverse_model, degree) - command, axis=1
    )
    paper_residual = np.linalg.norm(
        evaluate(command, forward_model, degree) - paper, axis=1
    )
    holdout_errors = []
    for region_index in range(len(REGION_ORDER)):
        train = region_indices != region_index
        test = ~train
        holdout_model = fit(paper[train], command[train], degree)
        holdout_errors.extend(
            np.linalg.norm(
                evaluate(paper[test], holdout_model, degree) - command[test],
                axis=1,
            )
        )
    print(
        f"degree={degree} command_fit_rmse="
        f"{math.sqrt(float(np.mean(command_residual ** 2))):.3f} "
        f"command_fit_max={command_residual.max():.3f} "
        f"paper_fit_rmse="
        f"{math.sqrt(float(np.mean(paper_residual ** 2))):.3f} "
        f"paper_fit_max={paper_residual.max():.3f} "
        f"leave_region_out_command_rmse="
        f"{math.sqrt(float(np.mean(np.array(holdout_errors) ** 2))):.3f}"
    )


def derive(degree: int = 2) -> dict[str, tuple[tuple[float, float], ...]]:
    paper, command, _ = calibration_arrays()
    inverse_model = fit(paper, command, degree)
    result = {}
    for name in REGION_ORDER:
        x0, y0 = TARGET_START[name]
        target = np.array(
            (
                (x0, y0),
                (x0 + 20.0, y0),
                (x0 + 20.0, y0 + 20.0),
                (x0, y0 + 20.0),
            )
        )
        command_vertices = evaluate(target, inverse_model, degree)
        result[name] = tuple(
            tuple(float(value) for value in point)
            for point in command_vertices
        )
    return result


def main() -> None:
    model_diagnostics(2)
    model_diagnostics(3)
    corrected = derive(2)
    for name in REGION_ORDER:
        print(
            f'{name} = {{{{'
            + "}, {".join(
                f"{point[0]:.3f}f, {point[1]:.3f}f"
                for point in corrected[name]
            )
            + "}}"
        )


if __name__ == "__main__":
    main()
