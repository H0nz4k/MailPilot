# MailPilot WebGUI – rozpracované úkoly (21. 10. 2026)

## Stav
Vývojová větev `feat/web-mail-scheduler` obsahuje NiceGUI správu nezávislých e-mailových úloh, plánovač, SMTP/Resend, nastavení NSSM a upozornění do HTML dashboardu Jídelny. Původní Qt verzi neměnit.

## Priorita 1: následující varný den – IMPLEMENTOVÁNO (čeká integrační ověření na Windows)
- Potvrzené schema: `public.varnedny` má `rok` (smallint), `mesic` (smallint), `typsluzby` (varchar), `d01` až `d31` (varchar), `updated_dt` (timestamptz).
- `A` znamená vaří, `N` nevaří; soboty, neděle ani svátky se nijak automaticky nevyřazují.
- `services/web_mail_cooking_days.py` čte výhradně DB a používá existující připojení `stravovaci_sestava.load_config` (heslo ze systémového úložiště). Výběr podle roku, měsíce a typu služby; měsíční cache.
- Nastavení typu služby v `web_mail_settings.json` přes WebGUI (výchozí `Oběd`). Worker i náhled termínu ve WebGUI používají společné `resolve_task_date`.
- Pokud chybí měsíc/typ, existuje duplicitní záznam nebo stav není `A/N`, výpočet končí chybou; datum se neodhaduje a PDF se neodešle.
- `test_web_mail_cooking_days.py`: 21 scénářů, z toho 14 syntetických a 7 podle skutečně poskytnutých ukázkových řádků pro Oběd (09/2010 a 10/2010). Pokrývají sobotu/neděli se stavem `A`, svátek, všední den `N`, přechod mezi měsíci, chybějící/duplicitní řádky, neplatné hodnoty a typ služby.
- **Aktuální lokální ověření ukázkových dat: 7/7 úspěšných** s mockovaným PostgreSQL a stejnou implementací výběru kalendáře. Nových 7 testů je zapsáno i v GitHub testovacím souboru. Celou 21-testovou sadu zatím znovu neověřeno v projektovém prostředí; nutno ještě provést test proti živé DB, celé aplikaci a NSSM na Windows. Žádné skutečné e-maily nebyly odeslány.

## Následující práce
- Dokončit sestavu „souhrn počtu jídel“ (`meal_summary`).
- Spolehlivá retry politika neodeslaných úloh; záznam chyb a obnova upozornění.
- Integrační ověření odesílání, WebGUI, NSSM služby a dashboardu na Windows; neposílat testy skutečným klientům bez souhlasu.
- Aktualizovat testy a README; vše commitovat do `feat/web-mail-scheduler`.

## Důležité
Toto je pouze uložené TODO, **nikoli hotová implementace**. Dřívější pokus o nový commit pro varné dny neprošel; existující vývojové commity zůstávají zachovány.
