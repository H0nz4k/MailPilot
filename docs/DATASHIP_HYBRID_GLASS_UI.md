# DataShip — Hybrid Glass compact UI (návrh v0.2)

**Stav:** čeká na schválení interaktivního náhledu, zatím **bez zásahu do běžící aplikace**.

**Náhled (Grafika):** [DataShip_Hybrid_Glass_v0.2_Preview.html](https://github.com/H0nz4k/Grafika/blob/main/demos/DataShip_Hybrid_Glass_v0.2_Preview.html)

## Cíl

Zpřehlednit vývojovou webovou aplikaci DataShip (NiceGUI): menší vizuální šířka, méně současně zobrazených tlačítek, jasná hierarchie denních kroků. Převzít decentní Apple Technical / Hybrid Glass ze sdílené knihovny návrhů Grafika, nikoli přidávat další dekorativní dashboard.

## Mapa obrazovek

| Oblast | Cílový návrh | Zachovat |
|---|---|---|
| Denní stav | kompaktní blok: datum + kategorie → PDF / Vytvořit a odeslat; pokročilá nastavení v rozbalení | všechny přepínače PDF, odesílání a kontrolu připojení, potvrzení odeslání |
| Uzávěrka | měsíc, sestavy, jedna primární akce; ZIP/mail/pokročilé oddělit | FKSP, arch, rekapitulace, cesty a současné CLI přepínače |
| E-mailové úlohy | stručný řádkový přehled; tlačítka Upravit/Kopírovat/Zapnout/Vypnout/Smazat pod **⋯** | veškeré CRUD, validační logiku a potvrzení smazání |
| Speciál Z 17-01, Hromadná zpráva | přístup přes „Další možnosti“, ne trvale na hlavní liště | stejné filtry, kategorie, práva a send confirmation |
| Administrace | viditelně oddělené technické nastavení; složité části v accordionu | heslo, zamykání, DB, e-mailové účty, NSSM, Plánovač, vzhled |
| Nastavení vzhledu | 5 světelných + 5 tmavých decentních schémat; A−/A+ **90–125 %** | respekt starších hodnot `config.json`, fungující přiblížení a úprava textu |

## Návrhové zásady

- Pracovní plocha max. kolem 1100–1200 px; na širokém monitoru netahat formuláře přes celou obrazovku.
- Rozdělení primární / sekundární / pokročilé: ne více než jedna skutečně dominantní CTA pro daný krok.
- Čitelné popisky, přístupné kontrasty v light i dark, výchozí viditelnost důležitých stavů bez technické zahlcenosti.
- Jemná průsvitnost, hranice, stíny a zaoblení; optimalizovat i pro slabší PC a respektovat `prefers-reduced-motion`.
- Responsive desktop i mobil; žádná funkce se nesmí ztratit na úzkém displeji.
- Neprovádět při designových změnách automatické odesílání, zásahy do DB nebo instalaci NSSM; UX demo nemá přístup k backendu.

## Implementační pořadí po schválení náhledu

1. Přidat nové barevné tokeny a stylované komponenty do prezentační vrstvy NiceGUI; ověřit starší konfigurace.
2. Kompaktní Denní stav a Uzávěrka; všechny stávající callbacky zůstanou na místě.
3. Seznam e-mailových úloh s menu ⋯ a bez zbytečných CTA; admin sekce s rozbalováním.
4. Responsivita, klávesnice, kontrast barevných palet, 90–125 % font.
5. Testy vzhledových helperů, smoke-test navigace/přístupů a sestavení Windows v CI; žádné reálné maily bez výslovného souhlasu.

**Výchozí omezení:** mění se pouze NiceGUI webová větev `feat/web-mail-scheduler`; původní Qt MailPilot ani funkční konfigurace a CLI se nepřejmenovávají násilně. Před první aktivací DataShip-Worker zkontrolovat existující NSSM službu, aby neběžely dvě instance současně.
