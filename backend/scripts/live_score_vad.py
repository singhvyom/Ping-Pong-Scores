#!/usr/bin/env python3
"""Live mic -> VAD chunks -> Whisper -> ping-pong score table.

Usage:
  python backend/scripts/live_score_vad.py --first-server h --model tiny
  python backend/scripts/live_score_vad.py --list-devices
  python backend/scripts/live_score_vad.py --first-server v --debug-vad
"""

from __future__ import annotations

import argparse
from datetime import datetime
import sys
import tempfile
from pathlib import Path
import wave

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pingpong.live_scores import LiveScoreTracker
from pingpong.transcript_scores import write_gt_rows
from pingpong.vad import SpeechSegment, iter_speech_segments, list_input_devices


def _device_arg(value: str) -> int | str:
    return int(value) if value.isdigit() else value


def _default_path(kind: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if kind == "predicted":
        return Path("data/runs") / f"live_{stamp}_predicted.txt"
    if kind == "transcript":
        return Path("data/transcripts") / f"live_{stamp}.txt"
    raise ValueError(f"unknown path kind: {kind}")


def _write_temp_wav(segment: SpeechSegment) -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()
    with wave.open(str(tmp_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(segment.sample_rate)
        wav.writeframes(segment.pcm)
    return tmp_path


def transcribe_segment(model, segment: SpeechSegment, *, language: str) -> str:
    wav_path = _write_temp_wav(segment)
    try:
        result = model.transcribe(
            str(wav_path),
            language=language,
            verbose=False,
            fp16=False,
        )
    finally:
        wav_path.unlink(missing_ok=True)
    return str(result.get("text") or "").strip()


def _append_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Live microphone score tracker using WebRTC VAD + Whisper."
    )
    parser.add_argument(
        "--first-server",
        choices=("h", "v"),
        help="Who serves before point 1 (required unless --list-devices is used)",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="Print sounddevice input/output devices and exit",
    )
    parser.add_argument(
        "--device",
        type=_device_arg,
        default=None,
        help="Optional sounddevice device id/name",
    )
    parser.add_argument(
        "--model",
        default="base",
        choices=("tiny", "base", "small", "medium", "large"),
        help="Whisper model size (default: base; tiny is useful for latency)",
    )
    parser.add_argument(
        "--language",
        default="en",
        help="Language code passed to Whisper (default: en)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="GT-like row output (default: data/runs/live_<timestamp>_predicted.txt)",
    )
    parser.add_argument(
        "--transcript-out",
        type=Path,
        default=None,
        help="Recognized phrase log (default: data/transcripts/live_<timestamp>.txt)",
    )
    parser.add_argument(
        "--no-transcript-out",
        action="store_true",
        help="Do not write recognized phrases to a transcript file",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=16000,
        help="Mic sample rate for VAD (default: 16000)",
    )
    parser.add_argument(
        "--frame-ms",
        type=int,
        default=30,
        choices=(10, 20, 30),
        help="WebRTC VAD frame size in ms (default: 30)",
    )
    parser.add_argument(
        "--vad-mode",
        type=int,
        default=2,
        choices=(0, 1, 2, 3),
        help="WebRTC VAD aggressiveness 0..3 (default: 2)",
    )
    parser.add_argument(
        "--min-speech-ms",
        type=int,
        default=250,
        help="Drop shorter speech bursts (default: 250)",
    )
    parser.add_argument(
        "--end-silence-ms",
        type=int,
        default=600,
        help="Silence needed to close a speech segment (default: 600)",
    )
    parser.add_argument(
        "--max-segment-ms",
        type=int,
        default=4000,
        help="Force a chunk boundary after this duration (default: 4000)",
    )
    parser.add_argument(
        "--max-inferred-gap",
        type=int,
        default=1,
        help="Max points to infer from one live phrase (default: 1)",
    )
    parser.add_argument(
        "--no-swapped",
        action="store_true",
        help="Disable swapped-order recovery",
    )
    parser.add_argument(
        "--debug-vad",
        action="store_true",
        help="Print VAD segment timings without running Whisper/scoring",
    )
    args = parser.parse_args()

    if args.list_devices:
        print(list_input_devices())
        return 0
    if args.first_server is None:
        parser.error("--first-server is required unless --list-devices is used")

    output = args.output or _default_path("predicted")
    transcript_out = None
    if not args.no_transcript_out:
        transcript_out = args.transcript_out or _default_path("transcript")

    print("Starting live VAD score tracker", file=sys.stderr)
    print(f"Output: {output}", file=sys.stderr)
    if transcript_out is not None:
        print(f"Transcript: {transcript_out}", file=sys.stderr)

    tracker = LiveScoreTracker(
        first_server=args.first_server,
        max_inferred_gap=args.max_inferred_gap,
        allow_swapped=not args.no_swapped,
    )
    write_gt_rows(output, tracker.rows())

    model = None
    if not args.debug_vad:
        import whisper

        print(f"Loading Whisper model {args.model!r}", file=sys.stderr)
        model = whisper.load_model(args.model)

    try:
        for segment in iter_speech_segments(
            sample_rate=args.sample_rate,
            frame_ms=args.frame_ms,
            vad_mode=args.vad_mode,
            min_speech_ms=args.min_speech_ms,
            end_silence_ms=args.end_silence_ms,
            max_segment_ms=args.max_segment_ms,
            device=args.device,
        ):
            rel_start = segment.start_time
            if args.debug_vad:
                print(
                    f"segment {segment.duration_ms}ms "
                    f"({segment.frames} frames, start={rel_start:.2f})"
                )
                continue

            text = transcribe_segment(model, segment, language=args.language)
            if transcript_out is not None:
                _append_line(transcript_out, text)

            event = tracker.process_text(text)
            if event.rows_added:
                write_gt_rows(output, tracker.rows())

            pair = "-" if event.pair is None else f"{event.pair[0]},{event.pair[1]}"
            print(
                f"{event.kind.upper():12s} score={event.h}-{event.v} "
                f"server={event.server} pair={pair} "
                f"text={text!r} :: {event.message}"
            )

            if tracker.state.is_finished():
                write_gt_rows(output, tracker.rows())
                print(
                    f"Final {tracker.state.h}-{tracker.state.v}, "
                    f"winner {tracker.state.winner_side()}",
                    file=sys.stderr,
                )
                return 0
    except KeyboardInterrupt:
        print("\nStopped by user.", file=sys.stderr)
    finally:
        write_gt_rows(output, tracker.rows())

    print(
        f"Stopped at {tracker.state.h}-{tracker.state.v} "
        f"(server {tracker.state.server}); rows written to {output}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
