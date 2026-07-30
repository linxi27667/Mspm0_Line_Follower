#!/usr/bin/env python3
"""Generate a three-position, four-joint-direction overlay calibration."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from check_firmware_no_sbow_v31 import firmware_map_no_sbow
from check_workspace_yshift15_v28 import inverse_user, joint_margin
from generate_paper_a4_full_width_square_spiral_v59 import home_user
from generate_paper_a4_zhang_jia_le_v30 import (
    A4_HEIGHT_MM,
    A4_WIDTH_MM,
    label_font,
    preview_xy,
)


TEST_ID = "PAPER_A4_3POS_4JOINTDIR_OVERLAY_GCODE_V70"
FIRMWARE_ID = "PAPER_A4_STANDARD_GCODE_JUNCTION_PLANNER_V32"
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"
GUIDE_PATH = ROOT / "gcode" / f"{TEST_ID}_GUIDE.md"

GROUP_X_MM = (40.0, 100.0, 160.0)
HORIZONTAL_Y_MM = 176.0
VERTICAL_CENTER_Y_MM = 168.0
HORIZONTAL_HALF_MM = 8.0
VERTICAL_HALF_MM = 8.0
VERTICAL_OFFSET_X_MM = 14.0
TANGENT_APPROACH_MM = 5.0
FEED_MM_MIN = 300
PAPER_X_RANGE_MM = (25.0, 185.0)
PAPER_Y_RANGE_MM = (75.0, 235.0)
STAGE1_STEPS_PER_DEG = 40.099216
STAGE2_STEPS_PER_DEG = 40.115790
PREVIEW_PIXELS_PER_MM = 4.0


@dataclass(frozen=True)
class DirectionStroke:
    group: str
    axis: str
    label: str
    expected_joint_signs: tuple[int, int]
    start: tuple[float, float]
    end: tuple[float, float]
    approach: tuple[float, float]


def sign(value: int | float) -> int:
    return 1 if value > 0 else (-1 if value < 0 else 0)


def lroundf(value: float) -> int:
    return (
        math.floor(value + 0.5)
        if value >= 0.0
        else math.ceil(value - 0.5)
    )


def joint_steps(point: tuple[float, float]) -> tuple[int, int]:
    theta_deg, psi_deg, _ = inverse_user(
        *firmware_map_no_sbow(point)
    )
    return (
        lroundf(theta_deg * STAGE1_STEPS_PER_DEG),
        lroundf(psi_deg * STAGE2_STEPS_PER_DEG),
    )


def approach_for(
    start: tuple[float, float], end: tuple[float, float]
) -> tuple[float, float]:
    length = math.dist(start, end)
    unit_x = (end[0] - start[0]) / length
    unit_y = (end[1] - start[1]) / length
    return (
        start[0] - unit_x * TANGENT_APPROACH_MM,
        start[1] - unit_y * TANGENT_APPROACH_MM,
    )


def build_strokes() -> tuple[DirectionStroke, ...]:
    strokes: list[DirectionStroke] = []
    for group_index, center_x in enumerate(GROUP_X_MM):
        group = ("L", "M", "R")[group_index]
        horizontal_left = (
            center_x - HORIZONTAL_HALF_MM,
            HORIZONTAL_Y_MM,
        )
        horizontal_right = (
            center_x + HORIZONTAL_HALF_MM,
            HORIZONTAL_Y_MM,
        )
        vertical_x = center_x + VERTICAL_OFFSET_X_MM
        vertical_bottom = (
            vertical_x,
            VERTICAL_CENTER_Y_MM - VERTICAL_HALF_MM,
        )
        vertical_top = (
            vertical_x,
            VERTICAL_CENTER_Y_MM + VERTICAL_HALF_MM,
        )
        specifications = (
            (
                "H",
                "LR",
                (1, -1),
                horizontal_left,
                horizontal_right,
            ),
            (
                "H",
                "RL",
                (-1, 1),
                horizontal_right,
                horizontal_left,
            ),
            (
                "V",
                "BT",
                (-1, -1),
                vertical_bottom,
                vertical_top,
            ),
            (
                "V",
                "TB",
                (1, 1),
                vertical_top,
                vertical_bottom,
            ),
        )
        for axis, label, expected, start, end in specifications:
            strokes.append(
                DirectionStroke(
                    group,
                    axis,
                    label,
                    expected,
                    start,
                    end,
                    approach_for(start, end),
                )
            )
    return tuple(strokes)


def gcode_lines(
    strokes: tuple[DirectionStroke, ...],
) -> tuple[str, ...]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware_required={FIRMWARE_ID}",
        "; coordinates=STANDARD_A4_PHYSICAL_PAPER_MM",
        "; purpose=DETERMINISTIC_BIDIRECTIONAL_JOINT_OFFSET_CALIBRATION",
        "; same_direction_repeatability=ALREADY_CONFIRMED_NOT_UNDER_TEST",
        "; each_nominal_line_is_drawn_once_in_each_opposite_direction",
        "; H_LR=STAGE1_POS_STAGE2_NEG H_RL=STAGE1_NEG_STAGE2_POS",
        "; V_BT=STAGE1_NEG_STAGE2_NEG V_TB=STAGE1_POS_STAGE2_POS",
        "; groups=LEFT_MIDDLE_RIGHT line_length=16mm",
        "G21",
        "G90",
        "G94",
        f"F{FEED_MM_MIN}",
        "S1000",
        "M5",
    ]
    active_group = ""
    for stroke in strokes:
        if stroke.group != active_group:
            if active_group:
                lines.append(f"; END_GROUP_{active_group}")
            active_group = stroke.group
            lines.append(f"; BEGIN_GROUP_{active_group}")
        lines.extend(
            (
                (
                    f"; group={stroke.group} axis={stroke.axis} "
                    f"direction={stroke.label} "
                    f"joint_signs={stroke.expected_joint_signs[0]},"
                    f"{stroke.expected_joint_signs[1]}"
                ),
                (
                    f"G0 X{stroke.approach[0]:.3f} "
                    f"Y{stroke.approach[1]:.3f}"
                ),
                f"G0 X{stroke.start[0]:.3f} Y{stroke.start[1]:.3f}",
                "M3",
                f"G1 X{stroke.end[0]:.3f} Y{stroke.end[1]:.3f}",
                "M5",
            )
        )
    lines.extend((f"; END_GROUP_{active_group}", "M5"))
    return tuple(lines)


def paper_samples(
    start: tuple[float, float],
    end: tuple[float, float],
    maximum_step_mm: float = 1.0,
) -> tuple[tuple[float, float], ...]:
    count = max(
        1,
        math.ceil(
            max(
                abs(end[0] - start[0]),
                abs(end[1] - start[1]),
            )
            / maximum_step_mm
        ),
    )
    return tuple(
        (
            start[0] + (end[0] - start[0]) * index / count,
            start[1] + (end[1] - start[1]) * index / count,
        )
        for index in range(count + 1)
    )


def audit(
    strokes: tuple[DirectionStroke, ...],
    lines: tuple[str, ...],
) -> dict[str, object]:
    direction_records: list[dict[str, object]] = []
    all_points: list[tuple[float, float]] = []
    previous_user = home_user()
    worst = (float("inf"), (0.0, 0.0))
    safe_samples = 0

    def check_user(target_user: tuple[float, float]) -> None:
        nonlocal previous_user, worst, safe_samples
        span = max(
            abs(target_user[0] - previous_user[0]),
            abs(target_user[1] - previous_user[1]),
        )
        count = max(1, math.ceil(span))
        for index in range(1, count + 1):
            ratio = index / count
            sample = (
                previous_user[0]
                + (target_user[0] - previous_user[0]) * ratio,
                previous_user[1]
                + (target_user[1] - previous_user[1]) * ratio,
            )
            margin, _ = joint_margin(sample)
            if margin < worst[0]:
                worst = (margin, sample)
            safe_samples += 1
        previous_user = target_user

    for stroke in strokes:
        all_points.extend((stroke.approach, stroke.start, stroke.end))
        check_user(firmware_map_no_sbow(stroke.approach))
        check_user(firmware_map_no_sbow(stroke.start))
        samples = paper_samples(stroke.start, stroke.end)
        observed_signs: set[tuple[int, int]] = set()
        for first, second in zip(samples, samples[1:]):
            first_steps = joint_steps(first)
            second_steps = joint_steps(second)
            delta = (
                second_steps[0] - first_steps[0],
                second_steps[1] - first_steps[1],
            )
            observed_signs.add((sign(delta[0]), sign(delta[1])))
            check_user(firmware_map_no_sbow(second))
        if observed_signs != {stroke.expected_joint_signs}:
            raise AssertionError(
                f"{stroke.group}/{stroke.label} joint signs "
                f"{observed_signs} != {stroke.expected_joint_signs}"
            )
        direction_records.append(
            {
                "group": stroke.group,
                "axis": stroke.axis,
                "direction": stroke.label,
                "joint_signs": list(stroke.expected_joint_signs),
                "start_mm": list(stroke.start),
                "end_mm": list(stroke.end),
                "start_joint_steps": list(joint_steps(stroke.start)),
                "end_joint_steps": list(joint_steps(stroke.end)),
            }
        )

    bounds = (
        min(point[0] for point in all_points),
        min(point[1] for point in all_points),
        max(point[0] for point in all_points),
        max(point[1] for point in all_points),
    )
    if not (
        PAPER_X_RANGE_MM[0]
        <= bounds[0]
        <= bounds[2]
        <= PAPER_X_RANGE_MM[1]
        and PAPER_Y_RANGE_MM[0]
        <= bounds[1]
        <= bounds[3]
        <= PAPER_Y_RANGE_MM[1]
    ):
        raise AssertionError(f"V70 bounds invalid: {bounds}")
    if worst[0] < -0.001:
        raise AssertionError(f"V70 violates joint limits: {worst}")
    if any(len(line) >= 192 for line in lines):
        raise AssertionError("V70 contains an overlong serial line")
    if len(strokes) != 12:
        raise AssertionError("V70 must contain 3 groups x 4 directions")
    if lines.count("M3") != len(strokes):
        raise AssertionError("V70 pen-down count mismatch")
    return {
        "bounds_mm": list(bounds),
        "safe_samples": safe_samples,
        "min_joint_margin_deg": worst[0],
        "min_margin_user_mm": list(worst[1]),
        "direction_records": direction_records,
        "stroke_count": len(strokes),
        "motion_line_count": sum(
            line.startswith(("G0 ", "G1 ")) for line in lines
        ),
    }


def write_preview(strokes: tuple[DirectionStroke, ...]) -> None:
    width = round(A4_WIDTH_MM * PREVIEW_PIXELS_PER_MM) + 1
    height = round(A4_HEIGHT_MM * PREVIEW_PIXELS_PER_MM) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, height - 1), outline=(30, 30, 30), width=3)
    draw.rectangle(
        (
            round(PAPER_X_RANGE_MM[0] * PREVIEW_PIXELS_PER_MM),
            round((A4_HEIGHT_MM - 185.0) * PREVIEW_PIXELS_PER_MM),
            round(PAPER_X_RANGE_MM[1] * PREVIEW_PIXELS_PER_MM),
            round((A4_HEIGHT_MM - 150.0) * PREVIEW_PIXELS_PER_MM),
        ),
        outline=(110, 170, 220),
        width=2,
    )
    drawn_geometry: set[tuple[str, str]] = set()
    for stroke in strokes:
        geometry_key = (stroke.group, stroke.axis)
        if geometry_key not in drawn_geometry:
            draw.line(
                (preview_xy(stroke.start), preview_xy(stroke.end)),
                fill=(20, 20, 20),
                width=3,
            )
            drawn_geometry.add(geometry_key)
    for group, center_x in zip(("L", "M", "R"), GROUP_X_MM):
        draw.text(
            preview_xy((center_x - 3.0, 184.0)),
            group,
            fill=(20, 20, 20),
            font=label_font(16),
        )
    draw.text(
        (20, 18),
        "V70 joint-direction overlay: each visible line is drawn both ways",
        fill=(25, 25, 25),
        font=label_font(17),
    )
    draw.text(
        (20, 44),
        "H: (+,-) / (-,+)    V: (-,-) / (+,+)",
        fill=(25, 25, 25),
        font=label_font(15),
    )
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def write_guide() -> None:
    GUIDE_PATH.write_text(
        f"""# V70 三位置四关节方向双向重合线

