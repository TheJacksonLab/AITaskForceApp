"""Pure helpers and shared constants for the ChemViva Streamlit pages."""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Mapping, MutableMapping
from typing import Any


# Typed-only is a deliberate CHEM 202 course policy. Voice input must not be
# re-enabled without the instructor's explicit sign-off.
ANSWER_METHOD = "typed"

SCHEMA_VERSION = "2"

CLOSING_MESSAGE = (
    "Thank you — that brings us to the end of the examination. "
    "I appreciate your responses; your results are being prepared now."
)

SCAFFOLDING_TYPES = (
    "probe",
    "correction",
    "hint",
    "supplied_fundamental",
)

# This tuple is the single source of truth for both the sheet header and row
# serialization order. New fields belong at the end so existing rows retain
# their historical meaning when the header is migrated in place.
SHEET_COLUMNS = (
    "timestamp",
    "student_name",
    "student_id",
    "topic",
    "subtopic",
    "question",
    "answer_method",
    "transcript",
    "score",
    "feedback",
    "misconceptions_flagged",
    "trajectory",
    "completion_status",
    "student_turns",
    "exchanges_completed",
    "scaffolding_probe_count",
    "scaffolding_correction_count",
    "scaffolding_hint_count",
    "scaffolding_supplied_fundamental_count",
    "feedback_flagged_for_review",
    "feedback_review_note",
    "schema_version",
)


_TURN_CLAIM_LOCK = threading.Lock()


def normalize_math_delimiters(text: str) -> str:
    """Convert model-preferred LaTeX delimiters into Streamlit/KaTeX syntax."""
    if not isinstance(text, str):
        return text
    text = re.sub(
        r"\\\[(.*?)\\\]",
        lambda match: f"$${match.group(1)}$$",
        text,
        flags=re.DOTALL,
    )
    return re.sub(
        r"\\\((.*?)\\\)",
        lambda match: f"${match.group(1)}$",
        text,
        flags=re.DOTALL,
    )


def normalize_conversation(conversation: list[dict[str, str]]) -> list[dict[str, str]]:
    """Normalize every stored turn in place and return the conversation."""
    for turn in conversation:
        turn["content"] = normalize_math_delimiters(turn.get("content", ""))
    return conversation


def claim_turn(
    state: MutableMapping[str, Any], turn_key: tuple[int, int]
) -> bool:
    """Atomically claim an attempt/exchange pair for processing.

    A completed key remains recorded, making a stale double-submit idempotent.
    Call :func:`release_turn` with ``succeeded=False`` after a failed transaction
    so the student can retry the same exchange.
    """
    with _TURN_CLAIM_LOCK:
        processed = set(state.get("processed_turn_keys", ()))
        if state.get("turn_in_flight") is not None or turn_key in processed:
            return False
        state["turn_in_flight"] = turn_key
        processed.add(turn_key)
        state["processed_turn_keys"] = list(processed)
        return True


def release_turn(
    state: MutableMapping[str, Any], turn_key: tuple[int, int], *, succeeded: bool
) -> None:
    """Release an in-flight claim, retaining only successful processed keys."""
    with _TURN_CLAIM_LOCK:
        if state.get("turn_in_flight") == turn_key:
            state.pop("turn_in_flight", None)
        if not succeeded:
            processed = set(state.get("processed_turn_keys", ()))
            processed.discard(turn_key)
            state["processed_turn_keys"] = list(processed)


def append_turn_if_expected(
    conversation: list[dict[str, str]], role: str, content: str
) -> bool:
    """Append a turn only when it preserves examiner/student alternation."""
    expected_previous = "examiner" if role == "student" else "student"
    if role not in {"student", "examiner"}:
        raise ValueError(f"Unsupported conversation role: {role}")
    if not conversation or conversation[-1].get("role") != expected_previous:
        return False
    conversation.append(
        {"role": role, "content": normalize_math_delimiters(content.strip())}
    )
    return True


def append_closing_turn(conversation: list[dict[str, str]]) -> None:
    """Append the deterministic close once, including after an early exit."""
    if conversation and conversation[-1].get("content") == CLOSING_MESSAGE:
        return
    conversation.append({"role": "examiner", "content": CLOSING_MESSAGE})


def completion_metrics(
    conversation: list[dict[str, str]],
    exchanges_completed: int,
    max_exchanges: int,
    *,
    ended_early: bool,
) -> dict[str, int | str]:
    """Return the explicit completion fields written to the results sheet."""
    student_turns = sum(turn.get("role") == "student" for turn in conversation)
    if student_turns == 0:
        status = "abandoned"
    elif ended_early or exchanges_completed < max_exchanges:
        status = "ended_early"
    else:
        status = "complete"
    return {
        "completion_status": status,
        "student_turns": student_turns,
        "exchanges_completed": exchanges_completed,
    }


def empty_scaffolding_counts() -> dict[str, int]:
    return {kind: 0 for kind in SCAFFOLDING_TYPES}


def count_scaffolding(items: list[dict[str, Any]]) -> dict[str, int]:
    """Count validated examiner scaffolding classifications."""
    counts = empty_scaffolding_counts()
    for item in items:
        kind = item.get("type")
        if kind in counts:
            counts[kind] += 1
    return counts


