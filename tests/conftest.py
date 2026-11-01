import pytest

from tirekick import config


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Every test gets its own data/ dir, fake AI, dev mode, and no real credentials."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setenv("TIREKICK_FAKE_AI", "1")
    monkeypatch.setenv("TIREKICK_DEV", "1")
    for var in ("WHATSAPP_TOKEN", "META_API_KEY", "WHATSAPP_APP_SECRET"):
        monkeypatch.delenv(var, raising=False)
    yield
