# DataShip Web / Worker: Windows build a NSSM služba

Vývojová větev: `feat/web-mail-scheduler`. Původní Qt MailPilot na `master` je samostatná aplikace.

## Rychlé spuštění nejnovějšího zdrojového GUI

V **Git Bash na Windows**, v kořeni klonu projektu:

```bash
git switch feat/web-mail-scheduler
git pull --ff-only
bash scripts/run_web_dev_windows.sh
```

Tento postup spouští jen uživatelské GUI z Python zdrojů a **nespouští automaticky NSSM ani Worker**. Při používání existujícího `config.json` skript preferuje `dist-web/DataShip/config.json`, případně starší `dist-web/MailPilot-Web/config.json`. Pozor na testovací data: neklikej na skutečné odesílání bez ověření příjemců.

## Kompletní Windows EXE

```bash
bash scripts/build_web_windows.sh
```

Výstupy v `dist-web/DataShip/`:

- `DataShip.exe` – webová aplikace a její administrační GUI
- `DataShip-Worker.exe` – samostatný plánovač pro Windows službu
- `START_WEB.cmd` – spustí GUI v prohlížeči
- `START_WORKER_MANUAL.cmd` – **spustí Worker doopravdy**, nepouštěj bez kontroly e-mailových úloh
- `config.json`, `web_mail_settings.json`, `web_mail_tasks.json`, `.env` – lokální provozní nastavení

Build přenáší existující provozní nastavení z předchozího adresáře `dist-web/MailPilot-Web` do `dist-web/DataShip`, pokud nejsou již u DataShip. Starší instalaci automaticky nemaže.

## NSSM – ověření stavu a oprava

1. V DataShip otevři **Administrace → Nastavení odesílání → Windows služba NSSM**.
2. Vyplň celou Windows cestu k `nssm.exe` (například `C:\\Tools\\nssm.exe`) a název služby (obvykle `DataShipScheduler`). Pokud je NSSM v PATH, pole cesty může být prázdné.
3. Klikni nejdřív na **Stav**. Výstup nebo přesná chyba nyní zůstává vypsaná v panelu.
4. **Instalovat / Spustit / Zastavit / Restart** vyžadují spustit samotný program (případně Git Bash při zdrojovém spuštění) **jako správce Windows**. Otevřený prohlížeč sám o sobě administrátorská oprávnění nezajistí.
5. Instalace NSSM pouze registruje službu, **nespouští** ji. `Spustit` může okamžitě odesílat splatné úlohy. Nejdřív zkontroluj recipienty, nastavení Resend/SMTP a e-mailové úlohy.

**Pozor na staré služby**: při přejmenování MailPilot → DataShip mohou v systému zůstat služby s původními jmény nebo cestami. **Neinstaluj dvě instance Workeru pro stejnou databázi/config**. Stará služba se automaticky nepřejmenuje ani nepřepíše. Pro bezpečný přechod nejprve zjisti její jméno, program a stav, teprve pak rozhodni, zda ji zastavit.

### Když hlásí chybu při startu

- V instalační složce hledej `logy/dataship_nssm_stderr.log` – chyby ještě před spuštěním Python loggeru.
- V `logy/web_mail_worker.log` jsou provozní zprávy Workeru, pokud už nastartoval.
- V režimu bez buildu se nyní používá absolutní cesta k `web_mail_worker_main.py` a pracovní složka zdrojového projektu, takže nehrozí původní `ModuleNotFoundError: services` pouze kvůli AppDirectory.
- V zabaleném režimu NSSM spouští `DataShip-Worker.exe` vedle `DataShip.exe`.
- U starší už nainstalované služby **změna Python kódu automaticky nepřepíše nastavení NSSM**. Ověř, na jakou cestu skutečně ukazuje, například kliknutím na Stav a externí diagnostikou.

### Read-only diagnostika ve Windows Git Bash

Pokud máš `nssm.exe` na PATH:

```bash
nssm status DataShipScheduler
nssm get DataShipScheduler Application
nssm get DataShipScheduler AppDirectory
```

Pokud není v PATH, nahraď `nssm` úplnou cestou ke svému `nssm.exe`. Služba může mít jméno jiné než `DataShipScheduler`, zkontroluj pole **Název služby** v administraci. Tyto tři příkazy nic neinstalují, nemažou ani neodesílají.

## Známé provozní podmínky

- Práva a přístup k DB přihlašovacím údajům se mohou lišit mezi přihlášeným uživatelem a účtem Windows služby (typicky LocalSystem). GUI `DB OK` samo o sobě neprokazuje, že Worker má přístup ke credentialům.
- `web_mail_settings.json` a `web_mail_tasks.json` se čtou za běhu ze stejné složky jako `config.json`. Worker kontroluje úlohy v intervalu.
- SMTP heslo musí být dostupné v prostředí **konkrétní služby** pod klíčem `MAILPILOT_SMTP_PASSWORD` (historické interní pojmenování).
- `mail_summary` není zatím plně propojen se sestavou. Odeslání selhané úlohy ani čekání na další retry není zaručeno bez dalšího otestování.
- Úspěšný GitHub Actions Windows build **není** důkazem úspěšného startu NSSM na cílovém stroji.
