import os
import re
import streamlit as st

st.set_page_config(page_title="InterviewForge AI", page_icon="🎙️", layout="wide")

# InterviewForge AI — hackathon starter
# Keep the application in this single file for the MVP.
# Add Gemini integration and document parsers where marked.

st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1400px;}
.hero {padding: 1.5rem; border-radius: 20px; border: 1px solid rgba(120,160,255,.25);}
.card {padding: 1rem; border-radius: 16px; border: 1px solid rgba(120,160,255,.18); margin-bottom: .8rem;}
.small {opacity: .75; font-size: .9rem;}
</style>
""", unsafe_allow_html=True)

def read_text(uploaded_file):
    """MVP placeholder. Add PDF/DOCX/TXT extraction here."""
    if uploaded_file is None:
        return ""
    name = uploaded_file.name.lower()
    if name.endswith(".txt"):
        return uploaded_file.getvalue().decode("utf-8", errors="ignore")
    return f"[Document uploaded: {uploaded_file.name}. Add parser integration here.]"

def build_evidence(candidate_text, profile_text, jd_text):
    return {
        "candidate": candidate_text,
        "profile": profile_text,
        "jd": jd_text,
        "rules": [
            "JD requirements are not candidate evidence.",
            "Public web information is context only.",
            "Never invent candidate experience."
        ],
    }

def safe_answer(question, evidence):
    """Replace this stub with Gemini + claim validation."""
    q = question.strip()
    if not q:
        return "Please enter a question."
    return (
        "I would answer this based only on the experience and skills documented "
        "in my supplied materials. I would avoid claiming direct experience that "
        "is not clearly evidenced, and I would explain my related approach instead."
    )

st.markdown('<div class="hero"><h1>🎙️ InterviewForge AI</h1><p>Your CV. Your Job. Your Experience. Your Interview.</p></div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("📄 Evidence Inputs")
    cv = st.file_uploader("CV / Resume", type=["pdf", "docx", "txt"])
    jd = st.file_uploader("Job Description", type=["pdf", "docx", "txt"])
    skills = st.text_area("Skills / Expertise", placeholder="Solar PV, BESS, technical due diligence...")
    company = st.text_input("Company (optional)")
    st.caption("Voice is designed for Mock Interview / Practice mode.")

cv_text = read_text(cv)
jd_text = read_text(jd)
evidence = build_evidence(cv_text, skills, jd_text)

tab1, tab2, tab3 = st.tabs(["🎯 Questions", "⌨️ Ask Question", "🎙️ Mock Interview"])

with tab1:
    st.subheader("Interview Question Engine")
    if cv and jd:
        questions = [
            "Tell me about your experience that is most relevant to this role.",
            "How have you approached reviewing technical project documentation?",
            "How would you assess technical risk in a solar PV and BESS project?",
            "Tell me about a time you identified an issue during technical review.",
            "Which areas of this job description are strongest in your background?"
        ]
        for i, q in enumerate(questions, 1):
            st.markdown(f"**{i}. {q}**")
            st.caption("Source: CV + JD • Difficulty: Medium")
    else:
        st.info("Upload both a CV and Job Description to generate grounded questions.")

with tab2:
    st.subheader("Ask an Interview Question")
    question = st.text_area("Question", placeholder="Tell me about your experience with...")
    if st.button("Generate Humanized Answer", type="primary"):
        answer = safe_answer(question, evidence)
        st.markdown("### Answer")
        st.write(answer)
        st.markdown("### 🛡 Evidence Status")
        st.success("MVP guardrail active: unsupported candidate claims are not invented.")
        st.caption("Production version: show exact source excerpts and claim-level validation.")

with tab3:
    st.subheader("🎙️ Mock Interview — Practice Mode")
    st.info("Practice mode: use your microphone to rehearse. The app should transcribe, detect the question, retrieve evidence and generate a grounded answer.")
    st.text_area("Live transcript", placeholder="Speech-to-text transcript appears here...")
    if st.button("Process Detected Question"):
        st.write("Question detection → evidence retrieval → answer generation → hallucination check")
        st.success("Practice answer ready. Production version should display source evidence and confidence.")

st.divider()
st.caption("InterviewForge AI • Hackathon MVP • Evidence-grounded interview preparation")
