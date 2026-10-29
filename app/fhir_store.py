# app/fhir_store.py
import httpx
import json

FHIR_BASE = "http://localhost:8080/fhir"   # adjust if running on Hetzner

async def store_resource(resource: dict) -> dict:
    """
    POST a single FHIR resource to the HAPI server.
    Returns the stored resource with server-assigned ID.
    """
    resource_type = resource["resourceType"]
    # Remove client-assigned id (if any) to let server assign its own
    resource.pop("id", None)
    async with httpx.AsyncClient() as client:
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
