
cat scenario/README.md

# Scenario

Everyone in this scenario is made up.

## The network

The closed network works like PGK: members are listed in a directory and only members can be reached. One member sends the requests:

| Member | Role | Matrix ID |
|---|---|---|
| Dr. Lena Hofer | Internal medicine, Klinikum Beispielstadt | `@lena.hofer:klinikum.example` |

Run one Matrix server for `klinikum.example`. You can add more members if you need them.

## Outside the network

These two people are not in the directory. Dr. Hofer only knows their name, role and one contact. The request is always for the named person. A colleague is not allowed to answer for them.

| Person | Role | Contact | Sends back |
|---|---|---|---|
| Dr. Eva Brandl | Lab physician at Labor KanalstraÃŸe, a lab that is not in the network | `eva.brandl@labor-kanal.example` (her personal work address) | Lab result |
| Stefan Kern | Discharge manager at Reha Waldblick, a rehab clinic | `+43 660 000 0101` | Rehab discharge report |

The `.example` addresses cannot receive mail and the phone number is made up. Do not send real email or SMS to them. Use a local mail catcher such as Mailpit, which accepts any address and a simulated SMS screen. Emails and SMS must not contain the patient's name, her birth date or what kind of document is requested.

## The patient

Maria Beispiel, born 12 March 1961, female. Her FHIR R4 Patient resource is in [`patient.json`](patient.json). Both requests are about her.

## Requests to run

1. Dr. Hofer asks Dr. Brandl for Maria's latest blood clotting tests before a planned procedure. Dr. Brandl answers with [`documents/lab-result-maria-beispiel.md`](documents/lab-result-maria-beispiel.md).
2. Dr. Hofer asks Stefan Kern for Maria's rehab discharge report. He answers with [`documents/rehab-report-maria-beispiel.md`](documents/rehab-report-maria-beispiel.md).

The outside person can upload the file or type the content into a form. That is up to you. A form must ask for the patient's name and birth date, so your service can check the answer is about the right patient. When testing, copy the name and birth date from the document file.

## Tools

- Matrix server: Synapse (`matrixdotorg/synapse` on Docker) or Conduit. Chat app: Element Web.
- FHIR server: HAPI FHIR (`hapiproject/hapi` on Docker) or the public test server `https://hapi.fhir.org/baseR4`. On the public server, give the patient your own ID so your data does not mix with other teams'.
- Email in tests: Mailpit (`axllent/mailpit` on Docker).
- SMS in tests: a page in your app that shows the SMS your service would send. A real SMS service is optional.
- FHIR validator: needs Java. Download `validator_cli.jar` from the releases of `hapifhir/org.hl7.fhir.core` on GitHub, then run `java -jar validator_cli.jar your-resource.json -version 4.0`.


cat scenario/patient.json
{
  "resourceType": "Patient",
  "id": "maria-beispiel",
  "identifier": [
    {
      "system": "urn:example:klinikum-beispielstadt:mrn",
      "value": "KB-000123"
    }
  ],
  "active": true,
  "name": [
    {
      "use": "official",
      "family": "Beispiel",
      "given": ["Maria"]
    }
  ],
  "telecom": [
    {
      "system": "phone",
      "value": "+43 660 000 0199",
      "use": "mobile"
    }
  ],
  "gender": "female",
  "birthDate": "1961-03-12",
  "address": [
    {
      "line": ["MusterstraÃŸe 1"],
      "city": "Beispielstadt",
      "postalCode": "1000",
      "country": "AT"
    }
  ],
  "managingOrganization": {
    "display": "Klinikum Beispielstadt"
  }
}


ls scenario/documents/


    Directory: C:\Users\krame\AIM_hackathon\TRACK-2-interoperability\scenario\documents


Mode                 LastWriteTime         Length Name
----                 -------------         ------ ----
-a----         29-Oct-26   6:27 PM            581 lab-result-maria-beispiel.md
-a----         29-Oct-26   6:27 PM            616 lab-result-max-beispiel.md
-a----         29-Oct-26   6:27 PM            972 rehab-report-maria-beispiel.md


