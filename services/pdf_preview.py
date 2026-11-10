"""Render the same export PDF to paged PNGs without a system PDF viewer."""
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from collections import Counter

_PDFIUM_LOCK = Lock()  # PDFium is not safe to call concurrently from IO workers.


def example_report(config):
    from stravovaci_sestava import ReportData, MenuSummary, CategorySummary, NormMenuSummary, DinerOrder
    dish = "Kuřecí plátek na bylinkách, dušená rýže, zeleninový salát, ovocný nápoj, čerstvé ovoce a domácí jogurt"
    code = config.categories[0]
    diners = tuple(DinerOrder(name, code, "Ukázková kategorie", "Oběd", 1 + i % 2, "A", dish,
                               diner_number=100 + i, classroom="3.A", collected=i % 2 == 0)
                   for i, name in enumerate(("Alena Novotná", "Jan Dvořák", "Petr Černý", "Eva Nováková")))
    if config.collection_status == "collected":
        diners = tuple(d for d in diners if d.collected)
    elif config.collection_status == "uncollected":
        diners = tuple(d for d in diners if not d.collected)
    count = len(diners)
    counts = Counter(d.menu for d in diners)
    return ReportData(
        menus=tuple(MenuSummary("Oběd", menu, portions, dish) for menu, portions in counts.items()),
        categories=(CategorySummary(code, "Ukázková kategorie", "A", count),),
        norms=tuple(NormMenuSummary("Oběd", "A", menu, portions) for menu, portions in counts.items()), diners=diners,
        subject_name="UKÁZKA – smyšlená jídelna a testovací data", active_categories=config.categories,
        delivery_rows=tuple(("Ukázkový výdej", code, "Ukázková kategorie", menu, portions, dish, "Oběd") for menu, portions in counts.items()),
    )


def generate_preview(config, *, example=False):
    from stravovaci_sestava import create_pdf, fetch_report
    report = example_report(config) if example else fetch_report(config)
    with TemporaryDirectory(prefix="dataship-pdf-preview-") as folder:
        target = Path(folder) / "preview.pdf"
        create_pdf(replace(config, pdf_output=target), report)
        return target.read_bytes()


def render_preview_page(data, page_index=0):
    import pypdfium2 as pdfium
    with _PDFIUM_LOCK, pdfium.PdfDocument(data) as document:
        count = len(document)
        if isinstance(page_index, bool) or not isinstance(page_index, int) or not 0 <= page_index < count:
            raise ValueError("Neplatná stránka náhledu PDF.")
        page = document[page_index]
        bitmap = None
        try:
            bitmap = page.render(scale=1.4)
            image = bitmap.to_pil()
            try:
                output = BytesIO()
                image.save(output, format="PNG")
            finally:
                image.close()
            return output.getvalue(), count
        finally:
            if bitmap:
                bitmap.close()
            page.close()
