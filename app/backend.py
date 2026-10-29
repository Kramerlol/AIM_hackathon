"""Backend interface used by the web pages.

The pages only call the functions on `backend` below. Today they are answered by
StubBackend (in memory, fake rules). When the real backend exists, write an
HttpBackend with the same methods and change `get_backend()`.
"""
import json
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import notify

PATIENT_FILE = Path(__file__).resolve().parent.parent / "scenario" / "patient.json"

IDENTITIES = {
    "brandl": {"label": "Dr. Eva Brandl", "detail": "Lab physician, Labor Kanalstrasse"},
    "colleague": {"label": "Colleague", "detail": "kollege@labor-kanal.example"},
    "kern": {"label": "Stefan Kern", "detail": "Discharge manager, Reha Waldblick"},
    "stranger": {"label": "Unknown person", "detail": "Not listed anywhere"},
}

LINK_VALID_DAYS = 7

MATRIX_USERS = {"@lena.hofer:klinikum.example": "Dr. Lena Hofer, Klinikum Beispielstadt"}


def lookup_patient(patient_id: str):
    """Stub patient registry: the scenario's Patient resource. The real system asks the FHIR server."""
    data = json.loads(PATIENT_FILE.read_text())
    if patient_id != data["id"]:
        return None
    name = data["name"][0]
    return {"name": " ".join(name["given"] + [name["family"]]), "birthdate": data["birthDate"]}


def identity_for(person: str):
    """Map a person's name to a mock identity. The real ID Austria check compares verified names."""
    norm = lambda t: re.sub(r"^dr\.?\s+", "", t.strip().lower())
    for key, ident in IDENTITIES.items():
        if norm(ident["label"]) == norm(person):
            return key
    return None


@dataclass
class Request:
    token: str
    code: str
    patient_name: str
    patient_birthdate: str  # ISO
    doc_type: str  # "lab" | "rehab"
    channel: str  # "email" | "sms"
    recipient: str
    expected_identity: str
    requested_by: str
    org: str = ""
    room_id: str | None = None
    created: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    used: bool = False


