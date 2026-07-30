"""Generate and verify the offline-IK 75 x 53 mm gated draw path."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np

import check_workspace_square_dircomp as model


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HEADER = ROOT / "TASK" / "a4_75x53_draw_path.h"

VERTEX_ANGLES = (
    ("P5_TL", 13.188161, 142.561806),
    ("P6_TR", 27.853001, 172.657236),
    ("P7_BR", 44.199812, 174.211959),
    ("P8_BL", 30.790427, 148.186407),
)
EDGE_SEGMENTS = (75, 53, 75, 53)
CORNER_INDICES = (0, 75, 128, 203, 256)


def configure_model() -> None:
    model.OFFSET_X_MM = np.float32(-35.901242)
    model.OFFSET_Y_MM = np.float32(182.889598)
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


def forward_machine(theta_deg: float, psi_deg: float) -> np.ndarray:
    theta = math.radians(theta_deg)
    psi = math.radians(psi_deg)
    return np.array(
        [
            -float(model.L1_MM) * math.cos(theta)
            - float(model.L2_MM) * math.cos(psi),
            float(model.L1_MM) * math.sin(theta)
            + float(model.L2_MM) * math.sin(psi),
        ],
        dtype=np.float64,
    )


def reference_points() -> tuple[list[np.ndarray], list[int]]:
    vertices = [
        forward_machine(theta, psi)
        for _, theta, psi in VERTEX_ANGLES
    ]
    points = [vertices[0]]
    edge_for_point = [-1]
    for edge_index, segment_count in enumerate(EDGE_SEGMENTS):
        start = vertices[edge_index]
        end = vertices[(edge_index + 1) % len(vertices)]
        for segment_index in range(1, segment_count + 1):
            ratio = segment_index / segment_count
            points.append(start + (end - start) * ratio)
            edge_for_point.append(edge_index)
    return points, edge_for_point


def machine_to_steps(machine_point: np.ndarray, label: str) -> tuple[int, int]:
    user_x = np.float32(machine_point[0] - float(model.OFFSET_X_MM))
    user_y = np.float32(machine_point[1] - float(model.OFFSET_Y_MM))
    theta, psi = model.inverse(float(user_x), float(user_y))
    stage1 = model.lroundf(
        np.float32(theta * model.STAGE1_STEPS_PER_DEG)
    )
    stage2 = model.lroundf(
        np.float32(psi * model.STAGE2_STEPS_PER_DEG)
    )
    quantized_theta = stage1 / float(model.STAGE1_STEPS_PER_DEG)
    quantized_psi = stage2 / float(model.STAGE2_STEPS_PER_DEG)
    model.check_pose(quantized_theta, quantized_psi, label)

    runtime_theta = np.float32(stage1) / model.STAGE1_STEPS_PER_DEG
    runtime_psi = np.float32(stage2) / model.STAGE2_STEPS_PER_DEG
    if model.lroundf(
        np.float32(runtime_theta * model.STAGE1_STEPS_PER_DEG)
    ) != stage1:
        raise AssertionError(f"{label}: Stage1 float round-trip changed")
    if model.lroundf(
        np.float32(runtime_psi * model.STAGE2_STEPS_PER_DEG)
    ) != stage2:
        raise AssertionError(f"{label}: Stage2 float round-trip changed")
    return stage1, stage2


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
    stage1 = model.lroundf(
        np.float32(theta * model.STAGE1_STEPS_PER_DEG)
    )
    stage2 = model.lroundf(
        np.float32(psi * model.STAGE2_STEPS_PER_DEG)
    )
    return model.State(stage1, stage2, stage2, 0, 1, 1)


def next_state(prior: model.State, target: tuple[int, int]) -> model.State:
    stage1, stage2 = target
    stage1_dir = model.step_direction(
        stage1 - prior.stage1_steps, prior.stage1_dir
    )
    stage2_dir = model.step_direction(
        stage2 - prior.stage2_motor_steps, prior.stage2_motor_dir
    )
    return model.State(stage1, stage2, stage2, 0, stage1_dir, stage2_dir)


def point_line_distance(
    point: tuple[float, float], start: np.ndarray, end: np.ndarray
) -> float:
    direction = end - start
    length = float(np.linalg.norm(direction))
    relative = np.asarray(point, dtype=np.float64) - start
    return abs(
        direction[0] * relative[1] - direction[1] * relative[0]
    ) / length


def verify_path(
    edge_for_point: list[int],
    targets: list[tuple[int, int]],
) -> None:
    vertices = [
        forward_machine(theta, psi)
        - np.array(
            [float(model.OFFSET_X_MM), float(model.OFFSET_Y_MM)]
        )
        for _, theta, psi in VERTEX_ANGLES
    ]
    state = initial_state()
    total_pulses = 0
    approach_pulses = 0
    max_deviation = [0.0] * len(EDGE_SEGMENTS)
    theta_values: list[float] = []
    psi_values: list[float] = []
    beta_values: list[float] = []

    for point_index, target_steps in enumerate(targets):
        target = next_state(state, target_steps)
        pulse_path = model.dda_user_points(
            state, target, f"path[{point_index}]"
        )
        pulses = len(pulse_path) - 1
        total_pulses += pulses
        if point_index == 0:
            approach_pulses = pulses
        else:
            edge_index = edge_for_point[point_index]
            for pulse_point in pulse_path:
                max_deviation[edge_index] = max(
                    max_deviation[edge_index],
                    point_line_distance(
                        pulse_point,
                        vertices[edge_index],
                        vertices[(edge_index + 1) % len(vertices)],
                    ),
                )

        theta = target.stage1_steps / float(model.STAGE1_STEPS_PER_DEG)
        psi = target.stage2_motor_steps / float(model.STAGE2_STEPS_PER_DEG)
        theta_values.append(theta)
        psi_values.append(psi)
        beta_values.append(psi - theta)
        state = target

    if len(targets) != 257:
        raise AssertionError(f"expected 257 points, got {len(targets)}")
    if any(targets[index] == targets[index - 1]
           for index in range(1, len(targets))):
        raise AssertionError("adjacent offline targets must be distinct")
    if targets[0] != targets[-1]:
        raise AssertionError("closed path does not return to P5")
    if state.bias_steps != 0:
        raise AssertionError("direction compensation must remain disabled")
    if max(max_deviation) > 0.10:
        raise AssertionError(
            f"integer-pulse line deviation {max(max_deviation):.6f} mm"
        )

    print(
        "PASS: 257 offline-IK targets and every synchronized integer pulse "
        "satisfy the enlarged probe limits"
    )
    print(
        f"approach_pulses={approach_pulses} "
        f"draw_pulses={total_pulses - approach_pulses} "
        f"total_pulses={total_pulses}"
    )
    print(
        f"theta={min(theta_values):.3f}..{max(theta_values):.3f} "
        f"psi={min(psi_values):.3f}..{max(psi_values):.3f} "
        f"beta={min(beta_values):.3f}..{max(beta_values):.3f} deg"
    )
    print(
        "max_integer_line_deviation_mm="
        + ",".join(f"{value:.4f}" for value in max_deviation)
    )
    print(
        "corners="
        + ",".join(
            f"{index}:{targets[index][0]}/{targets[index][1]}"
            for index in CORNER_INDICES
        )
    )
    print("pen=UP_APPROACH,DOWN_DRAW,UP_DONE gcode=DISABLED")


def render_header(targets: list[tuple[int, int]]) -> str:
    corner_labels = {
        0: "P5_TL start",
        75: "P6_TR",
        128: "P7_BR",
        203: "P8_BL",
        256: "P5_TL close",
    }
    lines = [
        "/**",
        " * @file    a4_75x53_draw_path.h",
        " * @brief   Generated 1 mm offline-IK joint path for the 75 x 53 mm rectangle.",
        " */",
        "#ifndef A4_75X53_DRAW_PATH_H",
        "#define A4_75X53_DRAW_PATH_H",
        "",
        "#include <stdint.h>",
        "",
        "#define A4_75X53_DRAW_PATH_POINT_COUNT (257u)",
        "#define A4_75X53_DRAW_PATH_SEGMENT_COUNT (256u)",
        "#define A4_75X53_DRAW_P6_INDEX (75u)",
        "#define A4_75X53_DRAW_P7_INDEX (128u)",
        "#define A4_75X53_DRAW_P8_INDEX (203u)",
        "#define A4_75X53_DRAW_CLOSE_INDEX (256u)",
        "",
        "typedef struct {",
        "    int16_t stage1_steps;",
        "    int16_t stage2_steps;",
        "} a4_75x53_draw_target_t;",
        "",
        "static const a4_75x53_draw_target_t",
        "    s_a4_75x53_draw_path[A4_75X53_DRAW_PATH_POINT_COUNT] = {",
    ]
    for index, (stage1, stage2) in enumerate(targets):
        if index in corner_labels:
            lines.append(f"    /* {index}: {corner_labels[index]} */")
        lines.append(f"    {{{stage1}, {stage2}}},")
    lines.extend(["};", "", "#endif /* A4_75X53_DRAW_PATH_H */", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write-header",
        type=Path,
        nargs="?",
        const=DEFAULT_HEADER,
        help="write the generated C path header",
    )
    args = parser.parse_args()

    configure_model()
    machine_points, edge_for_point = reference_points()
    targets = [
        machine_to_steps(point, f"target[{index}]")
        for index, point in enumerate(machine_points)
    ]
    verify_path(edge_for_point, targets)

    if args.write_header is not None:
        output_path = args.write_header.resolve()
        output_path.write_text(render_header(targets), encoding="ascii")
        print(f"wrote={output_path}")

    expected_header = render_header(targets)
    if not DEFAULT_HEADER.exists():
        raise AssertionError(f"generated header missing: {DEFAULT_HEADER}")
    if DEFAULT_HEADER.read_text(encoding="ascii") != expected_header:
        raise AssertionError(
            "generated path header is stale; run with --write-header"
        )
    print(f"header_sync=PASS path={DEFAULT_HEADER}")


if __name__ == "__main__":
    main()
