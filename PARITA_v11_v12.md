# Funkční parita v11 → v12

Seznam vznikl z inventáře v11 (NiceGUI rozhraní, konzolové režimy, servisní
moduly, konfigurace, spouštěče a testy). U každé položky je uvedeno, kde je
funkce ve v12 a čím je ověřená.

Legenda: **ano** = přeneseno a napojené na skutečnou logiku.

## Denní stav

| Funkce v11 | Stav | Kde ve v12 | Ověření |
| --- | --- | --- | --- |
| Volba data (DD.MM.RRRR, tlačítko Dnes) | ano | Denní stav | `DailyPageTests` |
| Výběr povolených kategorií z `public.kategor` | ano | Denní stav → Změnit… | `CategoryDialogTests` |
| Kontrola zaniklých kategorií proti databázi | ano | `services/daily.py` | `test_services_qt.py` |
| Orientace, jazyk, číslo jídelníčku, velikosti písma, tučná data | ano | Pokročilé nastavení PDF | `DailyPageTests` |
| Tabulky „podle kategorií“ a „podle norem“ | ano | Pokročilé nastavení PDF | `test_services_qt.py` |
| Výstupní cesta PDF se zástupnými znaky | ano | Administrace → PDF | `test_services_qt.py` |
| Přehled porcí (načtení z databáze) | ano | Denní stav, `F9` | ostrý běh nad PostgreSQL |
| Vytvoření PDF | ano | Denní stav, `F5` | ostrý běh, PDF v `vystup` |
| Vytvoření a odeslání e-mailem | ano | Denní stav | ostrý běh `--poctyemailem` |
| Informace o posledním PDF a mailu | ano | Patička obrazovky | `DailyPageTests` |
| Odesílat jen ve varných dnech | ano | Administrace → E-maily | beze změny logiky |
| Potvrzení před odesláním | ano | dialog před odesláním | `MainWindowTests` |

## Uzávěrka

| Funkce v11 | Stav | Kde ve v12 | Ověření |
| --- | --- | --- | --- |
| Měsíc a rok období | ano | Uzávěrka | `ClosingPageTests` |
| Aktuální měsíc z Jídelny (`--zaverka_am`) | ano | Uzávěrka, přepínač | ostrý běh CLI |
| Výběr sestav FKSP / stravovací arch / rekapitulace | ano | Uzávěrka | `ClosingPageTests` |
| Varianta archu a rekapitulace | ano | Pokročilé nastavení uzávěrky | `test_services_qt.py` |
| Výstupní složka se `{rok}` a `{mesic}` | ano | Uzávěrka → Procházet | `test_services_qt.py` |
| Zabalení do ZIP | ano | Uzávěrka | ostrý běh, `Uzaverka_2026-07.zip` |
| Odeslání mailem s vlastními příjemci | ano | Uzávěrka + Administrace → E-maily | `test_services_qt.py` |
| Poslední výstup a otevření složky | ano | Patička obrazovky | `ClosingPageTests` |
| CLI `--zaverka_MMRRRR`, `--uzaverka_MMRRRR`, `--zaverka_am` | ano | `services/cli.py` | ostrý běh, `test_portable_build.py` |

## Speciál · Z 17-01

| Funkce v11 | Stav | Kde ve v12 | Ověření |
| --- | --- | --- | --- |
| Rok výkazu a stav k 31. 10. | ano | Speciál | `SpecialPageTests` |
| Všechny kategorie / jen zvolené | ano | Speciál | `SpecialPageTests` |
| Vlastní výběr kategorií oddělený od denní sestavy | ano | Speciál → Změnit… | `test_services_qt.py` |
| Výstupní cesta se `{rok}` | ano | Speciál → Procházet | `test_services_qt.py` |
| Vytvoření PDF podkladu | ano | Speciál | ostrý běh, PDF v `vystup/z17/2026` |
| Poslední PDF a otevření složky | ano | Patička obrazovky | `SpecialPageTests` |
| Mapování kategorií na řádky 0102–0114a | ano | Administrace → Pokročilé | `test_services_qt.py` |
| Doplňková jídla v rámci vyhlášky | ano | Administrace → Pokročilé | `test_services_qt.py` |
| CLI `--z17_RRRR` | ano | `services/cli.py` | ostrý běh, `test_portable_build.py` |

