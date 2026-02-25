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

client = OpenAI(api_key=openai_api_key)
aai.settings.api_key = assemblyai_api_key

# --- 1. FRONTEND: Student Interface ---
st.set_page_config(page_title="Oral Exam: General Chemistry", layout="wide")
st.title("Oral Exam: General Chemistry")
st.write("**Prompt:** Explain the Ideal Gas Law ($PV = nRT$). Describe the relationship between the variables and the core assumptions of an ideal gas.")
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
        system_prompt = """You are a general chemistry evaluator. Read the transcript. 
Evaluate if the student accurately explained the Ideal Gas Law, including the proportional relationships between variables, and the assumptions of the kinetic molecular theory (e.g., no intermolecular forces, negligible particle volume).

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