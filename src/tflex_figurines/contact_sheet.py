"""Arrange 4 Blender turntable renders into one labeled 2x2 comparison PNG."""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def make_sheet(folder: Path, target: Path, tile: int = 640) -> None:
    if not 128 <= tile <= 2048:
        raise ValueError("tile size must be 128..2048")
    labels = ("front", "left", "back", "right")
    output = Image.new("RGB", (tile * 2, (tile + 48) * 2), (238, 238, 238))
    draw = ImageDraw.Draw(output)
    for i, name in enumerate(labels):
        source = folder / (name + ".png")
        if not source.is_file():
            raise ValueError(f"Missing Blender render: {source}")
        with Image.open(source) as image:
            image = image.convert("RGB")
            image.thumbnail((tile, tile))
            row, col = divmod(i, 2)
            x = col * tile + (tile - image.width) // 2
            y = row * (tile + 48) + (tile - image.height) // 2
            output.paste(image, (x, y))
            draw.text((col * tile + 16, row * (tile + 48) + tile + 10),
                      name.upper(), fill=(25, 25, 25))
    target.parent.mkdir(parents=True, exist_ok=True)
    output.save(target, format="PNG", optimize=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("render_folder", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tile", type=int, default=640)
    args = parser.parse_args(argv)
    make_sheet(args.render_folder, args.output, args.tile)


if __name__ == "__main__":
    main()
