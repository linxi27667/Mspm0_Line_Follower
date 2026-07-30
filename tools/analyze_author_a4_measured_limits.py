"""Find safe author-frame rectangles from the measured V15 limit angles."""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass


L1_MM = 200.0
L2_MM = 200.0
AUTHOR_OFFSET_X_MM = -129.0
AUTHOR_OFFSET_Y_MM = 128.0
A4_WIDTH_MM = 297.0
A4_HEIGHT_MM = 210.0

STAGE1_STEPS_PER_DEG = 43.708318
STAGE2_STEPS_PER_DEG = 48.8
CAL_THETA_DEG = 0.0
CAL_PSI_DEG = 135.0

STAGE1_INITIAL_SEARCH_STEPS = 31
STAGE2_INITIAL_SEARCH_STEPS = 33
STAGE1_FINAL_AWAY_STEPS = 52
STAGE2_FINAL_AWAY_STEPS = 57

HOMING_CLEARANCE_DEG = 1.0
OPERATING_MARGIN_DEG = 0.25
THETA_MAX_DEG = 135.0
PSI_MAX_DEG = 255.0
BETA_MIN_DEG = 1.0
BETA_MAX_DEG = 179.0


@dataclass(frozen=True)
class Pose:
    work_x_mm: float
    work_y_mm: float
    raw_x_mm: float
    raw_y_mm: float
    stage1_steps: int
    stage2_steps: int
    theta_deg: float
    psi_deg: float
    beta_deg: float
    margin_deg: float


@dataclass(frozen=True)
class Rectangle:
    x0_mm: float
    y0_mm: float
    x1_mm: float
    y1_mm: float

    @property
    def width_mm(self) -> float:
        return self.x1_mm - self.x0_mm

    @property
    def height_mm(self) -> float:
        return self.y1_mm - self.y0_mm

    @property
    def area_mm2(self) -> float:
        return self.width_mm * self.height_mm


def lround(value: float) -> int:
    if value >= 0.0:
        return math.floor(value + 0.5)
    return math.ceil(value - 0.5)


def inverse_raw(raw_x_mm: float, raw_y_mm: float) -> tuple[float, float]:
    standard_x = -raw_x_mm
    standard_y = raw_y_mm
    radius_sq = standard_x * standard_x + standard_y * standard_y
    c2 = (radius_sq - L1_MM * L1_MM - L2_MM * L2_MM) / (
        2.0 * L1_MM * L2_MM
    )
    if c2 < -1.0 or c2 > 1.0:
        raise ValueError("outside radial reach")
    s2 = math.sqrt(max(0.0, 1.0 - c2 * c2))
    k1 = L1_MM * L1_MM + L2_MM * L2_MM * c2
    k2 = L2_MM * L2_MM * s2
    theta = math.atan2(k1, k2) - math.atan2(standard_x, standard_y)
    psi = theta + math.atan2(s2, c2)
    return math.degrees(theta), math.degrees(psi)


def forward_raw(theta_deg: float, psi_deg: float) -> tuple[float, float]:
    theta = math.radians(theta_deg)
    psi = math.radians(psi_deg)
    return (
        -L1_MM * math.cos(theta) - L2_MM * math.cos(psi),
        L1_MM * math.sin(theta) + L2_MM * math.sin(psi),
    )


THETA_LIMIT_DEG = CAL_THETA_DEG - (
    STAGE1_INITIAL_SEARCH_STEPS / STAGE1_STEPS_PER_DEG
)
PSI_LIMIT_DEG = CAL_PSI_DEG - (
    STAGE2_INITIAL_SEARCH_STEPS / STAGE2_STEPS_PER_DEG
)
THETA_SAFE_MIN_DEG = THETA_LIMIT_DEG + HOMING_CLEARANCE_DEG
PSI_SAFE_MIN_DEG = PSI_LIMIT_DEG + HOMING_CLEARANCE_DEG


def quantized_pose(work_x_mm: float, work_y_mm: float) -> Pose:
    raw_x = work_x_mm + AUTHOR_OFFSET_X_MM
    raw_y = work_y_mm + AUTHOR_OFFSET_Y_MM
    theta, psi = inverse_raw(raw_x, raw_y)
    stage1 = lround(theta * STAGE1_STEPS_PER_DEG)
    stage2 = lround(psi * STAGE2_STEPS_PER_DEG)
    quantized_theta = stage1 / STAGE1_STEPS_PER_DEG
    quantized_psi = stage2 / STAGE2_STEPS_PER_DEG
    beta = quantized_psi - quantized_theta
    margin = min(
        quantized_theta - THETA_SAFE_MIN_DEG,
        THETA_MAX_DEG - quantized_theta,
        quantized_psi - PSI_SAFE_MIN_DEG,
        PSI_MAX_DEG - quantized_psi,
        beta - BETA_MIN_DEG,
        BETA_MAX_DEG - beta,
    )
    fk_x, fk_y = forward_raw(quantized_theta, quantized_psi)
    if math.hypot(fk_x - raw_x, fk_y - raw_y) > 0.09:
        raise AssertionError("integer-pulse FK error exceeds 0.09 mm")
    return Pose(
        work_x_mm=work_x_mm,
        work_y_mm=work_y_mm,
        raw_x_mm=raw_x,
        raw_y_mm=raw_y,
        stage1_steps=stage1,
        stage2_steps=stage2,
        theta_deg=quantized_theta,
        psi_deg=quantized_psi,
        beta_deg=beta,
        margin_deg=margin,
    )


