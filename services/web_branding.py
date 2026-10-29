"""DataShip public branding for the new NiceGUI edition only.

Keep legacy Qt MailPilot/AutoReport branding and file formats unchanged.
"""
BRAND_NAME = "MailShip"
BRAND_STAGE = "rc.10"
WEB_VERSION = "1.0.0-rc.10"
WEB_BUILD = "20261029.5"
BRAND_FOOTER = "MailShip by HanzG"
BRAND_ICON = "sailing"
BRAND_FAVICON = "🚢"
WEB_EXE_NAME = "DataShip.exe"
WORKER_EXE_NAME = "DataShip-Worker.exe"



def version_caption(*, frozen: bool = False) -> str:
    """Visible build identity also distinguishes source runs from frozen EXEs."""
    return f"{WEB_VERSION} · sestavení {WEB_BUILD} · {'EXE' if frozen else 'Python'}"



