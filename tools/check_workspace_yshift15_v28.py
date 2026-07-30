#!/usr/bin/env python3
"""Static and kinematic checks for the global +15 mm G-code workspace shift."""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from generate_paper_a4_3x3_baseonly_direction_v49 import map_base_only


HEADER = ROOT / "TASK" / "gcode_serial.h"
SERIAL = ROOT / "TASK" / "gcode_serial.c"
MOTION_HEADER = ROOT / "APP" / "Inc" / "app_writer_motion.h"
PIN_CONFIG = ROOT / "ti_msp_dl_config.c"

BUILD_ID = "PAPER_A4_CONTINUOUS_QUEUE_SAFE_HOME_YSHIFT15_GCODE_V28"
SHIFT_X_MM = 0.0
SHIFT_Y_MM = 15.0
PAPER_X_RANGE = (25.0, 185.0)
PAPER_Y_RANGE = (20.0, 240.333333)

L1_MM = 205.0
L2_MM = 203.0
OFFSET_X_MM = -129.0
OFFSET_Y_MM = 128.0
THETA_MIN_DEG = -0.773082 + 1.0
PSI_MIN_DEG = 134.177381 + 1.0
THETA_MAX_DEG = 135.0
PSI_MAX_DEG = 255.0
BETA_MIN_DEG = 1.0
BETA_MAX_DEG = 179.0

DEFINE_RE = re.compile(
    r"^\s*#define\s+(?P<name>[A-Z0-9_]+)\s+\((?P<value>-?\d+(?:\.\d+)?)f\)",
    re.MULTILINE,
)


def inverse_user(user_x: float, user_y: float) -> tuple[float, float, float]:
    machine_x = user_x + OFFSET_X_MM
    machine_y = user_y + OFFSET_Y_MM
    standard_x = -machine_x
    standard_y = machine_y
    cos_q2 = (
        standard_x * standard_x
        + standard_y * standard_y
        - L1_MM * L1_MM
        - L2_MM * L2_MM
    ) / (2.0 * L1_MM * L2_MM)
    if not -1.0 <= cos_q2 <= 1.0:
        raise AssertionError(
            f"unreachable shifted user point ({user_x:.3f},{user_y:.3f})"
        )
    sin_q2 = math.sqrt(max(0.0, 1.0 - cos_q2 * cos_q2))
    q2 = math.atan2(sin_q2, cos_q2)
    theta = math.atan2(
        L1_MM + L2_MM * cos_q2,
        L2_MM * sin_q2,
    ) - math.atan2(standard_x, standard_y)
    psi = theta + q2
    theta_deg = math.degrees(theta)
    psi_deg = math.degrees(psi)
    return theta_deg, psi_deg, psi_deg - theta_deg


def joint_margin(user: tuple[float, float]) -> tuple[float, tuple[float, ...]]:
    theta, psi, beta = inverse_user(*user)
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
    header = HEADER.read_text(encoding="utf-8")
    serial = SERIAL.read_text(encoding="utf-8")
    motion = MOTION_HEADER.read_text(encoding="utf-8")
    pins = PIN_CONFIG.read_text(encoding="utf-8")
    values = {
        match.group("name"): float(match.group("value"))
        for match in DEFINE_RE.finditer(header)
    }

    required_header = (
        f'"{BUILD_ID}"',
        "#define GCODE_SERIAL_PAPER_MAP_ENABLE         (0u)",
        "#define GCODE_SERIAL_WORKSPACE_SHIFT_X_MM     (0.0f)",
        "#define GCODE_SERIAL_WORKSPACE_SHIFT_Y_MM     (15.0f)",
    )
    for token in required_header:
        if token not in header:
            raise AssertionError(f"missing V28 header token: {token}")
    if values["GCODE_SERIAL_WORKSPACE_SHIFT_X_MM"] != SHIFT_X_MM:
        raise AssertionError("unexpected global X shift")
    if values["GCODE_SERIAL_WORKSPACE_SHIFT_Y_MM"] != SHIFT_Y_MM:
        raise AssertionError("unexpected global Y shift")

    required_source = (
        "*user_x_mm += GCODE_SERIAL_WORKSPACE_SHIFT_X_MM;",
        "*user_y_mm += GCODE_SERIAL_WORKSPACE_SHIFT_Y_MM;",
        "shift_x100=%d shift_y100=%d",
    )
    for token in required_source:
        if token not in serial:
            raise AssertionError(f"missing V28 source token: {token}")

    # Homing and the physical switch-angle contract must not move with the
    # Cartesian workspace translation.
    for token in (
        "#define APP_WRITER_THETA_LIMIT_DEG          (-0.773082f)",
        "#define APP_WRITER_PSI_LIMIT_DEG            (134.177381f)",
        "#define APP_WRITER_HOMING_PULLOFF_DEG       (1.0f)",
        "#define APP_WRITER_MACHINE_OFFSET_X_MM      (-129.0f)",
        "#define APP_WRITER_MACHINE_OFFSET_Y_MM      (128.0f)",
    ):
        if token not in motion:
            raise AssertionError(f"homing/machine contract changed: {token}")
    if pins.count("DL_GPIO_RESISTOR_PULL_UP") != 2:
        raise AssertionError("both NC limit inputs must retain pull-ups")

    worst = (float("inf"), (0.0, 0.0), (0.0, 0.0), (0.0, 0.0, 0.0))
    sample_count = 0
    # One-millimetre coverage of the full previously calibrated base-map
    # paper region, after the new global Cartesian translation.
    y = PAPER_Y_RANGE[0]
    while y <= PAPER_Y_RANGE[1] + 1.0e-6:
        x = PAPER_X_RANGE[0]
        while x <= PAPER_X_RANGE[1] + 1.0e-6:
            base_user = map_base_only((x, y))
            shifted_user = (
                base_user[0] + SHIFT_X_MM,
                base_user[1] + SHIFT_Y_MM,
            )
            margin, angles = joint_margin(shifted_user)
            if margin < worst[0]:
                worst = (margin, (x, y), shifted_user, angles)
            sample_count += 1
            x += 1.0
        y += 1.0

    if worst[0] < 10.0:
        raise AssertionError(
            f"global +15 mm shift leaves only {worst[0]:.3f} deg margin"
        )

    print(
        "workspace_yshift15_v28=PASS "
        f"id={BUILD_ID} shift=(0,+15)mm "
        "hard_limit_angles=UNCHANGED homing_pulloff=UNCHANGED "
        f"full_base_map_samples={sample_count} "
        f"min_joint_margin={worst[0]:.6f}deg "
        f"at_paper=({worst[1][0]:.1f},{worst[1][1]:.1f}) "
        f"shifted_user=({worst[2][0]:.3f},{worst[2][1]:.3f})"
    )


if __name__ == "__main__":
    main()
