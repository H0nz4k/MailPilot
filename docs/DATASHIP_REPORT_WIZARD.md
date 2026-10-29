# Průvodce přehledem a odesíláním

Verze 1.0.0-rc.10, sestavení 20261029.1.

## Ovládání

Po otevření aplikace se zobrazí Přehledy a první krok. Vždy je předvyplněné dnešní datum podle místního času počítače, i když config.json obsahuje staré datum. Datum náhledu lze změnit, pro pravidelné odesílání se ale používá samostatné pravidlo.

1. **Datum a strava:** datum náhledu, všechny nebo více konkrétních typů stravy a požadované kategorie.
2. **Obsah a PDF:** Jen součty / Součty a jmenný seznam, aktuální počty porcí, vytvoření PDF pro kontrolu. Nastavení PDF nabízí rozpad podle kategorií/norem, oddělení kategorií, orientaci, velikost písma a tučná data.
3. **Na který den:** dnes, zítra, pozítří, vlastní počet kalendářních dní nebo následující varný den. Náhled vypíše konkrétní datum i den v týdnu. Zvlášť vysvětluje výsledek vůči dnešku a datum PDF při příštím odeslání. Volitelně lze přeskočit nevarné cílové dny nebo vybrat jiný skutečný kalendář z Jídelny.
4. **E-mail a uložení:** název úlohy, příjemci, denní čas a zapnutí automatického odesílání. Neplatné adresy se neuloží. Tlačítko Uložit do plánovače uloží přehled i úlohu; žádný e-mail samo neodesílá.

Zpět zachovává rozepsaný výběr. Uložené přehledy lze v prvním kroku použít jako výchozí výběr. Pro vytvoření nové plánované úlohy není nutné přehled předem samostatně ukládat.

Po uložení se zobrazí potvrzení, nejbližší plánovaný termín a stav služby. Otevřít plánovač vede na uložené úlohy s možností úprav, pozastavení a zobrazením posledního výsledku. Vytvořit další úlohu začne opět dnešním datem.

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
