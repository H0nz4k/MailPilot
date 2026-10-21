# MailPilot WebGUI – rozpracované úkoly (21. 10. 2026)

## Stav
Vývojová větev `feat/web-mail-scheduler` obsahuje NiceGUI správu nezávislých e-mailových úloh, plánovač, SMTP/Resend, nastavení NSSM a upozornění do HTML dashboardu Jídelny. Původní Qt verzi neměnit.

## Priorita 1: následující varný den – NEDOKONČENO
- Zdroj pravdy je **PostgreSQL `public.varnedny`**, označení varného dne **`A`**.
- **Nefiltrovat automaticky soboty, neděle ani svátky**. Varný den může být kterýkoliv kalendářní den; pracovní den naopak nemusí být varný.
- Ověřit skutečné názvy a typy sloupců tabulky (v dostupném kódu nebyly doloženy), např.:
  ```sql
  SELECT column_name, data_type
  FROM information_schema.columns
  WHERE table_schema = 'public' AND table_name = 'varnedny'
  ORDER BY ordinal_position;
  ```
- V `services/web_mail_worker.py` nyní `dispatch()` pro `next_cooking_day` vyhazuje chybu „Čeká na propojení kalendáře varnedny z JídelnaSQL.“; propojit s existujícím DB připojením MailPilotu (konfigurace přes `stravovaci_sestava.load_config`, heslo ze systémového úložiště).
- `services/web_mail_tasks.py` už má `target_date(..., is_cooking_day=...)`; lze předat DB callback nebo bezpečnou funkci vracející nejbližší datum. Úpravu promítnout také do náhledu data v `services/web_mail_gui.py`.
- Při nedostupné DB/neznámém schématu **neodeslat sestavu pro nesprávné datum**; bezpečně zahlásit chybu.
- Otestovat případ: sobota = A; neděle = A; svátek = A; všední den bez A; žádný další dostupný den.

## Následující práce
- Dokončit sestavu „souhrn počtu jídel“ (`meal_summary`).
- Spolehlivá retry politika neodeslaných úloh; záznam chyb a obnova upozornění.
- Integrační ověření odesílání, WebGUI, NSSM služby a dashboardu na Windows; neposílat testy skutečným klientům bez souhlasu.
- Aktualizovat testy a README; vše commitovat do `feat/web-mail-scheduler`.

## Důležité
Toto je pouze uložené TODO, **nikoli hotová implementace**. Dřívější pokus o nový commit pro varné dny neprošel; existující vývojové commity zůstávají zachovány.
