# DataShip – sestavení a spuštění na Windows (Git Bash)

Aktuální postup pro verzi 1.0.0-rc.2, distribuční ZIPy s NSSM a GitHub Releases: [RELEASE_WINDOWS.md](RELEASE_WINDOWS.md).

Tento návod platí pro větev `feat/dataship-design-integration` a nové **NiceGUI webové rozhraní**. Starý skript `build_windows.bat` sestavuje **Qt 12.8**, nikoliv tuto webovou verzi.

## Předpoklady
- Windows 10/11 x64
- Git for Windows (Git Bash)
- Python **3.12 x64** z python.org včetně `py` launcheru

## 1. Stažení nové verze (Git Bash)

```bash
git clone --branch feat/dataship-design-integration https://github.com/H0nz4k/MailPilot.git
cd MailPilot
```

Pokud repozitář již máš stažený:

```bash
cd /c/cesta/k/MailPilot
git fetch origin
git switch feat/dataship-design-integration
git pull --ff-only
```

## 2. Sestavení dvou Windows EXE

```bash
bash scripts/build_web_windows.sh
```

Skript vytvoří izolované `.venv-web`, nainstaluje závislosti, sestaví webové EXE a samostatné EXE pro plánovač. Není třeba spouštět PowerShell. Součástí výstupu je ukázkový `config.json`, pokud dosud žádný nemáš.

Výstupy:
- `dist-web/DataShip/DataShip.exe` – NiceGUI v prohlížeči
- `dist-web/DataShip/DataShip-Worker.exe` – plánovač pro NSSM
- `dist-web/DataShip/START_WEB.cmd` – spouštěč dvojklikem
- `dist-web/DataShip/config.json` – lokální nastavení, doplň skutečnou databázi

**Před opakovaným buildem si ulož existující konfiguraci bokem.** Skript existující `config.json` v sestavené složce nepřepisuje, ale nepřebírá ji automaticky ze staré Qt instalace.

## 3. Otevření webové aplikace

```bash
./dist-web/DataShip/DataShip.exe --browser
```

Alternativa: dvojklik na `dist-web\\DataShip\\START_WEB.cmd`. Otevře se lokální webová aplikace ve výchozím prohlížeči, proces EXE musí zůstat spuštěný.

Po otevření zkontroluj databázové připojení přes TEST a záložky **E-mailové úlohy** a **Nastavení odesílání**. Typ služby pro tabulku `public.varnedny` je standardně **Oběd**.

## Rychlé vyzkoušení změn GUI BEZ buildu

Zavři předchozí okno programu. V Git Bash v kořeni repozitáře:

```bash
git pull --ff-only
bash scripts/run_web_dev_windows.sh
```

Spustí se aktuální `stravovaci_nicegui.py` z GitHubem aktualizovaných zdrojů, s Pythonem z `.venv-web` a se stejným `dist-web/DataShip/config.json` jako ve vytvořeném EXE. Skript neinstaluje ani nespouští NSSM službu. Okno Git Bash ponech otevřené, dokud testuješ; ukončíš jej klávesami Ctrl+C. Po změně Python kódu postup zopakuj. Při změně samotných závislostí může být potřeba znovu spustit build.

Až chceš znovu vyrobit samostatné EXE pro zákazníka, spusť:

```bash
bash scripts/build_web_windows.sh
```

Po buildu otevři `dist-web/DataShip/START_WEB.cmd`. Současné sestavené EXE **se aktualizací Gitu samo nezmění**.

## Aktualizace GUI po změnách (21. 10. 2026)

Nové vývojové verze:
- **Denní stav**: pole **Datum exportu** se při každém otevření GUI předvyplní dnešním datem z počítače (nikoli zastaralým datem z `config.json`).
- **Český kalendář**: názvy dnů a měsíců jsou česky, týden začíná pondělím.
- **Horní nabídka**: výchozí položky Denní stav, Uzávěrka, E-mailové úlohy a Administrace; Speciál a Hromadná zpráva jsou skryté.
- **Administrace → Hlavní nabídka**: správce může zaškrtávat Uzávěrku, Speciál, Hromadnou zprávu a E-mailové úlohy, změny se uloží do `config.json`.
- **Administrace → Nastavení odesílání**: původně samostatná záložka je přesunutá do administrace.

Pro získání těchto změn v již sestavené instalaci spusť v Git Bash v kořeni zdrojového repozitáře:

```bash
git fetch origin
git switch feat/dataship-design-integration
git pull --ff-only
bash scripts/build_web_windows.sh
```

Poté spusť nové `dist-web/DataShip/START_WEB.cmd`. Build zachovává `config.json` z tohoto výstupního adresáře, ale při kopírování na jiný počítač přenes také jeho provozní nastavení a znovu zkontroluj přístupové údaje. Worker a NSSM neměň během kontroly vzhledu.

## 4. Windows služba NSSM (až po otestování GUI)
V Nastavení odesílání vyplň cestu k `nssm.exe`. Po kliknutí na **Instalovat** se služba nastaví na samostatný `DataShip-Worker.exe`, nikoliv na webové GUI. Instalace a spuštění vyžaduje administrátorská práva. Nezapínej službu dřív, než ověříš cílové e-mailové adresy a nastavení odesílání; může odeslat skutečné zprávy.

## Omezení vývojové verze
- Datum `následující varný den` se čte z `public.varnedny` dle roku, měsíce, typu služby a `d01`…`d31`; `A` je varný, `N` nevarný. Víkendy a svátky se nefiltrují.
- Chybějící data znamenají chybu, nikoliv odhad data sestavy.
- `meal_summary` a spolehlivé opakování neúspěšných odeslání ještě nejsou dokončené.
- Testy Windows EXE, skutečné DB, NSSM a odeslání e-mailu je nutné provést na cílovém počítači; build samotný není potvrzením funkčnosti v produkci.

