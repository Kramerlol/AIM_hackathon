# app/parser.py
import re
import base64
from datetime import datetime

def _generate_id(prefix, index):
    return f"{prefix}-{index}"

def _extract_date(text, pattern):
    m = re.search(pattern, text)
    if m:
        return m.group(1).strip()
    return None

def parse_lab_report(text: str, request_data: dict):
    """
    Parse a lab report in Markdown format.
    Expected structure:
      - Lines before table contain patient info, sample taken, etc.
      - Table header: Test | Result | Unit | Reference range | LOINC code
      - Each subsequent row until 'Validated by' is a test result.
    Returns list of FHIR resources: Observation for each test + Provenance.
    """
    observations = []
    lines = text.strip().split("\n")

    # Extract sample taken datetime (for effectiveDateTime)
    sample_taken = None
    for line in lines:
        if line.startswith("Sample taken:"):
            sample_taken = line.split(":", 1)[1].strip()
            break
    # If not found, use reported time
    if not sample_taken:
        for line in lines:
            if line.startswith("Reported:"):
                sample_taken = line.split(":", 1)[1].strip()
                break

    # Convert to FHIR datetime (assuming format: "22 October 2026, 08:10")
    effective_dt = None
    if sample_taken:
        # Very simple conversion: keep as string if matches ISO, else we leave as provided
        # For prototype, we can use current time or try to parse with datetime
        # We'll use a placeholder: 2026-10-22T08:10:00Z (but dynamic)
        # Since we don't know exact format, we'll just set to now for demo
        # In real, you'd parse with dateutil
        effective_dt = datetime.utcnow().isoformat() + "Z"  # fallback
        # You can implement proper parsing later

    # Find table start
    in_table = False
    test_index = 0
    for line in lines:
        line = line.strip()
        if line.startswith("Test"):
            in_table = True
            continue
        if in_table and line and not line.startswith("Validated by"):
            # Split row by multiple spaces or tabs
            parts = re.split(r'\t+|\s{2,}', line)
            if len(parts) >= 5:
                test_name = parts[0].strip()
                result_str = parts[1].strip()
                unit = parts[2].strip() if len(parts) > 2 else ""
                ref_range = parts[3].strip() if len(parts) > 3 else ""
                loinc_code = parts[4].strip() if len(parts) > 4 else ""

                # Convert result to float if possible
                try:
                    value = float(result_str)
                except ValueError:
                    # Skip non‑numeric results for prototype (could handle strings later)
                    continue

                obs_id = _generate_id("obs", test_index + 1)
                test_index += 1

                observation = {
                    "resourceType": "Observation",
                    "id": obs_id,
                    "status": "final",
                    "code": {
                        "coding": [{
                            "system": "http://loinc.org",
                            "code": loinc_code,
                            "display": test_name
                        }]
                    },
                    "subject": {"reference": f"Patient/{request_data['patient_id']}"},
                    "effectiveDateTime": effective_dt,
                    "valueQuantity": {
                        "value": value,
                        "unit": unit,
                        "system": "http://unitsofmeasure.org",
                        "code": unit  # ideally map to UCUM, but for prototype we use same string
                    }
                }

                # Add reference range if present and parseable
                if ref_range:
                    m = re.match(r'([\d\.]+)\s*to\s*([\d\.]+)', ref_range)
                    if m:
                        observation["referenceRange"] = [{
                            "low": {"value": float(m.group(1))},
                            "high": {"value": float(m.group(2))}
                        }]

                observations.append(observation)

    if not observations:
        raise ValueError("No lab observations parsed from document.")

    # Create Provenance resource
    provenance = {
        "resourceType": "Provenance",
        "id": _generate_id("prov", 1),
        "target": [{"reference": f"Observation/{obs['id']}"} for obs in observations],
        "recorded": datetime.utcnow().isoformat() + "Z",
        "agent": [{
            "who": {"display": request_data["verified_identity"]["name"]},
            "onBehalfOf": {"display": request_data["verified_identity"]["org"]}
        }],
        "activity": {
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/v3-DataOperation",
                "code": "CREATE",
                "display": "create"
            }]
        }
    }

    return observations + [provenance]


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
        "type": {
            "coding": [{
                "system": "http://loinc.org",
                "code": "34111-5",
                "display": "Discharge summary"
            }]
        },
        "subject": {"reference": f"Patient/{request_data['patient_id']}"},
        "date": datetime.utcnow().isoformat() + "Z",  # could extract from report
        "content": [{
            "attachment": {
                "contentType": "text/markdown",
                "data": base64.b64encode(text.encode("utf-8")).decode("utf-8")
            }
        }]
    }

    provenance = {
        "resourceType": "Provenance",
        "id": _generate_id("prov", 2),
        "target": [{"reference": f"DocumentReference/{doc_id}"}],
        "recorded": datetime.utcnow().isoformat() + "Z",
        "agent": [{
            "who": {"display": request_data["verified_identity"]["name"]},
            "onBehalfOf": {"display": request_data["verified_identity"]["org"]}
        }],
        "activity": {
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/v3-DataOperation",
                "code": "CREATE",
                "display": "create"
            }]
        }
    }

    return [document_reference, provenance]
