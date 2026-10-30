import streamlit as st
import httpx
import sqlite3
import pandas as pd

FHIR_BASE = "http://localhost:8080/fhir"   # adjust if needed
AUDIT_DB = "audit.db"                      # path to SQLite audit database

st.set_page_config(page_title="Patient Summary", layout="wide")
st.title("Patient Summary: Maria Beispiel")

# --- FHIR Observations ---
st.subheader("Lab Results")
try:
    resp = httpx.get(f"{FHIR_BASE}/Observation", params={"subject": "Patient/maria-beispiel"})
    resp.raise_for_status()
    entries = resp.json().get("entry", [])
    rows = []
    for entry in entries:
        obs = entry["resource"]
        code = obs.get("code", {}).get("text", "")
        value = obs.get("valueQuantity", {}).get("value")
        unit = obs.get("valueQuantity", {}).get("unit", "")
        ref_range = obs.get("referenceRange", [{}])[0].get("text", "")
        rows.append({"Test": code, "Value": value, "Unit": unit, "Ref. Range": ref_range})
    if rows:
        st.table(pd.DataFrame(rows))
    else:
        st.info("No observations found.")
except Exception as e:
    st.error(f"Could not fetch FHIR data: {e}")

# --- DocumentReferences ---
st.subheader("Documents")
try:
    resp = httpx.get(f"{FHIR_BASE}/DocumentReference", params={"subject": "Patient/maria-beispiel"})
    resp.raise_for_status()
    entries = resp.json().get("entry", [])
    for entry in entries:
        doc = entry["resource"]
        # Show type and date; content is base64 encoded, not displayed fully
        st.markdown(f"- **{doc.get('type', {}).get('coding', [{}])[0].get('display', 'Document')}** "
                    f"(date: {doc.get('date', 'N/A')})")
except Exception as e:
    st.error(f"Could not fetch documents: {e}")

# --- Audit Log ---
st.subheader("Audit Trail")
try:
    conn = sqlite3.connect(AUDIT_DB)
    df = pd.read_sql_query(
        "SELECT timestamp, event, actor, details FROM audit_log ORDER BY id DESC LIMIT 30",
        conn
    )
    conn.close()
    st.dataframe(df, use_container_width=True)
except Exception as e:
    st.error(f"Could not read audit database: {e}")
