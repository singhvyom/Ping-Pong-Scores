"""Single-game state: first to 21, win by 2, service switches every 5 total points."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Side = Literal["h", "v"]


def is_valid_single_point_step(
    before: tuple[int, int], after: tuple[int, int]
) -> bool:
    """True iff `after` is exactly one rally from `before` (one side +1, the other unchanged)."""
    x, y = before
    xh, yh = after
    return (xh, yh) in ((x + 1, y), (x, y + 1))


@dataclass
class GameState:
    """Track score and who serves the next rally.

    Service rule: after each point, if the total points scored (h + v) is a
    positive multiple of 5, the server switches for the *next* rally.
    """

    h: int = 0
    v: int = 0
    server: Side = "h"

    def legal_next_scores(self) -> tuple[tuple[int, int], tuple[int, int]]:
        """Only two scores are reachable in one rally from the current (h, v)."""
        x, y = self.h, self.v
        return ((x + 1, y), (x, y + 1))

    def apply_point(self, winner: Side) -> None:
        if self.is_finished():
            raise ValueError("Game already finished")
        before = (self.h, self.v)
        w = winner.lower()
        if w == "h":
            self.h += 1
        elif w == "v":
            self.v += 1
        else:
            raise ValueError(f"winner must be 'h' or 'v', got {winner!r}")

        after = (self.h, self.v)
        if not is_valid_single_point_step(before, after):
            self.h, self.v = before
            raise ValueError(
                f"invariant: after one point scores must be ({before[0] + 1}, {before[1]}) "
                f"or ({before[0]}, {before[1] + 1}); got {after}"
            )

        total = self.h + self.v
        if total > 0 and total % 5 == 0:
            self.server = "v" if self.server == "h" else "h"

    def is_finished(self) -> bool:
        a, b = self.h, self.v
        hi, lo = max(a, b), min(a, b)
        if hi < 21:
            return False
        return (hi - lo) >= 2

    def winner_side(self) -> Side | None:
        if not self.is_finished():
            return None
        return "h" if self.h > self.v else "v"
