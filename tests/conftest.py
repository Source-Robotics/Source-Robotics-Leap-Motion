import pytest


@pytest.fixture(autouse=True)
def isolated_application_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_LEAP_CACHE", str(tmp_path / "app-cache"))
    monkeypatch.delenv("SOURCE_LEAP_CATALOG", raising=False)
