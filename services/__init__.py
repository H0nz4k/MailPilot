"""Servisní vrstva MailPilotu bez jakékoli závislosti na GUI.

Moduly v tomto balíčku stojí mezi prezentační vrstvou (NiceGUI nebo Qt)
a business logikou v korenových modulech (``stravovaci_sestava``,
``mail_service``, ``uzaverka``, ``z17`` …).  Nesmí importovat ``nicegui``
ani ``PySide6``; díky tomu je lze testovat bez běžícího UI.
"""
