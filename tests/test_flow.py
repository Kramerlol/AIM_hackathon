import smtplib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import backend, mailer, sms
from app.main import app

DOCS = Path(__file__).resolve().parent.parent / "scenario" / "documents"
LAB = "demo-lab-brandl"
REHAB = "demo-rehab-kern"
PII = ["maria", "beispiel", "1961", "12 march", "blood", "clotting", "lab result", "rehab", "inr"]


@pytest.fixture(autouse=True)
def fresh(monkeypatch, tmp_path):
    monkeypatch.setattr(backend, "_backend", backend.StubBackend())
    monkeypatch.setattr(sms, "DB", tmp_path / "sms.db")


@pytest.fixture
def client():
    return TestClient(app)


def login(client, token, who):
    return client.post(f"/r/{token}/identity", data={"identity_id": who}, follow_redirects=False)


def submit(client, token, doc, name="Maria Beispiel", birth="12.03.1961"):
    text = (DOCS / doc).read_text()
    return client.post(f"/r/{token}/answer",
                       data={"patient_name": name, "patient_birthdate": birth, "source": "paste",
                             "content": text})


def test_landing_leaks_nothing(client):
    page = client.get(f"/r/{LAB}").text.lower()
    assert not any(word in page for word in PII)


def test_happy_path_lab(client):
    assert login(client, LAB, "brandl").status_code == 303
    page = client.get(f"/r/{LAB}/answer").text
    assert "M. B., born 1961" in page and "Maria" not in page
    r = submit(client, LAB, "lab-result-maria-beispiel.md")
    assert "Thank you" in r.text and "(4 values)" in r.text
    assert login(client, LAB, "brandl").status_code == 403  # link is used up


def test_happy_path_rehab(client):
    login(client, REHAB, "kern")
    r = submit(client, REHAB, "rehab-report-maria-beispiel.md")
    assert "Thank you" in r.text


def test_m1_wrong_person_sees_nothing(client):
    r = login(client, LAB, "stranger")
    assert r.status_code == 403
    assert not any(word in r.text.lower() for word in PII)
    assert client.get(f"/r/{LAB}/answer").status_code == 403
    assert "identity_checked" in [a["event"] for a in backend.get_backend().audit]


def test_m2_colleague_blocked_and_hofer_told(client):
    assert login(client, LAB, "colleague").status_code == 403
    assert client.get(f"/r/{LAB}/answer").status_code == 403
    assert submit(client, LAB, "lab-result-maria-beispiel.md").status_code == 403
    be = backend.get_backend()
    assert "answer_filed" not in [a["event"] for a in be.audit]
    assert any("colleague" in n.lower() for n in be.notifications)


def test_m3_wrong_patient_not_filed(client):
    login(client, LAB, "brandl")
    r = submit(client, LAB, "lab-result-max-beispiel.md")
    assert "does not match" in r.text and "Max" not in r.text
    be = backend.get_backend()
    assert "answer_filed" not in [a["event"] for a in be.audit]
    assert any("Max Beispiel" in n and "Not filed" in n for n in be.notifications)


def test_unreadable_document_keeps_form_filled(client):
    login(client, LAB, "brandl")
    r = client.post(f"/r/{LAB}/answer", data={"patient_name": "Maria Beispiel",
                    "patient_birthdate": "12.03.1961", "source": "paste", "content": "hello"})
    assert r.status_code == 422 and "could not" in r.text.lower() and "Maria Beispiel" in r.text


def test_bad_date_is_rejected_politely(client):
    login(client, LAB, "brandl")
    r = submit(client, LAB, "lab-result-maria-beispiel.md", birth="soon")
    assert r.status_code == 422 and "valid birth date" in r.text


def test_file_upload(client):
    login(client, LAB, "brandl")
    f = (DOCS / "lab-result-maria-beispiel.md").read_bytes()
    r = client.post(f"/r/{LAB}/answer", data={"patient_name": "Maria Beispiel",
                    "patient_birthdate": "1961-03-12", "source": "upload"},
                    files={"file": ("lab.md", f, "text/markdown")})
    assert "Thank you" in r.text


def test_unknown_token_is_neutral(client):
    r = client.get("/r/nope")
    assert r.status_code == 403 and "intended recipient" in r.text


def test_email_and_sms_carry_only_link_and_code(monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def send_message(self, msg): sent.append(msg)

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    mailer.send_request("email", "eva.brandl@labor-kanal.example", "http://x/r/t", "ABCD1234")
    mailer.send_request("sms", "+43 660 000 0101", "http://x/r/t", "ABCD1234")
    texts = [str(sent[0]["Subject"]) + sent[0].get_content()] + [m["text"] for m in sms.all_messages()]
    for text in texts:
        assert "http://x/r/t" in text and "ABCD1234" in text
        assert not any(word in text.lower() for word in PII)
