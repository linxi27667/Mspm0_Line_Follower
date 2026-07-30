#!/usr/bin/env python3
"""Generate short bidirectional strokes with three tangent approach lengths."""

from __future__ import annotations

import hashlib
import json
import math
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


TEST_ID = "PAPER_A4_3POS_SHORTSTROKE_APPROACH_OVERLAY_GCODE_V71"
FIRMWARE_ID = "PAPER_A4_STANDARD_GCODE_JUNCTION_PLANNER_V32"
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"
GUIDE_PATH = ROOT / "gcode" / f"{TEST_ID}_GUIDE.md"

GROUP_X_MM = (40.0, 100.0, 160.0)
APPROACH_ROWS = (
    ("A1P2", 1.2, 226.0),
    ("A3", 3.0, 210.0),
    ("A5", 5.0, 194.0),
)
LINE_LENGTH_MM = 4.0
HALF_LINE_MM = LINE_LENGTH_MM / 2.0
VERTICAL_OFFSET_X_MM = 9.0
VERTICAL_CENTER_OFFSET_Y_MM = -5.0
FEED_MM_MIN = 300
PAPER_X_RANGE_MM = (25.0, 185.0)
PAPER_Y_RANGE_MM = (75.0, 235.0)
STAGE1_STEPS_PER_DEG = 40.099216
STAGE2_STEPS_PER_DEG = 40.115790
PREVIEW_PIXELS_PER_MM = 4.0


@dataclass(frozen=True)
class Stroke:
    group: str
    row: str
    approach_mm: float
    axis: str
    direction: str
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
    theta_deg, psi_deg, _ = inverse_user(*firmware_map_no_sbow(point))
    return (
        lroundf(theta_deg * STAGE1_STEPS_PER_DEG),
        lroundf(psi_deg * STAGE2_STEPS_PER_DEG),
    )


def approach_for(
    start: tuple[float, float],
    end: tuple[float, float],
    distance_mm: float,
) -> tuple[float, float]:
    length = math.dist(start, end)
    unit_x = (end[0] - start[0]) / length
    unit_y = (end[1] - start[1]) / length
    return (
        start[0] - unit_x * distance_mm,
        start[1] - unit_y * distance_mm,
    )


def build_strokes() -> tuple[Stroke, ...]:
    strokes: list[Stroke] = []
    for row, approach_mm, horizontal_y in APPROACH_ROWS:
        for group, center_x in zip(("L", "M", "R"), GROUP_X_MM):
            left = (center_x - HALF_LINE_MM, horizontal_y)
            right = (center_x + HALF_LINE_MM, horizontal_y)
            vertical_x = center_x + VERTICAL_OFFSET_X_MM
            vertical_center_y = (
                horizontal_y + VERTICAL_CENTER_OFFSET_Y_MM
            )
            bottom = (
                vertical_x,
                vertical_center_y - HALF_LINE_MM,
            )
            top = (
                vertical_x,
                vertical_center_y + HALF_LINE_MM,
            )
            specifications = (
                ("H", "LR", left, right),
                ("H", "RL", right, left),
                ("V", "BT", bottom, top),
                ("V", "TB", top, bottom),
            )
            for axis, direction, start, end in specifications:
                strokes.append(
                    Stroke(
                        group,
                        row,
                        approach_mm,
                        axis,
                        direction,
                        start,
                        end,
                        approach_for(start, end, approach_mm),
                    )
                )
    return tuple(strokes)


