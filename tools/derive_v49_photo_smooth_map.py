#!/usr/bin/env python3
"""Fit a smooth inverse paper correction from the V49 photo corners."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = (
    ROOT
    / "docs"
    / "diagnostics"
    / "V49_BASEONLY_DIRECTION_PHOTO_ANALYSIS.json"
)
PHOTO = (
    ROOT
    / "docs"
    / "diagnostics"
    / "V49_BASEONLY_DIRECTION_PHOTO_20260725.jpg"
)
OUTPUT = (
    ROOT
    / "docs"
    / "diagnostics"
    / "V49_PHOTO_SMOOTH_INVERSE_MAP_V1.json"
)
MAP_ID = "V49_PHOTO_SMOOTH_INVERSE_QUADRATIC_V1"
PX_PER_MM = 5.0
A4_HEIGHT_MM = 297.0
RECT_HALF_WIDTH_MM = 12.0
RECT_HALF_HEIGHT_MM = 4.0


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def basis(points: np.ndarray) -> np.ndarray:
    nx = (points[:, 0] - 105.0) / 100.0
    ny = (points[:, 1] - 130.0) / 100.0
    return np.column_stack(
        (
            np.ones(len(points)),
            nx,
            ny,
            nx * nx,
            nx * ny,
            ny * ny,
        )
    )


def load_samples() -> tuple[np.ndarray, np.ndarray, list[dict]]:
    analysis = json.loads(ANALYSIS.read_text(encoding="utf-8"))
    physical = []
    commanded = []
    metadata = []
    for rectangle in analysis["rectangles"]:
        center_x, center_y = rectangle["center_paper_mm"]
        intended = {
            "top_left": (
                center_x - RECT_HALF_WIDTH_MM,
                center_y + RECT_HALF_HEIGHT_MM,
            ),
            "top_right": (
                center_x + RECT_HALF_WIDTH_MM,
                center_y + RECT_HALF_HEIGHT_MM,
            ),
            "bottom_right": (
                center_x + RECT_HALF_WIDTH_MM,
                center_y - RECT_HALF_HEIGHT_MM,
            ),
            "bottom_left": (
                center_x - RECT_HALF_WIDTH_MM,
                center_y - RECT_HALF_HEIGHT_MM,
            ),
        }
        for corner_name, commanded_point in intended.items():
            pixel_x, pixel_y = rectangle["corners_rectified_px"][
                corner_name
            ]
            physical_point = (
                pixel_x / PX_PER_MM,
                A4_HEIGHT_MM - pixel_y / PX_PER_MM,
            )
            physical.append(physical_point)
            commanded.append(commanded_point)
            metadata.append(
                {
                    "zone": rectangle["zone"],
                    "slot": rectangle["vertical_slot"],
                    "direction": rectangle["direction"],
                    "corner": corner_name,
                    "physical_paper_mm": list(physical_point),
                    "base_source_paper_mm": list(commanded_point),
                }
            )
    return (
        np.asarray(physical, dtype=float),
        np.asarray(commanded, dtype=float),
        metadata,
    )


def fit_smooth_inverse() -> tuple[np.ndarray, dict, list[dict]]:
    physical, commanded, metadata = load_samples()
    design = basis(physical)
    weights = np.ones(len(physical), dtype=float)
    coefficients = np.zeros((6, 2), dtype=float)
    robust_scale = 0.0
    for _ in range(12):
        root_weight = np.sqrt(weights)[:, None]
        coefficients = np.linalg.lstsq(
            design * root_weight,
            commanded * root_weight,
            rcond=None,
        )[0]
        error = np.linalg.norm(design @ coefficients - commanded, axis=1)
        median = float(np.median(error))
        robust_scale = max(
            0.2,
            1.4826 * float(np.median(np.abs(error - median))),
        )
        weights = np.minimum(
            1.0,
            1.5 * robust_scale / np.maximum(error, 1.0e-9),
        )
    prediction = design @ coefficients
    error_vectors = prediction - commanded
    errors = np.linalg.norm(error_vectors, axis=1)
    for item, prediction_point, error_vector, error in zip(
        metadata, prediction, error_vectors, errors
    ):
        item["fitted_base_source_paper_mm"] = [
            float(value) for value in prediction_point
        ]
        item["residual_vector_mm"] = [
            float(value) for value in error_vector
        ]
        item["residual_mm"] = float(error)
    metrics = {
        "sample_count": len(physical),
        "mean_residual_mm": float(np.mean(errors)),
        "rms_residual_mm": float(np.sqrt(np.mean(errors * errors))),
        "p95_residual_mm": float(np.percentile(errors, 95.0)),
        "max_residual_mm": float(np.max(errors)),
        "robust_scale_mm": robust_scale,
        "physical_domain_mm": {
            "x": [
                float(np.min(physical[:, 0])),
                float(np.max(physical[:, 0])),
            ],
            "y": [
                float(np.min(physical[:, 1])),
                float(np.max(physical[:, 1])),
            ],
        },
    }
    return coefficients, metrics, metadata


def evaluate(
    point: tuple[float, float],
    coefficients: np.ndarray,
) -> tuple[float, float]:
    result = basis(np.asarray((point,), dtype=float))[0] @ coefficients
    return float(result[0]), float(result[1])


def main() -> None:
    coefficients, metrics, samples = fit_smooth_inverse()
    output = {
        "id": MAP_ID,
        "purpose": (
            "smooth desired-physical-paper to base-source-paper correction; "
            "the old 4x7 residual is not used"
        ),
        "source": {
            "photo": str(PHOTO),
            "photo_sha256": digest(PHOTO),
            "analysis": str(ANALYSIS),
            "analysis_sha256": digest(ANALYSIS),
        },
        "normalization": {
            "nx": "(paper_x - 105) / 100",
            "ny": "(paper_y - 130) / 100",
            "basis": ["1", "nx", "ny", "nx^2", "nx*ny", "ny^2"],
        },
        "coefficients": {
            "adjusted_base_source_x": [
                float(value) for value in coefficients[:, 0]
            ],
            "adjusted_base_source_y": [
                float(value) for value in coefficients[:, 1]
            ],
        },
        "fit": metrics,
        "known_limit": (
            "Pen-down CW/CCW compliance remains in the residual. The robust "
            "fit averages both directions and must be verified by V51."
        ),
        "samples": samples,
    }
    OUTPUT.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"derive_v49_photo_smooth_map=PASS id={MAP_ID} "
        f"samples={metrics['sample_count']} "
        f"rms={metrics['rms_residual_mm']:.3f}mm "
        f"p95={metrics['p95_residual_mm']:.3f}mm "
        f"max={metrics['max_residual_mm']:.3f}mm"
    )
    print("coeff_x", coefficients[:, 0].tolist())
    print("coeff_y", coefficients[:, 1].tolist())
    print(OUTPUT)


if __name__ == "__main__":
    main()
