# MailPilot Web – sestavení a spuštění na Windows (Git Bash)

Tento návod platí pro větev `feat/web-mail-scheduler` a nové **NiceGUI webové rozhraní**. Starý skript `build_windows.bat` sestavuje **Qt 12.8**, nikoliv tuto webovou verzi.

## Předpoklady
- Windows 10/11 x64
- Git for Windows (Git Bash)
- Python **3.12 x64** z python.org včetně `py` launcheru

## 1. Stažení nové verze (Git Bash)

```bash
git clone --branch feat/web-mail-scheduler https://github.com/H0nz4k/MailPilot.git
cd MailPilot
```

Pokud repozitář již máš stažený:

```bash
cd /c/cesta/k/MailPilot
git fetch origin
git switch feat/web-mail-scheduler
git pull --ff-only
```

## 2. Sestavení dvou Windows EXE

```bash
bash scripts/build_web_windows.sh
```

Skript vytvoří izolované `.venv-web`, nainstaluje závislosti, sestaví webové EXE a samostatné EXE pro plánovač. Není třeba spouštět PowerShell. Součástí výstupu je ukázkový `config.json`, pokud dosud žádný nemáš.

Výstupy:
- `dist-web/MailPilot-Web/MailPilot-Web.exe` – NiceGUI v prohlížeči
- `dist-web/MailPilot-Web/MailPilot-Web-Worker.exe` – plánovač pro NSSM
- `dist-web/MailPilot-Web/START_WEB.cmd` – spouštěč dvojklikem
- `dist-web/MailPilot-Web/config.json` – lokální nastavení, doplň skutečnou databázi

**Před opakovaným buildem si ulož existující konfiguraci bokem.** Skript existující `config.json` v sestavené složce nepřepisuje, ale nepřebírá ji automaticky ze staré Qt instalace.

## 3. Otevření webové aplikace

```bash
./dist-web/MailPilot-Web/MailPilot-Web.exe --browser
```

Alternativa: dvojklik na `dist-web\\MailPilot-Web\\START_WEB.cmd`. Otevře se lokální webová aplikace ve výchozím prohlížeči, proces EXE musí zůstat spuštěný.

Po otevření zkontroluj databázové připojení přes TEST a záložky **E-mailové úlohy** a **Nastavení odesílání**. Typ služby pro tabulku `public.varnedny` je standardně **Oběd**.

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
git switch feat/web-mail-scheduler
git pull --ff-only
bash scripts/build_web_windows.sh
```

Poté spusť nové `dist-web/MailPilot-Web/START_WEB.cmd`. Build zachovává `config.json` z tohoto výstupního adresáře, ale při kopírování na jiný počítač přenes také jeho provozní nastavení a znovu zkontroluj přístupové údaje. Worker a NSSM neměň během kontroly vzhledu.

## 4. Windows služba NSSM (až po otestování GUI)
V Nastavení odesílání vyplň cestu k `nssm.exe`. Po kliknutí na **Instalovat** se služba nastaví na samostatný `MailPilot-Web-Worker.exe`, nikoliv na webové GUI. Instalace a spuštění vyžaduje administrátorská práva. Nezapínej službu dřív, než ověříš cílové e-mailové adresy a nastavení odesílání; může odeslat skutečné zprávy.

## Omezení vývojové verze
- Datum `následující varný den` se čte z `public.varnedny` dle roku, měsíce, typu služby a `d01`…`d31`; `A` je varný, `N` nevarný. Víkendy a svátky se nefiltrují.
- Chybějící data znamenají chybu, nikoliv odhad data sestavy.
- `meal_summary` a spolehlivé opakování neúspěšných odeslání ještě nejsou dokončené.
- Testy Windows EXE, skutečné DB, NSSM a odeslání e-mailu je nutné provést na cílovém počítači; build samotný není potvrzením funkčnosti v produkci.
