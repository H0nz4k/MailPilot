# DataShip – stažení, sestavení a vydání pro Windows

První testovací verze: **1.0.0-rc.1**. Původní Qt MailPilot zůstává ve verzi 12.8.

## Hotové soubory

Otevři https://github.com/H0nz4k/MailPilot/releases (pro soukromý repozitář musíš být přihlášený).

- `DataShip-1.0.0-rc.1-Windows-x64.zip`: celá aplikace včetně `DataShip.exe`, složky `_internal` a `DataShip-Worker.exe`.
- `DataShip-1.0.0-rc.1-Windows-x64-NSSM.zip`: totéž plus 64bitový NSSM a skript pro instalaci služby.
- `SHA256SUMS.txt`: kontrolní součty obou ZIPů.

Rozbal celý ZIP do stálé zapisovatelné složky, například `C:\DataShip`. Samotný `DataShip.exe` bez `_internal` nefunguje. Spusť `START_WEB.cmd`, nastav databázi a ověř funkce podle `KONTROLA_FUNKCI.md`. Nový balíček neobsahuje tvoje hesla, příjemce, uložené přehledy ani naplánovaná odesílání. `BUILD_INFO.json` zaznamenává verzi a zdrojový commit.

Při aktualizaci nejprve zastav GUI a existující službu. Zálohuj celou původní instalaci. Zachovej své `config.json`, `daily_reports.json`, `web_mail_settings.json`, `web_mail_tasks.json`, `web_mail_worker_state.json`, `.env` a `planovac.json`; čistým ukázkovým `config.json` je nepřepiš. Přihlašovací údaje uložené ve Windows nejsou přenosnou součástí ZIPu. Při testu používej jednu instalaci a jeden worker, aby se zprávy neposílaly dvakrát.

## Build u tebe v Git Bash

Zavři spuštěnou aplikaci. V kořeni repozitáře:

```bash
git fetch origin &&
git switch feat/dataship-design-integration &&
git pull --ff-only &&
bash scripts/test_windows.sh &&
bash scripts/build_web_windows.sh &&
./.venv-web/Scripts/python.exe scripts/smoke_windows_build.py &&
./.venv-web/Scripts/python.exe scripts/package_web_release.py
```

Potřebuješ Windows 10/11 x64, Git Bash a Python 3.12 x64 včetně launcheru `py`. Testy DataShipu a společných výpočtů mají vlastní `.venv-test`, build používá `.venv-web`. Sada zahrnuje všechna webová a backendová testovací témata; dva moduly widgetových testů původního Qt GUI 12.8 do vydání DataShipu nepatří. Testy a smoke kontrola neposílají skutečné e-maily. Smoke kontrola spustí obě vytvořená EXE s oddělenou dočasnou konfigurací a bez úloh.

Výstup buildu je `dist-web/DataShip/`, distribuční ZIPy jsou v `release-dist/1.0.0-rc.1/`. Při opakovaném balení stejné verze použij nový prázdný výstupní adresář pomocí `--output`; existující balíčky se samy nepřepisují.

## Co je Release a jak ho vytvořit

Commit ukládá změny zdrojů. Tag označuje konkrétní verzi zdrojů. Release je stránka k danému tagu s popisem a soubory ke stažení. EXE a velké ZIPy patří mezi přílohy Release, ne mezi soubory zdrojového repozitáře.

Workflow **Build DataShip Web (Windows)** ve stránce Actions při změnách větve `feat/dataship-design-integration` spustí testy, sestaví EXE, ověří jejich start a vytvoří oba ZIPy. Úspěšný běh uloží soubory jako artefakt na 30 dní. U první verze vytvoří také koncept Release `dataship-v1.0.0-rc.1`, navázaný na přesný sestavený commit. Již existující Release stejné verze nepřepíše.

Koncept není vydaná verze. Po úspěšném průchodu kontrolním seznamem otevři **Releases → koncept DataShip 1.0.0-rc.1 → Edit**. Zkontroluj přílohy a ponech zaškrtnuté **Set as a pre-release**. Tlačítkem **Publish release** zveřejníš testovací vydání. U soukromého repozitáře ho uvidí jen lidé s přístupem. Automatické položky „Source code“ jsou jen zdroje; uživatelé aplikace stahují náš ZIP v Assets.

Pokud chceš nahrát vlastní lokální build, otevři **Releases → Draft a new release**, vytvoř tag `dataship-v1.0.0-rc.1` na skutečném sestaveném commitu, vlož obsah `docs/releases/1.0.0-rc.1.md` a přetáhni oba ZIPy i `SHA256SUMS.txt` z `release-dist`. Ulož nejprve jako koncept. Pokud už koncept automaticky vznikl, uprav ten existující; nevytvářej druhé vydání stejné verze.

Pro další verzi změň `VERSION` i `WEB_VERSION` v `services/web_branding.py` a přidej příslušné poznámky v `docs/releases/`. Test kontroluje shodu čísel. Nová verze dostane nový tag a nové přílohy; vydanou verzi zpětně nepřepisuj.

## NSSM až po ručním ověření

Použij ZIP s NSSM a stálou cestu. V **Nastavení → Nastavení odesílání** se přibalená cesta nabídne u nové instalace automaticky. Tlačítka pro službu vyžadují práva správce.

Alternativně otevři Git Bash **jako správce** v rozbalené složce:

```bash
bash INSTALOVAT_SLUZBU.sh
```

Skript nainstaluje `DataShipScheduler` pro `DataShip-Worker.exe`. Existující službu nepřepíše a worker nespustí. V `nssm edit DataShipScheduler` nastav účet služby, který má přístup k databázi a potřebným přihlašovacím údajům. Po dokončení kontrol:

```bash
./nssm/nssm.exe start DataShipScheduler
./nssm/nssm.exe status DataShipScheduler
```

Zastavení:

```bash
./nssm/nssm.exe stop DataShipScheduler
```

Po restartu Windows ověř stav a jediný běžící worker. Provozní log je `logy/web_mail_worker.log`. Přibalený NSSM 2.24-101 pochází z https://nssm.cc/download, je public domain a při balení se kontroluje jeho SHA-256. Zdroj a kontrolní součet jsou v `nssm/SOURCE.txt`.
