# MailShip: historie a stav odesílání

Administrace → Logy zobrazuje posledních 200 událostí workeru a obnovuje změny každých 5 sekund. Zobrazení vyžaduje odemčenou administraci. Odesílání u jednotlivých úloh ukazuje poslední výsledek po obnovení seznamu tlačítkem Obnovit. Chyby kalendáře uvádějí měsíc a kalendář s pokynem pro obsluhu.

Je nutné sestavit a aktualizovat GUI i DataShip-Worker.exe ze stejné revize. Název v GUI a upozornění je MailShip; názvy EXE a služby zůstávají kompatibilní. Službu před aktualizací zastavte. Zachovejte provozní JSON soubory, přístupové údaje a složku logy (včetně activity.sqlite3). Starší textové logy se automaticky neimportují.

Nová historie je v logy/activity.sqlite3 vedle provozního config.json. Uchovává nejvýše 2000 událostí. Neobsahuje transportní hesla ani plné výjimky. Původní technický log web_mail_worker.log zůstává k dispozici. Chyba zápisu historie nevyvolá opakované odeslání ani nezmění plánování. Stránka Logy sama nic neodesílá a nemění stav úloh.

Ověření na Windows: spustit aktualizovaný worker s izolovanou konfigurací a lokálním SMTP zachytávačem bez relay. Ověřit úspěch a chybějící kalendář, odpovídající stavy správných úloh, historii po restartu, uzamčení administrace a tlačítko Obnovit. Skutečné adresáty při validaci nepoužívat.