def is_operationally_safe(work_x_mm: float, work_y_mm: float) -> bool:
    try:
        pose = quantized_pose(work_x_mm, work_y_mm)
    except (AssertionError, ValueError):
        return False
    return pose.margin_deg >= OPERATING_MARGIN_DEG


def build_safe_cells(resolution_mm: float) -> list[list[bool]]:
    columns = lround(A4_WIDTH_MM / resolution_mm)
    rows = lround(A4_HEIGHT_MM / resolution_mm)
    result: list[list[bool]] = []
    sample_offsets = (
        (0.0, 0.0),
        (0.5, 0.0),
        (1.0, 0.0),
        (0.0, 0.5),
        (0.5, 0.5),
        (1.0, 0.5),
        (0.0, 1.0),
        (0.5, 1.0),
        (1.0, 1.0),
    )
    for row in range(rows):
        y0 = row * resolution_mm
        line: list[bool] = []
        for column in range(columns):
            x0 = column * resolution_mm
            line.append(
                all(
                    is_operationally_safe(
                        x0 + dx * resolution_mm,
                        y0 + dy * resolution_mm,
                    )
                    for dx, dy in sample_offsets
                )
            )
        result.append(line)
    return result


def largest_rectangle(
    cells: list[list[bool]], resolution_mm: float
) -> Rectangle:
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
                    best = (
                        left,
                        row - prior_height + 1,
                        column,
                        row + 1,
                    )
                start = left
            if not stack or stack[-1][1] < height:
                stack.append((start, height))

    x0, y0, x1, y1 = best
    return Rectangle(
        x0 * resolution_mm,
        y0 * resolution_mm,
        x1 * resolution_mm,
        y1 * resolution_mm,
    )


def prefix_sums(cells: list[list[bool]]) -> list[list[int]]:
    rows = len(cells)
    columns = len(cells[0])
    prefix = [[0] * (columns + 1) for _ in range(rows + 1)]
    for row in range(rows):
        running = 0
        for column in range(columns):
            running += 1 if cells[row][column] else 0
            prefix[row + 1][column + 1] = prefix[row][column + 1] + running
    return prefix


def all_safe(
    prefix: list[list[int]], x0: int, y0: int, width: int, height: int
) -> bool:
    safe_count = (
        prefix[y0 + height][x0 + width]
        - prefix[y0][x0 + width]
        - prefix[y0 + height][x0]
        + prefix[y0][x0]
    )
    return safe_count == width * height


def largest_ratio_rectangle(
    cells: list[list[bool]], resolution_mm: float, ratio: float
) -> Rectangle:
    rows = len(cells)
    columns = len(cells[0])
    prefix = prefix_sums(cells)
    for height in range(rows, 0, -1):
        width = lround(height * ratio)
        if width <= 0 or width > columns:
            continue
        for y0 in range(rows - height + 1):
            for x0 in range(columns - width + 1):
                if all_safe(prefix, x0, y0, width, height):
                    return Rectangle(
                        x0 * resolution_mm,
                        y0 * resolution_mm,
                        (x0 + width) * resolution_mm,
                        (y0 + height) * resolution_mm,
                    )
    raise AssertionError("no safe ratio rectangle")


def validate_rectangle(
    rectangle: Rectangle, verification_resolution_mm: float
) -> tuple[float, Pose]:
    minimum_pose: Pose | None = None
    y = rectangle.y0_mm
    while y < rectangle.y1_mm + 1.0e-9:
        x = rectangle.x0_mm
        while x < rectangle.x1_mm + 1.0e-9:
            pose = quantized_pose(
                min(x, rectangle.x1_mm), min(y, rectangle.y1_mm)
            )
            if minimum_pose is None or pose.margin_deg < minimum_pose.margin_deg:
                minimum_pose = pose
            x += verification_resolution_mm
        y += verification_resolution_mm
    if minimum_pose is None or minimum_pose.margin_deg < OPERATING_MARGIN_DEG:
        raise AssertionError(
            f"dense rectangle validation failed margin={minimum_pose.margin_deg if minimum_pose else -999.0:.6f}"
        )
    return minimum_pose.margin_deg, minimum_pose


def print_pose(label: str, pose: Pose) -> None:
    print(
        f"{label:16s} work=({pose.work_x_mm:7.2f},{pose.work_y_mm:7.2f}) "
        f"raw=({pose.raw_x_mm:7.2f},{pose.raw_y_mm:7.2f}) "
        f"steps=({pose.stage1_steps:6d},{pose.stage2_steps:6d}) "
        f"theta={pose.theta_deg:8.3f} psi={pose.psi_deg:8.3f} "
        f"beta={pose.beta_deg:8.3f} margin={pose.margin_deg:8.3f}"
    )


