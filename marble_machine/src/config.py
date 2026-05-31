"""config.py — Shared constants, style presets, and small helpers.

Centralises everything the other modules need so values stay consistent
across layout, physics, rendering and export.
"""

from __future__ import annotations

import math

# ── Phase 3-A: Canvas / physics constants ──────────────────────────────
# Vertical 9:16 (TikTok/Reels) by default to match the reference aesthetic.
WIDTH, HEIGHT = 720, 1280
FPS = 60
GRAVITY = 980          # pixels/sec^2 (screen space, +y is down)
BALL_RADIUS = 17
KEY_WIDTH = 92
KEY_HEIGHT = 26
SPAWN_X = WIDTH // 2
SPAWN_Y = 60
SIDE_MARGIN = 70       # horizontal margin for lane placement

# Vertical band that keys are allowed to occupy (Phase 3-B clamp).
# Leaves room for a title at the top and a watermark at the bottom.
KEY_Y_MIN = 230
KEY_Y_MAX = HEIGHT - 200

# Low-resolution fallback (ERROR HANDLING: slow frame generation).
LOW_WIDTH, LOW_HEIGHT = 540, 960

# Visual tidiness: cap how many lanes/keys we draw.  When a source has more
# unique pitches than this, pitches are folded by pitch class (note name) so
# keys never overlap and stay readable.
MAX_LANES = 14

# Seconds a ball stays on screen after it strikes its key, then it is removed
# so balls never pile into columns on the flat keys.
BALL_LIFETIME_AFTER_HIT = 0.45

SAMPLE_RATE = 44100

# Anthropic model used for vision calls (style + sheet music).
VISION_MODEL = "claude-sonnet-4-20250514"


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    """'#RRGGBB' (or 'RRGGBB') -> (r, g, b)."""
    value = value.lstrip("#")
    if len(value) == 3:  # allow shorthand like #abc
        value = "".join(c * 2 for c in value)
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def midi_to_freq(midi_note: int) -> float:
    """MIDI note number -> frequency in Hz (A4 = 69 = 440 Hz)."""
    return 440.0 * (2 ** ((midi_note - 69) / 12.0))


def midi_to_name(midi_note: int) -> str:
    """MIDI note number -> human label, e.g. 60 -> 'C4'."""
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    octave = midi_note // 12 - 1
    return f"{names[midi_note % 12]}{octave}"


def fall_time(drop_distance: float, gravity: float = GRAVITY) -> float:
    """Free-fall time to cover `drop_distance` pixels under `gravity`."""
    if drop_distance <= 0:
        return 0.0
    return math.sqrt(2.0 * drop_distance / gravity)


