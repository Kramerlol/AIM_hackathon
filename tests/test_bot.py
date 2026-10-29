import pytest
from fastapi.testclient import TestClient

from app import backend, mailer, matrix_bot, notify, sms
from app.main import app

HOFER = "@lena.hofer:klinikum.example"
ROOM = "!room:klinikum.example"
CMD = ('!request lab patient=maria-beispiel to=eva.brandl@labor-kanal.example '
       'person="Dr. Eva Brandl" org="Labor Kanalstrasse"')


@pytest.fixture(autouse=True)
def fresh(monkeypatch, tmp_path):
    monkeypatch.setattr(backend, "_backend", backend.StubBackend())
    monkeypatch.setattr(sms, "DB", tmp_path / "sms.db")
    monkeypatch.setattr(notify, "outbox", [])
    sent = []
    monkeypatch.setattr(mailer, "send_request", lambda *a: sent.append(a))
    return sent


def test_parse_full_command():
    cmd = matrix_bot.parse_command(CMD)
    assert cmd == {"kind": "lab", "patient_id": "maria-beispiel",
                   "to": "eva.brandl@labor-kanal.example", "person": "Dr. Eva Brandl",
                   "org": "Labor Kanalstrasse"}


def test_parse_quoted_phone_number():
    cmd = matrix_bot.parse_command('!request rehab patient=maria-beispiel to="+43 660 000 0101" person="Stefan Kern"')
    assert cmd["to"] == "+43 660 000 0101" and cmd["org"] == ""


@pytest.mark.parametrize("text", ["!request", "!request lab", "!request lab patient=x",
                                  "!request lab patient=x to=y person=z colour=red",
                                  '!request lab patient=x to=y person="Dr. Unclosed'])
def test_parse_errors_show_usage(text):
    with pytest.raises(matrix_bot.CommandError) as exc:
        matrix_bot.parse_command(text)
    assert "Usage" in str(exc.value) or "Missing" in str(exc.value)


def test_request_sends_email_and_replies(fresh):
    reply = matrix_bot.handle_message(HOFER, ROOM, CMD)
    assert "sent to Dr. Eva Brandl by email" in reply
    channel, to, url, code = fresh[0]
    assert (channel, to) == ("email", "eva.brandl@labor-kanal.example")
    assert code in reply and "/r/" in url
    assert "http" not in reply  # the secret link stays out of the chat
    events = [a["event"] for a in backend.get_backend().audit]
    assert events == ["request_sent"]


def test_phone_number_goes_by_sms(fresh):
    matrix_bot.handle_message(HOFER, ROOM, '!request rehab patient=maria-beispiel to="+43 660 000 0101" person="Stefan Kern"')
    assert fresh[0][0] == "sms"


def test_stranger_in_the_room_is_refused(fresh):
    reply = matrix_bot.handle_message("@mallory:klinikum.example", ROOM, CMD)
    assert "not allowed" in reply and not fresh


def test_chatter_is_ignored(fresh):
    assert matrix_bot.handle_message(HOFER, ROOM, "good morning") is None
    assert matrix_bot.handle_message(HOFER, ROOM, "!unknown") is None


def test_unknown_patient_and_kind_are_explained(fresh):
    assert "Unknown patient" in matrix_bot.handle_message(
        HOFER, ROOM, CMD.replace("maria-beispiel", "nobody"))
    assert "Unknown document type" in matrix_bot.handle_message(HOFER, ROOM, CMD.replace(" lab ", " xray "))
    assert not fresh


def test_send_failure_is_reported_and_not_audited(monkeypatch):
    def boom(*a):
        raise ConnectionRefusedError()
    monkeypatch.setattr(mailer, "send_request", boom)
    reply = matrix_bot.handle_message(HOFER, ROOM, CMD)
    assert "could not be sent" in reply
    assert backend.get_backend().audit == []


def test_typo_address_is_not_rejected_and_m1_reaches_the_room(fresh):
    """M1: the request goes to the mistyped address; the stranger who opens it fails and Hofer hears."""
    matrix_bot.handle_message(HOFER, ROOM, CMD.replace("labor-kanal", "labor-kanaI"))
    token = fresh[0][2].rsplit("/", 1)[1]
    client = TestClient(app)
    r = client.post(f"/r/{token}/identity", data={"identity_id": "stranger"})
    assert r.status_code == 403
    room, text = notify.outbox[-1]
    assert room == ROOM and "Failed identity check" in text and "Nothing was filed" in text


def test_filed_message_reaches_the_requesting_room(fresh):
    matrix_bot.handle_message(HOFER, ROOM, CMD)
    token = fresh[0][2].rsplit("/", 1)[1]
    client = TestClient(app)
    client.post(f"/r/{token}/identity", data={"identity_id": "brandl"})
    from pathlib import Path
    doc = (Path(__file__).resolve().parent.parent / "scenario/documents/lab-result-maria-beispiel.md").read_text()
    client.post(f"/r/{token}/answer", data={"patient_name": "Maria Beispiel",
                "patient_birthdate": "12.03.1961", "source": "paste", "content": doc})
    room, text = notify.outbox[-1]
    assert room == ROOM and "filed" in text and "Maria Beispiel" in text


def test_post_requests_endpoint(fresh):
    client = TestClient(app)
    r = client.post("/requests", json={"kind": "lab", "patient_id": "maria-beispiel",
                    "to": "eva.brandl@labor-kanal.example", "person": "Dr. Eva Brandl"})
    assert r.status_code == 201 and r.json()["channel"] == "email"
    assert client.post("/requests", json={"kind": "lab", "patient_id": "x", "to": "a@b", "person": "c"}).status_code == 422
