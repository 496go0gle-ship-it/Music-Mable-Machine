"""music_parser.py — Phase 2: turn a music source into a list of NoteEvents.

Supports four source kinds:
  * video_url  : yt-dlp -> wav -> librosa onset/pitch analysis
  * audio_file : local wav/mp3 -> librosa analysis
  * sheet_image: Claude Vision transcription -> notes
  * demo       : built-in melody (no input required)
"""

from __future__ import annotations

import base64
import json
import math
import os
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from config import VISION_MODEL

AUDIO = Path(__file__).resolve().parent.parent / "audio"
ASSETS = Path(__file__).resolve().parent.parent / "assets"


@dataclass
class NoteEvent:
    time_sec: float
    midi_note: int
    duration_sec: float

    def as_dict(self) -> dict:
        return asdict(self)


# ── Source type detection (Phase 2-A) ──────────────────────────────────
def detect_source_type(music_source: str | None) -> str:
    if not music_source:
        return "demo"
    if music_source.startswith("http"):
        return "video_url"
    ext = Path(music_source).suffix.lower()
    if ext in (".jpg", ".jpeg", ".png", ".pdf"):
        return "sheet_image"
    return "audio_file"


# ── Demo melody ────────────────────────────────────────────────────────
def _demo_notes() -> list[NoteEvent]:
    """'Twinkle Twinkle' style C-major phrase — guarantees a runnable output."""
    bpm = 120
    spb = 60.0 / bpm
    # (midi, beats) pairs
    seq = [(60, 1), (60, 1), (67, 1), (67, 1), (69, 1), (69, 1), (67, 2),
           (65, 1), (65, 1), (64, 1), (64, 1), (62, 1), (62, 1), (60, 2)]
    notes, t = [], 0.0
    for midi, beats in seq:
        notes.append(NoteEvent(time_sec=t, midi_note=midi, duration_sec=beats * spb * 0.9))
        t += beats * spb
    return notes


# ── Audio analysis (Phase 2-B-i / audio_file) ──────────────────────────
def _download_audio(url: str, retries: int = 3) -> Path | None:
    AUDIO.mkdir(parents=True, exist_ok=True)
    out_tmpl = str(AUDIO / "source.%(ext)s")
    for attempt in range(1, retries + 1):
        try:
            subprocess.run(
                ["yt-dlp", "-x", "--audio-format", "wav", "-o", out_tmpl, url],
                check=True, capture_output=True, text=True,
            )
            wav = AUDIO / "source.wav"
            if wav.exists():
                return wav
        except Exception as exc:  # noqa: BLE001
            print(f"[Phase 2] yt-dlp attempt {attempt}/{retries} failed: {exc}")
            time.sleep(2 * attempt)
    return None


def _analyze_audio(wav_path: Path) -> list[NoteEvent]:
    import librosa
    import numpy as np

    y, sr = librosa.load(str(wav_path), mono=True)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    tempo = float(np.atleast_1d(tempo)[0])  # newer librosa returns an array
    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, backtrack=True)
    onset_times = librosa.frames_to_time(onset_frames, sr=sr)

    f0 = librosa.yin(y, fmin=librosa.note_to_hz("C2"),
                     fmax=librosa.note_to_hz("C7"), sr=sr)
    times = librosa.times_like(f0, sr=sr)

    notes: list[NoteEvent] = []
    onset_list = list(onset_times)
    for i, onset in enumerate(onset_list):
        nxt = onset_list[i + 1] if i + 1 < len(onset_list) else onset + 0.4
        mask = (times >= onset) & (times < nxt)
        seg = f0[mask]
        seg = seg[np.isfinite(seg) & (seg > 0)]
        if seg.size == 0:
            continue
        midi = int(round(librosa.hz_to_midi(float(np.median(seg)))))
        midi = max(36, min(96, midi))
        notes.append(NoteEvent(time_sec=float(onset),
                               midi_note=midi,
                               duration_sec=float(min(nxt - onset, 0.6))))
    print(f"[Phase 2] audio analysis: tempo~{tempo:.0f} BPM, "
          f"{len(notes)} note events.")
    return notes


