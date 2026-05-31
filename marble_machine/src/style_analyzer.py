"""style_analyzer.py — Phase 1: derive a style descriptor.

Either uses a built-in preset, or (when a style reference image is given and
ANTHROPIC_API_KEY is set) asks Claude Vision to extract a descriptor from it.
Falls back to the default preset on any failure.
"""

from __future__ import annotations

import base64
import copy
import json
import os
import shutil
from pathlib import Path

import requests

from config import (DEFAULT_STYLE_PRESET, STYLE_PRESETS, VISION_MODEL)

ASSETS = Path(__file__).resolve().parent.parent / "assets"

_VISION_PROMPT = """Analyze this reference image as a graphic design art director would.
Return ONLY a valid JSON object (no markdown, no preamble) with these exact keys:

{
  "palette": ["#RRGGBB", ...],
  "background_color": "#RRGGBB",
  "accent_color": "#RRGGBB",
  "style_tags": ["tag1", ...],
  "ball_style": {"shape": "circle|hexagon|diamond", "fill": "#RRGGBB", "stroke": "#RRGGBB", "glow_radius": 0},
  "key_style": {"shape": "rect|rounded_rect|trapezoid", "fill": "#RRGGBB", "stroke": "#RRGGBB", "hit_flash_color": "#RRGGBB", "label_font": "monospace|serif|sans|pixel"},
  "wall_style": {"fill": "#RRGGBB", "pattern": "none|grid|scanline|dots|circuit"},
  "particle_effect": "none|sparks|rings|pixels|petals",
  "motion_blur": true,
  "vignette": true
}"""


def _load_style_image(style_image: str) -> Path | None:
    """Download (URL) or copy (local) the style image to assets/style_ref.png."""
    ASSETS.mkdir(parents=True, exist_ok=True)
    dest = ASSETS / "style_ref.png"
    try:
        if style_image.startswith("http"):
            resp = requests.get(style_image, timeout=30)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
        else:
            src = Path(style_image).expanduser()
            if not src.exists():
                print(f"[Phase 1] style image not found: {src}")
                return None
            shutil.copy(src, dest)
        return dest
    except Exception as exc:  # noqa: BLE001
        print(f"[Phase 1] could not load style image ({exc}).")
        return None


def _ensure_keys(style: dict) -> dict:
    """Merge an extracted descriptor over the default preset so no key is missing."""
    base = copy.deepcopy(STYLE_PRESETS[DEFAULT_STYLE_PRESET])
    for k, v in style.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k].update(v)
        else:
            base[k] = v
    return base


def analyze_style(style_image: str | None, preset: str = DEFAULT_STYLE_PRESET) -> dict:
    """Return a style dict.

    Priority: preset (if no usable image) -> Claude Vision extraction.
    Any failure falls back to the chosen/default preset.
    """
    preset = preset if preset in STYLE_PRESETS else DEFAULT_STYLE_PRESET

    if not style_image:
        print(f"[Phase 1] done — using preset '{preset}'.")
        return copy.deepcopy(STYLE_PRESETS[preset])

    img_path = _load_style_image(style_image)
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if img_path is None or not api_key:
        reason = "no image" if img_path is None else "ANTHROPIC_API_KEY not set"
        print(f"[Phase 1] done — falling back to preset '{preset}' ({reason}).")
        return copy.deepcopy(STYLE_PRESETS[preset])

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        b64 = base64.standard_b64encode(img_path.read_bytes()).decode()
        msg = client.messages.create(
            model=VISION_MODEL,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64",
                                                  "media_type": "image/png", "data": b64}},
                    {"type": "text", "text": _VISION_PROMPT},
                ],
            }],
        )
        text = msg.content[0].text.strip()
        # tolerate accidental code fences
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()
        style = _ensure_keys(json.loads(text))
        print("[Phase 1] done — style extracted via Claude Vision.")
        return style
    except Exception as exc:  # noqa: BLE001
        print(f"[Phase 1] vision call failed ({exc}); using preset '{preset}'.")
        return copy.deepcopy(STYLE_PRESETS[preset])
