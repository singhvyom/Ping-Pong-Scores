#!/usr/bin/env python3
"""Transcribe one audio file and emit a GT-shaped score table.

Output rows look like:
point,server,winner,h_after,v_after
1,h,v,0,1
2,h,h,1,1

Usage:
  python backend/scripts/audio_to_score_table.py data/game_audio/Game1.m4a --first-server h
  python backend/scripts/audio_to_score_table.py data/game_audio/Game1.m4a --first-server h \
      -o data/runs/game1_predicted.txt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from pingpong.transcript_scores import gt_rows_from_replay, replay_transcript, write_gt_rows
from transcribe_audio import transcribe_audio_lines


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audio in -> GT-like score table out."
    )
    parser.add_argument("audio", type=Path, help="Input audio file (.m4a/.wav/.mp3)")
    parser.add_argument(
        "--first-server",
        required=True,
        choices=("h", "v"),
        help="Who serves before point 1",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output GT-like .txt file (default: data/runs/<stem>_predicted.txt)",
    )
    parser.add_argument(
        "--model",
        default="base",
        choices=("tiny", "base", "small", "medium", "large"),
        help="Whisper model size (default: base)",
    )
    parser.add_argument(
        "--language",
        default="en",
        help="Language code passed to Whisper (default: en)",
    )
    parser.add_argument(
        "--transcript-out",
        type=Path,
        default=None,
        help="Optional raw transcript output for debugging",
    )
    parser.add_argument(
        "--no-require-0-0",
        action="store_true",
        help="Allow the first decoded score to be something other than 0-0",
    )
    args = parser.parse_args()

    audio = args.audio.resolve()
    if not audio.is_file():
        print(f"error: audio file not found: {audio}", file=sys.stderr)
        return 1

    out = args.output or Path("data/runs") / f"{audio.stem}_predicted.txt"
    transcript_out = args.transcript_out

    print(f"Loading Whisper model {args.model!r}", file=sys.stderr)
    print(f"Transcribing {audio} ...", file=sys.stderr)
    lines = transcribe_audio_lines(
        audio,
        model_name=args.model,
        language=args.language,
        timestamps=False,
    )

    if transcript_out is not None:
        transcript_out.parent.mkdir(parents=True, exist_ok=True)
        transcript_out.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        print(f"Wrote transcript to {transcript_out}", file=sys.stderr)

    result = replay_transcript(
        lines,
        args.first_server,
        require_opening_0_0=not args.no_require_0_0,
    )
    rows = gt_rows_from_replay(result)
    write_gt_rows(out, rows)

    print(f"Wrote {len(rows)} predicted point row(s) to {out}", file=sys.stderr)
    if result.errors:
        print("Replay errors:", file=sys.stderr)
        for err in result.errors:
            print(f"  {err}", file=sys.stderr)
        return 1

    if result.state.is_finished():
        print(
            f"Final {result.state.h}-{result.state.v}, winner {result.state.winner_side()}",
            file=sys.stderr,
        )
    else:
        print(
            f"Incomplete: {result.state.h}-{result.state.v} (server {result.state.server})",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
