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
                "feedback", "misconceptions_flagged", "trajectory",
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


MAX_EXCHANGES = 6  # number of student response turns before grading is triggered

EXAMINER_SYSTEM_PROMPT = """\
You are an oral examiner for an undergraduate general chemistry course (CHEM202).

ROLE: You are experienced, fair, and encouraging. Your goal is to accurately assess \
the student's conceptual understanding through adaptive dialogue — not to trick or \
discourage them.

TOPIC: {topic_instruction}
Stay on this topic throughout the examination.

EXCHANGE COUNTER: You are responding to student response {current_exchange} of {max_exchanges}.

DIFFICULTY RULES:
- If the student demonstrates strong understanding: escalate — ask them to go deeper, \
explain a mechanism, predict an outcome, or apply the concept to a new scenario.
- If the student struggles or answers only partially: adapt — ask a simpler follow-up \
that targets a foundational piece of the same concept.
- If the student shows a persistent misconception: note it and probe further before moving on.
- Never abandon a line of questioning while the student shows any partial understanding.

HANDLING STUDENT QUESTIONS:
- If the student asks for clarification about the wording or context of the question: \
clarify it. This is not penalized.
- If the student asks you to define a chemistry course concept (e.g. "what is entropy?", \
"can you explain what a rate law is?"): do NOT provide the definition. Instead say something \
like: "That concept is at the heart of what I'm asking — tell me what you understand about it." \
Then redirect them back to the question.
- If the student says they don't know: encourage them to try. Say something like: \
"Take a guess — what do you think might be happening at the molecular level here?"

TONE: Be warm and supportive. Acknowledge what the student gets right before probing gaps. \
Partial credit is valid — say what they got right, then probe what's missing.

FINAL TURN RULE: If current_exchange equals max_exchanges, do NOT ask another question. \
Instead, thank the student warmly for their responses and let them know the examination \
is now complete.

Return ONLY your examiner response — no labels, no preamble, no meta-commentary.\
"""


def start_examination(client, topic: str, style: str) -> str:
    topic_instruction = TOPICS[topic]
    if style == "Real-world scenario":
        domain = random.choice(REAL_WORLD_DOMAINS)
        style_instruction = QUESTION_STYLES[style].format(domain=domain)
    else:
        style_instruction = QUESTION_STYLES[style]
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": (
                "Generate a single opening question for a dynamic oral examination in an undergraduate "
                "general chemistry course (Chemistry 202). "
                f"{topic_instruction} "
                f"{style_instruction} "
                "The opening question should be moderately challenging — harder than a simple recall "
                "question, requiring the student to reason through a concept or explain a relationship, "
                "not just recite a definition. It should be accessible to a well-prepared student but "
                "push them to demonstrate deeper understanding. "
                "Avoid multi-part questions and questions that require strong quantitative calculation. "
                "Keep the question to 1-2 sentences. "
                "Be creative and specific — avoid generic or overused textbook examples. "
                "Do NOT use question stems like 'Define', 'List', 'State', or 'What is the formula for'. "
                "Return ONLY the question text, no preamble, topic label, or style label."
            )
        }],
        timeout=30.0
    )
    return response.choices[0].message.content.strip()


def get_examiner_response(
    client, conversation: list, exchange_count: int, topic_instruction: str
) -> str:
    """Generate the examiner's next turn given the full conversation history."""
    system_prompt = EXAMINER_SYSTEM_PROMPT.format(
        topic_instruction=topic_instruction,
        current_exchange=exchange_count,
        max_exchanges=MAX_EXCHANGES,
    )
    messages = [{"role": "system", "content": system_prompt}]
    for turn in conversation:
        if turn["role"] == "examiner":
            messages.append({"role": "assistant", "content": turn["content"]})
        else:
            messages.append({"role": "user", "content": turn["content"]})
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        timeout=45.0,
    )
    return response.choices[0].message.content.strip()


