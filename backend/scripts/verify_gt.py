#!/usr/bin/env python3
"""Replay ground-truth CSVs through pingpong.game_state.GameState and assert consistency.

Usage:
  python backend/scripts/verify_gt.py
  python backend/scripts/verify_gt.py data/game_gt/game1_gt.txt
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# Repo root on sys.path for `import pingpong`
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pingpong.game_state import GameState


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def verify_file(path: Path) -> list[str]:
    rows = load_rows(path)
    issues: list[str] = []
    if not rows:
        issues.append("empty file")
        return issues

    first = rows[0]
    state = GameState(h=0, v=0, server=first["server"].strip().lower())  # type: ignore[arg-type]

    prev_h, prev_v = 0, 0
    for i, row in enumerate(rows):
        p = int(row["point"])
        exp_srv = row["server"].strip().lower()
        w = row["winner"].strip().lower()
        exp_h = int(row["h_after"])
        exp_v = int(row["v_after"])

        if state.h != prev_h or state.v != prev_v:
            issues.append(f"point {p}: expected start ({prev_h},{prev_v}), got ({state.h},{state.v})")
        if state.server != exp_srv:
            issues.append(
                f"point {p}: server want {exp_srv!r}, got {state.server!r} "
                f"(score {state.h}-{state.v})"
            )

        try:
            state.apply_point(w)  # type: ignore[arg-type]
        except Exception as e:
            issues.append(f"point {p}: apply_point failed: {e}")
            break

        if state.h != exp_h or state.v != exp_v:
            issues.append(
                f"point {p}: after winner {w!r} want ({exp_h},{exp_v}), got ({state.h},{state.v})"
            )

        prev_h, prev_v = state.h, state.v

    if not issues and rows:
        last = rows[-1]
        eh, ev = int(last["h_after"]), int(last["v_after"])
        if not state.is_finished():
            issues.append(f"game not finished after last row; state {state.h}-{state.v}")
        elif state.h != eh or state.v != ev:
            issues.append(f"final state mismatch")

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify GT CSV against GameState.")
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        default=[
            Path("data/game_gt/game1_gt.txt"),
            Path("data/game_gt/game2_gt.txt"),
            Path("data/game_gt/game3_gt.txt"),
        ],
        help="GT CSV paths (default: game1..3)",
    )
    args = parser.parse_args()
    any_fail = False
    for f in args.files:
        f = Path(f)
        if not f.is_file():
            print(f"skip (missing): {f}", file=sys.stderr)
            any_fail = True
            continue
        issues = verify_file(f)
        if issues:
            any_fail = True
            print(f"FAIL {f}")
            for x in issues:
                print(f"  {x}")
        else:
            print(f"OK   {f}")
    return 1 if any_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
