"""Generate the V32 five-point measurement guide."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "docs"
    / "diagnostics"
    / "AUTHOR_FINAL_XY20_5POINT_DOTS_L205_L203_GATED_V32_PREVIEW.png"
)

POINTS = {
    "O": (205.0, 65.0),
    "W": (185.0, 65.0),
    "E": (225.0, 65.0),
    "S": (205.0, 45.0),
    "N": (205.0, 85.0),
}

WIDTH = 900
HEIGHT = 700
SCALE = 10.0
ORIGIN_X = 450
ORIGIN_Y = 360


def pixel(point: tuple[float, float]) -> tuple[int, int]:
    return (
        round(ORIGIN_X + (point[0] - 205.0) * SCALE),
        round(ORIGIN_Y - (point[1] - 65.0) * SCALE),
    )


def arrowhead(draw: ImageDraw.ImageDraw, tip: tuple[int, int], direction: str) -> None:
    x, y = tip
    if direction == "left":
        draw.polygon([(x, y), (x + 12, y - 6), (x + 12, y + 6)], fill=(40, 100, 190))
    elif direction == "right":
        draw.polygon([(x, y), (x - 12, y - 6), (x - 12, y + 6)], fill=(40, 100, 190))
    elif direction == "up":
        draw.polygon([(x, y), (x - 6, y + 12), (x + 6, y + 12)], fill=(40, 100, 190))
    else:
        draw.polygon([(x, y), (x - 6, y - 12), (x + 6, y - 12)], fill=(40, 100, 190))


def main() -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(image)
    draw.text((28, 24), "V32 FINAL XY20 FIVE-POINT MEASUREMENT GUIDE", fill=(15, 15, 15))
    draw.text(
        (28, 48),
        "ONLY THE FIVE BLACK DOT LOCATIONS ARE MARKED BY THE MACHINE",
        fill=(180, 30, 30),
    )
    draw.text(
        (28, 70),
        "BLUE DIMENSION LINES AND LABELS ARE REFERENCE ONLY - NOT DRAWN",
        fill=(40, 100, 190),
    )

    w = pixel(POINTS["W"])
    e = pixel(POINTS["E"])
    s = pixel(POINTS["S"])
    n = pixel(POINTS["N"])
    o = pixel(POINTS["O"])

    horizontal_y = o[1] - 70
    draw.line([(w[0], horizontal_y), (e[0], horizontal_y)], fill=(40, 100, 190), width=3)
    arrowhead(draw, (w[0], horizontal_y), "left")
    arrowhead(draw, (e[0], horizontal_y), "right")
    draw.text((o[0] - 24, horizontal_y - 24), "40 mm", fill=(40, 100, 190))

    vertical_x = o[0] + 70
    draw.line([(vertical_x, n[1]), (vertical_x, s[1])], fill=(40, 100, 190), width=3)
    arrowhead(draw, (vertical_x, n[1]), "up")
    arrowhead(draw, (vertical_x, s[1]), "down")
    draw.text((vertical_x + 12, o[1] - 7), "40 mm", fill=(40, 100, 190))

    draw.text((w[0] + 72, o[1] + 18), "20 mm", fill=(40, 100, 190))
    draw.text((o[0] + 72, o[1] + 18), "20 mm", fill=(40, 100, 190))
    draw.text((o[0] - 58, n[1] + 88), "20 mm", fill=(40, 100, 190))
    draw.text((o[0] - 58, o[1] + 88), "20 mm", fill=(40, 100, 190))

    for name, coordinate in POINTS.items():
        x, y = pixel(coordinate)
        radius = 9
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(10, 10, 10))
        draw.text((x + 14, y - 20), f"{name} ({coordinate[0]:.0f},{coordinate[1]:.0f})", fill=(15, 15, 15))

    draw.line([(700, 580), (790, 580)], fill=(40, 100, 190), width=3)
    arrowhead(draw, (790, 580), "right")
    draw.text((716, 550), "+X", fill=(40, 100, 190))
    draw.line([(700, 580), (700, 490)], fill=(40, 100, 190), width=3)
    arrowhead(draw, (700, 490), "up")
    draw.text((712, 505), "+Y", fill=(40, 100, 190))

    draw.text((28, 620), "MARK ORDER: O, W, O, E, O, S, O, N, O", fill=(15, 15, 15))
    draw.text((28, 644), "CENTER O IS STAMPED FIVE TIMES; W/E/S/N ONCE EACH", fill=(15, 15, 15))
    draw.text((28, 668), "ALIGN (150,20) IS PEN-UP ONLY AND IS NOT MARKED", fill=(15, 15, 15))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT)
    print(f"preview={OUTPUT}")


if __name__ == "__main__":
    main()
