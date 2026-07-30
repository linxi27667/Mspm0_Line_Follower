#!/usr/bin/env python3
"""Static and kinematic checks for the V34 trial paper-Y extension."""

from __future__ import annotations

import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAPER_HEADER = ROOT / "APP" / "Inc" / "app_writer_paper_map.h"
GCODE_HEADER = ROOT / "TASK" / "gcode_serial.h"
GCODE_SOURCE = ROOT / "TASK" / "gcode_serial.c"
CLOUD_SOURCE = ROOT / "TASK" / "writer_cloud.c"
FIRMWARE_HEX = ROOT / "keil" / "PAPER_A4_EXTENDED_Y45_265_TRIAL_V34.hex"

L1_MM = 205.0
L2_MM = 203.0
OFFSET_X_MM = -129.0
OFFSET_Y_MM = 128.0
THETA_MIN_DEG = -0.773082 + 1.0
THETA_MAX_DEG = 135.0
PSI_MIN_DEG = 134.177381 + 1.0
PSI_MAX_DEG = 255.0
PAPER_X_RANGE = (25, 185)
PAPER_Y_RANGE = (45, 265)
MINIMUM_MARGIN_DEG = 10.0

BASE_X = (
    290.945962, 62.273998, -78.732064,
    -3.922490, -2.442049, 5.239680,
)
BASE_Y = (
    30.887338, 84.802037, 52.883179,
    -7.669222, 3.617273, 3.846007,
)


def require(source: str, tokens: tuple[str, ...], name: str) -> None:
    missing = [token for token in tokens if token not in source]
    if missing:
        raise AssertionError(f"{name} missing: {missing}")


def intel_hex_payload(path: Path) -> bytes:
    payload = bytearray()
    for line in path.read_text(encoding="ascii").splitlines():
        if not line.startswith(":"):
            continue
        count = int(line[1:3], 16)
        record_type = int(line[7:9], 16)
        if record_type == 0:
            payload.extend(bytes.fromhex(line[9:9 + count * 2]))
    return bytes(payload)


def paper_to_user(paper_x_mm: float, paper_y_mm: float) -> tuple[float, float]:
    calibrated_x = 105.0 + (paper_x_mm - 105.0) / 1.03125
    calibrated_y = paper_y_mm - 15.0
    nx = (calibrated_x - 105.0) / 100.0
    ny = (calibrated_y - 130.0) / 100.0
    basis = (1.0, nx, ny, nx * nx, nx * ny, ny * ny)
    user_x = sum(value * coefficient for value, coefficient in zip(basis, BASE_X))
    user_y = sum(value * coefficient for value, coefficient in zip(basis, BASE_Y))
    return user_x, user_y + 15.0


def joint_margin(user_x_mm: float, user_y_mm: float) -> float:
    standard_x = -(user_x_mm + OFFSET_X_MM)
    standard_y = user_y_mm + OFFSET_Y_MM
    cos_q2 = (
        standard_x * standard_x + standard_y * standard_y
        - L1_MM * L1_MM - L2_MM * L2_MM
    ) / (2.0 * L1_MM * L2_MM)
    if not -1.0 <= cos_q2 <= 1.0:
        raise AssertionError(
            f"unreachable user point ({user_x_mm:.3f},{user_y_mm:.3f})"
        )
    q2 = math.acos(cos_q2)
    theta = math.atan2(
        L1_MM + L2_MM * cos_q2, L2_MM * math.sin(q2)
    ) - math.atan2(standard_x, standard_y)
    theta_deg = math.degrees(theta)
    psi_deg = theta_deg + math.degrees(q2)
    beta_deg = psi_deg - theta_deg
    return min(
        theta_deg - THETA_MIN_DEG,
        THETA_MAX_DEG - theta_deg,
        psi_deg - PSI_MIN_DEG,
        PSI_MAX_DEG - psi_deg,
        beta_deg - 1.0,
        179.0 - beta_deg,
    )


def main() -> None:
    paper_header = PAPER_HEADER.read_text(encoding="utf-8")
    gcode_header = GCODE_HEADER.read_text(encoding="utf-8")
    gcode_source = GCODE_SOURCE.read_text(encoding="utf-8")
    cloud_source = CLOUD_SOURCE.read_text(encoding="utf-8")

    require(paper_header, (
        '"A4_BASE_QUADRATIC_XSCALE_NO_SBOW_Y45_265_TRIAL_V9"',
        "APP_WRITER_PAPER_Y_MIN_MM             (45.0f)",
        "APP_WRITER_PAPER_Y_MAX_MM             (265.0f)",
        "APP_WRITER_PAPER_CALIBRATED_Y_MIN_MM  (75.0f)",
        "APP_WRITER_PAPER_CALIBRATED_Y_MAX_MM  (235.0f)",
    ), "paper map")
    require(gcode_header, (
        '"PAPER_A4_EXTENDED_Y45_265_TRIAL_V34"',
    ), "G-code build")
    require(gcode_source, (
        "paper_y_trial=%u",
        "outside_calibrated=EXTRAPOLATED",
        "map=%s",
    ), "EasyLogger diagnostics")
    require(cloud_source, (
        '\\"y_min\\":45.0,\\"y_max\\":265.0',
        'GCODE_SERIAL_BUILD_ID',
    ), "cloud status")
    firmware = intel_hex_payload(FIRMWARE_HEX)
    for token in (
        b"PAPER_A4_EXTENDED_Y45_265_TRIAL_V34",
        b"A4_BASE_QUADRATIC_XSCALE_NO_SBOW_Y45_265_TRIAL_V9",
        b"outside_calibrated=EXTRAPOLATED",
    ):
        if token not in firmware:
            raise AssertionError(f"firmware HEX missing: {token!r}")

    worst = (float("inf"), (0, 0), (0.0, 0.0))
    for paper_y in range(PAPER_Y_RANGE[0], PAPER_Y_RANGE[1] + 1):
        for paper_x in range(PAPER_X_RANGE[0], PAPER_X_RANGE[1] + 1):
            user = paper_to_user(float(paper_x), float(paper_y))
            margin = joint_margin(*user)
            if margin < worst[0]:
                worst = (margin, (paper_x, paper_y), user)

    if worst[0] < MINIMUM_MARGIN_DEG:
        raise AssertionError(
            f"joint margin {worst[0]:.3f} deg at paper {worst[1]} user {worst[2]}"
        )
    print(
        "PASS: V34 paper Y=45..265 mm; "
        f"dense-grid minimum joint margin={worst[0]:.3f} deg "
        f"at paper={worst[1]} user=({worst[2][0]:.3f},{worst[2][1]:.3f})"
    )


if __name__ == "__main__":
    main()
