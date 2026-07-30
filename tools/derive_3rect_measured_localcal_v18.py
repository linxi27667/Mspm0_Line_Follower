"""Derive V18 commands from the twelve manually measured V17 vertices."""

from __future__ import annotations

import math

import numpy as np

from derive_grid9_limited_y_v15 import (
    calibration_arrays,
    evaluate,
    fit,
)


REGIONS = (
    (
        "Y20",
        np.array(
            ((95.0, 20.0), (115.0, 20.0),
             (115.0, 40.0), (95.0, 40.0)),
            dtype=float,
        ),
        np.array(
            ((104.0, 46.0), (123.5, 46.0),
             (123.0, 62.0), (104.0, 64.5)),
            dtype=float,
        ),
    ),
    (
        "Y65",
        np.array(
            ((95.0, 65.0), (115.0, 65.0),
             (115.0, 85.0), (95.0, 85.0)),
            dtype=float,
        ),
        np.array(
            ((100.0, 90.0), (117.0, 90.2),
             (116.0, 109.5), (98.5, 110.0)),
            dtype=float,
        ),
    ),
    (
        "Y110",
        np.array(
            ((95.0, 110.0), (115.0, 110.0),
             (115.0, 130.0), (95.0, 130.0)),
            dtype=float,
        ),
        np.array(
            ((96.0, 135.0), (113.0, 135.0),
             (113.0, 155.0), (91.0, 155.0)),
            dtype=float,
        ),
    ),
)


def corrected_paper_vertices(
    target: np.ndarray, observed: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Invert a per-region affine paper response at the desired vertices."""
    local = target - target[0]
    design = np.column_stack((local, np.ones(4)))
    local_to_observed, _, _, _ = np.linalg.lstsq(
        design, observed, rcond=None
    )
    homogeneous = np.vstack(
        (local_to_observed.T, np.array((0.0, 0.0, 1.0)))
    )
    observed_fit = design @ local_to_observed
    desired_homogeneous = np.column_stack(
        (target, np.ones(4))
    )
    corrected_local = (
        desired_homogeneous @ np.linalg.inv(homogeneous).T
    )[:, :2]
    return corrected_local + target[0], observed_fit


def derive() -> dict[str, dict[str, np.ndarray]]:
    paper_calibration, command_calibration, _ = calibration_arrays()
    paper_to_command = fit(
        paper_calibration, command_calibration, 2
    )
    result: dict[str, dict[str, np.ndarray]] = {}
    for name, target, observed in REGIONS:
        corrected_paper, observed_fit = corrected_paper_vertices(
            target, observed
        )
        command = evaluate(corrected_paper, paper_to_command, 2)
        result[name] = {
            "target": target,
            "observed": observed,
            "observed_fit": observed_fit,
            "corrected_paper": corrected_paper,
            "command": command,
        }
    return result


def main() -> None:
    result = derive()
    for name, _, _ in REGIONS:
        region = result[name]
        residuals = np.linalg.norm(
            region["observed_fit"] - region["observed"], axis=1
        )
        print(
            f"{name} affine_observation_rmse="
            f"{math.sqrt(float(np.mean(residuals ** 2))):.3f}mm "
            f"max={float(residuals.max()):.3f}mm"
        )
        print(
            f"{name} corrected_paper="
            + ",".join(
                f"({point[0]:.3f},{point[1]:.3f})"
                for point in region["corrected_paper"]
            )
        )
        print(
            f'{name} = {{{{'
            + "}, {".join(
                f"{point[0]:.3f}f, {point[1]:.3f}f"
                for point in region["command"]
            )
            + "}}"
        )


if __name__ == "__main__":
    main()
