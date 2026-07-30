"""Derive per-region V14 command vertices from the photographed V13 result."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import cv2
import numpy as np

from analyze_grid9_photo_v13 import (
    REGION_ORDER,
    detect_region,
    rectify,
)


ORIGINAL_COMMAND = {
    "R11": ((169.467, -17.495), (182.943, 4.904),
            (166.276, 17.176), (152.799, -5.223)),
    "R12": ((206.527, 44.103), (220.004, 66.502),
            (203.336, 78.774), (189.859, 56.375)),
    "R13": ((243.588, 105.700), (257.064, 128.099),
            (240.396, 140.371), (226.920, 117.972)),
    "R23": ((309.425, 57.226), (322.901, 79.625),
            (306.234, 91.897), (292.757, 69.498)),
    "R22": ((272.364, -4.372), (285.841, 18.027),
            (269.173, 30.299), (255.697, 7.900)),
    "R21": ((235.304, -65.969), (248.780, -43.570),
            (232.113, -31.298), (218.636, -53.697)),
    "R31": ((285.307, -102.784), (298.783, -80.385),
            (282.116, -68.114), (268.639, -90.513)),
    "R32": ((322.367, -41.187), (335.844, -18.788),
            (319.176, -6.516), (305.700, -28.915)),
    "R33": ((359.428, 20.410), (372.904, 42.809),
            (356.236, 55.081), (342.760, 32.682)),
}

NOMINAL = np.array(
    ((0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)),
    dtype=np.float32,
)

TARGET_PAPER_X_MM = {
    "R11": 25.0,
    "R21": 25.0,
    "R31": 25.0,
    "R12": 95.0,
    "R22": 95.0,
    "R32": 95.0,
    "R13": 165.0,
    "R23": 165.0,
    "R33": 165.0,
}


def synthetic_r31(
    clipped: tuple[tuple[float, float], ...]
) -> tuple[tuple[float, float], ...]:
    """Reconstruct R31's clipped left side from its two visible outer sides."""
    _, lower_right, upper_right, _ = clipped
    # Average visible horizontal response. The original left side fell just
    # outside the sheet, so the paper edge must not be treated as an ink side.
    paper_x_response = np.array((22.4, 3.185), dtype=float)
    p1 = np.array(lower_right)
    p2 = np.array(upper_right)
    p0 = p1 - paper_x_response
    p3 = p2 - paper_x_response
    return tuple(tuple(float(value) for value in point)
                 for point in (p0, p1, p2, p3))


def correct_region(
    command: tuple[tuple[float, float], ...],
    observed: tuple[tuple[float, float], ...],
    anchor_shift: tuple[float, float] = (0.0, 0.0),
) -> tuple[tuple[float, float], ...]:
    observed_array = np.array(observed, dtype=np.float32)
    paper_from_nominal = cv2.getPerspectiveTransform(
        NOMINAL, observed_array
    )
    nominal_from_paper = np.linalg.inv(paper_from_nominal)

    anchor = observed_array[0] + np.array(anchor_shift, dtype=np.float32)
    desired_paper = np.array(
        (
            anchor,
            anchor + (20.0, 0.0),
            anchor + (20.0, 20.0),
            anchor + (0.0, 20.0),
        ),
        dtype=np.float32,
    )
    corrected_nominal = cv2.perspectiveTransform(
        desired_paper.reshape(1, -1, 2),
        nominal_from_paper,
    ).reshape(-1, 2)

    command_array = np.array(command, dtype=float)
    command_x_per_mm = (command_array[1] - command_array[0]) / 20.0
    command_y_per_mm = (command_array[3] - command_array[0]) / 20.0
    corrected_command = (
        command_array[0]
        + corrected_nominal[:, 0, None] * command_x_per_mm
        + corrected_nominal[:, 1, None] * command_y_per_mm
    )
    return tuple(
        tuple(float(value) for value in point)
        for point in corrected_command
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("photo", type=Path)
    args = parser.parse_args()
    image = cv2.imread(str(args.photo))
    if image is None:
        raise FileNotFoundError(args.photo)
    rectified, _ = rectify(image)
    observed = {
        name: detect_region(rectified, name) for name in REGION_ORDER
    }
    observed["R31"] = synthetic_r31(observed["R31"])

    corrected = {}
    for name in REGION_ORDER:
        shift = (
            TARGET_PAPER_X_MM[name] - observed[name][0][0],
            0.0,
        )
        corrected[name] = correct_region(
            ORIGINAL_COMMAND[name], observed[name], shift
        )

    for name in REGION_ORDER:
        print(
            f'{name} = {{{{'
            + "}, {".join(
                f"{point[0]:.3f}f, {point[1]:.3f}f"
                for point in corrected[name]
            )
            + "}}"
        )
        changes = [
            math.dist(old, new)
            for old, new in zip(
                ORIGINAL_COMMAND[name], corrected[name]
            )
        ]
        print(
            f"{name} command_vertex_changes_mm="
            + ",".join(f"{change:.3f}" for change in changes)
        )


if __name__ == "__main__":
    main()
