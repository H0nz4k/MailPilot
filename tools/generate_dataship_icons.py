"""Rebuild the two DataShip Windows icons; Pillow is needed only to regenerate.

The legacy app_icon.ico stays unchanged. Windows builds consume the committed ICOs.
"""
from __future__ import annotations

from math import cos, pi, sin
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SIZES = [(size, size) for size in (16, 20, 24, 32, 40, 48, 64, 128, 256)]


def draw_icon(*, worker: bool = False) -> Image.Image:
    # Draw at four times the largest ICO frame for clean edges at small sizes.
    scale = 4
    image = Image.new("RGBA", (256 * scale, 256 * scale))
    draw = ImageDraw.Draw(image)

    def polygon(points, fill):
        draw.polygon([(round(x * scale), round(y * scale)) for x, y in points], fill=fill)

    def rounded(box, radius, fill):
        draw.rounded_rectangle(tuple(round(v * scale) for v in box), radius=radius * scale, fill=fill)

    navy = "#092B62"
    white = "#F5FAFF"
    rounded((8, 8, 248, 248), 48, navy)
    # White passenger ship, orange funnel and cyan water echo the browser's ship.
    rounded((155, 49, 169, 116), 3, white)
    polygon([(169, 50), (193, 58), (169, 67)], "#FFA438")
    rounded((110, 77, 141, 120), 4, "#F57643")
    rounded((106, 74, 145, 85), 3, "#FFAD62")
    rounded((78, 108, 183, 153), 7, white)
    rounded((61, 137, 202, 173), 7, "#E2F2FF")
    polygon([(39, 163), (216, 163), (195, 202), (65, 202)], white)
    polygon([(58, 188), (202, 188), (195, 202), (65, 202)], "#F57643")
    for x in (88, 113, 138, 163):
        rounded((x, 120, x + 13, 130), 2, navy)
    for x in (75, 103, 131, 159, 187):
        rounded((x, 147, x + 11, 155), 2, navy)
    rounded((40, 209, 216, 218), 4, "#41C6E5")
    rounded((62, 225, 194, 232), 3, "#41C6E5")

    if worker:
        # An eight-tooth gear sits above the ship, distinct even in small views.
        cx, cy = 199, 65
        outline = []
        for tooth in range(8):
            for offset, radius in ((-.5, 31), (-.29, 31), (-.22, 39), (.22, 39), (.29, 31)):
                angle = (tooth + offset) * pi / 4
                outline.append((cx + cos(angle) * radius, cy + sin(angle) * radius))
        draw.ellipse((157 * scale, 23 * scale, 241 * scale, 107 * scale), fill=navy)
        polygon(outline, "#FFB547")
        draw.ellipse((184 * scale, 50 * scale, 214 * scale, 80 * scale), fill=navy)
        draw.ellipse((194 * scale, 60 * scale, 204 * scale, 70 * scale), fill=white)

    return image.resize((256, 256), Image.Resampling.LANCZOS)


def build_icons(directory: Path = ROOT / "assets") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for worker, name in ((False, "dataship"), (True, "dataship-worker")):
        image = draw_icon(worker=worker)
        image.save(directory / f"{name}.ico", format="ICO", sizes=SIZES)
        image.save(directory / f"{name}.png")


if __name__ == "__main__":
    build_icons()
    print("Created assets/dataship.ico and assets/dataship-worker.ico (+ PNG previews).")
