"""Settings for DataShip web scheduler and optional SMTP delivery."""
from __future__ import annotations
import json
import os
from pathlib import Path

DEFAULTS = {
    "nssm_path": "",
    "service_name": "DataShipScheduler",
    "cooking_meal_type": "Oběd",
    "dashboard_enabled": True,
    "dashboard_path": r"C:\Gastro\Programy\Templates\dashboard.template.html",
    "transport": "resend",
    "smtp_host": "",
    "smtp_port": 587,
    "smtp_security": "starttls",
    "smtp_username": "",
    "from_email": "",
    "from_name": "",
    "subject_template": "{report} – {date}",
    "body_template": "Dobrý den,\n\nv příloze zasíláme sestavu {report} za {date}.\n",
}

def settings_path(directory: Path) -> Path:
    return Path(directory) / "web_mail_settings.json"

def load_settings(path: Path) -> dict:
    if not path.exists():
        values = dict(DEFAULTS)
        bundled_nssm = path.parent / "nssm" / "nssm.exe"
        if bundled_nssm.is_file():
            values["nssm_path"] = str(bundled_nssm.resolve())
        return values
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Nastavení musí být JSON objekt.")
    return {**DEFAULTS, **raw}

def save_settings(path: Path, data: dict) -> None:
    values = {key: data[key] for key in DEFAULTS if key in data}
    cooking_meal_type = values.get("cooking_meal_type", "")
    if not isinstance(cooking_meal_type, str) or not cooking_meal_type.strip():
        raise ValueError("Typ služby pro varné dny musí být vyplněn.")
    values["cooking_meal_type"] = cooking_meal_type.strip()
    if values.get("transport") not in ("resend", "smtp"):
        raise ValueError("Neznámý typ odesílání.")
    if values.get("smtp_security") not in ("starttls", "ssl", "none"):
        raise ValueError("Neznámý typ zabezpečení SMTP.")
    port = int(values.get("smtp_port", 587))
    if not 1 <= port <= 65535:
        raise ValueError("SMTP port je mimo rozsah.")
    values["smtp_port"] = port
    if not isinstance(values.get("dashboard_enabled"), bool):
        raise ValueError("Neplatná volba upozornění.")
    for key in ("subject_template", "body_template"):
        template = values.get(key, "")
        if not isinstance(template, str):
            raise ValueError("Šablona musí být text.")
        try:
            template.format(report="Denní stav", date="21.10.2026")
        except (KeyError, ValueError, IndexError) as exc:
            raise ValueError("Šablona může obsahovat pouze {report} a {date}.") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(values, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)

