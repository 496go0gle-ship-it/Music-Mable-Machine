"""main.py — Music Marble Machine entry point.

Runs every phase end to end:
  Phase 0 audit (done by the caller) -> 1 style -> 2 music -> 3 layout ->
  4 physics -> 5 sound -> 6 render -> 7 mixdown -> 8 assemble -> 9 verify.

Headless: never opens a display; draws to an offscreen Surface and writes
each frame to disk.
"""

from __future__ import annotations

import argparse
import os
import random
import time
from pathlib import Path

# IMPORTANT NOTE 1 & 2: headless, no display.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from config import (BALL_LIFETIME_AFTER_HIT, DEFAULT_STYLE_PRESET, FPS, HEIGHT,
                    LOW_HEIGHT, LOW_WIDTH, SPAWN_Y, STYLE_PRESETS,
                    WIDTH)  # noqa: E402
from layout import build_layout  # noqa: E402
from music_parser import parse_music  # noqa: E402
from physics import PhysicsWorld  # noqa: E402
from renderer import Renderer  # noqa: E402
from sound import SampleBank, render_mixdown  # noqa: E402
from style_analyzer import analyze_style  # noqa: E402
from trajectory import CAM_OFFSET, build_trajectory  # noqa: E402
from video_export import (assemble_video, cleanup_frames, export_midi,
                          verify_output)  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FRAMES = ROOT / "frames"


# ── Phase 10 hooks exposed at the orchestration layer ──────────────────
def set_layout_algorithm(algo: str) -> str:
    """Validate/normalise a layout algorithm name."""
    return algo if algo in ("gravity", "zigzag", "cascade") else "gravity"


def apply_style_preset(preset_name: str) -> dict:
    """Return a copy of a named preset (Phase 10 hook)."""
    import copy
    return copy.deepcopy(STYLE_PRESETS.get(preset_name,
                                           STYLE_PRESETS[DEFAULT_STYLE_PRESET]))


class ActiveBall:
    __slots__ = ("body", "hit_time", "key", "triggered")

    def __init__(self, body, hit_time, key):
        self.body = body
        self.hit_time = hit_time
        self.key = key
        self.triggered = False


def _benchmark_scale(renderer: Renderer, keys) -> float:
    """Render a couple of probe frames; downscale output if drawing is slow."""
    start = time.perf_counter()
    probes = 6
    for _ in range(probes):
        renderer.draw_background(renderer.surface)
        for k in keys:
            renderer.draw_key(renderer.surface, k)
    avg = (time.perf_counter() - start) / probes
    if avg > 1.0 / 30.0:
        print(f"[Phase 6] slow frame draw ({avg*1000:.0f}ms); "
              f"downgrading output to {LOW_WIDTH}x{LOW_HEIGHT}.")
        return LOW_WIDTH / WIDTH
    return 1.0