def grade_conversation(
    client, conversation: list, topic: str, style: str, opening_question: str
) -> dict:
    """Holistically grade the full examination transcript."""
    lines = []
    for turn in conversation:
        label = "Examiner" if turn["role"] == "examiner" else "Student"
        lines.append(f"[{label}]: {turn['content']}")
    transcript = "\n\n".join(lines)

    system_prompt = (
        f"You are a general chemistry professor grading a complete oral examination.\n\n"
        f"TOPIC: {topic} | STYLE: {style}\n"
        f"OPENING QUESTION: {opening_question}\n\n"
        "GRADING PHILOSOPHY:\n"
        "- Evaluate the student's understanding across the ENTIRE conversation, not just their first response.\n"
        "- Reward trajectory: a student who started uncertain but meaningfully improved should score "
        "better than one who stayed confused throughout.\n"
        "- Reward intellectual honesty and self-correction.\n"
        "- Penalize persistent, uncorrected misconceptions more than early confusion followed by recovery.\n"
        "- Do not penalize a student for asking clarifying questions about the question itself.\n\n"
        "SCORING GUIDE:\n"
        "- 9-10: Consistently accurate, strong reasoning, excellent terminology, shows real depth\n"
        "- 7-8: Mostly accurate with minor gaps, good reasoning, clear improvement arc\n"
        "- 5-6: Partial understanding, some correct elements, struggled but showed effort and engagement\n"
        "- 3-4: Limited understanding, significant misconceptions, minimal improvement over exchanges\n"
        "- 1-2: Fundamental misunderstanding throughout, no meaningful engagement\n\n"
        "Respond in valid JSON with exactly these four keys:\n"
        '- "Score" (integer 1-10)\n'
        '- "Feedback" (string, 2-3 sentences: what they did well, what they struggled with, overall assessment)\n'
        '- "Misconceptions_Flagged" (boolean: true if significant uncorrected misconceptions remain at the end)\n'
        '- "Trajectory" (string, one of: "improving", "consistent_strong", "consistent_weak", "declining", "mixed")\n\n'
        "Respond with ONLY the JSON object, no additional text."
    )
    response = client.chat.completions.create(
        model="o3-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"TRANSCRIPT:\n\n{transcript}"},
        ],
        timeout=60.0,
    )
    return json.loads(response.choices[0].message.content)


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Oral Exam Test for CHEM202 - AITaskForce", layout="wide")
st.title("Oral Exam Test for CHEM202 - AITaskForce")

# ── Sidebar: Topic Pinning & Question Style ───────────────────────────────────
with st.sidebar:
    st.header("Question Settings")
    selected_topic = st.selectbox("Topic", options=list(TOPICS.keys()), index=0)
    selected_style = st.selectbox("Question style", options=list(QUESTION_STYLES.keys()), index=0)
    if st.button("New Question"):
        for key in ["question", "exam_state", "conversation", "exchange_count",
                    "answer_method", "evaluation", "sheet_logged"]:
            st.session_state.pop(key, None)
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
    for key in ["question", "exam_state", "conversation", "exchange_count",
                "answer_method", "evaluation", "sheet_logged"]:
        st.session_state.pop(key, None)
    was_initialized = st.session_state.get("active_topic") is not None
    st.session_state["active_topic"] = selected_topic
    st.session_state["active_style"] = selected_style
    if was_initialized:  # Don't increment on initial page load, only on actual topic/style changes
        st.session_state["attempt_counter"] = st.session_state.get("attempt_counter", 0) + 1

if "question" not in st.session_state:
    with st.spinner("Loading question..."):
        try:
            st.session_state["question"] = start_examination(client, selected_topic, selected_style)
        except Exception as e:
            st.error(f"❌ Failed to generate question: {str(e)}")
            st.stop()

question = st.session_state["question"]
attempt = st.session_state.get("attempt_counter", 0)
exam_state = st.session_state.get("exam_state", "not_started")


# ── UI helpers ────────────────────────────────────────────────────────────────

def _transcribe_audio(audio_bytes) -> str | None:
    """Transcribe audio bytes via AssemblyAI. Returns text or None on failure."""
    temp_audio_path = "temp_audio.wav"
    try:
        with open(temp_audio_path, "wb") as f:
            f.write(audio_bytes.getbuffer())
        transcriber = aai.Transcriber()
        result = transcriber.transcribe(
            temp_audio_path,
            config=aai.TranscriptionConfig(
                language_code="en",
                speech_models=["universal-2"],
                entity_detection=True,
            ),
        )
        return result.text
    except Exception as e:
        st.error(f"❌ Transcription failed: {str(e)}")
        return None
    finally:
        if os.path.exists(temp_audio_path):
            try:
                os.remove(temp_audio_path)
            except Exception:
                pass


