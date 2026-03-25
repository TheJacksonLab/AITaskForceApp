import streamlit as st
from openai import OpenAI
import assemblyai as aai
import json
import os
import re
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
    Row order: timestamp, student_name, student_id, topic, subtopic, question,
               answer_method, transcript, score, feedback, misconceptions_flagged, trajectory
    """
    try:
        gc = get_gspread_client()
        if gc is None:
            return
        sh = gc.open(google_sheet_name)
        worksheet = sh.sheet1
        if worksheet.row_count == 0 or worksheet.acell("A1").value is None:
            headers = [
                "timestamp", "student_name", "student_id", "topic", "subtopic",
                "question", "answer_method", "transcript", "score",
                "feedback", "misconceptions_flagged", "trajectory",
            ]
            worksheet.append_row(headers)
        worksheet.append_row(row)
    except gspread.exceptions.SpreadsheetNotFound:
        st.warning(f"⚠ Google Sheet '{google_sheet_name}' not found — check GOOGLE_SHEET_NAME and sharing permissions.")
    except Exception as e:
        st.warning(f"⚠ Failed to write to Google Sheets: {e}")


# ── Question bank ─────────────────────────────────────────────────────────────
def _load_question_bank() -> dict[str, list[str]]:
    """Parse oral_exam_questions_list.txt into {subtopic: [question_texts]}."""
    bank: dict[str, list[str]] = {}
    current_topic: str | None = None
    topic_order = [
        "Stoichiometry",
        "Gases",
        "Chemical Equilibrium",
        "Energy & Enthalpy",
        "Thermodynamics",
        "Periodic Table Trends",
        "Chemical Bonding & Lewis Structures",
        "VSEPR, Polarity & IMFs",
        "Chemical Kinetics",
        "Acids and Bases",
    ]
    q_re = re.compile(r"^\d+\.\s+(.+)")
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "oral_exam_questions_list.txt")
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except FileNotFoundError:
        st.error("❌ oral_exam_questions_list.txt not found. Please add it to the app directory.")
        return {}
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        for topic in topic_order:
            if topic in stripped and not q_re.match(stripped):
                current_topic = topic
                if current_topic not in bank:
                    bank[current_topic] = []
                break
        if current_topic:
            m = q_re.match(stripped)
            if m:
                bank[current_topic].append(m.group(1).strip())
    return bank


QUESTION_BANK = _load_question_bank()

SUBTOPICS = ["Random (any topic)"] + list(QUESTION_BANK.keys())

TOPIC_INSTRUCTIONS = {
    "Stoichiometry": "Focus on stoichiometry: limiting reagents, percent yield, and solution stoichiometry.",
    "Gases": "Focus on gases: ideal gas law, gas mixtures, kinetic molecular theory, real gases, and the van der Waals equation.",
    "Chemical Equilibrium": "Focus on chemical equilibrium: equilibrium expressions, Le Chatelier's principle, and Kp vs Kc.",
    "Energy & Enthalpy": "Focus on energy and enthalpy: heat transfer, Hess's law, calorimetry, and bond enthalpies.",
    "Thermodynamics": "Focus on thermodynamics: entropy, Gibbs free energy, spontaneity, and thermodynamic vs kinetic control.",
    "Periodic Table Trends": "Focus on periodic table trends: atomic radius, ionization energy, electronegativity, and electron affinity.",
    "Chemical Bonding & Lewis Structures": "Focus on chemical bonding and Lewis structures: ionic vs covalent bonding, formal charge, and resonance.",
    "VSEPR, Polarity & IMFs": "Focus on VSEPR theory, molecular geometry, polarity, and intermolecular forces.",
    "Chemical Kinetics": "Focus on chemical kinetics: rate laws, reaction order, the Arrhenius equation, reaction mechanisms, and catalysis.",
    "Acids and Bases": "Focus on acids and bases: properties, definitions, acid-base equilibria, buffers, and titrations.",
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


def start_examination(topic: str) -> tuple[str, str]:
    """Sample an opening question from the question bank.

    Returns (question_text, resolved_topic) — resolved_topic is the actual
    subtopic used even when 'Random (any topic)' was selected.
    """
    if topic == "Random (any topic)":
        resolved_topic = random.choice(list(QUESTION_BANK.keys()))
    else:
        resolved_topic = topic
    questions = QUESTION_BANK.get(resolved_topic, [])
    if not questions:
        raise ValueError(f"No questions found for subtopic: {resolved_topic}")
    return random.choice(questions), resolved_topic


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


def generate_improvement_advice(
    client, conversation: list, topic: str, evaluation: dict
) -> str:
    """Generate personalized, friendly improvement advice based on exam performance."""
    lines = []
    for turn in conversation:
        label = "Examiner" if turn["role"] == "examiner" else "Student"
        lines.append(f"[{label}]: {turn['content']}")
    transcript = "\n\n".join(lines)

    score = evaluation.get("Score", 5)
    trajectory = evaluation.get("Trajectory", "mixed")
    feedback = evaluation.get("Feedback", "")
    misconceptions = evaluation.get("Misconceptions_Flagged", False)

    system_prompt = (
        "You are a supportive and encouraging chemistry professor giving personalized study advice "
        "to a student who just completed an oral exam.\n\n"
        f"TOPIC: {topic}\n"
        f"SCORE: {score}/10\n"
        f"TRAJECTORY: {trajectory}\n"
        f"MISCONCEPTIONS FLAGGED: {misconceptions}\n"
        f"GRADER FEEDBACK: {feedback}\n\n"
        "TASK: Based on the full exam transcript and the grading results above, write a short, "
        "warm, and targeted recommendation for what this student should study or practice to improve. "
        "Be specific — reference the actual concepts or areas where they struggled in the exam. "
        "If they scored 9 or 10, genuinely congratulate them, but still point to one concept or "
        "deeper aspect of the topic they could explore to truly master it. "
        "Keep it to 3-5 sentences. Be friendly and encouraging — like advice from a professor "
        "who genuinely wants the student to succeed. "
        "Do not repeat the score back to them. Just give the advice directly."
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"TRANSCRIPT:\n\n{transcript}"},
        ],
        timeout=45.0,
    )
    return response.choices[0].message.content.strip()


def grade_conversation(
    client, conversation: list, topic: str, opening_question: str
) -> dict:
    """Holistically grade the full examination transcript."""
    lines = []
    for turn in conversation:
        label = "Examiner" if turn["role"] == "examiner" else "Student"
        lines.append(f"[{label}]: {turn['content']}")
    transcript = "\n\n".join(lines)

    system_prompt = (
        f"You are a general chemistry professor grading a complete oral examination.\n\n"
        f"TOPIC: {topic}\n"
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

# ── Sidebar: Subtopic selection ───────────────────────────────────────────────
with st.sidebar:
    st.header("Question Settings")
    selected_topic = st.selectbox("Subtopic", options=SUBTOPICS, index=0)
    if st.button("New Question"):
        for key in ["question", "exam_state", "conversation", "exchange_count",
                    "answer_method", "evaluation", "sheet_logged", "resolved_topic",
                    "improvement_advice"]:
            st.session_state.pop(key, None)
        st.session_state["question_requested"] = True
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
settings_changed = st.session_state.get("active_topic") != selected_topic
if settings_changed:
    for key in ["question", "exam_state", "conversation", "exchange_count",
                "answer_method", "evaluation", "sheet_logged", "question_requested",
                "resolved_topic", "improvement_advice"]:
        st.session_state.pop(key, None)
    was_initialized = st.session_state.get("active_topic") is not None
    st.session_state["active_topic"] = selected_topic
    if was_initialized:  # Don't increment on initial page load, only on actual topic changes
        st.session_state["attempt_counter"] = st.session_state.get("attempt_counter", 0) + 1

if "question" not in st.session_state:
    if st.session_state.get("question_requested"):
        with st.spinner("Loading question..."):
            try:
                question, resolved_topic = start_examination(selected_topic)
                st.session_state["question"] = question
                st.session_state["resolved_topic"] = resolved_topic
                st.session_state.pop("question_requested", None)
            except Exception as e:
                st.error(f"❌ Failed to load question: {str(e)}")
                st.stop()
    else:
        st.info(
            "Select a subtopic in the sidebar, "
            "then click **New Question** to load your opening question."
        )
        st.stop()

question        = st.session_state["question"]
resolved_topic  = st.session_state.get("resolved_topic", selected_topic)
attempt         = st.session_state.get("attempt_counter", 0)
exam_state      = st.session_state.get("exam_state", "not_started")


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

        # Always get the examiner's response — on the final turn the FINAL TURN RULE
        # in the system prompt causes it to close the exam warmly instead of asking again.
        with st.spinner("Examiner is thinking..."):
            try:
                follow_up = get_examiner_response(
                    client, conversation, new_count,
                    TOPIC_INSTRUCTIONS.get(resolved_topic, resolved_topic)
                )
                conversation.append({"role": "examiner", "content": follow_up})
            except Exception as e:
                st.error(f"❌ Failed to get examiner response: {str(e)}")
                st.stop()

        st.session_state["conversation"] = conversation
        st.session_state["exchange_count"] = new_count

        if new_count >= MAX_EXCHANGES:
            # All exchanges done — grade the full conversation immediately
            with st.spinner("Evaluating your performance across all exchanges..."):
                try:
                    evaluation = grade_conversation(
                        client, conversation, resolved_topic, question
                    )
                    st.session_state["evaluation"] = evaluation
                    st.session_state["exam_state"] = "complete"
                except json.JSONDecodeError as e:
                    st.error(f"❌ Invalid JSON from evaluator: {str(e)}")
                except Exception as e:
                    st.error(f"❌ Evaluation failed: {str(e)}")

        st.rerun()

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

    st.subheader("Feedback")
    st.info(feedback)

    # Generate and display personalized improvement recommendations
    if "improvement_advice" not in st.session_state:
        with st.spinner("Generating personalized study recommendations..."):
            try:
                advice = generate_improvement_advice(client, conversation, resolved_topic, evaluation)
                st.session_state["improvement_advice"] = advice
            except Exception as e:
                st.session_state["improvement_advice"] = None

    advice = st.session_state.get("improvement_advice")
    if advice:
        st.subheader("Study Recommendations")
        st.success(advice)

    with st.expander("View full conversation transcript"):
        for turn in conversation:
            label = "Examiner" if turn["role"] == "examiner" else "You"
            st.markdown(f"**{label}:** {turn['content']}")
            st.write("")

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
            resolved_topic,
            question,
            answer_method_logged,
            formatted_transcript,
            score,
            feedback,
            str(misconceptions),
            trajectory,
        ])
        st.session_state["sheet_logged"] = True
