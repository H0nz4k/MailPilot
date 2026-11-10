"""Validated PDF block positions, shared by the editor and renderer."""
SECTIONS = {
    "menus": "Jídelníček a počty porcí",
    "categories": "Souhrn podle kategorií",
    "norms": "Souhrn podle norem",
    "delivery": "Souhrn podle typů výdeje",
    "diners": "Seznam strávníků",
    "collection": "Seznam odběrů stravy",
}
DEFAULT_LAYOUT = tuple((key,) for key in SECTIONS)


def normalize_layout(value):
    if value is None or value == () or value == []:
        return ()
    if not isinstance(value, (list, tuple)) or len(value) > len(SECTIONS):
        raise ValueError("Rozložení PDF musí obsahovat řádky bloků.")
    result, seen = [], set()
    for row in value:
        if not isinstance(row, (list, tuple)) or not 1 <= len(row) <= 2:
            raise ValueError("Na jednom řádku mohou být jeden nebo dva bloky.")
        if any(not isinstance(key, str) or key not in SECTIONS or key in seen for key in row) or len(set(row)) != len(row):
            raise ValueError("Blok PDF je neznámý nebo se v rozložení opakuje.")
        seen.update(row)
        result.append(tuple(row))
    # Older templates still show newly introduced blocks when enabled.
    result.extend((key,) for key in SECTIONS if key not in seen)
    return tuple(result)


def normalize_page_breaks(value):
    if value is None:
        return ("diners",)
    if not isinstance(value, (list, tuple)) or any(not isinstance(k, str) or k not in SECTIONS for k in value):
        raise ValueError("Neplatné zalomení stránky PDF.")
    return tuple(dict.fromkeys(value))


def layout_story(layout, breaks, builders, width):
    from reportlab.platypus import PageBreak, Spacer, Table, TableStyle
    from reportlab.lib.units import mm
    story = []
    for row in normalize_layout(layout) or DEFAULT_LAYOUT:
        keys = [key for key in row if key in builders]
        if not keys:
            continue
        if any(key in breaks for key in keys):
            story.append(PageBreak())
        if len(keys) == 1:
            story.extend(builders[keys[0]](width))
        else:
            gap = 6 * mm
            column = (width - gap) / 2
            # splitInRow lets each nested LongTable continue across pages.
            story.append(Table([[builders[keys[0]](column), "", builders[keys[1]](column)]],
                               colWidths=[column, gap, column], splitByRow=0, splitInRow=1,
                               style=TableStyle([
                                   ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                   ("TOPPADDING", (0, 0), (-1, -1), 0),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                               ])))
        story.append(Spacer(1, 2 * mm))
    return story


def ellipsize(value, width, font, size):
    """Fit real font metrics, including the ellipsis, without splitting words of markup."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    text = " ".join(str(value).split())
    if stringWidth(text, font, size) <= width:
        return text
    marker = "…"
    if stringWidth(marker, font, size) > width:
        return ""
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if stringWidth(text[:mid] + marker, font, size) <= width:
            low = mid
        else:
            high = mid - 1
    return text[:low].rstrip() + marker
