"""Offline integer-pulse safety check for A4_JOINT_ENVELOPE_GATED_V9."""

from __future__ import annotations

import math

import numpy as np

import check_workspace_square_dircomp as model


WAYPOINTS = (
    ("S50X35_TL", 13.188161, 142.561806),
    ("S50X35_TR", 20.747725, 161.270287),
    ("S50X35_BR", 32.907090, 164.565446),
    ("S50X35_BL", 25.133816, 146.949438),
    ("S75X53_TL", 13.188161, 142.561806),
    ("S75X53_TR", 27.853001, 172.657236),
    ("S75X53_BR", 44.199812, 174.211959),
    ("S75X53_BL", 30.790427, 148.186407),
    ("S150X106_TL", 13.188161, 142.561806),
    ("S150X106_TR", 63.506862, 212.753342),
    ("S150X106_BR", 75.992840, 192.139797),
    ("S150X106_BL", 46.160898, 148.616029),
    ("S220X155_TL", 13.188161, 142.561806),
    ("S220X155_TR", 98.729713, 239.252275),
    ("S220X155_BR", 101.249308, 194.958218),
    ("S220X155_BL", 59.648044, 145.472500),
    ("A4_297X210_TL", 13.188161, 142.561806),
    ("A4_297X210_TR", 125.908066, 248.193504),
    ("A4_297X210_BR", 129.534170, 184.898053),
    ("A4_297X210_BL", 75.757737, 137.845082),
    ("PARK", 20.000000, 150.000000),
)


def configure_model() -> None:
    model.OFFSET_X_MM = np.float32(-35.923301)
    model.OFFSET_Y_MM = np.float32(167.210999)
    model.THETA_LIMIT_DEG = np.float32(0.0)
    model.PSI_LIMIT_DEG = np.float32(135.0)
    model.THETA_MIN_DEG = np.float32(1.0)
    model.THETA_MAX_DEG = np.float32(135.0)
    model.PSI_MIN_DEG = np.float32(136.0)
    model.PSI_MAX_DEG = np.float32(255.0)
    model.BETA_MIN_DEG = np.float32(1.0)
    model.BETA_MAX_DEG = np.float32(179.0)
    model.THETA_REV_PSI_STEPS = 0
    model.PSI_REV_PSI_STEPS = 0


def initial_state() -> model.State:
    stage1_clearance = model.lroundf(model.STAGE1_STEPS_PER_DEG)
    stage2_clearance = model.lroundf(model.STAGE2_STEPS_PER_DEG)
    theta = np.float32(
        model.THETA_LIMIT_DEG
        + np.float32(1 + stage1_clearance) / model.STAGE1_STEPS_PER_DEG
    )
    psi = np.float32(
        model.PSI_LIMIT_DEG
        + np.float32(1 + stage2_clearance) / model.STAGE2_STEPS_PER_DEG
    )
    return model.State(
        model.lroundf(np.float32(theta * model.STAGE1_STEPS_PER_DEG)),
        model.lroundf(np.float32(psi * model.STAGE2_STEPS_PER_DEG)),
        model.lroundf(np.float32(psi * model.STAGE2_STEPS_PER_DEG)),
        0,
        1,
        1,
    )


def target_state(
    prior: model.State, theta: float, psi: float, label: str
) -> model.State:
    stage1 = model.lroundf(
        np.float32(theta) * model.STAGE1_STEPS_PER_DEG
    )
    stage2 = model.lroundf(
        np.float32(psi) * model.STAGE2_STEPS_PER_DEG
    )
    quantized_theta = stage1 / float(model.STAGE1_STEPS_PER_DEG)
    quantized_psi = stage2 / float(model.STAGE2_STEPS_PER_DEG)
    model.check_pose(quantized_theta, quantized_psi, label)
    return model.State(
        stage1,
        stage2,
        stage2,
        0,
        1 if stage1 >= prior.stage1_steps else -1,
        1 if stage2 >= prior.stage2_motor_steps else -1,
    )


def main() -> None:
    configure_model()
    state = initial_state()
    total_pulses = 0
    theta_values: list[float] = []
    psi_values: list[float] = []
    beta_values: list[float] = []

    for index, (name, theta, psi) in enumerate(WAYPOINTS, 1):
        target = target_state(state, theta, psi, name)
        path = model.dda_user_points(state, target, name)
        total_pulses += len(path) - 1
        quantized_theta = target.stage1_steps / float(
            model.STAGE1_STEPS_PER_DEG
        )
        quantized_psi = target.stage2_motor_steps / float(
            model.STAGE2_STEPS_PER_DEG
        )
        beta = quantized_psi - quantized_theta
        theta_values.append(quantized_theta)
        psi_values.append(quantized_psi)
        beta_values.append(beta)
        print(
            f"{index:02d}/{len(WAYPOINTS)} {name:16s} "
            f"theta={quantized_theta:8.3f} psi={quantized_psi:8.3f} "
            f"beta={beta:8.3f} pulses={len(path) - 1:5d}"
        )
        state = target

    if not math.isclose(state.bias_steps, 0):
        raise AssertionError("direction compensation must remain disabled")
    print(
        "PASS: every target and every synchronized integer-pulse path "
        "satisfies probe theta/psi/beta limits"
    )
    print(
        f"targets theta={min(theta_values):.3f}..{max(theta_values):.3f} "
        f"psi={min(psi_values):.3f}..{max(psi_values):.3f} "
        f"beta={min(beta_values):.3f}..{max(beta_values):.3f} deg"
    )
    print(f"moves={len(WAYPOINTS)} total_master_pulses={total_pulses}")
    print("pen=UP direction_comp=OFF gcode=DISABLED command_gate=NEXT")


if __name__ == "__main__":
    main()
