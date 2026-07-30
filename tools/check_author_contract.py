"""Verify the DrawBot coordinate contract and generate the pen-up probe path."""

from __future__ import annotations

import argparse
import math
import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MOTION_HEADER = ROOT / "APP" / "Inc" / "app_writer_motion.h"
PROBE_HEADER = ROOT / "TASK" / "author_coordinate_probe_path.h"
SOURCE_ROOT = ROOT.parent / "writer_robot_source"

L1_MM = 200.0
L2_MM = 200.0
AUTHOR_OFFSET_X_MM = -135.0
AUTHOR_OFFSET_Y_MM = 105.0

# Place the paper without moving this machine's measured 0/135-degree limit
# switches. This is a work offset, not part of the author's fixed tower offset.
# It maps the official lower-left paper origin to raw (0, 43), preserving the
# previously checked raw A4 envelope while using the generator's +Y-up frame.
WORK_ORIGIN_X_MM = 135.0
WORK_ORIGIN_Y_MM = -62.0

STAGE1_STEPS_PER_DEG = 43.708318
STAGE2_STEPS_PER_DEG = 48.8
THETA_MIN_DEG = 1.0
THETA_MAX_DEG = 135.0
PSI_MIN_DEG = 136.0
PSI_MAX_DEG = 255.0
BETA_MIN_DEG = 1.0
BETA_MAX_DEG = 179.0

A4_WIDTH_MM = 297.0
A4_HEIGHT_MM = 210.0


@dataclass(frozen=True)
class ProbePoint:
    name: str
    work_x_mm: float
    work_y_mm: float


PROBE_POINTS = (
    ProbePoint("ORIGIN_BL", 0.0, 0.0),
    ProbePoint("X_PLUS_50", 50.0, 0.0),
    ProbePoint("ORIGIN_AFTER_X", 0.0, 0.0),
    ProbePoint("Y_PLUS_50", 0.0, 50.0),
    ProbePoint("ORIGIN_AFTER_Y", 0.0, 0.0),
    ProbePoint("A4_BR", 297.0, 0.0),
    ProbePoint("A4_TR", 297.0, 210.0),
    ProbePoint("A4_TL", 0.0, 210.0),
    ProbePoint("ORIGIN_CLOSE", 0.0, 0.0),
)


@dataclass(frozen=True)
class Target:
    point: ProbePoint
    raw_x_mm: float
    raw_y_mm: float
    stage1_steps: int
    stage2_steps: int
    theta_deg: float
    psi_deg: float


def lround(value: float) -> int:
    if value >= 0.0:
        return math.floor(value + 0.5)
    return math.ceil(value - 0.5)


def work_to_raw(
    work_x_mm: float,
    work_y_mm: float,
    work_origin_x_mm: float = WORK_ORIGIN_X_MM,
    work_origin_y_mm: float = WORK_ORIGIN_Y_MM,
) -> tuple[float, float]:
    return (
        work_x_mm + work_origin_x_mm + AUTHOR_OFFSET_X_MM,
        work_y_mm + work_origin_y_mm + AUTHOR_OFFSET_Y_MM,
    )


def inverse_raw(raw_x_mm: float, raw_y_mm: float) -> tuple[float, float]:
    standard_x = -raw_x_mm
    standard_y = raw_y_mm
    radius_sq = standard_x * standard_x + standard_y * standard_y
    c2 = (radius_sq - L1_MM * L1_MM - L2_MM * L2_MM) / (
        2.0 * L1_MM * L2_MM
    )
    if c2 < -1.0005 or c2 > 1.0005:
        raise ValueError(
            f"unreachable radius raw=({raw_x_mm:.3f},{raw_y_mm:.3f}) "
            f"c2={c2:.6f}"
        )
    c2 = max(-1.0, min(1.0, c2))
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


def pose_margin(theta_deg: float, psi_deg: float) -> float:
    beta_deg = psi_deg - theta_deg
    return min(
        theta_deg - THETA_MIN_DEG,
        THETA_MAX_DEG - theta_deg,
        psi_deg - PSI_MIN_DEG,
        PSI_MAX_DEG - psi_deg,
        beta_deg - BETA_MIN_DEG,
        BETA_MAX_DEG - beta_deg,
    )


