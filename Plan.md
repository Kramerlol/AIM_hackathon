We're on Track 2: Health Data Interoperability. The goal is to build a service that bridges the Matrix‑based PGK network and outside parties (labs, rehab clinics, patients) by letting a doctor request a document, the outside person submits it via a browser link, and the system turns it into valid FHIR R4 resources with full audit and misdelivery detection. **You don't need to convert from HL7** – you are creating FHIR from raw documents (Markdown). The key challenges are:

1. **Identity verification** without accounts (simulate ID Austria)  
2. **Parsing Markdown** into structured FHIR (Observations with LOINC, DocumentReference)  
3. **Misdelivery detection** (comparing patient identity in document vs. request)  
4. **Audit logging** at six specific steps  
5. **Integration with Matrix** (bot) and **email/SMS** delivery (privacy‑preserving)

---

## Immediate Next Steps (before the hackathon officially starts)

### 1. Read the scenario files in your repository
The repository already contains everything you need to understand the expected data and tests. Run:

```bash
cd ~/hackathon/TRACK-2-interoperability   # or wherever you cloned it
cat scenario/README.md
cat scenario/patient.json
ls scenario/documents/
cat scenario/documents/*.md        # inspect each document
cat scenario/misdelivery.md
```

This will tell you:
- Who the people are (doctor, patient, outside persons)
- The exact format of the Markdown answers (so you can write a parser)
- The three misdelivery tests (what to look for)
- The command the jury will use for FHIR validation

### 2. Decide on a lightweight tech stack

Given your server (2 vCPU, 4 GB RAM) and the need for speed, I recommend:

| Component          | Choice                                                                 | Why                                                                 |
|--------------------|------------------------------------------------------------------------|---------------------------------------------------------------------|
| Web framework      | **Python + FastAPI**                                                   | Quick to develop, easy async, good for REST APIs                    |
| FHIR handling      | **`fhir.resources`** library (Python) + **HAPI FHIR server** in Docker | `fhir.resources` for validation and creation; HAPI for storage      |
| Database           | **SQLite** (for audit logs and request tracking)                       | Zero config, file‑based, perfect for single‑node demo               |
| Matrix bot         | **`matrix-nio`** Python library                                        | Simple bot that can listen and post to a room                      |
| Email/SMS sending  | **SendGrid** (email) and **Twilio** (SMS) – both free tiers            | Reliable, easy to set up; can be replaced with any other provider   |
| Identity simulation| **Mock ID Austria** web page (just a form)                              | No external dependency, you control the flow                        |
| Document parsing   | **Rule‑based parsing** (regex) for known Markdown structure + optional LLM for fallback | Keep deterministic for the provided scenario; LLM only if needed    |

### 3. Set up the development environment

- Create a Python virtual environment and install dependencies:
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  pip install fastapi uvicorn fhir.resources matrix-nio sendgrid twilio sqlite3
  ```
- Pull and run HAPI FHIR server (or use a free cloud FHIR server like `https://hapi.fhir.org/baseR4` for testing; but for your own deployment, use Docker):
  ```bash
  docker run -p 8080:8080 hapiproject/hapi:latest
  ```

---

## Architectural Blueprint

### High‑level flow

1. **Doctor (in Matrix)** sends a command to the bot, e.g.  
   `!request lab <outside_email_or_phone> <patient_id> <document_type>`
2. **Bot** creates a request record, generates a unique link, and sends an email or SMS to the outside person.  
   *Email/SMS contains **only** the link and a reference code – no patient name, DOB, or document type.*
3. **Outside person** opens the link in a browser. They are first asked to **verify their identity** using the mock ID Austria (e.g., enter a test user/password that maps to a known person/organisation).  
   - This proves they are who they claim to be (e.g., lab technician at “Labor Wien”).
   - After successful verification, the web page shows the request details (patient name, document type) and allows them to upload/paste the document (Markdown).
4. **Web app** receives the document, **parses it** into FHIR resources:
   - Lab results → multiple `Observation` resources with LOINC codes.
   - Rehab report → `DocumentReference` with the text attached (as `Binary` or inline).
   - Adds `Provenance` resource indicating the outside person, the identity check method, and timestamp.
5. **Misdelivery detection**: before filing, compare the patient identifier (name, DOB, etc.) extracted from the document with the patient in the request. If mismatch, flag and **do not file**; log audit and notify doctor.
6. **FHIR validation**: run each resource through the HL7 validator (or `fhir.resources` validation) to ensure 0 errors.
7. **Store** the validated resources on the FHIR server (HAPI) and **notify the doctor** via Matrix that the document is ready.
8. **Audit log**: record each of the six steps with who, what, when.

