"""Generate and verify the V6-axis-aligned full A4 draw path."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

import check_a4_75x53_draw as offline
import check_workspace_square_dircomp as model


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HEADER = ROOT / "TASK" / "a4_297x210_axis_draw_path.h"

MACHINE_VERTICES = (
    ("A4_TL", 0.0, 253.0),
    ("A4_TR", 297.0, 253.0),
    ("A4_BR", 297.0, 43.0),
    ("A4_BL", 0.0, 43.0),
)
EDGE_SEGMENTS = (297, 210, 297, 210)
CORNER_INDICES = (0, 297, 507, 804, 1014)


def reference_points() -> tuple[list[np.ndarray], list[int]]:
    vertices = [
        np.array((x_mm, y_mm), dtype=np.float64)
        for _, x_mm, y_mm in MACHINE_VERTICES
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


def verify_interior() -> None:
    min_margin = (float("inf"), "")
    theta_values: list[float] = []
    psi_values: list[float] = []
    beta_values: list[float] = []

    for machine_x in range(0, 298):
        for machine_y in range(43, 254):
            label = f"interior({machine_x},{machine_y})"
            stage1, stage2 = offline.machine_to_steps(
                np.array((machine_x, machine_y), dtype=np.float64),
                label,
            )
            theta = stage1 / float(model.STAGE1_STEPS_PER_DEG)
            psi = stage2 / float(model.STAGE2_STEPS_PER_DEG)
            beta = psi - theta
            margin = min(
                theta - float(model.THETA_MIN_DEG),
                float(model.THETA_MAX_DEG) - theta,
                psi - float(model.PSI_MIN_DEG),
                float(model.PSI_MAX_DEG) - psi,
                beta - float(model.BETA_MIN_DEG),
                float(model.BETA_MAX_DEG) - beta,
            )
            if margin < min_margin[0]:
                min_margin = (margin, label)
            theta_values.append(theta)
            psi_values.append(psi)
            beta_values.append(beta)

    if min_margin[0] < 4.5:
        raise AssertionError(
            f"full A4 joint margin too small: {min_margin[0]:.6f} deg"
        )
    print(
        "interior_grid=298x211 PASS "
        f"min_joint_margin={min_margin[0]:.6f}deg at {min_margin[1]}"
    )
    print(
        f"interior theta={min(theta_values):.3f}..{max(theta_values):.3f} "
        f"psi={min(psi_values):.3f}..{max(psi_values):.3f} "
        f"beta={min(beta_values):.3f}..{max(beta_values):.3f} deg"
    )


def verify_boundary(
    edge_for_point: list[int], targets: list[tuple[int, int]]
) -> None:
    vertices = [
        np.array((x_mm, y_mm), dtype=np.float64)
        - np.array(
            [float(model.OFFSET_X_MM), float(model.OFFSET_Y_MM)]
        )
        for _, x_mm, y_mm in MACHINE_VERTICES
    ]
    state = offline.initial_state()
    total_pulses = 0
    approach_pulses = 0
    max_deviation = [0.0] * len(EDGE_SEGMENTS)
    theta_values: list[float] = []
    psi_values: list[float] = []
    beta_values: list[float] = []

    for point_index, target_steps in enumerate(targets):
        target = offline.next_state(state, target_steps)
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
                    offline.point_line_distance(
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

    if len(targets) != 1015:
        raise AssertionError(f"expected 1015 points, got {len(targets)}")
    if any(
        targets[index] == targets[index - 1]
        for index in range(1, len(targets))
    ):
        raise AssertionError("adjacent offline targets must be distinct")
    if targets[0] != targets[-1]:
        raise AssertionError("closed path does not return to A4_TL")
    if state.bias_steps != 0:
        raise AssertionError("direction compensation must remain disabled")
    if max(max_deviation) > 0.10:
        raise AssertionError(
            f"integer-pulse line deviation {max(max_deviation):.6f} mm"
        )

    print(
        "PASS: 1015 offline-IK boundary targets and every synchronized "
        "integer pulse satisfy the enlarged probe limits"
    )
    print(
        f"approach_pulses={approach_pulses} "
        f"draw_pulses={total_pulses - approach_pulses} "
        f"total_pulses={total_pulses}"
    )
    print(
        f"boundary theta={min(theta_values):.3f}..{max(theta_values):.3f} "
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
    print("machine_workspace=X0..297,Y43..253 axis=V6_XY")
    print("pen=UP_APPROACH,DOWN_DRAW,UP_DONE gcode=DISABLED")


def render_header(targets: list[tuple[int, int]]) -> str:
    corner_labels = {
        0: "A4_TL start",
        297: "A4_TR",
        507: "A4_BR",
        804: "A4_BL",
        1014: "A4_TL close",
    }
    lines = [
        "/**",
        " * @file    a4_297x210_axis_draw_path.h",
        " * @brief   Generated 1 mm offline-IK path for a V6-axis-aligned A4 boundary.",
        " */",
        "#ifndef A4_297X210_AXIS_DRAW_PATH_H",
        "#define A4_297X210_AXIS_DRAW_PATH_H",
        "",
        "#include <stdint.h>",
        "",
        "#define A4_297X210_DRAW_PATH_POINT_COUNT (1015u)",
        "#define A4_297X210_DRAW_PATH_SEGMENT_COUNT (1014u)",
        "#define A4_297X210_DRAW_TR_INDEX (297u)",
        "#define A4_297X210_DRAW_BR_INDEX (507u)",
        "#define A4_297X210_DRAW_BL_INDEX (804u)",
        "#define A4_297X210_DRAW_CLOSE_INDEX (1014u)",
        "",
        "typedef struct {",
        "    int16_t stage1_steps;",
        "    int16_t stage2_steps;",
        "} a4_297x210_axis_draw_target_t;",
        "",
        "static const a4_297x210_axis_draw_target_t",
        "    s_a4_297x210_axis_draw_path[A4_297X210_DRAW_PATH_POINT_COUNT] = {",
    ]
    for index, (stage1, stage2) in enumerate(targets):
        if index in corner_labels:
            lines.append(f"    /* {index}: {corner_labels[index]} */")
        lines.append(f"    {{{stage1}, {stage2}}},")
    lines.extend(
        ["};", "", "#endif /* A4_297X210_AXIS_DRAW_PATH_H */", ""]
    )
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

    offline.configure_model()
    machine_points, edge_for_point = reference_points()
    targets = [
        offline.machine_to_steps(point, f"target[{index}]")
        for index, point in enumerate(machine_points)
    ]
    verify_interior()
    verify_boundary(edge_for_point, targets)

    expected_header = render_header(targets)
    if args.write_header is not None:
        output_path = args.write_header.resolve()
        output_path.write_text(expected_header, encoding="ascii")
        print(f"wrote={output_path}")

    if not DEFAULT_HEADER.exists():
        raise AssertionError(f"generated header missing: {DEFAULT_HEADER}")
    if DEFAULT_HEADER.read_text(encoding="ascii") != expected_header:
        raise AssertionError(
            "generated path header is stale; run with --write-header"
        )
    print(f"header_sync=PASS path={DEFAULT_HEADER}")


if __name__ == "__main__":
    main()