def render_frames(style, layout, total_duration_sec, key_elasticity=0.5,
                  title="", watermark=""):
    """Phase 6-C main loop. Returns (frame_count, output_w, output_h)."""
    world = PhysicsWorld(key_elasticity=key_elasticity)
    for key in layout.keys:
        key.pymunk_body = world.create_key_segment(key.x, key.y, key.width)
        key.pymunk_body._mm_key = key  # back-reference for hit lookup

    renderer = Renderer(style)
    renderer.title = title
    renderer.watermark = watermark
    renderer.prepare(layout.keys)
    scale = _benchmark_scale(renderer, layout.keys)
    out_w, out_h = int(WIDTH * scale), int(HEIGHT * scale)

    FRAMES.mkdir(parents=True, exist_ok=True)
    dt = 1.0 / FPS
    sim_time = 0.0
    frame_idx = 0
    spawn_ptr = 0
    spawns = layout.spawns
    active: list[ActiveBall] = []

    # Auto-retry envelope for the "balls tunnel through keys" rule.
    while sim_time < total_duration_sec:
        # 1. spawn scheduled balls whose time has arrived
        while spawn_ptr < len(spawns) and spawns[spawn_ptr].spawn_time < sim_time + dt:
            sp = spawns[spawn_ptr]
            body = world.create_ball((sp.spawn_x, SPAWN_Y))
            active.append(ActiveBall(body, sp.hit_time, sp.key))
            spawn_ptr += 1

        # 2. step physics (sub-stepped internally)
        world.step(dt)
        world.drain_hits()  # keep buffer clear; sync is schedule-driven

        # 3. schedule-driven hit -> flash + particles (locked to the audio).
        #    On impact, kick the ball off to the side so it falls away and
        #    never piles up on the flat key.
        for ab in active:
            if not ab.triggered and sim_time >= ab.hit_time:
                ab.triggered = True
                ab.key.flash_timer = 0.12
                renderer.spawn_particles(ab.key.x, ab.key.y)
                ab.body.velocity = (random.uniform(-260, 260), -260)

        # 4. update particles; cull balls that left the screen or have lingered
        #    too long after striking (safety against pile-ups).
        renderer.update_particles(dt)
        survivors = []
        for ab in active:
            off_screen = (ab.body.position.y > HEIGHT + 60
                          or ab.body.position.x < -60 or ab.body.position.x > WIDTH + 60)
            expired = ab.triggered and sim_time > ab.hit_time + BALL_LIFETIME_AFTER_HIT
            if off_screen or expired:
                renderer.forget_ball(ab.body)
                world.remove_ball(ab.body)
            else:
                survivors.append(ab)
        active = survivors

        # 5. render frame
        surf = renderer.surface
        renderer.draw_background(surf)
        for key in layout.keys:
            renderer.draw_key(surf, key, is_flashing=key.flash_timer > 0)
            key.flash_timer = max(0.0, key.flash_timer - dt)
        for ab in active:
            renderer.draw_ball(surf, ab.body)
        renderer.draw_particles(surf)
        if style.get("vignette"):
            renderer.draw_vignette(surf)

        # 6. save frame (downscaled if benchmark asked for it)
        out_surf = surf if scale == 1.0 else pygame.transform.smoothscale(surf, (out_w, out_h))
        pygame.image.save(out_surf, str(FRAMES / f"frame_{frame_idx:06d}.png"))

        sim_time += dt
        frame_idx += 1
        if frame_idx % 120 == 0:
            print(f"[Phase 6] rendered {frame_idx} frames "
                  f"({sim_time:.1f}/{total_duration_sec:.1f}s)...")

    print(f"[Phase 6] done — {frame_idx} frames, {world.collision_count} collisions.")
    return frame_idx, out_w, out_h, world.collision_count


def render_single_ball(style, traj, title="", watermark=""):
    """Phase 6 loop for the single-ball / scrolling-camera model."""
    renderer = Renderer(style)
    renderer.title = title
    renderer.watermark = watermark
    renderer.prepare(traj.keys, by_pitch=True)

    FRAMES.mkdir(parents=True, exist_ok=True)
    dt = 1.0 / FPS
    sim_time = 0.0
    frame_idx = 0
    kp = 0
    keys = traj.keys
    total = traj.total_time

    while sim_time < total:
        bx, by = traj.position(sim_time)
        camera_y = by - CAM_OFFSET

        # trigger any keys whose hit moment has arrived
        while kp < len(keys) and keys[kp].hit_time <= sim_time:
            keys[kp].flash_timer = 0.14
            renderer.spawn_particles(keys[kp].x, keys[kp].y - camera_y)
            kp += 1
        renderer.update_particles(dt)

        surf = renderer.surface
        renderer.draw_bg_scroll(surf, camera_y)
        for key in keys:
            renderer.draw_key_scroll(surf, key, camera_y, is_flashing=key.flash_timer > 0)
            key.flash_timer = max(0.0, key.flash_timer - dt)
        renderer.draw_particles(surf)
        renderer.draw_ball_scroll(surf, (bx, by), camera_y)

        pygame.image.save(surf, str(FRAMES / f"frame_{frame_idx:06d}.png"))
        sim_time += dt
        frame_idx += 1
        if frame_idx % 120 == 0:
            print(f"[Phase 6] rendered {frame_idx} frames ({sim_time:.1f}/{total:.1f}s)...")

    print(f"[Phase 6] done — {frame_idx} frames (single-ball run).")
    return frame_idx


