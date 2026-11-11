# DataShip 2 — prototyp Odběrů

Oddělený experiment vycházející z DataShip 1.4.0. Odběry lze zobrazit pomocí ukázkových dat nebo po zadání cesty ke konfiguraci DataShip 1.4 načíst ze skutečné Jídelny. Počítačový výpočet používá existující `fetch_collection_period` a generátor PDF, s testovací náhradou databázového kurzoru. Připojení používá existující systémově uložené heslo a konfiguraci pouze čte; při uložení úlohy zapisuje profily a úlohy do úložiště 1.4; sama nespouští plánovač ani neposílá e-maily. Již běžící plánovač 1.4 však může zapnutou úlohu zpracovat.

Záměr: prověřit nový vzhled, samostatné okno Tauri, propojení s Pythonem a velikost celé aplikace včetně výpočetního EXE. Verze 1.4 zůstává samostatná. Čtyřkrokový průvodce po připojení ukládá profily a úlohy kompatibilní s plánovačem 1.4. Nové úlohy jsou ve výchozím stavu pozastavené. Zachování všech možností a ověření služby na skutečném počítači zůstává další prací. Obrázek `concept.png` je generovaný návrh, vlastní UI je implementované v Reactu a upravené podle požadavku na střídmost.

## Spuštění při vývoji

V Git Bash z tohoto adresáře: `npm ci` a `npm run dev`. Prohlížeč ukazuje samostatnou ukázku bez tvorby PDF; desktopové sestavení používá Python engine přes Tauri příkaz. Pro sestavení je potřeba Rust/MSVC, Node, WebView2 a Python prostředí s PyInstallerem a závislostmi projektu.

PDF se vytváří v dočasné složce systému s jedinečným názvem. Výstup ze skutečných dat je nutné před provozním použitím ověřit na konkrétní databázi. Omezení: vlastní nastavení a služba plánovače verze 2 zatím nejsou připojené; datum a filtry jsou omezené na 366 dní. WebView2 je systémová závislost a není zahrnutá do měření složky.


## Vyzkoušení hotového prototypu

Rozbalte ZIP do vlastní složky a spusťte `DataShip-2-Prototyp.exe`. Soubor `dataship-v2-engine.exe` musí zůstat vedle něj. Aplikace potřebuje Microsoft Edge WebView2 Runtime. Vytvořené PDF se uloží do dočasné složky uvedené v aplikaci. Pro ukázkový režim není potřeba nastavení ani databáze. Pro skutečná data je třeba zadat cestu ke konfiguraci 1.4 a mít uložené heslo k databázi. Skutečné PDF se zatím vytváří v dočasné složce, jejíž cestu aplikace zobrazí.

## Ověření desktopového PDF

Sestavený prototyp lze spustit s argumentem `--self-test-pdf`. Izolovaný autotest aktivuje stejné tlačítko PDF ve WebView, použije smyšlená data a zapíše výsledek do dočasné složky systému; nepoužívá databázi ani e-mail.

Úlohy neupravujte současně v DataShip 1.4 a 2: jejich sdílené soubory zatím nemají společné zamykání a souběžné změny by se mohly přepsat. Ověření na skutečné Jídelně a se službou zatím chybí.
