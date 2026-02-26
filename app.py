import streamlit as st
from openai import OpenAI
import assemblyai as aai
import json
import os
import random
from datetime import datetime, timezone
from dotenv import load_dotenv

import gspread
from google.oauth2.service_account import Credentials

load_dotenv()


# ── Secret resolution: prefer st.secrets (Streamlit Cloud), fall back to env ──
def _get_secret(key: str):
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key)


openai_api_key     = _get_secret("OPENAI_API_KEY")
assemblyai_api_key = _get_secret("ASSEMBLYAI_API_KEY")
google_creds_str   = _get_secret("GOOGLE_SHEETS_CREDENTIALS")
google_sheet_name  = _get_secret("GOOGLE_SHEET_NAME") or "CHEM202_OralExam_Submissions"

if not openai_api_key:
    st.error("❌ OPENAI_API_KEY not found. Please set it in Streamlit secrets or .env file.")
    st.stop()

if not assemblyai_api_key:
    st.error("❌ ASSEMBLYAI_API_KEY not found. Please set it in Streamlit secrets or .env file.")
    st.stop()

try:
    client = OpenAI(api_key=openai_api_key)
except Exception as e:
    st.error(f"❌ Failed to initialize OpenAI client: {str(e)}")
    st.stop()

try:
    aai.settings.api_key = assemblyai_api_key
except Exception as e:
    st.error(f"❌ Failed to initialize AssemblyAI: {str(e)}")
    st.stop()


# ── Google Sheets helpers ─────────────────────────────────────────────────────
def get_gspread_client():
    """
    Authenticate with Google Sheets using service account credentials.
    Tries the recommended TOML section format ([gcp_service_account]) first,
    then falls back to a JSON string (GOOGLE_SHEETS_CREDENTIALS).
    Returns None with a warning if credentials are unavailable — the exam
    still works; only logging is skipped.
    """
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    # Preferred: credentials stored as a TOML section in Streamlit secrets
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except KeyError:
        pass  # section not present, try JSON string fallback
    except Exception as e:
        st.warning(f"⚠ Could not connect to Google Sheets: {e} — submissions will not be logged.")
        return None

    # Fallback: credentials stored as a minified JSON string
    if not google_creds_str:
        st.warning("⚠ Google Sheets credentials not configured — submissions will not be logged.")
        return None
    try:
        creds_dict = json.loads(google_creds_str)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except json.JSONDecodeError:
        st.warning("⚠ GOOGLE_SHEETS_CREDENTIALS is not valid JSON — submissions will not be logged.")
        return None
    except Exception as e:
        st.warning(f"⚠ Could not connect to Google Sheets: {e} — submissions will not be logged.")
        return None


def append_to_sheet(row: list):
    """
    Append a single row to the Google Sheet.
    Failures warn but never call st.stop() — logging must not break the exam.
    Row order: timestamp, student_name, student_id, topic, style, question,
               answer_method, transcript, score, feedback, misconceptions_flagged
    """
    try:
        gc = get_gspread_client()
        if gc is None:
            return
        sh = gc.open(google_sheet_name)
        worksheet = sh.sheet1
        if worksheet.row_count == 0 or worksheet.acell("A1").value is None:
            headers = [
                "timestamp", "student_name", "student_id", "topic", "style",
                "question", "answer_method", "transcript", "score",
                "feedback", "misconceptions_flagged",
            ]
            worksheet.append_row(headers)
        worksheet.append_row(row)
    except gspread.exceptions.SpreadsheetNotFound:
        st.warning(f"⚠ Google Sheet '{google_sheet_name}' not found — check GOOGLE_SHEET_NAME and sharing permissions.")
    except Exception as e:
        st.warning(f"⚠ Failed to write to Google Sheets: {e}")


