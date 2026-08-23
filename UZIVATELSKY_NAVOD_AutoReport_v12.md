# MailPilot v12.2 - Uzivatelsky navod

Toto je plnohodnotny provozni navod pro kazdodenni praci v MailPilot v12.2.
Navod je psany krokove tak, aby podle nej sel aplikaci nastavit i obsluhovat
novy uzivatel bez predchozi zkusenosti.

## 1) Co aplikace resi

MailPilot slouzi k:

- vytvareni denniho PDF prehledu porci
- odesilani denniho prehledu e-mailem
- mesicni uzaverce
- vykazu Z 17-01
- hromadnemu rozesilani zprav
- sledovani stavu automatickeho odesilani

## 2) Rezimy pristupu

### Bezny uzivatel

Bezny uzivatel standardne pracuje v sekcich:

- Denni stav
- Uzaverka
- Special
- Hromadna zprava
- Prehled

### Administrator

Administrator ma navic pristup do sekce Administrace:

- Databaze
- E-maily
- Planovac
- PDF
- Vzhled
- Bez GUI
- Pokrocile

Vstup do administrace je chraneny heslem.

## 3) Prvni spusteni - kompletni nastaveni krok za krokem

Tento postup doporucujeme udelat pri prvnim nasazeni aplikace na stanici.

### Krok 1: Vstup do administrace

1. Kliknete na `Soubor -> Vstup do administrace` nebo na polozku `Administrace`.
2. Pri prvnim otevreni nastavte heslo administratora.
3. Heslo potvrďte.
4. Po dokonceni zustane administrace odemcena.

### Krok 2: Databaze

1. Otevrete `Administrace -> Databaze`.
2. Vyplnte:
   - Server
   - Port
   - Databaze
   - Uzivatel
   - Heslo
3. Kliknete na `Test pripojeni`.
4. Overte, ze se v horni liste zobrazi `Pripojeno`.

Pokud test neprojde:

- zkontrolujte host/port
- zkontrolujte uzivatele a heslo
- overte dostupnost DB serveru ze stanice

### Krok 3: E-maily

1. Otevrete `Administrace -> E-maily`.
2. Vyplnte odesilatele.
3. Ulozte Resend API klic.
4. Pro kazdou funkci vyberte:
   - seznam prijemcu
   - text zpravy
   - pripadne omezeni na varne dny

Poznamka: API klic se uklada mimo config do systemoveho uloziste.

### Krok 4: Planovac automatickych uloh

1. Otevrete `Administrace -> Planovac`.
2. Pridejte ulohu pro denni automaticky export.
3. Nastavte cas spousteni a parametry.
4. Ulozte.

### Krok 5: Vzhled aplikace

1. Otevrete `Administrace -> Vzhled`.
2. Nastavte motiv, velikost UI, pismo a pripadne vlastni barvy.
3. Overte citelnost na konkretni obrazovce.

### Krok 6: Pokrocile

1. Otevrete `Administrace -> Pokrocile`.
2. Zkontrolujte mapovani kategorii pro Z 17-01.
3. Pro JidelnaSQL warning nastavte cestu k `dashboard.template.html`.
4. Volitelne overte warning testovacimi tlacitky.

## 4) Bezna denni prace (operacni postup)

### Varianta A: Vytvorit jen PDF

1. Otevrete `Denni stav`.
2. Zvolte datum.
3. Zkontrolujte kategorie.
4. Kliknete `Vytvorit PDF`.
5. Overte, ze se PDF otevre a ulozi do cilove slozky.

### Varianta B: Vytvorit PDF a rovnou odeslat

1. Otevrete `Denni stav`.
2. Zvolte datum a kategorie.
3. Kliknete `Vytvorit PDF a odeslat`.
4. Zkontrolujte vysledek ve statusu.
5. Pri chybe otevrete `Prehled` a zkontrolujte posledni chybu.

## 5) Mesicni uzaverka - doporuceny postup

1. Otevrete `Uzaverka`.
2. Nastavte mesic a rok.
3. Zkontrolujte vyber sestav a priloh.
4. Zkontrolujte vystupni cestu.
5. Spustte generovani.
6. Otevrete vystupni slozku a overte:
   - PDF sestavy
   - pripadne ZIP
   - navazne e-mailove odeslani (pokud je zapnute)

