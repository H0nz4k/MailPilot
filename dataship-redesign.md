# DataShip – nový vzhled v NiceGUI aplikaci

Větev `feat/dataship-design-integration` (H0nz4k/MailPilot). Kumulativní patch: `/workspace/dataship-redesign.patch`. Obsahuje i dřívější úpravy z `dataship-ui-fixes.patch`. Nic nebylo pushnuto.

## Ověření
- `git apply --check` proti lokální kopii větve: OK
- `py_compile` všech .py: OK
- pytest (`test_nicegui_helpers.py`, `test_web_daily_workspace.py`, `test_web_mail_tasks.py`) ve venv s NiceGUI 3.18: 36 passed (před úpravou také 36 passed)
- Aplikace spuštěná naostro (bez databáze) a nafocená v Chrome 1440×900: `/workspace/dataship-real/denni-stav.png`, `uzaverka.png`, `emailove-ulohy.png`, `nova-uloha.png`

## Změny po souborech
**ui_theme.py**
- Barevná schémata jsou jen 3: `horcicova` (Hořčicová na antracitu, výchozí), `svestkova` (Švestková s růžovou), `kremova` (Krémová s vínovou, světlé). Hodnoty jsou převzaté z `index-bold.html`.
- Dříve uložená schémata (svetle, tmave, ocean, les, pisek, burgund) neexistují, takže `peek_ui_theme` je automaticky převede na `horcicova`.
- Každé schéma má navíc proměnné `--ds-bar`, `--ds-surface-2`, `--ds-on-primary` (tmavý text na hořčicovém tlačítku) a `--ds-accent-text`.
- Velikosti písma z předchozího patche (text 15 px, popisky 13 px).

**services/web_daily_design_css.py** (veškerá prezentace)
- Horní lišta: sticky, vlastní barva `--ds-bar`, stín, výška 64 px. Navigace v liště, aktivní položka má 3px podtržení. Pilulka stavu připojení je zelená nebo červená. U krémového schématu je lišta vínová s bílým textem.
- Proti „slévání“: karty mají rámeček i stín. Vstupní pole mají viditelný rámeček a hover. Vybrané skupiny a sestavy jsou plné (hořčicové s tmavým textem), nevybrané jen obrysové. Primární tlačítko (`ds-primary-cta`) je 48 px vysoké a má stín. Všechna tlačítka mají hover a stisk.
- Denní stav je jeden sloupec široký max. 760 px. Řádek „Celkem … porcí“ s přepínačem detailu.
- Uzávěrka: číslované kroky a dlaždice sestav.
- E-mailové úlohy: prázdný stav a boční panel (drawer).

**stravovaci_nicegui.py**
- `_build_topbar`: logo, DataShip, název školy, navigace (`_build_navigation` se volá odtud), období, pilulka připojení s tooltipem, Administrace a přepínač tématu (hořčicová ↔ krémová).
- Interní hodnoty „DB OK“ / „BEZ SPOJENÍ“ se uživateli ukazují jako „Připojeno“ / „Bez spojení“ (`CONNECTION_CAPTION_TEXT`).
- Období („Říjen 2026“) se po TESTu připojení vytáhne z detailu (`connection_period_text`).
- Akční lišta: primární tlačítko je „Vytvořit PDF“. „Vytvořit a odeslat“ i „Otevřít poslední“ zůstávají jako vedlejší. Předmět mailu je skrytý.
- Uzávěrka je rozdělená do 3 kroků:
  1. Které sestavy (checkboxy jako dlaždice).
  2. Co s nimi udělat (ZIP a e-mail jako přepínače `ui.switch`; hodnota i ukládání `save_closing_settings` jsou stejné).
  3. Informace, že se nastavení ukládá samo.
  Složka pro uložení je pod „Pokročilé“.
- Z předchozího patche: toasty místo stavového pruhu, skryté CLI texty, cesty a server.

**services/web_daily_design.py**
- Pravá karta „Souhrn“ je odstraněná. Celkový počet je pod skupinami strávníků v řádku „Celkem N porcí“.
- „Zobrazit detail / Skrýt detail“ připíše do štítku skupiny její počet („Žáci … · 180“). Nulové počty jsou ztlumené. Výchozí stav je vypnuto.
- Tabulka a ostatní souhrnné prvky (`daily_summary_*`) dál existují, jen jsou skryté, takže stávající logika a testy fungují.

**services/web_mail_gui.py**
- Nadpis se značkou ⓘ, v jejím tooltipu je informace o plánovací službě a cesta ke konfiguraci.
- Prázdný stav: ikona, vysvětlení a jedno tlačítko „Nová úloha“. Když úlohy existují, nahoře jsou tlačítka „Obnovit“ a „Nová úloha“.
- Editor úlohy je boční panel vpravo (`ui.dialog` s `position=right maximized`).
- Pole „Posun“ a „Konkrétní datum“ se ukážou jen u příslušného režimu. Uložený přehled a „Úloha aktivní“ jsou pod „Pokročilé“.

**test_nicegui_helpers.py**
- Očekávané hodnoty upravené záměrně: velikosti písma 14 a 13, nová schémata a mapování starých schémat na `horcicova`.

**config.example.json**
- `ui_barevne_schema` je `horcicova`.

## Rizika / neověřeno
- **Bez databáze:** nafoceno bez připojení k Jídelně. Štítky skupin, „Celkem“, detail s počty a období v liště jsem neviděl s reálnými daty. Logiku detailu jsem nespouštěl proti DB.
- **Celkový počet** se počítá jako porce všech menu (stávající `report.menus`). Proto je popisek „porcí“, ne „obědů“.
- **Uzávěrka:** aplikace nemá tlačítko pro spuštění uzávěrky (běží z Jídelny přes CLI). Krok 3 proto jen vysvětluje, nic nespouští.
- **Testy:** spuštěny jen 3 testovací soubory, ke kterým byly stažené závislosti. Ostatní (Qt, sestavy, plánovač) ne.
- **Rekonstrukce souborů:** soubory jsou poskládané z GitHub API. Případný rozdíl v koncovém odřádkování by mohl způsobit, že `git apply` na skutečném checkoutu selže. V tom případě použij `git apply --3way`.
- **Šířka a uložené nastavení:** horní lišta se drží šířky obsahu (max. 1240 px), na širokém monitoru tedy není přes celou šířku. Uživatelská nastavení šablony (dashboard/minimal) a zoom zůstávají a mohou vzhled ovlivnit.
- **Drobnosti:** aktivní záložka má ještě jemné šedé pozadí ze základního CSS. „Vytvořit PDF“ je při výšce 900 px až na spodním okraji obrazovky (lišta je sticky).
