# DataShip M6 — správa služby a aktualizace

## Služba

Při otevření DataShipu se stav ověřuje ve Windows Service Control Manageru. Instalaci lze přeskočit a později provést v **Nastavení → Služba a odesílání**. Pro změny služby je potřeba přístup do nastavení DataShipu a spuštění aplikace se zvýšenými oprávněními Windows. Instalace používá stávající NSSM a službu ponechá zastavenou do ověření nastavení.

## Klíč a balíčky

Správce vydávání potřebuje klíč Ed25519. Soukromý klíč zůstává v důvěryhodném prostředí vydávání. Veřejný klíč (32 bajtů ve formátu raw) doručte nezávislým důvěryhodným kanálem jako `dataship-update-public-key.bin` vedle DataShip.exe. Instalaci a tento soubor chraňte pomocí přístupových práv Windows.

```bash
bash scripts/build_web_windows.sh
.venv-web/Scripts/python.exe scripts/package_dataship_update.py \
  --app dist-web/DataShip --version "$(cat VERSION)" \
  --key /c/cesta/mimo/repozitar/signing-key.pem \
  --output "DataShip-$(cat VERSION)-Windows-x64-Update.zip"
```

GitHub Releases používá stabilní tag `dataship-vX.Y.Z` a balíček `DataShip-X.Y.Z-Windows-x64-Update.zip`. Přístup k soukromému repozitáři používá oprávnění účtu přihlášeného do GitHub CLI. Lokální ZIP používá stejný podpis a funguje offline. Starší distribuční ZIP bez manifestu nelze použít jako aktualizační balíček.

## Průběh a zotavení

V Nastavení otevřete **Aktualizace** a vyberte GitHub nebo místní ZIP. Dokončete práci v otevřených oknech a DataShip zavřete. Aktualizátor ověří balíček, nechá běžící službu dokončit přijatou úlohu, vymění programové soubory, ověří verze EXE a obnoví běh služby. Výsledek je v `logy/dataship_updates.log`. Soubory konfigurace, PDF, historie, NSSM a registrace služby i Windows úloh zůstávají ve stávajících cestách.

Běžící starší worker bez podpory režimu údržby výměnu nepotvrdí. Pro jeho první převod naplánujte odstávku, doběhnutí úloh ověřte a službu zastavte před aktualizací. Po úspěchu ji znovu spusťte. Při tvrdém přerušení spusťte po zavření GUI ve stejné instalaci `DataShip-Updater.exe --recover` (s původním `--config`, je-li mimo instalační složku). Obnova vrací programové soubory. Tento balíček nemění schéma externího PostgreSQL Jídelny.

Windows CI sestavuje přenosný základ a variantu s NSSM. Samostatný podepsaný aktualizační ZIP vyžaduje důvěryhodný vydávací klíč. PR nic nepublikuje do GitHub Releases.