# ── Topic and style definitions ───────────────────────────────────────────────
TOPICS = {
    "Random (any topic)": (
        "Pick a random topic from the following course syllabus: "
        "stoichiometry (limiting reagents, percent yield, solution stoichiometry); "
        "gases (ideal gas law, gas mixtures, kinetic molecular theory, real gases and van der Waals equation); "
        "chemical equilibrium (equilibrium expressions, Le Chatelier's principle, Kp vs Kc); "
        "energy and enthalpy (heat transfer, Hess's law, calorimetry, bond enthalpies); "
        "thermodynamics (entropy, Gibbs free energy, spontaneity, thermodynamic vs kinetic control); "
        "periodic table trends (atomic radius, ionization energy, electronegativity, electron affinity); "
        "chemical bonding and Lewis structures (ionic vs covalent, formal charge, resonance); "
        "VSEPR, molecular geometry, polarity, and intermolecular forces; "
        "chemical kinetics (rate laws, reaction order, Arrhenius equation, reaction mechanisms, catalysis)."
    ),
    "Stoichiometry": "Focus on stoichiometry: limiting reagents, percent yield, and solution stoichiometry.",
    "Gases": "Focus on gases: ideal gas law, gas mixtures, kinetic molecular theory, real gases, and the van der Waals equation.",
    "Chemical Equilibrium": "Focus on chemical equilibrium: equilibrium expressions, Le Chatelier's principle, and Kp vs Kc.",
    "Energy & Enthalpy": "Focus on energy and enthalpy: heat transfer, Hess's law, calorimetry, and bond enthalpies.",
    "Thermodynamics": "Focus on thermodynamics: entropy, Gibbs free energy, spontaneity, and thermodynamic vs kinetic control.",
    "Periodic Table Trends": "Focus on periodic table trends: atomic radius, ionization energy, electronegativity, and electron affinity.",
    "Chemical Bonding & Lewis Structures": "Focus on chemical bonding and Lewis structures: ionic vs covalent bonding, formal charge, and resonance.",
    "VSEPR, Polarity & IMFs": "Focus on VSEPR theory, molecular geometry, polarity, and intermolecular forces.",
    "Chemical Kinetics": "Focus on chemical kinetics: rate laws, reaction order, the Arrhenius equation, reaction mechanisms, and catalysis.",
}

REAL_WORLD_DOMAINS = [
    "smartphone lithium-ion batteries overheating in a pocket",
    "SPF ratings in sunscreen and UV protection",
    "PFAS 'forever chemicals' detected in drinking water",
    "microplastics accumulating in the ocean",
    "wildfire smoke and air quality index",
    "electric vehicle battery range dropping in cold weather",
    "tattoo ink fading and breaking down under skin",
    "energy drink ingredients (caffeine, taurine, B vitamins) and the body",
    "teeth whitening strips and enamel",
    "skincare actives — retinol, niacinamide, AHAs — and skin pH",
    "vaping aerosol chemistry and lung exposure",
    "Ozempic / GLP-1 receptor agonists and metabolism",
    "protein powder supplements and nitrogen content",
    "glow sticks at concerts — chemiluminescence",
    "OLED screens on phones and electroluminescence",
    "concrete cracking in bridges and chemical weathering",
    "car airbag sodium azide rapid decomposition",
    "pool chlorination and disinfection byproducts",
    "dry ice sublimation in shipping packages",
    "wine or beer fermentation gone wrong — off-flavors and spoilage",
    "fast fashion synthetic dyes polluting rivers",
    "solar panel semiconductor chemistry and the photoelectric effect",
    "reusable water bottle BPA leaching",
    "carbon dating ancient artifacts",
    "mRNA vaccine cold-chain storage requirements",
    "antibiotic resistance and bacterial cell membranes",
    "hand sanitizer alcohol chemistry and why concentration matters",
    "sunburn and UV-induced DNA damage",
    "contact lens oxygen permeability and polymer chemistry",
    "composting and the chemistry of organic decomposition",
    "food dye stability in acidic vs. basic drinks",
    "nicotine patches and transdermal drug delivery",
    "rust on a bike left outside — electrochemical corrosion",
    "the Maillard reaction when toasting bread or searing meat",
    "acetaminophen (Tylenol) overdose and liver chemistry",
]

