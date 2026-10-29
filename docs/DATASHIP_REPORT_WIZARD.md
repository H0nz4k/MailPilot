# Průvodce přehledem a odesíláním

Verze 1.0.0-rc.10, sestavení 20261029.9.

## Dvě oddělená hesla

Vstupní dialog **Administrace** žádá **Heslo administrace** a kontroluje pouze administrační heslo aplikace. Databáze má samostatné pole **Heslo k databázi** uvnitř **Nastavení → Databáze** (nebo v následném průvodci připojením). Zadání hesla do jednoho pole nepřepíše druhé heslo a přihlášení do administrace samo netestuje databázové spojení.

V systémovém trezoru jsou údaje oddělené: heslo administrace má vlastní účet; databázové heslo používá účet určený hostitelem, portem, databází a databázovým uživatelem. Aktualizace stávající hesla nemění. Hesla se neukládají do config.json.

Závěrečná kontrola sestavení 20261029.8: 119 cílených testů prošlo pro první spuštění, oddělení hesel a jejich úložišť, administraci, plánovač a vlastní termíny úloh, kalendáře, export PDF bez e-mailu, e-mailové nastavení, NSSM operace a vlastní témata. Prošla kompilace Pythonu, kontrola syntaxe Bash a čísel sestavení obou zdrojových CLI. Skutečné Windows EXE/NSSM, zákaznická DB a živé odesílání z tohoto prostředí ověřené nejsou.

## Ověření skutečně spuštěné verze

Ikony Windows jsou od sestavení 20261029.4, režim exportu PDF a velká tlačítka dní od 20261029.6. Pokud hlavička ukazuje 20261029.3, stále běží staré EXE. Aktualizace zdrojů sama běžící proces ani službu nevymění. Před sestavením zastavte službu a zavřete aplikaci včetně starých záložek. Po sestavení spusťte EXE z `dist-web/DataShip` a zkontrolujte sestavení v hlavičce.

Od 20261029.7 vypisují obě EXE přes `--version` také číslo sestavení. Build oba programy zkontroluje a při nesouladu skončí chybou. V Git Bash lze ověřit:

```bash
./dist-web/DataShip/DataShip.exe --version
./dist-web/DataShip/DataShip-Worker.exe --version
```

Při chybě `WinError 5` na `DataShip-Worker.exe` soubor může držet spuštěná služba nebo ručně spuštěný worker. NSSM je při instalaci nastavené na restart workeru po ukončení s prodlevou 10 sekund; samotné ukončování procesů tedy službu nezastaví. Dva procesy stejného názvu mohou být spouštěcí a pracovní proces jednoho PyInstaller onefile workeru. Zastavte skutečnou službu DataShipu (výchozí název `DataShipScheduler`; starší `MailPilot_denniprehled` může být jiná služba), zavřete GUI a teprve potom sestavujte.

Build nyní kontroluje přístup k instalovanému GUI, workeru a NSSM před instalací závislostí a znovu před nasazením. Při zamčeném souboru skončí s návodem; procesy automaticky neukončuje. PyInstaller sestavuje do jedinečné pracovní složky `dist-web/.dataship-build-*`, nikdy nemaže používanou instalaci. Až po ověření obou EXE a přidání NSSM se přenesou nastavení, úlohy a uživatelské soubory. Původní složka zůstane jako `dist-web/DataShip.backup-*`; při selhání přesunu nového buildu se obnoví. Při neúplné instalaci po starém neúspěšném buildu se chybějící nastavení načte z `build/dataship-preserved` (pokud tam původní skript stihl vytvořit zálohu). Tuto zálohu nemažte před úspěšným obnovením. Při prvním sestavení se nadále podporuje import nastavení z `dist-web/MailPilot-Web`.

Heartbeat nového workeru obsahuje jeho sestavení. GUI upozorní na starý nebo neznámý worker místo běžného potvrzení čekání. Technický log workeru uvádí sestavení, PID, cestu konfigurace a u každé splatné úlohy její ID, název, plánovaný čas a čas kontroly.

Každá úloha má vlastní čas. Worker termíny standardně kontroluje po 30 sekundách a úlohy zpracovává postupně. Po pozdním spuštění dohání již splatné úlohy; při delším exportu může být další úloha opožděná. Nejde o záruku odeslání na přesnou sekundu. Změna sestavení tento dosavadní režim dohánění sama nemění.

## Co znamená chyba kalendáře

Více typů stravy, například Oběd a Večeře, není duplicita. Duplicitní kalendář znamená více řádků pro stejný rok, měsíc a stejný typ služby. Starší společná hláška „Chybí nebo je duplicitní…“ mohla znamenat i úplnou absenci dat pro další měsíc. Nově se chybějící kalendář, prázdný typ služby a skutečné duplicity vypisují odděleně; duplicita uvádí typ a počet záznamů.

