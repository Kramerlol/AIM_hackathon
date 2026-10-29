# Outside-person UI, email/SMS and Matrix bot: spec

Owner: Desislava. Track 2 (Health Data Interoperability).
Scope: everything the outside person sees, the messages that reach them, and the Matrix bot Dr. Hofer uses.
Out of scope (other owners): FHIR mapping and validation, identity logic and audit storage, parser rules and LOINC, Docker/infra.

## 1. Goals and metrics this slice carries

- Effort for the outside person: 0 installs, 0 accounts, under 2 minutes from opening the link to sending.
- M1 (wrong address): an unverified or wrong person sees no patient data and no document type.
- M2 (forwarded): a different person cannot file an answer. Dr. Hofer is told.
- M3 (wrong patient): Dr. Hofer is told in Matrix. UI shows a neutral result to the sender.
- Emails and SMS never contain the patient's name, birth date or the document type.

## 2. Stack

- FastAPI + Jinja2 server-rendered templates, one CSS file, a few lines of vanilla JS. No React, no build step.
- Optional: HTMX (one script tag) for the result without page reload.
- Email: `smtplib` to Mailpit (`localhost:1025`; web UI on 8025).
- SMS: no provider. The service stores each SMS in a table and shows them at `/sms`.
- Matrix bot: `matrix-nio`.
- English only. Mobile-friendly, single column, large buttons.

## 3. Decisions made in the interview

| Topic | Decision |
|---|---|
| Patient name on the page | After identity check, show a partial hint only (initials + birth year, e.g. "M. B., born 1961"). Before identity: nothing. Sender types the full name and birth date from their own document; both are checked against the request. |
| Document type on the page | Shown only after a successful identity check. |
| Input | File upload (`.md`, `.txt`) and a paste box. |
| Failed identity (M1, M2) | One neutral message for every cause. No hint about what was wrong. |
| Forwarded answer (M2) | Block, log `misdelivery_caught`, notify Dr. Hofer in Matrix. Not filed. |
| Review step | None. Submit, then a result screen. |
| Link validity | 7 days. Closed after one successful answer. Failed attempts are logged and do not use up the link. |
| Mock ID Austria | Pick a test identity from a list. Clearly labelled SIMULATION. |
| Rehab identity | Must be Stefan Kern, the named recipient. "Written by" (Dr. Leitner) is stored as the author, not checked. |
| SMS display | One shared inbox page `/sms`. |
| Bot command | One command with named fields. |
| Matrix messages | Full clinical detail (Hofer is inside the closed network). |
| Language | English. |
| Visual polish | Clean and simple. |
| Priority if time is short | Pages + email, then bot, then SMS page. |

## 4. Screens

All pages: single column, max width ~640px, readable at 360px width, large touch targets, a visible "Prototype" note.

### 4.1 Landing `GET /r/{token}`
- Shows: a neutral heading ("A document has been requested from you"), a "Log in with ID Austria (simulated)" button, a short note that no account or install is needed.
- Must not show: patient, document type, requester name, organisation.
- Unknown, expired or used token: the same neutral failure screen as 4.5 (do not reveal which).
- Writes audit `link_opened` (backend).

### 4.2 Mock ID Austria `GET/POST /r/{token}/identity`
- Banner: "SIMULATION: this stands in for ID Austria."
- List of test identities, one click each:
  - Dr. Eva Brandl, Labor Kanalstrasse (correct for request 1)
  - Colleague (kollege@labor-kanal.example) (M2)
  - Stefan Kern, Reha Waldblick (correct for request 2)
  - Unknown person (M1)
- POST sends the chosen identity. Backend decides pass or fail and writes audit `identity_checked`.
- Pass: set a session cookie, redirect to 4.3. Fail: 4.5.

### 4.3 Answer page `GET /r/{token}/answer` (requires verified session)
- Shows: document type (e.g. "Lab result"), requested by (Dr. Lena Hofer, Klinikum Beispielstadt), the patient hint ("M. B., born 1961").
- Fields:
  - Patient full name (required, text).
  - Patient birth date (required; text with placeholder `DD.MM.YYYY` or `YYYY-MM-DD`; the server normalises).
  - Document: tabs or toggle "Upload file" / "Paste text". Only the active one is sent.
- One button "Send". Disable it after the click to avoid double submits.
- No session: redirect to the neutral failure screen.

### 4.4 Result `POST /r/{token}/answer`
Outcomes returned by the backend and the sender-facing text:

