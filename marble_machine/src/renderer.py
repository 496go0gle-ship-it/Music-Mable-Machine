"""renderer.py — Phase 6: draw every frame onto an offscreen Surface.

Two render paths, chosen by style["render_mode"]:
  * "flat"     — the original neon/2D look (presets neon_dark, signal_90s, …)
  * "studio3d" — a pseudo-3D studio look (preset concrete_marble): light
                 concrete wall, chrome-bolted glossy colour bars with soft cast
                 shadows, and a glossy marble.  Aims at the spicy.motion vibe.

Nothing opens a display; the caller saves each Surface to a PNG.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict, deque
from dataclasses import dataclass

import pygame

from config import BALL_RADIUS, HEIGHT, KEY_HEIGHT, WIDTH, hex_to_rgb

_FONT_MAP = {
    "monospace": "menlo,dejavusansmono,couriernew,monospace",
    "serif": "georgia,timesnewroman,serif",
    "sans": "helvetica,arial,sans",
    "pixel": "menlo,monospace",
}


def _lighten(c, f):
    return tuple(min(255, int(c[i] + (255 - c[i]) * f)) for i in range(3))


def _darken(c, f):
    return tuple(max(0, int(c[i] * (1 - f))) for i in range(3))


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    color: tuple

    @property
    def pos(self):
        return (int(self.x), int(self.y))

    @property
    def tail(self):
        return (int(self.x - self.vx * 0.03), int(self.y - self.vy * 0.03))


class Renderer:
    def __init__(self, style: dict, width: int = WIDTH, height: int = HEIGHT):
        self.style = style
        self.width = width
        self.height = height
        self.mode = style.get("render_mode", "flat")
        self.title = ""
        self.watermark = ""
        pygame.font.init()
        font_name = _FONT_MAP.get(style["key_style"].get("label_font", "sans"), None)
        self.font = pygame.font.SysFont(font_name, 16, bold=True)
        self.title_font = pygame.font.SysFont(font_name, 40, bold=True)
        self.small_font = pygame.font.SysFont(font_name, 22, bold=True)
        self.surface = pygame.Surface((width, height))
        self.particles: list[Particle] = []
        self._trails: dict[int, deque] = defaultdict(lambda: deque(maxlen=6))
        self._ball_trail: deque = deque(maxlen=20)
        self._vignette = (self._build_vignette()
                          if style.get("vignette") and self.mode == "flat" else None)
        self._bg_cache = None
        self._wall_cache = None     # studio3d: concrete + static keys
        self._shadow = self._build_shadow_sprite()
        self._keys = []

    # ── one-time prep: assign per-lane colours ──────────────────────
    def prepare(self, keys, by_pitch=False):
        self._keys = list(keys)
        palette = self.style.get("key_palette")
        if palette:
            cols = [hex_to_rgb(c) for c in palette]
            for i, k in enumerate(self._keys):
                idx = (k.midi_note % 12) if by_pitch else i
                k.color = cols[idx % len(cols)]

    # ── soft shadow sprite (radial alpha) ───────────────────────────
    def _build_shadow_sprite(self, size=128):
        spr = pygame.Surface((size, size), pygame.SRCALPHA)
        c = size // 2
        for r in range(c, 0, -1):
            a = int(120 * (1 - r / c) ** 1.6)
            pygame.draw.circle(spr, (0, 0, 0, a), (c, c), r)
        return spr

    def _blit_shadow(self, surf, cx, cy, w, h):
        spr = pygame.transform.smoothscale(self._shadow, (max(2, int(w)), max(2, int(h))))
        surf.blit(spr, (int(cx - w / 2), int(cy - h / 2)))

    # ════════════════════════════════════════════════════════════════
    #  BACKGROUND
    # ════════════════════════════════════════════════════════════════
    def _draw_pattern(self, surf):
        wall = self.style["wall_style"]
        color = hex_to_rgb(wall["fill"])
        pattern = wall.get("pattern", "none")
        if pattern == "grid":
            for x in range(0, self.width, 40):
                pygame.draw.line(surf, color, (x, 0), (x, self.height), 1)
            for y in range(0, self.height, 40):
                pygame.draw.line(surf, color, (0, y), (self.width, y), 1)
        elif pattern == "scanline":
            for y in range(0, self.height, 4):
                pygame.draw.line(surf, color, (0, y), (self.width, y), 1)
        elif pattern == "dots":
            for x in range(20, self.width, 40):
                for y in range(20, self.height, 40):
                    pygame.draw.circle(surf, color, (x, y), 2)
        elif pattern == "circuit":
            for y in range(30, self.height, 60):
                pygame.draw.line(surf, color, (0, y), (self.width, y), 1)
                for x in range(60, self.width, 120):
                    pygame.draw.circle(surf, color, (x, y), 3, 1)

    def _build_concrete(self, gradient=True):
        base = hex_to_rgb(self.style["background_color"])
        bg = pygame.Surface((self.width, self.height))
        bg.fill(base)
        if gradient:
            # gentle top-to-bottom light falloff (static modes only)
            for y in range(self.height):
                f = 0.12 * (1 - y / self.height) - 0.06
                pygame.draw.line(bg, _lighten(base, max(0, f)) if f > 0 else _darken(base, -f),
                                 (0, y), (self.width, y))
        # mottled plaster blobs
        rng = random.Random(7)
        blob = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        for _ in range(900):
            x = rng.randint(0, self.width)
            y = rng.randint(0, self.height)
            r = rng.randint(8, 46)
            up = rng.random() < 0.5
            col = _lighten(base, 0.10) if up else _darken(base, 0.10)
            pygame.draw.circle(blob, (*col, 16), (x, y), r)
        bg.blit(blob, (0, 0))
        return bg

    def draw_background(self, surf):
        if self.mode == "studio3d":
            if self._wall_cache is None:
                self._wall_cache = self._build_wall()
            surf.blit(self._wall_cache, (0, 0))
            self._draw_overlays(surf)
            return
        if self._bg_cache is None:
            bg = pygame.Surface((self.width, self.height))
            bg.fill(hex_to_rgb(self.style["background_color"]))
            self._draw_pattern(bg)
            self._bg_cache = bg
        surf.blit(self._bg_cache, (0, 0))

    def _draw_overlays(self, surf):
        if self.title:
            band = pygame.Surface((self.width, 96), pygame.SRCALPHA)
            band.fill((0, 0, 0, 70))
            surf.blit(band, (0, 30))
            txt = self.title_font.render(self.title, True, (255, 255, 255))
            surf.blit(txt, txt.get_rect(center=(self.width // 2, 78)))
        if self.watermark:
            wm = self.small_font.render(self.watermark, True, (255, 255, 255))
            wm.set_alpha(150)
            surf.blit(wm, wm.get_rect(center=(self.width // 2, self.height - 90)))

    # ════════════════════════════════════════════════════════════════
    #  SCROLLING SINGLE-BALL MODE (camera follows the marble)
    # ════════════════════════════════════════════════════════════════
    def _build_gradient_tile(self, stops):
        cols = [hex_to_rgb(c) for c in stops]
        tile = pygame.Surface((self.width, self.height))
        n = len(cols) - 1
        for y in range(self.height):
            f = y / max(1, self.height - 1) * n
            i = min(n - 1, int(f))
            t = f - i
            c = tuple(int(cols[i][k] * (1 - t) + cols[i + 1][k] * t) for k in range(3))
            pygame.draw.line(tile, c, (0, y), (self.width, y))
        # faint mottle so it isn't a flat ramp
        rng = random.Random(11)
        blob = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        for _ in range(400):
            x, y, r = rng.randint(0, self.width), rng.randint(0, self.height), rng.randint(20, 80)
            pygame.draw.circle(blob, (255, 255, 255, 6), (x, y), r)
        tile.blit(blob, (0, 0))
        return tile

    def draw_bg_scroll(self, surf, camera_y):
        if self._bg_cache is None:
            stops = self.style.get("bg_gradient")
            self._bg_cache = (self._build_gradient_tile(stops) if stops
                              else self._build_concrete(gradient=False))
            self._bg_flip = pygame.transform.flip(self._bg_cache, False, True)
            if self.style.get("vignette"):
                self._scroll_vig = self._build_vignette()
        th = self._bg_cache.get_height()
        # mirror alternate tiles so the seams join seamlessly
        period = 2 * th
        off = int(camera_y) % period
        for base_y in (-off, period - off):
            surf.blit(self._bg_cache, (0, base_y))
            surf.blit(self._bg_flip, (0, base_y + th))
        if getattr(self, "_scroll_vig", None) is not None:
            surf.blit(self._scroll_vig, (0, 0))
        self._draw_overlays(surf)

    def _slab_surface(self, key, flash):
        """Render a glossy mounted bar onto its own surface for rotation.

        With key_style.emissive set, the bar gets a bright edge-glow and a
        faux-3D side extrusion (the glow_3d preset / Blender-ish look).
        """
        ks = self.style["key_style"]
        emissive = ks.get("emissive", False)
        depth = int(ks.get("depth", 0))
        w = int(key.width)
        h = KEY_HEIGHT
        pad = 24 if emissive else 16
        surf = pygame.Surface((w + pad * 2, h + pad * 2 + depth), pygame.SRCALPHA)
        l, t = pad, pad
        rect = pygame.Rect(l, t, w, h)
        base = (255, 255, 255) if flash else key.color
        rad = 9

        # outer edge glow (additive halo) for emissive bars
        if emissive:
            glow_col = hex_to_rgb(ks.get("edge_glow", "#7df9ff"))
            for gp, ga in ((10, 50), (6, 70), (3, 100)):
                g = pygame.Surface((w + 2 * gp, h + 2 * gp), pygame.SRCALPHA)
                pygame.draw.rect(g, (*glow_col, ga), g.get_rect(), border_radius=rad + gp)
                surf.blit(g, (l - gp, t - gp), special_flags=pygame.BLEND_RGBA_ADD)
        if flash:
            fg = pygame.Surface((w + 2 * pad, h + 2 * pad), pygame.SRCALPHA)
            pygame.draw.rect(fg, (255, 255, 255, 120), fg.get_rect(), border_radius=rad + 10)
            surf.blit(fg, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

        # faux-3D side face (extrude downward)
        if depth:
            side = pygame.Rect(l, t + h - rad, w, depth + rad)
            pygame.draw.rect(surf, _darken(base, 0.5), side, border_radius=rad)

        # top face
        pygame.draw.rect(surf, base, rect, border_radius=rad)
        gloss = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(gloss, (255, 255, 255, 70), (0, 0, w, int(h * 0.5)),
                         border_top_left_radius=rad, border_top_right_radius=rad)
        surf.blit(gloss, (l, t))
        pygame.draw.line(surf, _darken(base, 0.35), (l + rad, t + h - 2), (l + w - rad, t + h - 2), 2)
        # bright emissive top edge / normal highlight
        edge_col = hex_to_rgb(ks.get("edge_glow", "#ffffff")) if emissive else _lighten(base, 0.6)
        pygame.draw.line(surf, edge_col, (l + rad, t + 2), (l + w - rad, t + 2), 2)
        pygame.draw.rect(surf, _darken(base, 0.45), rect, 1, border_radius=rad)
        for bx in (l + int(w * 0.24), l + int(w * 0.76)):
            cy = t + h // 2
            pygame.draw.circle(surf, (150, 152, 156), (bx, cy), 4)
            pygame.draw.circle(surf, (235, 236, 238), (bx - 1, cy - 1), 2)
        return surf

    def draw_key_scroll(self, surf, key, camera_y, is_flashing=False):
        sx = key.x
        sy = key.y - camera_y
        if sy < -60 or sy > self.height + 60:
            return
        # soft cast shadow on the wall (axis-aligned, offset down-right)
        self._blit_shadow(surf, sx + 10, sy + 16, key.width * 1.5, KEY_HEIGHT * 2.6)
        slab = self._slab_surface(key, is_flashing)
        rot = pygame.transform.rotate(slab, -math.degrees(key.angle))
        surf.blit(rot, rot.get_rect(center=(int(sx), int(sy))))

    def draw_ball_scroll(self, surf, world_pos, camera_y):
        bs = self.style["ball_style"]
        wx, wy = world_pos
        self._ball_trail.append((wx, wy))
        fill = hex_to_rgb(bs["fill"])
        # fading world-space trail
        for i, (tx, ty) in enumerate(list(self._ball_trail)[:-1]):
            a = int(70 * (i + 1) / len(self._ball_trail))
            rr = max(2, int(BALL_RADIUS * (0.35 + 0.5 * (i + 1) / len(self._ball_trail))))
            ghost = pygame.Surface((rr * 2, rr * 2), pygame.SRCALPHA)
            pygame.draw.circle(ghost, (*fill, a), (rr, rr), rr)
            surf.blit(ghost, (int(tx - rr), int(ty - camera_y - rr)))
        self._draw_glossy_ball(surf, (int(wx), int(wy - camera_y)), BALL_RADIUS,
                               fill, hex_to_rgb(bs["stroke"]))

    # ════════════════════════════════════════════════════════════════
    #  STUDIO3D: static wall (concrete + brackets + slabs)
    # ════════════════════════════════════════════════════════════════
    def _build_wall(self):
        wall = self._build_concrete()
        # cast shadows first, then the mounts, then the slabs
        for k in self._keys:
            l, t, w, h = k.rect
            self._blit_shadow(wall, l + w / 2 + 10, t + h / 2 + 16, w * 1.5, h * 2.6)
        for k in self._keys:
            self._draw_mount(wall, k)
        for k in self._keys:
            self._draw_slab(wall, k, flash=False)
        return wall

    def _draw_mount(self, surf, key):
        """Two chrome stand-offs that 'bolt' the bar to the wall."""
        l, t, w, h = key.rect
        chrome = (176, 178, 182)
        for bx in (l + int(w * 0.24), l + int(w * 0.76)):
            rod = pygame.Rect(bx - 4, t - 6, 8, h + 16)
            pygame.draw.rect(surf, _darken(chrome, 0.25), rod, border_radius=4)
            pygame.draw.line(surf, _lighten(chrome, 0.5),
                             (bx - 2, t - 4), (bx - 2, t + h + 8), 2)

    def _draw_slab(self, surf, key, flash=False):
        l, t, w, h = key.rect
        rect = pygame.Rect(l, t, w, h)
        base = (255, 255, 255) if flash else key.color
        rad = 9
        # body
        pygame.draw.rect(surf, base, rect, border_radius=rad)
        # glossy upper highlight
        gloss = pygame.Surface((w, h), pygame.SRCALPHA)
        gh = int(h * 0.5)
        pygame.draw.rect(gloss, (255, 255, 255, 70), (0, 0, w, gh),
                         border_top_left_radius=rad, border_top_right_radius=rad)
        surf.blit(gloss, (l, t))
        # bottom shade + top edge light
        pygame.draw.line(surf, _darken(base, 0.35), (l + rad, t + h - 2),
                         (l + w - rad, t + h - 2), 2)
        pygame.draw.line(surf, _lighten(base, 0.6), (l + rad, t + 2),
                         (l + w - rad, t + 2), 2)
        pygame.draw.rect(surf, _darken(base, 0.45), rect, 1, border_radius=rad)
        # two bolts
        for bx in (l + int(w * 0.24), l + int(w * 0.76)):
            cy = t + h // 2
            pygame.draw.circle(surf, (150, 152, 156), (bx, cy), 4)
            pygame.draw.circle(surf, (235, 236, 238), (bx - 1, cy - 1), 2)
        if flash:
            glow = pygame.Surface((w + 24, h + 24), pygame.SRCALPHA)
            pygame.draw.rect(glow, (255, 255, 255, 90), (0, 0, w + 24, h + 24),
                             border_radius=rad + 6)
            surf.blit(glow, (l - 12, t - 12), special_flags=pygame.BLEND_RGBA_ADD)

    # ════════════════════════════════════════════════════════════════
    #  KEYS (dispatch)
    # ════════════════════════════════════════════════════════════════
    def draw_key(self, surf, key, is_flashing=False):
        if self.mode == "studio3d":
            # static slabs are already in the wall cache; only redraw on flash
            if is_flashing:
                self._draw_slab(surf, key, flash=True)
            return
        ks = self.style["key_style"]
        fill = hex_to_rgb(ks["hit_flash_color"] if is_flashing else ks["fill"])
        rect = pygame.Rect(*key.rect)
        shape = ks.get("shape", "rect")
        if shape == "rounded_rect":
            pygame.draw.rect(surf, fill, rect, border_radius=8)
            pygame.draw.rect(surf, hex_to_rgb(ks["stroke"]), rect, 2, border_radius=8)
        elif shape == "trapezoid":
            l, t, w, h = key.rect
            pts = [(l + w * 0.1, t), (l + w * 0.9, t), (l + w, t + h), (l, t + h)]
            pygame.draw.polygon(surf, fill, pts)
            pygame.draw.polygon(surf, hex_to_rgb(ks["stroke"]), pts, 2)
        else:
            pygame.draw.rect(surf, fill, rect)
            pygame.draw.rect(surf, hex_to_rgb(ks["stroke"]), rect, 2)
        label = self.font.render(key.label, True, hex_to_rgb(ks["stroke"]))
        surf.blit(label, label.get_rect(center=rect.center))

    # ════════════════════════════════════════════════════════════════
    #  BALL (dispatch)
    # ════════════════════════════════════════════════════════════════
    def draw_ball(self, surf, body):
        bs = self.style["ball_style"]
        pos = (int(body.position.x), int(body.position.y))
        r = BALL_RADIUS
        if self.mode == "studio3d" or bs.get("gloss"):
            self._draw_glossy_ball(surf, pos, r,
                                   hex_to_rgb(bs["fill"]), hex_to_rgb(bs["stroke"]))
            return
        fill = hex_to_rgb(bs["fill"])
        if self.style.get("motion_blur"):
            trail = self._trails[id(body)]
            for i, tp in enumerate(trail):
                a = int(60 * (i + 1) / max(1, len(trail)))
                ghost = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
                pygame.draw.circle(ghost, (*fill, a), (r, r), r)
                surf.blit(ghost, (tp[0] - r, tp[1] - r))
            trail.append(pos)
        if bs.get("glow_radius", 0) > 0:
            self._draw_glow(surf, pos, r, bs["glow_radius"],
                            hex_to_rgb(self.style["accent_color"]))
        shape = bs.get("shape", "circle")
        if shape == "hexagon":
            pts = [(pos[0] + r * math.cos(a), pos[1] + r * math.sin(a))
                   for a in [math.pi / 3 * k for k in range(6)]]
            pygame.draw.polygon(surf, fill, pts)
            pygame.draw.polygon(surf, hex_to_rgb(bs["stroke"]), pts, 2)
        elif shape == "diamond":
            pts = [(pos[0], pos[1] - r), (pos[0] + r, pos[1]),
                   (pos[0], pos[1] + r), (pos[0] - r, pos[1])]
            pygame.draw.polygon(surf, fill, pts)
            pygame.draw.polygon(surf, hex_to_rgb(bs["stroke"]), pts, 2)
        else:
            pygame.draw.circle(surf, fill, pos, r)
            pygame.draw.circle(surf, hex_to_rgb(bs["stroke"]), pos, r, 2)

    def _draw_glossy_ball(self, surf, pos, r, fill, swirl):
        x, y = pos
        bs = self.style["ball_style"]
        gr = bs.get("glow_radius", 0)
        if gr > 0:    # emissive halo (glow_3d marble)
            self._draw_glow(surf, pos, r, gr, hex_to_rgb(self.style["accent_color"]))
        # soft cast shadow on the wall, offset down-right
        self._blit_shadow(surf, x + 12, y + 16, r * 2.6, r * 1.7)
        # body shading: dark base -> lit toward top-left
        pygame.draw.circle(surf, _darken(fill, 0.18), (x, y), r)
        pygame.draw.circle(surf, fill, (x - int(r * 0.12), y - int(r * 0.12)), int(r * 0.92))
        pygame.draw.circle(surf, _lighten(fill, 0.28),
                           (x - int(r * 0.3), y - int(r * 0.3)), int(r * 0.55))
        # yellow swirl accent (like the reference marble)
        sw = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(sw, (*swirl, 150), (int(r * 1.35), int(r * 1.25)), int(r * 0.42))
        mask = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(mask, (255, 255, 255, 255), (r, r), r)
        sw.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surf.blit(sw, (x - r, y - r))
        # specular highlight
        hi = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(hi, (255, 255, 255, 220),
                           (int(r * 0.62), int(r * 0.55)), max(2, int(r * 0.22)))
        surf.blit(hi, (x - r, y - r))
        # rim
        pygame.draw.circle(surf, _darken(fill, 0.35), (x, y), r, 1)

    def forget_ball(self, body):
        self._trails.pop(id(body), None)

    # ── glow (flat mode) ─────────────────────────────────────────────
    def _draw_glow(self, surf, pos, radius, glow_radius, color):
        size = (radius + glow_radius) * 2
        glow = pygame.Surface((size, size), pygame.SRCALPHA)
        cx = size // 2
        steps = 6
        for i in range(steps, 0, -1):
            rr = int(radius + glow_radius * i / steps)
            alpha = int(70 * (1 - i / steps) + 10)
            pygame.draw.circle(glow, (*color, alpha), (cx, cx), rr)
        surf.blit(glow, (pos[0] - cx, pos[1] - cx), special_flags=pygame.BLEND_RGBA_ADD)

    # ── particles ───────────────────────────────────────────────────
    def spawn_particles(self, x, y, n=12):
        effect = self.style.get("particle_effect", "none")
        if effect == "none":
            return
        color = hex_to_rgb(self.style["accent_color"])
        flash = hex_to_rgb(self.style["key_style"]["hit_flash_color"])
        for _ in range(n):
            ang = random.uniform(0, 2 * math.pi)
            spd = random.uniform(60, 240)
            self.particles.append(Particle(
                x=x, y=y, vx=math.cos(ang) * spd, vy=math.sin(ang) * spd - 60,
                life=random.uniform(0.3, 0.7), max_life=0.7,
                color=random.choice([color, flash])))

    def update_particles(self, dt):
        alive = []
        for p in self.particles:
            p.life -= dt
            if p.life <= 0:
                continue
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vy += 400 * dt
            alive.append(p)
        self.particles = alive

    def draw_particles(self, surf):
        effect = self.style.get("particle_effect", "none")
        for p in self.particles:
            frac = max(0.0, p.life / p.max_life)
            if effect == "sparks":
                pygame.draw.line(surf, p.color, p.pos, p.tail, 2)
            elif effect == "rings":
                pygame.draw.circle(surf, p.color, p.pos, int((1 - frac) * 20) + 1, 1)
            elif effect == "pixels":
                pygame.draw.rect(surf, p.color, (*p.pos, 4, 4))
            elif effect == "petals":
                pygame.draw.circle(surf, p.color, p.pos, max(1, int(frac * 4)))
            elif effect != "none":
                pygame.draw.circle(surf, p.color, p.pos, max(1, int(frac * 3)))

    # ── vignette (flat mode) ─────────────────────────────────────────
    def _build_vignette(self):
        vig = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        cx, cy = self.width / 2, self.height / 2
        max_d = math.hypot(cx, cy)
        for y in range(0, self.height, 4):
            for x in range(0, self.width, 4):
                d = math.hypot(x - cx, y - cy) / max_d
                a = int(min(180, max(0, (d - 0.55) * 320)))
                if a > 0:
                    pygame.draw.rect(vig, (0, 0, 0, a), (x, y, 4, 4))
        return vig

    def draw_vignette(self, surf):
        if self._vignette is not None:
            surf.blit(self._vignette, (0, 0))
