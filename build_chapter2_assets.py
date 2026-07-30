from pathlib import Path
import sys

from PIL import Image, ImageOps


def main():
    if len(sys.argv) != 4:
        raise SystemExit(
            "Usage: build_chapter2_assets.py HARDWARE.jpg MARKET.png OUTPUT_DIR"
        )

    hardware_path = Path(sys.argv[1])
    market_path = Path(sys.argv[2])
    output_dir = Path(sys.argv[3])
    output_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(hardware_path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        crop_bottom = min(image.height, 980)
        hardware = image.crop((0, 0, image.width, crop_bottom))
        hardware.save(
            output_dir / "chapter2_scara_hardware.jpg",
            quality=92,
            optimize=True,
        )

    with Image.open(market_path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        side = min(image.width - 60, 900)
        left = (image.width - side) // 2
        top = min(470, max(0, image.height - side))
        market = image.crop((left, top, left + side, top + side))
        market.save(
            output_dir / "chapter2_market_interface.jpg",
            quality=92,
            optimize=True,
        )

    print(output_dir / "chapter2_scara_hardware.jpg")
    print(output_dir / "chapter2_market_interface.jpg")


if __name__ == "__main__":
    main()
