#!/usr/bin/env python3
"""Replay exported ChemViva transcripts through the production grader rubric.

This is intentionally an opt-in API regression check rather than part of the
offline unit suite. It reports trajectory diversity and score/word-count
correlation for the same sampled sessions before and after regrading.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import random
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from openai import OpenAI

from chemviva_core import grade_conversation


TURN_RE = re.compile(r"\[(Examiner|Student)\]:\s*(.*?)(?=\n\n\[(?:Examiner|Student)\]:|\Z)", re.DOTALL)


def parse_transcript(text: str) -> list[dict[str, str]]:
    return [
        {
            "role": "examiner" if label == "Examiner" else "student",
            "content": content.strip(),
        }
        for label, content in TURN_RE.findall(text or "")
    ]


def student_word_count(conversation: list[dict[str, str]]) -> int:
    return sum(
        len(re.findall(r"\b\w+\b", turn["content"]))
        for turn in conversation
        if turn["role"] == "student"
    )


def correlation(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2 or len(xs) != len(ys):
        return math.nan
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denominator = math.sqrt(
        sum((x - mean_x) ** 2 for x in xs) * sum((y - mean_y) ** 2 for y in ys)
    )
    return numerator / denominator if denominator else math.nan


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", help="Google Sheet CSV export")
    parser.add_argument("--sample-size", type=int, default=12)
    parser.add_argument("--seed", type=int, default=20250918)
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY must be set")

    with open(args.csv_path, newline="", encoding="utf-8-sig") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("transcript")]
    random.Random(args.seed).shuffle(rows)
    rows = rows[: min(args.sample_size, len(rows))]
    if len(rows) < 2:
        parser.error("At least two transcripts are required")

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], max_retries=5)
    old_scores = []
    new_scores = []
    word_counts = []
    trajectories = []

    for index, row in enumerate(rows, 1):
        conversation = parse_transcript(row["transcript"])
        if not conversation:
            raise ValueError(f"Could not parse transcript in sampled row {index}")
        topic = row.get("subtopic") or row.get("topic") or "General Chemistry"
        opening_question = row.get("question") or conversation[0]["content"]
        result = grade_conversation(client, conversation, topic, opening_question)
        old_scores.append(float(row["score"]) if row.get("score") else math.nan)
        new_scores.append(float(result["Score"]))
        word_counts.append(float(student_word_count(conversation)))
        trajectories.append(result["Trajectory"])

    paired_old = [
        (words, score)
        for words, score in zip(word_counts, old_scores)
        if not math.isnan(score)
    ]
    old_r = correlation(
        [pair[0] for pair in paired_old], [pair[1] for pair in paired_old]
    )
    new_r = correlation(word_counts, new_scores)
    distribution = Counter(trajectories)

    print(f"Regraded sessions: {len(rows)}")
    print(f"Trajectory distribution: {dict(sorted(distribution.items()))}")
    print(f"Original score/word-count correlation: {old_r:.3f}")
    print(f"New score/word-count correlation: {new_r:.3f}")

    if len(distribution) < 2:
        raise AssertionError(
            "Trajectory distribution is degenerate; inspect the grader prompt/results"
        )


if __name__ == "__main__":
    main()
