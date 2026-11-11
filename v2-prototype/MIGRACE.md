# DataShip 2 — stav převodu

Vývojová větev `feature/dataship-v2-prototype`; verze 1.4 zůstává provozní základnou. Cílem je zachovat její funkce a krokový průvodce v desktopovém prostředí Tauri. Prototyp není náhradou verze 1.4.

## Přeneseno a ověřeno izolovaně

- Volitelný import do odděleného prostoru verze 2 kopíruje konfiguraci, profily, šablony PDF a historii příjemců a úlohy převede jako pozastavené; nepřepisuje existující prostor ani staré soubory. Nová služba používá vlastní název. Ověřeno izolovaně.
- Jednorázové Odběry: po vytvoření lze PDF uložit pod novým názvem nebo odeslat podle nastavení SMTP/Resend bez vytvoření úlohy. Odeslání je testováno pouze s náhradním transportem.
- Odběry za období: součty po strávnících v náhledu a PDF, výběr stavu, více kategorií a typů stravy/výdeje, volitelný souhrn kategorií a desktopové vytvoření ukázkového PDF.
- Volitelné čtení konfigurace verze 1.4 a odběrů přes původní služby, s omezením na povolené kategorie. Připojení používá uložené heslo, ale heslo ani konfiguraci nepřepisuje. Ověřeno pouze testy s náhradou databáze; skutečná Jídelna a její výsledky zatím nejsou ověřeny.
- Průvodce umí vypočítat příští den spuštění a den sestavy včetně kalendáře varných dnů (ověřeno náhradou databáze).
- Průvodce může vytvořit PDF náhledu z vybraného profilu bez uložení úlohy; ověřeno izolovaně.
- Průvodce načítá uložené šablony PDF a zachovává jejich rozložení i velikosti písma.
- Průvodce podporuje výběr více kategorií, skutečných typů stravy a výdeje a základní volby PDF; backend ověřuje jejich dostupnost. Ověřeno na náhradách databáze.
- Nastavení e-mailu a NSSM v odděleném prostoru je chráněné existujícím heslem administrace; klíč Resend se při importu nekopíruje. Ověřeno simulovanými přihlašovacími údaji.
- Samostatný worker verze 2 používá zámek proti dalšímu workeru nad stejnou konfigurací. Službu lze nainstalovat, spustit, zastavit, opravit a odstranit; akce služby jsou ověřené pouze náhradami, nikoli skutečnou službou.
- Čtyřkrokový průvodce při připojení uloží profil a úlohu do úložiště 1.4; umí vypsat úlohy, pozastavit, zapnout, odstranit a upravit je krokovým průvodcem. Při změně vytváří nový profil a chrání ostatní úlohy sdílející původní profil. Zobrazuje diagnostický stav původní služby a workeru; existující službu umí spustit a zastavit po ověření workeru a konfigurace. Nové úlohy jsou výchozím stavem pozastavené. Ověřeno izolovaně s náhradou databáze, ne reálnou službou nebo odesláním.

## K převodu a ověření

1. Nastavení připojení, založení a změna hesla administrace, správa oprávnění a bezpečné ukládání hesel.
2. Přehledy a PDF včetně všech voleb z 1.4, hromadných strávníků, šablon a uložených profilů.
3. Dokončit průvodce: zbývající volby PDF a interaktivní náhled; ověřit běh přes skutečnou službu.
4. Ověřit samostatný plánovač a jeho Windows službu v reálném prostředí; zabránit duplicitnímu odeslání při souběhu samostatných konfigurací. Nezapínat automatické odesílání při migraci bez jasného stavu a ověření.
5. Jednorázové Odběry: doplnit zbývající původní volby a ověřit skutečné doručení a cílové uložení v desktopu.
6. Ostatní dostupné sestavy a uzávěrky, konfigurace, ochrana heslem, diagnostika a návody.
7. Přenos konfigurace bez ztráty údajů, kompatibilita pracovníků, Windows balíček, měření velikosti, integrační testy a ověření na skutečné databázi a cílovém počítači.

Nepovažovat simulované testy za ověření skutečného databázového připojení, odesílání nebo služby.

Úpravy z více instancí verze 2 používají společný zámek a kontrolu změny úlohy. Oddělený import umožňuje pracovat s vlastními kopiemi. Pozor: verze 1.4 tento zámek nezná; souběžné úpravy z 1.4 a 2 stále nejsou bezpečné a před provozním nasazením je nutná jejich koordinace.
