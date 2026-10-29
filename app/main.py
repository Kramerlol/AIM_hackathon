import os
from pathlib import Path

from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import mailer, sms
from .backend import IDENTITIES, get_backend
from .dates import normalise_date

BASE = Path(__file__).resolve().parent
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
MAX_UPLOAD = 200_000

app = FastAPI(title="Outside-person UI")
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET", "dev-only-secret"),
                   same_site="strict", max_age=3600)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")

DOC_LABELS = {"lab": "Lab result", "rehab": "Rehab discharge report"}


def render(request: Request, name: str, status_code: int = 200, **ctx):
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def failure(request: Request):
    """One neutral page for every failure: wrong person, bad, expired or used link."""
    return render(request, "failure.html", status_code=403)


def verified_identity(request: Request, token: str) -> str | None:
    return request.session.get("verified", {}).get(token)


@app.get("/r/{token}", response_class=HTMLResponse)
def landing(request: Request, token: str):
    info = get_backend().get_request(token)
    if not info:
        return failure(request)
    return render(request, "landing.html", token=token, code=info["code"])


@app.get("/r/{token}/identity", response_class=HTMLResponse)
def identity_form(request: Request, token: str):
    if not get_backend().get_context(token):
        return failure(request)
    return render(request, "identity.html", token=token, identities=IDENTITIES)


@app.post("/r/{token}/identity")
def identity_submit(request: Request, token: str, identity_id: str = Form(...)):
    if identity_id not in IDENTITIES or not get_backend().verify_identity(token, identity_id):
        return failure(request)
    verified = request.session.get("verified", {})
    verified[token] = identity_id
    request.session["verified"] = verified
    return RedirectResponse(f"/r/{token}/answer", status_code=303)


def answer_page(request: Request, token: str, status_code=200, error=None, values=None):
    ctx = get_backend().get_context(token)
    if not ctx:
        return failure(request)
    return render(request, "answer.html", status_code=status_code, token=token, error=error,
                  values=values or {}, doc_label=DOC_LABELS.get(ctx["doc_type"], "Document"),
                  requested_by=ctx["requested_by"], patient_hint=ctx["patient_hint"])


@app.get("/r/{token}/answer", response_class=HTMLResponse)
def answer_form(request: Request, token: str):
    if not verified_identity(request, token):
        return failure(request)
    return answer_page(request, token)


@app.post("/r/{token}/answer", response_class=HTMLResponse)
async def answer_submit(request: Request, token: str, patient_name: str = Form(""),
                        patient_birthdate: str = Form(""), source: str = Form("paste"),
                        content: str = Form(""), file: UploadFile | None = None):
    identity = verified_identity(request, token)
    if not identity:
        return failure(request)
    values = {"patient_name": patient_name, "patient_birthdate": patient_birthdate,
              "content": content, "source": source}

    iso_date = normalise_date(patient_birthdate)
    if not patient_name.strip() or not iso_date:
        return answer_page(request, token, 422, "Please enter the patient's full name and a "
                           "valid birth date, for example 12.03.1961.", values)

    text = content
    if source == "upload":
        raw = await file.read(MAX_UPLOAD + 1) if file else b""
        if len(raw) > MAX_UPLOAD:
            return answer_page(request, token, 413, "This file is too large.", values)
        text = raw.decode("utf-8", errors="replace")
    if not text.strip():
        return answer_page(request, token, 422, "Please add the document: upload a file or "
                           "paste the text.", values)

    result = get_backend().submit_answer(token, identity, patient_name.strip(), iso_date, text)
    status = result["status"]
    if status == "rejected":
        return answer_page(request, token, 422,
                           (result.get("message") or "We could not read this document.")
                           + " Check that the patient line and the results are present.", values)
    if status == "blocked":
        return failure(request)
    return render(request, "result.html", status=status, count=result.get("count"))


@app.get("/sms", response_class=HTMLResponse)
def sms_inbox(request: Request):
    return render(request, "sms.html", messages=sms.all_messages())


# --- development helpers: seeded demo requests and sending (remove when the real backend exists)
@app.get("/dev", response_class=HTMLResponse)
def dev(request: Request, sent: str | None = None, error: str | None = None):
    be = get_backend()
    return render(request, "dev.html", requests=list(be.requests.values()), base=BASE_URL,
                  audit=be.audit[-30:][::-1], notifications=be.notifications[::-1],
                  sent=sent, error=error)


@app.post("/dev/send/{token}")
def dev_send(token: str):
    req = get_backend().requests.get(token)
    if not req:
        return RedirectResponse("/dev", status_code=303)
    try:
        mailer.send_request(req.channel, req.recipient, f"{BASE_URL}/r/{token}", req.code)
    except OSError as exc:
        return RedirectResponse(f"/dev?error=Could not send: {exc}", status_code=303)
    return RedirectResponse(f"/dev?sent={req.code}", status_code=303)
