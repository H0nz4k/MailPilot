from dataclasses import replace
from datetime import date
from io import BytesIO
from pathlib import Path
import json
import shutil
from unittest.mock import patch

import pytest
from pypdf import PdfReader

from services.pdf_layout import normalize_layout, normalize_page_breaks, ellipsize
from services.pdf_preview import example_report, generate_preview, render_preview_page
from services.pdf_templates import PdfTemplate, load_templates, save_template, template_file
from services.web_daily_profiles import DailyProfile, apply_profile, save_profile, load_profiles, profile_file
from stravovaci_sestava import AppConfig, create_pdf, load_config


def config(tmp_path, **values):
    return AppConfig(database={}, report_date=date.today(), categories=("1",),
                     language="česky", menu_list_number=1, pdf_output=tmp_path / "test.pdf",
                     pdf_orientation="na_vysku", **values)


@pytest.mark.parametrize("bad", ["menus", [["unknown"]], [["menus", "menus"]], [["menus"], ["menus"]], [[]], [["menus", "categories", "norms"]]])
def test_layout_rejects_invalid_or_duplicated_blocks(bad):
    with pytest.raises(ValueError):
        normalize_layout(bad)


def test_layout_roundtrip_keeps_order_columns_and_missing_blocks():
    layout = normalize_layout([["norms", "categories"], ["menus"]])
    assert layout[:2] == (("norms", "categories"), ("menus",))
    assert normalize_layout(json.loads(json.dumps(layout))) == layout
    assert len([key for row in layout for key in row]) == 6
    assert normalize_page_breaks(["menus", "menus"]) == ("menus",)
    with pytest.raises(ValueError):
        normalize_page_breaks("menus")


def test_fixed_data_rows_shorten_dishes_without_losing_names(tmp_path):
    from reportlab.platypus import LongTable
    tables = []
    class Capture(LongTable):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            tables.append(self)
    cfg = config(tmp_path, pdf_compact_rows=True, category_separation=False)
    report = example_report(cfg)
    long_name = "Jan Josef Václav Novotný Dvořák Černý"
    report = replace(report, diners=(replace(report.diners[0], name=long_name, meal_name="Malé jídlo"),
                                     replace(report.diners[1], meal_name="DLOUHYPOKRM " * 45)))
    with patch("reportlab.platypus.LongTable", Capture):
        text = "\n".join(p.extract_text() for p in PdfReader(create_pdf(cfg, report)).pages)
    assert "…" in text and "DLOUHYPOKRM " * 20 not in text
    assert long_name in text
    fixed = [table for table in tables if table._argH[1:] and table._argH[1] is not None]
    assert fixed and all(len(set(table._rowHeights[1:])) == 1 for table in fixed)
    full = create_pdf(replace(cfg, pdf_compact_rows=False, pdf_output=tmp_path / "full.pdf"), report)
    full_text = " ".join("\n".join(p.extract_text() for p in PdfReader(full).pages).split())
    assert "DLOUHYPOKRM " * 15 in full_text


def test_ellipsis_uses_font_width_and_handles_markup(tmp_path):
    cfg = config(tmp_path)
    create_pdf(cfg, example_report(cfg))  # Registers the actual bundled font.
    from reportlab.pdfbase.pdfmetrics import stringWidth
    result = ellipsize("Česnek <a> & bylinky " * 30, 70, "StravovaciSans", 10)
    assert result.endswith("…")
    assert stringWidth(result, "StravovaciSans", 10) <= 70
    assert ellipsize("Krátké", 100, "StravovaciSans", 10) == "Krátké"


