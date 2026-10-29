import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import backend, fhir_store, parser, validator
from app.main import app

REAL_AVAILABLE = validator.validator_available  # the shared fixture switches it off; some tests need it
DOCS = Path(__file__).resolve().parent.parent / "scenario" / "documents"
RD = {"patient_id": "maria-beispiel", "verified_identity": {"name": "Dr. Eva Brandl", "org": "Labor Kanalstrasse"}}


def doc(name):
    return (DOCS / name).read_text()


def test_lab_report_becomes_four_observations_and_a_provenance():
    out = parser.parse_lab_report(doc("lab-result-maria-beispiel.md"), RD)
    obs = [r for r in out if r["resourceType"] == "Observation"]
    assert [o["code"]["coding"][0]["code"] for o in obs] == ["6301-6", "14979-9", "777-3", "3255-7"]
    assert all(o["subject"]["reference"] == "Patient/maria-beispiel" for o in obs)
    assert obs[0]["effectiveDateTime"] == "2026-10-22T08:10:00+02:00"  # sample time, Vienna
    assert obs[0]["valueQuantity"] == {"value": 1.0}                   # INR has no unit
    assert obs[2]["valueQuantity"]["code"] == "10*9/L"                 # UCUM, not 10^9/L
    assert obs[1]["referenceRange"][0]["low"]["value"] == 25
    prov = out[-1]
    assert prov["resourceType"] == "Provenance" and len(prov["target"]) == 4
    roles = [a["type"]["coding"][0]["code"] for a in prov["agent"]]
    assert roles == ["author", "verifier"] and "ID Austria" in prov["agent"][1]["who"]["display"]
    assert prov["recorded"]


def test_rehab_report_becomes_a_document_reference_with_the_text():
    text = doc("rehab-report-maria-beispiel.md")
    ref, prov = parser.parse_rehab_report(text, RD)
    assert ref["resourceType"] == "DocumentReference"
    assert ref["type"]["coding"][0]["code"] == "18842-5"
    assert base64.b64decode(ref["content"][0]["attachment"]["data"]).decode() == text
    assert prov["target"] == [{"reference": f"DocumentReference/{ref['id']}"}]


@pytest.mark.parametrize("bad", [
    "# report\nPatient: Maria Beispiel, born 12 March 1961\nSample taken: 22 October 2026, 08:10\n",
    "Sample taken: 22 October 2026, 08:10\n| Test | Result | Unit | Reference range | LOINC code |\n|---|---|---|---|---|\n| X | high | | | 6301-6 |\n",
    "Sample taken: 22 October 2026, 08:10\n| Test | Result | Unit | Reference range | LOINC code |\n|---|---|---|---|---|\n| X | 1.0 | | | none |\n",
    "| Test | Result | Unit | Reference range | LOINC code |\n|---|---|---|---|---|\n| X | 1.0 | | | 6301-6 |\n",
])
def test_unusable_lab_documents_are_refused(bad):
    with pytest.raises(ValueError):
        parser.parse_lab_report(bad, RD)


@pytest.mark.skipif(not REAL_AVAILABLE(), reason="validator_cli.jar not downloaded")
def test_resources_pass_the_hl7_validator_with_zero_errors(monkeypatch):
    monkeypatch.setattr(validator, "validator_available", REAL_AVAILABLE)
    for fn, name in [(parser.parse_lab_report, "lab-result-maria-beispiel.md"),
                     (parser.parse_rehab_report, "rehab-report-maria-beispiel.md")]:
        ok, result = validator.validate_resources(fn(doc(name), RD))
        assert ok and result["errors"] == 0, result["output"]


def test_validator_fails_closed_when_the_jar_is_missing(monkeypatch):
    monkeypatch.setattr(validator, "validator_available", REAL_AVAILABLE)
    monkeypatch.setattr(validator, "VALIDATOR_JAR", "/nonexistent.jar")
    ok, result = validator.validate_resources([{"resourceType": "Patient"}])
    assert not ok and "not found" in result["output"]


# --- live mode with the validator and the FHIR server replaced by fakes ----------------------------
LAB = "demo-lab-brandl"


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(backend, "_backend", backend.StubBackend())
    monkeypatch.setattr(backend, "FHIR_MODE", "live")
    monkeypatch.setattr(validator, "validator_available", lambda: True)
    state = {"stored": []}

    async def fake_store(resources, patient_id):
        state["stored"] = resources
        return [{"resourceType": r["resourceType"], "id": str(i)} for i, r in enumerate(resources)]
    monkeypatch.setattr(fhir_store, "store_with_patient", fake_store)
    state["valid"] = (True, {"errors": 0, "output": ""})
    monkeypatch.setattr(validator, "validate_resources", lambda res: state["valid"])
    return state


def file_lab(client):
    client.post(f"/r/{LAB}/identity", data={"identity_id": "brandl"})
    return client.post(f"/r/{LAB}/answer", data={
        "patient_name": "Maria Beispiel", "patient_birthdate": "12.03.1961", "source": "paste",
        "content": doc("lab-result-maria-beispiel.md")})


def events():
    from app import audit
    return [e["event"] for e in audit.read_log(100)]


def test_live_mode_validates_then_stores_then_reports_filed(live):
    r = file_lab(TestClient(app))
    assert "Thank you" in r.text and len(live["stored"]) == 5
    assert "answer_filed" in events()
    be = backend.get_backend()
    assert "validated" in be.notifications[-1] and "5 resources" in be.notifications[-1]


def test_live_mode_does_not_file_invalid_resources(live):
    live["valid"] = (False, {"errors": 2, "output": "bad"})
    r = file_lab(TestClient(app))
    assert "could not save" in r.text and live["stored"] == []
    assert "validation_failed" in events() and "answer_filed" not in events()
    assert "could not be filed" in backend.get_backend().notifications[-1]
    # the link is not used up: the sender can try again
    assert backend.get_backend().requests[LAB].used is False


def test_live_mode_reports_a_fhir_server_failure(live, monkeypatch):
    async def down(resources, patient_id):
        raise Exception("connection refused")
    monkeypatch.setattr(fhir_store, "store_with_patient", down)
    r = file_lab(TestClient(app))
    assert "could not save" in r.text
    assert "filing_failed" in events() and "answer_filed" not in events()


def test_wrong_patient_never_reaches_the_validator_or_the_store(live):
    client = TestClient(app)
    client.post(f"/r/{LAB}/identity", data={"identity_id": "brandl"})
    r = client.post(f"/r/{LAB}/answer", data={
        "patient_name": "Maria Beispiel", "patient_birthdate": "12.03.1961", "source": "paste",
        "content": doc("lab-result-max-beispiel.md")})  # typed details are Maria's, document is Max's
    assert "does not match" in r.text and live["stored"] == []
    assert "misdelivery_caught" in events()
