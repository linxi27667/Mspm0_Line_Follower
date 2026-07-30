#!/usr/bin/env python3
"""Audit dead-zone and kinematic-singularity margins for the full A4 layout."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import check_author_text_demo_v30 as v30
import check_diary_notebook_repositioned_a4_preview as checked
import generate_diary_notebook_repositioned_a4_preview as full


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = (
    ROOT
    / "docs"
    / "diagnostics"
    / "DIARY_NOTEBOOK_REPOSITIONED_A4_SINGULARITY_AUDIT_20260721.json"
)


@dataclass
class Extrema:
    minimum: float = float("inf")
    minimum_at: tuple[float, float] | None = None
    maximum: float = float("-inf")
    maximum_at: tuple[float, float] | None = None

    def add(self, value: float, paper_xy: tuple[float, float]) -> None:
        if value < self.minimum:
            self.minimum = value
            self.minimum_at = paper_xy
        if value > self.maximum:
            self.maximum = value
            self.maximum_at = paper_xy

    def record(self) -> dict[str, object]:
        return {
            "minimum": self.minimum,
            "minimum_at_paper_mm": list(self.minimum_at) if self.minimum_at else None,
            "maximum": self.maximum,
            "maximum_at_paper_mm": list(self.maximum_at) if self.maximum_at else None,
        }


class Metrics:
    def __init__(self) -> None:
        self.theta = Extrema()
        self.psi = Extrema()
        self.beta = Extrema()
        self.radius = Extrema()
        self.theta_lower = Extrema()
        self.theta_upper = Extrema()
        self.psi_lower = Extrema()
        self.psi_upper = Extrema()
        self.beta_from_zero = Extrema()
        self.beta_from_180 = Extrema()
        self.inner_radius_gap = Extrema()
        self.outer_radius_gap = Extrema()
        self.normalized_jacobian = Extrema()
        self.jacobian_condition = Extrema()
        self.pose_margin = Extrema()
        self.samples = 0

    def add_angles(
        self,
        theta_deg: float,
        psi_deg: float,
        paper_xy: tuple[float, float],
    ) -> None:
        model = v30.v21.base
        beta_deg = psi_deg - theta_deg
        theta_rad = math.radians(theta_deg)
        psi_rad = math.radians(psi_deg)
        raw_x = -float(model.L1_MM) * math.cos(theta_rad) - float(
            model.L2_MM
        ) * math.cos(psi_rad)
        raw_y = float(model.L1_MM) * math.sin(theta_rad) + float(
            model.L2_MM
        ) * math.sin(psi_rad)
        radius = math.hypot(raw_x, raw_y)
        inner_radius = abs(float(model.L1_MM) - float(model.L2_MM))
        outer_radius = float(model.L1_MM) + float(model.L2_MM)
        normalized_jacobian = abs(math.sin(math.radians(beta_deg)))

        l1_sq = float(model.L1_MM) ** 2
        l2_sq = float(model.L2_MM) ** 2
        cross = float(model.L1_MM) * float(model.L2_MM) * math.cos(
            math.radians(beta_deg)
        )
        trace = l1_sq + l2_sq
        discriminant = math.sqrt((l1_sq - l2_sq) ** 2 + 4.0 * cross * cross)
        eigen_max = (trace + discriminant) / 2.0
        eigen_min = (trace - discriminant) / 2.0
        condition = math.sqrt(eigen_max / eigen_min)

        margins = (
            theta_deg - float(model.THETA_MIN_DEG),
            float(model.THETA_MAX_DEG) - theta_deg,
            psi_deg - float(model.PSI_MIN_DEG),
            float(model.PSI_MAX_DEG) - psi_deg,
            beta_deg - float(model.BETA_MIN_DEG),
            float(model.BETA_MAX_DEG) - beta_deg,
        )
        self.theta.add(theta_deg, paper_xy)
        self.psi.add(psi_deg, paper_xy)
        self.beta.add(beta_deg, paper_xy)
        self.radius.add(radius, paper_xy)
        self.theta_lower.add(margins[0], paper_xy)
        self.theta_upper.add(margins[1], paper_xy)
        self.psi_lower.add(margins[2], paper_xy)
        self.psi_upper.add(margins[3], paper_xy)
        self.beta_from_zero.add(beta_deg, paper_xy)
        self.beta_from_180.add(180.0 - beta_deg, paper_xy)
        self.inner_radius_gap.add(radius - inner_radius, paper_xy)
        self.outer_radius_gap.add(outer_radius - radius, paper_xy)
        self.normalized_jacobian.add(normalized_jacobian, paper_xy)
        self.jacobian_condition.add(condition, paper_xy)
        self.pose_margin.add(min(margins), paper_xy)
        self.samples += 1

    def record(self) -> dict[str, object]:
        return {
            "samples": self.samples,
            "theta_deg": self.theta.record(),
            "psi_deg": self.psi.record(),
            "beta_deg": self.beta.record(),
            "radius_mm": self.radius.record(),
            "theta_lower_limit_margin_deg": self.theta_lower.record(),
            "theta_upper_limit_margin_deg": self.theta_upper.record(),
            "psi_lower_limit_margin_deg": self.psi_lower.record(),
            "psi_upper_limit_margin_deg": self.psi_upper.record(),
            "beta_distance_from_0deg_singularity": self.beta_from_zero.record(),
            "beta_distance_from_180deg_singularity": self.beta_from_180.record(),
            "inner_radial_singularity_gap_mm": self.inner_radius_gap.record(),
            "outer_radial_singularity_gap_mm": self.outer_radius_gap.record(),
            "normalized_abs_sin_beta": self.normalized_jacobian.record(),
            "jacobian_condition_number": self.jacobian_condition.record(),
            "combined_pose_margin_deg": self.pose_margin.record(),
        }


def add_quantized_command(metrics: Metrics, command_x: float, command_y: float) -> None:
    model = v30.v21.base
    theta, psi = model.inverse(command_x, command_y)
    stage1 = model.lroundf(theta * model.STAGE1_STEPS_PER_DEG)
    stage2 = model.lroundf(psi * model.STAGE2_STEPS_PER_DEG)
    quantized_theta = stage1 / float(model.STAGE1_STEPS_PER_DEG)
    quantized_psi = stage2 / float(model.STAGE2_STEPS_PER_DEG)
    paper_xy = full.command_to_paper(command_x, command_y)
    metrics.add_angles(quantized_theta, quantized_psi, paper_xy)


def scan_paper_grid() -> Metrics:
    metrics = Metrics()
    for paper_x in range(15, 283):
        for paper_y in range(15, 196):
            add_quantized_command(metrics, *full.paper_to_command(paper_x, paper_y))
    return metrics


def add_step_state(metrics: Metrics, stage1: int, stage2: int) -> None:
    model = v30.v21.base
    theta = stage1 / float(model.STAGE1_STEPS_PER_DEG)
    psi = stage2 / float(model.STAGE2_STEPS_PER_DEG)
    user_xy = v30.v21.loop.user_from_steps(stage1, stage2)
    paper_xy = full.command_to_paper(*user_xy)
    metrics.add_angles(theta, psi, paper_xy)


def scan_routed_path(points: tuple[v30.DemoPoint, ...]) -> Metrics:
    metrics = Metrics()
    align = v30.ALIGN_PATH[-1]
    current_nominal = align.xy
    current_steps, _, _ = v30.point_margin(align, "SINGULARITY_ALIGN")
    add_step_state(metrics, *current_steps)

    for point_index, point in enumerate(points):
        target = point.xy
        if target == current_nominal:
            continue
        planned = v30.v21.plan_line(
            current_nominal, target, f"SINGULARITY_MOVE_{point_index}"
        )
        for segment_steps in planned:
            delta1 = segment_steps[0] - current_steps[0]
            delta2 = segment_steps[1] - current_steps[1]
            steps1 = abs(delta1)
            steps2 = abs(delta2)
            master = max(steps1, steps2)
            direction1 = 1 if delta1 > 0 else -1
            direction2 = 1 if delta2 > 0 else -1
            error1 = master // 2
            error2 = master // 2
            for _ in range(master):
                error1 += steps1
                if error1 >= master:
                    error1 -= master
                    current_steps = (current_steps[0] + direction1, current_steps[1])
                error2 += steps2
                if error2 >= master:
                    error2 -= master
                    current_steps = (current_steps[0], current_steps[1] + direction2)
                add_step_state(metrics, *current_steps)
            if current_steps != segment_steps:
                raise AssertionError("DDA state did not reach planned segment")
        current_nominal = target
    return metrics


def require_safe(metrics: Metrics, label: str) -> None:
    if metrics.pose_margin.minimum < 10.0:
        raise AssertionError(
            f"{label}: pose margin {metrics.pose_margin.minimum:.6f} deg"
        )
    if metrics.beta_from_zero.minimum <= 0.0 or metrics.beta_from_180.minimum <= 0.0:
        raise AssertionError(f"{label}: elbow singularity reached")
    if metrics.normalized_jacobian.minimum <= 0.0:
        raise AssertionError(f"{label}: Jacobian determinant reached zero")
    if metrics.inner_radius_gap.minimum <= 0.0 or metrics.outer_radius_gap.minimum <= 0.0:
        raise AssertionError(f"{label}: radial singularity reached")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    v30.configure_model()
    _, _, _, page = full.generate()
    routed, route_stats = checked.route_command_path(page)
    grid = scan_paper_grid()
    path = scan_routed_path(routed)
    require_safe(grid, "paper grid")
    require_safe(path, "routed text path")

    report = {
        "artifact": "DIARY_NOTEBOOK_REPOSITIONED_A4_SINGULARITY_AUDIT_20260721",
        "model": {
            "l1_mm": float(v30.v21.base.L1_MM),
            "l2_mm": float(v30.v21.base.L2_MM),
            "offset_mm": [
                float(v30.v21.base.OFFSET_X_MM),
                float(v30.v21.base.OFFSET_Y_MM),
            ],
            "stage1_steps_per_degree": float(v30.v21.base.STAGE1_STEPS_PER_DEG),
            "stage2_steps_per_degree": float(v30.v21.base.STAGE2_STEPS_PER_DEG),
            "theta_hard_range_deg": [
                float(v30.v21.base.THETA_MIN_DEG),
                float(v30.v21.base.THETA_MAX_DEG),
            ],
            "psi_hard_range_deg": [
                float(v30.v21.base.PSI_MIN_DEG),
                float(v30.v21.base.PSI_MAX_DEG),
            ],
            "beta_hard_range_deg": [
                float(v30.v21.base.BETA_MIN_DEG),
                float(v30.v21.base.BETA_MAX_DEG),
            ],
        },
        "paper_mapping": {
            "usable_paper_rectangle_mm": [15.0, 15.0, 282.0, 195.0],
            "command_shift_mm": [
                full.COMMAND_SHIFT_X_MM,
                full.COMMAND_SHIFT_Y_MM,
            ],
            "align_machine_mm": [full.ALIGN_COMMAND_X_MM, full.ALIGN_COMMAND_Y_MM],
            "align_paper_mm": [full.ALIGN_PAPER_X_MM, full.ALIGN_PAPER_Y_MM],
        },
        "full_paper_grid": grid.record(),
        "routed_text_integer_pulse_path": path.record(),
        "routing": route_stats,
        "conclusion": {
            "ik_dead_zone_reached": False,
            "inner_or_outer_radial_singularity_reached": False,
            "jacobian_singularity_reached": False,
            "joint_hard_limit_reached": False,
            "model_check_passed": True,
            "physical_collision_proven_absent": False,
            "reason_physical_collision_not_proven": (
                "the model contains link geometry and limits, but no bodies for the pen, "
                "paper holder, table, wiring, or self-collision volumes"
            ),
        },
    }
    if args.write:
        REPORT_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    print(
        f"grid_singularity=PASS samples={grid.samples} "
        f"theta_deg={grid.theta.minimum:.6f}..{grid.theta.maximum:.6f} "
        f"psi_deg={grid.psi.minimum:.6f}..{grid.psi.maximum:.6f} "
        f"beta_deg={grid.beta.minimum:.6f}..{grid.beta.maximum:.6f} "
        f"radius_mm={grid.radius.minimum:.6f}..{grid.radius.maximum:.6f}"
    )
    print(
        f"grid_margins=PASS pose_deg={grid.pose_margin.minimum:.6f} "
        f"beta_from_0_deg={grid.beta_from_zero.minimum:.6f} "
        f"beta_from_180_deg={grid.beta_from_180.minimum:.6f} "
        f"inner_radius_gap_mm={grid.inner_radius_gap.minimum:.6f} "
        f"outer_radius_gap_mm={grid.outer_radius_gap.minimum:.6f} "
        f"min_abs_sin_beta={grid.normalized_jacobian.minimum:.9f} "
        f"max_jacobian_condition={grid.jacobian_condition.maximum:.6f}"
    )
    print(
        f"path_singularity=PASS pulse_samples={path.samples} "
        f"pose_margin_deg={path.pose_margin.minimum:.6f} "
        f"beta_deg={path.beta.minimum:.6f}..{path.beta.maximum:.6f} "
        f"beta_from_0_deg={path.beta_from_zero.minimum:.6f} "
        f"beta_from_180_deg={path.beta_from_180.minimum:.6f} "
        f"inner_radius_gap_mm={path.inner_radius_gap.minimum:.6f} "
        f"outer_radius_gap_mm={path.outer_radius_gap.minimum:.6f} "
        f"min_abs_sin_beta={path.normalized_jacobian.minimum:.9f} "
        f"max_jacobian_condition={path.jacobian_condition.maximum:.6f}"
    )
    print(
        "singularity_audit=PASS ik_dead_zone=0 radial_singularity=0 "
        "jacobian_singularity=0 joint_hard_limit=0 physical_collision_proven=0"
    )
    if args.write:
        print(f"report={REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
