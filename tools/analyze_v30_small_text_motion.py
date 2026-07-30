#!/usr/bin/env python3
"""Quantify firmware-side distortion for the V66 6 mm text test.

This deliberately separates three effects:

1. the measured S-bow prewarp added by V30;
2. absolute joint-step rounding at every requested path vertex;
3. joint-direction reversals that the continuous queue currently crosses
   without junction-aware deceleration.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from check_firmware_right_sbow_v30 import firmware_map, firmware_prewarp
from check_workspace_yshift15_v28 import (
    L1_MM,
    L2_MM,
    OFFSET_X_MM,
    OFFSET_Y_MM,
    inverse_user,
)


GCODE_PATH = (
    ROOT
    / "gcode"
    / "PAPER_A4_STANDARD_UPPER_4FONT_6MM_WRITER_TEST_TIMESTAMP_GCODE_V66.gcode"
)
REPORT_PATH = (
    ROOT
    / "docs"
    / "diagnostics"
    / "V30_V66_SMALL_TEXT_MOTION_AUDIT_20260725.json"
)

STAGE1_STEPS_PER_DEG = 40.099216
STAGE2_STEPS_PER_DEG = 40.115790
FINITE_DIFFERENCE_MM = 0.01
MOTION_RE = re.compile(
    r"^G(?P<mode>[01])\s+X(?P<x>-?\d+(?:\.\d+)?)"
    r"\s+Y(?P<y>-?\d+(?:\.\d+)?)$"
)


def lroundf(value: float) -> int:
    """Match C lroundf for the positive joint angles used by this robot."""
    return math.floor(value + 0.5) if value >= 0.0 else math.ceil(value - 0.5)


def forward_user(theta_deg: float, psi_deg: float) -> tuple[float, float]:
    theta = math.radians(theta_deg)
    psi = math.radians(psi_deg)
    machine_x = -L1_MM * math.cos(theta) - L2_MM * math.cos(psi)
    machine_y = L1_MM * math.sin(theta) + L2_MM * math.sin(psi)
    return machine_x - OFFSET_X_MM, machine_y - OFFSET_Y_MM


def quantized_user(paper: tuple[float, float]) -> tuple[float, float]:
    user = firmware_map(paper)
    theta, psi, _ = inverse_user(*user)
    stage1 = lroundf(theta * STAGE1_STEPS_PER_DEG)
    stage2 = lroundf(psi * STAGE2_STEPS_PER_DEG)
    return forward_user(
        stage1 / STAGE1_STEPS_PER_DEG,
        stage2 / STAGE2_STEPS_PER_DEG,
    )


def map_jacobian(paper: tuple[float, float]) -> tuple[tuple[float, float], ...]:
    h = FINITE_DIFFERENCE_MM
    x_plus = firmware_map((paper[0] + h, paper[1]))
    x_minus = firmware_map((paper[0] - h, paper[1]))
    y_plus = firmware_map((paper[0], paper[1] + h))
    y_minus = firmware_map((paper[0], paper[1] - h))
    return (
        (
            (x_plus[0] - x_minus[0]) / (2.0 * h),
            (y_plus[0] - y_minus[0]) / (2.0 * h),
        ),
        (
            (x_plus[1] - x_minus[1]) / (2.0 * h),
            (y_plus[1] - y_minus[1]) / (2.0 * h),
        ),
    )


def paper_delta_from_user_delta(
    paper: tuple[float, float],
    user_delta: tuple[float, float],
) -> tuple[float, float]:
    jacobian = map_jacobian(paper)
    a, b = jacobian[0]
    c, d = jacobian[1]
    determinant = a * d - b * c
    if abs(determinant) < 1.0e-9:
        raise AssertionError(f"singular paper map near {paper}")
    return (
        (d * user_delta[0] - b * user_delta[1]) / determinant,
        (-c * user_delta[0] + a * user_delta[1]) / determinant,
    )


def quantization_error_paper(
    paper: tuple[float, float],
) -> tuple[float, float]:
    nominal = firmware_map(paper)
    actual = quantized_user(paper)
    return paper_delta_from_user_delta(
        paper,
        (actual[0] - nominal[0], actual[1] - nominal[1]),
    )


def joint_steps(paper: tuple[float, float]) -> tuple[int, int]:
    theta, psi, _ = inverse_user(*firmware_map(paper))
    return (
        lroundf(theta * STAGE1_STEPS_PER_DEG),
        lroundf(psi * STAGE2_STEPS_PER_DEG),
    )


def parse_pen_down_paths() -> tuple[tuple[tuple[float, float], ...], ...]:
    paths: list[tuple[tuple[float, float], ...]] = []
    current: list[tuple[float, float]] | None = None
    last_position: tuple[float, float] | None = None
    pen_down = False
    for raw in GCODE_PATH.read_text(encoding="ascii").splitlines():
        line = raw.split(";", 1)[0].strip()
        if not line:
            continue
        if line == "M3":
            if last_position is None:
                raise AssertionError("M3 without a source position")
            pen_down = True
            current = [last_position]
            continue
        if line == "M5":
            if pen_down and current is not None and len(current) >= 2:
                paths.append(tuple(current))
            pen_down = False
            current = None
            continue
        match = MOTION_RE.fullmatch(line)
        if match is None:
            continue
        point = (float(match.group("x")), float(match.group("y")))
        if pen_down:
            if int(match.group("mode")) != 1:
                raise AssertionError("G0 encountered with the pen down")
            assert current is not None
            current.append(point)
        last_position = point
    return tuple(paths)


def sign(value: int) -> int:
    return 1 if value > 0 else (-1 if value < 0 else 0)


def reversal_metrics(
    paths: tuple[tuple[tuple[float, float], ...], ...],
) -> dict[str, int]:
    vertices = 0
    zero_motion_segments = 0
    any_joint_reversals = 0
    both_joint_reversals = 0
    direction_changes = 0
    for path in paths:
        steps = [joint_steps(point) for point in path]
        previous_delta: tuple[int, int] | None = None
        for start, end in zip(steps, steps[1:]):
            delta = (end[0] - start[0], end[1] - start[1])
            vertices += 1
            if delta == (0, 0):
                zero_motion_segments += 1
                continue
            if previous_delta is not None:
                old = (sign(previous_delta[0]), sign(previous_delta[1]))
                new = (sign(delta[0]), sign(delta[1]))
                changed = (
                    (old[0] != 0 and new[0] != 0 and old[0] != new[0])
                    or (old[1] != 0 and new[1] != 0 and old[1] != new[1])
                )
                both = (
                    old[0] != 0
                    and new[0] != 0
                    and old[0] != new[0]
                    and old[1] != 0
                    and new[1] != 0
                    and old[1] != new[1]
                )
                if old != new:
                    direction_changes += 1
                if changed:
                    any_joint_reversals += 1
                if both:
                    both_joint_reversals += 1
            previous_delta = delta
    return {
        "pen_down_segments": vertices,
        "zero_step_segments": zero_motion_segments,
        "joint_direction_changes": direction_changes,
        "junctions_with_any_joint_reversal": any_joint_reversals,
        "junctions_with_both_joint_reversal": both_joint_reversals,
    }


def quantization_metrics(
    paths: tuple[tuple[tuple[float, float], ...], ...],
) -> dict[str, object]:
    errors: list[tuple[float, float, float, tuple[float, float]]] = []
    for path in paths:
        for point in path:
            dx, dy = quantization_error_paper(point)
            errors.append((dx, dy, math.hypot(dx, dy), point))
    worst = max(errors, key=lambda item: item[2])
    return {
        "sample_count": len(errors),
        "rms_mm": math.sqrt(
            sum(item[2] * item[2] for item in errors) / len(errors)
        ),
        "max_mm": worst[2],
        "max_at_paper_mm": list(worst[3]),
        "max_error_xy_mm": [worst[0], worst[1]],
        "axis_abs_max_mm": [
            max(abs(item[0]) for item in errors),
            max(abs(item[1]) for item in errors),
        ],
    }


def prewarp_local_metrics() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for x in (30.0, 60.0, 90.0, 120.0, 150.0):
        for y in (227.0, 213.0):
            h0 = firmware_prewarp((x - 3.0, y))
            h1 = firmware_prewarp((x + 3.0, y))
            v0 = firmware_prewarp((x, y - 3.0))
            v1 = firmware_prewarp((x, y + 3.0))
            horizontal = (h1[0] - h0[0], h1[1] - h0[1])
            vertical = (v1[0] - v0[0], v1[1] - v0[1])
            records.append(
                {
                    "center_paper_mm": [x, y],
                    "prewarped_6mm_horizontal_delta_mm": list(horizontal),
                    "horizontal_tilt_deg": math.degrees(
                        math.atan2(horizontal[1], horizontal[0])
                    ),
                    "prewarped_6mm_vertical_delta_mm": list(vertical),
                    "vertical_from_up_deg": math.degrees(
                        math.atan2(vertical[0], vertical[1])
                    ),
                }
            )
    return records


def main() -> None:
    paths = parse_pen_down_paths()
    report = {
        "test": "V30 firmware with V66 6 mm four-font path",
        "gcode": str(GCODE_PATH),
        "finding_scope": (
            "Static mapping and quantization are computed exactly enough for "
            "diagnosis; mechanical backlash and inertia require a physical test."
        ),
        "path_count": len(paths),
        "prewarp_local": prewarp_local_metrics(),
        "quantization": quantization_metrics(paths),
        "continuous_queue": {
            **reversal_metrics(paths),
            "junction_aware_deceleration_present": False,
            "direction_compensation_enabled": False,
        },
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    quantization = report["quantization"]
    queue = report["continuous_queue"]
    tilts = [
        abs(record["horizontal_tilt_deg"])
        for record in report["prewarp_local"]
    ]
    print(
        "v30_v66_small_text_audit=PASS "
        f"paths={len(paths)} "
        f"quant_rms={quantization['rms_mm']:.4f}mm "
        f"quant_max={quantization['max_mm']:.4f}mm "
        f"prewarp_h_tilt_max={max(tilts):.3f}deg "
        f"joint_reversal_junctions="
        f"{queue['junctions_with_any_joint_reversal']} "
        "junction_decel=OFF dircomp=OFF"
    )
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
