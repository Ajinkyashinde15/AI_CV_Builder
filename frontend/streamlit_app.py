import os
import streamlit as st
import requests
import json

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="AI Resume Builder", layout="wide")
st.title("AI Resume Builder (LangGraph + Gemini + S3)")

with st.sidebar:
    st.markdown("### Settings")
    st.text(f"Backend: {BACKEND_URL}")

st.markdown("Upload your CVs to the configured S3 bucket/prefix (LocalStack in local mode). This UI will trigger resume generation for **all** CVs found.")

# List CVs via backend
if st.button("Refresh CV list"):
    resp = requests.get(f"{BACKEND_URL}/resume/list-cvs")
    if resp.status_code == 200:
        data = resp.json()
        st.session_state["cv_keys"] = data.get("keys", [])
        st.success(f"Found {len(st.session_state['cv_keys'])} CV(s)")
    else:
        st.error(f"Failed to list CVs: {resp.text}")

job_description = st.text_area("Job Description", height=220, placeholder="Paste the JD here...")

if st.button("Generate Resumes"):
    if not job_description.strip():
        st.error("Please paste a Job Description")
    else:
        with st.spinner("Generating resumes for all CVs in S3..."):
            resp = requests.post(f"{BACKEND_URL}/resume/generate", json={"job_description": job_description})
        if resp.status_code == 200:
            data = resp.json()
            st.success(f"Generated {len(data.get('output_keys', []))} resume(s)")
            st.write("Output keys:")
            st.code("".join(data.get("output_keys", [])))
        else:
            st.error(f"Generation failed: {resp.text}")

# Show cached list
cv_keys = st.session_state.get("cv_keys", [])
if cv_keys:
    st.markdown("### CVs detected in S3:")
    st.code("".join(cv_keys))
