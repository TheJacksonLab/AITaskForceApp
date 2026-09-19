import threading
import unittest

from chemviva_core import (
    ANSWER_METHOD,
    CLOSING_MESSAGE,
    SCHEMA_VERSION,
    SHEET_COLUMNS,
    append_closing_turn,
    append_turn_if_expected,
    build_grader_prompt,
    claim_turn,
    completion_metrics,
    count_scaffolding,
    daily_sheet_title,
    deserialize_sheet_values,
    normalize_math_delimiters,
    release_turn,
    serialize_sheet_row,
)


class ConversationTests(unittest.TestCase):
    def test_two_racing_submissions_produce_one_exchange(self):
        state = {}
        conversation = [{"role": "examiner", "content": "Opening question"}]
        turn_key = (3, 0)
        barrier = threading.Barrier(2)
        results = []
        result_lock = threading.Lock()

        def submit():
            barrier.wait()
            claimed = claim_turn(state, turn_key)
            with result_lock:
                results.append(claimed)
            if not claimed:
                return
            succeeded = False
            try:
                self.assertTrue(
                    append_turn_if_expected(conversation, "student", "My answer")
                )
                self.assertTrue(
                    append_turn_if_expected(conversation, "examiner", "Follow-up?")
                )
                succeeded = True
            finally:
                release_turn(state, turn_key, succeeded=succeeded)

        threads = [threading.Thread(target=submit) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(
            [turn["role"] for turn in conversation],
            ["examiner", "student", "examiner"],
        )
        self.assertEqual(
            sum(turn["role"] == "student" for turn in conversation), 1
        )
        self.assertEqual(
            sum(turn["content"] == "Follow-up?" for turn in conversation), 1
        )
        self.assertFalse(claim_turn(state, turn_key))

    def test_turn_append_is_idempotent_in_both_directions(self):
        conversation = [{"role": "examiner", "content": "Question"}]
        self.assertTrue(append_turn_if_expected(conversation, "student", "Answer"))
        self.assertFalse(
            append_turn_if_expected(conversation, "student", "Duplicate answer")
        )
        self.assertTrue(append_turn_if_expected(conversation, "examiner", "Probe"))
        self.assertFalse(
            append_turn_if_expected(conversation, "examiner", "Phantom reply")
        )

    def test_early_close_and_completion_statuses(self):
        abandoned = [{"role": "examiner", "content": "Question"}]
        append_closing_turn(abandoned)
        append_closing_turn(abandoned)
        self.assertEqual(abandoned[-1]["content"], CLOSING_MESSAGE)
        self.assertEqual(len(abandoned), 2)
        self.assertEqual(
            completion_metrics(abandoned, 0, 6, ended_early=True)[
                "completion_status"
            ],
            "abandoned",
        )

        partial = [
            {"role": "examiner", "content": "Question"},
            {"role": "student", "content": "Answer"},
        ]
        self.assertEqual(
            completion_metrics(partial, 1, 6, ended_early=True)[
                "completion_status"
            ],
            "ended_early",
        )
        self.assertEqual(
            completion_metrics(partial * 6, 6, 6, ended_early=False)[
                "completion_status"
            ],
            "complete",
        )


class FormattingAndLoggingTests(unittest.TestCase):
    def test_math_delimiters_normalize_across_lines(self):
        raw = r"Inline \(PV=nRT\), display \[\text{CO}_2 + H_2O\] end"
        self.assertEqual(
            normalize_math_delimiters(raw),
            r"Inline $PV=nRT$, display $$\text{CO}_2 + H_2O$$ end",
        )
        unicode_formulas = "CO₂ Fe₂O₃ NaN₃ Cr₂O₇²⁻"
        self.assertEqual(normalize_math_delimiters(unicode_formulas), unicode_formulas)

    def test_sheet_row_uses_shared_schema_order(self):
        row = {
            "timestamp": "now",
            "answer_method": f"dialogue-{ANSWER_METHOD}",
            "schema_version": SCHEMA_VERSION,
        }
        serialized = serialize_sheet_row(row)
        self.assertEqual(len(serialized), len(SHEET_COLUMNS))
        self.assertEqual(serialized[SHEET_COLUMNS.index("timestamp")], "now")
        self.assertEqual(
            serialized[SHEET_COLUMNS.index("answer_method")], "dialogue-typed"
        )
        self.assertEqual(serialized[-1], SCHEMA_VERSION)

    def test_daily_sheet_title_uses_chicago_calendar_date(self):
        # 04:30 UTC on Sept. 19 is still 11:30 PM on Sept. 18 in Chicago.
        self.assertEqual(
            daily_sheet_title(
                "2025-09-19T04:30:00+00:00", "America/Chicago"
            ),
            "2025-09-18",
        )

    def test_legacy_and_headerless_sheet_rows_are_preserved(self):
        stale_header = [
            "timestamp", "student_name", "student_id", "topic", "style",
            "question", "answer_method", "transcript", "score", "feedback",
            "misconceptions_flagged", "",
        ]
        historical_row = [
            "2025-09-18T15:00:00+00:00", "Student", "123", "Gases", "Gases",
            "Question", "dialogue-typed", "Transcript", "8", "Feedback",
            "False", "consistent_strong",
        ]
        records = deserialize_sheet_values([stale_header, historical_row])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["subtopic"], "Gases")
        self.assertEqual(records[0]["trajectory"], "consistent_strong")
        self.assertEqual(records[0]["completion_status"], "")

        headerless_records = deserialize_sheet_values([historical_row])
        self.assertEqual(headerless_records[0]["student_id"], "123")

    def test_scaffolding_counts_ignore_unknown_values(self):
        counts = count_scaffolding(
            [
                {"type": "probe"},
                {"type": "hint"},
                {"type": "hint"},
                {"type": "unexpected"},
            ]
        )
        self.assertEqual(counts["probe"], 1)
        self.assertEqual(counts["hint"], 2)
        self.assertEqual(counts["supplied_fundamental"], 0)

    def test_grader_prompt_defines_declining_and_length_neutrality(self):
        prompt = build_grader_prompt("Gases", "Explain the pressure change.")
        self.assertIn("Response length is not evidence", prompt)
        self.assertIn(
            '"declining" = started sound but degraded under follow-up', prompt
        )
        self.assertIn(
            '"mixed" = inconsistent throughout with no directional trend', prompt
        )


if __name__ == "__main__":
    unittest.main()
