# DataShip 2 — prototyp Odběrů

Oddělený experiment vycházející z DataShip 1.4.0. Odběry lze zobrazit pomocí ukázkových dat nebo po zadání cesty ke konfiguraci DataShip 1.4 načíst ze skutečné Jídelny. Ukázkový režim používá testovací náhradu databázového kurzoru; připojený režim využívá původní výpočty a generátor PDF. Připojení používá systémově uložené heslo. Při přímém připojení k 1.4 se úlohy ukládají do jejího úložiště a může je zpracovat běžící plánovač 1.4. Alternativou je import do samostatného prostoru verze 2.

Záměr: prověřit nový vzhled, samostatné okno Tauri, propojení s Pythonem a velikost celé aplikace včetně výpočetního EXE. Verze 1.4 zůstává samostatná. Čtyřkrokový průvodce po připojení ukládá profily a úlohy kompatibilní s plánovačem 1.4. Nové úlohy jsou ve výchozím stavu pozastavené. Zachování všech možností a ověření služby na skutečném počítači zůstává další prací. Obrázek `concept.png` je generovaný návrh, vlastní UI je implementované v Reactu a upravené podle požadavku na střídmost.

## Spuštění při vývoji

V Git Bash z tohoto adresáře: `npm ci` a `npm run dev`. Prohlížeč ukazuje samostatnou ukázku bez tvorby PDF; desktopové sestavení používá Python engine přes Tauri příkaz. Pro sestavení je potřeba Rust/MSVC, Node, WebView2 a Python prostředí s PyInstallerem a závislostmi projektu.

PDF se vytváří v dočasné složce systému s jedinečným názvem. Výstup ze skutečných dat je nutné před provozním použitím ověřit na konkrétní databázi. Omezení: vlastní nastavení ještě není dokončené a služba plánovače verze 2 nebyla ověřena na cílovém počítači; datum a filtry jsou omezené na 366 dní. WebView2 je systémová závislost a není zahrnutá do měření složky.


## Vyzkoušení hotového prototypu

Rozbalte ZIP do vlastní složky a spusťte `DataShip-2-Prototyp.exe`. Soubor `dataship-v2-engine.exe` musí zůstat vedle něj. Aplikace potřebuje Microsoft Edge WebView2 Runtime. Vytvořené PDF je nejprve v dočasné složce; poté ho lze uložit na zvolenou cestu. Pro ukázkový režim není potřeba nastavení ani databáze. Pro skutečná data je třeba zadat cestu ke konfiguraci a mít uložené heslo k databázi. Skutečné PDF se zatím vytváří v dočasné složce, jejíž cestu aplikace zobrazí.

## Ověření desktopového PDF

Sestavený prototyp lze spustit s argumentem `--self-test-pdf`. Izolovaný autotest aktivuje stejné tlačítko PDF ve WebView, použije smyšlená data a zapíše výsledek do dočasné složky systému; nepoužívá databázi ani e-mail.

Při přímém použití konfigurace 1.4 neupravujte úlohy současně v DataShip 1.4 a 2: jejich sdílené soubory zatím nemají společné zamykání a souběžné změny by se mohly přepsat. Ověření na skutečné Jídelně a se službou zatím chybí.

Příkaz „Převést do DataShip 2“ vytvoří oddělený uživatelský prostor, zachová původní soubory a převede úlohy jako pozastavené. Při tomto převodu se služba neinstaluje ani nespouští. Opakovaný import existující prostor nepřepíše. Pro samostatné plánování lze nainstalovat službu DataShip2Scheduler (vyžaduje práva správce a dostupné NSSM); instalace ji nespustí. Skutečná instalace a běh služby zatím nebyly ověřeny na cílovém počítači.

Odběry lze po připojení jednorázově vytvořit a odeslat podle existujícího nastavení SMTP/Resend; plánovaná úloha se tím nevytváří. Vytvořené PDF lze zkopírovat na uvedenou úplnou cestu, pokud cílový soubor dosud neexistuje. Skutečné odesílání nebylo ověřeno.

Nastavení v samostatném prostoru vyžaduje heslo administrace DataShipu. Pokud zatím neexistuje, lze jej při prvním vstupu vytvořit. Klíč Resend se při importu nekopíruje; lze jej zadat v Nastavení. Heslo SMTP se používá z prostředí služby. Připojení k databázi se před uložením ověřuje; heslo se ukládá do systémového úložiště, které může používat i verze 1.4.

Pro novou instalaci bez verze 1.4 zvolte „Vytvořit nové nastavení“. Aplikace ověří databázové připojení a uloží hesla do systémového úložiště; úlohy ani službu automaticky nespustí. Tato cesta byla zatím ověřena pouze s náhradami databáze a trezoru.

Průvodce umožňuje po vytvoření PDF procházet jeho stránky přímo v aplikaci. Pro sestavení enginu s tímto náhledem nainstalujte závislosti projektu včetně `pypdfium2` a spusťte z adresáře `backend` příkaz `python -m PyInstaller --noconfirm engine.spec`.