cat scenario/documents/*.md
# Labor KanalstraÃŸe: lab report

Patient: Maria Beispiel, born 12 March 1961
Requested by: Dr. Lena Hofer, Klinikum Beispielstadt
Sample taken: 22 October 2026, 08:10
Reported: 22 October 2026, 11:40

| Test | Result | Unit | Reference range | LOINC code |
|---|---|---|---|---|
| INR (prothrombin time) | 1.0 | | 0.8 to 1.2 | 6301-6 |
| aPTT | 31 | s | 25 to 37 | 14979-9 |
| Platelets | 245 | 10^9/L | 150 to 400 | 777-3 |
| Fibrinogen | 3.1 | g/L | 2.0 to 4.0 | 3255-7 |

All values are within the reference range.

Validated by: Dr. Eva Brandl, lab physician
# Labor KanalstraÃŸe: lab report

Patient: Max Beispiel, born 1 January 1960
Requested by: Dr. Lena Hofer, Klinikum Beispielstadt
Sample taken: 22 October 2026, 08:25
Reported: 22 October 2026, 11:45

| Test | Result | Unit | Reference range | LOINC code |
|---|---|---|---|---|
| INR (prothrombin time) | 2.6 | | 0.8 to 1.2 | 6301-6 |
| aPTT | 44 | s | 25 to 37 | 14979-9 |
| Platelets | 198 | 10^9/L | 150 to 400 | 777-3 |
| Fibrinogen | 3.4 | g/L | 2.0 to 4.0 | 3255-7 |

INR and aPTT are raised, as expected under anticoagulation with phenprocoumon.

Validated by: Dr. Eva Brandl, lab physician
# Reha Waldblick: discharge report

Patient: Maria Beispiel, born 12 March 1961
Stay: 2 to 23 September 2026
Reason: rehabilitation after a total hip replacement on the left, on 18 August 2026 at Klinikum Beispielstadt

## Course

On arrival, Maria walked with two crutches. After three weeks of physiotherapy she walks up to 500 metres without aids and climbs stairs with a handrail. The wound healed without problems. There were no falls.

## Medication at discharge

- Rivaroxaban 10 mg once a day until 29 September 2026, to prevent thrombosis for six weeks after the operation
- Paracetamol 500 mg up to three times a day if needed
- Pantoprazole 20 mg once a day

## Recommendations

- Continue the home exercises.
- Outpatient physiotherapy twice a week for six weeks.
- Follow-up X-ray at Klinikum Beispielstadt in November 2026.

Written by: Dr. Johanna Leitner, medical director, Reha Waldblick
Sent by: Stefan Kern, discharge management


cat scenario/misdelivery.md
# Misdelivery tests

Run all three. A test counts as caught if its "Caught if" condition holds and your service writes the event to the audit log. Run them on request 1, with Dr. Brandl, who is reached by email.

## M1: Wrong address

Dr. Hofer types Dr. Brandl's address with a capital I instead of a lowercase l: `eva.brandl@labor-kanaI.example`. Someone who is not Dr. Brandl opens the email, clicks the link and tries to answer.

Caught if: that person cannot see the patient or the type of document, cannot answer and the failed identity check is in the audit log.

## M2: Forwarded request

Dr. Brandl forwards the email to a colleague, `kollege@labor-kanal.example`, who tries to answer it.

Caught if: the colleague's answer is not filed. Your service either blocks it or shows it to Dr. Hofer clearly marked as sent by someone other than Dr. Brandl.

## M3: Wrong patient

Dr. Brandl answers the request about Maria Beispiel with [`documents/lab-result-max-beispiel.md`](documents/lab-result-max-beispiel.md), a result for Max Beispiel, born 1 January 1960.

Caught if: Dr. Hofer is told about the mismatch in her Matrix room and the result is not filed for Maria.