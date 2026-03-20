import pytest

from src.config.settings import build_settings


def test_build_settings_fails_when_database_url_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError) as exc_info:
        build_settings(env_file=None)

    assert "DATABASE_URL is required" in str(exc_info.value)


def test_build_settings_fails_when_database_url_invalid(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "not-a-valid-sqlalchemy-url")

    with pytest.raises(RuntimeError) as exc_info:
        build_settings(env_file=None)

    assert "DATABASE_URL is not a valid SQLAlchemy URL" in str(exc_info.value)


def test_build_settings_accepts_valid_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./stage1_config_check.db")

    cfg = build_settings(env_file=None)

    assert cfg.DATABASE_URL == "sqlite:///./stage1_config_check.db"