def require_safe(theta_deg: float, psi_deg: float, label: str) -> float:
    beta_deg = psi_deg - theta_deg
    margin = pose_margin(theta_deg, psi_deg)
    if (
        margin < -1.0e-6
        or psi_deg <= theta_deg
        or beta_deg < BETA_MIN_DEG
        or beta_deg > BETA_MAX_DEG
    ):
        raise AssertionError(
            f"{label}: unsafe theta={theta_deg:.6f} psi={psi_deg:.6f} "
            f"beta={beta_deg:.6f} margin={margin:.6f}"
        )
    return margin


def quantized_target(point: ProbePoint) -> Target:
    raw_x_mm, raw_y_mm = work_to_raw(point.work_x_mm, point.work_y_mm)
    theta_deg, psi_deg = inverse_raw(raw_x_mm, raw_y_mm)
    stage1_steps = lround(theta_deg * STAGE1_STEPS_PER_DEG)
    stage2_steps = lround(psi_deg * STAGE2_STEPS_PER_DEG)
    quantized_theta = stage1_steps / STAGE1_STEPS_PER_DEG
    quantized_psi = stage2_steps / STAGE2_STEPS_PER_DEG
    require_safe(quantized_theta, quantized_psi, point.name)

    fk_x, fk_y = forward_raw(quantized_theta, quantized_psi)
    if math.hypot(fk_x - raw_x_mm, fk_y - raw_y_mm) > 0.08:
        raise AssertionError(
            f"{point.name}: integer FK error exceeds 0.08 mm"
        )
    return Target(
        point=point,
        raw_x_mm=raw_x_mm,
        raw_y_mm=raw_y_mm,
        stage1_steps=stage1_steps,
        stage2_steps=stage2_steps,
        theta_deg=quantized_theta,
        psi_deg=quantized_psi,
    )


def check_dda(
    start: tuple[int, int],
    end: tuple[int, int],
    label: str,
) -> tuple[int, float]:
    delta1 = end[0] - start[0]
    delta2 = end[1] - start[1]
    steps1 = abs(delta1)
    steps2 = abs(delta2)
    sign1 = 1 if delta1 >= 0 else -1
    sign2 = 1 if delta2 >= 0 else -1
    master = max(steps1, steps2)
    if master == 0:
        theta = start[0] / STAGE1_STEPS_PER_DEG
        psi = start[1] / STAGE2_STEPS_PER_DEG
        return 0, require_safe(theta, psi, label)

    current1, current2 = start
    error1 = master // 2
    error2 = master // 2
    min_margin = float("inf")
    for tick in range(master):
        error1 += steps1
        if error1 >= master:
            error1 -= master
            current1 += sign1
        error2 += steps2
        if error2 >= master:
            error2 -= master
            current2 += sign2
        theta = current1 / STAGE1_STEPS_PER_DEG
        psi = current2 / STAGE2_STEPS_PER_DEG
        margin = require_safe(theta, psi, f"{label}/tick{tick + 1}")
        min_margin = min(min_margin, margin)

    if (current1, current2) != end:
        raise AssertionError(
            f"{label}: DDA ended at {(current1, current2)}, expected {end}"
        )
    return master, min_margin


def nominal_home_steps() -> tuple[int, int]:
    # Homing releases at least one pulse, then adds a one-degree clearance.
    stage1 = 1 + lround(STAGE1_STEPS_PER_DEG)
    stage2 = lround(135.0 * STAGE2_STEPS_PER_DEG)
    stage2 += 1 + lround(STAGE2_STEPS_PER_DEG)
    return stage1, stage2


def a4_boundary_points() -> list[ProbePoint]:
    result = [ProbePoint("BOUNDARY_BL", 0.0, 0.0)]
    for x_mm in range(1, 298):
        result.append(ProbePoint(f"BOUNDARY_B_X{x_mm}", float(x_mm), 0.0))
    for y_mm in range(1, 211):
        result.append(
            ProbePoint(f"BOUNDARY_R_Y{y_mm}", 297.0, float(y_mm))
        )
    for x_mm in range(296, -1, -1):
        result.append(
            ProbePoint(f"BOUNDARY_T_X{x_mm}", float(x_mm), 210.0)
        )
    for y_mm in range(209, -1, -1):
        result.append(
            ProbePoint(f"BOUNDARY_L_Y{y_mm}", 0.0, float(y_mm))
        )
    return result


def macro_float(text: str, name: str) -> float:
    match = re.search(
        rf"^#define\s+{re.escape(name)}\s+\(([-+0-9.]+)f?\)",
        text,
        re.MULTILINE,
    )
    if match is None:
        raise AssertionError(f"missing direct numeric macro {name}")
    return float(match.group(1))