def test_block_order_and_real_side_by_side_coordinates(tmp_path):
    cfg = config(tmp_path, pdf_layout=(("categories", "norms"), ("menus",), ("diners",)), pdf_page_breaks=())
    report = example_report(cfg)
    pages = PdfReader(create_pdf(cfg, report)).pages
    positions = {}
    def visitor(text, cm, tm, font, size):
        for title in ("Přihlášky podle kategorií", "Objednaná menu podle norem", "Jídelníček a počty porcí"):
            if title in text:
                positions[title] = (cm[4] + tm[4], cm[5] + tm[5])
    pages[0].extract_text(visitor_text=visitor)
    left, right = positions["Přihlášky podle kategorií"], positions["Objednaná menu podle norem"]
    assert right[0] > left[0] + 100
    assert abs(right[1] - left[1]) < 2
    assert positions["Jídelníček a počty porcí"][1] < left[1]


def test_two_long_columns_continue_without_lost_orders(tmp_path):
    cfg = config(tmp_path, pdf_layout=(("categories", "diners"), ("menus", "norms")),
                 pdf_page_breaks=(), category_separation=False, pdf_compact_rows=True)
    report = example_report(cfg)
    report = replace(report,
                     diners=tuple(replace(report.diners[i % 4], name=f"Strávník {i:03}") for i in range(130)),
                     categories=tuple(replace(report.categories[0], code=f"K{i:03}", name=f"Kategorie {i:03}") for i in range(90)))
    reader = PdfReader(create_pdf(cfg, report))
    text = "\n".join(p.extract_text() for p in reader.pages)
    assert len(reader.pages) > 1
    assert all(f"Strávník {i:03}" in text for i in range(130))
    assert all(f"Kategorie {i:03}" in text for i in range(90))


def test_page_breaks_and_disabled_sections(tmp_path):
    cfg = config(tmp_path, pdf_layout=(("norms",), ("menus",), ("categories",)),
                 pdf_page_breaks=("menus",), show_by_categories=False, show_diner_list=False)
    pages = [page.extract_text() for page in PdfReader(create_pdf(cfg, example_report(cfg))).pages]
    assert "Objednaná menu podle norem" in pages[0]
    assert "Jídelníček a počty porcí" not in pages[0]
    assert any("Jídelníček a počty porcí" in p for p in pages[1:])
    assert "Přihlášky podle kategorií" not in "\n".join(pages)


def test_too_narrow_layout_reports_actionable_error_instead_of_overflow(tmp_path):
    cfg = config(tmp_path, pdf_layout=(("categories", "norms"),), pdf_label_font_size=18)
    report = example_report(cfg)
    report = replace(report, norms=tuple(replace(report.norms[0], menu=i) for i in range(1, 10)))
    with pytest.raises(ValueError, match="samostatný řádek"):
        create_pdf(cfg, report)


def test_template_roundtrip_snapshot_and_corrupt_store_protection(tmp_path):
    layout = (("categories", "norms"), ("menus",))
    template = PdfTemplate.from_dict({"name": "Kuchyně", "settings": {"pdf_compact_rows": True, "pdf_layout": layout}})
    store = template_file(tmp_path)
    save_template(store, template)
    loaded = load_templates(store)[0]
    assert loaded == template
    profile = DailyProfile.from_dict({"name": "Přehled", "categories": ["1"], **loaded.settings})
    save_profile(profile_file(tmp_path), profile)
    save_template(store, replace(template, settings={**template.settings, "pdf_layout": (("menus",),)}))
    saved = load_profiles(profile_file(tmp_path))[0]
    assert saved.pdf_layout[:2] == layout
    assert apply_profile(config(tmp_path), saved, {"poctyemailem": {"vsechny_kategorie": True}}).pdf_compact_rows
    with pytest.raises(ValueError, match="názvem"):
        save_template(store, replace(template, id="other"))
    store.write_text('{"templates":{}}')
    with pytest.raises(ValueError):
        save_template(store, template)
    assert store.read_text() == '{"templates":{}}'


@pytest.mark.parametrize("bad", [{"categories": ["1"]}, {"pdf_compact_rows": "true"},
                                  {"pdf_data_font_size": 99}, {"pdf_orientation": "invalid"},
                                  {"delivery_page_per_type": True, "pdf_layout": [["delivery", "menus"]]}])
