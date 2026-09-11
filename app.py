````python
import os
import json
import re
from io import BytesIO
from typing import Dict, List, Any

import streamlit as st
from groq import Groq
from dotenv import load_dotenv
from pypdf import PdfReader
from docx import Document

load_dotenv()

# ============================================================
# INTERVIEWFORGE AI
# Evidence-Grounded Interview Preparation & Mock Interview
#
# MVP architecture:
#   app.py
#   requirements.txt
#
# Core principle:
#   HONESTY > COMPLETENESS
#
# Candidate-specific claims must come from candidate evidence.
# JD requirements are NOT proof of candidate experience.
# ============================================================


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="InterviewForge AI",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# PREMIUM UI
# ============================================================

st.markdown(
    """
    <style>
    .stApp {
        background:
            radial-gradient(circle at 10% 10%, rgba(59,130,246,.10), transparent 28%),
            radial-gradient(circle at 90% 10%, rgba(139,92,246,.08), transparent 28%),
            #080b12;
        color: #f5f7fb;
    }

    .block-container {
        max-width: 1450px;
        padding-top: 1.5rem;
        padding-bottom: 3rem;
    }

    .hero {
        padding: 28px;
        border-radius: 22px;
        border: 1px solid rgba(96,165,250,.25);
        background: linear-gradient(
            135deg,
            rgba(30,41,59,.90),
            rgba(15,23,42,.85)
        );
        box-shadow: 0 20px 60px rgba(0,0,0,.25);
        margin-bottom: 22px;
    }

    .hero h1 {
        font-size: 42px;
        margin-bottom: 5px;
        letter-spacing: -1px;
    }

    .hero p {
        color: #aab4c5;
        font-size: 17px;
        margin: 0;
    }

    .glass-card {
        background: rgba(20,27,40,.82);
        border: 1px solid rgba(148,163,184,.15);
        border-radius: 18px;
        padding: 20px;
        margin-bottom: 15px;
    }

    .evidence-card {
        background: rgba(15,23,42,.95);
        border-left: 4px solid #22c55e;
        border-radius: 12px;
        padding: 15px;
        margin-top: 10px;
    }

    .warning-card {
        background: rgba(120,53,15,.18);
        border-left: 4px solid #f59e0b;
        border-radius: 12px;
        padding: 15px;
        margin-top: 10px;
    }

    .danger-card {
        background: rgba(127,29,29,.18);
        border-left: 4px solid #ef4444;
        border-radius: 12px;
        padding: 15px;
        margin-top: 10px;
    }

    .success-card {
        background: rgba(20,83,45,.18);
        border-left: 4px solid #22c55e;
        border-radius: 12px;
        padding: 15px;
        margin-top: 10px;
    }

    .status-pill {
        display: inline-block;
        padding: 5px 10px;
        border-radius: 999px;
        background: rgba(59,130,246,.12);
        color: #93c5fd;
        border: 1px solid rgba(59,130,246,.25);
        font-size: 12px;
        margin-right: 5px;
    }

    div[data-testid="stMetric"] {
        background: rgba(20,27,40,.8);
        border: 1px solid rgba(148,163,184,.12);
        padding: 12px;
        border-radius: 15px;
    }

    .stButton > button {
        border-radius: 10px;
        font-weight: 600;
        min-height: 42px;
    }

    section[data-testid="stSidebar"] {
        background: #0b0f17;
        border-right: 1px solid rgba(148,163,184,.10);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# SESSION STATE
# ============================================================

DEFAULT_STATE = {
    "candidate_text": "",
    "profile_text": "",
    "jd_text": "",
    "company_text": "",
    "evidence_ready": False,
    "interview_started": False,
    "current_question": "",
    "current_question_meta": {},
    "messages": [],
    "feedbacks": [],
    "questions": [],
    "voice_transcript": "",
    "readiness": 0,
}

for key, value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# FILE EXTRACTION
# ============================================================

def extract_pdf(file) -> str:
    """Extract text from PDF."""
    try:
        reader = PdfReader(file)
        pages = []

        for page in reader.pages:
            text = page.extract_text() or ""
            pages.append(text)

        return "\n".join(pages).strip()

    except Exception as exc:
        return f"[PDF extraction error: {exc}]"


def extract_docx(file) -> str:
    """Extract text from DOCX."""
    try:
        document = Document(file)
        paragraphs = [p.text for p in document.paragraphs]

        # Also capture simple tables.
        for table in document.tables:
            for row in table.rows:
                paragraphs.append(
                    " | ".join(cell.text for cell in row.cells)
                )

        return "\n".join(paragraphs).strip()

    except Exception as exc:
        return f"[DOCX extraction error: {exc}]"


def extract_uploaded_text(file) -> str:
    """Extract PDF, DOCX or TXT content."""
    if file is None:
        return ""

    filename = file.name.lower()

    if filename.endswith(".pdf"):
        return extract_pdf(file)

    if filename.endswith(".docx"):
        return extract_docx(file)

    if filename.endswith(".txt"):
        return file.getvalue().decode(
            "utf-8",
            errors="ignore"
        ).strip()

    return ""


# ============================================================
# BASIC TEXT NORMALIZATION
# ============================================================

def normalize_text(text: str) -> str:
    text = text or ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def sentences(text: str) -> List[str]:
    """Break text into reasonably useful evidence chunks."""
    text = normalize_text(text)

    if not text:
        return []

    parts = re.split(r"(?<=[.!?])\s+", text)

    return [
        p.strip()
        for p in parts
        if len(p.strip()) > 20
    ]


# ============================================================
# EVIDENCE ENGINE
# ============================================================

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from",
    "have", "has", "are", "was", "were", "will", "your",
    "you", "our", "their", "about", "into", "using", "use",
    "role", "job", "candidate", "experience", "years",
    "work", "working", "required", "requirements"
}


def keywords(text: str) -> set:
    words = re.findall(r"[a-zA-Z0-9+#.-]{3,}", text.lower())

    return {
        word
        for word in words
        if word not in STOPWORDS
    }


def retrieve_evidence(
    query: str,
    candidate_text: str,
    profile_text: str,
    jd_text: str,
    top_k: int = 8,
) -> Dict[str, List[Dict[str, Any]]]:

    query_words = keywords(query)

    candidate_chunks = sentences(candidate_text)
    profile_chunks = sentences(profile_text)
    jd_chunks = sentences(jd_text)

    def score(chunk):
        chunk_words = keywords(chunk)

        if not query_words or not chunk_words:
            return 0

        overlap = query_words.intersection(chunk_words)

        return len(overlap) / max(len(query_words), 1)

    def rank(chunks, source):
        ranked = []

        for chunk in chunks:
            s = score(chunk)

            if s > 0:
                ranked.append({
                    "source": source,
                    "text": chunk,
                    "score": round(s, 3),
                })

        ranked.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        return ranked[:top_k]

    return {
        "candidate": rank(candidate_chunks, "CV / Resume"),
        "profile": rank(profile_chunks, "Candidate Profile / Skills"),
        "jd": rank(jd_chunks, "Job Description"),
    }


def format_evidence(evidence: Dict) -> str:
    """Create a clearly separated evidence context for the LLM."""

    sections = []

    sections.append("=== CANDIDATE EVIDENCE ===")

    for source in ["candidate", "profile"]:
        for item in evidence.get(source, []):
            sections.append(
                f"[{item['source']}] {item['text']}"
            )

    sections.append("\n=== JOB DESCRIPTION EVIDENCE ===")

    for item in evidence.get("jd", []):
        sections.append(
            f"[Job Description] {item['text']}"
        )

    sections.append(
        """
=== CRITICAL EVIDENCE RULES ===
1. CV/Profile evidence may support candidate-specific claims.
2. Job Description evidence describes employer requirements only.
3. JD requirements are NOT proof that the candidate has the skill.
4. Never invent employers, projects, clients, tools, certifications,
   dates, years, project values, KPIs, MW/MWh or responsibilities.
5. If evidence is missing, explicitly say so.
"""
    )

    return "\n".join(sections)


# ============================================================
# GEMINI/GROQ JSON SAFETY
# ============================================================

def clean_json_response(text: str) -> Dict:
    """Safely parse model JSON."""

    text = text.strip()

    # Remove accidental markdown fences.
    text = re.sub(
        r"^```(?:json)?",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"```$",
        "",
        text
    )

    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, re.DOTALL)

        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass

    return {}


# ============================================================
# LLM FUNCTIONS
# ============================================================

def call_llm(
    client,
    model,
    system_prompt,
    user_prompt,
    temperature=0.2,
    max_tokens=700,
):

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_prompt
            },
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )

    return response.choices[0].message.content.strip()


def generate_questions(
    client,
    model,
    role,
    candidate_text,
    profile_text,
    jd_text,
):
    """Generate practical questions with provenance."""

    evidence = retrieve_evidence(
        "role responsibilities technical skills experience competencies",
        candidate_text,
        profile_text,
        jd_text,
        top_k=10,
    )

    context = format_evidence(evidence)

    system_prompt = """
You are InterviewForge AI.

Your job is to generate practical interview questions grounded in
candidate evidence and the target Job Description.

IMPORTANT:

- Never assume a candidate has a skill simply because the JD requests it.
- Questions should be relevant to both the candidate and the role.
- Prefer questions that an actual interviewer could ask.
- Keep questions short and human.
- Include CV/JD provenance.
- Do not generate questions about unsupported candidate experience.
- If a JD requirement is not evidenced in the CV, you may ask a
  competency/situational question, but do not imply the candidate has
  prior experience.

Return STRICT JSON:

{
  "questions": [
    {
      "question": "...",
      "category": "CV Based | JD Based | Technical | Behavioral | Situational",
      "difficulty": "Easy | Medium | Hard",
      "cv_evidence": "...",
      "jd_evidence": "...",
      "expected_competency": "..."
    }
  ]
}
"""

    user_prompt = f"""
Target role:
{role}

{context}

Generate 8 highly relevant interview questions.
"""

    raw = call_llm(
        client,
        model,
        system_prompt,
        user_prompt,
        temperature=0.4,
        max_tokens=1400,
    )

    result = clean_json_response(raw)

    return result.get("questions", [])


def generate_first_question(
    client,
    model,
    role,
    candidate_text,
    profile_text,
    jd_text,
):
    questions = generate_questions(
        client,
        model,
        role,
        candidate_text,
        profile_text,
        jd_text,
    )

    if questions:
        return questions[0]

    return {
        "question": (
            "Can you briefly introduce yourself and explain "
            "why this role is relevant to your experience?"
        ),
        "category": "Introduction",
        "difficulty": "Easy",
        "cv_evidence": "",
        "jd_evidence": "",
        "expected_competency": "Role relevance",
    }


def evaluate_answer(
    client,
    model,
    role,
    question,
    answer,
    candidate_text,
    profile_text,
    jd_text,
):
    """
    Evaluate an answer while explicitly separating:
    candidate evidence vs JD requirements vs general knowledge.
    """

    evidence = retrieve_evidence(
        f"{question} {answer}",
        candidate_text,
        profile_text,
        jd_text,
        top_k=10,
    )

    context = format_evidence(evidence)

    system_prompt = """
You are the InterviewForge AI Evidence & Coaching Agent.

Evaluate the candidate answer.

The most important rule:

DO NOT reward invented experience.

Candidate-specific claims must be supported by the CV or candidate profile.

The Job Description describes what the employer wants. It is NOT
evidence that the candidate has done something.

Return STRICT JSON:

{
  "overall_score": 0,
  "technical_relevance_score": 0,
  "communication_clarity_score": 0,
  "jd_alignment_score": 0,
  "evidence_grounding_score": 0,
  "grounding_status": "Evidence grounded | Limited evidence | Unsupported claim",
  "unsupported_claims": [],
  "strengths": [],
  "areas_for_improvement": [],
  "detailed_critique": "",
  "safe_answer": "",
  "evidence_used": [],
  "answer_length_words": 0
}

Scoring rules:

Evidence grounded:
Candidate claims are clearly supported.

Limited evidence:
The topic is relevant, but direct candidate evidence is weak or absent.

Unsupported claim:
The candidate states specific experience that cannot be supported.

For unsupported claims:
DO NOT repeat or strengthen the invented claim.

Instead, create a safe answer based only on supported evidence.

The safe answer should normally be 35–80 words and sound natural.
"""

    user_prompt = f"""
Target role:
{role}

Question:
{question}

Candidate answer:
{answer}

Evidence:
{context}
"""

    raw = call_llm(
        client,
        model,
        system_prompt,
        user_prompt,
        temperature=0.1,
        max_tokens=1200,
    )

    result = clean_json_response(raw)

    if not result:
        result = {
            "overall_score": 0,
            "technical_relevance_score": 0,
            "communication_clarity_score": 0,
            "jd_alignment_score": 0,
            "evidence_grounding_score": 0,
            "grounding_status": "Limited evidence",
            "unsupported_claims": [],
            "strengths": [],
            "areas_for_improvement": [
                "The AI evaluation could not be parsed safely."
            ],
            "detailed_critique": (
                "Please retry the evaluation."
            ),
            "safe_answer": answer,
            "evidence_used": [],
            "answer_length_words": len(answer.split()),
        }

    return result


def generate_humanized_answer(
    client,
    model,
    role,
    question,
    candidate_text,
    profile_text,
    jd_text,
):
    """
    Generate a short answer BEFORE showing it to the user,
    with strong grounding constraints.
    """

    evidence = retrieve_evidence(
        question,
        candidate_text,
        profile_text,
        jd_text,
        top_k=8,
    )

    context = format_evidence(evidence)

    system_prompt = """
You are InterviewForge AI's Humanized Answer Builder.

Create a short interview answer.

RULES:

1. Candidate experience may ONLY come from CV/Profile evidence.
2. JD requirements are not candidate experience.
3. Public/company information is not candidate experience.
4. Never invent employers, projects, responsibilities, technologies,
   certifications, dates, years, project sizes, KPIs or clients.
5. Use natural spoken language.
6. Prefer first-person wording.
7. Default length: 35–80 words.
8. Do not sound robotic or overly corporate.
9. If evidence is insufficient, clearly acknowledge that.
10. Never turn a hypothetical approach into claimed experience.

Return JSON:

{
  "answer": "...",
  "grounding_status": "Evidence grounded | Limited evidence | Unsupported claim",
  "evidence_used": ["..."],
  "confidence": 0
}
"""

    user_prompt = f"""
Target role:
{role}

Interview question:
{question}

Evidence:
{context}
"""

    raw = call_llm(
        client,
        model,
        system_prompt,
        user_prompt,
        temperature=0.25,
        max_tokens=500,
    )

    return clean_json_response(raw)


def generate_follow_up(
    client,
    model,
    role,
    question,
    answer,
    candidate_text,
    profile_text,
    jd_text,
):
    evidence = retrieve_evidence(
        f"{question} {answer}",
        candidate_text,
        profile_text,
        jd_text,
        top_k=8,
    )

    context = format_evidence(evidence)

    system_prompt = """
You are a realistic human interviewer.

Ask ONE short follow-up question.

The follow-up must:
- relate directly to the previous answer;
- be relevant to the target role;
- stay within supported candidate evidence where asking about experience;
- not invent a project or technology;
- sound like a real interviewer.

Return ONLY the question.
"""

    user_prompt = f"""
Role:
{role}

Previous question:
{question}

Candidate answer:
{answer}

Evidence:
{context}
"""

    return call_llm(
        client,
        model,
        system_prompt,
        user_prompt,
        temperature=0.35,
        max_tokens=180,
    ).strip()


# ============================================================
# VOICE TRANSCRIPTION
# ============================================================

def transcribe_audio(client, audio_bytes: bytes) -> str:
    """
    Groq Whisper transcription.

    Requires a supported Groq audio transcription model.
    """

    audio_file = BytesIO(audio_bytes)
    audio_file.name = "interview_question.wav"

    transcription = client.audio.transcriptions.create(
        file=audio_file,
        model="whisper-large-v3-turbo",
        response_format="text",
    )

    if isinstance(transcription, str):
        return transcription.strip()

    return getattr(transcription, "text", "").strip()


# ============================================================
# READINESS CALCULATION
# ============================================================

def calculate_readiness(feedbacks: List[Dict]) -> int:

    if not feedbacks:
        return 0

    scores = []

    for f in feedbacks:
        score = (
            float(f.get("overall_score", 0))
            + float(f.get("jd_alignment_score", 0))
            + float(f.get("evidence_grounding_score", 0))
            + float(f.get("communication_clarity_score", 0))
        ) / 4

        scores.append(score)

    return round(sum(scores) / len(scores))


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown("## 🎙️ InterviewForge AI")

    st.caption(
        "Evidence-grounded interview preparation & "
        "Mock Interview practice"
    )

    st.divider()

    api_key = st.text_input(
        "Groq API Key",
        type="password",
        value=os.getenv("GROQ_API_KEY", ""),
        help="Use Streamlit Secrets or an environment variable in production.",
    )

    model_name = st.selectbox(
        "LLM Model",
        [
            "openai/gpt-oss-120b",
            "llama-3.3-70b-versatile",
        ],
    )

    st.divider()

    st.markdown("### 📄 Candidate Evidence")

    cv_file = st.file_uploader(
        "CV / Resume",
        type=["pdf", "docx", "txt"],
    )

    profile_file = st.file_uploader(
        "Candidate Profile / Skills",
        type=["pdf", "docx", "txt"],
    )

    skills = st.text_area(
        "Skills & Expertise",
        placeholder=(
            "Example:\n"
            "Solar PV\n"
            "BESS\n"
            "Technical Due Diligence\n"
            "Energy Yield Review"
        ),
        height=130,
    )

    st.markdown("### 💼 Target Role")

    jd_file = st.file_uploader(
        "Job Description",
        type=["pdf", "docx", "txt"],
    )

    target_role = st.text_input(
        "Target Role",
        placeholder="Senior Renewable Energy Engineer",
    )

    company_name = st.text_input(
        "Company Name (optional)",
        placeholder="Company name",
    )

    st.divider()

    if st.button(
        "🚀 Build Evidence & Start",
        type="primary",
        use_container_width=True,
    ):

        if not api_key:
            st.error("Please provide your Groq API key.")

        elif not cv_file:
            st.error("Please upload the candidate CV / Resume.")

        elif not jd_file:
            st.error("Please upload the Job Description.")

        else:

            with st.spinner("Building evidence knowledge base..."):

                st.session_state.candidate_text = (
                    extract_uploaded_text(cv_file)
                )

                st.session_state.profile_text = (
                    extract_uploaded_text(profile_file)
                    if profile_file
                    else ""
                )

                if skills:
                    st.session_state.profile_text += (
                        "\nCandidate Skills:\n" + skills
                    )

                st.session_state.jd_text = (
                    extract_uploaded_text(jd_file)
                )

                st.session_state.company_text = company_name

                st.session_state.evidence_ready = True
                st.session_state.interview_started = True
                st.session_state.messages = []
                st.session_state.feedbacks = []
                st.session_state.questions = []
                st.session_state.current_question = ""
                st.session_state.current_question_meta = {}

            st.success("Evidence base ready.")

    st.divider()

    st.caption("🛡 Evidence Lock: ON")
    st.caption("🎙️ Voice Mode: Mock Interview / Practice")


# ============================================================
# API VALIDATION
# ============================================================

if not api_key:
    st.markdown(
        """
        <div class="warning-card">
        <b>Welcome to InterviewForge AI</b><br><br>
        Add your Groq API key in the sidebar, then upload a CV and
        Job Description to begin.
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.stop()


client = Groq(api_key=api_key)


# ============================================================
# HERO
# ============================================================

st.markdown(
    """
    <div class="hero">
        <h1>🎙️ InterviewForge AI</h1>
        <p>
        Your CV. Your Job. Your Experience. Your Interview.
        </p>
        <br>
        <span class="status-pill">Evidence Grounded</span>
        <span class="status-pill">Humanized Answers</span>
        <span class="status-pill">Mock Interview</span>
        <span class="status-pill">Hallucination Firewall</span>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# TOP METRICS
# ============================================================

readiness = calculate_readiness(
    st.session_state.feedbacks
)

m1, m2, m3, m4, m5 = st.columns(5)

m1.metric(
    "🎯 Readiness",
    f"{readiness}%"
)

m2.metric(
    "🧠 Questions",
    len(st.session_state.feedbacks)
)

m3.metric(
    "🛡 Grounded",
    sum(
        1
        for f in st.session_state.feedbacks
        if f.get("grounding_status") == "Evidence grounded"
    )
)

m4.metric(
    "⚠️ Unsupported",
    sum(
        len(f.get("unsupported_claims", []))
        for f in st.session_state.feedbacks
    )
)

m5.metric(
    "🎙️ Voice",
    "Ready"
)


# ============================================================
# TABS
# ============================================================

(
    tab_dashboard,
    tab_interview,
    tab_voice,
    tab_evidence,
    tab_analytics,
) = st.tabs(
    [
        "🏠 Dashboard",
        "💬 Interview",
        "🎙️ Voice Practice",
        "🛡 Evidence Center",
        "📊 Analytics",
    ]
)


# ============================================================
# DASHBOARD
# ============================================================

with tab_dashboard:

    if not st.session_state.evidence_ready:

        st.info(
            "Upload a CV and Job Description from the sidebar "
            "to build your interview workspace."
        )

    else:

        st.subheader("Interview Intelligence")

        c1, c2 = st.columns(2)

        with c1:

            st.markdown(
                """
                <div class="glass-card">
                <h3>📄 Candidate Evidence</h3>
                <p>
                Your CV, profile and supplied skills form the primary
                source for candidate-specific claims.
                </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with c2:

            st.markdown(
                """
                <div class="glass-card">
                <h3>💼 Role Intelligence</h3>
                <p>
                The Job Description determines what the interviewer
                should test — but does not prove candidate experience.
                </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.subheader("🎯 Interview Strategy")

        if target_role:
            st.write(
                f"Target role: **{target_role}**"
            )

        if company_name:
            st.write(
                f"Company: **{company_name}**"
            )

        if not st.session_state.questions:

            if st.button(
                "Generate Interview Questions",
                type="primary",
            ):

                with st.spinner(
                    "Generating CV + JD grounded questions..."
                ):

                    st.session_state.questions = (
                        generate_questions(
                            client,
                            model_name,
                            target_role,
                            st.session_state.candidate_text,
                            st.session_state.profile_text,
                            st.session_state.jd_text,
                        )
                    )

                st.success(
                    f"Generated {len(st.session_state.questions)} questions."
                )

        if st.session_state.questions:

            for idx, q in enumerate(
                st.session_state.questions,
                start=1,
            ):

                with st.expander(
                    f"{idx}. {q.get('question', '')}"
                ):

                    st.write(
                        f"**Category:** "
                        f"{q.get('category', 'N/A')}"
                    )

                    st.write(
                        f"**Difficulty:** "
                        f"{q.get('difficulty', 'N/A')}"
                    )

                    st.write(
                        f"**Expected competency:** "
                        f"{q.get('expected_competency', 'N/A')}"
                    )

                    st.markdown(
                        "**CV Evidence:** "
                        + q.get("cv_evidence", "Not clearly evidenced.")
                    )

                    st.markdown(
                        "**JD Evidence:** "
                        + q.get("jd_evidence", "Not available.")
                    )


# ============================================================
# INTERVIEW TAB
# ============================================================

with tab_interview:

    st.subheader("💬 Mock Interview — Text Mode")

    if not st.session_state.evidence_ready:

        st.info(
            "Build your evidence base first."
        )

    else:

        if not st.session_state.current_question:

            first = generate_first_question(
                client,
                model_name,
                target_role,
                st.session_state.candidate_text,
                st.session_state.profile_text,
                st.session_state.jd_text,
            )

            st.session_state.current_question = (
                first["question"]
            )

            st.session_state.current_question_meta = first

            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": first["question"],
                    "meta": first,
                }
            )

        # Question card
        st.markdown(
            f"""
            <div class="glass-card">
                <div class="small">CURRENT INTERVIEW QUESTION</div>
                <h2>{st.session_state.current_question}</h2>
            </div>
            """,
            unsafe_allow_html=True,
        )

        meta = st.session_state.current_question_meta

        if meta:

            c1, c2, c3 = st.columns(3)

            c1.metric(
                "Category",
                meta.get("category", "Interview")
            )

            c2.metric(
                "Difficulty",
                meta.get("difficulty", "Medium")
            )

            c3.metric(
                "Competency",
                meta.get(
                    "expected_competency",
                    "General"
                )
            )

        # Transcript
        for message in st.session_state.messages:

            if message["role"] == "assistant":

                with st.chat_message(
                    "assistant",
                    avatar="🤖"
                ):
                    st.write(message["content"])

            else:

                with st.chat_message(
                    "user",
                    avatar="👤"
                ):
                    st.write(message["content"])

        user_answer = st.chat_input(
            "Type your interview answer..."
        )

        if user_answer:

            current_q = (
                st.session_state.current_question
            )

            st.session_state.messages.append(
                {
                    "role": "user",
                    "content": user_answer,
                }
            )

            with st.spinner(
                "Evidence Agent + Coaching Agent analyzing..."
            ):

                result = evaluate_answer(
                    client,
                    model_name,
                    target_role,
                    current_q,
                    user_answer,
                    st.session_state.candidate_text,
                    st.session_state.profile_text,
                    st.session_state.jd_text,
                )

            st.session_state.feedbacks.append(result)

            # ------------------------------------------------
            # Feedback
            # ------------------------------------------------

            with st.expander(
                "🔍 Evidence-Grounded Coach Feedback",
                expanded=True,
            ):

                cols = st.columns(5)

                cols[0].metric(
                    "Overall",
                    f"{result.get('overall_score', 0)}"
                )

                cols[1].metric(
                    "Technical",
                    f"{result.get('technical_relevance_score', 0)}"
                )

                cols[2].metric(
                    "JD Match",
                    f"{result.get('jd_alignment_score', 0)}"
                )

                cols[3].metric(
                    "Grounding",
                    f"{result.get('evidence_grounding_score', 0)}"
                )

                cols[4].metric(
                    "Clarity",
                    f"{result.get('communication_clarity_score', 0)}"
                )

                status = result.get(
                    "grounding_status",
                    "Limited evidence"
                )

                if status == "Evidence grounded":

                    st.markdown(
                        f"""
                        <div class="success-card">
                        🟢 <b>Evidence Grounded</b><br>
                        Candidate-specific claims are supported by
                        the supplied evidence.
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                elif status == "Unsupported claim":

                    st.markdown(
                        f"""
                        <div class="danger-card">
                        🔴 <b>Unsupported Claim Detected</b><br>
                        The answer contains candidate-specific claims
                        that are not clearly supported by the supplied
                        materials.
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                else:

                    st.markdown(
                        f"""
                        <div class="warning-card">
                        🟡 <b>Limited Evidence</b><br>
                        The topic is relevant, but direct evidence is
                        not sufficiently clear.
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                st.markdown(
                    "### Strengths"
                )

                for strength in result.get(
                    "strengths",
                    []
                ):
                    st.write("• " + strength)

                st.markdown(
                    "### Areas to Improve"
                )

                for area in result.get(
                    "areas_for_improvement",
                    []
                ):
                    st.write("• " + area)

                st.markdown(
                    "### Detailed Critique"
                )

                st.write(
                    result.get(
                        "detailed_critique",
                        ""
                    )
                )

                unsupported = result.get(
                    "unsupported_claims",
                    []
                )

                if unsupported:

                    st.markdown(
                        "### ⚠️ Unsupported Claims"
                    )

                    for claim in unsupported:
                        st.error(claim)

                st.markdown(
                    "### 🛡 Safe / Improved Answer"
                )

                st.info(
                    result.get(
                        "safe_answer",
                        user_answer
                    )
                )

            # ------------------------------------------------
            # Follow-up
            # ------------------------------------------------

            with st.spinner(
                "Interviewer preparing follow-up..."
            ):

                follow_up = generate_follow_up(
                    client,
                    model_name,
                    target_role,
                    current_q,
                    user_answer,
                    st.session_state.candidate_text,
                    st.session_state.profile_text,
                    st.session_state.jd_text,
                )

            st.session_state.current_question = follow_up

            st.session_state.current_question_meta = {
                "question": follow_up,
                "category": "Follow-up",
                "difficulty": "Medium",
                "cv_evidence": "",
                "jd_evidence": "",
                "expected_competency": "Follow-up reasoning",
            }

            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": follow_up,
                    "meta": st.session_state.current_question_meta,
                }
            )

            st.rerun()


# ============================================================
# VOICE PRACTICE
# ============================================================

with tab_voice:

    st.subheader(
        "🎙️ Real-Time Voice Mock Interview"
    )

    st.warning(
        "Practice mode: this feature is designed for interview "
        "rehearsal. It should not be used as concealed assistance "
        "during an actual employer assessment."
    )

    if not st.session_state.evidence_ready:

        st.info(
            "Build the evidence base before starting voice practice."
        )

    else:

        st.markdown(
            """
            <div class="glass-card">
            <h3>Voice Workflow</h3>
            <p>
            🎙️ Microphone → Speech-to-Text → Question Detection →
            Evidence Retrieval → Grounded Answer → Hallucination Check
            </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        audio = st.audio_input(
            "Ask your interview question"
        )

        if audio:

            with st.spinner(
                "Transcribing your question..."
            ):

                try:

                    transcript = transcribe_audio(
                        client,
                        audio.getvalue()
                    )

                    st.session_state.voice_transcript = (
                        transcript
                    )

                except Exception as exc:

                    st.error(
                        "Voice transcription failed. "
                        "Please check your Groq configuration."
                    )

                    st.exception(exc)

        if st.session_state.voice_transcript:

            st.markdown("### 📝 Detected Question")

            st.info(
                st.session_state.voice_transcript
            )

            transcript = (
                st.session_state.voice_transcript
            )

            # Simple question quality check.
            if len(transcript.split()) < 3:

                st.warning(
                    "Question unclear — please repeat."
                )

            else:

                if st.button(
                    "Generate Grounded Voice Answer",
                    type="primary",
                ):

                    with st.spinner(
                        "Building evidence-grounded answer..."
                    ):

                        voice_answer = (
                            generate_humanized_answer(
                                client,
                                model_name,
                                target_role,
                                transcript,
                                st.session_state.candidate_text,
                                st.session_state.profile_text,
                                st.session_state.jd_text,
                            )
                        )

                    if not voice_answer:

                        st.error(
                            "The answer could not be safely generated."
                        )

                    else:

                        status = voice_answer.get(
                            "grounding_status",
                            "Limited evidence"
                        )

                        if status == "Evidence grounded":

                            st.success(
                                "🟢 Evidence Grounded"
                            )

                        elif status == "Unsupported claim":

                            st.error(
                                "🔴 Unsupported candidate claim risk"
                            )

                        else:

                            st.warning(
                                "🟡 Limited Evidence"
                            )

                        st.markdown(
                            "### 💬 Humanized Short Answer"
                        )

                        st.markdown(
                            f"""
                            <div class="glass-card">
                            {voice_answer.get("answer", "")}
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                        st.markdown(
                            "### 🛡 Evidence Used"
                        )

                        for evidence_item in voice_answer.get(
                            "evidence_used",
                            []
                        ):

                            st.write(
                                "• " + evidence_item
                            )

                        st.metric(
                            "Evidence Confidence",
                            f"{voice_answer.get('confidence', 0)}%"
                        )


# ============================================================
# EVIDENCE CENTER
# ============================================================

with tab_evidence:

    st.subheader(
        "🛡 Evidence Center"
    )

    if not st.session_state.evidence_ready:

        st.info(
            "Upload the CV and JD to inspect the evidence."
        )

    else:

        c1, c2, c3 = st.columns(3)

        with c1:

            st.markdown(
                """
                <div class="evidence-card">
                <h3>Candidate Evidence</h3>
                CV + Profile + Skills
                </div>
                """,
                unsafe_allow_html=True,
            )

        with c2:

            st.markdown(
                """
                <div class="warning-card">
                <h3>Employer Evidence</h3>
                Job Description
                </div>
                """,
                unsafe_allow_html=True,
            )

        with c3:

            st.markdown(
                """
                <div class="danger-card">
                <h3>Never Mix</h3>
                JD requirements ≠ candidate experience
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown(
            "### Candidate CV Evidence"
        )

        st.text_area(
            "Extracted CV",
            st.session_state.candidate_text,
            height=250,
            disabled=True,
        )

        st.markdown(
            "### Candidate Profile / Skills"
        )

        st.text_area(
            "Profile",
            st.session_state.profile_text,
            height=180,
            disabled=True,
        )

        st.markdown(
            "### Job Description"
        )

        st.text_area(
            "JD",
            st.session_state.jd_text,
            height=250,
            disabled=True,
        )

        st.markdown(
            """
            ### Evidence Lock Rules

            🟢 **Candidate Evidence**
            - CV
            - Candidate profile
            - Candidate-provided skills
            - Candidate project experience

            🟡 **Employer Evidence**
            - Job Description
            - Role requirements
            - Responsibilities

            🔵 **Context Evidence**
            - Public company information
            - Public role information

            🔴 **Never claim**
            - Unsupported employers
            - Unsupported projects
            - Unsupported tools
            - Unsupported certifications
            - Unsupported project sizes
            - Unsupported years of experience
            """
        )


# ============================================================
# ANALYTICS
# ============================================================

with tab_analytics:

    st.subheader(
        "📊 Interview Analytics"
    )

    if not st.session_state.feedbacks:

        st.info(
            "Complete at least one interview question."
        )

    else:

        feedbacks = (
            st.session_state.feedbacks
        )

        def avg(field):
            values = [
                float(f.get(field, 0))
                for f in feedbacks
            ]

            return (
                sum(values) / len(values)
                if values else 0
            )

        c1, c2, c3, c4 = st.columns(4)

        c1.metric(
            "Overall",
            f"{avg('overall_score'):.1f}%"
        )

        c2.metric(
            "Technical",
            f"{avg('technical_relevance_score'):.1f}%"
        )

        c3.metric(
            "JD Alignment",
            f"{avg('jd_alignment_score'):.1f}%"
        )

        c4.metric(
            "Grounding",
            f"{avg('evidence_grounding_score'):.1f}%"
        )

        st.markdown(
            "### Interview History"
        )

        for idx, feedback in enumerate(
            feedbacks,
            start=1,
        ):

            with st.expander(
                f"Question #{idx} — "
                f"{feedback.get('grounding_status', 'Unknown')}"
            ):

                c1, c2, c3 = st.columns(3)

                c1.metric(
                    "Overall",
                    feedback.get(
                        "overall_score",
                        0
                    )
                )

                c2.metric(
                    "Technical",
                    feedback.get(
                        "technical_relevance_score",
                        0
                    )
                )

                c3.metric(
                    "Grounding",
                    feedback.get(
                        "evidence_grounding_score",
                        0
                    )
                )

                st.markdown(
                    "**Strengths**"
                )

                for item in feedback.get(
                    "strengths",
                    []
                ):
                    st.write("• " + item)

                st.markdown(
                    "**Improvement Areas**"
                )

                for item in feedback.get(
                    "areas_for_improvement",
                    []
                ):
                    st.write("• " + item)

                st.markdown(
                    "**Unsupported Claims**"
                )

                claims = feedback.get(
                    "unsupported_claims",
                    []
                )

                if claims:

                    for claim in claims:
                        st.error(claim)

                else:

                    st.success(
                        "No unsupported candidate-specific "
                        "claims detected."
                    )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "InterviewForge AI • Hackathon MVP • "
    "Evidence-grounded interview preparation • "
    "Honesty > Completeness"
)
````