def check_source_contract() -> None:
    text = MOTION_HEADER.read_text(encoding="ascii")
    expected = {
        "APP_WRITER_L1_MM": L1_MM,
        "APP_WRITER_L2_MM": L2_MM,
        "APP_WRITER_MACHINE_OFFSET_X_MM": AUTHOR_OFFSET_X_MM,
        "APP_WRITER_MACHINE_OFFSET_Y_MM": AUTHOR_OFFSET_Y_MM,
        "APP_WRITER_THETA_LIMIT_DEG": 0.0,
        "APP_WRITER_PSI_LIMIT_DEG": 135.0,
        "APP_WRITER_STAGE1_STEPS_PER_DEG": STAGE1_STEPS_PER_DEG,
        "APP_WRITER_STAGE2_STEPS_PER_DEG": STAGE2_STEPS_PER_DEG,
    }
    for name, value in expected.items():
        actual = macro_float(text, name)
        if abs(actual - value) > 1.0e-6:
            raise AssertionError(f"{name}={actual}, expected {value}")
    if "#define APP_WRITER_DIRECTION_COMP_ENABLE     (0u)" not in text:
        raise AssertionError("direction compensation must be disabled")
    print("source_contract=PASS author_offset=-135,105 home_limit=0,135")


WORD_RE = re.compile(r"([A-Z])\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+))", re.I)


def gcode_bounds(path: Path) -> tuple[float, float, float, float, int]:
    absolute = True
    x_mm = 0.0
    y_mm = 0.0
    points: list[tuple[float, float]] = []
    for raw_line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw_line.split(";", 1)[0].upper()
        words = [(letter, float(value)) for letter, value in WORD_RE.findall(line)]
        g_values = [value for letter, value in words if letter == "G"]
        if 90.0 in g_values:
            absolute = True
        if 91.0 in g_values:
            absolute = False
        if not any(value in (0.0, 1.0) for value in g_values):
            continue
        next_x = next((value for letter, value in words if letter == "X"), None)
        next_y = next((value for letter, value in words if letter == "Y"), None)
        if next_x is None and next_y is None:
            continue
        if absolute:
            x_mm = x_mm if next_x is None else next_x
            y_mm = y_mm if next_y is None else next_y
        else:
            x_mm += 0.0 if next_x is None else next_x
            y_mm += 0.0 if next_y is None else next_y
        points.append((x_mm, y_mm))
    if not points:
        raise AssertionError(f"no XY motion in {path}")
    return (
        min(point[0] for point in points),
        max(point[0] for point in points),
        min(point[1] for point in points),
        max(point[1] for point in points),
        len(points),
    )


def report_gcode() -> None:
    for name in ("G_Code.txt.gcode", "2.0.gcode"):
        path = SOURCE_ROOT / name
        if not path.exists():
            print(f"gcode={name} missing")
            continue
        min_x, max_x, min_y, max_y, count = gcode_bounds(path)
        fits = (
            min_x >= 0.0
            and max_x <= A4_WIDTH_MM
            and min_y >= 0.0
            and max_y <= A4_HEIGHT_MM
        )
        print(
            f"gcode={name} points={count} X={min_x:.3f}..{max_x:.3f} "
            f"Y={min_y:.3f}..{max_y:.3f} fits_author_A4={int(fits)}"
        )


def render_header(targets: list[Target]) -> str:
    lines = [
        "/**",
        " * @file    author_coordinate_probe_path.h",
        " * @brief   Generated offline-IK targets for the author A4 work frame.",
        " */",
        "#ifndef AUTHOR_COORDINATE_PROBE_PATH_H",
        "#define AUTHOR_COORDINATE_PROBE_PATH_H",
        "",
        "#include <stdint.h>",
        "",
        f"#define AUTHOR_COORDINATE_PROBE_POINT_COUNT ({len(targets)}u)",
        f"#define AUTHOR_WORK_ORIGIN_X_X10 ({lround(WORK_ORIGIN_X_MM * 10.0)})",
        f"#define AUTHOR_WORK_ORIGIN_Y_X10 ({lround(WORK_ORIGIN_Y_MM * 10.0)})",
        "",
        "typedef struct {",
        "    const char *name;",
        "    int16_t work_x_x10;",
        "    int16_t work_y_x10;",
        "    int16_t raw_x_x10;",
        "    int16_t raw_y_x10;",
        "    int16_t stage1_steps;",
        "    int16_t stage2_steps;",
        "} author_coordinate_probe_target_t;",
        "",
        "static const author_coordinate_probe_target_t",
        "    s_author_coordinate_probe_points[AUTHOR_COORDINATE_PROBE_POINT_COUNT] = {",
    ]
    for target in targets:
        lines.append(
            "    {"
            f'"{target.point.name}", '
            f"{lround(target.point.work_x_mm * 10.0)}, "
            f"{lround(target.point.work_y_mm * 10.0)}, "
            f"{lround(target.raw_x_mm * 10.0)}, "
            f"{lround(target.raw_y_mm * 10.0)}, "
            f"{target.stage1_steps}, {target.stage2_steps}"
            "},"
        )
    lines.extend(
        [
            "};",
            "",
            "#endif /* AUTHOR_COORDINATE_PROBE_PATH_H */",
            "",
        ]
    )
    return "\n".join(lines)


