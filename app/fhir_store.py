# app/fhir_store.py
import json
import os
from pathlib import Path

import httpx

FHIR_BASE = os.environ.get("FHIR_BASE", "http://localhost:8080/fhir")   # adjust if running on Hetzner
PATIENT_FILE = Path(__file__).resolve().parent.parent / "scenario" / "patient.json"


async def ensure_patient(patient_id: str) -> None:
    """The Observations point at Patient/<id>, so that Patient must exist on the server first."""
    patient = json.loads(PATIENT_FILE.read_text())
    if patient["id"] != patient_id:
        raise Exception(f"unknown patient {patient_id}")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.put(f"{FHIR_BASE}/Patient/{patient_id}", json=patient,
                                headers={"Content-Type": "application/fhir+json"})
        if resp.status_code not in (200, 201):
            raise Exception(f"FHIR patient upload failed ({resp.status_code}): {resp.text[:200]}")


async def store_with_patient(resources: list, patient_id: str):
    """Make sure the patient exists, then store the resources and link the Provenance to them."""
    await ensure_patient(patient_id)
    return await store_resources_with_provenance(resources, {"patient_id": patient_id})

async def store_resource(resource: dict) -> dict:
    """
    POST a single FHIR resource to the HAPI server.
    Returns the stored resource with server-assigned ID.
    """
    resource_type = resource["resourceType"]
    # Remove client-assigned id (if any) to let server assign its own
    resource.pop("id", None)
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{FHIR_BASE}/{resource_type}",
            json=resource,
            headers={"Content-Type": "application/fhir+json"}
        )
        if resp.status_code not in (200, 201):
            raise Exception(f"FHIR storage failed ({resp.status_code}): {resp.text}")
        return resp.json()

async def store_resources_with_provenance(resources: list, request_data: dict):
    """
    Store all resources, then update Provenance.target with actual IDs.
    Returns list of stored resources (with IDs).
    """
    stored = []
    # Separate Provenance from other resources
    non_prov = [r for r in resources if r["resourceType"] != "Provenance"]
    prov = [r for r in resources if r["resourceType"] == "Provenance"]

    # Store non-Provenance resources first
    for res in non_prov:
        stored_res = await store_resource(res)
        stored.append(stored_res)

    # Build target references from stored resources
    target_refs = []
    for res in stored:
        target_refs.append({"reference": f"{res['resourceType']}/{res['id']}"})

    # Store Provenance(s) with updated targets
    for p in prov:
        p["target"] = target_refs
        stored_prov = await store_resource(p)
        stored.append(stored_prov)

    return stored