### Data model for audit (SQLite table)

```sql
CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL,
  event TEXT NOT NULL,           -- 'request_sent', 'link_opened', 'identity_checked', 'answer_sent', 'answer_filed', 'misdelivery_caught'
  actor TEXT,                    -- e.g., doctor email, outside person id, system
  details TEXT                   -- JSON with relevant ids
);
```

---

## Key Design Decisions (answer these in your README)

### How does an outside person prove who they are?
We simulate **ID Austria** (the Austrian national eID). The outside person is assumed to already have an ID Austria account. On the web page, they click “Login with ID Austria (simulated)”, enter a test user ID and password (e.g., `lab_wien` / `demo123`). The system then retrieves their verified identity (name, organisation) from a local mapping. This is analogous to how a real eID would provide a signed assertion.

**Why this is strong enough?**  
It provides authentication (something they know) and the identity is linked to a trusted national system (simulated). It avoids burdening the outside person with new accounts or app installations.

### Which identity check do you require for each document type?
- **Lab results** (highly sensitive, but often from a known lab): require ID Austria login (authentication) + that the authenticated person belongs to the expected organisation (e.g., the lab name provided by the doctor). This prevents a random person from submitting.
- **Rehab report** (also sensitive, but from a clinic): same level – ID Austria + organisation match.
- **In general**, we require **Level of Assurance “Substantial”** (equivalent to ID Austria), because health data is sensitive. The organisation match adds an extra layer.

### Which FHIR resources do you create?
- `Patient` (already provided)
- `Practitioner` (for the doctor, e.g., Dr. Lena Hofer)
- `Organization` (for the outside lab/clinic)
- `ServiceRequest` or `Task` (representing the doctor’s request – we use `Task` to track workflow)
- `Observation` (one per lab value, with LOINC code, value, unit, effective date)
- `DocumentReference` (for the rehab report, with `content.attachment.data` or a reference to a `Binary` resource containing the Markdown/text)
- `Provenance` (links the `Observation`/`DocumentReference` to the `Task`, the outside person (`Agent`), the identity check method, and timestamp)
- `AuditEvent` (optional, but we can also map audit logs to FHIR `AuditEvent` resources for completeness)

All resources reference the `Patient` via `subject` or `patient` fields.

### How do you notice a misdelivery?
- **Rule‑based extraction**: from the submitted Markdown, extract patient name, date of birth, or social security number (whatever is present). Compare with the `Patient` resource of the requested patient. If any mismatch → flag.
- **Additional checks**: if the document mentions a different patient ID or the outside person’s organisation is not the one expected for that request, also flag.
- The three provided misdelivery tests will guide the exact patterns to look for.

### Where does your service run?
- **At a third party** (cloud). It acts as a trusted intermediary between the Matrix network and outside organisations. This is realistic because the service needs to send emails/SMS and host a public web endpoint. The FHIR server can also be at the third party (or at the clinic). For the prototype, everything runs on your Hetzner server.

---

## Division of Labour (suggested)

| Team member      | Primary tasks                                                                 |
|------------------|-------------------------------------------------------------------------------|
| **Andrew**       | FHIR mapping and validation, backend logic (FastAPI endpoints), misdelivery detection, database integration |
| **Elena**        | Clinical input: ensure LOINC codes are correct, validate document parsing, define realistic identity requirements, help test with real‑world scenarios |
| **Marina**       | Identity simulation (mock ID Austria), security/privacy considerations, audit logging design, perhaps frontend of identity page |
| **Desislava**    | Frontend for outside person (upload page), Matrix bot integration, email/SMS sending setup |
| **Andrey**       | Matrix bot logic (listening to commands), deployment on Hetzner server, Docker setup for HAPI FHIR, overall integration |

You should all collaborate on the initial design and the README answers.

---

## Next Actions

1. **Read the scenario files now** – understand the exact format of the Markdown documents and the misdelivery tests.
2. **Set up the repository structure** (folders for `app/`, `bot/`, `fhir/`, `templates/`, etc.) and push an initial commit.
3. **Create a simple FastAPI app** with a health check and a dummy endpoint to test deployment on the server.
4. **Start building the FHIR parsing** using one sample document – convert it manually to `Observation`/`DocumentReference` and validate with `fhir.resources`.
5. **Set up the Matrix bot** using a test account and a room; get it to send a message.
6. **Implement the email/SMS sending** (choose provider, get API keys).

Once you have these building blocks, you can integrate them into the full flow.

If you need help with specific FHIR resource examples, the Markdown parsing, or the Matrix bot, let me know.