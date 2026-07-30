"""Offline IK, integer-step, and DDA checks for the V8 corner-dot test."""

from __future__ import annotations

import numpy as np

import check_workspace_square_dircomp as model


CORNERS = (
    ("TOP_LEFT", (0.000, -0.019)),
    ("TOP_RIGHT", (16.611, -0.019)),
    ("BOTTOM_RIGHT", (16.611, -5.700)),
    ("BOTTOM_LEFT", (0.000, -5.700)),
)


def configure_model() -> None:
    model.OFFSET_X_MM = np.float32(-35.901242)
    model.OFFSET_Y_MM = np.float32(182.889598)
    model.THETA_LIMIT_DEG = np.float32(0.0)
    model.PSI_LIMIT_DEG = np.float32(135.0)
    model.THETA_MIN_DEG = np.float32(1.0)
    model.THETA_MAX_DEG = np.float32(45.0)
    model.PSI_MIN_DEG = np.float32(136.0)
    model.PSI_MAX_DEG = np.float32(179.0)
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


def main() -> None:
    configure_model()
    state = initial_state()
    model.check_pose(
        state.stage1_steps / float(model.STAGE1_STEPS_PER_DEG),
        state.stage2_motor_steps / float(model.STAGE2_STEPS_PER_DEG),
        "home",
    )

    path_points: list[tuple[float, float]] = []
    theta_targets: list[float] = []
    psi_targets: list[float] = []
    max_error = 0.0

    for index, (name, point) in enumerate(CORNERS, 1):
        prior = state
        state = model.target_state(state, point, f"corner{index} {name}")
        path = model.dda_user_points(prior, state, f"travel{index} {name}")
        path_points.extend(path)

        actual = model.user_from_steps(
            state.stage1_steps, state.stage2_motor_steps
        )
        error_x = actual[0] - point[0]
        error_y = actual[1] - point[1]
        max_error = max(max_error, abs(error_x), abs(error_y))
        theta_targets.append(
            state.stage1_steps / float(model.STAGE1_STEPS_PER_DEG)
        )
        psi_targets.append(
            state.stage2_motor_steps / float(model.STAGE2_STEPS_PER_DEG)
        )
        print(
            f"corner={index}/4 name={name} requested=({point[0]:.3f},"
            f"{point[1]:.3f}) quantized=({actual[0]:.3f},{actual[1]:.3f}) "
            f"error=({error_x:+.3f},{error_y:+.3f}) pulses={len(path) - 1}"
        )

    if state.bias_steps != 0:
        raise AssertionError("direction compensation must remain disabled")
    if max_error > 0.08:
        raise AssertionError(f"quantized corner error {max_error:.6f} mm")

    print(
        "PASS: four endpoints and every pen-up DDA travel pulse satisfy "
        "theta/psi/beta limits"
    )
    print("requested workspace: X=0.000..16.611 Y=-5.700..-0.019 mm")
    print(
        f"joint targets: theta={min(theta_targets):.3f}.."
        f"{max(theta_targets):.3f} psi={min(psi_targets):.3f}.."
        f"{max(psi_targets):.3f} deg"
    )
    print(f"maximum quantized endpoint error: {max_error:.3f} mm")
    print(
        f"all pen-up paths: X={min(p[0] for p in path_points):.3f}.."
        f"{max(p[0] for p in path_points):.3f} "
        f"Y={min(p[1] for p in path_points):.3f}.."
        f"{max(p[1] for p in path_points):.3f} mm"
    )


if __name__ == "__main__":
    main()