def report_nominal_author_origin() -> None:
    print("author_fixed_offset_without_paper_translation:")
    for point in (
        ProbePoint("BL", 0.0, 0.0),
        ProbePoint("BR", 297.0, 0.0),
        ProbePoint("TR", 297.0, 210.0),
        ProbePoint("TL", 0.0, 210.0),
    ):
        raw_x, raw_y = work_to_raw(
            point.work_x_mm,
            point.work_y_mm,
            work_origin_x_mm=0.0,
            work_origin_y_mm=0.0,
        )
        try:
            theta, psi = inverse_raw(raw_x, raw_y)
            safe = pose_margin(theta, psi) >= 0.0
            print(
                f"  {point.name} raw=({raw_x:.1f},{raw_y:.1f}) "
                f"theta={theta:.2f} psi={psi:.2f} safe={int(safe)}"
            )
        except ValueError as exc:
            print(f"  {point.name} raw=({raw_x:.1f},{raw_y:.1f}) {exc}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write-header",
        action="store_true",
        help="write TASK/author_coordinate_probe_path.h",
    )
    args = parser.parse_args()

    check_source_contract()
    report_nominal_author_origin()

    targets = [quantized_target(point) for point in PROBE_POINTS]
    start = nominal_home_steps()
    total_ticks = 0
    min_margin = float("inf")
    for index, target in enumerate(targets):
        end = (target.stage1_steps, target.stage2_steps)
        ticks, margin = check_dda(start, end, f"probe[{index}]/{target.point.name}")
        total_ticks += ticks
        min_margin = min(min_margin, margin)
        print(
            f"probe[{index + 1}]={target.point.name} "
            f"work=({target.point.work_x_mm:.1f},{target.point.work_y_mm:.1f}) "
            f"raw=({target.raw_x_mm:.1f},{target.raw_y_mm:.1f}) "
            f"steps={target.stage1_steps}/{target.stage2_steps} "
            f"theta={target.theta_deg:.3f} psi={target.psi_deg:.3f}"
        )
        start = end
    print(
        f"probe_integer_dda=PASS points={len(targets)} ticks={total_ticks} "
        f"min_joint_margin_deg={min_margin:.6f} pen=UP_ONLY"
    )

    boundary = [quantized_target(point) for point in a4_boundary_points()]
    start = (boundary[0].stage1_steps, boundary[0].stage2_steps)
    boundary_ticks = 0
    boundary_margin = float("inf")
    for index, target in enumerate(boundary[1:], start=1):
        end = (target.stage1_steps, target.stage2_steps)
        ticks, margin = check_dda(start, end, f"boundary[{index}]")
        boundary_ticks += ticks
        boundary_margin = min(boundary_margin, margin)
        start = end
    print(
        f"author_A4_boundary=PASS work_X=0..297 work_Y=0..210 "
        f"points={len(boundary)} ticks={boundary_ticks} "
        f"min_joint_margin_deg={boundary_margin:.6f}"
    )

    expected_header = render_header(targets)
    if args.write_header:
        PROBE_HEADER.write_text(expected_header, encoding="ascii")
        print(f"wrote={PROBE_HEADER}")
    if not PROBE_HEADER.exists():
        raise AssertionError(f"missing generated header: {PROBE_HEADER}")
    if PROBE_HEADER.read_text(encoding="ascii") != expected_header:
        raise AssertionError(
            "probe header is stale; run tools/check_author_contract.py --write-header"
        )
    print(f"probe_header_sync=PASS path={PROBE_HEADER}")
    report_gcode()


if __name__ == "__main__":
    main()
