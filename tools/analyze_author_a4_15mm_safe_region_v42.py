#!/usr/bin/env python3
"""Find conservative rectangles inside the author-layout A4 15 mm inset."""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass

import check_author_text_demo_v30 as v30


PAPER_X0 = 15.0
PAPER_X1 = 282.0
PAPER_Y0 = 15.0
PAPER_Y1 = 195.0
SHIFT_X = 136.0
SHIFT_Y = -38.0
AUX_TOGGLE_COMMAND_X_MIN = 150.0


@dataclass(frozen=True)
class Rectangle:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        return self.width * self.height


def quantized_metrics(paper_x: float, paper_y: float) -> tuple[float, float, float, float]:
    model = v30.v21.base
    command_x = paper_x + SHIFT_X
    command_y = paper_y + SHIFT_Y
    if command_x < AUX_TOGGLE_COMMAND_X_MIN:
        raise ValueError("below empirical auxiliary-toggle command-X guard")
    theta, psi = model.inverse(command_x, command_y)
    stage1 = model.lroundf(theta * model.STAGE1_STEPS_PER_DEG)
    stage2 = model.lroundf(psi * model.STAGE2_STEPS_PER_DEG)
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
    normalized_jacobian = abs(math.sin(math.radians(beta)))
    return theta, psi, margin, normalized_jacobian


def safe_cell(x0: int, y0: int, margin_deg: float) -> bool:
    for dx, dy in (
        (0.0, 0.0),
        (0.5, 0.0),
        (1.0, 0.0),
        (0.0, 0.5),
        (0.5, 0.5),
        (1.0, 0.5),
        (0.0, 1.0),
        (0.5, 1.0),
        (1.0, 1.0),
    ):
        try:
            _, _, margin, _ = quantized_metrics(x0 + dx, y0 + dy)
        except ValueError:
            return False
        if margin < margin_deg:
            return False
    return True


def build_cells(margin_deg: float) -> list[list[bool]]:
    return [
        [
            safe_cell(x, y, margin_deg)
            for x in range(int(PAPER_X0), int(PAPER_X1))
        ]
        for y in range(int(PAPER_Y0), int(PAPER_Y1))
    ]


def largest_rectangle(cells: list[list[bool]]) -> Rectangle:
    rows = len(cells)
    columns = len(cells[0])
    heights = [0] * columns
    best_area = 0
    best = (0, 0, 0, 0)
    for row in range(rows):
        for column in range(columns):
            heights[column] = heights[column] + 1 if cells[row][column] else 0
        stack: list[tuple[int, int]] = []
        for column in range(columns + 1):
            height = heights[column] if column < columns else 0
            start = column
            while stack and stack[-1][1] > height:
                left, prior_height = stack.pop()
                area = prior_height * (column - left)
                if area > best_area:
                    best_area = area
                    best = (left, row - prior_height + 1, column, row + 1)
                start = left
            if not stack or stack[-1][1] < height:
                stack.append((start, height))
    x0, y0, x1, y1 = best
    return Rectangle(PAPER_X0 + x0, PAPER_Y0 + y0, PAPER_X0 + x1, PAPER_Y0 + y1)


def rectangle_minimum(rectangle: Rectangle, resolution: float = 0.25) -> tuple[float, tuple[float, float]]:
    minimum = float("inf")
    minimum_at = (0.0, 0.0)
    y = rectangle.y0
    while y <= rectangle.y1 + 1.0e-9:
        x = rectangle.x0
        while x <= rectangle.x1 + 1.0e-9:
            _, _, margin, _ = quantized_metrics(
                min(x, rectangle.x1), min(y, rectangle.y1)
            )
            if margin < minimum:
                minimum = margin
                minimum_at = (min(x, rectangle.x1), min(y, rectangle.y1))
            x += resolution
        y += resolution
    return minimum, minimum_at


def print_corner(label: str, x: float, y: float) -> None:
    theta, psi, margin, normalized_jacobian = quantized_metrics(x, y)
    print(
        f"corner={label} paper=({x:.1f},{y:.1f}) command=({x + SHIFT_X:.1f},{y + SHIFT_Y:.1f}) "
        f"theta={theta:.6f} psi={psi:.6f} beta={psi - theta:.6f} "
        f"margin_deg={margin:.6f} abs_sin_beta={normalized_jacobian:.9f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--margin-deg", type=float, default=20.0)
    args = parser.parse_args()
    if args.margin_deg < 0.0:
        raise ValueError("margin must be nonnegative")
    v30.configure_model()
    for label, x, y in (
        ("PHOTO_DOWN_RIGHT", PAPER_X0, PAPER_Y0),
        ("PHOTO_DOWN_LEFT", PAPER_X0, PAPER_Y1),
        ("PHOTO_UP_RIGHT", PAPER_X1, PAPER_Y0),
        ("PHOTO_UP_LEFT", PAPER_X1, PAPER_Y1),
    ):
        print_corner(label, x, y)
    cells = build_cells(args.margin_deg)
    safe_count = sum(sum(1 for value in row if value) for row in cells)
    total = len(cells) * len(cells[0])
    rectangle = largest_rectangle(cells)
    minimum, minimum_at = rectangle_minimum(rectangle)
    print(
        f"safe_cells={safe_count}/{total} safe_fraction={safe_count / total:.9f} "
        f"required_margin_deg={args.margin_deg:.3f}"
    )
    print(
        f"largest_rectangle paper=({rectangle.x0:.1f},{rectangle.y0:.1f}).."
        f"({rectangle.x1:.1f},{rectangle.y1:.1f}) size={rectangle.width:.1f}x{rectangle.height:.1f} "
        f"area={rectangle.area:.1f} min_margin_deg={minimum:.6f} "
        f"minimum_at=({minimum_at[0]:.2f},{minimum_at[1]:.2f})"
    )
    print("offline_author_a4_15mm_safe_region_analysis=PASS motion=NONE")


if __name__ == "__main__":
    main()