## Hromadná zpráva

| Funkce v11 | Stav | Kde ve v12 | Ověření |
| --- | --- | --- | --- |
| Filtr podle tříd | ano | Hromadná zpráva | `BulkPageTests` |
| Filtr podle kategorií | ano | Hromadná zpráva | `BulkPageTests` |
| Načtení příjemců z databáze | ano | Hromadná zpráva | ostrý běh: 1296 strávníků, 86 tříd, 21 kategorií |
| Seznam příjemců s e-maily | ano | tabulka Příjemci | `BulkPageTests` |
| Počet vybraných a chybějící e-maily | ano | souhrn nad tabulkou | `BulkPageTests` |
| Předmět a text zprávy | ano | Hromadná zpráva | `test_services_qt.py` |
| Uložení předmětu a textu do configu | ano | `services/bulk.py` | `test_services_qt.py` |
| Odeslání samostatných zpráv (adresy se nesdílí) | ano | tlačítko Odeslat | logika `hromadna_zprava.py` beze změny |
| Zakázané odeslání bez příjemců nebo textu | ano | stav tlačítka | `BulkPageTests` |

Ostré hromadné rozeslání se záměrně netestovalo: šlo by o skutečné maily
1296 strávníkům. Ověřen je celý řetězec až po sestavení zprávy a příjemců.

## Administrace

| Funkce v11 | Stav | Kde ve v12 |
| --- | --- | --- |
| Server, port, databáze, uživatel, maskované heslo | ano | Databáze |
| Test připojení a uložení hesla do Credential Manageru | ano | Databáze |
| Název provozovny, období, kategorie, stav spojení | ano | hlavička okna a Databáze |
| Odesílatel a Resend API klíč (ukládá se do `.env`) | ano | E-maily |
| Příjemci podle funkce (denní stav, uzávěrka, Z 17-01) | ano | E-maily |
| Text a předmět zpráv | ano | E-maily, Hromadná zpráva |
| Úlohy plánovače: název, funkce, plán, čas, zapnuto | ano | Plánovač |
| Ukládání do `planovac.json` | ano | Plánovač |
| Příkazy pro spuštění bez GUI | ano | Bez GUI |
| Vzhled PDF a výstupní cesta | ano | PDF |
| Motiv světlý / tmavý | ano | Vzhled |
| Systémový motiv podle Windows | nově | Vzhled |
| Zvětšení rozhraní 90–160 % | nově | Vzhled a nabídka Zobrazení |
| Přehled souborů aplikace a míst s tajemstvími | ano | Pokročilé |
| Mapování Z 17-01 | ano | Pokročilé |

## Běh bez okna a integrace

| Funkce v11 | Stav | Poznámka |
| --- | --- | --- |
| `--automatic` / `--poctyemailem` | ano | `MailPilot.exe --poctyemailem`, ověřeno ostrým odesláním |
| `--zaverka_MMRRRR`, `--uzaverka_MMRRRR` | ano | ověřeno pro 07/2026 |
| `--zaverka_am`, `--uzaverka_am` | ano | období z `public.parametry` |
| `--z17_RRRR` | ano | ověřeno pro 2026 z EXE i ze zdrojů |
| `--config`, `--log` | ano | předává se do všech režimů |
| Chybné kombinace přepínačů | ano | návratový kód 2 a srozumitelná hláška |
| Spouštěče `spustit_*.bat` | ano | volají EXE, jinak `AutoReport_qt.py` |
| Windows Task Scheduler | ano | stejné BAT soubory, návratové kódy beze změny |
| Logy `logy\*.log` s rotací | ano | beze změny |

## Co se záměrně liší

- Administrace nemá druhý svislý panel; sekce se přepínají vodorovnou
  navigací nad obsahem.
- Hustota rozhraní z v11 je nahrazena jedním zvětšením 90–160 %. Staré
  hodnoty z configu se převedou.
- Motiv `system` je nový; `light` zůstává výchozí.
- Webové rozhraní NiceGUI zůstává v projektu a funguje, ale není součástí
  EXE a nové funkce se do něj nedoplňují.