class StubBackend:
    def __init__(self):
        self.requests: dict[str, Request] = {}
        self.audit: list[dict] = []
        self.notifications: list[str] = []
        self.seed()

    def seed(self):
        self.create_request(
            patient_name="Maria Beispiel", patient_birthdate="1961-03-12", doc_type="lab",
            channel="email", recipient="eva.brandl@labor-kanal.example",
            expected_identity="brandl", token="demo-lab-brandl",
        )
        self.create_request(
            patient_name="Maria Beispiel", patient_birthdate="1961-03-12", doc_type="rehab",
            channel="sms", recipient="+43 660 000 0101",
            expected_identity="kern", token="demo-rehab-kern",
        )

    # --- helpers -----------------------------------------------------------
    def _log(self, event, actor, req, **details):
        self.audit.append({
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "event": event, "actor": actor, "request": req.code if req else None, "details": details,
        })

    def _valid(self, token):
        req = self.requests.get(token)
        if not req or req.used:
            return None
        if datetime.now(timezone.utc) - req.created > timedelta(days=LINK_VALID_DAYS):
            return None
        return req

    # --- interface ---------------------------------------------------------
    def create_request(self, *, patient_name, patient_birthdate, doc_type, channel, recipient,
                       expected_identity, requested_by="Dr. Lena Hofer, Klinikum Beispielstadt",
                       org="", room_id=None, token=None):
        token = token or secrets.token_urlsafe(24)
        req = Request(token=token, code=secrets.token_hex(4).upper(), patient_name=patient_name,
                      patient_birthdate=patient_birthdate, doc_type=doc_type, channel=channel,
                      recipient=recipient, expected_identity=expected_identity,
                      requested_by=requested_by, org=org, room_id=room_id)
        self.requests[token] = req
        return {"token": token, "code": req.code}

    def mark_sent(self, token):
        """Call after the email or SMS was really handed over, so the audit entry is true."""
        req = self.requests[token]
        self._log("request_sent", req.requested_by, req, channel=req.channel)

    def _notify(self, req, text):
        self.notifications.append(text)
        notify.notify_doctor(req.room_id, text)

    def get_request(self, token):
        """Landing page data. Never contains patient data."""
        req = self._valid(token)
        if not req:
            return None
        self._log("link_opened", "unknown", req)
        return {"channel": req.channel, "code": req.code}

    def verify_identity(self, token, identity_id):
        req = self._valid(token)
        if not req:
            return False
        ok = identity_id == req.expected_identity
        self._log("identity_checked", identity_id, req, ok=ok)
        if not ok:
            self._log("misdelivery_caught", identity_id, req, reason="identity mismatch")
            who = IDENTITIES.get(identity_id, {"label": identity_id, "detail": ""})
            self._notify(req, f"Failed identity check for request {req.code}: {who['label']} "
                              f"({who['detail']}) tried to answer. Nothing was filed.")
        return ok

    def get_context(self, token):
        req = self._valid(token)
        if not req:
            return None
        parts = req.patient_name.split()
        hint = f"{parts[0][0]}. {parts[-1][0]}., born {req.patient_birthdate[:4]}"
        return {"doc_type": req.doc_type, "requested_by": req.requested_by, "patient_hint": hint}

    def submit_answer(self, token, identity_id, patient_name, patient_birthdate, markdown):
        """Stub rules only: the real parser and FHIR mapping replace this."""
        req = self._valid(token)
        if not req or identity_id != req.expected_identity:
            return {"status": "blocked"}
        self._log("answer_sent", identity_id, req)
        m = re.search(r"^Patient:\s*(.+?),\s*born\s+(.+?)\s*$", markdown, re.M)
        if not m:
            self._notify(req, f"Request {req.code}: {IDENTITIES[identity_id]['label']} submitted a "
                              "document that could not be read. Nothing was filed.")
            return {"status": "rejected",
                    "message": "We could not find the patient line in this document."}
        doc_name = m.group(1).strip()
        rows = re.findall(r"^\|.*\|\s*\d[\d-]*-\d\s*\|\s*$", markdown, re.M) if req.doc_type == "lab" else []
        if req.doc_type == "lab" and not rows:
            self._notify(req, f"Request {req.code}: {IDENTITIES[identity_id]['label']} submitted a "
                              "document that could not be read. Nothing was filed.")
            return {"status": "rejected", "message": "We could not find a results table."}
        typed_ok = patient_name.strip().lower() == req.patient_name.lower() \
            and patient_birthdate == req.patient_birthdate
        doc_ok = doc_name.lower() == req.patient_name.lower() and _birth_matches(m.group(2), req)
        if not (typed_ok and doc_ok):
            self._log("misdelivery_caught", identity_id, req, reason="patient mismatch")
            self._notify(req, f"Request {req.code}: a result for {doc_name} was submitted for the "
                              f"request about {req.patient_name}. Not filed. "
                              f"Sender: {IDENTITIES[identity_id]['label']}.")
            return {"status": "mismatch"}
        req.used = True
        self._log("answer_filed", identity_id, req, resources=len(rows) or 1)
        self._notify(req, f"{req.patient_name}: {'lab result' if req.doc_type == 'lab' else 'rehab report'} "
                          f"filed (request {req.code}). {len(rows) or 1} resource(s). "
                          f"Sender: {IDENTITIES[identity_id]['label']} (ID Austria, simulated).")
        return {"status": "filed", "count": len(rows) or None}


def _birth_matches(text, req):
    try:
        return datetime.strptime(text.strip(), "%d %B %Y").date().isoformat() == req.patient_birthdate
    except ValueError:
        return False


_backend = StubBackend()


def get_backend():
    return _backend
