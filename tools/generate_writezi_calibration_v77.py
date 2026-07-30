#!/usr/bin/env python3
"""Generate the V33 three-position 8 mm B-font writing calibration."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import generate_paper_a4_3pos_bfont_writezi_v72 as base
import generate_paper_a4_standard_upper_bfont_6mm_v65 as sampling
from check_firmware_no_sbow_v31 import firmware_map_no_sbow
from check_workspace_yshift15_v28 import joint_margin
from generate_paper_a4_full_width_square_spiral_v59 import home_user


TEST_ID = "PAPER_A4_3POS_BFONT_WRITEZI_8MM_V33_CAL_GCODE_V77"
FIRMWARE_ID = "PAPER_A4_STANDARD_GCODE_AMASS_PLANNER_V33"
PAPER_MAP_ID = "A4_BASE_QUADRATIC_XSCALE_NO_SBOW_CAL_V8"
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
GUIDE_PATH = ROOT / "gcode" / f"{TEST_ID}_GUIDE.md"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"
MIN_DRAWING_MARGIN_DEG = 15.0


def minimum_margin_on_user_line(
    start: tuple[float, float],
    target: tuple[float, float],
) -> tuple[float, tuple[float, float], int]:
    worst = (float("inf"), target)
    count = 0
    for sample in sampling.user_line_samples(start, target, 1.0):
        margin, _ = joint_margin(sample)
        if margin < worst[0]:
            worst = (margin, sample)
        count += 1
    return worst[0], worst[1], count


def audit(
    layout,
    lines: tuple[str, ...],
) -> dict[str, object]:
    first_approach_user = firmware_map_no_sbow(layout.strokes[0].approach)
    home_exit_margin, home_exit_point, home_exit_samples = (
        minimum_margin_on_user_line(home_user(), first_approach_user)
    )

    previous_user = first_approach_user
    drawing_worst = (float("inf"), first_approach_user)
    drawing_samples = 0

    def check_user(target_user: tuple[float, float]) -> None:
        nonlocal previous_user, drawing_worst, drawing_samples
        margin, point, count = minimum_margin_on_user_line(
            previous_user, target_user
        )
        if margin < drawing_worst[0]:
            drawing_worst = (margin, point)
        drawing_samples += count
        previous_user = target_user

    for stroke in layout.strokes:
        check_user(firmware_map_no_sbow(stroke.approach))
        check_user(firmware_map_no_sbow(stroke.points[0]))
        previous_paper = stroke.points[0]
        for target_paper in stroke.points[1:]:
            for paper_sample in sampling.paper_line_samples(
                previous_paper, target_paper
            ):
                check_user(firmware_map_no_sbow(paper_sample))
            previous_paper = target_paper

    if home_exit_margin < -0.001:
        raise AssertionError(
            f"V77 home exit violates joint limits: "
            f"{home_exit_margin}, {home_exit_point}"
        )
    if drawing_worst[0] < MIN_DRAWING_MARGIN_DEG:
        raise AssertionError(
            f"V77 drawing margin is too small: {drawing_worst}"
        )
    if any(len(line) >= 192 for line in lines):
        raise AssertionError("V77 contains an overlong serial line")
    if lines.count("M3") != len(layout.strokes):
        raise AssertionError("V77 pen-down count mismatch")

    return {
        "home_exit": {
            "sample_count": home_exit_samples,
            "minimum_joint_margin_deg": home_exit_margin,
            "minimum_margin_user_mm": list(home_exit_point),
            "first_approach_joint_margin_deg": joint_margin(
                first_approach_user
            )[0],
            "note": (
                "The home pose is the configured joint-minimum reference; "
                "this value covers only the initial pen-up departure."
            ),
        },
        "writing_sequence": {
            "sample_count": drawing_samples,
            "minimum_joint_margin_deg": drawing_worst[0],
            "minimum_margin_user_mm": list(drawing_worst[1]),
            "required_minimum_margin_deg": MIN_DRAWING_MARGIN_DEG,
        },
        "stroke_count": len(layout.strokes),
        "motion_line_count": sum(
            line.startswith(("G0 ", "G1 ")) for line in lines
        ),
    }


def write_preview(layout) -> None:
    pixels_per_mm = base.PREVIEW_PIXELS_PER_MM
    width = round(base.A4_WIDTH_MM * pixels_per_mm) + 1
    height = round(base.A4_HEIGHT_MM * pixels_per_mm) + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (0, 0, width - 1, height - 1),
        outline=(30, 30, 30),
        width=3,
    )
    for stroke in layout.strokes:
        draw.line(
            [base.preview_xy(point) for point in stroke.points],
            fill=(20, 20, 20),
            width=2,
            joint="curve",
        )
    for group, center_x in base.GROUPS:
        draw.text(
            base.preview_xy((center_x - 2.0, 196.0)),
            group,
            fill=(20, 20, 20),
            font=base.label_font(15),
        )
    draw.text(
        (20, 18),
        "V77 / V33 / B font / WRITE ZI / 8 mm / left-middle-right",
        fill=(25, 25, 25),
        font=base.label_font(16),
    )
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def write_guide(manifest: dict[str, object]) -> None:
    safety = manifest["safety"]
    GUIDE_PATH.write_text(
        f"""# V77 三位置“写字”校准

