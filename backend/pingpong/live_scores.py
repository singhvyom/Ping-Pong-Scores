"""Incremental score tracking for live speech recognition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pingpong.game_state import GameState, Side
from pingpong.transcript_scores import (
    ScoreLogEntry,
    gt_rows_from_replay,
    parse_spoken_pair,
    spoken_to_absolute_hv,
)


EventKind = Literal[
    "accepted",
    "duplicate",
    "ignored",
    "unreconciled",
    "finished",
]


@dataclass(frozen=True)
class LiveScoreEvent:
    """Structured result from processing one recognized phrase."""

    kind: EventKind
    text: str
    pair: tuple[int, int] | None
    message: str
    h: int
    v: int
    server: Side
    winner: Side | None = None
    rows_added: int = 0


@dataclass
class _ReplayLike:
    """Minimal shape needed by ``gt_rows_from_replay``."""

    log: list[ScoreLogEntry]


def _server_after(server: Side, total_before: int, points: int) -> Side:
    flips = (total_before + points) // 5 - total_before // 5
    if flips % 2 == 0:
        return server
    return "v" if server == "h" else "h"


def _find_advance(
    state: GameState, pair: tuple[int, int], max_gap: int
) -> tuple[int, int] | None:
    """Return ``(points, h_wins)`` if ``pair`` can be reached soon."""
    total_before = state.h + state.v
    ai, bi = pair
    for points in range(1, max_gap + 1):
        server_after = _server_after(state.server, total_before, points)
        target_h, target_v = spoken_to_absolute_hv(ai, bi, server_after)
        h_wins = target_h - state.h
        v_wins = target_v - state.v
        if h_wins < 0 or v_wins < 0:
            continue
        if h_wins + v_wins == points:
            return (points, h_wins)
    return None


class LiveScoreTracker:
    """Apply score announcements to a single live ``GameState``."""

    def __init__(
        self,
        *,
        first_server: Side,
        max_inferred_gap: int = 1,
        allow_swapped: bool = True,
    ) -> None:
        if first_server not in ("h", "v"):
            raise ValueError("first_server must be 'h' or 'v'")
        if max_inferred_gap < 1:
            raise ValueError("max_inferred_gap must be >= 1")
        self.state = GameState(h=0, v=0, server=first_server)
        self.max_inferred_gap = max_inferred_gap
        self.allow_swapped = allow_swapped
        self.log: list[ScoreLogEntry] = [
            ScoreLogEntry(
                point_total=0,
                h=0,
                v=0,
                server=first_server,
                winner=None,
                source_line="start",
            )
        ]
        self.ignored = 0
        self.unreconciled = 0
        self.duplicates = 0
        self.inferred_gap_points = 0
        self.swapped_lines = 0

    def process_text(self, text: str) -> LiveScoreEvent:
        """Process one recognized phrase from the live STT loop."""
        clean = text.strip()
        if not clean:
            self.ignored += 1
            return self._event("ignored", clean, None, "empty phrase")
        if self.state.is_finished():
            return self._event("finished", clean, None, "game already finished")

        pair = parse_spoken_pair(clean)
        if pair is None:
            self.ignored += 1
            return self._event("ignored", clean, None, "no score pair found")

        current = spoken_to_absolute_hv(pair[0], pair[1], self.state.server)
        if current == (self.state.h, self.state.v):
            self.duplicates += 1
            return self._event("duplicate", clean, pair, "matches current score")

        match = _find_advance(self.state, pair, self.max_inferred_gap)
        swapped = False
        if match is None and self.allow_swapped:
            swapped_pair = (pair[1], pair[0])
            match = _find_advance(self.state, swapped_pair, self.max_inferred_gap)
            swapped = match is not None

        if match is None:
            self.unreconciled += 1
            return self._event(
                "unreconciled",
                clean,
                pair,
                (
                    f"cannot advance from {self.state.h}-{self.state.v} "
                    f"server={self.state.server!r}"
                ),
            )

        points, h_wins = match
        if swapped:
            self.swapped_lines += 1
        if points > 1:
            self.inferred_gap_points += points - 1

        rows_before = len(self.rows())
        last_winner: Side | None = None
        for i in range(points):
            winner: Side = "h" if i < h_wins else "v"  # type: ignore[assignment]
            self.state.apply_point(winner)
            last_winner = winner
            self.log.append(
                ScoreLogEntry(
                    point_total=self.state.h + self.state.v,
                    h=self.state.h,
                    v=self.state.v,
                    server=self.state.server,
                    winner=winner,
                    source_line=clean if i == points - 1 else f"{clean} (inferred)",
                )
            )

        message = f"accepted {points} point(s)"
        if swapped:
            message += " using swapped order"
        return self._event(
            "accepted",
            clean,
            pair,
            message,
            winner=last_winner,
            rows_added=len(self.rows()) - rows_before,
        )

    def rows(self) -> list[dict[str, str]]:
        return gt_rows_from_replay(_ReplayLike(log=self.log))  # type: ignore[arg-type]

    def _event(
        self,
        kind: EventKind,
        text: str,
        pair: tuple[int, int] | None,
        message: str,
        *,
        winner: Side | None = None,
        rows_added: int = 0,
    ) -> LiveScoreEvent:
        if self.state.is_finished() and kind == "accepted":
            kind = "finished"
            message = f"{message}; final {self.state.h}-{self.state.v}"
        return LiveScoreEvent(
            kind=kind,
            text=text,
            pair=pair,
            message=message,
            h=self.state.h,
            v=self.state.v,
            server=self.state.server,
            winner=winner,
            rows_added=rows_added,
        )
