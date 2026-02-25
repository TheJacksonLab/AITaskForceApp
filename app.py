import streamlit as st
from openai import OpenAI
import assemblyai as aai
import json
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize OpenAI client with API key from .env
openai_api_key = os.getenv("OPENAI_API_KEY")
assemblyai_api_key = os.getenv("ASSEMBLYAI_API_KEY")

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


QUESTION_STYLES = {
    "Random (any style)": (
        "Choose randomly from these question styles: "
        "a real-world scenario the student must explain chemically; "
        "a 'predict and explain' question where a variable changes and the student reasons through the outcome; "
        "a troubleshooting scenario where something unexpected happened and the student diagnoses why; "
        "or a compare-and-contrast between two systems, conditions, or substances."
    ),
    "Real-world scenario": (
        "Frame the question as an observable phenomenon, everyday situation, or news-worthy event "
        "(e.g., cooking, environmental chemistry, medicine, engineering, weather) that the student must explain "
        "using chemical principles. Start with a concrete observation or context, then ask 'why' or 'how'."
    ),
    "Predict & explain": (
        "Ask the student to predict what happens when a condition changes — temperature, pressure, concentration, "
        "catalyst, solvent, etc. — and explain the chemical reasoning behind their prediction. "
        "Use stems like 'What would happen if...', 'How would X change if Y were doubled...', or 'A chemist increases...'."
    ),
    "Troubleshoot": (
        "Describe a scenario where something went wrong or produced an unexpected result in a lab or real-world setting. "
        "Ask the student to diagnose the chemical reason. "
        "Use stems like 'A student ran an experiment and observed...', 'A reaction produced far less product than expected...', "
        "or 'An engineer noticed that...'."
    ),
    "Compare & contrast": (
        "Ask the student to compare two related substances, systems, conditions, or processes and explain "
        "the chemical reasoning behind their differences or similarities in behavior. "
        "Use stems like 'Compare how...', 'Why does X behave differently from Y when...', or 'Under what conditions would X be preferred over Y?'."
    ),
}


def generate_question(client, topic: str, style: str):
    topic_instruction = TOPICS[topic]
    style_instruction = QUESTION_STYLES[style]
    response = client.chat.completions.create(
        model="o3-mini",
        messages=[{
            "role": "user",
            "content": (
                "Generate a single oral exam question for an undergraduate general chemistry course (Chemistry 202). "
                f"{topic_instruction} "
                f"{style_instruction} "
                "The question must require genuine chemical reasoning and sense-making — not recitation of facts, definitions, or formulas. "
                "Do NOT use question stems like 'Define', 'List', 'State', or 'What is the formula for'. "
                "Return ONLY the question text, no preamble, topic label, or style label."
            )
        }],
        timeout=30.0
    )
    return response.choices[0].message.content.strip()


# --- 1. FRONTEND: Student Interface ---
st.set_page_config(page_title="Oral Exam Test for CHEM202 - AITaskForce", layout="wide")
st.title("Oral Exam Test for CHEM202 - AITaskForce")

# --- Sidebar: Topic Pinning & Question Style ---
with st.sidebar:
    st.header("Question Settings")
    selected_topic = st.selectbox("Topic", options=list(TOPICS.keys()), index=0)
    selected_style = st.selectbox("Question style", options=list(QUESTION_STYLES.keys()), index=0)
    if st.button("New Question"):
        st.session_state.pop("question", None)
        st.session_state.pop("active_topic", None)
        st.session_state.pop("active_style", None)

# If topic or style changed, discard the cached question so a new one is generated
settings_changed = (
    st.session_state.get("active_topic") != selected_topic
    or st.session_state.get("active_style") != selected_style
)
if settings_changed:
    st.session_state.pop("question", None)
    st.session_state["active_topic"] = selected_topic
    st.session_state["active_style"] = selected_style

if "question" not in st.session_state:
    with st.spinner("Loading question..."):
        try:
            st.session_state["question"] = generate_question(client, selected_topic, selected_style)
        except Exception as e:
            st.error(f"❌ Failed to generate question: {str(e)}")
            st.stop()

st.write(f"**Prompt:** {st.session_state['question']}")
st.caption("☁️ **Cloud Version** - Shareable with colleagues via link")

audio_bytes = st.audio_input("Record your answer:")

if audio_bytes:
    # --- 2. TRANSCRIPTION: AssemblyAI ---
    with st.spinner("Transcribing audio..."):
        temp_audio_path = "temp_audio.wav"
        try:
            # Save audio file temporarily
            with open(temp_audio_path, "wb") as f:
                f.write(audio_bytes.getbuffer())
            
            # Use AssemblyAI to transcribe
            transcriber = aai.Transcriber()
            transcript = transcriber.transcribe(
                temp_audio_path,
                config=aai.TranscriptionConfig(
                    language_code="en",
                    speech_models=["universal-2"],
                    entity_detection=True
                )
            )
            
            transcript_text = transcript.text
            st.success("✓ Audio transcribed successfully")
            
        except Exception as e:
            st.error(f"❌ Transcription failed: {str(e)}")
            st.stop()
        
        finally:
            # Clean up temporary audio file
            if os.path.exists(temp_audio_path):
                try:
                    os.remove(temp_audio_path)
                except Exception as e:
                    st.warning(f"⚠ Could not delete temp file: {str(e)}")

    # --- 3. EVALUATION: LLM Structured Output (using OpenAI o3-mini) ---
    with st.spinner("Evaluating conceptual accuracy..."):
        system_prompt = f"""You are a general chemistry evaluator. The student was asked: "{st.session_state['question']}"

Read their transcript and evaluate how accurately and completely they answered the question.

You MUST respond in valid JSON format with exactly three keys:
- "Score" (integer out of 10)
- "Feedback" (string, 1-2 sentences)
- "Misconceptions_Flagged" (boolean)

Respond with ONLY the JSON object, no additional text."""
        
        try:
            response = client.chat.completions.create(
                model="o3-mini",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Transcript: {transcript_text}"}
                ],
                timeout=60.0
            )
            
            evaluation = json.loads(response.choices[0].message.content)
            st.success("✓ Evaluation complete")
            
            # Display results in a organized format
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Score", f"{evaluation.get('Score', 'N/A')}/10")
            with col2:
                st.metric("Misconceptions?", "Yes" if evaluation.get('Misconceptions_Flagged') else "No")
            
            st.subheader("📋 Feedback")
            st.info(evaluation.get('Feedback', 'No feedback available'))
            
            # Show full JSON for transparency
            with st.expander("View full evaluation JSON"):
                st.json(evaluation)
            
            # Display transcript for reference
            with st.expander("View transcript"):
                st.text(transcript_text)
            
        except json.JSONDecodeError as e:
            st.error(f"❌ Invalid JSON response from API: {str(e)}")
        except Exception as e:
            st.error(f"❌ Evaluation failed: {str(e)}")