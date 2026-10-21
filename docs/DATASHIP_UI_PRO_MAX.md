# DataShip · nové rozhraní a uložené denní přehledy

Implementace schváleného konceptu ui-ux-pro-max do existující NiceGUI aplikace.

## Co se změnilo

- Denní stav má formulář s přehledy vlevo a souhrn skutečných počtů porcí vpravo. Na menších obrazovkách se obsah skládá do sloupce.
- Nové společné styly upravují hlavičku, navigaci, formuláře a akce. Světlý a tmavý motiv mají modré akcenty; další dosavadní barevná schémata a rozvržení zůstávají dostupná.
- Výchozí střední velikost textu je 16 px, větší 18 px a extra velká 20 px. Přiblížení a volba velikosti písma fungují dál.
- Přepínač motivu v hlavičce ukládá vzhled a vrací se z tmavého motivu na předchozí světlé schéma.
- Typ stravy zůstává viditelný i bez spojení. Uložený filtr se při změně dne nerozšiřuje na všechny typy, pokud zvolený typ nemá objednávky.
- Souhrn načítá stávající `fetch_report`; změny filtrů mají prodlevu 450 ms a zastaralá odpověď nesmí přepsat novější výběr. Souhrn negeneruje PDF, neukládá přístupové údaje a neodesílá e-mail.

## Dva přehledy pro různé kategorie

1. Proveďte TEST databáze v Administraci. Správce zde nadále určuje dostupné kategorie.
2. V Denním stavu pojmenujte první přehled, zaškrtněte například dvě kategorie a zvolte **Uložit přehled**.
3. Zvolte **Nový přehled**, pojmenujte jej, vyberte jiné čtyři kategorie a uložte.
4. Mezi přehledy přepínáte tlačítky nad formulářem. Každý si pamatuje vlastní kategorie, typ stravy, oddělení kategorií, součty kategorií/norem a zapnutí seznamu strávníků.
5. Platné rozpracované změny se při přepnutí uloží. Neplatný formulář se nezahodí; nejprve opravte název nebo výběr kategorií.

Přehledy jsou v `daily_reports.json` vedle provozního `config.json`. Datum je pracovní volba pro ruční sestavu; po spuštění aplikace zůstává výchozí dnešní datum. První uložený přehled se načte při otevření. Nezakládají se žádné ukázkové kategorie ani ukázková data.

Při každém TESTu se uložený výběr protne s aktuálně dostupnými a povolenými kategoriemi. Přehled proto neobchází oprávnění správce. Poškozený soubor přehledů se při ukládání automaticky nepřepisuje.

## Vlastní přehled v e-mailové úloze

V **E-mailové úlohy → Nová úloha / Upravit → Uložený denní přehled** vyberte požadovaný přehled. Každá úloha může mít jiné kategorie, příjemce, čas a pravidlo data. Uložení úlohy samo nic neodesílá.

Starší úlohy bez `profile_id` používají dosavadní společné nastavení. Worker při každém spuštění znovu načte přehled a povolené kategorie. Chybějící přehled nebo úplně zakázaný výběr skončí chybou; nikdy se tiše nenahradí všemi kategoriemi. Výstupní PDF úloh s přehledem má vlastní příponu, aby nepřepsalo výstup jiného přehledu.

Pro úlohy s přehledem je potřeba nová verze **GUI i DataShip-Worker.exe**. Při zkoušení samotného GUI stávající službu neměňte. Nové úlohy s přehledem aktivujte až po aktualizaci workeru; starší worker volbu `profile_id` nezná. Před aktualizací workeru zastavte dosavadní NSSM službu a po výměně EXE spusťte znovu stejnou službu; nezakládejte druhou instanci.

## Spuštění na Windows v Git Bash

Z kořene již staženého repozitáře:

```bash
git fetch origin
git switch feat/dataship-design-integration
git pull --ff-only
bash scripts/run_web_dev_windows.sh
```

Pro nové samostatné Windows EXE:

```bash
bash scripts/build_web_windows.sh
./dist-web/DataShip/DataShip.exe --browser
```

Build zachovává i `daily_reports.json`, vedle dosavadní konfigurace a e-mailových úloh. Spuštění ze zdrojů nové EXE nevytváří a worker samo neaktualizuje.

## Kontrola

- Cílené testy skutečného NiceGUI rozhraní, nezávislosti uložených filtrů, opožděných odpovědí souhrnu, ukládání, omezování kategorií a předání přehledu workeru; e-mailové transporty jsou nahrazené testovacími objekty.
- Regresní testy hlavní navigace, data, značky, kategorií, názvů výstupů a původních e-mailových úloh.
- Výsledek cílené sady: **65 testů a 2 podtesty prošly**. Rozhraní bylo ověřeno v Chromium na 320, 375, 768, 1024 a 1440 px bez přetečení dokumentu a bez chyb JavaScriptu; kontrolovány byly snímky světlého, tmavého a mobilního zobrazení. Pro tuto vizuální kontrolu byly použity izolované testovací počty, nikoliv zákaznická DB.
- Windows build, skutečná zákaznická DB, přihlašovací údaje a NSSM vyžadují ověření na cílovém počítači. V rámci implementace neproběhlo skutečné odeslání e-mailu.

Původní Qt MailPilot, CLI přepínače, výpočty PDF a kalendář varných dnů zůstávají na dosavadní implementaci.