QUESTION_STYLES = {
    "Random (any style)": (
        "Choose randomly from these question styles: "
        "a real-world scenario the student must explain chemically; "
        "a 'predict and explain' question where a variable changes and the student reasons through the outcome; "
        "a troubleshooting scenario where something unexpected happened and the student diagnoses why; "
        "or a compare-and-contrast between two systems, conditions, or substances."
    ),
    "Real-world scenario": (
        "Frame the question around this specific real-world context: {domain}. "
        "Describe one brief, concrete observation from that context that a college student in 2025 would recognize, "
        "then ask the student to explain the underlying chemistry."
    ),
    "Predict & explain": (
        "Ask the student to predict what happens when one variable changes in a real, relatable system, and explain why. "
        "Ground the scenario in something a college student might actually encounter or read about — "
        "for example: what happens to a lithium battery's performance in winter cold, "
        "how a sports drink's electrolyte concentration affects hydration, "
        "what changing pH does to a skincare product's effectiveness, "
        "how adding more catalyst affects a reaction rate in a drug synthesis, "
        "what happens to solubility when you heat a carbonated drink, "
        "how atmospheric CO2 concentration affects ocean pH over time, "
        "or what happens to enzyme activity when body temperature rises during a fever. "
        "Use stems like 'What would happen if...', 'How would X change if Y increases...', or 'A researcher finds that...'."
    ),
    "Troubleshoot": (
        "Describe a specific situation where something went wrong or gave a surprising result, "
        "grounded in a context a college student would find plausible and interesting. "
        "Draw from settings like: a campus lab experiment, a pharmaceutical manufacturing plant, "
        "a water treatment facility detecting contamination, an EV battery pack failing unexpectedly, "
        "a food scientist noticing unexpected spoilage, a climate researcher seeing unexpected data, "
        "a cosmetics chemist whose product separated on the shelf, "
        "or an athlete's supplement causing an unexpected reaction. "
        "Ask the student to diagnose the chemical reason behind the unexpected result. "
        "Use stems like 'A student ran an experiment and noticed...', 'A batch of product unexpectedly failed...', "
        "or 'A researcher observed something surprising when...'."
    ),
    "Compare & contrast": (
        "Ask the student to compare two related substances, conditions, or processes that both appear in the real world. "
        "Choose pairs that are adjacent in chemistry but meaningfully different, and connect them to something tangible — for example: "
        "why a lithium-ion vs. alkaline battery behaves differently under load, "
        "how polar vs. nonpolar sunscreen ingredients interact with skin differently, "
        "why strong vs. weak acids feel different on contact, "
        "how endothermic vs. exothermic hand warmers work, "
        "why ionic vs. covalent compounds have such different melting points, "
        "how a catalyst vs. an inhibitor changes a drug's shelf life, "
        "or why CO2 vs. N2 behaves differently when dissolved in a beverage. "
        "Ask the student to explain what drives the chemical difference in behavior."
    ),
}


def generate_question(client, topic: str, style: str) -> str:
    topic_instruction = TOPICS[topic]
    if style == "Real-world scenario":
        domain = random.choice(REAL_WORLD_DOMAINS)
        style_instruction = QUESTION_STYLES[style].format(domain=domain)
    else:
        style_instruction = QUESTION_STYLES[style]
    response = client.chat.completions.create(
        model="o3-mini",
        messages=[{
            "role": "user",
            "content": (
                "Generate a single short oral exam question for an undergraduate general chemistry course (Chemistry 202). "
                f"{topic_instruction} "
                f"{style_instruction} "
                "The question should ask the student to explain a basic concept or describe a simple relationship — "
                "accessible to a student who has attended lectures and done the reading, but not necessarily mastered the material deeply. "
                "Avoid multi-part questions, advanced problem-solving, or questions that require strong quantitative reasoning. "
                "Keep the question to 1-2 sentences. "
                "Be creative and specific — avoid generic or overused textbook examples. "
                "Do NOT use question stems like 'Define', 'List', 'State', or 'What is the formula for'. "
                "Return ONLY the question text, no preamble, topic label, or style label."
            )
        }],
        timeout=30.0
    )
    return response.choices[0].message.content.strip()


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Oral Exam Test for CHEM202 - AITaskForce", layout="wide")
st.title("Oral Exam Test for CHEM202 - AITaskForce")

