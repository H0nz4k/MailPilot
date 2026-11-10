# Odebraná / neodebraná strava

V Přehledech v kroku **Obsah a PDF** vyberte **Speciální: Odebraná / neodebraná strava**.
Jsou dostupné tři varianty: **Odebraná i neodebraná**, **Pouze odebraná**, **Pouze neodebraná**.
Platí datum náhledu, všechny nebo vybrané typy stravy, kategorie a typy výdeje z prvního kroku.
Filtry lze kombinovat. Prázdný výběr typů stravy/výdeje znamená všechny; alespoň jedna
povolená kategorie musí být vybrána.

PDF uvádí evidenční číslo, jméno, třídu, kategorii, typ stravy, menu a stav odběru.
Jeden řádek odpovídá jedné objednávce. Více objednávek stejného člověka se neslévá.
V záhlaví je datum a počet objednávek; dále počty odebrané a neodebrané stravy.
Prázdný výsledek je výslovně označen. Volba oddělení kategorií a nastavení písma/orientace platí i zde.

## Datum a plánování

Pouze tato sestava dovoluje datum v minulosti. Ručně lze vybrat konkrétní historický den.
V průvodci plánováním jsou navíc volby **Včera** a **Jiný počet dní zpět** (1–370 dní).
Například denní spuštění v 08:00 s volbou Včera vždy vytvoří PDF za předchozí kalendářní den.
V editoru uložené úlohy znamená posun −1 včerejšek; záporný posun je dostupný pouze
pro přehled odběrů. Historický pevný den je povolen též pouze pro tuto sestavu.
Kalendář varných dnů se případně kontroluje pro den PDF, nikoli pro den odeslání.

Režim sestavy se ukládá do profilu (`collection_status`) a používá při plánovaném
odesílání, exportu PDF i exportu uloženého přehledu přes CLI. Původní úlohy bez
profilu nepřebírají speciální režim z ručního exportu. Ruční varianty dostávají
odlišné názvy souborů podle režimu a filtrů, aby si nepřepsaly výstupy.

## Zdroj dat

Výchozím souborem jsou individuální objednávky `public.prihlas`, pro které je v denním
sloupci `d01`–`d31` menu 1–9. Neobjednaná nebo odhlášená strava není neodebraná strava.
Kategorie je převzata z přihlášky, při prázdné hodnotě z karty strávníka.

V `public.odebral` se páruje **strávník + rok + měsíc + typ stravy + pořadí přihlášky**.
Znak `O` na pozici příslušného dne v poli `odebral` znamená odebráno. Jiný znak,
krátký řetězec, NULL nebo chybějící záznam znamená neodebráno. SQL používá EXISTS,
takže duplicitní záznam o odběru neznásobí objednávku.
Toto odpovídá logice `H0nz4k/Jcode/src/Qneodebr.pas` a konstantě `ZnakOdebral`
v `src/Pomoc.pas` (ověřeno nad větví main, commit `3a73fcb`).

Typ výdeje se určuje stejně jako v denních sestavách z platných sazeb pro kategorii,
typ stravy a **cílové datum**. Nejednoznačné sazby jsou chybou.
Hromadné přihlášky `prihlasn` nemají jednotlivý osobní stav odběru a do tohoto seznamu
se nezahrnují. Historie je dostupná v rozsahu dat ponechaných v databázi; tato změna
neobnovuje smazané či externě archivované přihlášky. Databáze se pouze čte, bez migrace.

## Ověření

- Prošlo 182 cílených testů a 14 podtestů sestav/PDF, průvodce, profilů, exportu CLI a plánovače; součástí je
  ověření historie pouze pro tento režim a zachování filtrů při uložení.
- SQL provedeno na izolovaném PostgreSQL enginu PGlite: 13 kontrol pro O/chybějící
  záznam/NULL/krátký řetězec, dvojí objednávku, duplicitní odběr, typ stravy,
  kategorii, den/měsíc/rok a přestupný den. Nejde o zákaznickou databázi.
- PDF vizuálně ověřeno na výšku; oba směry ověřeny testy textu a generování.
  Dlouhá sestava zachovala 80 objednávek na šesti stránkách při písmu 12 bodů.
- Interakce formuláře ověřeny simulací NiceGUI. Samostatný Chromium v tomto
  prostředí nelze spustit kvůli odmítnutému vytvoření AF_UNIX socketu; screenshoty
  webového formuláře a skutečný Windows EXE nebyly ověřeny.
- Produkční databáze, skutečné odeslání e-mailu a nasazení nejsou součástí této změny.