def gcode_lines(strokes: tuple[Stroke, ...]) -> tuple[str, ...]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware_required={FIRMWARE_ID}",
        "; coordinates=STANDARD_A4_PHYSICAL_PAPER_MM",
        "; purpose=SHORT_STROKE_TANGENT_APPROACH_ISOLATION",
        "; line_length_is_fixed_at_4mm_and_is_not_under_test",
        "; each_nominal_line_is_drawn_once_in_each_opposite_direction",
        "; rows_top_to_bottom=A1P2,A3,A5",
        "; columns_left_to_right=L,M,R",
        "G21",
        "G90",
        "G94",
        f"F{FEED_MM_MIN}",
        "S1000",
        "M5",
    ]
    active_cell = ""
    for stroke in strokes:
        cell = f"{stroke.row}_{stroke.group}"
        if cell != active_cell:
            if active_cell:
                lines.append(f"; END_CELL_{active_cell}")
            active_cell = cell
            lines.append(f"; BEGIN_CELL_{active_cell}")
        lines.extend(
            (
                (
                    f"; row={stroke.row} group={stroke.group} "
                    f"approach={stroke.approach_mm:.1f}mm "
                    f"axis={stroke.axis} direction={stroke.direction}"
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
    lines.extend((f"; END_CELL_{active_cell}", "M5"))
    return tuple(lines)


def audit(
    strokes: tuple[Stroke, ...],
    lines: tuple[str, ...],
) -> dict[str, object]:
    previous_user = home_user()
    all_points: list[tuple[float, float]] = []
    records: list[dict[str, object]] = []
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
        start_steps = joint_steps(stroke.start)
        end_steps = joint_steps(stroke.end)
        joint_signs = (
            sign(end_steps[0] - start_steps[0]),
            sign(end_steps[1] - start_steps[1]),
        )
        if 0 in joint_signs:
            raise AssertionError(
                f"{stroke.row}/{stroke.group}/{stroke.axis}/"
                f"{stroke.direction} has zero joint delta"
            )
        check_user(firmware_map_no_sbow(stroke.end))
        records.append(
            {
                "row": stroke.row,
                "group": stroke.group,
                "approach_mm": stroke.approach_mm,
                "axis": stroke.axis,
                "direction": stroke.direction,
                "joint_signs": list(joint_signs),
                "start_mm": list(stroke.start),
                "end_mm": list(stroke.end),
                "start_joint_steps": list(start_steps),
                "end_joint_steps": list(end_steps),
            }
        )

    for index in range(0, len(records), 2):
        forward = records[index]
        reverse = records[index + 1]
        if forward["axis"] != reverse["axis"]:
            raise AssertionError("overlay pair axis mismatch")
        if forward["start_mm"] != reverse["end_mm"]:
            raise AssertionError("overlay pair endpoint mismatch")
        if forward["end_mm"] != reverse["start_mm"]:
            raise AssertionError("overlay pair endpoint mismatch")
        if tuple(forward["joint_signs"]) != tuple(
            -value for value in reverse["joint_signs"]
        ):
            raise AssertionError("overlay pair joint signs are not opposite")

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
        raise AssertionError(f"V71 bounds invalid: {bounds}")
    if worst[0] < -0.001:
        raise AssertionError(f"V71 violates joint limits: {worst}")
    if len(strokes) != 36:
        raise AssertionError("V71 must contain 3 rows x 3 groups x 4 strokes")
    if lines.count("M3") != len(strokes):
        raise AssertionError("V71 pen-down count mismatch")
    if any(len(line) >= 192 for line in lines):
        raise AssertionError("V71 contains an overlong serial line")
    return {
        "bounds_mm": list(bounds),
        "safe_samples": safe_samples,
        "min_joint_margin_deg": worst[0],
        "min_margin_user_mm": list(worst[1]),
        "stroke_count": len(strokes),
        "records": records,
    }


def write_preview(strokes: tuple[Stroke, ...]) -> None:
    width = round(A4_WIDTH_MM * PREVIEW_PIXELS_PER_MM) + 1
    height = round(A4_HEIGHT_MM * PREVIEW_PIXELS_PER_MM) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, height - 1), outline=(30, 30, 30), width=3)
    drawn: set[tuple[str, str, str]] = set()
    for stroke in strokes:
        key = (stroke.row, stroke.group, stroke.axis)
        if key in drawn:
            continue
        draw.line(
            (preview_xy(stroke.start), preview_xy(stroke.end)),
            fill=(20, 20, 20),
            width=3,
        )
        drawn.add(key)
    for row, approach_mm, horizontal_y in APPROACH_ROWS:
        draw.text(
            preview_xy((26.0, horizontal_y + 5.0)),
            f"{approach_mm:.1f} mm",
            fill=(20, 20, 20),
            font=label_font(15),
        )
    draw.text(
        (20, 18),
        "V71 short-stroke approach overlay: top 1.2 / middle 3 / bottom 5 mm",
        fill=(25, 25, 25),
        font=label_font(16),
    )
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def write_guide() -> None:
    GUIDE_PATH.write_text(
        f"""# V71 短笔画切向预走双向重合测试

- 所需固件：`{FIRMWARE_ID}`
- G-code：`{GCODE_PATH.name}`
- 标准纸面坐标：是
- 离线坐标补偿：无
- 固定可见线长：{LINE_LENGTH_MM:.0f} mm（长度不参与判断）
- 速度：F{FEED_MM_MIN}

这不是长度测试，也不是重复性测试。V70 已确认直线长度正确，且大多数正反方向中心线可以重合。

本测试只改变落笔前最后一段切向预走距离：

- 上排：1.2 mm（当前小字使用值）
- 中排：3.0 mm
- 下排：5.0 mm（V70 使用值）

每排从左到右有左、中、右三个位置。每个位置各有一条 4 mm 横线和一条 4 mm 竖线；每条名义线沿原路以两个相反方向各画一次。

## 判断方法

不要测长度，只看同一条线是否变粗、形成双线或小透镜：

- 若 1.2 mm 排明显分离，而 3/5 mm 排逐渐合拢，说明小字问题主要发生在换向后的预加载距离不足。
- 若三排几乎一样，预走长度不是主因，下一步应测落笔状态下短折线内部的关节换向。
- 若仅右列持续分离，说明还存在位置相关的方向迟滞，不能用一个全局固定回差值补偿。

拍一张正对纸面的近照即可，不需要手工量长度。
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
            "isolate tangent approach length on bidirectional short strokes"
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
            "approach_rows": [
                {
                    "row": row,
                    "approach_mm": approach_mm,
                    "horizontal_y_mm": horizontal_y,
                }
                for row, approach_mm, horizontal_y in APPROACH_ROWS
            ],
            "line_length_mm": LINE_LENGTH_MM,
        },
        "motion": {
            "feed_mm_min": FEED_MM_MIN,
            "line_length_under_test": False,
            "same_direction_repeatability_under_test": False,
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
        "shortstroke_approach_overlay_v71=PASS "
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
