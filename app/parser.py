# app/parser.py
import re
import base64
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

VIENNA = ZoneInfo("Europe/Vienna")
DATE_FORMATS = ("%d %B %Y, %H:%M", "%d %B %Y %H:%M", "%Y-%m-%dT%H:%M", "%d.%m.%Y %H:%M")

# The documents write units in plain text. UCUM needs 10*9/L, not 10^9/L.
UCUM = {"10^9/L": "10*9/L", "10^12/L": "10*12/L"}


def _generate_id(prefix, index):
    return f"{prefix}-{index}"


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _to_fhir_datetime(text):
    """'22 October 2026, 08:10' (Vienna time) -> '2026-10-22T08:10:00+02:00'. None if unreadable."""
    text = (text or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=VIENNA).isoformat(timespec="seconds")
        except ValueError:
            continue
    return None


def _header(lines, label):
    for line in lines:
        if line.lower().startswith(label.lower() + ":"):
            return line.split(":", 1)[1].strip()
    return None


def _table_rows(lines):
    """Yield the cells of each data row in a Markdown table (header and separator rows skipped)."""
    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and cells[0].lower() == "test":
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        yield cells


def _provenance(prov_id, targets, request_data):
    who = request_data["verified_identity"]
    method = who.get("method", "ID Austria (simulated), level substantial")
    return {
        "resourceType": "Provenance",
        "id": prov_id,
        "target": targets,
        "recorded": _now(),
        "activity": {"coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/v3-DataOperation",
            "code": "CREATE", "display": "create"}]},
        "agent": [
            {"type": {"coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/provenance-participant-type",
                "code": "author", "display": "Author"}]},
             "who": {"display": who["name"]},
             "onBehalfOf": {"display": who["org"]}},
            # how the identity was checked: the identity provider acts as verifier
            {"type": {"coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/provenance-participant-type",
                "code": "verifier", "display": "Verifier"}]},
             "who": {"display": method}},
        ],
    }


def parse_lab_report(text: str, request_data: dict):
    """
    Parse a lab report in Markdown format.
    Expected structure:
      - Header lines (Patient, Sample taken, Reported, ...)
      - A pipe table: Test | Result | Unit | Reference range | LOINC code
      - A closing 'Validated by' line.
    Returns a list of FHIR resources: one Observation per numeric test + a Provenance.
    Raises ValueError if nothing could be parsed.
    """
    lines = text.strip().split("\n")
    effective_dt = (_to_fhir_datetime(_header(lines, "Sample taken"))
                    or _to_fhir_datetime(_header(lines, "Reported")))
    if not effective_dt:
        raise ValueError("No readable 'Sample taken' or 'Reported' time in the document.")

    observations = []
    for cells in _table_rows(lines):
        if len(cells) < 5:
            continue
        test_name, result_str, unit, ref_range, loinc_code = cells[:5]
        if not re.fullmatch(r"\d{1,6}-\d", loinc_code):
            raise ValueError(f"'{test_name}' has no valid LOINC code.")
        try:
            value = float(result_str.replace(",", "."))
        except ValueError:
            raise ValueError(f"The result for '{test_name}' is not a number.")

        quantity = {"value": value}
        if unit:
            quantity.update({"unit": unit, "system": "http://unitsofmeasure.org",
                             "code": UCUM.get(unit, unit)})
        observation = {
            "resourceType": "Observation",
            "id": _generate_id("obs", len(observations) + 1),
            "status": "final",
            "category": [{"coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                "code": "laboratory", "display": "Laboratory"}]}],
            # No coding.display: it must equal the official LOINC term, which the document does not give.
            "code": {"coding": [{"system": "http://loinc.org", "code": loinc_code}], "text": test_name},
            "subject": {"reference": f"Patient/{request_data['patient_id']}"},
            "effectiveDateTime": effective_dt,
            "valueQuantity": quantity,
        }
        m = re.fullmatch(r"([\d.]+)\s*to\s*([\d.]+)", ref_range)
        if m:
            low, high = {"value": float(m.group(1))}, {"value": float(m.group(2))}
            if unit:
                for q in (low, high):
                    q.update({"unit": unit, "system": "http://unitsofmeasure.org",
                              "code": UCUM.get(unit, unit)})
            observation["referenceRange"] = [{"low": low, "high": high, "text": ref_range}]
        observations.append(observation)

    if not observations:
        raise ValueError("No lab observations parsed from document.")

    targets = [{"reference": f"Observation/{obs['id']}"} for obs in observations]
    return observations + [_provenance(_generate_id("prov", 1), targets, request_data)]


def parse_rehab_report(text: str, request_data: dict):
    """
    Parse a rehab discharge report (free text).
    Returns a DocumentReference containing the full text, plus Provenance.
    """
    doc_id = _generate_id("docref", 1)
    document_reference = {
        "resourceType": "DocumentReference",
        "id": doc_id,
        "status": "current",
        "type": {"coding": [{"system": "http://loinc.org", "code": "18842-5",
                             "display": "Discharge summary"}]},
        "subject": {"reference": f"Patient/{request_data['patient_id']}"},
        "date": _now(),
        "content": [{"attachment": {
            "contentType": "text/markdown",
            "data": base64.b64encode(text.encode("utf-8")).decode("utf-8"),
        }}],
    }
    return [document_reference,
            _provenance(_generate_id("prov", 2), [{"reference": f"DocumentReference/{doc_id}"}],
                        request_data)]