## 6) Rocni vykaz Z 17-01 - doporuceny postup

1. Otevrete `Special`.
2. Nastavte rok vykazu.
3. Zkontrolujte kategorie.
4. Pokud je potreba, vratte se do `Pokrocile` a upravte mapovani radku.
5. Vytvorte PDF vykaz.
6. Vizualne zkontrolujte hlavicku, hodnoty i ulozeni.

## 7) Hromadna zprava - doporuceny postup

1. Otevrete `Hromadna zprava`.
2. Nactete prijemce.
3. Zvolte filtr prijemcu.
4. Zkontrolujte pocet a nahled.
5. Vyplnte predmet a text.
6. Odeslete.

Pred odeslanim doporucujeme:

- overit, ze nezustali zahrnuti nechteni prijemci
- overit predmet (jasny, kratky, vecny)

## 8) Prehled - jak cist stav automailu

V sekci `Prehled` uvidite:

- datum posledniho uspesneho odeslani
- datum a cas dalsiho planovaneho behu
- zdroj planu (nazev aktivni ulohy)
- posledni chyby
- tlacitko pro rucni opakovani odeslani

### Kdy pouzit rucni odeslani

Pouzijte, kdyz:

- automat selhal kvuli docasne chybe
- opravil se API klic / konektivita
- potrebujete okamzite dodelat odeslani bez cekani na dalsi plan

## 9) JidelnaSQL warning - pravidla a testovani

### Automaticke pravidlo

Warning v dashboardu se:

1. zobrazi pri chybe automatickeho exportu/mailu
2. nezobrazi pri stavu SKIP (napr. ne-varny den)
3. odstrani po uspesnem automatickem odeslani

### Rucni test v aplikaci

V `Administrace -> Pokrocile`:

- `Test: Show warning` vlozi standardni warning
- `Test: Show sample error...` vlozi warning s vlastnim textem chyby
- `Test: Clear warning` warning odstrani

Warning se zapisuje mezi znacky:

- `AUTOREPORT_AUTOMAIL_BEGIN`
- `AUTOREPORT_AUTOMAIL_END`

## 10) Vzhled a citelnost

V `Administrace -> Vzhled` nastavite:

- motiv (Svetly/Tmavy/Systemovy)
- velikost UI 90-160 %
- rezim tucneho pisma:
  - bez tucneho
  - tucne nadpisy
  - tucne texty
  - tucne nadpisy i texty
- vlastni barevne schema

Klavesove zkratky:

- `Ctrl +` zvetsi rozhrani
- `Ctrl -` zmensi rozhrani
- `Ctrl 0` vrati 100 %

## 11) Co se uklada mezi spusteni

Aplikace si pamatuje:

- velikost okna
- pozici okna
- maximalizovany stav
- vybrany motiv a zvetseni
- dalsi ulozena nastaveni

## 12) Incident postupy (co delat kdyz...)

### A) Nepodarilo se odeslat e-mail

1. Otevrete `Prehled` a prectete chybu.
2. Otevrete `Administrace -> E-maily`:
   - overte API klic
   - overte odesilatele
   - overte prijemce
3. Po oprave provedte rucni opakovani.

### B) Nefunguje spojeni na DB

1. Otevrete `Administrace -> Databaze`.
2. Zkontrolujte server, port, DB, uzivatele.
3. Znovu ulozte heslo.
4. Spustte `Test pripojeni`.

### C) Neodpovida JidelnaSQL warning

1. Otevrete `Administrace -> Pokrocile`.
2. Overte cestu k `dashboard.template.html`.
3. Spustte `Test: Show warning`.
4. Pokud warning zustava, spustte `Test: Clear warning` a opakujte.

## 13) Doporuceny provozni rezim

Na bezne smene doporucujeme:

1. Rano zkontrolovat `Prehled` (stav automailu).
2. Pred obedem pripravit denni PDF.
3. Pri mesicni uzaverce postupovat podle kapitol 5 a 6.
4. Po vetsich zmenach v nastaveni administraci zamknout.

## 14) Napoveda v aplikaci

- `Napoveda -> Navod a nastaveni` (F1)
- `Napoveda -> O aplikaci`

Tento dokument je urcen jako hlavni provozni manual pro MailPilot v12.2.
