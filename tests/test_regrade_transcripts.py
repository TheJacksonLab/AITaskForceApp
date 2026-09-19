import math
import unittest

from scripts.regrade_transcripts import correlation, parse_transcript, student_word_count


class ReplayCheckTests(unittest.TestCase):
    def test_transcript_parser_and_student_word_count(self):
        transcript = (
            "[Examiner]: First question?\n\n"
            "[Student]: A concise answer.\n\n"
            "[Examiner]: Follow-up?\n\n"
            "[Student]: Two more words."
        )
        conversation = parse_transcript(transcript)
        self.assertEqual(
            [turn["role"] for turn in conversation],
            ["examiner", "student", "examiner", "student"],
        )
        self.assertEqual(student_word_count(conversation), 6)

    def test_correlation(self):
        self.assertAlmostEqual(correlation([1, 2, 3], [2, 4, 6]), 1.0)
        self.assertTrue(math.isnan(correlation([1, 1], [2, 3])))


if __name__ == "__main__":
    unittest.main()
