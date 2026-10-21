# DataShip – denní stav, kategorie, typ stravy a stručná PDF sestava

Stav: implementováno na vývojové větvi `feat/web-mail-scheduler` (NiceGUI DataShip).
Původní Qt MailPilot na větvi `master` nebyl měněn.

## Kategorie

- **Výchozí: všechny aktuální kategorie z `public.kategor`.** I když historický `config.json` obsahuje omezený seznam `povolene_kategorie`, tento seznam **automaticky neomezuje** export.
- Správce může v **Administrace → Povolené kategorie** zvolit **Jen vybrané kategorie**. Změna je aktivní teprve po tlačítku **Uložit nastavení kategorií**.
- Zápis `poctyemailem.vsechny_kategorie=true` znamená všechny; `false` znamená použití `poctyemailem.povolene_kategorie` (minimálně jedna kategorie). Chybějící volba = všechny.
- **Běžný uživatel** v **Denní stav → Kategorie → Změnit výběr** zvolí podmnožinu kategorií povolených správcem; přednastavené jsou **všechny povolené**. Volba ovlivňuje jen aktuální ruční PDF či ruční e-mail, ne uložený administrátorský whitelist ani Worker.
- Automatické denní sestavy používají uložený seznam **povolených kategorií**. Ruční sestavy používají uživatelův aktuální výběr.
- Pro stejný den lze vyrobit více samostatných PDF: vybrat 2 kategorie, **Vytvořit PDF**, vybrat jiné 4, znovu **Vytvořit PDF**. **Odlišné výběry se nepřepíší**: pouze ruční filtrované sestavy dostanou deterministický suffix `_kat-2-...` / `_kat-4-...`. Výchozí soubor při výběru všech povolených zůstává kompatibilní; automatické úlohy používají původní cestu.
- Vytvoření PDF nepřepíná výběr kategorií automaticky. Uživatel jej může změnit mezi jednotlivými exporty kdykoli přes **Změnit výběr**.
- Při výchozím režimu se kategorie načítají v okamžiku sestavy z DB, takže nově přidaná kategorie nepřestane být započítávána.

## Typ stravy

- **Denní stav** po úspěšném TESTu DB načte skutečné typy služby evidované v aktuálním roce v tabulkách `prihlas`, `varnedny` a `jidelnicek` (nikoliv jen objednávky pro jeden den).
- Filtr **Typ stravy** se zobrazuje vždy, také pokud existuje jen jeden typ. Obsahuje s výchozí volbou **Všechny typy stravy** a jednotlivými typy (např. Oběd, Snídaně, Večeře).
- Filtr se současně uplatní na souhrn menu, kategorie, rozpad norem, jmenný seznam a kontrolu varných dnů v ručním odeslání.
- Volba v GUI je **pro konkrétní ruční export**, ne pro bezobslužné úlohy Workeru. Při novém otevření zůstává výchozí **Všechny**.

## PDF → Pokročilé nastavení PDF → Seznam strávníků

- **true** (výchozí, kompatibilní se starším configem): PDF obsahuje základní tabulky a **Seznam strávníků** od nové stránky.
- **false**: PDF obsahuje **souhrn objednané stravy**, bez jmenného seznamu, bez dalších stránek vyhrazených pro jména. Při tomto režimu se ani neprovádí `DINER_LIST_QUERY` (nenačítají se jména z DB).
- Zbývající přepínače souhrnných tabulek (**Souhrn dle kategorií**, **Souhrn dle norem**) fungují nezávisle.
- Názvy oddílů a PDF metadat neobsahují staré označení „Jmenný seznam strávníků“.

## Důležité testy

- Na konkrétním dni porovnat menu/typy stravy s tiskovou sestavou JídelnaSQL (včetně Integrované školy).
- Ověřit `seznam_stravniku=false`: součet porcí zůstává stejný, v PDF nejsou osobní jména ani záložka pro jmenný seznam.
- Ověřit `seznam_stravniku=true`: původní seznam zůstává viditelný.
- Ověřit po přepnutí typu stravy, že se změní všechny souhrnné počty a jmenné řádky konzistentně.
- Ověřit automatické odesílání s `mail_jen_varne_dny=true` pro nové ALL režimy (přítomnost `A` v `public.varnedny`).
- Rozhodující rozdíl počtů **nelze potvrdit bez přímého dotazu nad uživatelskou DB**; shoda přesně 102 porcím jedné kategorie je silná indicie, nikoli již ověřená příčina.

## Vyzkoušení ve Windows Git Bash

```bash
git switch feat/web-mail-scheduler
git pull
bash scripts/run_web_dev_windows.sh
```

Poté: Administrace → TEST připojení → Povolené kategorie; v Denním stavu datum / Kategorie → Změnit výběr / Typ stravy / Pokročilé nastavení PDF. Pro zabalený EXE spusťte `bash scripts/build_web_windows.sh`.

**Pozor:** Tlačítko „Vytvořit a odeslat“ opravdu rozesílá e-maily – před testováním odešlete jen na bezpečnou testovací adresu, případně použijte „Vytvořit PDF“.
