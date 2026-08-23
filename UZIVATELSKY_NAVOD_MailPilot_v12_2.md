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

### Krok 1: Vstup do administrace
1. Kliknete na `Soubor -> Vstup do administrace` nebo na polozku `Administrace`.
2. Pri prvnim otevreni nastavte heslo administratora.
3. Po dokonceni zustane administrace odemcena.

### Krok 2: Databaze
1. Otevrete `Administrace -> Databaze`.
2. Vyplnte Server, Port, Databazi, Uzivatele a Heslo.
3. Kliknete na `Test pripojeni`.
4. Overte, ze se v horni liste zobrazi `Pripojeno`.

### Krok 3: E-maily
1. Otevrete `Administrace -> E-maily`.
2. Vyplnte odesilatele.
3. Ulozte Resend API klic.
4. Pro kazdou funkci nastavte prijemce a text.

### Krok 4: Planovac
1. Otevrete `Administrace -> Planovac`.
2. Pridejte ulohu pro denni automaticky export.
3. Nastavte cas spousteni a parametry.

### Krok 5: Vzhled
1. Otevrete `Administrace -> Vzhled`.
2. Nastavte motiv, velikost UI a pismo.

### Krok 6: Pokrocile
1. Otevrete `Administrace -> Pokrocile`.
2. Zkontrolujte mapovani kategorii pro Z 17-01.
3. Nastavte cestu k `dashboard.template.html`.

## 4) Bezna denni prace

### Varianta A: Vytvorit jen PDF
1. Otevrete `Denni stav`.
2. Zvolte datum a kategorie.
3. Kliknete `Vytvorit PDF`.

### Varianta B: Vytvorit PDF a odeslat
1. Otevrete `Denni stav`.
2. Zvolte datum a kategorie.
3. Kliknete `Vytvorit PDF a odeslat`.
4. Pri chybe zkontrolujte `Prehled`.

## 5) Mesicni uzaverka
1. Otevrete `Uzaverka`.
2. Nastavte mesic a rok.
3. Zkontrolujte vystupni cestu.
4. Spustte generovani.

## 6) Rocni vykaz Z 17-01
1. Otevrete `Special`.
2. Nastavte rok vykazu a kategorie.
3. Vytvorte PDF vykaz.

## 7) Hromadna zprava
1. Otevrete `Hromadna zprava`.
2. Nactete prijemce a zvolte filtr.
3. Vyplnte predmet a text.
4. Odeslete zpravu.

## 8) Prehled automailu

V sekci `Prehled` uvidite:
- datum posledniho uspesneho odeslani
- datum/cas dalsiho behu
- nazev aktivni ulohy
- posledni chyby
- tlacitko pro rucni opakovani

## 9) JidelnaSQL warning - pravidla a testovani

### Automaticke pravidlo
1. Warning se zobrazi pri chybe automatickeho exportu/mailu.
2. Pri stavu SKIP (napr. ne-varny den) se warning nezobrazi.
3. Po uspesnem automatickem odeslani se warning odstrani.

### Rucni test
V `Administrace -> Pokrocile`:
- `Test: Show warning`
- `Test: Show sample error...`
- `Test: Clear warning`

Po aktivaci warningu se tlacitka vizualne prepnou:
- Show tlacitka zcervenaji
- Clear tlacitko zezeleni

## 10) Vzhled a citelnost

V `Administrace -> Vzhled` nastavite:
- motiv (Svetly/Tmavy/Systemovy)
- velikost UI 90-160 %
- pismo (normalni, tucne nadpisy, tucne texty, oboje)
- vlastni barevne schema

Zkratky:
- `Ctrl +` zvetsi rozhrani
- `Ctrl -` zmensi rozhrani
- `Ctrl 0` vrati 100 %

## 11) Co se uklada mezi spusteni

MailPilot si pamatuje:
- velikost okna
- pozici okna
- maximalizovany stav
- vybrany motiv a zvetseni

## 12) Incident postupy

### Nepodarilo se odeslat e-mail
1. Otevrete `Prehled` a prectete chybu.
2. Zkontrolujte API klic a prijemce v `Administrace -> E-maily`.
3. Po oprave provedte rucni opakovani.

### Nefunguje spojeni na DB
1. Otevrete `Administrace -> Databaze`.
2. Zkontrolujte host/port/uzivatele/heslo.
3. Spustte znovu `Test pripojeni`.

### Warning v JidelnaSQL nereaguje
1. Overte cestu k `dashboard.template.html`.
2. Spustte `Test: Show warning`.
3. Pro reset spustte `Test: Clear warning`.

## 13) Napoveda v aplikaci

- `Napoveda -> Navod a nastaveni` (F1)
- `Napoveda -> O aplikaci`

Tento dokument je hlavni provozni manual pro MailPilot v12.2.