# ── TRENDING STYLE PRESETS (2025-2026) ─────────────────────────────────
STYLE_PRESETS = {
    "neon_dark": {
        # Deep Glow + Retro-Futurism (neon on dark)
        "background_color": "#0a0a12",
        "accent_color": "#00fff7",
        "palette": ["#0a0a12", "#141428", "#1e1e3c", "#00fff7", "#ff3cac"],
        "ball_style": {"shape": "circle", "fill": "#ffffff", "stroke": "#00fff7", "glow_radius": 20},
        "key_style": {"shape": "rounded_rect", "fill": "#1a1a3a", "stroke": "#00fff7",
                      "hit_flash_color": "#ff3cac", "label_font": "monospace"},
        "wall_style": {"fill": "#10101e", "pattern": "scanline"},
        "particle_effect": "sparks", "motion_blur": True, "vignette": True,
    },
    "signal_90s": {
        # Signal Graphics (90s TV ident, explosive colour)
        "background_color": "#0d0d0d",
        "accent_color": "#ffdd00",
        "palette": ["#0d0d0d", "#ff2d2d", "#ffdd00", "#00ccff", "#ffffff"],
        "ball_style": {"shape": "circle", "fill": "#ffdd00", "stroke": "#ff2d2d", "glow_radius": 0},
        "key_style": {"shape": "rect", "fill": "#ff2d2d", "stroke": "#ffffff",
                      "hit_flash_color": "#ffffff", "label_font": "sans"},
        "wall_style": {"fill": "#1a1a1a", "pattern": "grid"},
        "particle_effect": "pixels", "motion_blur": False, "vignette": False,
    },
    "minimal_white": {
        # Minimalist Maximalism — white base, bold balls
        "background_color": "#f8f8f4",
        "accent_color": "#1a1a1a",
        "palette": ["#f8f8f4", "#e0e0d8", "#c8c8c0", "#1a1a1a", "#ff4500"],
        "ball_style": {"shape": "circle", "fill": "#1a1a1a", "stroke": "#f8f8f4", "glow_radius": 0},
        "key_style": {"shape": "rounded_rect", "fill": "#1a1a1a", "stroke": "#f8f8f4",
                      "hit_flash_color": "#ff4500", "label_font": "serif"},
        "wall_style": {"fill": "#e8e8e0", "pattern": "dots"},
        "particle_effect": "rings", "motion_blur": False, "vignette": False,
    },
    "retro_wood": {
        # Acoustic wood grain — Wintergatan-style original
        "background_color": "#1c1008",
        "accent_color": "#d4a843",
        "palette": ["#1c1008", "#3b2410", "#6b4020", "#d4a843", "#f5e4c0"],
        "ball_style": {"shape": "circle", "fill": "#c8c8c8", "stroke": "#808080", "glow_radius": 0},
        "key_style": {"shape": "rect", "fill": "#d4a843", "stroke": "#8b6914",
                      "hit_flash_color": "#ffffff", "label_font": "serif"},
        "wall_style": {"fill": "#2a1808", "pattern": "none"},
        "particle_effect": "petals", "motion_blur": False, "vignette": True,
    },
    "concrete_marble": {
        # Photoreal-ish 3D studio look (spicy.motion reference):
        # light concrete wall, chrome-bracketed glossy colour bars, glossy
        # marble, soft cast shadows.  Rendered by the renderer's "studio3d" path.
        "render_mode": "studio3d",
        "background_color": "#bdbdb8",      # light concrete
        "accent_color": "#ffffff",
        "palette": ["#8d8d88", "#bdbdb8", "#d8d8d3", "#ff2d9b", "#ffd54f"],
        # candy colours cycled across the wall-mounted bars
        "key_palette": ["#9ccc3a", "#43b649", "#2e9e4f", "#3f51b5", "#5c6bc0",
                        "#e53935", "#ff7043", "#ffb300", "#ec407a", "#26c6da",
                        "#ab47bc", "#66bb6a"],
        "ball_style": {"shape": "circle", "fill": "#ff2d9b", "stroke": "#ffd54f",
                       "glow_radius": 0, "gloss": True},
        "key_style": {"shape": "slab", "fill": "#9ccc3a", "stroke": "#5a5a5a",
                      "hit_flash_color": "#ffffff", "label_font": "sans"},
        "wall_style": {"fill": "#a9a9a4", "pattern": "concrete"},
        "particle_effect": "none", "motion_blur": False, "vignette": False,
    },
    "glow_3d": {
        # Toward the Blender "music ball" look (3Dにゃん reference):
        # emissive glowing bars with cyan edge-glow + faux 3D depth, glass
        # marble, vibrant gradient backdrop.  Rendered by the scroll path.
        "render_mode": "studio3d",
        "background_color": "#1a1030",
        "accent_color": "#7df9ff",
        "palette": ["#0e1430", "#2a2d6b", "#5e2a7a", "#18c5ff", "#7df9ff"],
        # vertical gradient stops for the backdrop (top → bottom)
        "bg_gradient": ["#16463a", "#23306e", "#4a2a78", "#7a2a5e", "#2a1846"],
        # cool blues/cyans like the reference bars (subtle per-pitch variation)
        "key_palette": ["#1e6bff", "#1e8cff", "#18b6ff", "#15d8ff", "#2a5bff",
                        "#2e7bff", "#1e6bff", "#18b6ff", "#15d8ff", "#1e8cff",
                        "#2a5bff", "#2e7bff"],
        "ball_style": {"shape": "circle", "fill": "#2aa8ff", "stroke": "#9be8a0",
                       "glow_radius": 14, "gloss": True, "swirl": True},
        "key_style": {"shape": "slab", "fill": "#1e6bff", "stroke": "#cfefff",
                      "hit_flash_color": "#ffffff", "label_font": "sans",
                      "emissive": True, "edge_glow": "#7df9ff", "depth": 8},
        "wall_style": {"fill": "#2a2d6b", "pattern": "gradient"},
        "particle_effect": "sparks", "motion_blur": False, "vignette": True,
    },
}
DEFAULT_STYLE_PRESET = "concrete_marble"