Pokud při hledání následujícího varného dne dojde aplikace do listopadu a listopadový kalendář chybí, datum se neodhaduje a úloha e-mail neodešle. Je nutné doplnit varné dny daného měsíce v Jídelně nebo vybrat existující správný kalendář.

## Pouze exportovat a uložit PDF

Ve čtvrtém kroku lze zaškrtnout **Pouze exportovat a uložit PDF**. Příjemci i jednorázové odeslání zmizí. Zobrazí se úplná cesta cílové složky, tlačítko Procházet a název souboru. Čas se změní na **Každý den vytvořit v**. Úlohu lze zapnout nebo pozastavit stejně jako e-mailovou úlohu.

Například složka `C:\DataShip\Exporty` a název `Prehled_{date}.pdf` vytvoří pro přehled za 30. 10. 2026 soubor `C:\DataShip\Exporty\Prehled_2026-10-30.pdf`. Použije se cílový den ze třetího kroku a skutečné varné dny Jídelny. Datum v názvu je datum přehledu, nikoli datum spuštění. Proměnná `{date}` je volitelná; pokud se znovu vytvoří stejný název, soubor se nahradí. Pro různé úlohy zvolte odlišné složky nebo názvy.

Worker pouze vytvoří PDF, uloží je do vybrané složky a zapíše výsledek do historie. Nečte nastavení e-mailu ani API klíč, nepoužije SMTP/Resend a PDF neotevírá. Složku případně vytvoří. Nejprve vznikne dočasné PDF ve stejné složce a teprve po úspěšném dokončení nahradí cílový soubor; při chybě zůstává předchozí PDF zachované. Účet Windows služby musí mít ke složce právo zápisu, u síťových cest i přístup k danému sdílení.

Úloha se ukládá s volitelnými položkami `output_mode`, `output_directory` a `output_filename`. Starší úlohy bez nich nadále posílají e-mail. Nový režim je podporovaný i při úpravě a kopírování úloh. **Aktualizujte GUI i DataShip-Worker.exe na sestavení 20261029.6 a službu restartujte.** Starší worker režim exportu neumí.

## Čitelnější ovládání

Počet dní se zadává číslem nebo velkými tlačítky − a + o velikosti 48 px; drobné systémové šipky jsou odstraněné. Šipky rozbalovacích voleb mají 44px plochu. Stejné ovládání používá průvodce i editor uložených úloh. Kalendáře mají srozumitelnější názvy a vysvětlení, že určují varné dny, nikoli obsah PDF.

Rozhraní používá jednu rodinu písma Segoe UI (s běžným systémovým fallbackem) a tři role: běžný text, nadpis a pomocný popis. Síla písma je běžná nebo polotučná, včetně nastavení tučnosti. Ikony si ponechávají vlastní ikonové písmo. Písmo a vzhled exportovaných PDF tím nejsou změněné.

## Zjednodušený plánovač

Stránka **Plánovač** obsahuje rovnou seznam plánovaných přehledů a jejich stav. Záložky **E-maily funkcí** a **Původní plánovač** byly odstraněny z nového rozhraní. Nové úlohy vznikají průvodcem v Přehledech, každá má vlastní příjemce a čas. Společný odesílatel, API klíč, způsob odesílání a šablony e-mailu jsou pouze v **Nastavení → Služba a odesílání**.

Volitelné **Jednorázové odeslání** je nově ve čtvrtém kroku průvodce a používá zde uvedené příjemce i společné nastavení Resend/SMTP. Odešle aktuální PDF pro datum náhledu z prvního kroku; pravidlo cílového dne a čas se uplatní až při plánovaném odesílání. Odeslání vyžaduje výslovné potvrzení a nevytváří plánovanou úlohu.

Staré údaje příjemců v `config.json` a soubor `planovac.json` se nemažou ani nemigrují. Původní příkazy pro automatický export a uzávěrku zůstávají kompatibilní; odstranění záložek samo nevypíná případné externí spouštění starých plánů. Export PDF už nepotřebuje pole ani API klíč ze starého e-mailového editoru.

## Ikony Windows aplikací

`DataShip.exe` má ikonu lodičky podle motivu záložky v prohlížeči. `DataShip-Worker.exe` používá stejnou lodičku doplněnou ozubeným kolečkem vpravo nahoře. Windows build vkládá každému EXE jeho vlastní soubor ICO; všechny velikosti od 16 do 256 pixelů jsou součástí ikon. Po aktualizaci zdrojů je nutné EXE znovu sestavit pomocí `bash scripts/build_web_windows.sh`.

