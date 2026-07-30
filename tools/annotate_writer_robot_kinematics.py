#!/usr/bin/env python3
"""Overlay the firmware kinematics model on the writer robot photograph."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


DEFAULT_INPUT = Path(
    r"C:\Users\zjl\AppData\Local\Temp\codex-clipboard-9e4888b0-54df-44a6-9913-c112924584c6.jpg"
)
DEFAULT_OUTPUT = Path("docs/figures/writer_robot_kinematics_annotated.png")

# Pixel locations on the supplied 4096 x 3072 photograph. P is the planar
# writing-axis location at the pen holder, not the raised nib's apparent tip.
BASE_O = (2368, 2048)
ELBOW_A = (1016, 680)
PEN_P = (2836, 744)

FONT_REGULAR = r"C:\Windows\Fonts\msyh.ttc"
FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"
FONT_MONO = r"C:\Windows\Fonts\consola.ttf"

INK = (248, 250, 252, 255)
MUTED = (191, 205, 216, 255)
CYAN = (0, 200, 255, 255)
AMBER = (255, 181, 48, 255)
MAGENTA = (255, 91, 158, 255)
GREEN = (87, 235, 169, 255)
PANEL = (12, 21, 29, 224)
PANEL_BORDER = (255, 255, 255, 38)


def font(size: int, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_MONO if mono else (FONT_BOLD if bold else FONT_REGULAR)
    return ImageFont.truetype(path, size)


def rounded_panel(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    radius: int = 30,
    fill: tuple[int, int, int, int] = PANEL,
    outline: tuple[int, int, int, int] = PANEL_BORDER,
    width: int = 2,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def stroked_line(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[int, int]],
    color: tuple[int, int, int, int],
    width: int = 13,
) -> None:
    draw.line(points, fill=(5, 10, 14, 185), width=width + 12, joint="curve")
    draw.line(points, fill=color, width=width, joint="curve")


def dashed_line(
    draw: ImageDraw.ImageDraw,
    start: tuple[float, float],
    end: tuple[float, float],
    color: tuple[int, int, int, int],
    width: int = 7,
    dash: int = 22,
    gap: int = 15,
) -> None:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return
    ux, uy = dx / length, dy / length
    pos = 0.0
    while pos < length:
        stop = min(pos + dash, length)
        p0 = (start[0] + ux * pos, start[1] + uy * pos)
        p1 = (start[0] + ux * stop, start[1] + uy * stop)
        draw.line((p0, p1), fill=color, width=width)
        pos += dash + gap


def arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    color: tuple[int, int, int, int],
    width: int = 8,
    head: int = 26,
) -> None:
    draw.line((start, end), fill=color, width=width)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    left = (
        end[0] - head * math.cos(angle - math.pi / 6),
        end[1] - head * math.sin(angle - math.pi / 6),
    )
    right = (
        end[0] - head * math.cos(angle + math.pi / 6),
        end[1] - head * math.sin(angle + math.pi / 6),
    )
    draw.polygon((end, left, right), fill=color)


def marker(
    draw: ImageDraw.ImageDraw,
    point: tuple[int, int],
    color: tuple[int, int, int, int],
    radius: int = 24,
) -> None:
    x, y = point
    draw.ellipse(
        (x - radius - 7, y - radius - 7, x + radius + 7, y + radius + 7),
        fill=(5, 10, 14, 210),
    )
    draw.ellipse(
        (x - radius, y - radius, x + radius, y + radius),
        fill=(8, 16, 23, 245),
        outline=color,
        width=8,
    )
    draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=INK)


def label_chip(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    accent: tuple[int, int, int, int],
    size: int = 42,
    padding_x: int = 24,
    padding_y: int = 15,
) -> tuple[int, int, int, int]:
    label_font = font(size, bold=True)
    bbox = draw.textbbox((0, 0), text, font=label_font)
    width = bbox[2] - bbox[0] + padding_x * 2 + 12
    height = bbox[3] - bbox[1] + padding_y * 2
    box = (xy[0], xy[1], xy[0] + width, xy[1] + height)
    rounded_panel(draw, box, radius=18, fill=(10, 18, 25, 226))
    draw.rounded_rectangle(
        (box[0], box[1], box[0] + 12, box[3]),
        radius=6,
        fill=accent,
    )
    draw.text(
        (xy[0] + padding_x + 12, xy[1] + padding_y - bbox[1]),
        text,
        font=label_font,
        fill=INK,
    )
    return box


def draw_title(draw: ImageDraw.ImageDraw) -> None:
    box = (72, 66, 1830, 326)
    rounded_panel(draw, box, radius=34, fill=(9, 17, 24, 226))
    draw.rectangle((72, 66, 88, 326), fill=CYAN)
    draw.text((126, 102), "双连杆写字机器人运动学模型", font=font(70, bold=True), fill=INK)
    draw.text(
        (129, 208),
        "与 MID/Src/mid_scara.c 的绝对角定义及公式一致",
        font=font(37),
        fill=MUTED,
    )


def draw_formula_panel(draw: ImageDraw.ImageDraw) -> None:
    x0, y0, x1, y1 = (72, 1570, 1565, 2974)
    rounded_panel(draw, (x0, y0, x1, y1), radius=34)

    draw.text((124, 1612), "代码中的运动学公式", font=font(58, bold=True), fill=INK)
    draw.text(
        (124, 1696),
        "θ、ψ：相对机械 -X 轴的绝对角    β = ψ - θ",
        font=font(35),
        fill=MUTED,
    )

    draw.rounded_rectangle((124, 1771, 365, 1834), radius=14, fill=(0, 200, 255, 48))
    draw.text((148, 1773), "正运动学", font=font(40, bold=True), fill=CYAN)
    draw.text((124, 1860), "x = -L1 cosθ - L2 cosψ", font=font(52), fill=INK)
    draw.text((124, 1937), "y =  L1 sinθ + L2 sinψ", font=font(52), fill=INK)

    draw.line((124, 2034, 1508, 2034), fill=(255, 255, 255, 42), width=2)
    draw.rounded_rectangle((124, 2077, 365, 2140), radius=14, fill=(255, 181, 48, 48))
    draw.text((148, 2079), "逆运动学", font=font(40, bold=True), fill=AMBER)

    formulas = [
        "r² = x² + y²",
        "c2 = (r² - L1² - L2²) / (2 L1 L2)",
        "s2 = ±√(1 - c2²),  q2 = atan2(s2, c2)",
        "k1 = L1 + L2c2,    k2 = L2s2",
        "θ = atan2(k1,k2) - atan2(-x,y)",
        "ψ = θ + q2,          β = q2",
    ]
    y = 2170
    for line in formulas:
        draw.text((124, y), line, font=font(39), fill=INK)
        y += 77

    draw.line((124, 2651, 1508, 2651), fill=(255, 255, 255, 42), width=2)
    draw.text(
        (124, 2694),
        "L1 = 205 mm   ·   L2 = 203 mm",
        font=font(42, bold=True),
        fill=GREEN,
    )
    draw.text(
        (124, 2772),
        "可达条件：|L1-L2| ≤ r ≤ L1+L2",
        font=font(37),
        fill=MUTED,
    )
    draw.text(
        (124, 2842),
        "机械坐标：+X 向右，+Y 向上",
        font=font(34),
        fill=MUTED,
    )


def draw_mechanism(draw: ImageDraw.ImageDraw) -> None:
    # Effective two-link centerlines used by the firmware model.
    stroked_line(draw, [BASE_O, ELBOW_A], CYAN)
    stroked_line(draw, [ELBOW_A, PEN_P], AMBER)

    # Machine axes. +Y points upward in the photograph.
    dashed_line(draw, BASE_O, (1660, BASE_O[1]), (87, 235, 169, 145), width=6)
    arrow(draw, BASE_O, (3650, BASE_O[1]), GREEN, width=8, head=30)
    arrow(draw, BASE_O, (BASE_O[0], 1040), GREEN, width=8, head=30)
    draw.text((3670, 1995), "+Xm", font=font(46, bold=True), fill=GREEN)
    draw.text((2405, 980), "+Ym", font=font(46, bold=True), fill=GREEN)
    draw.text((1664, 2074), "-Xm（角度零基准）", font=font(32), fill=(166, 245, 208, 235))

    # theta: from the -X axis clockwise to the first link.
    r_theta = 324
    theta_box = (
        BASE_O[0] - r_theta,
        BASE_O[1] - r_theta,
        BASE_O[0] + r_theta,
        BASE_O[1] + r_theta,
    )
    draw.arc(theta_box, start=180, end=226, fill=CYAN, width=11)
    draw.text((1980, 1735), "θ", font=font(66, bold=True), fill=CYAN)

    # beta = psi - theta: angle between the translated link directions.
    r_beta = 255
    beta_box = (
        ELBOW_A[0] - r_beta,
        ELBOW_A[1] - r_beta,
        ELBOW_A[0] + r_beta,
        ELBOW_A[1] + r_beta,
    )
    draw.arc(beta_box, start=226, end=359, fill=MAGENTA, width=11)
    draw.text((1120, 404), "β = ψ - θ", font=font(44, bold=True), fill=MAGENTA)

    marker(draw, BASE_O, CYAN, radius=28)
    marker(draw, ELBOW_A, MAGENTA, radius=25)
    marker(draw, PEN_P, AMBER, radius=25)

    label_chip(draw, (1405, 1225), "一级臂  L1 = 205 mm  ·  绝对角 θ", CYAN, size=42)
    label_chip(draw, (1540, 470), "二级臂  L2 = 203 mm  ·  绝对角 ψ", AMBER, size=42)
    label_chip(draw, (2440, 2200), "O  基座转轴 / 机械原点", CYAN, size=42)
    label_chip(draw, (665, 790), "A  肘关节", MAGENTA, size=42)
    label_chip(draw, (2910, 850), "P  笔尖 (x, y)", AMBER, size=42)

    # Leader for P clarifies that the raised pen's apparent nib is not the XY point.
    draw.line((PEN_P, (2910, 880)), fill=AMBER, width=7)


def annotate(input_path: Path, output_path: Path) -> None:
    image = Image.open(input_path).convert("RGBA")
    if image.size != (4096, 3072):
        raise ValueError(f"Expected a 4096 x 3072 source image, got {image.size}")

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw_title(draw)
    draw_formula_panel(draw)
    draw_mechanism(draw)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = Image.alpha_composite(image, overlay).convert("RGB")
    result.save(output_path, format="PNG", optimize=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    annotate(args.input, args.output)