def _render_conversation(conversation: list, answer_method: str):
    """Render the full conversation thread as chat bubbles."""
    for turn in conversation:
        if turn["role"] == "examiner":
            with st.chat_message("assistant", avatar="🎓"):
                st.write(turn["content"])
        else:
            avatar = "🎤" if answer_method == "audio" else "✍️"
            with st.chat_message("user", avatar=avatar):
                st.write(turn["content"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EXAM STATE MACHINE
# States: "not_started" → "in_progress" → "complete"
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ── State: not_started ────────────────────────────────────────────────────────
if exam_state == "not_started":
    st.write(f"**Opening Question:** {question}")

    st.info(
        "**How this exam works**\n\n"
        f"You will have **{MAX_EXCHANGES} exchanges** with an AI oral examiner. "
        "The examiner will adapt follow-up questions based on your responses — "
        "going deeper if you're strong, or probing foundational concepts if you need support. "
        "You may ask the examiner to clarify the question; you will not be penalized for this. "
        "Your final score reflects your understanding across the full conversation.\n\n"
        "**Scoring considers:** conceptual accuracy · reasoning quality · correct terminology · trajectory of improvement"
    )

    answer_mode = st.radio(
        "How would you like to answer throughout the exam?",
        options=["Record audio", "Type my answers"],
        horizontal=True,
        key=f"mode_{attempt}",
    )

    if st.button("Begin Exam", type="primary", key=f"begin_{attempt}"):
        st.session_state["answer_method"] = "audio" if answer_mode == "Record audio" else "typed"
        st.session_state["conversation"] = [{"role": "examiner", "content": question}]
        st.session_state["exchange_count"] = 0
        st.session_state["exam_state"] = "in_progress"
        st.rerun()

# ── State: in_progress ────────────────────────────────────────────────────────
elif exam_state == "in_progress":
    conversation   = st.session_state["conversation"]
    exchange_count = st.session_state["exchange_count"]
    answer_method  = st.session_state["answer_method"]

    st.progress(
        exchange_count / MAX_EXCHANGES,
        text=f"Exchange {exchange_count + 1} of {MAX_EXCHANGES}",
    )

    _render_conversation(conversation, answer_method)

    transcript_text = None

    if answer_method == "audio":
        audio_bytes = st.audio_input(
            "Record your response:", key=f"audio_{attempt}_{exchange_count}"
        )
        if audio_bytes:
            with st.spinner("Transcribing audio..."):
                transcript_text = _transcribe_audio(audio_bytes)
    else:
        typed = st.text_area(
            "Your response:",
            height=150,
            placeholder="Type your response to the examiner's question...",
            key=f"typed_{attempt}_{exchange_count}",
        )
        if st.button("Submit", key=f"submit_{attempt}_{exchange_count}"):
            if not typed.strip():
                st.error("Please write a response before submitting.")
            else:
                transcript_text = typed.strip()

    if transcript_text:
        conversation.append({"role": "student", "content": transcript_text})
        new_count = exchange_count + 1

        if new_count < MAX_EXCHANGES:
            with st.spinner("Examiner is thinking..."):
                try:
                    follow_up = get_examiner_response(
                        client, conversation, new_count, TOPICS[selected_topic]
                    )
                    conversation.append({"role": "examiner", "content": follow_up})
                except Exception as e:
                    st.error(f"❌ Failed to get examiner response: {str(e)}")
                    st.stop()
            st.session_state["conversation"] = conversation
            st.session_state["exchange_count"] = new_count
            st.rerun()
        else:
            # Final student turn — grade the full conversation
            st.session_state["conversation"] = conversation
            st.session_state["exchange_count"] = new_count
            with st.spinner("Evaluating your performance across all exchanges..."):
                try:
                    evaluation = grade_conversation(
                        client, conversation, selected_topic, selected_style, question
                    )
                    st.session_state["evaluation"] = evaluation
                    st.session_state["exam_state"] = "complete"
                    st.rerun()
                except json.JSONDecodeError as e:
                    st.error(f"❌ Invalid JSON from evaluator: {str(e)}")
                except Exception as e:
                    st.error(f"❌ Evaluation failed: {str(e)}")

# ── State: complete ───────────────────────────────────────────────────────────
elif exam_state == "complete":
    conversation  = st.session_state["conversation"]
    evaluation    = st.session_state["evaluation"]
    answer_method = st.session_state["answer_method"]

    _render_conversation(conversation, answer_method)

    st.divider()
    st.subheader("Examination Complete")

    score          = evaluation.get("Score", "N/A")
    feedback       = evaluation.get("Feedback", "No feedback available.")
    misconceptions = evaluation.get("Misconceptions_Flagged", False)
    trajectory     = evaluation.get("Trajectory", "N/A")

    TRAJECTORY_LABELS = {
        "improving":         "Improving",
        "consistent_strong": "Consistently Strong",
        "consistent_weak":   "Consistently Weak",
        "declining":         "Declining",
        "mixed":             "Mixed",
    }
    trajectory_display = TRAJECTORY_LABELS.get(trajectory, trajectory)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Score", f"{score}/10")
    with col2:
        st.metric("Trajectory", trajectory_display)
    with col3:
        st.metric("Misconceptions?", "Yes" if misconceptions else "No")

    st.subheader("Feedback")
    st.info(feedback)

    with st.expander("View full conversation transcript"):
        for turn in conversation:
            label = "Examiner" if turn["role"] == "examiner" else "You"
            st.markdown(f"**{label}:** {turn['content']}")
            st.write("")

    with st.expander("View full evaluation JSON"):
        st.json(evaluation)

    # ── Google Sheets logging (once per completed exam) ───────────────────────
    if not st.session_state.get("sheet_logged"):
        formatted_transcript = "\n\n".join(
            f"[{'Examiner' if t['role'] == 'examiner' else 'Student'}]: {t['content']}"
            for t in conversation
        )
        answer_method_logged = f"dialogue-{answer_method}"
        append_to_sheet([
            exam_timestamp,
            student_name,
            student_id,
            selected_topic,
            selected_style,
            question,
            answer_method_logged,
            formatted_transcript,
            score,
            feedback,
            str(misconceptions),
            trajectory,
        ])
        st.session_state["sheet_logged"] = True
