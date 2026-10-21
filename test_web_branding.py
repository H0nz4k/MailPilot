"""Public-facing name of the independent DataShip web build."""
from services.web_branding import (
    BRAND_NAME, BRAND_STAGE, BRAND_FOOTER, BRAND_ICON,
    WEB_EXE_NAME, WORKER_EXE_NAME,
)


def test_dataship_brand_is_consistent():
    assert BRAND_NAME == "DataShip"
    assert BRAND_STAGE == "beta"
    assert BRAND_FOOTER.startswith("DataShip")
    assert BRAND_ICON == "sailing"
    assert WEB_EXE_NAME == "DataShip.exe"
    assert WORKER_EXE_NAME == "DataShip-Worker.exe"
