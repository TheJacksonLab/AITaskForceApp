"""
Instructor Dashboard — CHEM202 Oral Exam
Standalone Streamlit page. Does NOT import from app.py.
"""

import streamlit as st
import json
import os
import pandas as pd

import gspread
from google.oauth2.service_account import Credentials


# ── Secret helpers ────────────────────────────────────────────────────────────
def _get_secret(key: str):
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key)


INSTRUCTOR_PASSWORD = _get_secret("INSTRUCTOR_PASSWORD") or ""
GOOGLE_CREDS_STR    = _get_secret("GOOGLE_SHEETS_CREDENTIALS") or ""
GOOGLE_SHEET_NAME   = _get_secret("GOOGLE_SHEET_NAME") or "CHEM202_OralExam_Submissions"

SHEET_COLUMNS = [
    "timestamp", "student_name", "student_id", "topic", "style",
    "question", "answer_method", "transcript", "score",
    "feedback", "misconceptions_flagged",
]


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Instructor Dashboard — CHEM202", layout="wide")
st.title("Instructor Dashboard — CHEM202")


# ── Password Gate ─────────────────────────────────────────────────────────────
if "instructor_authenticated" not in st.session_state:
    st.session_state["instructor_authenticated"] = False

if not st.session_state["instructor_authenticated"]:
    st.subheader("Instructor Login")
    with st.form("instructor_login_form"):
        password_input = st.text_input("Password", type="password")
        login_btn = st.form_submit_button("Log In")
    if login_btn:
        if not INSTRUCTOR_PASSWORD:
            st.error("❌ INSTRUCTOR_PASSWORD secret is not configured.")
        elif password_input == INSTRUCTOR_PASSWORD:
            st.session_state["instructor_authenticated"] = True
            st.rerun()
        else:
            st.error("❌ Incorrect password.")
    st.stop()


# ── Google Sheets data loader ─────────────────────────────────────────────────
@st.cache_data(ttl=60)
def load_sheet_data() -> pd.DataFrame:
    if not GOOGLE_CREDS_STR:
        raise ValueError("GOOGLE_SHEETS_CREDENTIALS secret is not configured.")

    creds_dict = json.loads(GOOGLE_CREDS_STR)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open(GOOGLE_SHEET_NAME)
    records = sh.sheet1.get_all_records()

    if not records:
        return pd.DataFrame(columns=SHEET_COLUMNS)

    df = pd.DataFrame(records)
    df["score"] = pd.to_numeric(df["score"], errors="coerce")
    df["misconceptions_flagged"] = df["misconceptions_flagged"].apply(
        lambda v: str(v).strip().lower() in ("true", "1", "yes")
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    return df


# ── Load data ─────────────────────────────────────────────────────────────────
try:
    df = load_sheet_data()
except Exception as e:
    st.error(f"❌ Failed to load Google Sheet data: {e}")
    st.stop()

if df.empty:
    st.info("No submissions yet. Data will appear here once students complete the exam.")
    st.stop()


# ── Sidebar: Filters ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    all_topics = sorted(df["topic"].dropna().unique().tolist())
    selected_topics = st.multiselect(
        "Filter by Topic",
        options=all_topics,
        default=all_topics,
    )
    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()

filtered_df = df[df["topic"].isin(selected_topics)] if selected_topics else df


# ── Section 1: Summary Metrics ────────────────────────────────────────────────
st.subheader("Summary")
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Submissions", len(filtered_df))
with col2:
    st.metric("Unique Students", filtered_df["student_id"].nunique())
with col3:
    avg = filtered_df["score"].mean()
    st.metric("Avg Score", f"{avg:.1f}/10" if not pd.isna(avg) else "—")
with col4:
    misc_rate = filtered_df["misconceptions_flagged"].mean() * 100
    st.metric("Misconception Rate", f"{misc_rate:.0f}%" if not pd.isna(misc_rate) else "—")


# ── Section 2: Full Submissions Table ─────────────────────────────────────────
st.subheader("All Submissions")
st.dataframe(
    filtered_df[[
        "timestamp", "student_name", "student_id", "topic", "style",
        "answer_method", "score", "misconceptions_flagged", "feedback",
    ]],
    use_container_width=True,
)


# ── Section 3: Average Score by Topic ────────────────────────────────────────
st.subheader("Average Score by Topic")
avg_score = (
    filtered_df.groupby("topic")["score"]
    .agg(avg_score="mean", submissions="count")
    .reset_index()
    .rename(columns={"avg_score": "Average Score", "submissions": "Submissions"})
    .sort_values("Average Score", ascending=False)
)
avg_score["Average Score"] = avg_score["Average Score"].round(2)
st.dataframe(avg_score, use_container_width=True)
st.bar_chart(avg_score.set_index("topic")["Average Score"])


# ── Section 4: Misconception Rate by Topic ────────────────────────────────────
st.subheader("Misconception Rate by Topic")
misc_rate_df = (
    filtered_df.groupby("topic")["misconceptions_flagged"]
    .agg(
        misconception_rate=lambda x: round(x.mean() * 100, 1),
        submissions="count",
    )
    .reset_index()
    .rename(columns={"misconception_rate": "Misconception Rate (%)", "submissions": "Submissions"})
    .sort_values("Misconception Rate (%)", ascending=False)
)
st.dataframe(misc_rate_df, use_container_width=True)
st.bar_chart(misc_rate_df.set_index("topic")["Misconception Rate (%)"])


# ── Section 5: CSV Export ─────────────────────────────────────────────────────
st.subheader("Export Data")
csv_bytes = filtered_df.to_csv(index=False).encode("utf-8")
st.download_button(
    label="Download filtered submissions as CSV",
    data=csv_bytes,
    file_name="chem202_oral_exam_submissions.csv",
    mime="text/csv",
)
