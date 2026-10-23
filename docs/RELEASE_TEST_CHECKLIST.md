# DataShip 1.0.0-rc.4 – kontrola před vydáním

Automatické testy používají izolované soubory a nahrazené DB/e-mailové transporty. Windows smoke kontrola ověřuje start skutečných sestavených EXE a HTTP odpověď GUI. Úspěšný build nepotvrzuje funkci zákaznické databáze ani účtu Windows služby.

Doplň datum, počítač, verzi z `BUILD_INFO.json` a výsledek každého bodu. Testuj nejprve na kopii nastavení, s jednou vlastní e-mailovou adresou a bez druhého workeru.

| Oblast | Co ověřit u sebe na Windows | Výsledek |
|---|---|---|
| Čisté spuštění | Rozbal celý ZIP mimo zdroje, otevři START_WEB.cmd; GUI se otevře bez instalace Pythonu. | ☐ |
| Databáze | Správný server a jídelna, TEST uspěje; chybné údaje ukážou srozumitelnou chybu. | ☐ |
| Přístup | Běžný uživatel vidí jen povolené nabídky/kategorie; Nastavení vyžaduje heslo a znovu se zamkne. | ☐ |
| Denní počty | Datum 21.10.2026 v referenční DB: oběd 627, snídaně 36, večeře 32, celkem 695; ISŠ celkem 170. Pokud se data od referenčního exportu změnila, porovnej aktuální shodný okamžik. | ☐ |
| Filtry a přehledy | Vytvoř 2 přehledy s odlišnými kategoriemi; přepínání i restart zachová samostatné výběry a typ stravy. Pouhé prohlížení a přepnutí nesmí přepsat uložený přehled; ověř Uložit změny a Uložit jako nový. | ☐ |
| PDF | Správná jídelna, datum, čeština/diakritika, počty kategorií/menu/norem; změny orientace a seznamu strávníků. | ☐ |
| Ruční e-mail | Odešli jeden PDF jen na vlastní adresu; zkontroluj přílohu, datum a předmět; vyzkoušej chybnou adresu i chybu transportu. | ☐ |
| Pravidelné odesílání | Přidání adresy ji označí, duplicita nevznikne, odebrání funguje; uložená úloha zachová správný přehled, čas, datum a aktivitu. Přehledy → Nastavit odesílání přenese přesně vybraný přehled; zrušení nic neodesílá a nevytvoří plán. | ☐ |
| Varné dny | Dnes, zítra, posun, konkrétní datum a další varný den odpovídají skutečnému public.varnedny. Dvě odesílání s různými kalendáři (např. Oběd a Večeře) nezávisle určí datum; výběr se zachová při úpravě, kopírování i restartu. Starší úloha zachová dosavadní kalendář. Chybějící data oznámí chybu. | ☐ |
| Uzávěrka | Zvol měsíc, vytvoř všechny používané výstupy FKSP/arch/rekapitulace, zkontroluj částky a ZIP proti stávajícím ověřeným sestavám. | ☐ |
| Volitelné nabídky | Pokud je klient používá, zapni a ověř Speciál Z 17-01, hromadné zprávy a režimy bez GUI. | ☐ |
| Vzhled | Světlé/tmavé/vlastní barvy, celá rámování, zoom, velikosti a všechny tři volby tučného písma přežijí restart; formuláře a dialogy jsou čitelné při 100 %. | ☐ |
| Služba | Instalace NSSM, správný účet, start/stop/status; plánovaná zpráva přijde jednou, i když je GUI zavřené. | ☐ |
| Restart Windows | Služba automaticky naběhne, má přístup k DB i odesílání, neběží druhá kopie a log neobsahuje chyby. | ☐ |
| Aktualizace | Po výměně programu zůstávají přehledy, příjemci, úlohy a nastavení; lze obnovit zálohu původní složky. | ☐ |

Známé omezení: nepodporovaný starý typ „Souhrn počtu jídel“ se neposílá. Neúspěšná úloha nového webového workeru se v ten den automaticky znovu neopakuje; chybu je nutné zjistit z logu a vyřešit. Nepovažuj testovací RC za potvrzené produkční vydání, dokud neprojde tento seznam.
