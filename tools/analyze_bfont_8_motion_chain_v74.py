#!/usr/bin/env python3
"""Audit the B-font digit 8 through the current paper-map/IK/step chain.

This is an offline diagnostic only.  It does not alter the font or firmware.
The rendered comparison separates source geometry from absolute joint-step
quantization so a physical defect is not incorrectly written into the glyph.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from check_firmware_no_sbow_v31 import firmware_map_no_sbow
from check_workspace_yshift15_v28 import (
    L1_MM,
    L2_MM,
    OFFSET_X_MM,
    OFFSET_Y_MM,
    inverse_user,
)
from kenjoy_gfont import load_gfont


TEST_ID = "BFONT_DIGIT8_MOTION_CHAIN_AUDIT_V74"
FONT_PATH = (
    ROOT / "assets" / "kenjoy_gfont" / "AA_GUO_JINGMING_b7c9ccc1.gfont"
)
FONT_SHA256 = (
    "D5D8E41EF24BF380FDAB57B4746795D691CC4E2DF878A394E4FA8C6D594C09F8"
)
PAPER_CENTER_MM = (105.0, 215.0)
VISIBLE_HEIGHT_MM = 12.0
FIRMWARE_SEGMENT_MM = 1.0
STAGE1_STEPS_PER_DEG = 40.099216
STAGE2_STEPS_PER_DEG = 40.115790
REPORT_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}.json"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}.png"
PIXELS_PER_MM = 36.0


def split_strokes(glyph) -> tuple[tuple[tuple[float, float], ...], ...]:
    strokes: list[list[tuple[float, float]]] = []
    for point, command in zip(glyph.points, glyph.commands):
        if command == 0:
            strokes.append([point])
        elif not strokes:
            raise AssertionError("glyph begins with a draw command")
        elif math.dist(strokes[-1][-1], point) > 1.0e-12:
            strokes[-1].append(point)
    return tuple(tuple(stroke) for stroke in strokes if len(stroke) >= 2)


def place_glyph(glyph) -> tuple[tuple[tuple[float, float], ...], ...]:
    x_min, y_min, x_max, y_max = glyph.bounds
    scale = VISIBLE_HEIGHT_MM / (y_max - y_min)
    width = (x_max - x_min) * scale
    left = PAPER_CENTER_MM[0] - width / 2.0
    bottom = PAPER_CENTER_MM[1] - VISIBLE_HEIGHT_MM / 2.0
    placed = []
    for stroke in split_strokes(glyph):
        placed.append(
            tuple(
                (
                    left + (x - x_min) * scale,
                    bottom + (y - y_min) * scale,
                )
                for x, y in stroke
            )
        )
    return tuple(placed)


def segment_line(
    start: tuple[float, float],
    target: tuple[float, float],
) -> tuple[tuple[float, float], ...]:
    dx = target[0] - start[0]
    dy = target[1] - start[1]
    count = max(1, math.ceil(max(abs(dx), abs(dy)) / FIRMWARE_SEGMENT_MM))
    return tuple(
        (
            start[0] + dx * index / count,
            start[1] + dy * index / count,
        )
        for index in range(1, count + 1)
    )


def firmware_dense_points(
    stroke: tuple[tuple[float, float], ...],
) -> tuple[tuple[float, float], ...]:
    dense = [stroke[0]]
    for start, target in zip(stroke, stroke[1:]):
        dense.extend(segment_line(start, target))
    return tuple(dense)


def forward_user(theta_deg: float, psi_deg: float) -> tuple[float, float]:
    theta = math.radians(theta_deg)
    psi = math.radians(psi_deg)
    machine_x = -L1_MM * math.cos(theta) - L2_MM * math.cos(psi)
    machine_y = L1_MM * math.sin(theta) + L2_MM * math.sin(psi)
    return machine_x - OFFSET_X_MM, machine_y - OFFSET_Y_MM


def inverse_firmware_map(
    target_user: tuple[float, float],
    initial_paper: tuple[float, float],
) -> tuple[float, float]:
    paper_x, paper_y = initial_paper
    epsilon = 0.01
    for _ in range(12):
        current = firmware_map_no_sbow((paper_x, paper_y))
        error_x = target_user[0] - current[0]
        error_y = target_user[1] - current[1]
        if math.hypot(error_x, error_y) < 1.0e-10:
            break
        x_probe = firmware_map_no_sbow((paper_x + epsilon, paper_y))
        y_probe = firmware_map_no_sbow((paper_x, paper_y + epsilon))
        j_xx = (x_probe[0] - current[0]) / epsilon
        j_yx = (x_probe[1] - current[1]) / epsilon
        j_xy = (y_probe[0] - current[0]) / epsilon
        j_yy = (y_probe[1] - current[1]) / epsilon
        determinant = j_xx * j_yy - j_xy * j_yx
        if abs(determinant) < 1.0e-12:
            raise AssertionError("paper-map inverse Jacobian is singular")
        paper_x += (j_yy * error_x - j_xy * error_y) / determinant
        paper_y += (-j_yx * error_x + j_xx * error_y) / determinant
    residual = math.dist(
        firmware_map_no_sbow((paper_x, paper_y)), target_user
    )
    if residual > 1.0e-6:
        raise AssertionError(f"paper-map inverse residual {residual:.9f} mm")
    return paper_x, paper_y


def quantized_paper_point(
    paper: tuple[float, float],
) -> tuple[tuple[float, float], tuple[int, int]]:
    user = firmware_map_no_sbow(paper)
    theta_deg, psi_deg, _ = inverse_user(*user)
    stage1_steps = round(theta_deg * STAGE1_STEPS_PER_DEG)
    stage2_steps = round(psi_deg * STAGE2_STEPS_PER_DEG)
    achieved_user = forward_user(
        stage1_steps / STAGE1_STEPS_PER_DEG,
        stage2_steps / STAGE2_STEPS_PER_DEG,
    )
    return (
        inverse_firmware_map(achieved_user, paper),
        (stage1_steps, stage2_steps),
    )


def polyline_length(points: tuple[tuple[float, float], ...]) -> float:
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def source_corner_angles(
    stroke: tuple[tuple[float, float], ...],
) -> tuple[float, ...]:
    result = []
    for first, middle, last in zip(stroke, stroke[1:], stroke[2:]):
        incoming = (middle[0] - first[0], middle[1] - first[1])
        outgoing = (last[0] - middle[0], last[1] - middle[1])
        incoming_length = math.hypot(*incoming)
        outgoing_length = math.hypot(*outgoing)
        if incoming_length <= 1.0e-12 or outgoing_length <= 1.0e-12:
            continue
        cosine = (
            incoming[0] * outgoing[0] + incoming[1] * outgoing[1]
        ) / (incoming_length * outgoing_length)
        result.append(math.degrees(math.acos(max(-1.0, min(1.0, cosine)))))
    return tuple(result)


def draw_preview(
    source_strokes: tuple[tuple[tuple[float, float], ...], ...],
    quantized_strokes: tuple[tuple[tuple[float, float], ...], ...],
) -> None:
    panel_width = 400
    panel_height = 600
    margin = 42
    image = Image.new("RGB", (panel_width * 3, panel_height), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 22)
        small_font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 17)
    except OSError:
        font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    all_points = [point for stroke in source_strokes for point in stroke]
    x_min = min(point[0] for point in all_points)
    x_max = max(point[0] for point in all_points)
    y_min = min(point[1] for point in all_points)
    y_max = max(point[1] for point in all_points)
    scale = min(
        (panel_width - 2 * margin) / (x_max - x_min),
        (panel_height - 2 * margin - 70) / (y_max - y_min),
    )

    def pixel(
        point: tuple[float, float], panel: int
    ) -> tuple[float, float]:
        return (
            panel * panel_width
            + margin
            + (point[0] - x_min) * scale,
            panel_height - margin - (point[1] - y_min) * scale,
        )

    titles = (
        "B 字体原始“8”",
        "1 mm 分段后（几何不变）",
        "关节脉冲取整后反算",
    )
    for panel, title in enumerate(titles):
        draw.text(
            (panel * panel_width + 18, 15),
            title,
            fill=(25, 25, 25),
            font=font,
        )
        draw.rectangle(
            (
                panel * panel_width + 1,
                1,
                (panel + 1) * panel_width - 2,
                panel_height - 2,
            ),
            outline=(205, 205, 205),
            width=2,
        )

    dense_strokes = tuple(
        firmware_dense_points(stroke) for stroke in source_strokes
    )
    for stroke in source_strokes:
        draw.line(
            [pixel(point, 0) for point in stroke],
            fill=(15, 80, 190),
            width=4,
            joint="curve",
        )
        for point in stroke:
            x, y = pixel(point, 0)
            draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(205, 40, 35))
    for stroke in dense_strokes:
        draw.line(
            [pixel(point, 1) for point in stroke],
            fill=(15, 80, 190),
            width=4,
            joint="curve",
        )
    for source, quantized in zip(dense_strokes, quantized_strokes):
        draw.line(
            [pixel(point, 2) for point in source],
            fill=(190, 190, 190),
            width=7,
            joint="curve",
        )
        draw.line(
            [pixel(point, 2) for point in quantized],
            fill=(190, 45, 35),
            width=3,
            joint="curve",
        )

    draw.text(
        (panel_width * 2 + 18, 50),
        "灰：命令；红：理论脉冲落点",
        fill=(75, 75, 75),
        font=small_font,
    )
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def main() -> None:
    actual_hash = hashlib.sha256(FONT_PATH.read_bytes()).hexdigest().upper()
    if actual_hash != FONT_SHA256:
        raise AssertionError("B-font hash changed")
    font = load_gfont(FONT_PATH)
    glyph = font.glyphs["8"]
    source_strokes = place_glyph(glyph)
    dense_strokes = tuple(
        firmware_dense_points(stroke) for stroke in source_strokes
    )
    quantized_strokes = []
    step_strokes = []
    errors = []
    joint_reversals = [0, 0]
    for dense in dense_strokes:
        quantized = []
        steps = []
        previous_delta = [0, 0]
        previous_steps = None
        for paper in dense:
            achieved, step_pair = quantized_paper_point(paper)
            quantized.append(achieved)
            steps.append(step_pair)
            errors.append(
                (
                    achieved[0] - paper[0],
                    achieved[1] - paper[1],
                )
            )
            if previous_steps is not None:
                for axis in range(2):
                    delta = step_pair[axis] - previous_steps[axis]
                    if (
                        delta != 0
                        and previous_delta[axis] != 0
                        and (delta > 0) != (previous_delta[axis] > 0)
                    ):
                        joint_reversals[axis] += 1
                    if delta != 0:
                        previous_delta[axis] = delta
            previous_steps = step_pair
        quantized_strokes.append(tuple(quantized))
        step_strokes.append(tuple(steps))

    source_segments = [
        math.dist(a, b)
        for stroke in source_strokes
        for a, b in zip(stroke, stroke[1:])
    ]
    corner_angles = [
        angle
        for stroke in source_strokes
        for angle in source_corner_angles(stroke)
    ]
    error_lengths = [math.hypot(x, y) for x, y in errors]
    start_end_gap = min(
        math.dist(stroke[0], stroke[-1]) for stroke in source_strokes
    )
    report = {
        "id": TEST_ID,
        "scope": "offline_only_no_motion_no_source_change",
        "font": {
            "file": FONT_PATH.name,
            "sha256": FONT_SHA256,
            "name": font.name,
            "glyph": "8",
            "visible_height_mm": VISIBLE_HEIGHT_MM,
            "source_point_count": len(glyph.points),
            "source_stroke_count": len(source_strokes),
            "source_segment_count": len(source_segments),
            "source_longest_segment_mm": max(source_segments),
            "source_shortest_segment_mm": min(source_segments),
            "source_start_end_gap_mm": start_end_gap,
            "source_path_length_mm": sum(
                polyline_length(stroke) for stroke in source_strokes
            ),
            "source_corner_angle_max_deg": max(corner_angles),
            "source_corner_angle_rms_deg": math.sqrt(
                sum(angle * angle for angle in corner_angles)
                / len(corner_angles)
            ),
        },
        "firmware_chain": {
            "paper_center_mm": list(PAPER_CENTER_MM),
            "cartesian_segment_limit_mm": FIRMWARE_SEGMENT_MM,
            "dense_point_count": sum(len(stroke) for stroke in dense_strokes),
            "stage1_steps_per_deg": STAGE1_STEPS_PER_DEG,
            "stage2_steps_per_deg": STAGE2_STEPS_PER_DEG,
            "joint_reversal_count": joint_reversals,
            "quantization_rms_mm": math.sqrt(
                sum(value * value for value in error_lengths)
                / len(error_lengths)
            ),
            "quantization_max_mm": max(error_lengths),
            "quantization_axis_abs_max_mm": [
                max(abs(error[0]) for error in errors),
                max(abs(error[1]) for error in errors),
            ],
        },
        "conclusion": {
            "source_geometry_can_explain_mm_scale_digit8_shape": (
                start_end_gap > 1.0 or max(source_segments) > 2.0
            ),
            "joint_quantization_can_explain_1mm_misalignment": (
                max(error_lengths) >= 0.5
            ),
            "motion_dynamics_still_require_physical_forward_reverse_overlay": True,
        },
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    draw_preview(
        source_strokes,
        tuple(quantized_strokes),
    )
    print(
        f"{TEST_ID}=PASS "
        f"source_points={len(glyph.points)} "
        f"longest_source_segment={max(source_segments):.6f}mm "
        f"start_end_gap={start_end_gap:.6f}mm "
        f"dense_points={sum(len(stroke) for stroke in dense_strokes)} "
        f"quant_rms={report['firmware_chain']['quantization_rms_mm']:.6f}mm "
        f"quant_max={report['firmware_chain']['quantization_max_mm']:.6f}mm "
        f"joint_reversals={joint_reversals}"
    )
    print(REPORT_PATH)
    print(PREVIEW_PATH)


if __name__ == "__main__":
    main()
