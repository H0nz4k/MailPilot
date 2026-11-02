# MailPilot v12.9

Production-readiness release zamereny na spolehlivost scheduleru, retry chovani,
warning integraci do JidelnaSQL a kompatibilitu cenove logiky (`PouzivatCenik=0/1`).

## Hlavni oblasti

- **Denni stav**: PDF + odesilani e-mailem
- **Uzaverka**: mesicni financni vystupy (FKSP, arch, rekapitulace, ZIP)
- **Special (Z 17-01)**: rocni podklad podle kategorii
- **Hromadna zprava**: rozesilani prijemcum podle filtru
- **Prehled**: posledni odeslani, chyby, runtime scheduleru, rucni retry
- **Administrace**: DB, e-maily, planovac, PDF, vzhled, bez GUI, pokrocile

## Novinky v12.9

- Zpřehlednění přístupnosti pokročilých nastavení a hlavních akcí denní sestavy.
- Odolnější čtení stavu plánovače, pokud chybí Windows nástroj sc (například při Linux testech).
- Automatizované Linux testy a Windows sestavení s ověřením verze, dostupné přes GitHub Actions.

## Co bylo nove ve v12.8

- scheduler status je navazany na realny runtime stav (ne jen na JSON plan)
- kontrola credential dostupnosti pro ucet runtime (NSSM / lokalni beh)
- retry automatickeho exportu pri sitovych/transient chybach vcetne HTTP 429
- warning tlacitka v Pokrocile reagují na skutecny stav `dashboard.template.html`
- warning zapis je atomicky + escaped HTML + kompatibilni legacy/new markery
- diagnostika cenoveho rezimu (`Sazby` / `Cenik`) bez nahrazovani DB business logiky
- cache uzaverky invaliduje i pri zmene cenovych tabulek a zmenach cenoveho rezimu

## Role a pristup

- **Bezny uzivatel**: Denni stav, Uzaverka, Special, Hromadna zprava, Prehled
- **Administrator**: vsechny administracni sekce (pod heslem)
- auto-lock administrace po **60 s** necinnosti

## Spusteni ve vyvoji

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\spustit_qt.bat
```

Alternativne:

```powershell
python -m gui_qt.app --config config.json
```

## CLI rezimy (bez GUI)

```text
MailPilot.exe --poctyemailem
MailPilot.exe --automatic
MailPilot.exe --zaverka_072026
MailPilot.exe --zaverka_am
MailPilot.exe --z17_2026
```

## Build (portable EXE)

Spust:

```text
build_windows.bat
```

Vysledkem je:

```text
dist\MailPilot-v12.9-portable.zip
dist\MailPilot\MailPilot.exe
```

## Requirements split

- `requirements.txt` - produkcni runtime MailPilotu (Qt + backend)
- `requirements-legacy.txt` - legacy NiceGUI/pywebview reference stack
- `requirements-dev.txt` - komplet pro testy a legacy reference moduly
- `requirements-build.txt` - build nastroje (PyInstaller + PyMuPDF)

## Uzivatelsky navod

- `UZIVATELSKY_NAVOD_MailPilot.pdf` (stabilni nazev)
- `UZIVATELSKY_NAVOD_MailPilot_v12_8.pdf` (verzovana kopie)

Generovani:

```powershell
.\.venv\Scripts\python.exe tools\generate_user_manual_pdf.py
```

## Poznamky k bezpecnosti

- DB hesla nejsou v `config.json` (Credential Manager + machine-scope fallback)
- API klice nejsou logovany ani ukladany v plaintextu do configu
