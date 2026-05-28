"""Live microphone speech segmentation using WebRTC VAD.

The rest of the scoring pipeline wants complete speech chunks. This module keeps
the microphone and WebRTC details in one place and yields timestamped PCM
segments that can be handed to Whisper or saved as WAV for debugging.
"""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Iterator


SUPPORTED_SAMPLE_RATES = (8000, 16000, 32000, 48000)
SUPPORTED_FRAME_MS = (10, 20, 30)


@dataclass(frozen=True)
class SpeechSegment:
    """A complete voiced segment from the microphone."""

    pcm: bytes
    sample_rate: int
    start_time: float
    end_time: float
    frames: int

    @property
    def duration_s(self) -> float:
        return self.end_time - self.start_time

    @property
    def duration_ms(self) -> int:
        return int(round(self.duration_s * 1000))


def _require_live_audio_deps():
    try:
        import sounddevice as sd  # type: ignore[import-not-found]
        import webrtcvad  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "live VAD dependencies are missing; run `pip install -r requirements.txt`"
        ) from exc
    return sd, webrtcvad


def list_input_devices() -> str:
    """Return a printable table of available PortAudio devices."""
    sd, _ = _require_live_audio_deps()
    return str(sd.query_devices())


def iter_speech_segments(
    *,
    sample_rate: int = 16000,
    frame_ms: int = 30,
    vad_mode: int = 2,
    min_speech_ms: int = 250,
    end_silence_ms: int = 600,
    max_segment_ms: int = 4000,
    device: int | str | None = None,
) -> Iterator[SpeechSegment]:
    """Yield speech chunks from the default microphone.

    Args:
        sample_rate: WebRTC-compatible sample rate. Defaults to 16 kHz.
        frame_ms: Frame size in milliseconds; WebRTC accepts 10/20/30 ms.
        vad_mode: WebRTC aggressiveness 0..3, where 3 is most aggressive.
        min_speech_ms: Drop shorter voiced bursts.
        end_silence_ms: End a segment after this much trailing silence.
        max_segment_ms: Force a segment boundary after this duration.
        device: Optional sounddevice device id/name.
    """
    if sample_rate not in SUPPORTED_SAMPLE_RATES:
        raise ValueError(f"sample_rate must be one of {SUPPORTED_SAMPLE_RATES}")
    if frame_ms not in SUPPORTED_FRAME_MS:
        raise ValueError(f"frame_ms must be one of {SUPPORTED_FRAME_MS}")
    if not 0 <= vad_mode <= 3:
        raise ValueError("vad_mode must be between 0 and 3")
    if min_speech_ms <= 0 or end_silence_ms <= 0 or max_segment_ms <= 0:
        raise ValueError("speech/silence durations must be positive")

    sd, webrtcvad = _require_live_audio_deps()
    vad = webrtcvad.Vad(vad_mode)
    samples_per_frame = sample_rate * frame_ms // 1000
    bytes_per_frame = samples_per_frame * 2
    max_frames = max(1, max_segment_ms // frame_ms)
    end_silence_frames = max(1, end_silence_ms // frame_ms)
    min_speech_frames = max(1, min_speech_ms // frame_ms)

    segment_frames: list[bytes] = []
    voiced_frames = 0
    trailing_silence = 0
    segment_start: float | None = None

    with sd.RawInputStream(
        samplerate=sample_rate,
        blocksize=samples_per_frame,
        channels=1,
        dtype="int16",
        device=device,
    ) as stream:
        while True:
            data, overflowed = stream.read(samples_per_frame)
            frame = bytes(data)
            if len(frame) != bytes_per_frame:
                continue

            is_speech = bool(vad.is_speech(frame, sample_rate))
            now = time.monotonic()
            if overflowed:
                # Keep running; a dropped frame is less harmful than killing a
                # live session. The CLI can expose this by enabling debug output.
                pass

            if is_speech and not segment_frames:
                segment_start = now - (frame_ms / 1000)

            if segment_frames or is_speech:
                segment_frames.append(frame)

            if not segment_frames:
                continue

            if is_speech:
                voiced_frames += 1
                trailing_silence = 0
            else:
                trailing_silence += 1

            segment_is_long = len(segment_frames) >= max_frames
            segment_is_done = trailing_silence >= end_silence_frames
            if not segment_is_long and not segment_is_done:
                continue

            pcm = b"".join(segment_frames)
            end_time = now
            if voiced_frames >= min_speech_frames and segment_start is not None:
                yield SpeechSegment(
                    pcm=pcm,
                    sample_rate=sample_rate,
                    start_time=segment_start,
                    end_time=end_time,
                    frames=len(segment_frames),
                )

            segment_frames = []
            voiced_frames = 0
            trailing_silence = 0
            segment_start = None
