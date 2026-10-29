import pytest
from fastapi.testclient import TestClient

from app import mailbox
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_mail_inbox_lists_messages_and_escapes(monkeypatch, client):
    monkeypatch.setattr(mailbox, "list_messages", lambda: [
        {"id": "abc", "to": "eva@x.example", "subject": "<b>Secure request</b>", "created": "10:00:00", "snippet": "hi"}])
    page = client.get("/mail").text
    assert "&lt;b&gt;Secure request" in page and '<a href="/mail/abc">' in page


def test_mail_inbox_explains_when_mailpit_is_down(monkeypatch, client):
    def down():
        raise mailbox.MailboxUnavailable("refused")
    monkeypatch.setattr(mailbox, "list_messages", down)
    r = client.get("/mail")
    assert r.status_code == 200 and "Mailpit is not reachable" in r.text


def test_mail_view_sandboxes_the_email(monkeypatch, client):
    monkeypatch.setattr(mailbox, "get_message", lambda i: {
        "id": i, "to": "eva@x.example", "subject": "S", "created": "10:00:00",
        "html": "<p onclick=\"x()\">Hello</p><script>alert(1)</script>", "text": ""})
    page = client.get("/mail/abc").text
    assert 'sandbox=""' in page and "<script>alert(1)" not in page  # escaped inside srcdoc