# ── Sidebar: Topic Pinning & Question Style ───────────────────────────────────
with st.sidebar:
    st.header("Question Settings")
    selected_topic = st.selectbox("Topic", options=list(TOPICS.keys()), index=0)
    selected_style = st.selectbox("Question style", options=list(QUESTION_STYLES.keys()), index=0)
    if st.button("New Question"):
        st.session_state.pop("question", None)
        st.session_state["attempt_counter"] = st.session_state.get("attempt_counter", 0) + 1

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FEATURE 1: Student Identity Gate
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if "student_name" not in st.session_state:
    st.subheader("Student Information")
    st.write("Please enter your information before the exam question loads.")
    with st.form("student_gate_form"):
        name_input = st.text_input("Full Name", placeholder="Jane Smith")
        id_input   = st.text_input("Student ID", placeholder="e.g. 12345678")
        submitted  = st.form_submit_button("Begin Exam")
    if submitted:
        if not name_input.strip() or not id_input.strip():
            st.error("Both Full Name and Student ID are required.")
        else:
            st.session_state["student_name"]   = name_input.strip()
            st.session_state["student_id"]     = id_input.strip()
            st.session_state["exam_timestamp"] = datetime.now(timezone.utc).isoformat()
            st.rerun()
    st.stop()

student_name   = st.session_state["student_name"]
student_id     = st.session_state["student_id"]
exam_timestamp = st.session_state["exam_timestamp"]

st.caption(f"Logged in as: **{student_name}** | ID: {student_id} | ☁️ Cloud Version")

# ── Question caching ──────────────────────────────────────────────────────────
settings_changed = (
    st.session_state.get("active_topic") != selected_topic
    or st.session_state.get("active_style") != selected_style
)
if settings_changed:
    st.session_state.pop("question", None)
    was_initialized = st.session_state.get("active_topic") is not None
    st.session_state["active_topic"] = selected_topic
    st.session_state["active_style"] = selected_style
    if was_initialized:  # Don't increment on initial page load, only on actual topic/style changes
        st.session_state["attempt_counter"] = st.session_state.get("attempt_counter", 0) + 1

if "question" not in st.session_state:
    with st.spinner("Loading question..."):
        try:
            st.session_state["question"] = generate_question(client, selected_topic, selected_style)
        except Exception as e:
            st.error(f"❌ Failed to generate question: {str(e)}")
            st.stop()

