import pytest

from app import audit, backend, validator


@pytest.fixture(autouse=True)
def audit_db(monkeypatch, tmp_path):
    """Every test gets its own audit database."""
    monkeypatch.setattr(audit, "DB_PATH", str(tmp_path / "audit.db"))


@pytest.fixture(autouse=True)
def no_fhir_server_or_java(monkeypatch):
    """Default: parse only. No Java validator, no FHIR server. Tests that need them say so."""
    monkeypatch.setattr(backend, "FHIR_MODE", "dry")
    monkeypatch.setattr(validator, "validator_available", lambda: False)
