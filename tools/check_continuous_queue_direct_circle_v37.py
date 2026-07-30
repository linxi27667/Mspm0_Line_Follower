#!/usr/bin/env python3
"""Static checks for the V27 firmware and V37 direct circle test."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GCODE_PATH = (
    ROOT
    / "gcode"
    / "PAPER_A4_CONTINUOUS_QUEUE_DIRECT_6CIRCLE_D18_GCODE_V37.gcode"
)
MANIFEST_PATH = (
    ROOT
    / "gcode"
    / "PAPER_A4_CONTINUOUS_QUEUE_DIRECT_6CIRCLE_D18_GCODE_V37.json"
)
STEPPER_SOURCE = ROOT / "APP" / "stepper" / "Src" / "app_stepper.c"
SERIAL_SOURCE = ROOT / "TASK" / "gcode_serial.c"
SERIAL_HEADER = ROOT / "TASK" / "gcode_serial.h"

MOVE_RE = re.compile(
    r"^G([01])\s+X(-?\d+(?:\.\d+)?)\s+Y(-?\d+(?:\.\d+)?)$"
)
L1_MM = 205.0
L2_MM = 203.0
OFFSET_X_MM = -129.0
OFFSET_Y_MM = 128.0
THETA_MIN_DEG = -0.773082 + 1.0
PSI_MIN_DEG = 134.177381 + 1.0
THETA_MAX_DEG = 135.0
PSI_MAX_DEG = 255.0


def signed_area(points: list[tuple[float, float]]) -> float:
    return 0.5 * sum(
        x0 * y1 - x1 * y0
        for (x0, y0), (x1, y1) in zip(points, points[1:])
    )


def inverse_user(x_mm: float, y_mm: float) -> tuple[float, float]:
    standard_x = -(x_mm + OFFSET_X_MM)
    standard_y = y_mm + OFFSET_Y_MM
    cos_q2 = (
        standard_x * standard_x
        + standard_y * standard_y
        - L1_MM * L1_MM
        - L2_MM * L2_MM
    ) / (2.0 * L1_MM * L2_MM)
    assert -1.0 <= cos_q2 <= 1.0
    sin_q2 = math.sqrt(max(0.0, 1.0 - cos_q2 * cos_q2))
    theta = math.atan2(
        L1_MM + L2_MM * cos_q2,
        L2_MM * sin_q2,
    ) - math.atan2(standard_x, standard_y)
    psi = theta + math.atan2(sin_q2, cos_q2)
    return math.degrees(theta), math.degrees(psi)


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    lines = [
        line.strip()
        for line in GCODE_PATH.read_text(encoding="ascii").splitlines()
        if line.strip()
    ]
    stepper = STEPPER_SOURCE.read_text(encoding="utf-8")
    serial = SERIAL_SOURCE.read_text(encoding="utf-8")
    header = SERIAL_HEADER.read_text(encoding="utf-8")

    assert '"PAPER_A4_CONTINUOUS_QUEUE_SAFE_HOME_GCODE_V27"' in header
    assert "#define GCODE_SERIAL_PAPER_MAP_ENABLE         (0u)" in header
    assert "App_Stepper_Dual_Load_Queued_Block()" in stepper
    assert "if (App_Stepper_Dual_Load_Queued_Block())" in stepper
    assert "APP_STEPPER_QUEUE_ACCEL_STEP_HZ" in stepper
    assert "App_Stepper_Use_Stage1_Pwm_Step_Pin" in stepper
    assert "App_Stepper_Use_Stage2_Pwm_Step_Pin" in stepper
    assert "App_Stepper_Use_Pwm_Step_Pins" not in stepper
    assert (
        "!s_dda.active &&\n"
        "        !s_dual_queue_mode &&\n"
        "        (s_dual_queue_head == s_dual_queue_tail)"
    ) in stepper
    assert "WriterMotion_Queue_To_At_Feed" in serial
    assert "GCODE_SERIAL_STATE_WAIT_SYNC_PEN" in serial
    assert "GCODE_SERIAL_STATE_WAIT_SYNC_DWELL" in serial

    circles: list[list[tuple[float, float]]] = []
    moves: list[tuple[float, float]] = []
    current: list[tuple[float, float]] | None = None
    pen_down = False
    for line in lines:
        if line.startswith(";"):
            continue
        if line == "M3":
            assert not pen_down
            pen_down = True
            current = []
            continue
        if line == "M5":
            if pen_down:
                assert current is not None
                circles.append(current)
            pen_down = False
            current = None
            continue
        match = MOVE_RE.match(line)
        if match:
            moves.append(
                (float(match.group(2)), float(match.group(3)))
            )
        if match and pen_down:
            assert match.group(1) == "1"
            assert current is not None
            current.append((float(match.group(2)), float(match.group(3))))

    assert not pen_down
    assert len(circles) == 6
    assert len(manifest["circles"]) == len(circles)
    assert manifest["paper_map_enabled"] is False

    for index, (circle, record) in enumerate(
        zip(circles, manifest["circles"])
    ):
        assert len(circle) == 72
        center_x, center_y = record["command_user_center_mm"]
        radii = [
            math.hypot(x - center_x, y - center_y)
            for x, y in circle
        ]
        assert max(abs(radius - 9.0) for radius in radii) < 0.001
        start = (center_x, center_y + 9.0)
        assert math.hypot(
            circle[-1][0] - start[0],
            circle[-1][1] - start[1],
        ) < 0.001
        polygon = [start, *circle]
        direction = "CCW" if signed_area(polygon) > 0.0 else "CW"
        assert direction == record["direction"], (index, direction, record)

    home_theta = math.radians(THETA_MIN_DEG)
    home_psi = math.radians(PSI_MIN_DEG)
    previous = (
        -L1_MM * math.cos(home_theta)
        - L2_MM * math.cos(home_psi)
        - OFFSET_X_MM,
        L1_MM * math.sin(home_theta)
        + L2_MM * math.sin(home_psi)
        - OFFSET_Y_MM,
    )
    path_samples = 0
    for target in moves:
        dx = target[0] - previous[0]
        dy = target[1] - previous[1]
        count = max(
            1,
            math.ceil(max(abs(dx), abs(dy)) / 1.0),
        )
        for sample_index in range(1, count + 1):
            ratio = sample_index / count
            x_mm = previous[0] + dx * ratio
            y_mm = previous[1] + dy * ratio
            theta_deg, psi_deg = inverse_user(x_mm, y_mm)
            beta_deg = psi_deg - theta_deg
            assert THETA_MIN_DEG <= theta_deg <= THETA_MAX_DEG
            assert PSI_MIN_DEG <= psi_deg <= PSI_MAX_DEG
            assert 1.0 <= beta_deg <= 179.0
            path_samples += 1
        previous = target

    print(
        "PASS: V27 safe-home continuous queue source contract; "
        "V37 direct circles=6, G1=432, segments/circle=72, "
        f"paper_map=OFF, row_y=140mm, safe_samples={path_samples}"
    )


if __name__ == "__main__":
    main()