question = st.session_state["question"]
st.write(f"**Prompt:** {question}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FEATURE 2: Rubric Transparency
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.info(
    "**Scoring Rubric** — your answer will be evaluated on:\n\n"
    "- **Conceptual Accuracy** — are the chemical principles correct?\n"
    "- **Reasoning Quality** — do you explain *why*, not just *what*?\n"
    "- **Correct Terminology** — are terms used precisely and appropriately?\n"
    "- **Addressing the Question** — does your answer directly respond to what was asked?\n\n"
    "Answers are scored out of 10 by an AI evaluator using these four dimensions."
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FEATURE 3: Typed Fallback Answer
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
attempt = st.session_state.get("attempt_counter", 0)

answer_method = st.radio(
    "How would you like to submit your answer?",
    options=["Record audio", "Type my answer"],
    horizontal=True,
    key=f"answer_method_{attempt}",
)
answer_method_logged = "audio" if answer_method == "Record audio" else "typed"
transcript_text = None

if answer_method == "Record audio":
    audio_bytes = st.audio_input("Record your answer:", key=f"audio_input_{attempt}")

    if audio_bytes:
        # --- 2. TRANSCRIPTION: AssemblyAI ---
        with st.spinner("Transcribing audio..."):
            temp_audio_path = "temp_audio.wav"
            try:
                with open(temp_audio_path, "wb") as f:
                    f.write(audio_bytes.getbuffer())
                transcriber = aai.Transcriber()
                transcript = transcriber.transcribe(
                    temp_audio_path,
                    config=aai.TranscriptionConfig(
                        language_code="en",
                        speech_models=["universal-2"],
                        entity_detection=True,
                    ),
                )
                transcript_text = transcript.text
                st.success("✓ Audio transcribed successfully")
            except Exception as e:
                st.error(f"❌ Transcription failed: {str(e)}")
                st.stop()
            finally:
                if os.path.exists(temp_audio_path):
                    try:
                        os.remove(temp_audio_path)
                    except Exception as cleanup_err:
                        st.warning(f"⚠ Could not delete temp file: {cleanup_err}")

else:
    typed_answer = st.text_area(
        "Type your answer here:",
        height=200,
        placeholder="Write your full answer to the question above...",
        key=f"typed_answer_{attempt}",
    )
    if st.button("Submit typed answer"):
        if not typed_answer.strip():
            st.error("Please write an answer before submitting.")
        else:
            transcript_text = typed_answer.strip()
            st.success("✓ Typed answer received")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVALUATION — runs for both audio and typed paths once transcript_text is set
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if transcript_text:

    # --- FEATURE 4: Audit Log ---
    audit_log = (
        f"[AUDIT LOG]\n"
        f"Student: {student_name} | ID: {student_id}\n"
        f"Timestamp: {exam_timestamp}\n"
        f"Topic: {selected_topic} | Style: {selected_style}\n"
        f"Question: {question}\n"
        f"Answer method: {answer_method_logged}\n"
        f"---\n"
        f"TRANSCRIPT:\n"
        f"{transcript_text}"
    )

    # --- 3. EVALUATION: LLM Structured Output (using OpenAI o3-mini) ---
    with st.spinner("Evaluating conceptual accuracy..."):
        system_prompt = (
            f'You are a general chemistry evaluator. The student was asked: "{question}"\n\n'
            "Read their transcript and evaluate how accurately and completely they answered the question.\n\n"
            "You MUST respond in valid JSON format with exactly three keys:\n"
            '- "Score" (integer out of 10)\n'
            '- "Feedback" (string, 1-2 sentences)\n'
            '- "Misconceptions_Flagged" (boolean)\n\n'
            "Respond with ONLY the JSON object, no additional text."
        )

        try:
            response = client.chat.completions.create(
                model="o3-mini",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Transcript: {audit_log}"},
                ],
                timeout=60.0,
            )

            evaluation = json.loads(response.choices[0].message.content)
            st.success("✓ Evaluation complete")

            score          = evaluation.get("Score", "N/A")
            feedback       = evaluation.get("Feedback", "No feedback available")
            misconceptions = evaluation.get("Misconceptions_Flagged", False)

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Score", f"{score}/10")
            with col2:
                st.metric("Misconceptions?", "Yes" if misconceptions else "No")

            st.subheader("📋 Feedback")
            st.info(feedback)

            with st.expander("View full evaluation JSON"):
                st.json(evaluation)

            with st.expander("View transcript"):
                st.text(transcript_text)

            # --- FEATURE 5: Google Sheets Logging ---
            append_to_sheet([
                exam_timestamp,
                student_name,
                student_id,
                selected_topic,
                selected_style,
                question,
                answer_method_logged,
                transcript_text,
                score,
                feedback,
                str(misconceptions),
            ])

        except json.JSONDecodeError as e:
            st.error(f"❌ Invalid JSON response from API: {str(e)}")
        except Exception as e:
            st.error(f"❌ Evaluation failed: {str(e)}")
