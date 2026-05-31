"""video_export.py — Phase 8 (assemble), Phase 9 (verify) + Phase 10 hooks.

ffmpeg muxes the PNG frame sequence with the mixdown WAV into the final MP4,
ffprobe verifies the result, then the frame directory is cleaned up.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRAMES = ROOT / "frames"


def assemble_video(frames_dir: Path, audio_wav: Path, out_path: str,
                   fps: int = 60) -> str:
    """Phase 8: encode frames + audio into an H.264/AAC MP4."""
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", str(Path(frames_dir) / "frame_%06d.png"),
        "-i", str(audio_wav),
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    print(f"[Phase 8] done — video assembled -> {out_path}")
    return out_path


def verify_output(out_path: str) -> bool:
    """Phase 9: ffprobe the output and assert video+audio streams exist."""
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", out_path],
        capture_output=True, text=True,
    )
    info = json.loads(probe.stdout)
    streams = {s["codec_type"]: s for s in info["streams"]}
    assert "video" in streams, "ERROR: No video stream found"
    assert "audio" in streams, "ERROR: No audio stream found"
    duration = float(info["format"].get("duration",
                                         streams["video"].get("duration", 0)))
    assert duration > 1.0, "ERROR: Video too short"
    v = streams["video"]
    print(f"✅ Output video verified: {out_path}")
    print(f"   Duration  : {duration:.2f}s")
    print(f"   Resolution: {v['width']}x{v['height']}")
    print(f"   FPS       : {v['r_frame_rate']}")
    return True


def cleanup_frames(frames_dir: Path = FRAMES) -> None:
    """Delete PNG frames to reclaim disk space."""
    frames_dir = Path(frames_dir)
    if frames_dir.exists():
        for png in frames_dir.glob("frame_*.png"):
            png.unlink()
    print("[Phase 8] frames cleaned up.")


# ── Phase 10 extension hooks ───────────────────────────────────────────
def export_midi(notes, path: str, time_offset: float = 0.0,
                program: int = 0) -> str:
    """Phase 10 hook: write the NoteEvent list out as a MIDI file."""
    import pretty_midi
    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=program)
    for ev in notes:
        start = ev.time_sec + time_offset
        inst.notes.append(pretty_midi.Note(
            velocity=100, pitch=int(ev.midi_note),
            start=start, end=start + max(0.1, ev.duration_sec)))
    pm.instruments.append(inst)
    pm.write(path)
    print(f"[Phase 10] MIDI exported -> {path}")
    return path


def record_section(in_path: str, out_path: str,
                   start_sec: float, end_sec: float) -> str:
    """Phase 10 hook: export only [start_sec, end_sec] of the finished video."""
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(start_sec), "-to", str(end_sec),
         "-i", in_path, "-c", "copy", out_path],
        check=True, capture_output=True, text=True,
    )
    print(f"[Phase 10] section [{start_sec},{end_sec}] -> {out_path}")
    return out_path
