"""Offline pulse and limit check for the compensated 5 mm square test."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


L1_MM = np.float32(200.0)
L2_MM = np.float32(200.0)
OFFSET_X_MM = np.float32(-135.0)
OFFSET_Y_MM = np.float32(105.0)

THETA_LIMIT_DEG = np.float32(-45.43)
PSI_LIMIT_DEG = np.float32(95.67)
THETA_MIN_DEG = np.float32(-44.43)
THETA_MAX_DEG = np.float32(45.0)
PSI_MIN_DEG = np.float32(96.67)
PSI_MAX_DEG = np.float32(179.0)
BETA_MIN_DEG = np.float32(1.0)
BETA_MAX_DEG = np.float32(179.0)

STAGE1_STEPS_PER_DEG = np.float32(43.708318)
STAGE2_STEPS_PER_DEG = np.float32(48.8)
THETA_REV_PSI_STEPS = 15
PSI_REV_PSI_STEPS = 21
MAX_BIAS_STEPS = 64


CW = ((5.5, -0.35), (10.5, -0.35), (10.5, -5.35), (5.5, -5.35), (5.5, -0.35))
CCW = ((5.5, -0.35), (5.5, -5.35), (10.5, -5.35), (10.5, -0.35), (5.5, -0.35))


def lroundf(value: np.float32) -> int:
    value_float = float(value)
    if value_float >= 0.0:
        return math.floor(value_float + 0.5)
    return math.ceil(value_float - 0.5)


def step_direction(delta: int, previous: int) -> int:
    if delta > 0:
        return 1
    if delta < 0:
        return -1
    return previous


def inverse(user_x: float, user_y: float) -> tuple[np.float32, np.float32]:
    machine_x = np.float32(np.float32(user_x) + OFFSET_X_MM)
    machine_y = np.float32(np.float32(user_y) + OFFSET_Y_MM)
    standard_x = np.float32(-machine_x)
    standard_y = machine_y
    radius_sq = np.float32(standard_x * standard_x + standard_y * standard_y)
    l1_sq = np.float32(L1_MM * L1_MM)
    l2_sq = np.float32(L2_MM * L2_MM)
    c2 = np.float32(
        (radius_sq - l1_sq - l2_sq) / np.float32(2.0 * L1_MM * L2_MM)
    )
    c2 = np.clip(c2, np.float32(-1.0), np.float32(1.0)).astype(np.float32)
    s2 = np.sqrt(np.float32(1.0) - np.float32(c2 * c2), dtype=np.float32)
    k1 = np.float32(l1_sq + l2_sq * c2)
    k2 = np.float32(l2_sq * s2)
    theta = np.float32(
        np.arctan2(k1, k2) - np.arctan2(standard_x, standard_y)
    )
    q2 = np.float32(np.arctan2(s2, c2))
    psi = np.float32(theta + q2)
    rad_to_deg = np.float32(180.0 / math.pi)
    return np.float32(theta * rad_to_deg), np.float32(psi * rad_to_deg)


def user_from_steps(stage1_steps: int, stage2_motor_steps: int) -> tuple[float, float]:
    theta = np.float32(stage1_steps) / STAGE1_STEPS_PER_DEG
    psi = np.float32(stage2_motor_steps) / STAGE2_STEPS_PER_DEG
    deg_to_rad = np.float32(math.pi / 180.0)
    machine_x = np.float32(
        -np.cos(np.float32(theta * deg_to_rad), dtype=np.float32) * L1_MM
        - np.cos(np.float32(psi * deg_to_rad), dtype=np.float32) * L2_MM
    )
    machine_y = np.float32(
        np.sin(np.float32(theta * deg_to_rad), dtype=np.float32) * L1_MM
        + np.sin(np.float32(psi * deg_to_rad), dtype=np.float32) * L2_MM
    )
    return float(machine_x - OFFSET_X_MM), float(machine_y - OFFSET_Y_MM)


@dataclass
class State:
    stage1_steps: int
    stage2_logical_steps: int
    stage2_motor_steps: int
    bias_steps: int
    stage1_dir: int
    stage2_motor_dir: int


def check_pose(theta: float, psi: float, label: str) -> None:
    beta = psi - theta
    if not (float(THETA_MIN_DEG) <= theta <= float(THETA_MAX_DEG)):
        raise AssertionError(f"{label}: theta {theta:.6f} outside limits")
    if not (float(PSI_MIN_DEG) <= psi <= float(PSI_MAX_DEG)):
        raise AssertionError(f"{label}: psi {psi:.6f} outside limits")
    if not (float(BETA_MIN_DEG) <= beta <= float(BETA_MAX_DEG)):
        raise AssertionError(f"{label}: beta {beta:.6f} outside limits")
    if psi <= theta:
        raise AssertionError(f"{label}: psi <= theta")


def target_state(state: State, point: tuple[float, float], label: str) -> State:
    theta, psi = inverse(*point)
    check_pose(float(theta), float(psi), f"{label} logical")
    stage1_target = lroundf(np.float32(theta * STAGE1_STEPS_PER_DEG))
    stage2_logical_target = lroundf(np.float32(psi * STAGE2_STEPS_PER_DEG))
    stage1_delta = stage1_target - state.stage1_steps
    next_stage1_dir = step_direction(stage1_delta, state.stage1_dir)

    next_bias = state.bias_steps
    if next_stage1_dir and next_stage1_dir != state.stage1_dir:
        next_bias -= next_stage1_dir * THETA_REV_PSI_STEPS

    preliminary_motor_target = stage2_logical_target + next_bias
    preliminary_delta = preliminary_motor_target - state.stage2_motor_steps
    next_stage2_dir = step_direction(preliminary_delta, state.stage2_motor_dir)
    if preliminary_delta and next_stage2_dir != state.stage2_motor_dir:
        next_bias += next_stage2_dir * PSI_REV_PSI_STEPS

    if abs(next_bias) > MAX_BIAS_STEPS:
        raise AssertionError(f"{label}: bias {next_bias} outside guard")

    stage2_motor_target = stage2_logical_target + next_bias
    final_delta = stage2_motor_target - state.stage2_motor_steps
    if step_direction(final_delta, state.stage2_motor_dir) != next_stage2_dir:
        raise AssertionError(f"{label}: compensated direction changed")

    theta_quantized = stage1_target / float(STAGE1_STEPS_PER_DEG)
    psi_motor_quantized = stage2_motor_target / float(STAGE2_STEPS_PER_DEG)
    check_pose(theta_quantized, psi_motor_quantized, f"{label} compensated")
    user_rigid_x, user_rigid_y = user_from_steps(stage1_target, stage2_motor_target)
    error_x = user_rigid_x - point[0]
    error_y = user_rigid_y - point[1]

    print(
        f"{label:18s} user=({point[0]:6.2f},{point[1]:6.2f}) "
        f"theta={float(theta):9.5f} psi={float(psi):9.5f} "
        f"s1={stage1_target:5d} s2log={stage2_logical_target:5d} "
        f"bias={next_bias:3d} s2motor={stage2_motor_target:5d} "
        f"delta=({stage1_delta:4d},{final_delta:4d}) "
        f"dir=({next_stage1_dir:+d},{next_stage2_dir:+d}) "
        f"rigid_err=({error_x:+6.3f},{error_y:+6.3f})"
    )

    return State(
        stage1_target,
        stage2_logical_target,
        stage2_motor_target,
        next_bias,
        next_stage1_dir,
        next_stage2_dir,
    )


def dda_user_points(start: State, target: State, label: str) -> list[tuple[float, float]]:
    delta1 = target.stage1_steps - start.stage1_steps
    delta2 = target.stage2_motor_steps - start.stage2_motor_steps
    steps1 = abs(delta1)
    steps2 = abs(delta2)
    master_steps = max(steps1, steps2)
    if master_steps == 0:
        return [user_from_steps(start.stage1_steps, start.stage2_motor_steps)]

    direction1 = 1 if delta1 > 0 else -1
    direction2 = 1 if delta2 > 0 else -1
    current1 = start.stage1_steps
    current2 = start.stage2_motor_steps
    error1 = master_steps // 2
    error2 = master_steps // 2
    points = [user_from_steps(current1, current2)]
    for _ in range(master_steps):
        error1 += steps1
        if error1 >= master_steps:
            error1 -= master_steps
            current1 += direction1
        error2 += steps2
        if error2 >= master_steps:
            error2 -= master_steps
            current2 += direction2
        theta = current1 / float(STAGE1_STEPS_PER_DEG)
        psi = current2 / float(STAGE2_STEPS_PER_DEG)
        check_pose(theta, psi, f"{label} DDA")
        points.append(user_from_steps(current1, current2))

    if current1 != target.stage1_steps or current2 != target.stage2_motor_steps:
        raise AssertionError(f"{label}: DDA endpoint mismatch")
    return points


def main() -> None:
    # Homing always releases each active switch by at least one pulse, then
    # adds the configured 1 degree clearance. Use that minimum release here.
    stage1_clearance = lroundf(STAGE1_STEPS_PER_DEG)
    stage2_clearance = lroundf(STAGE2_STEPS_PER_DEG)
    home_theta = np.float32(
        THETA_LIMIT_DEG
        + np.float32(1 + stage1_clearance) / STAGE1_STEPS_PER_DEG
    )
    home_psi = np.float32(
        PSI_LIMIT_DEG
        + np.float32(1 + stage2_clearance) / STAGE2_STEPS_PER_DEG
    )
    state = State(
        lroundf(np.float32(home_theta * STAGE1_STEPS_PER_DEG)),
        lroundf(np.float32(home_psi * STAGE2_STEPS_PER_DEG)),
        lroundf(np.float32(home_psi * STAGE2_STEPS_PER_DEG)),
        0,
        1,
        1,
    )
    check_pose(
        state.stage1_steps / float(STAGE1_STEPS_PER_DEG),
        state.stage2_motor_steps / float(STAGE2_STEPS_PER_DEG),
        "home compensated",
    )
    print(
        f"home               s1={state.stage1_steps:5d} "
        f"s2={state.stage2_motor_steps:5d} bias=0 dir=(+1,+1)"
    )

    bias_states = {state.bias_steps}
    rigid_points: list[tuple[float, float]] = []
    for pass_index, path in enumerate((CW, CW, CCW, CCW), start=1):
        state = target_state(state, path[0], f"pass{pass_index} approach")
        bias_states.add(state.bias_steps)
        for edge_index, point in enumerate(path[1:], start=1):
            prior_state = state
            state = target_state(state, point, f"pass{pass_index} edge{edge_index}")
            bias_states.add(state.bias_steps)
            rigid_points.extend(
                dda_user_points(prior_state, state, f"pass{pass_index} edge{edge_index}")
            )

    x_values = [point[0] for point in rigid_points]
    y_values = [point[1] for point in rigid_points]
    print(
        "PASS: all logical and compensated targets satisfy theta/psi/beta limits; "
        f"bias_states={sorted(bias_states)}"
    )
    print(
        "Rigid-link worst-case compensated DDA drawing path (assumes zero backlash): "
        f"X={min(x_values):.3f}..{max(x_values):.3f} "
        f"Y={min(y_values):.3f}..{max(y_values):.3f} mm"
    )


if __name__ == "__main__":
    main()
