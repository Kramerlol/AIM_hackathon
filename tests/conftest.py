import pytest

from app import audit


@pytest.fixture(autouse=True)
def audit_db(monkeypatch, tmp_path):
    """Every test gets its own audit database."""
    monkeypatch.setattr(audit, "DB_PATH", str(tmp_path / "audit.db"))
