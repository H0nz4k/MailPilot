# MailPilot v12.7

Desktop aplikace pro skolni jidelny: denni PDF, e-mailing, mesicni uzaverka, podklad Z 17-01, hromadne zpravy a automaticke ulohy.

## Co aplikace umi

- **Denni stav**: souhrn porci, PDF a odeslani e-mailem
- **Uzaverka**: FKSP, arch, rekapitulace, ZIP a e-mail
- **Special (Z 17-01)**: rocni podklad podle kategorii
- **Hromadna zprava**: rozeslani podle trid/kategorii
- **Prehled**: stav automatickych odeslani, chyby, rucni retry
- **Administrace**: DB, e-maily, PDF, vzhled, bez GUI, pokrocile

## Pristup a role

- **Bezny uzivatel**: Denni stav, Uzaverka, Special, Hromadna zprava, Prehled
- **Administrator**: vsechny administracni sekce (pod heslem)
- Administrace se automaticky uzamyka po **60 s** necinnosti

## Planovac ve v12.7

Planovac je zjednoduseny na 3 jasne akce nad vybranou ulohou:

- `Spustit`
- `Povolit / Zakazat`
- `Odstranit` (s potvrzenim)

Zmeny uloh se zapisi po kliknuti na `Ulozit planovac`.

## Spusteni ve vyvoji

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\spustit_qt.bat
```

nebo:

```powershell
python AutoReport_qt.py --config config.json
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
dist\MailPilot-v12_7-portable.zip
dist\MailPilot\MailPilot.exe
```

## Uzivatelsky navod (PDF)

V repozitari i ve vystupni slozce je vzdy prilozen:

- `UZIVATELSKY_NAVOD_MailPilot.pdf` (stabilni nazev)
- `UZIVATELSKY_NAVOD_MailPilot_v12_7.pdf` (verzovana kopie)

Generovani navodu:

```powershell
.\.venv\Scripts\python.exe tools\generate_user_manual_pdf.py
```

## Struktura projektu

- `gui_qt/` - Qt UI (okna, stranky, widgety, tema, modely)
- `services/` - UI-agnosticka logika
- `tools/` - build a utility skripty
- `assets/` - ikony, vizualni podklady
- `dist/` - hotove buildy

## Poznamka k bezpecnosti

- DB heslo je v Credential Manageru (neni v `config.json`)
- Resend API klic je v `.env`
