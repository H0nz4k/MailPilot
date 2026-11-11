# DataShip 2 — stav převodu

Vývojová větev `feature/dataship-v2-prototype`; verze 1.4 zůstává provozní základnou. Cílem je zachovat její funkce a krokový průvodce v desktopovém prostředí Tauri. Prototyp není náhradou verze 1.4.

## Přeneseno a ověřeno izolovaně

- Nový prázdný prostor lze založit bez verze 1.4, po testu připojení a nastavení systémových hesel; ověřeno s náhradami databáze a trezoru.
- Volitelný import do odděleného prostoru verze 2 kopíruje konfiguraci, profily, šablony PDF a historii příjemců a úlohy převede jako pozastavené; nepřepisuje existující prostor ani staré soubory. Nová služba používá vlastní název. Ověřeno izolovaně.
- Hromadná zpráva: výběr tříd nebo kategorií, náhled příjemců a Resend; při odeslání se seznam znovu načte a porovná s náhledem. Ověřeno s náhradní databází a odesílačem, skutečné odeslání neproběhlo.
- Speciál Z 17-01: jednorázový podklad s výběrem povolených kategorií a mapováním řádků přes původní výpočet; ověřeno s náhradou výpočtu, nikoli na skutečných datech. Mapování lze v odděleném prostoru uložit s heslem administrace; kategorie mimo oprávněný rozsah zůstávají zachované.
- Uzávěrka: generování FKSP, stravovacího archu a rekapitulace přes původní služby, do jedinečné dočasné složky bez odeslání e-mailu, s následným uložením do nové cílové složky a jednorázovým odesláním; ověřeno s náhradou výpočtu, nikoli na skutečných datech.
- Jednorázové Odběry: po vytvoření lze PDF uložit pod novým názvem nebo odeslat podle nastavení SMTP/Resend bez vytvoření úlohy. Odeslání je testováno pouze s náhradním transportem.
- Odběry za období: součty po strávnících v náhledu a PDF, výběr stavu, více kategorií a typů stravy/výdeje, volitelný souhrn kategorií a desktopové vytvoření ukázkového PDF.
- Volitelné čtení konfigurace verze 1.4 a odběrů přes původní služby, s omezením na povolené kategorie. Připojení používá uložené heslo, ale heslo ani konfiguraci nepřepisuje. Ověřeno pouze testy s náhradou databáze; skutečná Jídelna a její výsledky zatím nejsou ověřeny.
- Průvodce umí vypočítat příští den spuštění a den sestavy včetně kalendáře varných dnů (ověřeno náhradou databáze).
- Průvodce může vytvořit PDF náhledu z vybraného profilu bez uložení úlohy; ověřeno izolovaně.
- Průvodce načítá uložené šablony PDF a umožňuje uložit nové; pořadí, umístění vedle sebe, prohození a zalomení bloků lze upravit přímo v průvodci.
- Průvodce podporuje výběr více kategorií, skutečných typů stravy a výdeje a základní volby PDF, velikosti písma, jazyk a číslo jídelníčku; backend ověřuje jejich dostupnost. Ověřeno na náhradách databáze.
- Administrace umožňuje vytvořit nebo změnit heslo v systémovém úložišti (sdíleném s původním DataShipem); ověřeno testovacími náhradami trezoru.
- Administrace umožňuje vybrat povolené kategorie ze skutečné Jídelny; ověřeno s náhradou databáze.
- Nastavení databázového připojení se před uložením ověřuje a používá systémové úložiště hesel; ověřeno náhradou databáze.
- Nastavení e-mailu a NSSM v odděleném prostoru je chráněné existujícím heslem administrace; klíč Resend se při importu nekopíruje. Ověřeno simulovanými přihlašovacími údaji.
- Administrace umožňuje načíst posledních 200 událostí workeru po ověření hesla; ověřeno izolovaně.
- Samostatný worker verze 2 používá zámek proti dalšímu workeru nad stejnou konfigurací. Službu lze nainstalovat, spustit, zastavit, opravit a odstranit; akce služby jsou ověřené pouze náhradami, nikoli skutečnou službou.
- Čtyřkrokový průvodce v odděleném prostoru uloží profil a úlohu; umí vypsat úlohy, pozastavit, zapnout, odstranit a upravit je krokovým průvodcem. Při změně vytváří nový profil a chrání ostatní úlohy sdílející původní profil. Zobrazuje diagnostický stav původní služby a workeru; existující službu umí spustit a zastavit po ověření workeru a konfigurace. Nové úlohy jsou výchozím stavem pozastavené. Ověřeno izolovaně s náhradou databáze, ne reálnou službou nebo odesláním.

## K převodu a ověření

1. Ověření administrace, připojení a oprávnění na skutečném počítači a Jídelně.
2. Přehledy a PDF včetně všech voleb z 1.4, hromadných strávníků, šablon a uložených profilů.
3. Ověřit průvodce a plánování přes skutečnou službu a stránkový náhled na skutečných datech.
4. Ověřit samostatný plánovač a jeho Windows službu v reálném prostředí; zabránit duplicitnímu odeslání při souběhu samostatných konfigurací. Nezapínat automatické odesílání při migraci bez jasného stavu a ověření.
5. Jednorázové Odběry: doplnit zbývající původní volby a ověřit skutečné doručení a cílové uložení v desktopu.
6. Ověřit uzávěrku a odeslání na reálném prostředí; doplnit ostatní sestavy, diagnostiku a návody.
7. Přenos konfigurace bez ztráty údajů, kompatibilita pracovníků, Windows balíček, měření velikosti, integrační testy a ověření na skutečné databázi a cílovém počítači.

Nepovažovat simulované testy za ověření skutečného databázového připojení, odesílání nebo služby.

Úpravy z více instancí verze 2 používají společný zámek a kontrolu změny úlohy. Oddělený import umožňuje pracovat s vlastními kopiemi. Verze 1.4 tento zámek nezná, proto DataShip 2 odmítá zápis úloh do úložiště 1.4. Import provádějte během klidu, bez současných změn původních souborů.

Jednorázové odesílání uzávěrky a Z 17-01 používá nakonfigurovaný transport SMTP/Resend, ale nebylo ověřeno skutečným e-mailem.

Průvodce zobrazuje jednotlivé stránky vytvořeného PDF přímo v aplikaci. Vykreslení bylo ověřeno na ukázkovém PDF i v zabaleném enginu; skutečná databáze dosud ověřena nebyla.

Uložené přehledy lze načíst jako kopii v průvodci. Výběr kategorií se omezí na aktuální oprávnění a změna se nepromítá do původního profilu; ověřeno izolovaně.

Starší denní úlohu bez vlastního profilu lze otevřít v průvodci; při uložení se její tehdejší společné nastavení převede na samostatný profil a před uložením se kontroluje jeho změna. Ověřeno izolovaně; automatické změny globálního nastavení se po převedení již do úlohy nepřenášejí.

Průvodce umožňuje zvolit kalendář podle typu přehledu, všechny kalendáře nebo konkrétní kalendáře z databáze. Výběr se při uložení i náhledu ověřuje; původní explicitní výběr lze upravit. Ověřeno testy s náhradou databáze a zobrazením ukázkového průvodce.

V běžném průvodci lze vytvořený PDF náhled uložit na novou cestu bez vytvoření úlohy; existující soubor se nepřepisuje. Backend ukládání pokrývají izolované testy.

Zápis úloh je na hranici enginu omezen na oddělený pracovní prostor DataShip 2; starou konfiguraci lze prohlížet a použít pro sestavy. Ověřeny všechny čtyři operace zápisu i povolení v izolovaném prostoru.
