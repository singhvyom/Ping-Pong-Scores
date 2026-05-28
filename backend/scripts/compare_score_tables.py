#!/usr/bin/env python3
"""Compare two GT-like score tables and report how close they are.

Both files should have rows like:
point,server,winner,h_after,v_after
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def compare_tables(predicted: list[dict[str, str]], truth: list[dict[str, str]]) -> list[str]:
    lines: list[str] = []
    n_pred = len(predicted)
    n_true = len(truth)
    n = min(n_pred, n_true)

    exact_rows = 0
    winner_matches = 0
    server_matches = 0
    score_matches = 0
    mismatch_lines: list[str] = []

    for i in range(n):
        p = predicted[i]
        t = truth[i]

        same_winner = p.get("winner", "").strip().lower() == t.get("winner", "").strip().lower()
        same_server = p.get("server", "").strip().lower() == t.get("server", "").strip().lower()
        same_score = (
            p.get("h_after", "").strip() == t.get("h_after", "").strip()
            and p.get("v_after", "").strip() == t.get("v_after", "").strip()
        )

        if same_winner:
            winner_matches += 1
        if same_server:
            server_matches += 1
        if same_score:
            score_matches += 1
        if same_winner and same_server and same_score:
            exact_rows += 1
        else:
            mismatch_lines.append(
                "point "
                f"{i + 1}: pred=({p.get('server')},{p.get('winner')},{p.get('h_after')},{p.get('v_after')}) "
                f"gt=({t.get('server')},{t.get('winner')},{t.get('h_after')},{t.get('v_after')})"
            )

    lines.append(f"predicted rows: {n_pred}")
    lines.append(f"ground truth rows: {n_true}")
    lines.append(f"compared rows: {n}")
    lines.append(f"exact row matches: {exact_rows}/{n}")
    lines.append(f"winner matches: {winner_matches}/{n}")
    lines.append(f"server matches: {server_matches}/{n}")
    lines.append(f"score matches: {score_matches}/{n}")

    if n_pred != n_true:
        lines.append(f"row count mismatch: predicted {n_pred}, ground truth {n_true}")

    if predicted:
        p_last = predicted[-1]
        lines.append(
            f"predicted final score: {p_last.get('h_after', '?')}-{p_last.get('v_after', '?')}"
        )
    if truth:
        t_last = truth[-1]
        lines.append(
            f"ground truth final score: {t_last.get('h_after', '?')}-{t_last.get('v_after', '?')}"
        )

    if mismatch_lines:
        lines.append("")
        lines.append("mismatches:")
        lines.extend(mismatch_lines)

    return lines


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare predicted score table vs ground-truth score table."
    )
    parser.add_argument("predicted", type=Path, help="Predicted GT-like .txt file")
    parser.add_argument("ground_truth", type=Path, help="Ground-truth GT-like .txt file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Optional report file path",
    )
    args = parser.parse_args()

    pred = args.predicted.resolve()
    gt = args.ground_truth.resolve()
    if not pred.is_file():
        raise SystemExit(f"error: predicted file not found: {pred}")
    if not gt.is_file():
        raise SystemExit(f"error: ground-truth file not found: {gt}")

    report = compare_tables(load_rows(pred), load_rows(gt))
    text = "\n".join(report) + "\n"
    print(text, end="")

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
