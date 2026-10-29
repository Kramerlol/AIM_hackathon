# app/main.py
import secrets
import datetime
import json
from typing import Optional

from fastapi import FastAPI, HTTPException, Form, Request, UploadFile, File, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from fhir_store import store_resources_with_provenance
from validator import validate_resources        # <-- ADD THIS IMPORT

from audit import log_audit, init_db
import parser

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
async def startup_event():
    init_db()

# ---------- In‑memory request store ----------
REQUESTS = {}

# ---------- Simulated ID Austria user database ----------
ID_AUSTRIA_USERS = {
    "eva.brandl": {"password": "demo123", "name": "Dr. Eva Brandl", "org": "Labor Kanalstraße"},
    "stefan.kern": {"password": "demo123", "name": "Stefan Kern", "org": "Reha Waldblick"},
}

# ---------- Helper functions ----------
def create_request(doctor: str, contact: str, patient_id: str, doc_type: str, recipient_name: str, recipient_org: str):
    token = secrets.token_urlsafe(16)
    REQUESTS[token] = {
        "doctor": doctor,
        "contact": contact,
        "patient_id": patient_id,
        "doc_type": doc_type,
        "recipient_name": recipient_name,
        "recipient_org": recipient_org,
        "status": "pending",
        "verified_identity": None
    }
    return token

def simulate_email(recipient: str, subject: str, body: str):
    print(f"[EMAIL] To: {recipient}\nSubject: {subject}\nBody: {body}")
    log_audit("email_sent", "system", {"to": recipient, "subject": subject})

def simulate_sms(phone: str, message: str):
    print(f"[SMS] To: {phone}\nMessage: {message}")
    log_audit("sms_sent", "system", {"to": phone})

class RequestCreate(BaseModel):
    doctor: str
    contact: str
    patient_id: str
    doc_type: str
    recipient_name: str
    recipient_org: str

# ---------- Endpoints ----------
@app.post("/request")
async def request_document(req: RequestCreate):
    token = create_request(req.doctor, req.contact, req.patient_id, req.doc_type, req.recipient_name, req.recipient_org)

    base_url = "http://localhost:8000"
    link = f"{base_url}/answer/{token}"

    if req.contact.startswith("+43"):
        message = f"Please answer the document request: {link}"
        simulate_sms(req.contact, message)
    else:
        subject = "Document Request"
        body = f"Please click this link to submit the requested document: {link}"
        simulate_email(req.contact, subject, body)

    log_audit("request_sent", req.doctor, {"token": token, "contact": req.contact})
    return {"token": token, "link": link}

@app.get("/answer/{token}", response_class=HTMLResponse)
async def answer_page(token: str, request: Request):
    if token not in REQUESTS:
        raise HTTPException(404, "Invalid or expired link")
    log_audit("link_opened", "unknown", {"token": token})
    return templates.TemplateResponse("identity.html", {"request": request, "token": token})

@app.post("/answer/{token}/verify")
async def verify_identity(token: str, username: str = Form(...), password: str = Form(...)):
    if token not in REQUESTS:
        raise HTTPException(404, "Invalid token")
    req_data = REQUESTS[token]

    user = ID_AUSTRIA_USERS.get(username)
    if not user or user["password"] != password:
        log_audit("identity_checked", username, {"token": token, "success": False})
        raise HTTPException(401, "Invalid credentials")

    if user["name"].lower() != req_data["recipient_name"].lower():
        log_audit("misdelivery_caught", user["name"], {"token": token, "reason": "identity_mismatch"})
        raise HTTPException(403, "You are not the intended recipient for this request.")

    log_audit("identity_checked", user["name"], {"token": token, "success": True})
    req_data["verified_identity"] = user
    return RedirectResponse(url=f"/submit/{token}", status_code=303)

@app.get("/submit/{token}", response_class=HTMLResponse)
async def submit_page(token: str, request: Request):
    if token not in REQUESTS or not REQUESTS[token]["verified_identity"]:
        raise HTTPException(403, "Identity not verified")
    req_data = REQUESTS[token]
    patient_name = "Maria Beispiel"
    return templates.TemplateResponse("submit.html", {
        "request": request,
        "token": token,
        "patient_name": patient_name,
        "doc_type": req_data["doc_type"]
    })

@app.post("/submit/{token}")
async def submit_document(
    token: str,
    patient_name: str = Form(...),
    patient_birthdate: str = Form(...),
    content: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None)
):
    if token not in REQUESTS or not REQUESTS[token]["verified_identity"]:
        raise HTTPException(403, "Identity not verified")
    req_data = REQUESTS[token]

    if file:
        doc_text = (await file.read()).decode("utf-8")
    elif content:
        doc_text = content
    else:
        raise HTTPException(400, "No document provided")

    # Level 1: Clinical and identity checks
    expected_patient_name = "Maria Beispiel"
    expected_birthdate = "1961-03-12"

    if patient_name.strip().lower() != expected_patient_name.lower() or patient_birthdate != expected_birthdate:
        log_audit("misdelivery_caught", req_data["verified_identity"]["name"], {
            "token": token,
            "reason": "patient_mismatch",
            "submitted_name": patient_name,
            "submitted_birthdate": patient_birthdate
        })
        return {"error": "The document is for a different patient. It has not been filed."}

    # Parse document
    try:
        if req_data["doc_type"] == "lab":
            fhir_resources = parser.parse_lab_report(doc_text, req_data)
        elif req_data["doc_type"] == "rehab":
            fhir_resources = parser.parse_rehab_report(doc_text, req_data)
        else:
            raise HTTPException(400, "Unsupported document type")
    except Exception as e:
        log_audit("parsing_error", req_data["verified_identity"]["name"], {"token": token, "error": str(e)})
        raise HTTPException(400, f"Failed to parse document: {str(e)}")

    # Level 2: Structured validation (already handled in parser, but can be extended)

    # Level 3: Official FHIR validation
    all_valid, validation_results = validate_resources(fhir_resources)
    if not all_valid:
        log_audit("validation_failed", "system", {"token": token, "results": validation_results})
        return {"error": "FHIR validation failed. Document not filed.", "details": validation_results}

    # Store resources on FHIR server
    try:
        stored_resources = await store_resources_with_provenance(fhir_resources, req_data)
    except Exception as e:
        log_audit("storage_error", "system", {"token": token, "error": str(e)})
        return {"error": f"Failed to store FHIR resources: {str(e)}"}

    log_audit("answer_filed", "system", {"token": token, "resource_count": len(stored_resources)})

    # Notify doctor via Matrix (stub for now)
    return {"success": True, "message": "Document submitted and filed."}
