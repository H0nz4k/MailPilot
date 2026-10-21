"""Standalone PyInstaller entrypoint for the independent MailPilot web scheduler."""
from __future__ import annotations

from multiprocessing import freeze_support
from services.web_mail_worker import main


if __name__ == "__main__":
    freeze_support()
    raise SystemExit(main())
