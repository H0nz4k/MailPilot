"""Vygeneruje ikonu pro Windows EXE (ICO) z jednoduché kresby."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "assets" / "app_icon.ico"


def _rounded_rect(draw: ImageDraw.ImageDraw, size: int) -> None:
    pad = max(8, size // 16)
    radius = max(8, size // 5)
    draw.rounded_rectangle(
        (pad, pad, size - pad, size - pad),
        radius=radius,
        fill=(33, 110, 190, 255),
    )
    inner = pad + max(4, size // 20)
    draw.rounded_rectangle(
        (inner, inner, size - inner, size - inner),
        radius=max(6, radius - 6),
        outline=(255, 255, 255, 50),
        width=max(1, size // 48),
    )


def _mark(draw: ImageDraw.ImageDraw, size: int) -> None:
    w = max(5, size // 18)
    # Stylizované "A" + lomítko.
    draw.line(
        ((size * 0.30, size * 0.72), (size * 0.46, size * 0.28)),
        fill=(255, 255, 255, 240),
        width=w,
        joint="curve",
    )
    draw.line(
        ((size * 0.46, size * 0.28), (size * 0.62, size * 0.72)),
        fill=(255, 255, 255, 240),
        width=w,
        joint="curve",
    )
    draw.line(
        ((size * 0.36, size * 0.56), (size * 0.56, size * 0.56)),
        fill=(233, 243, 255, 235),
        width=max(3, w - 2),
    )
    draw.line(
        ((size * 0.66, size * 0.74), (size * 0.80, size * 0.26)),
        fill=(233, 243, 255, 220),
        width=max(3, w - 2),
    )


def build_ico(path: Path) -> None:
    canvas = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    _rounded_rect(draw, 256)
    _mark(draw, 256)
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(
        path,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


if __name__ == "__main__":
    build_ico(TARGET)
    print(TARGET)
