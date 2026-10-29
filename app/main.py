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

from audit import log_audit, init_db
import parser  # your parser.py module

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Initialize audit database on startup
@app.on_event("startup")
async def startup_event():
    init_db()

# ---------- In‑memory request store ----------
REQUESTS = {}

# ---------- Simulated ID Austria user database ----------
ID_AUSTRIA_USERS = {
    "eva.brandl": {"password": "demo123", "name": "Dr. Eva Brandl", "org": "Labor Kanalstraße"},
    "stefan.kern": {"password": "demo123", "name": "Stefan Kern", "org": "Reha Waldblick"},
    # Add more test users if needed
}

# ---------- Helper functions ----------
def create_request(doctor: str, contact: str, patient_id: str, doc_type: str, recipient_name: str, recipient_org: str):
    token = secrets.token_urlsafe(16)
    REQUESTS[token] = {
        "doctor": doctor,
        "contact": contact,
        "patient_id": patient_id,
        "doc_type": doc_type,          # "lab" or "rehab"
        "recipient_name": recipient_name,  # expected person's full name
        "recipient_org": recipient_org,
        "status": "pending",
        "verified_identity": None
    }
    return token

def simulate_email(recipient: str, subject: str, body: str):
    # In real prototype, send to Mailpit via SMTP; for now, just log
    print(f"[EMAIL] To: {recipient}\nSubject: {subject}\nBody: {body}")
    log_audit("email_sent", "system", {"to": recipient, "subject": subject})

def simulate_sms(phone: str, message: str):
    print(f"[SMS] To: {phone}\nMessage: {message}")
    log_audit("sms_sent", "system", {"to": phone})

# ---------- Pydantic models for request body ----------
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
    """
    Called by the Matrix bot to create a document request.
    Sends an email or SMS with a link (privacy‑preserving).
    """
    token = create_request(req.doctor, req.contact, req.patient_id, req.doc_type, req.recipient_name, req.recipient_org)

    # Build the link (adjust base URL when deployed)
    base_url = "http://localhost:8000"  # or your public server URL
    link = f"{base_url}/answer/{token}"

    # Determine contact method
    if req.contact.startswith("+43"):   # phone
        message = f"Please answer the document request: {link}"
        simulate_sms(req.contact, message)
    else:                               # email
        subject = "Document Request"
        body = f"Please click this link to submit the requested document: {link}"
        simulate_email(req.contact, subject, body)

    log_audit("request_sent", req.doctor, {"token": token, "contact": req.contact})
    return {"token": token, "link": link}

@app.get("/answer/{token}", response_class=HTMLResponse)
async def answer_page(token: str, request: Request):
    """
    Outside person opens the link. Shows identity verification page.
    """
    if token not in REQUESTS:
        raise HTTPException(404, "Invalid or expired link")
    log_audit("link_opened", "unknown", {"token": token})
    return templates.TemplateResponse("identity.html", {"request": request, "token": token})

@app.post("/answer/{token}/verify")
async def verify_identity(token: str, username: str = Form(...), password: str = Form(...)):
    """
    Identity check (mock ID Austria). On success, redirect to submission page.
    """
    if token not in REQUESTS:
        raise HTTPException(404, "Invalid token")
    req_data = REQUESTS[token]

    user = ID_AUSTRIA_USERS.get(username)
    if not user or user["password"] != password:
        log_audit("identity_checked", username, {"token": token, "success": False})
        raise HTTPException(401, "Invalid credentials")

    # Check that the authenticated person is the intended recipient
    if user["name"].lower() != req_data["recipient_name"].lower():
        # M1 or M2: someone else tried to answer
        log_audit("misdelivery_caught", user["name"], {"token": token, "reason": "identity_mismatch"})
        # Do not allow them to proceed
        raise HTTPException(403, "You are not the intended recipient for this request.")

    # Successful identity check
    log_audit("identity_checked", user["name"], {"token": token, "success": True})
    req_data["verified_identity"] = user
    # Redirect to submission page
    return RedirectResponse(url=f"/submit/{token}", status_code=303)

@app.get("/submit/{token}", response_class=HTMLResponse)
async def submit_page(token: str, request: Request):
    """
    Submission form for the outside person (after identity verified).
    """
    if token not in REQUESTS or not REQUESTS[token]["verified_identity"]:
        raise HTTPException(403, "Identity not verified")
    req_data = REQUESTS[token]
    # In a real system, patient name would be fetched from FHIR server;
    # for demo, we hardcode Maria Beispiel
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
    """
    Receives the document, performs checks, creates FHIR resources, and files them.
    """
    if token not in REQUESTS or not REQUESTS[token]["verified_identity"]:
        raise HTTPException(403, "Identity not verified")
    req_data = REQUESTS[token]

    # Obtain document text from either file upload or textarea
    if file:
        doc_text = (await file.read()).decode("utf-8")
    elif content:
        doc_text = content
    else:
        raise HTTPException(400, "No document provided")

    # --- Level 1: Clinical and identity checks ---
    # Hardcoded expected patient for demo; in production, retrieve from FHIR server using patient_id
    expected_patient_name = "Maria Beispiel"
    expected_birthdate = "1961-03-12"

    if patient_name.strip().lower() != expected_patient_name.lower() or patient_birthdate != expected_birthdate:
        # M3: wrong patient document
        log_audit("misdelivery_caught", req_data["verified_identity"]["name"], {
            "token": token,
            "reason": "patient_mismatch",
            "submitted_name": patient_name,
            "submitted_birthdate": patient_birthdate
        })
        # Notify doctor via Matrix (will be added later)
        # For now, just return error
        return {"error": "The document is for a different patient. It has not been filed."}

    # --- Parse document and generate FHIR resources ---
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

    # --- Level 2: Structured data validation (Pydantic could be used inside parser) ---
    # If parser returns None or raises, it's handled above.

    # --- Level 3: Official FHIR validation (stub) ---
    # For prototype, we skip running validator_cli.jar here but log that validation passed.
    # In final, run validate_fhir_resources(fhir_resources) and only file if no errors.
    validation_ok = True  # Placeholder
    if not validation_ok:
        log_audit("validation_failed", "system", {"token": token})
        return {"error": "FHIR validation failed. Document not filed."}

    # --- Store resources on FHIR server (stub) ---
    # For now, just log the resource count.
    # log_audit("answer_filed", "system", {"token": token, "resource_count": len(fhir_resources)})

    # Store resources on FHIR server
    try:
        stored_resources = await store_resources_with_provenance(fhir_resources, req_data)
    except Exception as e:
        log_audit("storage_error", "system", {"token": token, "error": str(e)})
        return {"error": f"Failed to store FHIR resources: {str(e)}"}
    
    log_audit("answer_filed", "system", {"token": token, "resource_count": len(stored_resources)})
    # Now the FHIR server will be populated.

    # --- Notify doctor via Matrix (stub) ---
    # In real integration, call a webhook or have bot poll.

    return {"success": True, "message": "Document submitted and filed."}
