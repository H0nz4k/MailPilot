# MailPilot v12.8 - Uzivatelsky navod

Tento navod popisuje bezny provoz MailPilotu v12.8 se zamerenim na spolehlivost
automatickeho provozu, scheduler a warning integraci do JidelnaSQL.

## 1) Co aplikace umi

- denni PDF prehled porci + odeslani e-mailem
- mesicni uzaverka (vsechny vystupy jako v predchozich verzich)
- rocni podklad Z 17-01
- hromadne zpravy
- planovac automatickych uloh
- prehled stavu automailu a warningu

## 2) Prava a role

### Bezny uzivatel

Pouziva stranky:

- Denni stav
- Uzaverka
- Special
- Hromadna zprava
- Prehled

### Administrator

Ma navic sekce:

- Databaze
- E-maily
- Planovac
- PDF
- Vzhled
- Bez GUI
- Pokrocile

Administrace je chranena heslem a po 60 sekundach necinnosti se sama uzamkne.

## 3) Prvni nastaveni

1. Otevrete `Administrace` v horni liste a prihlaste se.
2. V `Databaze` vyplnte pripojeni a spustte `Test pripojeni`.
3. V `E-maily` nastavte odesilatele, prijemce a API klic.
4. V `Planovac` vytvorte ulohu pro automaticky denni stav.
5. V `Pokrocile` overte cestu k `dashboard.template.html`.

## 4) Denni provoz

### Denni stav

1. Zvolte datum.
2. Vyberte kategorie.
3. Kliknete `Vytvorit PDF` nebo `Vytvorit PDF a odeslat`.

### Uzaverka

1. Vyberte mesic a rok.
2. Zkontrolujte vystupni cestu.
3. Spustte generovani.

### Special (Z 17-01)

1. Vyberte rok a kategorie.
2. Spustte export.

## 5) Planovac ve v12.8

Planovac ma tri hlavni akce nad vybranou ulohou:

- `Spustit ulohu`
- `Povolit / Zakazat ulohu`
- `Odstranit ulohu` (s potvrzenim)

Tlacitka se aktivuji az po vyberu radku v seznamu.

Ve scheduler casti je novy stav runtime:

- zda runtime bezi,
- typ runtime (NSSM / internal / not running),
- posledni beh,
- vysledek posledniho behu,
- dalsi planovany beh,
- posledni chyba.

Pokud scheduler nema dostupne DB credentials pro aktualni ucet runtime, uvidite
to primo ve stavu runtime i v Prehledu.

## 6) Retry pri vypadku internetu

Automaticky export ve v12.8 neukonci beh po prvnim vypadku internetu. Kazdy
pokus je samostatny:

- pokus 1 -> chyba -> cekani
- pokus 2 -> chyba -> cekani
- pokus 3 ...

Retry se pouziva pro transient chyby (sit, timeout, DNS, HTTP 429, HTTP 5xx).
Pri HTTP 429 je respektovan `Retry-After`, pokud je uveden.

## 7) JidelnaSQL warning (STAV SYSTEMU)

Warning pravidla:

1. Chyba automatickeho exportu -> warning se vlozi.
2. Uspesny automaticky export -> warning se odstrani.
3. Stav warningu se cte ze skutecneho `dashboard.template.html`.

Rucni test je v `Administrace -> Pokrocile`:

- `Test: Show warning`
- `Test: Show sample error...`
- `Test: Clear warning`

Vizualni stav tlacitek:

- bez warningu: Show normalni, Clear deaktivovane
- s warningem: Show cervene (aktivni), Clear zelene (aktivni)

MailPilot rozumi novym i legacy markerum a nevytvari duplikat warning bloku.

## 8) Cenova kompatibilita

MailPilot v12.8 podporuje oba rezimy:

- `PouzivatCenik=0` (Sazby)
- `PouzivatCenik=1` (Cenik)

Detekce rezimu je pouze diagnosticka. Vypocty zustavaji na puvodnich DB business
funkcich JidelnaSQL, bez vlastni paralelni matematicke logiky v aplikaci.

## 9) Napoveda a diagnostika

- tlacitko `Napoveda` v levem menu (F1)
- `Test pripojeni` v databazi vypise i cenovy rezim
- `Prehled` ukazuje stav automailu a runtime

## 10) Co se uklada

MailPilot si pamatuje:

- velikost a pozici okna
- stav maximalizace
- vzhled (motiv, zoom, pismo)
- administracni a pokrocila nastaveni

## 11) Incident postup

### E-mail se automaticky neodeslal

1. Otevrete `Prehled` a zkontrolujte posledni chybu.
2. Overte internet a API klic.
3. V `Pokrocile` overte warning v dashboardu.
4. Provedte rucni opakovani.

### DB nepripojena

1. Kliknete na cerveny DB stav v horni liste.
2. Prihlaste se do administrace.
3. Opravte nastaveni DB a spustte `Test pripojeni`.

---

Tento dokument je provozni navod pro MailPilot v12.8.