- 固件：`{FIRMWARE_ID}`
- 纸面映射：`{PAPER_MAP_ID}`
- 内容：左、中、右三个位置各写一次“写字”
- 字体：B 类原始 gfont，字形点序不修改
- 可见字高：{base.VISIBLE_HEIGHT_MM:.0f} mm
- 落笔前切向预走：{base.TANGENT_APPROACH_MM:.0f} mm
- 速度：F{base.FEED_MM_MIN}
- 三组中心 X：40、100、160 mm
- 字形顶部 Y：{base.CONTENT_TOP_MM:.0f} mm
- 标准纸面 G-code，无离线坐标补偿

安全检查：

- 从回零参考位抬笔离开的首段采样最小余量：
  `{safety['home_exit']['minimum_joint_margin_deg']:.6f} deg`
- 到达第一写字位置后的完整写字序列最小余量：
  `{safety['writing_sequence']['minimum_joint_margin_deg']:.6f} deg`
- 写字序列要求至少：
  `{safety['writing_sequence']['required_minimum_margin_deg']:.1f} deg`

三组字使用完全相同的原始字库点序，只做刚性平移。比较时先看同一笔画
是否在三个位置出现相同问题，再区分字库、纸面映射和机械换向误差。
""",
        encoding="utf-8",
    )


def main() -> None:
    base.TEST_ID = TEST_ID
    base.FIRMWARE_ID = FIRMWARE_ID
    layout, stroke_groups = base.build_layout()
    lines = base.gcode_lines(layout, stroke_groups)
    content = "\n".join(lines) + "\n"
    safety = audit(layout, lines)

    GCODE_PATH.parent.mkdir(parents=True, exist_ok=True)
    GCODE_PATH.write_text(content, encoding="ascii", newline="\n")
    manifest = {
        "id": TEST_ID,
        "required_firmware": FIRMWARE_ID,
        "required_paper_map": PAPER_MAP_ID,
        "text": base.TEXT,
        "repetitions": 3,
        "font": {
            "option": "B",
            "name": base.source.FONT_NAME,
            "file": base.source.FONT_PATH.name,
            "sha256": base.source.FONT_SHA256,
            "geometry": "unmodified gfont paths; rigid translation only",
        },
        "layout": {
            "visible_height_mm": base.VISIBLE_HEIGHT_MM,
            "character_gap_mm": base.CHARACTER_GAP_MM,
            "content_top_mm": base.CONTENT_TOP_MM,
            "group_centers_x_mm": [
                center for _, center in base.GROUPS
            ],
            "bounds_mm": list(layout.bounds_mm),
        },
        "coordinate_contract": {
            "units": "mm",
            "frame": "nominal physical A4 paper",
            "offline_mapping": False,
            "offline_prewarp": False,
            "firmware_mapping": True,
        },
        "motion": {
            "feed_mm_min": base.FEED_MM_MIN,
            "tangent_approach_mm": base.TANGENT_APPROACH_MM,
        },
        "safety": safety,
        "gcode": {
            "file": GCODE_PATH.name,
            "line_count": len(lines),
            "sha256": hashlib.sha256(content.encode("ascii"))
            .hexdigest()
            .upper(),
        },
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_preview(layout)
    write_guide(manifest)
    print(
        f"{TEST_ID}=PASS strokes={safety['stroke_count']} "
        f"home_exit_margin="
        f"{safety['home_exit']['minimum_joint_margin_deg']:.6f}deg "
        f"writing_margin="
        f"{safety['writing_sequence']['minimum_joint_margin_deg']:.6f}deg "
        f"sha256={manifest['gcode']['sha256']}"
    )
    print(GCODE_PATH)
    print(MANIFEST_PATH)
    print(PREVIEW_PATH)
    print(GUIDE_PATH)


if __name__ == "__main__":
    main()
