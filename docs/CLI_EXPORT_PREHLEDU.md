# Export uloženého přehledu – DataShip {{VERSION}}

Přehled si nejprve uložte v aplikaci, například jako **mujprehled**. V místní instalaci musí zůstat jeho `daily_reports.json`, nastavení databáze a uložené heslo k databázi. Pro tento export není potřeba heslo administrace, e-mail, API klíč ani služba NSSM.

V Git Bash ve složce s EXE:

```bash
./DataShip.exe --export-report "mujprehled"
```

Příkaz pouze načte data a vytvoří PDF. Neotevře web, nespouští plánovač a nic neodesílá. Bez určení data použije dnešek, nikoli datum posledního náhledu uložené v konfiguraci.

## Zástupce na ploše Windows

Vytvořte zástupce na `DataShip.exe`. Do pole **Cíl** zadejte například:

```text
"C:\DataShip\DataShip.exe" --export-report "mujprehled" --open-pdf
```

Zástupce pojmenujte **Můj přehled**. Dvojklik vytvoří dnešní PDF a otevře ho v nastaveném prohlížeči PDF. Webové rozhraní DataShipu se neotevře. Pokud chcete jen soubor uložit, vynechte `--open-pdf`. VBS ani pomocný skript nejsou potřeba.

## Datum a cílový soubor

```bash
./DataShip.exe --export-report "mujprehled" --date 2027-01-15 --open-pdf
./DataShip.exe --export-report "mujprehled" --days-ahead 1 --open-pdf
./DataShip.exe --export-report "mujprehled" --output 'C:\Prehledy\mujprehled.pdf'
```

Datum v minulosti je dostupné pouze pro uložený přehled **Odebraná / neodebraná strava**. Ostatní přehledy dovolují dnešek a budoucí dny.

Datum lze zapsat jako `RRRR-MM-DD` nebo `DD.MM.RRRR`. `--days-ahead` znamená 0–370 kalendářních dní dopředu, nikoli posun podle varných dnů. Nelze ho kombinovat s `--date`.

Výchozí cíl je podsložka `exporty` vedle používaného `config.json`. Název obsahuje název přehledu, datum a krátký identifikátor, například `mujprehled_2027-01-15_a1b2c3d4.pdf`. Krátký identifikátor odlišuje přehledy, jejichž názvy by po převodu na název souboru splývaly. Při opakovaném exportu stejného přehledu za stejné datum se úspěšně vytvořené PDF nahradí. Při selhání tvorby zůstává původní soubor zachovaný.

`--output` určuje konkrétní soubor s příponou `.pdf`; relativní cesta se vztahuje ke složce konfigurace. Případné složky se vytvoří. Názvy i cesty s mezerami uzavřete do uvozovek.

## Vlastní konfigurace a shodné názvy

```bash
./DataShip.exe --config 'C:\DataShip\config.json' --export-report "mujprehled"
./DataShip.exe --export-report-id 'id-z-daily-reports-json' --open-pdf
```

Název se porovnává bez rozlišení velikosti písmen. Pokud existuje více shodných názvů, aplikace žádný neodhadne: přehledy přejmenujte, nebo použijte `--export-report-id` s přesným ID ze souboru `daily_reports.json`. Export vždy respektuje aktuálně povolené kategorie administrace.

## Co tento příkaz nepřebírá

Používá obsah uloženého přehledu: kategorie, stravu, členění a vzhled PDF. Nepřebírá čas, příjemce, výstupní složku ani kalendářní pravidla úlohy v Plánovači. Vytváří přehled pro datum určené parametrem nebo pro dnešek a neprovádí automatické přeskakování nevarných dnů.

Potřebujete přístup k databázi a přihlašovací údaje dostupné účtu Windows, který EXE spouští. Pokud systém blokuje aplikace či zápis do cílové složky, samotný přepínač toto oprávnění nenahrazuje.

Výsledek je v Logách aplikace a v textovém logu `logy/automaticky_export.log` vedle EXE (lze změnit pomocí `--log`). Windowed EXE také ukládá standardní diagnostiku do `logy/dataship_web.log`. Návratový kód `0` značí hotové PDF, `2` chybu exportu a `3` hotové PDF, které se nepodařilo otevřít v externím prohlížeči. Chyba neotevírá GUI ani interaktivní přihlašovací dialog.
