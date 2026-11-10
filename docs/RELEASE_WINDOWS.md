# DataShip {{VERSION}} – Windows

Rozbalte celý ZIP do stálé zapisovatelné složky, například `C:\DataShip`, a spusťte **DataShip.exe**. Otevře se aplikace v prohlížeči bez černého konzolového okna. Samotné EXE bez složky `_internal` nefunguje. VBS ani Windows Script Host nejsou potřeba.

Balíčky pro verzi **{{VERSION}}**, sestavení **{{BUILD}}**:

- `DataShip-{{VERSION}}-Windows-x64.zip` – aplikace, worker a potřebné knihovny.
- `DataShip-{{VERSION}}-Windows-x64-NSSM.zip` – navíc NSSM a instalace plánovací služby.
- `SHA256SUMS.txt` na stránce vydání – kontrolní součty ZIPů.

Distribuce obsahuje čistou ukázkovou konfiguraci. Neobsahuje vaše hesla, příjemce, úlohy ani uložené přehledy. Verze, sestavení a zdrojový commit jsou uvedeny na začátku tohoto README.

### První nastavení

V Administraci se zadává **heslo administrace**. V nastavení databáze patří samostatné **heslo k databázi**. Vyplňte připojení a proveďte TEST; heslo musí být dostupné účtu Windows, pod kterým se exporty spouštějí. Odchozí e-mail nastavte v **Nastavení → Služba a odesílání** podle zvoleného transportu SMTP nebo Resend.

V Přehledech vyberte datum, všechny nebo vybrané typy stravy, kategorie a typy výdeje. V kroku **Obsah a PDF** zvolte součty, jmenný seznam nebo speciální přehled **Odebraná / neodebraná strava**. Ten nabízí obě skupiny, pouze odebranou nebo pouze neodebranou stravu; jako jediný dovoluje historii včetně přehledu za včerejšek.

V **Nastavení PDF** lze zkracovat názvy jídel a držet stejně vysoké datové řádky. Na záložce **Rozložení, náhled a šablony** přesouvejte souhrny, umístěte dva bloky vedle sebe, určete nové stránky a zobrazte skutečné PDF. Náhled používá vybraná data z Jídelny nebo výslovně označená ukázková data. Vzhled lze uložit jako pojmenovanou šablonu; datum a filtry se do ní neukládají.

### Automatické přehledy a služba

Přehled můžete uložit a v průvodci nastavit datum, čas, příjemce nebo pouze export PDF do složky. Uložená úloha si uchová kopii nastavení vzhledu; pozdější změna šablony ji sama nezmění.

Po ručním ověření připojení a výstupu spusťte aplikaci jako správce Windows a v **Nastavení → Služba a odesílání** nainstalujte službu. U NSSM balíčku má cesta končit `nssm\win64\nssm.exe`. Výchozí název služby je **DataShipScheduler** a spouští **DataShip-Worker.exe** ze stejné instalace. Uložením zapnuté úlohy se ověří služba; potíže s oprávněním nebo spuštěním se zobrazí v aplikaci. Běžné otevření aplikace ani ruční export PDF správce nevyžadují.

Worker může pracovat se zavřeným GUI. Počítač musí zůstat zapnutý a neuspaný. Úlohy se kontrolují přibližně každých 30 sekund. Varné dny vyžadují skutečné kalendáře Jídelny SQL. Pro síťové složky musí mít přístup také účet služby.

### Aktualizace a diagnostika

Zastavte plánovací službu a ukončete příslušný `DataShip.exe` ve Správci úloh; zavření záložky prohlížeče webový proces neukončuje. Zálohujte celou instalaci. Zachovejte vlastní `config.json`, `daily_reports.json`, `pdf_templates.json`, `web_mail_settings.json`, `web_mail_tasks.json`, `web_mail_worker_state.json`, `.env`, `planovac.json` a případnou historii adres `recipient_history.json`. Čistým vzorem tyto soubory nepřepisujte. Přihlašovací údaje Windows nejsou přenosnou součástí ZIPu. Po výměně aplikace i workeru znovu spusťte službu.

Po přesunu instalace použijte **Opravit cesty služby**. Nevytvářejte další službu pro tutéž instalaci. Výsledky najdete v sekci **Logy** a v souborech `logy/dataship_web.log`, `logy/web_mail_worker.log` a `logy/automaticky_export.log`.

Jednorázový export uloženého přehledu bez webu, služby a e-mailu popisuje následující část tohoto README.
