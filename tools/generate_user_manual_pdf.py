"""Generate a styled user manual PDF from markdown."""

from __future__ import annotations

from pathlib import Path
import textwrap
from datetime import datetime

import pymupdf as fitz


ROOT = Path(__file__).resolve().parents[1]
VERSION = "12.8"
VERSION_SLUG = "v12_8"
SOURCE = ROOT / f"UZIVATELSKY_NAVOD_MailPilot_{VERSION_SLUG}.md"
TARGET = ROOT / f"UZIVATELSKY_NAVOD_MailPilot_{VERSION_SLUG}.pdf"
STABLE_COPY = ROOT / "UZIVATELSKY_NAVOD_MailPilot.pdf"
LEGACY_COPY = ROOT / "UZIVATELSKY_NAVOD_AutoReport_v10_4.pdf"

PAGE_W = 595
PAGE_H = 842
MARGIN_X = 44
MARGIN_TOP = 44
MARGIN_BOTTOM = 44

COLOR_TEXT = (0.11, 0.14, 0.2)
COLOR_MUTED = (0.37, 0.42, 0.5)
COLOR_ACCENT = (0.14, 0.39, 0.68)
COLOR_ACCENT_SOFT = (0.9, 0.95, 1.0)
COLOR_LIGHT_LINE = (0.84, 0.88, 0.94)


def _font_file() -> str | None:
    candidates = (
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path(r"C:\Windows\Fonts\segoeui.ttf"),
        Path(r"C:\Windows\Fonts\calibri.ttf"),
    )
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def _draw_line(
    page: fitz.Page,
    x: float,
    y: float,
    text: str,
    fontname: str,
    fontsize: float,
) -> None:
    page.insert_text(
        fitz.Point(x, y),
        text,
        fontname=fontname,
        fontsize=fontsize,
        color=COLOR_TEXT,
    )


