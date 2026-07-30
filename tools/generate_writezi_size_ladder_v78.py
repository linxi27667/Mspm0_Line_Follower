#!/usr/bin/env python3
"""Generate the V33 center-column writing-size calibration ladder."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import generate_paper_a4_3pos_bfont_writezi_v72 as base
import generate_writezi_calibration_v77 as v77


TEST_ID = "PAPER_A4_CENTER_BFONT_WRITEZI_SIZE_LADDER_V33_GCODE_V78"
FIRMWARE_ID = "PAPER_A4_STANDARD_GCODE_AMASS_PLANNER_V33"
PAPER_MAP_ID = "A4_BASE_QUADRATIC_XSCALE_NO_SBOW_CAL_V8"
GCODE_PATH = ROOT / "gcode" / f"{TEST_ID}.gcode"
MANIFEST_PATH = ROOT / "gcode" / f"{TEST_ID}.json"
GUIDE_PATH = ROOT / "gcode" / f"{TEST_ID}_GUIDE.md"
PREVIEW_PATH = ROOT / "docs" / "diagnostics" / f"{TEST_ID}_PREVIEW.png"

CENTER_X_MM = 105.0
SIZE_ROWS = (
    (12.0, 225.0),
    (10.0, 195.0),
    (8.0, 165.0),
    (6.0, 140.0),
)


def build_plan():
    strokes = []
    metadata = []
    bounds = []
    for visible_height_mm, content_top_mm in SIZE_ROWS:
        base.VISIBLE_HEIGHT_MM = visible_height_mm
        base.CONTENT_TOP_MM = content_top_mm
        base.GROUPS = ((f"SIZE_{int(visible_height_mm)}MM", CENTER_X_MM),)
        layout, groups = base.build_layout()
        strokes.extend(layout.strokes)
        metadata.extend(
            (visible_height_mm, character_index, stroke_index)
            for _, character_index, stroke_index in groups
        )
        bounds.append(layout.bounds_mm)
    return SimpleNamespace(strokes=tuple(strokes)), tuple(metadata), tuple(bounds)


def gcode_lines(layout, metadata) -> tuple[str, ...]:
    lines = [
        f"; {TEST_ID}",
        f"; firmware_required={FIRMWARE_ID}",
        f"; paper_map_required={PAPER_MAP_ID}",
        "; coordinates=STANDARD_A4_PHYSICAL_PAPER_MM",
        "; offline_mapping=NONE offline_prewarp=NONE",
        f"; source_font={base.source.FONT_PATH.name} "
        f"sha256={base.source.FONT_SHA256}",
        "; requested_text=WRITE_ZI sizes=12,10,8,6mm center_x=105mm",
        f"; tangent_approach={base.TANGENT_APPROACH_MM:.0f}mm",
        "G21",
        "G90",
        "G94",
        f"F{base.FEED_MM_MIN}",
        "S1000",
        "M5",
    ]
    active_size = None
    for stroke, item in zip(layout.strokes, metadata):
        size, character_index, stroke_index = item
        if size != active_size:
            if active_size is not None:
                lines.append(f"; END_SIZE_{int(active_size)}MM")
            active_size = size
            lines.append(f"; BEGIN_SIZE_{int(size)}MM")
        lines.extend(
            (
                f"; size={int(size)}mm char={character_index + 1} "
                f"stroke={stroke_index}",
                f"G0 X{stroke.approach[0]:.3f} Y{stroke.approach[1]:.3f}",
                f"G0 X{stroke.points[0][0]:.3f} "
                f"Y{stroke.points[0][1]:.3f}",
                "M3",
            )
        )
        lines.extend(
            f"G1 X{point[0]:.3f} Y{point[1]:.3f}"
            for point in stroke.points[1:]
        )
        lines.append("M5")
    lines.extend((f"; END_SIZE_{int(active_size)}MM", "M5"))
    return tuple(lines)


def write_preview(layout, metadata) -> None:
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
    for size, top in SIZE_ROWS:
        draw.text(
            base.preview_xy((78.0, top - size / 2.0)),
            f"{int(size)} mm",
            fill=(35, 35, 35),
            font=base.label_font(15),
        )
    draw.text(
        (20, 18),
        "V78 / V33 / WRITE ZI size ladder / 12, 10, 8, 6 mm",
        fill=(25, 25, 25),
        font=base.label_font(16),
    )
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW_PATH)


def write_guide(manifest: dict[str, object]) -> None:
    safety = manifest["safety"]
    GUIDE_PATH.write_text(
        f"""# V78 “写字”尺寸阶梯校准

- 固件：`{FIRMWARE_ID}`
- 纸面映射：`{PAPER_MAP_ID}`
- 中心 X：{CENTER_X_MM:.0f} mm
- 从上到下：12、10、8、6 mm“写字”
- 字体：B 类原始 gfont，字形点序不修改
- 落笔前切向预走：{base.TANGENT_APPROACH_MM:.0f} mm
- 速度：F{base.FEED_MM_MIN}
- 标准纸面 G-code，无离线坐标补偿

安全检查：

- 写字序列最小关节余量：
  `{safety['writing_sequence']['minimum_joint_margin_deg']:.6f} deg`
- 要求的最小余量：
  `{safety['writing_sequence']['required_minimum_margin_deg']:.1f} deg`

判定时从 12 mm 向 6 mm 观察：哪一级开始出现粘连、缺笔、接点开口或
字形不可辨，就把上一级作为当前机构、笔尖和字体组合的最小正式字号。
""",
        encoding="utf-8",
    )


def main() -> None:
    layout, metadata, bounds = build_plan()
    lines = gcode_lines(layout, metadata)
    content = "\n".join(lines) + "\n"
    safety = v77.audit(layout, lines)
    if len(metadata) != len(layout.strokes):
        raise AssertionError("V78 metadata/stroke count mismatch")

    GCODE_PATH.parent.mkdir(parents=True, exist_ok=True)
    GCODE_PATH.write_text(content, encoding="ascii", newline="\n")
    manifest = {
        "id": TEST_ID,
        "required_firmware": FIRMWARE_ID,
        "required_paper_map": PAPER_MAP_ID,
        "text": base.TEXT,
        "center_x_mm": CENTER_X_MM,
        "size_rows": [
            {"visible_height_mm": size, "content_top_mm": top}
            for size, top in SIZE_ROWS
        ],
        "bounds_by_size_mm": [list(item) for item in bounds],
        "font": {
            "option": "B",
            "name": base.source.FONT_NAME,
            "file": base.source.FONT_PATH.name,
            "sha256": base.source.FONT_SHA256,
            "geometry": "unmodified gfont paths; rigid scale and translation only",
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
    write_preview(layout, metadata)
    write_guide(manifest)
    print(
        f"{TEST_ID}=PASS strokes={safety['stroke_count']} "
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