def run(style_image, music_source, output_video, preset, algorithm,
        write_midi=True, title="", watermark=""):
    print("[Phase 0] environment ready.")

    # Phase 1
    style = analyze_style(style_image, preset)

    # Phase 2
    notes, _, source_type = parse_music(music_source)

    # Phase 3: design the single-ball path. The audio plays exactly the notes
    # the marble strikes, so every sound matches a visible hit.
    traj = build_trajectory(notes)
    hit_notes = traj.hit_notes
    total_duration_sec = traj.total_time

    # Phase 5: sample bank (extract from source recording if we have one)
    bank = SampleBank()
    src_wav = ROOT / "audio" / "source.wav"
    if source_type in ("video_url", "audio_file") and src_wav.exists():
        try:
            onsets = [n.time_sec for n in hit_notes]
            midis = [n.midi_note for n in hit_notes]
            bank.extract_from_source(src_wav, onsets, midis)
            print("[Phase 5] done — per-note clips extracted from source audio.")
        except Exception as exc:  # noqa: BLE001
            print(f"[Phase 5] clip extraction failed ({exc}); using synth tones.")
    else:
        print("[Phase 5] done — using synthesised sine tones.")

    # Phase 6
    render_single_ball(style, traj, title=title, watermark=watermark)

    # Phase 7: mix only the struck notes, time-aligned to the hits.
    mixdown = render_mixdown(hit_notes, total_duration_sec, traj.time_offset, bank)

    # Phase 10: also drop a MIDI export alongside the video.
    if write_midi:
        try:
            export_midi(hit_notes, str(ROOT / "audio" / "notes.mid"),
                        time_offset=traj.time_offset)
        except Exception as exc:  # noqa: BLE001
            print(f"[Phase 10] MIDI export skipped ({exc}).")

    # Phase 8
    assemble_video(FRAMES, mixdown, output_video, fps=FPS)

    # Phase 9
    verify_output(output_video)

    # cleanup
    cleanup_frames(FRAMES)


def main():
    ap = argparse.ArgumentParser(description="Music Marble Machine generator")
    ap.add_argument("--style-image", default=os.environ.get("STYLE_IMAGE", ""),
                    help="style reference image path/URL (optional)")
    ap.add_argument("--music-source", default=os.environ.get("MUSIC_SOURCE", ""),
                    help="video/audio URL, audio file, or sheet image (blank = demo)")
    ap.add_argument("--output", default=os.environ.get("OUTPUT_VIDEO",
                    str(ROOT.parent / "marble_machine_output.mp4")))
    ap.add_argument("--preset", default=DEFAULT_STYLE_PRESET,
                    choices=list(STYLE_PRESETS.keys()))
    ap.add_argument("--algorithm", default="gravity",
                    choices=["gravity", "zigzag", "cascade"])
    ap.add_argument("--title", default="", help="title shown at the top")
    ap.add_argument("--watermark", default="", help="watermark shown at the bottom")
    ap.add_argument("--no-midi", action="store_true")
    args = ap.parse_args()

    run(style_image=args.style_image or None,
        music_source=args.music_source or None,
        output_video=args.output,
        preset=args.preset,
        algorithm=args.algorithm,
        write_midi=not args.no_midi,
        title=args.title,
        watermark=args.watermark)


if __name__ == "__main__":
    main()
