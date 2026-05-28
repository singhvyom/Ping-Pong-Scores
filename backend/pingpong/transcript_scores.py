"""Parse score announcements from transcript lines and advance :class:`GameState`.

Each spoken line is treated as the score **before** the next rally, in **server-first,
receiver-second** order (same as your house rules). We walk consecutive readings and
apply exactly one point whenever the absolute (H, V) moves by one point.

The parser tolerates:

- Digit pairs like ``11-7`` and English number words like ``"eleven seven"`` or
  ``"twenty one nineteen"``.
- Repeated identical announcements (callers re-saying the same score).
- Short Whisper gaps where one or two announcements are missing — we infer the
  intervening winners by matching the announced board to a small forward search.
- Single-line order inversions (``"six seven"`` instead of ``"seven six"``); we
  retry with the swapped pair if the announced order can't be reconciled.

Anything we can't reconcile becomes a non-fatal entry in ``ReplayResult.errors``;
the replay keeps going so the comparison script can still get partial output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from pingpong.game_state import GameState, Side

_TS_PREFIX = re.compile(r"^\[[^\]]+\]\s*")
_SCORE_PAIR = re.compile(
    r"\b(\d{1,2})\s*[-–:]\s*(\d{1,2})\b",
)
_TOKEN = re.compile(r"\d+|[a-z]+")

_WORD_NUMBERS: dict[str, int] = {
    "zero": 0, "oh": 0, "o": 0, "nil": 0, "love": 0,
    "one": 1, "won": 1,
    "two": 2, "to": 2, "too": 2,
    "three": 3,
    "four": 4, "for": 4, "fore": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8, "ate": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17, "seveneen": 17,
    "eighteen": 18,
    "nineteen": 19, "nineteenth": 19,
    "twenty": 20,
    "thirty": 30,
}
_TENS: dict[str, int] = {"twenty": 20, "thirty": 30}
_ONES: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9,
}

_MAX_VALID_NUM = 30


def strip_timestamp_prefix(line: str) -> str:
    return _TS_PREFIX.sub("", line.strip())


def _extract_numbers(text: str) -> list[int]:
    """Return all integers found in ``text``, in order, supporting English words.

    Tokens are read left-to-right; ``"twenty"``/``"thirty"`` may merge with a
    following ones word (``"twenty one"`` -> ``21``). Anything outside ``0..30``
    is dropped (likely a mishear or unrelated number).
    """
    tokens = _TOKEN.findall(text.lower())
    out: list[int] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.isdigit():
            n = int(t)
            i += 1
        elif t in _TENS:
            n = _TENS[t]
            if i + 1 < len(tokens) and tokens[i + 1] in _ONES:
                n += _ONES[tokens[i + 1]]
                i += 2
            else:
                i += 1
        elif t in _WORD_NUMBERS:
            n = _WORD_NUMBERS[t]
            i += 1
        else:
            i += 1
            continue
        if 0 <= n <= _MAX_VALID_NUM:
            out.append(n)
    return out


def parse_spoken_pair(line: str) -> tuple[int, int] | None:
    """Return the (server_first, receiver_second) pair of integers on the line.

    Strategy:

    1. Prefer an explicit ``"a-b"`` digit pair (handles ``"0-0"`` cleanly even
       when the line also contains stray digits like ``"game 1"``).
    2. Otherwise extract every numeric token (digits + English words) and take
       the **last two**. Score calls usually end the sentence, and this avoids
       ordinals like ``"game 1"`` or ``"point 27"`` polluting the result.
    """
    s = strip_timestamp_prefix(line)
    m = _SCORE_PAIR.search(s)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if 0 <= a <= _MAX_VALID_NUM and 0 <= b <= _MAX_VALID_NUM:
            return (a, b)
    nums = _extract_numbers(s)
    if len(nums) < 2:
        return None
    return (nums[-2], nums[-1])


def spoken_to_absolute_hv(
    server_first: int, recv_second: int, server: Side
) -> tuple[int, int]:
    """Map announced order to absolute (H_score, V_score)."""
    if server == "h":
        return (server_first, recv_second)
    return (recv_second, server_first)


@dataclass
class ScoreLogEntry:
    point_total: int
    h: int
    v: int
    server: Side
    winner: Side | None = None
    source_line: str = ""


@dataclass
class ReplayResult:
    state: GameState
    log: list[ScoreLogEntry] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped_duplicate_lines: int = 0
    inferred_gap_points: int = 0
    swapped_order_lines: int = 0


def _server_after(server: Side, total_before: int, k: int) -> Side:
    """Server in effect after ``k`` consecutive points starting from ``total_before``.

    Service flips on every total that is a positive multiple of 5.
    """
    flips = (total_before + k) // 5 - total_before // 5
    if flips % 2 == 0:
        return server
    return "v" if server == "h" else "h"


def _find_advance(
    state: GameState, ai: int, bi: int, max_gap: int
) -> tuple[int, int] | None:
    """Smallest ``k`` in ``[1, max_gap]`` whose post-point board matches the
    announced ``(ai, bi)`` decoded with the resulting server.

    Returns ``(k, h_wins)`` where the remaining ``k - h_wins`` points go to V.
    The per-point ordering inside a multi-point gap is ambiguous; callers pick
    a deterministic order (currently H-wins-first).
    """
    total_before = state.h + state.v
    for k in range(1, max_gap + 1):
        new_server = _server_after(state.server, total_before, k)
        target_h, target_v = spoken_to_absolute_hv(ai, bi, new_server)
        i_h = target_h - state.h
        i_v = target_v - state.v
        if i_h < 0 or i_v < 0 or i_h + i_v != k:
            continue
        return (k, i_h)
    return None


def replay_transcript(
    lines: list[str],
    first_server: Side,
    *,
    require_opening_0_0: bool = True,
    max_inferred_gap: int = 4,
) -> ReplayResult:
    """Advance game state from transcript lines; return final state and score log.

    Each line is the score **announced before** the next rally, in **server-first**
    order for **that** rally. Consecutive lines therefore use **different** server
    orientations whenever service rotates.

    For each parsed line we:

    * Skip it as a duplicate if it decodes to the current board.
    * Otherwise search for the smallest 1..``max_inferred_gap`` step advance whose
      resulting board matches the announcement. Multi-step matches indicate a
      missed announcement; per-point winners are recorded H-first as a
      deterministic fallback (the order isn't recoverable from the audio alone).
    * If the announced order can't be reconciled, retry with the pair swapped
      (handles ``"six seven"`` mistakenly spoken instead of ``"seven six"``);
      this is recorded under ``swapped_order_lines``.
    * Anything still unreconciled is logged to ``errors`` and skipped.
    """
    state = GameState(h=0, v=0, server=first_server)
    out = ReplayResult(state=state, log=[])

    parsed: list[tuple[str, tuple[int, int]]] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        pair = parse_spoken_pair(line)
        if pair is None:
            continue
        parsed.append((line, pair))

    if not parsed:
        out.errors.append("no score pairs found in transcript")
        return out

    first_line, (fa, fb) = parsed[0]
    abs0 = spoken_to_absolute_hv(fa, fb, state.server)
    if require_opening_0_0 and abs0 != (0, 0):
        out.errors.append(
            f"first score must read 0-0 for opening server={state.server!r}; "
            f"got spoken ({fa},{fb}) -> HV {abs0} (line: {first_line!r})"
        )
        return out

    out.log.append(
        ScoreLogEntry(
            point_total=0,
            h=0,
            v=0,
            server=state.server,
            winner=None,
            source_line=first_line,
        )
    )

    i = 1
    while i < len(parsed):
        if state.is_finished():
            break

        li, (ai, bi) = parsed[i]
        cur_dec = spoken_to_absolute_hv(ai, bi, state.server)
        if (state.h, state.v) == cur_dec:
            out.skipped_duplicate_lines += 1
            i += 1
            continue

        match = _find_advance(state, ai, bi, max_inferred_gap)
        swapped = False
        if match is None:
            match = _find_advance(state, bi, ai, max_inferred_gap)
            swapped = match is not None

        if match is None:
            out.errors.append(
                f"line {i} {li!r}: cannot advance from "
                f"{state.h}-{state.v} server={state.server!r} within "
                f"{max_inferred_gap} points (parsed pair {ai},{bi})"
            )
            i += 1
            continue

        if swapped:
            out.swapped_order_lines += 1
            out.errors.append(
                f"line {i} {li!r}: interpreted as swapped pair "
                f"({bi},{ai}) to fit {state.h}-{state.v} server={state.server!r}"
            )

        k, h_wins = match
        if k > 1:
            out.inferred_gap_points += k - 1

        for j in range(k):
            if state.is_finished():
                out.errors.append(
                    f"line {i}: game finished while filling inferred gap"
                )
                break
            winner: Side = "h" if j < h_wins else "v"  # type: ignore[assignment]
            try:
                state.apply_point(winner)
            except ValueError as exc:
                out.errors.append(f"line {i}: apply_point failed: {exc}")
                break
            out.log.append(
                ScoreLogEntry(
                    point_total=state.h + state.v,
                    h=state.h,
                    v=state.v,
                    server=state.server,
                    winner=winner,
                    source_line=li if j == k - 1 else f"{li} (inferred)",
                )
            )
        i += 1

    return out


def gt_rows_from_replay(result: ReplayResult) -> list[dict[str, str]]:
    """Convert replay output into GT-like rows.

    Output schema matches the hand-authored files:
    ``point,server,winner,h_after,v_after``

    The `server` column is the server *before* that point, so it comes from the
    previous log entry (which represents the board announced before the rally).
    """
    rows: list[dict[str, str]] = []
    if len(result.log) < 2:
        return rows

    for i in range(1, len(result.log)):
        before = result.log[i - 1]
        after = result.log[i]
        if after.winner is None:
            continue
        rows.append(
            {
                "point": str(i),
                "server": before.server,
                "winner": after.winner,
                "h_after": str(after.h),
                "v_after": str(after.v),
            }
        )
    return rows


def write_gt_rows(path: str | Path, rows: list[dict[str, str]]) -> None:
    """Write GT-like score rows as a CSV-formatted .txt file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines_out = ["point,server,winner,h_after,v_after"]
    for row in rows:
        lines_out.append(
            ",".join(
                [
                    row["point"],
                    row["server"],
                    row["winner"],
                    row["h_after"],
                    row["v_after"],
                ]
            )
        )
    p.write_text("\n".join(lines_out) + "\n", encoding="utf-8")
