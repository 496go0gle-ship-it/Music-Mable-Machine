"""trajectory.py — single-ball path design (Pythagoras-switch model).

Instead of dropping one ball per note, a SINGLE marble travels a designed
path and strikes a key at the exact moment each note should sound.  The keys
are placed wherever the ball is at each note time, so a hit is guaranteed by
construction; the ball's launch velocity out of each key is chosen to keep a
steady downward drift (the camera scrolls to follow it, like a vertical
marble run).  Bar angles are set to the bounce bisector so it reads as a real
ricochet.

The audio mixdown plays exactly the struck notes, so every sound matches a
visible hit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from config import GRAVITY, HEIGHT, SIDE_MARGIN, WIDTH, midi_to_name
from layout import Key
from music_parser import NoteEvent

# Horizontal play area for key placement.
L = SIDE_MARGIN + 14
R = WIDTH - SIDE_MARGIN - 14

LEAD_IN = 0.9            # s: initial straight drop onto the first key
DESCENT_TARGET = 155.0  # px: preferred vertical drop between consecutive keys
VMAX_X = 650.0          # px/s: cap on horizontal speed (keeps bars flatter)
MAX_TILT = 0.88         # rad (~50°): clamp bar tilt so none look fully vertical
VY_UP_MAX = 840.0       # px/s: cap on upward bounce (keeps apex on screen)
VY_DOWN_MAX = 1250.0    # px/s: cap on downward launch
MIN_HIT_DT = 0.10       # s: closest two hits a single ball can make
CAM_OFFSET = int(HEIGHT * 0.40)   # ball sits this far below the screen top
START_Y = 360.0         # world y of the first key

_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


@dataclass
class Segment:
    t0: float
    t1: float
    x0: float
    y0: float
    vx: float
    vy: float            # vertical velocity at t0

    def pos(self, t: float) -> tuple[float, float]:
        dt = t - self.t0
        return (self.x0 + self.vx * dt,
                self.y0 + self.vy * dt + 0.5 * GRAVITY * dt * dt)

    def vel(self, t: float) -> tuple[float, float]:
        return (self.vx, self.vy + GRAVITY * (t - self.t0))


@dataclass
class Trajectory:
    segments: list[Segment] = field(default_factory=list)
    keys: list[Key] = field(default_factory=list)
    hit_notes: list[NoteEvent] = field(default_factory=list)
    time_offset: float = LEAD_IN
    total_time: float = 0.0

    def position(self, t: float) -> tuple[float, float]:
        if not self.segments:
            return (WIDTH / 2, START_Y)
        if t <= self.segments[0].t0:
            return self.segments[0].pos(self.segments[0].t0)
        for seg in self.segments:
            if seg.t0 <= t <= seg.t1:
                return seg.pos(t)
        last = self.segments[-1]
        return last.pos(t)   # extrapolate the final fall


def _pitch_x(midi: int) -> float:
    """Map pitch class to a fixed horizontal lane (C left … B right)."""
    pc = midi % 12
    return L + (pc / 11.0) * (R - L)


def _merge(notes: list[NoteEvent]) -> list[NoteEvent]:
    """A single ball cannot strike two keys at once; thin out close notes."""
    out: list[NoteEvent] = []
    last_t = -1e9
    for n in sorted(notes, key=lambda e: e.time_sec):
        if n.time_sec - last_t >= MIN_HIT_DT:
            out.append(n)
            last_t = n.time_sec
    return out


def _normalize(vx, vy):
    m = math.hypot(vx, vy)
    return (0.0, 1.0) if m < 1e-6 else (vx / m, vy / m)


def _bar_angle(v_in, v_out) -> float:
    """Tangent angle of a bar that bounces v_in into v_out (bisector normal)."""
    ix, iy = _normalize(*v_in)
    ox, oy = _normalize(*v_out)
    nx, ny = ox - ix, oy - iy            # normal ∝ out_unit - in_unit
    if math.hypot(nx, ny) < 1e-3:
        return 0.0                        # near-straight pass → flat bar
    ang = math.atan2(nx, -ny)            # tangent ⟂ normal
    # fold into [-90°,90°] then clamp so bars read as tilted tines, not walls
    if ang > math.pi / 2:
        ang -= math.pi
    elif ang < -math.pi / 2:
        ang += math.pi
    return max(-MAX_TILT, min(MAX_TILT, ang))


def build_trajectory(notes: list[NoteEvent]) -> Trajectory:
    hit_notes = _merge(notes)
    if len(hit_notes) < 2:
        raise SystemExit("Not enough notes for a single-ball run.")

    g = GRAVITY
    times = [n.time_sec + LEAD_IN for n in hit_notes]

    # First key + the straight lead-in drop onto it.
    x0 = _pitch_x(hit_notes[0].midi_note)
    drop = 0.5 * g * LEAD_IN * LEAD_IN
    segments = [Segment(t0=0.0, t1=times[0], x0=x0, y0=START_Y - drop, vx=0.0, vy=0.0)]

    key_pos = [(x0, START_Y)]
    out_vel = [None]   # launch velocity leaving each key (filled below)

    for k in range(len(hit_notes) - 1):
        dt = max(MIN_HIT_DT, times[k + 1] - times[k])
        xk, yk = key_pos[k]
        # horizontal: head toward the next pitch lane, capped
        vx = (_pitch_x(hit_notes[k + 1].midi_note) - xk) / dt
        vx = max(-VMAX_X, min(VMAX_X, vx))
        # vertical: aim for a steady descent, capped so apex stays on screen
        vy = (DESCENT_TARGET - 0.5 * g * dt * dt) / dt
        vy = max(-VY_UP_MAX, min(VY_DOWN_MAX, vy))
        xn = xk + vx * dt
        yn = yk + vy * dt + 0.5 * g * dt * dt
        segments.append(Segment(t0=times[k], t1=times[k + 1], x0=xk, y0=yk, vx=vx, vy=vy))
        key_pos.append((xn, yn))
        out_vel.append((vx, vy))

    # Trailing fall so the ball exits downward after the last note.
    last = segments[-1]
    tail_t0 = times[-1]
    tail = Segment(t0=tail_t0, t1=tail_t0 + 2.0,
                   x0=key_pos[-1][0], y0=key_pos[-1][1],
                   vx=last.vx * 0.4, vy=200.0)
    segments.append(tail)

    # Build Key objects with bounce angles + per-pitch colour/label.
    keys: list[Key] = []
    for k, n in enumerate(hit_notes):
        # incoming velocity = end of the segment that arrives at this key
        v_in = segments[k].vel(times[k])
        v_out = out_vel[k + 1] if (k + 1) < len(out_vel) and out_vel[k + 1] else (v_in[0], -200.0)
        angle = _bar_angle(v_in, v_out)
        x, y = key_pos[k]
        key = Key(lane_id=n.midi_note % 12, midi_note=n.midi_note,
                  x=x, y=y, label=_NAMES[n.midi_note % 12])
        key.angle = angle
        key.hit_time = times[k]
        keys.append(key)

    total_time = times[-1] + 2.0
    print(f"[Phase 3] done — single-ball path: {len(keys)} keys placed, "
          f"{len(hit_notes)} hits, lead {LEAD_IN:.2f}s, run {total_time:.1f}s.")
    return Trajectory(segments=segments, keys=keys, hit_notes=hit_notes,
                      time_offset=LEAD_IN, total_time=total_time)
