#!/usr/bin/env python3
"""Transcribe audio to a text file: one line per Whisper speech segment.

Requires: pip install -r requirements.txt
System: ffmpeg must be on PATH (e.g. brew install ffmpeg on macOS) for m4a/mp3.

Usage:
  python backend/scripts/transcribe_audio.py data/game_audio/Game1.m4a
  python backend/scripts/transcribe_audio.py data/game_audio/Game1.m4a -o data/transcripts/game1.txt
  python backend/scripts/transcribe_audio.py data/game_audio/Game1.m4a --model small --timestamps
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path
import whisper


def _format_ts(seconds: float) -> str:
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m:d}:{s:05.2f}"


def transcribe_audio_lines(
    audio: Path,
    *,
    model_name: str = "base",
    language: str = "en",
    timestamps: bool = False,
) -> list[str]:
    """Transcribe an audio file and return one line per Whisper segment."""
    model = whisper.load_model(model_name)
    result = model.transcribe(
        str(audio),
        language=language,
        verbose=False,
    )

    segments = result.get("segments") or []
    lines: list[str] = []
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        if timestamps:
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", 0.0))
            prefix = f"[{_format_ts(start)}-{_format_ts(end)}] "
            lines.append(prefix + text)
        else:
            lines.append(text)
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Transcribe audio to a .txt file (one line per segment)."
    )
    parser.add_argument(
        "audio",
        type=Path,
        help="Input audio file (e.g. .m4a, .wav, .mp3)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output .txt path (default: data/transcripts/<stem>.txt)",
    )
    parser.add_argument(
        "--model",
        default="base",
        choices=("tiny", "base", "small", "medium", "large"),
        help="Whisper model size (default: base)",
    )
    parser.add_argument(
        "--timestamps",
        action="store_true",
        help="Prefix each line with [mm:ss.ss-mm:ss.ss] from the segment times",
    )
    parser.add_argument(
        "--language",
        default="en",
        help="Language code passed to Whisper (default: en)",
    )
    args = parser.parse_args()

    audio = args.audio.resolve()
    if not audio.is_file():
        print(f"error: audio file not found: {audio}", file=sys.stderr)
        return 1

    out = args.output
    if out is None:
        out = Path("data/transcripts") / f"{audio.stem}.txt"
    else:
        out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading Whisper model {args.model!r}", file=sys.stderr)
    print(f"Transcribing {audio} ...", file=sys.stderr)
    lines = transcribe_audio_lines(
        audio,
        model_name=args.model,
        language=args.language,
        timestamps=args.timestamps,
    )

    out.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    print(f"Wrote {len(lines)} line(s) to {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