def print_rectangle(
    label: str, rectangle: Rectangle, verification_resolution_mm: float
) -> None:
    margin, minimum_pose = validate_rectangle(
        rectangle, verification_resolution_mm
    )
    print(
        f"{label} x={rectangle.x0_mm:.2f}..{rectangle.x1_mm:.2f} "
        f"y={rectangle.y0_mm:.2f}..{rectangle.y1_mm:.2f} "
        f"size={rectangle.width_mm:.2f}x{rectangle.height_mm:.2f} "
        f"area={rectangle.area_mm2:.2f} min_margin_deg={margin:.3f} "
        f"at=({minimum_pose.work_x_mm:.2f},{minimum_pose.work_y_mm:.2f})"
    )
    for name, x, y in (
        ("BL", rectangle.x0_mm, rectangle.y0_mm),
        ("BR", rectangle.x1_mm, rectangle.y0_mm),
        ("TR", rectangle.x1_mm, rectangle.y1_mm),
        ("TL", rectangle.x0_mm, rectangle.y1_mm),
    ):
        print_pose(f"  {label}_{name}", quantized_pose(x, y))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resolution-mm", type=float, default=1.0)
    parser.add_argument("--verify-resolution-mm", type=float, default=0.25)
    parser.add_argument(
        "--operating-margin-deg", type=float, default=OPERATING_MARGIN_DEG
    )
    return parser.parse_args()


def main() -> None:
    global OPERATING_MARGIN_DEG

    args = parse_args()
    if (
        args.resolution_mm <= 0.0
        or args.verify_resolution_mm <= 0.0
        or args.operating_margin_deg < 0.0
    ):
        raise ValueError("resolutions must be positive and margin nonnegative")
    OPERATING_MARGIN_DEG = args.operating_margin_deg
    if not math.isclose(
        A4_WIDTH_MM / args.resolution_mm,
        round(A4_WIDTH_MM / args.resolution_mm),
        abs_tol=1.0e-9,
    ) or not math.isclose(
        A4_HEIGHT_MM / args.resolution_mm,
        round(A4_HEIGHT_MM / args.resolution_mm),
        abs_tol=1.0e-9,
    ):
        raise ValueError("resolution must divide both A4 dimensions")

    theta_home = THETA_LIMIT_DEG + (
        STAGE1_FINAL_AWAY_STEPS / STAGE1_STEPS_PER_DEG
    )
    psi_home = PSI_LIMIT_DEG + (
        STAGE2_FINAL_AWAY_STEPS / STAGE2_STEPS_PER_DEG
    )
    print(
        f"contract author_offset=({AUTHOR_OFFSET_X_MM:.0f},{AUTHOR_OFFSET_Y_MM:.0f}) "
        f"A4={A4_WIDTH_MM:.0f}x{A4_HEIGHT_MM:.0f} "
        f"steps_per_deg=({STAGE1_STEPS_PER_DEG:.6f},{STAGE2_STEPS_PER_DEG:.1f})"
    )
    print(
        f"measured initial_search=({STAGE1_INITIAL_SEARCH_STEPS},{STAGE2_INITIAL_SEARCH_STEPS}) "
        f"limit=({THETA_LIMIT_DEG:.6f},{PSI_LIMIT_DEG:.6f}) "
        f"final_away=({STAGE1_FINAL_AWAY_STEPS},{STAGE2_FINAL_AWAY_STEPS}) "
        f"home=({theta_home:.6f},{psi_home:.6f})"
    )
    print(
        f"safety hard_min=({THETA_SAFE_MIN_DEG:.6f},{PSI_SAFE_MIN_DEG:.6f}) "
        f"operating_margin={OPERATING_MARGIN_DEG:.2f}deg"
    )

    corners = (
        ("A4_BL", 0.0, 0.0),
        ("A4_BR", A4_WIDTH_MM, 0.0),
        ("A4_TR", A4_WIDTH_MM, A4_HEIGHT_MM),
        ("A4_TL", 0.0, A4_HEIGHT_MM),
    )
    for label, x, y in corners:
        print_pose(label, quantized_pose(x, y))

    cells = build_safe_cells(args.resolution_mm)
    safe_cells = sum(sum(1 for value in row if value) for row in cells)
    total_cells = len(cells) * len(cells[0])
    print(
        f"grid resolution={args.resolution_mm:.3f}mm safe_cells={safe_cells}/{total_cells} "
        f"safe_fraction={safe_cells / total_cells:.6f}"
    )

    any_rectangle = largest_rectangle(cells, args.resolution_mm)
    a4_ratio_rectangle = largest_ratio_rectangle(
        cells, args.resolution_mm, A4_WIDTH_MM / A4_HEIGHT_MM
    )
    square = largest_ratio_rectangle(cells, args.resolution_mm, 1.0)
    print_rectangle("MAX_AREA", any_rectangle, args.verify_resolution_mm)
    print_rectangle("MAX_A4_RATIO", a4_ratio_rectangle, args.verify_resolution_mm)
    print_rectangle("MAX_SQUARE", square, args.verify_resolution_mm)
    print("offline_author_frame_analysis=PASS motion=NONE")


if __name__ == "__main__":
    main()