def format_transcript(conversation: list[dict[str, str]]) -> str:
    return "\n\n".join(
        f"[{'Examiner' if turn['role'] == 'examiner' else 'Student'}]: {turn['content']}"
        for turn in conversation
    )


def build_grader_prompt(topic: str, opening_question: str) -> str:
    """Build the production grading rubric used by the app and replay check."""
    return (
        f"You are a general chemistry professor grading an oral examination.\n\n"
        f"TOPIC: {topic}\n"
        f"OPENING QUESTION: {opening_question}\n\n"
        "EVIDENCE DISCIPLINE (read first):\n"
        "- Base your assessment ONLY on what the student actually wrote. Never credit, "
        "assume, or invent reasoning the student did not express.\n"
        "- The exam may have been ended early, so the transcript can be short. Grade only "
        "the responses that are present; never reward a student for questions they did not "
        "answer.\n"
        "- If the student gave few responses, or responses with little substance, the score "
        "MUST be low (1-4) and the feedback must state plainly that too little was "
        "demonstrated to judge deeper understanding. Do not be congratulatory in this case.\n\n"
        "GRADING PHILOSOPHY:\n"
        "- Credit only the understanding the student demonstrated through THEIR OWN reasoning. "
        "Do NOT credit ideas, terms, or steps that the examiner's questions supplied or led them to.\n"
        "- Response length is not evidence of understanding. A concise, correct, complete answer "
        "must score the same as a verbose answer expressing the same chemistry; padding, repetition, "
        "and restatement earn no credit.\n"
        "- Use the FULL 1-10 range and apply the bands below literally. Do NOT default to high "
        "scores: an ordinary performance is not a 9-10. Reserve 9-10 for genuinely exceptional, "
        "independent mastery, which is uncommon.\n"
        "- Trajectory, effort, and engagement are only minor tie-breakers between otherwise-adjacent "
        "scores — never a way to lift a weak performance. Improvement that happened ONLY because the "
        "examiner walked the student there step by step is NOT evidence of independent understanding.\n"
        "- Hedging or guessing that happens to land near a correct idea (\"I think\", \"maybe\", "
        "\"I'm not sure\", \"I can't remember the equation\") is NOT mastery and caps the score in "
        "the lower-middle bands.\n"
        "- Inability to recall or apply the governing fundamentals (e.g. the relevant equation or "
        "balanced reaction), even if the student eventually stumbles toward them after prompting, "
        "caps the score at 4 or below.\n"
        "- Reward intellectual honesty and self-correction, but only as a tie-breaker.\n"
        "- Penalize persistent, uncorrected misconceptions.\n"
        "- Do not penalize a student for asking clarifying questions about the question itself.\n\n"
        "SCORING GUIDE (use the whole range; most students are not 9-10):\n"
        "- 9-10: Exceptional. Independently accurate and precise throughout, strong reasoning, correct "
        "terminology, real depth; little or no prompting needed.\n"
        "- 7-8: Strong. Mostly accurate and largely independent; correct core reasoning with only minor "
        "gaps or imprecision.\n"
        "- 5-6: Partial. Grasps the basic idea and some correct elements, but with real gaps, vagueness, "
        "or an error, and needed noticeable prompting; little depth.\n"
        "- 3-4: Weak. Major gaps or misconceptions; could not recall or apply the governing fundamentals "
        "even with prompting; only fragmentary correct pieces, often via guessing.\n"
        "- 1-2: No meaningful understanding or engagement.\n\n"
        "Respond in valid JSON with exactly these four keys:\n"
        '- "Score" (integer 1-10)\n'
        '- "Feedback" (string, 2-3 sentences: what they did well, what they struggled with, overall assessment)\n'
        '- "Misconceptions_Flagged" (boolean: true ONLY if the student actually expressed an '
        "incorrect belief that went uncorrected by the end — NOT for gaps, vagueness, "
        '"I don\'t know", or an incomplete-but-not-wrong answer)\n'
        '- "Trajectory" (string, use exactly one definition: "improving" = understanding became '
        'clearly stronger across follow-ups; "consistent_strong" = sound throughout; '
        '"consistent_weak" = weak throughout; "declining" = started sound but degraded under '
        'follow-up; "mixed" = inconsistent throughout with no directional trend)\n\n'
        "Respond with ONLY the JSON object, no additional text."
    )


def grade_conversation(
    client: Any,
    conversation: list[dict[str, str]],
    topic: str,
    opening_question: str,
) -> dict[str, Any]:
    """Holistically grade a transcript with the production rubric."""
    if not any(turn["role"] == "student" for turn in conversation):
        return {
            "Score": 1,
            "Feedback": "No responses were provided, so there was nothing to assess. "
            "The examination was ended before any question was answered.",
            "Misconceptions_Flagged": False,
            "Trajectory": "consistent_weak",
        }
    response = client.chat.completions.create(
        model="gpt-5.1",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": build_grader_prompt(topic, opening_question),
            },
            {
                "role": "user",
                "content": f"TRANSCRIPT:\n\n{format_transcript(conversation)}",
            },
        ],
        timeout=60.0,
    )
    return json.loads(response.choices[0].message.content)


def serialize_sheet_row(row: Mapping[str, Any]) -> list[Any]:
    """Serialize a named row in exactly the shared sheet-column order."""
    return [row.get(column, "") for column in SHEET_COLUMNS]