| Backend status | Sender sees |
|---|---|
| `filed` | "Thank you. Your answer was received." Optionally a count ("4 values received"). No patient data repeated. |
| `rejected` (unreadable) | "We could not read this document." Plus a short hint: check that the patient line and the results table are present. Form stays filled. |
| `mismatch` (M3) | "The document does not match the request, so it was not sent on." No detail about the expected patient. |
| `blocked` (M2) | The neutral failure message (4.5). |

### 4.5 Neutral failure
Single text: "We could not verify that you are the intended recipient." No reason, no patient data. Same text for wrong address, wrong person, expired and used links.

### 4.6 SMS inbox `GET /sms`
- Table: time, recipient number, message text, link (clickable).
- Newest first. Auto-refresh every few seconds (small JS or HTMX).
- Banner: "Simulated SMS: nothing is really sent."

## 5. Email and SMS content

Both contain only a link and a reference code. Never: patient name, birth date, document type, requester's patient list.

Email (to Dr. Brandl):
- Subject: `Secure request, ref {code}`
- Body: "You have a secure request. Open this link to answer: {url}. Reference: {code}. If you did not expect this, ignore this message."
- From: `noreply@pgk-bridge.example`

SMS (to Stefan Kern):
- `Secure request, ref {code}: {url}`

Reference code: short and unguessable enough to avoid enumeration (e.g. 8 characters). The token in the URL is long and random (the code is for the doctor's records and phone support, not for authentication).

## 6. Matrix bot (second priority)

### 6.1 Request command
```
!request lab patient=maria-beispiel to=eva.brandl@labor-kanal.example person="Dr. Eva Brandl" org="Labor Kanalstrasse"
!request rehab patient=maria-beispiel to=+436600000101 person="Stefan Kern" org="Reha Waldblick"
```
- `to` containing `@` means email, otherwise SMS.
- The bot calls `POST /requests`, then replies in the room: "Request {code} sent to {person} by {channel}."
- Parse errors: reply with usage help, never crash.
- Only members of the configured room can issue commands.

### 6.2 Notifications to the room (full clinical detail)
- Filed: patient name, document type, sender and identity method, number of resources, link to the FHIR resources.
- Mismatch (M3): "Result for {document patient} was submitted for the request about {requested patient}. Not filed." Include sender and time.
- Blocked (M1/M2): "A failed identity check for request {code}: {identity attempted}. Nothing was filed."
- Rejected (unreadable): "{person} submitted an unreadable document for request {code}."

## 7. Backend contract needed from the team

Agree these before building; stub them meanwhile.

- `GET /r/{token}` returns `{status, channel}` only. No patient data.
- `POST /r/{token}/identity` body `{identity_id}` returns `{ok}` and sets the session.
- `GET /r/{token}/context` (verified session only) returns `{doc_type, requested_by, patient_hint}`.
- `POST /r/{token}/answer` body `{patient_name, patient_birthdate, markdown}` returns `{status: filed|rejected|mismatch|blocked, message?, count?}`.
- `POST /requests` body `{patient_id, doc_type, recipient, channel, person, org, matrix_user, room_id}` returns `{request_id, code, url}`.
- `notify_doctor(request_id, message)` is called by the backend, or the bot subscribes to events.
- Audit: backend writes `request_sent`, `link_opened`, `identity_checked`, `answer_sent`, `answer_filed`, `misdelivery_caught`. UI only triggers them through these endpoints.

## 8. Open points for the team

- Marina: confirm the mock identity list and how a mock identity maps to the expected person and organisation.
- Andrew/Elena: parser tolerance for varied documents; the exact `rejected` reasons.
- Andrey: ports and service names for Mailpit, Synapse, Element, HAPI.
- Whether `session` is a signed cookie or a server-side session table.

## 9. Build order

1. Contracts file `contracts/api.md` agreed with the team; a stub API returning fixed JSON.
2. Landing, mock login, answer page, result screens against the stub.
3. Email function via Mailpit; test with `docker run axllent/mailpit`.
4. Swap the stub for the real backend; run request 1 end to end.
5. Matrix bot command and notifications.
6. SMS inbox page; run request 2.

## 10. Tests for this slice

- Landing with a valid token reveals nothing about the patient or document (check page source too, not only visible text).
- Answer page without a verified session redirects to the neutral failure.
- M1: log in as "Unknown person". Neutral failure; no patient or document type anywhere in the HTML.
- M2: log in as the colleague. Neutral failure; Hofer gets a Matrix message.
- M3: Brandl submits the Max document. Result is "mismatch"; Hofer is told in Matrix.
- Email and SMS bodies contain no name, birth date or document type (assert on the raw message).
- Time a new person from opening the email to the result screen: under 2 minutes.
- Pages work at 360px width and without JavaScript for the main flow.
