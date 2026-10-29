"""Create a request and send the link. Used by the Matrix bot and POST /requests."""
import os

from . import mailer
from .backend import MATRIX_USERS, get_backend, identity_for, lookup_patient

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
KINDS = {"lab": "lab", "rehab": "rehab"}


class RequestError(ValueError):
    """The request cannot be made. The message is safe to show to the doctor."""


def create_and_send(*, kind, patient_id, to, person, org="", room_id=None, matrix_user=None):
    if kind not in KINDS:
        raise RequestError(f"Unknown document type '{kind}'. Use lab or rehab.")
    patient = lookup_patient(patient_id)
    if not patient:
        raise RequestError(f"Unknown patient '{patient_id}'.")
    if not to.strip() or not person.strip():
        raise RequestError("Both 'to' and 'person' are required.")
    # No check that the address looks right: a mistyped address is exactly what must be caught later.
    channel = "email" if "@" in to else "sms"
    be = get_backend()
    created = be.create_request(
        patient_name=patient["name"], patient_birthdate=patient["birthdate"], doc_type=kind,
        channel=channel, recipient=to.strip(), expected_identity=identity_for(person) or "nobody",
        requested_by=MATRIX_USERS.get(matrix_user, matrix_user or "Dr. Lena Hofer, Klinikum Beispielstadt"),
        org=org, room_id=room_id, patient_id=patient_id)
    url = f"{BASE_URL}/r/{created['token']}"
    mailer.send_request(channel, to.strip(), url, created["code"])  # raises OSError if it fails
    be.mark_sent(created["token"])
    return {"code": created["code"], "channel": channel, "url": url}