# ── Sheet music transcription (Phase 2-B-ii) ───────────────────────────
_SHEET_PROMPT = """You are a music transcription AI. Analyze this sheet music image.
Return ONLY a valid JSON object with:
{
  "bpm": 120,
  "time_signature": "4/4",
  "key": "C major",
  "notes": [
    {"bar": 1, "beat": 1.0, "midi_note": 60, "duration_beats": 1.0}
  ]
}
midi_note follows MIDI standard (C4 = 60). Include all visible notes in order.
No markdown, no preamble."""


def _transcribe_sheet(image_path: str) -> list[NoteEvent]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set; cannot transcribe sheet music.")
    import anthropic

    src = Path(image_path).expanduser()
    media = "image/png"
    suffix = src.suffix.lower()
    if suffix in (".jpg", ".jpeg"):
        media = "image/jpeg"
    elif suffix == ".pdf":
        media = "application/pdf"

    client = anthropic.Anthropic(api_key=api_key)
    b64 = base64.standard_b64encode(src.read_bytes()).decode()
    block_type = "document" if media == "application/pdf" else "image"
    msg = client.messages.create(
        model=VISION_MODEL,
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {"type": block_type,
                 "source": {"type": "base64", "media_type": media, "data": b64}},
                {"type": "text", "text": _SHEET_PROMPT},
            ],
        }],
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1].lstrip("json").strip()
    data = json.loads(text)
    bpm = float(data.get("bpm", 120))
    bars_seen: dict = {}
    notes: list[NoteEvent] = []
    for n in data["notes"]:
        # absolute beat within the piece
        bar = float(n.get("bar", 1))
        beat = float(n.get("beat", 1.0))
        # assume 4 beats/bar unless time signature says otherwise
        beats_per_bar = 4.0
        ts = data.get("time_signature", "4/4")
        try:
            beats_per_bar = float(ts.split("/")[0])
        except Exception:  # noqa: BLE001
            pass
        abs_beat = (bar - 1) * beats_per_bar + (beat - 1)
        time_sec = abs_beat / (bpm / 60.0)
        dur = float(n.get("duration_beats", 1.0)) / (bpm / 60.0)
        notes.append(NoteEvent(time_sec=time_sec,
                               midi_note=int(n["midi_note"]),
                               duration_sec=dur))
    print(f"[Phase 2] sheet transcription: {len(notes)} notes at {bpm:.0f} BPM.")
    return notes


# ── Public entry point ─────────────────────────────────────────────────
def parse_music(music_source: str | None) -> tuple[list[NoteEvent], float, str]:
    """Return (sorted NoteEvents, total_duration_sec, source_type).

    Implements the ERROR HANDLING fallbacks: network failure -> demo,
    too-few-notes -> raised error with a helpful message.
    """
    source_type = detect_source_type(music_source)
    notes: list[NoteEvent] = []

    if source_type == "video_url":
        wav = _download_audio(music_source)
        if wav is None:
            print("[Phase 2] download failed after retries; falling back to demo melody.")
            notes, source_type = _demo_notes(), "demo"
        else:
            notes = _analyze_audio(wav)
    elif source_type == "audio_file":
        notes = _analyze_audio(Path(music_source).expanduser())
    elif source_type == "sheet_image":
        notes = _transcribe_sheet(music_source)
    else:
        notes = _demo_notes()

    # Phase 2-C: validate & sort
    notes.sort(key=lambda n: n.time_sec)
    unique = {n.midi_note for n in notes}
    if len(unique) < 4:
        raise SystemExit("Could not detect enough notes. "
                         "Please provide a clearer image.")

    last = notes[-1]
    total_duration_sec = last.time_sec + last.duration_sec + 2.0
    print(f"[Phase 2] done — {len(notes)} notes, {len(unique)} unique pitches, "
          f"duration {total_duration_sec:.1f}s (source: {source_type}).")
    return notes, total_duration_sec, source_type
