from __future__ import annotations

from pathlib import Path
import sys
import unittest

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from pingpong.live_scores import LiveScoreTracker
from pingpong.transcript_scores import parse_spoken_pair


class ParserTests(unittest.TestCase):
    def test_parse_spoken_number_words(self) -> None:
        self.assertEqual(parse_spoken_pair("Zero one."), (0, 1))
        self.assertEqual(parse_spoken_pair("Fourteen thirteen."), (14, 13))
        self.assertEqual(parse_spoken_pair("Twenty one nineteen."), (21, 19))

    def test_prefers_explicit_digit_pair(self) -> None:
        self.assertEqual(parse_spoken_pair("Okay, game 1, 0-0."), (0, 0))


class LiveScoreTrackerTests(unittest.TestCase):
    def test_accepts_single_point_advances_and_duplicates(self) -> None:
        tracker = LiveScoreTracker(first_server="h")

        duplicate_start = tracker.process_text("zero zero")
        self.assertEqual(duplicate_start.kind, "duplicate")
        self.assertEqual((tracker.state.h, tracker.state.v), (0, 0))

        first = tracker.process_text("zero one")
        self.assertEqual(first.kind, "accepted")
        self.assertEqual(first.winner, "v")
        self.assertEqual((tracker.state.h, tracker.state.v), (0, 1))

        second = tracker.process_text("one one")
        self.assertEqual(second.kind, "accepted")
        self.assertEqual(second.winner, "h")
        self.assertEqual((tracker.state.h, tracker.state.v), (1, 1))

        repeated = tracker.process_text("one one")
        self.assertEqual(repeated.kind, "duplicate")
        self.assertEqual((tracker.state.h, tracker.state.v), (1, 1))
        self.assertEqual(len(tracker.rows()), 2)

    def test_rejects_chatter_that_looks_numeric_but_is_unreachable(self) -> None:
        tracker = LiveScoreTracker(first_server="h")

        event = tracker.process_text("I love you too.")

        self.assertEqual(event.kind, "unreconciled")
        self.assertEqual(event.pair, (0, 2))
        self.assertEqual((tracker.state.h, tracker.state.v), (0, 0))
        self.assertEqual(tracker.rows(), [])

    def test_swapped_order_recovery(self) -> None:
        tracker = LiveScoreTracker(first_server="h")
        tracker.process_text("zero one")

        event = tracker.process_text("two zero")

        self.assertEqual(event.kind, "accepted")
        self.assertEqual(event.winner, "v")
        self.assertEqual((tracker.state.h, tracker.state.v), (0, 2))
        self.assertEqual(tracker.swapped_lines, 1)

    def test_small_inferred_gap_when_enabled(self) -> None:
        tracker = LiveScoreTracker(first_server="h", max_inferred_gap=2)

        event = tracker.process_text("zero two")

        self.assertEqual(event.kind, "accepted")
        self.assertEqual(event.rows_added, 2)
        self.assertEqual((tracker.state.h, tracker.state.v), (0, 2))
        self.assertEqual(tracker.inferred_gap_points, 1)


if __name__ == "__main__":
    unittest.main()
