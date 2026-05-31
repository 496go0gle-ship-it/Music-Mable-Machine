"""sound.py — Phase 5 (synthesis) and Phase 7 (audio mixdown).

Builds a per-MIDI-note sample bank (sine + ADSR by default, or custom WAVs /
clips sliced from a source recording) and renders the whole NoteEvent
timeline into a single WAV that is later muxed onto the video.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from config import SAMPLE_RATE, midi_to_freq

AUDIO = Path(__file__).resolve().parent.parent / "audio"


def synth_note(midi_note: int, duration: float = 0.5,
               sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Pure sine tone for a MIDI note with a short attack/release envelope."""
    freq = midi_to_freq(midi_note)
    n = max(1, int(sample_rate * duration))
    t = np.linspace(0, duration, n, endpoint=False)
    wave = 0.5 * np.sin(2 * np.pi * freq * t)
    # add a soft 2nd harmonic so it reads as a "note" rather than a beep
    wave += 0.15 * np.sin(2 * np.pi * 2 * freq * t)
    attack = min(int(0.01 * sample_rate), n // 2)
    release = min(int(0.10 * sample_rate), n - attack)
    if attack > 0:
        wave[:attack] *= np.linspace(0, 1, attack)
    if release > 0:
        wave[-release:] *= np.linspace(1, 0, release)
    return wave.astype(np.float32)


class SampleBank:
    """Holds one waveform per MIDI note; synthesises lazily on demand."""

    def __init__(self, sample_rate: int = SAMPLE_RATE):
        self.sample_rate = sample_rate
        self._samples: dict[int, np.ndarray] = {}
        self._custom: dict[int, np.ndarray] = {}  # Phase 10 hook overrides

    def load_custom_instrument(self, midi_note: int, wav_path: str) -> None:
        """Phase 10 hook: replace a note's sample with an external WAV."""
        from scipy.io import wavfile
        sr, data = wavfile.read(wav_path)
        data = data.astype(np.float32)
        if data.ndim > 1:
            data = data.mean(axis=1)
        peak = np.max(np.abs(data)) or 1.0
        self._custom[midi_note] = (data / peak * 0.6).astype(np.float32)

    def extract_from_source(self, source_wav: Path, onsets, midis,
                            clip_len: float = 0.4) -> None:
        """Phase 5-1: slice short clips around onsets as per-note samples."""
        from scipy.io import wavfile
        sr, data = wavfile.read(str(source_wav))
        data = data.astype(np.float32)
        if data.ndim > 1:
            data = data.mean(axis=1)
        peak = np.max(np.abs(data)) or 1.0
        data /= peak
        n_clip = int(clip_len * sr)
        for onset, midi in zip(onsets, midis):
            start = int(onset * sr)
            clip = data[start:start + n_clip]
            if clip.size:
                self._custom.setdefault(midi, (clip * 0.6).astype(np.float32))

    def get(self, midi_note: int, duration: float = 0.5) -> np.ndarray:
        if midi_note in self._custom:
            return self._custom[midi_note]
        key = midi_note
        if key not in self._samples:
            self._samples[key] = synth_note(midi_note, duration, self.sample_rate)
        return self._samples[key]


def render_mixdown(notes, total_duration_sec: float, time_offset: float,
                   bank: SampleBank, out_path: Path | str | None = None) -> Path:
    """Phase 7: sum every note's sample into one WAV at its (offset) time."""
    from scipy.io import wavfile

    AUDIO.mkdir(parents=True, exist_ok=True)
    out_path = Path(out_path) if out_path else AUDIO / "mixdown.wav"
    sr = bank.sample_rate
    total = int(total_duration_sec * sr) + sr  # +1s tail headroom
    track = np.zeros(total, dtype=np.float32)

    for ev in notes:
        sample = bank.get(ev.midi_note, max(0.2, ev.duration_sec))
        start = int((ev.time_sec + time_offset) * sr)
        end = min(total, start + sample.size)
        if start < total:
            track[start:end] += sample[: end - start]

    peak = np.max(np.abs(track))
    if peak > 1.0:
        track /= peak  # prevent clipping
    pcm = (track * 32767).astype(np.int16)
    wavfile.write(str(out_path), sr, pcm)
    print(f"[Phase 7] done — mixdown written ({total_duration_sec:.1f}s) -> {out_path}")
    return out_path