- 所需固件：`{FIRMWARE_ID}`
- G-code：`{GCODE_PATH.name}`
- 速度：F{FEED_MM_MIN}
- 位置：纸面 Y=155..181 mm
- 三组中心：X={GROUP_X_MM[0]:.0f}、{GROUP_X_MM[1]:.0f}、{GROUP_X_MM[2]:.0f} mm
- 每条名义线长度：16 mm

这不是重复性测试。同方向重复性已经确认正常，本文件只测确定性的正反方向中心线分离。

每组包含两条互不相交的名义线，每条线沿原路画两个相反方向：

- 横线左到右：Stage1+ / Stage2-
- 横线右到左：Stage1- / Stage2+
- 竖线下到上：Stage1- / Stage2-
- 竖线上到下：Stage1+ / Stage2+

## 发送与拍照

1. 使用当前 V32 固件，发送整个 V70 文件一次。
2. 若 Y=155..181 mm 已有深色笔迹，请换一张纸；不要修改 G-code 坐标。
3. 完成后拍整张纸，尽量让四个纸角都进入画面，镜头正对纸面。
4. 再补一张三组线的近照。无需手工测量或画辅助线。

照片将用于自动提取横线与竖线的双中心线间距，并拟合 Stage1/Stage2 的四方向偏置。
""",
        encoding="utf-8",
    )


def main() -> None:
    strokes = build_strokes()
    lines = gcode_lines(strokes)
    text = "\n".join(lines) + "\n"
    safety = audit(strokes, lines)
    GCODE_PATH.parent.mkdir(parents=True, exist_ok=True)
    GCODE_PATH.write_text(text, encoding="ascii", newline="\n")
    manifest = {
        "id": TEST_ID,
        "required_firmware": FIRMWARE_ID,
        "purpose": (
            "fit deterministic joint-direction offsets after same-direction "
            "repeatability was already confirmed"
        ),
        "coordinate_contract": {
            "units": "mm",
            "frame": "nominal physical A4 paper",
            "offline_mapping": False,
            "offline_prewarp": False,
            "firmware_mapping": True,
        },
        "layout": {
            "group_x_mm": list(GROUP_X_MM),
            "horizontal_y_mm": HORIZONTAL_Y_MM,
            "vertical_center_y_mm": VERTICAL_CENTER_Y_MM,
            "line_length_mm": 2.0 * HORIZONTAL_HALF_MM,
            "tangent_approach_mm": TANGENT_APPROACH_MM,
        },
        "motion": {
            "feed_mm_min": FEED_MM_MIN,
            "same_direction_repeatability_under_test": False,
            "joint_direction_combinations": [
                [1, -1],
                [-1, 1],
                [-1, -1],
                [1, 1],
            ],
        },
        "safety": safety,
        "gcode": {
            "file": GCODE_PATH.name,
            "line_count": len(lines),
            "sha256": hashlib.sha256(text.encode("ascii")).hexdigest().upper(),
        },
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_preview(strokes)
    write_guide()
    print(
        "joint_direction_overlay_v70=PASS "
        f"bounds={tuple(safety['bounds_mm'])} "
        f"strokes={safety['stroke_count']} "
        f"safe_samples={safety['safe_samples']} "
        f"min_joint_margin={safety['min_joint_margin_deg']:.6f}deg"
    )
    print(f"gcode_sha256={manifest['gcode']['sha256']}")
    print(GCODE_PATH)
    print(MANIFEST_PATH)
    print(PREVIEW_PATH)
    print(GUIDE_PATH)


if __name__ == "__main__":
    main()
