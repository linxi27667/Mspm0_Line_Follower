"""Offline check for WORKSPACE_NO_DIRCOMP_RECT_10X5MM_AXES_V5."""

import numpy as np

import check_workspace_square_dircomp as model


model.THETA_REV_PSI_STEPS = 0
model.PSI_REV_PSI_STEPS = 0

CW = (
    (3.0, -0.35),
    (13.0, -0.35),
    (13.0, -5.35),
    (3.0, -5.35),
    (3.0, -0.35),
)
CCW = (
    (3.0, -0.35),
    (3.0, -5.35),
    (13.0, -5.35),
    (13.0, -0.35),
    (3.0, -0.35),
)
AXES = (
    ("X_POS", (3.0, -2.85), (13.0, -2.85)),
    ("Y_POS", (8.0, -5.35), (8.0, -0.35)),
)

WORKSPACE = (0.0, 16.611, -5.700, -0.019)


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


def move(
    state: model.State,
    point: tuple[float, float],
    label: str,
) -> tuple[model.State, list[tuple[float, float]]]:
    target = model.target_state(state, point, label)
    if target.bias_steps != 0:
        raise AssertionError(f"{label}: unexpected direction bias")
    return target, model.dda_user_points(state, target, label)


def main() -> None:
    state = initial_state()
    pen_down_points: list[tuple[float, float]] = []

    for pass_index, path in enumerate((CW, CW, CCW, CCW), 1):
        state, _ = move(state, path[0], f"pass{pass_index} approach")
        for edge_index, point in enumerate(path[1:], 1):
            state, points = move(state, point, f"pass{pass_index} edge{edge_index}")
            pen_down_points.extend(points)

    for name, start, end in AXES:
        state, _ = move(state, start, f"axis {name} approach")
        state, points = move(state, end, f"axis {name} line")
        pen_down_points.extend(points)

    xs = [point[0] for point in pen_down_points]
    ys = [point[1] for point in pen_down_points]
    envelope = min(xs), max(xs), min(ys), max(ys)
    x_min, x_max, y_min, y_max = WORKSPACE
    if not (
        x_min <= envelope[0] <= envelope[1] <= x_max
        and y_min <= envelope[2] <= envelope[3] <= y_max
    ):
        raise AssertionError(f"pen-down envelope outside workspace: {envelope}")

    print("PASS: rectangle, both axis approaches, and both pen-down axis lines are safe")
    print(
        f"Pen-down DDA envelope: X={envelope[0]:.3f}..{envelope[1]:.3f} "
        f"Y={envelope[2]:.3f}..{envelope[3]:.3f} mm"
    )
    print(
        "Workspace margins: "
        f"left={envelope[0] - x_min:.3f} right={x_max - envelope[1]:.3f} "
        f"bottom={envelope[2] - y_min:.3f} top={y_max - envelope[3]:.3f} mm"
    )


if __name__ == "__main__":
    main()