Zdrojem ikon je `tools/generate_dataship_icons.py` (pro přegenerování vyžaduje Pillow). Soubory `assets/dataship.ico` a `assets/dataship-worker.ico` jsou uložené v repozitáři, takže běžný build ikony nekreslí ani nestahuje. Původní ikona staré Qt aplikace se nemění.

Přihlašovací dialog uvádí „Zadejte heslo pro administraci.“ Jde o heslo nastavení aplikace; přihlašovací údaje databáze se zadávají zvlášť v nastavení databáze.

## Odstranění Windows služby

V **Nastavení → Služba a odesílání → Windows služba NSSM** je tlačítko **Odstranit službu**. Dialog zobrazí název služby a vyžádá potvrzení. Aplikace nejprve ověří, že jde o worker DataShipu, běžící službu zastaví a po ověření zastavení odstraní její registraci z Windows pomocí NSSM. Pokud zastavení selže, služba se neodstraní. Uložené přehledy, úlohy, API klíč i konfigurace zůstávají zachované; automatické odesílání touto službou se ukončí. Službu lze později znovu nainstalovat. Odstranění vyžaduje oprávnění správce Windows a odemknuté nastavení aplikace.

## Nastavení Resend API

V **Nastavení → Služba a odesílání → Odchozí e-mail** vyberte **Resend API**, vložte klíč do pole **Resend API klíč** a klikněte na **Uložit API klíč** (nebo stiskněte Enter). Zobrazí se potvrzení uložení a pole se vyprázdní. Existující klíč se při otevření stránky nevypisuje, zobrazí se pouze stav. Prázdné pole uložený klíč nemaže.

Klíč se zapisuje do stávajícího souboru `.env` vedle aplikace, nikoli do JSON nastavení. Stejný klíč používá GUI i worker. Ostatní volby odchozího e-mailu se dál ukládají automaticky; API klíč má samostatné potvrzení uložení. Uložení neodesílá zprávu ani nespouští službu. Nastavení klíče vyžaduje odemknutou administraci aplikace, nikoli oprávnění správce Windows.

## Ovládání

Po otevření aplikace se zobrazí Přehledy a první krok. Vždy je předvyplněné dnešní datum podle místního času počítače, i když config.json obsahuje staré datum. Datum náhledu lze změnit, pro pravidelné odesílání se ale používá samostatné pravidlo.

1. **Datum a strava:** datum náhledu, všechny nebo více konkrétních typů stravy a požadované kategorie.
2. **Obsah a PDF:** Jen součty / Součty a jmenný seznam, aktuální počty porcí, vytvoření PDF pro kontrolu. Nastavení PDF nabízí rozpad podle kategorií/norem, oddělení kategorií, orientaci, velikost písma a tučná data.
3. **Na který den:** dnes, zítra, pozítří, vlastní počet kalendářních dní nebo následující varný den. Náhled vypíše konkrétní datum i den v týdnu. Zvlášť vysvětluje výsledek vůči dnešku a datum PDF při příštím odeslání. Volitelně lze přeskočit nevarné cílové dny nebo vybrat jiný skutečný kalendář z Jídelny.
4. **E-mail a uložení:** název úlohy, příjemci, denní čas a zapnutí automatického odesílání. Neplatné adresy se neuloží. Tlačítko Uložit do plánovače uloží přehled i úlohu; žádný e-mail samo neodesílá.

Zpět zachovává rozepsaný výběr. Uložené přehledy lze v prvním kroku použít jako výchozí výběr. Pro vytvoření nové plánované úlohy není nutné přehled předem samostatně ukládat.

Po uložení se zobrazí potvrzení, nejbližší plánovaný termín a stav služby. Otevřít plánovač vede na uložené úlohy s možností úprav, pozastavení a zobrazením posledního výsledku. Vytvořit další úlohu začne opět dnešním datem.

## Vzhled a čitelnost

Vizuální úprava vychází z pravidel UI/UX Pro Max: stálé pořadí kroků, číslované indikátory s výrazným aktivním krokem, kontrastní ovládání a viditelné zaměření klávesnicí. Pracovní plocha má omezenou šířku, větší karty a klidné pozadí. Volba součtů nebo jmenného seznamu je zobrazena jako dvě velké přepínací karty. Průběžný popis připomíná datum, stravu, počet kategorií a vybraný obsah.