def test_templates_reject_nonappearance_fields_and_invalid_values(bad):
    with pytest.raises(ValueError):
        PdfTemplate.from_dict({"name": "Šablona", "settings": bad})


def test_preview_matches_export_and_renders_pages_without_external_viewer(tmp_path):
    cfg = config(tmp_path, pdf_compact_rows=True)
    data = generate_preview(cfg, example=True)
    assert data.startswith(b"%PDF")
    text = "\n".join(p.extract_text() for p in PdfReader(BytesIO(data)).pages)
    assert "UKÁZKA" in text and "Jan Dvořák" in text
    png, count = render_preview_page(data, 0)
    assert png.startswith(b"\x89PNG") and count >= 2
    assert render_preview_page(data, count - 1)[0].startswith(b"\x89PNG")
    with pytest.raises(ValueError):
        render_preview_page(data, count)


@pytest.mark.asyncio
async def test_editor_template_preview_and_profile_configuration(tmp_path):
    from nicegui.testing.user_simulation import user_simulation
    from stravovaci_nicegui import NiceGuiApp
    path = tmp_path / "config.json"
    shutil.copyfile(Path(__file__).with_name("config.example.json"), path)
    pages = []
    def root():
        app = NiceGuiApp(path)
        app.build()
        app.populate_categories([("1", "Žáci"), ("2", "Hosté")])
        pages.append(app)
    with patch.object(NiceGuiApp, "_stored_password", return_value=""), \
         patch.object(NiceGuiApp, "_stored_api_key", return_value=""), \
         patch.object(NiceGuiApp, "_schedule_first_run"):
        async with user_simulation(root) as user:
            await user.open("/")
            with user:
                app = pages[0]
                designer = app.pdf_designer
                designer.join(2)  # Category and norm summaries beside each other.
                designer.move(1, -1)
                assert designer.rows[0] == ["categories", "norms"]
                designer.swap(0)
                assert designer.rows[0] == ["norms", "categories"]
                app.pdf_compact_rows.value = True
                designer.template_name.value = "Moje kuchyně"
                designer.save(as_new=True)
                template = load_templates(template_file(tmp_path))[0]
                app._apply_daily_categories(["2"])
                app.pdf_compact_rows.value = False
                designer.reset_layout()
                designer.apply_template(template.id)
                assert app.pdf_compact_rows.value
                assert app._manual_daily_categories() == ("2",)
                assert designer.rows[0] == ["norms", "categories"]
                profile = app._current_daily_profile()
                assert profile.pdf_compact_rows and profile.pdf_layout[0] == ("norms", "categories")
                raw = app._collect_config()
                path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
                with patch("stravovaci_sestava.get_password", return_value="dummy"):
                    loaded = load_config(path)
                assert loaded.pdf_compact_rows and loaded.pdf_layout[0] == ("norms", "categories")
                await designer.refresh_preview()
                assert designer.preview_image.visible and "Ukázková data" in designer.preview_status.text
                assert designer._pdf.startswith(b"%PDF")
                app.pdf_bold.value = True
                assert "Aktualizujte náhled" in designer.preview_status.text
                app.meal_type_select.set_options({"večeře": "Večeře"}, value=["večeře"])
                app.connection_ok = True
                app._connection_password = "dummy"
                designer.source.value = "database"
                preview_config = designer._preview_config()
                with patch("stravovaci_sestava.fetch_report", return_value=example_report(preview_config)) as fetch:
                    await designer.refresh_preview()
                assert fetch.call_args.args[0].categories == ("2",)
                assert fetch.call_args.args[0].meal_type == "večeře"
                assert "Vybraná data z Jídelny" in designer.preview_status.text
                app.categories = []
                with pytest.raises(ValueError, match="kategorii"):
                    designer._preview_config()
