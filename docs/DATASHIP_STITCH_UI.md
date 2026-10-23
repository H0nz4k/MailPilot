# DataShip – zapracování návrhů ze Stitch

Podklady dodané uživatelem:

- `stitch_redesign_rozhran_dataship (1).zip`: Přehledy, uložení výběru.
- `stitch_redesign_rozhran_dataship.zip`: měsíční uzávěrka.
- `stitch_redesign_rozhran_dataship (2).zip`: Služba a odesílání.

## Převzatý vzhled

Námořní modrá, bílé bloky, jemně tónované pozadí, celé rámečky,
čitelné nadpisy, popisy a velká tlačítka. Základní text nadále respektuje
nastavenou velikost (výchozí 20 px), popisy 16 px. Zůstávají vlastní barvy,
tučné řezy, přiblížení i tmavý režim. Písmo používá systémový Segoe UI;
rozhraní nevyžaduje stahování fontů nebo Tailwindu z internetu.

## Skutečné chování

- Přehledy: výběr uloženého přehledu v horní liště; samostatný náhled,
  filtry a vybrané kategorie vlevo, počty a PDF vpravo. Uložení změn je výslovné.
- Odesílání: stejný uložený přehled, příjemci jako označené adresy, čas,
  pravidlo data a vlastní kalendář varných dnů. Uložení neodesílá e-mail.
- Uzávěrka: měsíc, rok, výběr skutečně podporovaných PDF, volitelný ZIP,
  vytvoření souborů a stažení. Ruční vytvoření vždy používá samostatný
  snímek konfigurace s vypnutým e-mailem, i když automatická uzávěrka e-mail
  povolený má. Snímek se odstraní také při chybě. Původní nastavení se nemění.
- Nastavení: vodorovná navigace; služba a upozornění v levém sloupci,
  odchozí e-mail v pravém. SMTP pole se zobrazují jen pro SMTP.
- Stav NSSM se zobrazí až po skutečném ověření. Zachovány stávající instalační
  příkazy, cesta k přibalenému NSSM a české chyby.

## Úpravy proti návrhům

Návrhy obsahují ukázková data a nepodložená tvrzení. Aplikace nepřebírá
fiktivní finanční ukazatele, úplnost docházky, ověření normování, elektronický
podpis, zamykání databázových záznamů, smyšlenou podporu ani značku VIS.
Oběd 1/2 nejsou použity jako typy stravy: zachováno databázové rozlišení
typu stravy a varianty menu. Odesílání nadále používá skutečný worker.

## Ověření

Regresní průchod uloženými přehledy a editorem odesílání. Test samostatného
snímku uzávěrky včetně zákazu e-mailu, zachování konfigurace a úklidu po chybě.
Kontrola rozložení v prohlížeči na notebooku, velkém monitoru a úzké obrazovce.