Hlavní barevná akce je Pokračovat / Uložit do plánovače. Vytvoření zkušebního PDF je vedlejší akce; jednorázový e-mail je ve volitelném rozbalení. Malé obrazovky skládají volby a tlačítka pod sebe. Všechny barvy používají dosavadní proměnné vzhledu, takže funguje světlý, tmavý i vlastní motiv. Nezavádí se nové závislosti ani externí fonty.

## Význam stavu

Uložená/zapnutá úloha sama nepotvrzuje běžící službu. Aktualizovaný worker zapisuje heartbeat každých 15 sekund, i když právě vytváří PDF nebo odesílá e-mail. GUI stav kontroluje každých 10 sekund:

- Plánovač běží · čeká na další spuštění.
- Právě zpracovává přehled — pro konkrétní právě zpracovávanou úlohu.
- Pozastaveno — automatické odesílání úlohy je vypnuté.
- Plánovač je zastaven — služba ukončila běh.
- Běh plánovače není potvrzen — heartbeat neexistuje, je nečitelný nebo je starší než 90 sekund. Takto se zobrazí i starší worker, který heartbeat nepodporuje.

Výsledky Odesláno / Přeskočeno / Chyba zůstávají v dosavadní aktivitě. Při delším otevření seznamu použijte Obnovit pro poslední výsledky a další termíny; živý stav běhu se aktualizuje sám.

## Ukládání a kompatibilita

Nová úloha dostane vlastní kopii konfigurace přehledu, aby jiné úlohy používající původní přehled nebyly nechtěně změněny. Kopie obsahuje kategorie, typy stravy, seznam/součty, orientaci, obě velikosti písma, tučnost, jazyk a číslo jídelníčku. Výstup workeru tedy používá uložený vzhled, nikoli později změněný globální vzhled.

Staré přehledy bez nových PDF položek nadále dědí globální vzhled. Formát daily_reports.json zůstává version 1; nové položky jsou volitelné. Existující úlohy a jejich kalendáře se nemigrují ani nemažou. Editace existujících úloh v Plánovači používá kompatibilní editor; nová hlavní cesta vede průvodcem.

Nové úlohy mají first_send_date: při uložení po dnešním nastaveném čase se poprvé spustí až zítra. Tím se předchází okamžitému odeslání kvůli původnímu dohánění zmeškaných termínů. Staré úlohy bez first_send_date si zachovávají původní chování. Varný den se vždy řeší podle public.varnedny, nikoli podle víkendů či odhadovaného názvu stravy. Při nedostupném kalendáři ukáže náhled chybu, žádné náhradní datum si nevymýšlí; worker takovou úlohu také neodešle jako jiný den.

Nejprve se atomicky zapíše kopie přehledu, potom atomicky úloha. Pokud druhý zápis selže, úloha se nezapne; může zůstat nepřiřazená kopie přehledu. Opakované uložení stejného rozepsaného průvodce použije stejná ID. Znovukliknutí po úspěšném uložení nevytvoří duplicitu.

## Aktualizace a ověření

Je nutné aktualizovat GUI i DataShip-Worker.exe ze stejné verze a restartovat worker. Starší worker nezná first_send_date, uložený vzhled ani heartbeat. Pro změnu není třeba upravovat databázi Jídelny.

Ověření v Linuxu: průchod reálnou NiceGUI stránkou, dnešní výchozí datum, součty bez jmen, více typů stravy, vlastní uložený vzhled, konkrétní datum dalšího varného dne z nahrazeného kalendáře, validace příjemců, ochrana před duplicitou a okamžitým odesláním po uložení, čerstvý/zastaralý heartbeat a regresní testy filtrů, oprávnění a workeru s nahrazeným transportem.

Skutečná zákaznická DB, živé e-maily, Windows EXE a NSSM nebyly v tomto prostředí ověřeny. Grafická kontrola v Chromiu se nepodařila: stažení prohlížeče vrátilo neplatný archiv. Funkční testy používají skutečné NiceGUI komponenty a simulaci uživatelských akcí.



### Viditelný stav Resend API klíče (20261029.9)

Klíč zůstává v `RESEND_API_KEY` souboru `.env` vedle EXE; pole slouží k zadání nového klíče a po úspěšném uložení se vyprázdní. Nastavení zobrazuje přesnou cestu k souboru. Trvalý zelený rámeček s fajfkou a textem „API klíč je uložený a načtený.“ se objeví po načtení existujícího klíče i po uložení s ověřením zpětného načtení stejné hodnoty. Oranžový stav označí chybějící nebo rozepsaný neuložený klíč, červený chybu čtení, zápisu či ověření. Prázdné uložení uložený klíč nemění a znovu načte jeho stav. Zelená potvrzuje místní uložení a načtení; platnost klíče u poskytovatele se zde online neověřuje.
