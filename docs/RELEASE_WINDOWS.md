# DataShip – Windows build a vydání

Aktuální verze: **1.2.0**, sestavení **20261103.1**. Původní Qt MailPilot zůstává samostatnou aplikací.

## Stažení a spuštění

Soubory patří do [GitHub Releases](https://github.com/H0nz4k/MailPilot/releases), nikoli mezi zdrojové soubory repozitáře:

- `DataShip-1.2.0-Windows-x64.zip` – celé GUI, worker a potřebné knihovny.
- `DataShip-1.2.0-Windows-x64-NSSM.zip` – navíc NSSM pro službu Windows.
- `SHA256SUMS.txt` – kontrolní součty ZIPů.

Rozbalte celý ZIP do stálé zapisovatelné složky, například `C:\DataShip`, a spusťte přímo **DataShip.exe**. Otevře web v prohlížeči bez černého konzolového okna. VBS ani Windows Script Host nejsou potřeba. Samotné EXE bez složky `_internal` nefunguje.

Distribuce neobsahuje uživatelská hesla, API klíč, příjemce, úlohy ani uložené přehledy. `BUILD_INFO.json` zaznamenává verzi, sestavení a zdrojový commit.

## Sestavení v Git Bash

Potřebujete Windows 10/11 x64, Git Bash a Python 3.12 x64 včetně launcheru `py`. Před buildem zastavte službu a ukončete GUI. Z kořene repozitáře:

```bash
(
  set -e
  bash scripts/build_web_windows.sh
  ./.venv-web/Scripts/python.exe scripts/package_web_release.py
)
```

EXE jsou v `dist-web/DataShip/`, ZIPy v `release-dist/1.2.0/`. Build ověřuje oba programy: windowed GUI pomocí výstupu `--version-file`, konzolový worker přes `--version`. Sestavuje do pracovní složky a původní instalaci ponechá v záloze `DataShip.backup-*`.

Existující balíčky se nepřepisují. Při opakovaném balení použijte například `--output release-dist/1.2.0-build20261103.1`.

Doplňková kontrola skutečných EXE s oddělenou dočasnou konfigurací a bez e-mailových úloh:

```bash
./.venv-web/Scripts/python.exe scripts/smoke_windows_build.py
```

Volba `--service` navíc ověřuje dočasnou NSSM službu a vyžaduje Git Bash jako správce. Obyčejné otevření GUI ani export PDF práva správce nevyžadují.

## GitHub Releases

Vydání `dataship-v1.2.0` obsahuje ZIP s NSSM a kontrolní součty. Před aktualizací postupujte podle části Aktualizace a diagnostika níže.

## První nastavení a služba

V Administraci se zadává **heslo administrace**. V nastavení databáze pak samostatné **heslo k databázi**; musí být uložené pro účet Windows, který exporty provádí. Resend API klíč patří do `.env` vedle EXE, pole po uložení zůstává prázdné a jeho načtení potvrzuje zelený stav.

Po ručním ověření databáze, PDF a e-mailu spusťte GUI jako správce Windows a v **Nastavení → Služba a odesílání** nainstalujte NSSM službu. Cesta musí končit `nssm\win64\nssm.exe`. Výchozí služba je **DataShipScheduler** a používá **DataShip-Worker.exe** ze stejné instalace.

Uložení nebo zapnutí aktivní úlohy ověří službu a případně se ji pokusí spustit. Chybějící práva, služba nebo chybná cesta se ohlásí viditelným upozorněním; uložená úloha se neztratí. Běžící služba a skutečný heartbeat workeru se zobrazují odděleně. Službu lze také spustit a ověřit přímo v nastavení.

Worker může pracovat se zavřeným GUI, ale počítač musí zůstat zapnutý a neuspaný. Úlohy se kontrolují přibližně každých 30 sekund a zpracovávají postupně; po pozdním startu se mohou dohnat splatné úlohy. Varné dny vyžadují skutečné vyplněné kalendáře Jídelny SQL.

## Jednorázový export bez GUI

```bash
./DataShip.exe --export-report "mujprehled" --open-pdf
```

Příkaz lze dát do cíle zástupce na ploše. Použije uložený obsah a dnešní datum, vytvoří PDF, případně je otevře. Web, e-mail ani službu nespouští. Podporuje vlastní datum, počet dní dopředu, cestu PDF a jednoznačné ID přehledu. Podrobnosti jsou v přibaleném `EXPORT_PREHLEDU.md` nebo [návodu v repozitáři](CLI_EXPORT_PREHLEDU.md).

## Aktualizace a diagnostika

Před výměnou souborů zastavte službu a ukončete příslušný `DataShip.exe` ve Správci úloh; zavření záložky webový proces na pozadí neukončuje. Zálohujte celou instalaci. Zachovejte vlastní `config.json`, `daily_reports.json`, `web_mail_settings.json`, `web_mail_tasks.json`, `web_mail_worker_state.json`, `.env` a `planovac.json`. Nepřepište je čistým vzorem. Přihlašovací údaje Windows nejsou přenosnou součástí ZIPu. Po aktualizaci GUI i workeru znovu spusťte službu.

Po přesunu zastavené instalace použijte **Opravit cesty služby**. Nevytvářejte další kopii služby pro stejnou instalaci. Pro síťové složky musí mít účet služby příslušný přístup; výchozí LocalSystem nemusí mít vaše uživatelská oprávnění.

Logy: `logy/dataship_web.log` pro GUI bez konzole, `logy/web_mail_worker.log` pro plánovač a `logy/automaticky_export.log` pro export přes parametr. Výsledky jsou také v sekci Logy aplikace.

NSSM se bere z oficiálního serveru a kontroluje pevným SHA-256. Při výpadku lze použít ověřenou kopii z předchozího vydání přes přihlášené GitHub CLI; zdroj je zaznamenaný v `nssm/SOURCE.txt`.
