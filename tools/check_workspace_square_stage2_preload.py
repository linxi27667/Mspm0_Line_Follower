"""Offline pulse-level check for WORKSPACE_STAGE2_PRELOAD_28_4P5MM_V3."""

from __future__ import annotations

import numpy as np

import check_workspace_square_dircomp as model


model.THETA_REV_PSI_STEPS = 0
model.PSI_REV_PSI_STEPS = 28
model.CW = (
    (3.0, -0.86),
    (7.5, -0.86),
    (7.5, -5.36),
    (3.0, -5.36),
    (3.0, -0.86),
)
model.CCW = (
    (3.0, -0.86),
    (3.0, -5.36),
    (7.5, -5.36),
    (7.5, -0.86),
    (3.0, -0.86),
)

WORKSPACE_X_MIN = 0.0
WORKSPACE_X_MAX = 16.611
WORKSPACE_Y_MIN = -5.700
WORKSPACE_Y_MAX = -0.019


def initial_state() -> model.State:
    stage1_clearance = model.lroundf(model.STAGE1_STEPS_PER_DEG)
    stage2_clearance = model.lroundf(model.STAGE2_STEPS_PER_DEG)
    home_theta = np.float32(
        model.THETA_LIMIT_DEG
        + np.float32(1 + stage1_clearance) / model.STAGE1_STEPS_PER_DEG
    )
    home_psi = np.float32(
        model.PSI_LIMIT_DEG
        + np.float32(1 + stage2_clearance) / model.STAGE2_STEPS_PER_DEG
    )
    return model.State(
        model.lroundf(np.float32(home_theta * model.STAGE1_STEPS_PER_DEG)),
        model.lroundf(np.float32(home_psi * model.STAGE2_STEPS_PER_DEG)),
        model.lroundf(np.float32(home_psi * model.STAGE2_STEPS_PER_DEG)),
        0,
        1,
        1,
    )


def run_target(
    state: model.State,
    point: tuple[float, float],
    label: str,
) -> tuple[model.State, list[tuple[float, float]], list[tuple[float, float]]]:
    target = model.target_state(state, point, label)
    preload_delta = target.bias_steps - state.bias_steps
    preload = model.State(
        state.stage1_steps,
        state.stage2_logical_steps,
        state.stage2_logical_steps + target.bias_steps,
        target.bias_steps,
        state.stage1_dir,
        target.stage2_motor_dir,
    )

    if preload.stage2_motor_steps - state.stage2_motor_steps != preload_delta:
        raise AssertionError(f"{label}: preload delta invariant failed")
    if (
        target.stage2_motor_steps - preload.stage2_motor_steps
        != target.stage2_logical_steps - state.stage2_logical_steps
    ):
        raise AssertionError(f"{label}: main Stage2 delta is not logical delta")

    preload_points = model.dda_user_points(state, preload, f"{label} preload")
    main_points = model.dda_user_points(preload, target, f"{label} main")
    print(
        f"  phases preload={preload_delta:+d} "
        f"main=({target.stage1_steps - state.stage1_steps:+d},"
        f"{target.stage2_logical_steps - state.stage2_logical_steps:+d})"
    )
    return target, preload_points, main_points


def main() -> None:
    state = initial_state()
    bias_states = {state.bias_steps}
    drawing_points: list[tuple[float, float]] = []
    preload_events = 0

    for pass_index, path in enumerate((model.CW, model.CW, model.CCW, model.CCW), 1):
        state, _, _ = run_target(state, path[0], f"pass{pass_index} approach")
        bias_states.add(state.bias_steps)
        for edge_index, point in enumerate(path[1:], 1):
            state, preload_points, main_points = run_target(
                state, point, f"pass{pass_index} edge{edge_index}"
            )
            bias_states.add(state.bias_steps)
            if len(preload_points) > 1:
                preload_events += 1
            drawing_points.extend(preload_points)
            drawing_points.extend(main_points)

    if bias_states != {-28, 0}:
        raise AssertionError(f"unexpected bias states: {sorted(bias_states)}")

    x_values = [point[0] for point in drawing_points]
    y_values = [point[1] for point in drawing_points]
    envelope = (min(x_values), max(x_values), min(y_values), max(y_values))
    if not (
        WORKSPACE_X_MIN <= envelope[0] <= envelope[1] <= WORKSPACE_X_MAX
        and WORKSPACE_Y_MIN <= envelope[2] <= envelope[3] <= WORKSPACE_Y_MAX
    ):
        raise AssertionError(f"rigid DDA envelope outside workspace: {envelope}")

    print(
        "PASS: separate preload and main DDA phases satisfy all joint/beta "
        f"limits; bias_states={sorted(bias_states)} preload_events={preload_events}"
    )
    print(
        "Rigid-link worst-case pen-down envelope: "
        f"X={envelope[0]:.3f}..{envelope[1]:.3f} "
        f"Y={envelope[2]:.3f}..{envelope[3]:.3f} mm"
    )
    print(
        "Workspace margins: "
        f"left={envelope[0] - WORKSPACE_X_MIN:.3f} "
        f"right={WORKSPACE_X_MAX - envelope[1]:.3f} "
        f"bottom={envelope[2] - WORKSPACE_Y_MIN:.3f} "
        f"top={WORKSPACE_Y_MAX - envelope[3]:.3f} mm"
    )


if __name__ == "__main__":
    main()
