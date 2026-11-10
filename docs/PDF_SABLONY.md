# Rozložení, náhled a šablony PDF

V kroku **Obsah a PDF** otevřete **Nastavení PDF**. Dialog má dvě záložky:

- **Vzhled a obsah**: viditelné souhrny, seznamy, orientace, písmo a volba
  **Zkracovat názvy jídel – stejně vysoké řádky**.
- **Rozložení, náhled a šablony**: pořadí bloků, jeden nebo dva bloky vedle sebe,
  nové stránky, stránkovaný náhled a uložené šablony.

## Zkracování jídel

Při zapnutí se názvy jídel v jídelníčku, seznamu strávníků a souhrnu výdeje
zkracují podle skutečné šířky sloupce a zvoleného písma. Konec označuje výpustka
`…`. Datové řádky mají pevnou, shodnou výšku; jiné údaje (například dlouhé jméno)
se ve své buňce zmenší tak, aby se zachoval celý text. Záhlaví se může zalomit.
Po vypnutí se vrátí úplné názvy jídel a automatická výška řádků.

## Sestavení rozložení

1. Šipkami přesuňte řádek nahoru nebo dolů.
2. **Vedle předchozího** umístí dva sousední bloky vedle sebe.
3. **Prohodit** vymění jejich levou a pravou pozici; **Pod sebe** je opět rozdělí.
4. **Začít na nové stránce** přesune celý řádek na další stránku.
5. **Obnovit výchozí rozložení** vrátí původní pořadí a seznam strávníků na novou stránku.

Upravovat lze jídelníček, souhrn kategorií, souhrn norem, souhrn výdejů a seznam
strávníků. U speciálního přehledu odběrů se zobrazuje jeho vlastní blok. Blok
vypnutý v záložce Vzhled a obsah se do PDF nevloží. Hlavička, datum a základní
počty zůstávají před uspořádanými bloky.

Dlouhé tabulky vedle sebe mohou pokračovat přes více stran. Pokud se jednotlivý
znak záhlaví do úzkého sloupce při zvoleném písmu nevejde, náhled ohlásí potřebu
samostatného řádku nebo menšího písma. Samostatné stránky jednotlivých typů výdeje
vyžadují pro tento blok vlastní řádek.

## Náhled a šablona

**Aktualizovat náhled** vytvoří stejný PDF dokument jako export a zobrazí jej jako
obrázek přímo v aplikaci. Lze procházet všechny jeho stránky. Po změně nastavení,
data nebo filtrů aplikace označí náhled jako zastaralý, dokud jej neaktualizujete.

Jako zdroj vyberte **Vybraná data z Jídelny** (vyžaduje ověřené připojení) nebo
**Ukázková data** (výslovně označené smyšlené údaje pro návrh vzhledu). Náhled
nic neodesílá, nepřepisuje export a neukládá pracovní změny do konfigurace.

Zadejte název a zvolte **Uložit jako novou**, případně **Uložit změny šablony**.
Šablona ukládá vzhled, viditelnost bloků, rozložení a zalomení stránek. Neobsahuje
datum, vybrané kategorie, typy stravy/výdeje, stav odběru, připojení ani adresáty.
Lze ji tedy použít pro jiný přehled a jiné filtry.

Při uložení přehledu nebo úlohy průvodce se uloží kopie vzhledu a rozložení do
profilu. Pozdější úprava šablony sama nezmění již naplánované přehledy. Pro jejich
změnu použijte šablonu v příslušném přehledu a uložte jej.

## Technické ověření

- Šablony jsou v `pdf_templates.json`, ukládaném atomicky. Poškozený soubor se
  nepřepisuje; duplicitní názvy a neplatné definice se odmítají. Aktualizace
  instalace zachovává i tento soubor.
- Náhled používá přibalený PDFium (`pypdfium2`), nevyžaduje systémový prohlížeč PDF
  ani Poppler. Windows build zahrnuje jeho balíčky a nativní knihovnu.
- Ověřena shodná výška řádků, výpustky podle metrik fontu, zachování celých jmen,
  skutečné souřadnice bloků vedle sebe, nové stránky, vypínání bloků a zachování
  130 jmen i 90 kategorií ve dvou dlouhých sloupcích.
- Ověřeno uložení a nové načtení šablony/profilu, nastavení exportu, generování a
  rasterizace náhledu, listování stránkami a interakce editoru simulací NiceGUI.
  PDF bylo vizuálně zkontrolováno na výšku i na šířku.
- Cílená sada prošla: 221 testů a 14 podtestů; jeden test vyžaduje Windows a je
  na Linuxu přeskočen. Rozšířená kontrola `test_nicegui_helpers.py` vykazuje tři
  starší chyby, reprodukované i beze změn na commitu `9e59fd7`: dvě kontroly
  odstraněné `_build_mail_panel` a zastaralé očekávání pevného Resend API klíče.
- Chromium v tomto prostředí odmítá vytvoření AF_UNIX socketu, proto nebyla
  provedena kontrola screenshotů webového editoru. Windows EXE, zákaznická
  databáze a skutečné odeslání nejsou touto kontrolou ověřeny. Změna není nasazená.