def generate(
    source: Path = SOURCE,
    target: Path = TARGET,
    stable_copy: Path | None = STABLE_COPY,
    legacy_copy: Path | None = LEGACY_COPY,
) -> Path:
    text = source.read_text(encoding="utf-8")
    lines = text.splitlines()

    doc = fitz.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)  # A4 portrait
    x = MARGIN_X
    y = MARGIN_TOP
    line_h = 15.0
    body_size = 11.0
    heading1_size = 22.0
    heading2_size = 15.5
    heading3_size = 12.5

    fontfile = _font_file()
    if fontfile:
        fontname = "manualfont"
        page.insert_font(fontname=fontname, fontfile=fontfile)
    else:
        fontname = "helv"

    max_width_chars = 88

    def new_page() -> None:
        nonlocal page, y
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        if fontfile:
            page.insert_font(fontname=fontname, fontfile=fontfile)
        # Header stripe on each content page.
        page.draw_rect(
            fitz.Rect(0, 0, PAGE_W, 28),
            color=None,
            fill=COLOR_ACCENT_SOFT,
            overlay=True,
        )
        page.draw_line(
            fitz.Point(0, 28),
            fitz.Point(PAGE_W, 28),
            color=COLOR_LIGHT_LINE,
            width=1,
        )
        page.insert_text(
            fitz.Point(MARGIN_X, 19),
            f"MailPilot v{VERSION} - Uzivatelsky navod",
            fontname=fontname,
            fontsize=9.0,
            color=COLOR_MUTED,
        )
        y = MARGIN_TOP + 8

    def ensure_space(height: float) -> None:
        nonlocal y
        if y + height > PAGE_H - MARGIN_BOTTOM:
            new_page()

    def draw_cover() -> None:
        nonlocal y
        # Top accent bar.
        page.draw_rect(
            fitz.Rect(0, 0, PAGE_W, 132),
            color=None,
            fill=COLOR_ACCENT,
            overlay=True,
        )
        page.insert_text(
            fitz.Point(MARGIN_X, 58),
            f"MailPilot v{VERSION}",
            fontname=fontname,
            fontsize=28,
            color=(1, 1, 1),
        )
        page.insert_text(
            fitz.Point(MARGIN_X, 88),
            "Uzivatelsky navod",
            fontname=fontname,
            fontsize=16,
            color=(1, 1, 1),
        )
        page.insert_text(
            fitz.Point(MARGIN_X, 112),
            f"Aktualizace: {datetime.now().strftime('%d.%m.%Y')}",
            fontname=fontname,
            fontsize=10.5,
            color=(0.92, 0.96, 1),
        )

        y = 176
        page.insert_text(
            fitz.Point(MARGIN_X, y),
            "Co v navodu najdete",
            fontname=fontname,
            fontsize=heading2_size,
            color=COLOR_ACCENT,
        )
        y += 22
        bullets = (
            "Role bezny uzivatel / administrator",
            "Prvni nastaveni databaze a e-mailu",
            "Denni stav, Uzaverka, Special, Hromadna zprava",
            "Prehled automailu a rucni opakovani",
            "Vzhled aplikace a klavesove zkratky",
            "JidelnaSQL warning a testovaci tlacitka",
        )
        for item in bullets:
            page.insert_text(
                fitz.Point(MARGIN_X + 8, y),
                f"- {item}",
                fontname=fontname,
                fontsize=11.3,
                color=COLOR_TEXT,
            )
            y += 19

        y += 16
        page.draw_line(
            fitz.Point(MARGIN_X, y),
            fitz.Point(PAGE_W - MARGIN_X, y),
            color=COLOR_LIGHT_LINE,
            width=1,
        )
        y += 24
        page.insert_text(
            fitz.Point(MARGIN_X, y),
            "Tip: V aplikaci otevrite N\u00e1pov\u011bda v levem menu (F1).",
            fontname=fontname,
            fontsize=10.5,
            color=COLOR_MUTED,
        )

    def draw_wrapped_block(
        text_value: str,
        *,
        width: int,
        size: float,
        color: tuple[float, float, float],
        indent: float = 0,
        spacing_after: float = 8.0,
    ) -> None:
        nonlocal y
        wrapped = textwrap.wrap(
            text_value,
            width=width,
            break_long_words=False,
            break_on_hyphens=False,
        )
        if not wrapped:
            wrapped = [text_value]
        block_h = len(wrapped) * (line_h if size <= body_size else line_h * 1.1)
        ensure_space(block_h + spacing_after)
        for part in wrapped:
            page.insert_text(
                fitz.Point(x + indent, y),
                part,
                fontname=fontname,
                fontsize=size,
                color=color,
            )
            y += line_h if size <= body_size else line_h * 1.1
        y += spacing_after

    draw_cover()
    new_page()

    in_list = False
    for raw in lines:
        stripped = raw.strip()
        is_h1 = stripped.startswith("# ")
        is_h2 = stripped.startswith("## ")
        is_h3 = stripped.startswith("### ")
        is_bullet = stripped.startswith("- ")
        is_numbered = (
            len(stripped) > 2
            and stripped[0].isdigit()
            and stripped[1] == "."
            and stripped[2] == " "
        )
        content = stripped
        if is_h1:
            content = stripped[2:].strip()
        elif is_h2:
            content = stripped[3:].strip()
        elif is_h3:
            content = stripped[4:].strip()
        elif is_bullet:
            content = stripped[2:].strip()
        elif is_numbered:
            content = stripped[3:].strip()

        if not content:
            y += 6
            in_list = False
            continue

        if is_h1:
            ensure_space(34)
            page.draw_line(
                fitz.Point(MARGIN_X, y - 8),
                fitz.Point(PAGE_W - MARGIN_X, y - 8),
                color=COLOR_LIGHT_LINE,
                width=1,
            )
            draw_wrapped_block(
                content,
                width=56,
                size=heading1_size,
                color=COLOR_ACCENT,
                spacing_after=10.0,
            )
            in_list = False
            continue

        if is_h2:
            draw_wrapped_block(
                content,
                width=72,
                size=heading2_size,
                color=COLOR_ACCENT,
                spacing_after=6.0,
            )
            in_list = False
            continue

        if is_h3:
            draw_wrapped_block(
                content,
                width=76,
                size=heading3_size,
                color=COLOR_TEXT,
                spacing_after=5.0,
            )
            in_list = False
            continue

        if is_bullet:
            draw_wrapped_block(
                f"- {content}",
                width=max_width_chars - 2,
                size=body_size,
                color=COLOR_TEXT,
                indent=10,
                spacing_after=2.5,
            )
            in_list = True
            continue

        if is_numbered:
            draw_wrapped_block(
                f"{stripped[:2]} {content}",
                width=max_width_chars - 2,
                size=body_size,
                color=COLOR_TEXT,
                indent=10,
                spacing_after=2.5,
            )
            in_list = True
            continue

        draw_wrapped_block(
            content,
            width=max_width_chars,
            size=body_size,
            color=COLOR_TEXT,
            spacing_after=4.0 if in_list else 7.0,
        )
        in_list = False

    target.parent.mkdir(parents=True, exist_ok=True)
    doc.save(target)
    doc.close()
    if stable_copy is not None:
        stable_copy.write_bytes(target.read_bytes())
    if legacy_copy is not None:
        legacy_copy.write_bytes(target.read_bytes())
    return target


if __name__ == "__main__":
    out = generate()
    print(str(out))
