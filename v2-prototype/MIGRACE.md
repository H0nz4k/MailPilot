# DataShip 2 — stav převodu

Vývojová větev `feature/dataship-v2-prototype`; verze 1.4 zůstává provozní základnou. Cílem je zachovat její funkce a krokový průvodce v desktopovém prostředí Tauri. Prototyp není náhradou verze 1.4.

## Přeneseno a ověřeno izolovaně

- Odběry za období: součty po strávnících v náhledu a PDF, výběr stavu a kategorie, desktopové vytvoření ukázkového PDF.
- Volitelné čtení konfigurace verze 1.4 a odběrů přes původní služby, s omezením na povolené kategorie. Připojení používá uložené heslo, ale heslo ani konfiguraci nepřepisuje. Ověřeno pouze testy s náhradou databáze; skutečná Jídelna a její výsledky zatím nejsou ověřeny.
- Čtyřkrokový průvodce při připojení uloží profil a úlohu do úložiště 1.4; umí vypsat úlohy, pozastavit a zapnout je. Nové úlohy jsou výchozím stavem pozastavené. Ověřeno izolovaně s náhradou databáze, ne reálnou službou nebo odesláním.

## K převodu a ověření

1. Nastavení připojení, správa oprávnění a bezpečné ukládání hesel, výběr kategorií a typů stravy/výdeje podle skutečných dat.
2. Přehledy a PDF včetně všech voleb z 1.4, hromadných strávníků, šablon a uložených profilů.
3. Dokončit průvodce: výběr více kategorií a typů stravy/výdeje, všechny volby PDF, úpravy úloh a úplný náhled; ověřit běh přes skutečnou službu.
4. Plánovač/Windows služba, její stav, instalace a odinstalace; zabránit souběhu starého a nového plánovače. Nezapínat automatické odesílání při migraci bez jasného stavu a ověření.
5. Jednorázové Odběry: cílové uložení a odeslání, všechny původní filtry a volby.
6. Ostatní dostupné sestavy a uzávěrky, konfigurace, ochrana heslem, diagnostika a návody.
7. Přenos konfigurace bez ztráty údajů, kompatibilita pracovníků, Windows balíček, měření velikosti, integrační testy a ověření na skutečné databázi a cílovém počítači.

Nepovažovat simulované testy za ověření skutečného databázového připojení, odesílání nebo služby.

Pozor: úložiště 1.4 nemá společný zámek pro souběžné editace z 1.4 a 2. Needitovat současně; před provozním nasazením vyřešit koordinaci zápisů.
