"""layout.py — Phase 3: place keys on the wall and schedule ball drops.

Each unique MIDI note gets its own horizontal lane and a key at a height
chosen by pitch.  Balls are dropped straight down the lane so they reach the
key at exactly the note's `time_sec` (pure free-fall kinematics), which keeps
the visual hit locked to the audio.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from config import (BALL_RADIUS, GRAVITY, HEIGHT, KEY_HEIGHT, KEY_WIDTH,
                    KEY_Y_MAX, KEY_Y_MIN, MAX_LANES, SIDE_MARGIN, SPAWN_Y,
                    WIDTH, fall_time, midi_to_name)
from music_parser import NoteEvent


@dataclass
class Key:
    lane_id: int             # what defines the lane (midi note, or pitch class)
    midi_note: int           # representative MIDI note (for the label)
    x: float                 # lane centre x
    y: float                 # top surface y where the ball strikes
    label: str
    width: float = KEY_WIDTH
    color: tuple = (156, 204, 58)   # assigned per-lane by the renderer
    angle: float = 0.0              # bar tilt (radians); single-ball model
    hit_time: float = 0.0           # when the marble strikes this key
    flash_timer: float = 0.0
    pymunk_body: object = None

    @property
    def rect(self) -> tuple[int, int, int, int]:
        """(left, top, width, height) for drawing."""
        return (int(self.x - self.width / 2), int(self.y),
                int(self.width), KEY_HEIGHT)


@dataclass
class ScheduledSpawn:
    spawn_time: float
    spawn_x: float
    hit_time: float
    key: Key


@dataclass
class Layout:
    keys: list[Key] = field(default_factory=list)
    spawns: list[ScheduledSpawn] = field(default_factory=list)
    key_by_note: dict = field(default_factory=dict)
    # Global lead time added to every note so the first ball can spawn at t>=0.
    # The audio mixdown shifts every note by this same amount to stay in sync.
    time_offset: float = 0.0


def _lane_id(midi: int, fold: bool) -> int:
    """Lane key: the MIDI note itself, or its pitch class when folding."""
    return midi % 12 if fold else midi


def _lane_geometry(n: int) -> tuple[dict[int, float] | None, float]:
    """Return (spacing helper, key width) so keys never overlap."""
    usable = WIDTH - 2 * SIDE_MARGIN
    if n <= 1:
        return None, KEY_WIDTH
    step = usable / (n - 1)
    width = max(28.0, min(KEY_WIDTH, step - 10))
    return None, width


def _assign_height(rank: int, total: int) -> float:
    """Map a pitch rank to a key height (low pitch low on screen)."""
    if total == 1:
        return (KEY_Y_MIN + KEY_Y_MAX) / 2
    band = KEY_Y_MAX - KEY_Y_MIN
    # highest pitch -> near top (KEY_Y_MIN), lowest -> near bottom
    frac = 1.0 - rank / (total - 1)
    return KEY_Y_MIN + frac * band


def build_layout(notes: list[NoteEvent], algorithm: str = "gravity") -> Layout:
    """Build keys + ball spawn schedule for the given notes.

    If a source has more unique pitches than MAX_LANES, pitches are folded by
    pitch class so keys stay readable and never overlap.
    """
    unique_pitches = sorted({n.midi_note for n in notes})
    fold = len(unique_pitches) > MAX_LANES
    lane_ids = sorted({_lane_id(m, fold) for m in unique_pitches})
    n = len(lane_ids)

    usable = WIDTH - 2 * SIDE_MARGIN
    _, key_width = _lane_geometry(n)

    def lane_x(rank: int) -> float:
        if n == 1:
            return WIDTH / 2
        return SIDE_MARGIN + rank * (usable / (n - 1))

    # representative MIDI per lane (median) just for the label/height
    rep_midi: dict[int, int] = {}
    for lid in lane_ids:
        members = [m for m in unique_pitches if _lane_id(m, fold) == lid]
        rep_midi[lid] = members[len(members) // 2]

    keys: dict[int, Key] = {}
    for rank, lid in enumerate(lane_ids):
        if algorithm == "cascade":
            y = KEY_Y_MIN + (rank / max(1, n - 1)) * (KEY_Y_MAX - KEY_Y_MIN)
        elif algorithm == "zigzag":
            y = KEY_Y_MIN if rank % 2 == 0 else KEY_Y_MAX - KEY_HEIGHT
        else:  # "gravity" (default): height by pitch order
            y = _assign_height(rank, n)
        y = max(KEY_Y_MIN, min(KEY_Y_MAX, y))
        label = midi_to_name(rep_midi[lid])
        if fold:  # pitch class only — drop the octave digit
            label = label.rstrip("0123456789")
        keys[lid] = Key(lane_id=lid, midi_note=rep_midi[lid], x=lane_x(rank),
                        y=y, label=label, width=key_width)

    # Longest fall over all keys -> global lead so every ball spawns at t>=0.
    lead_for = {lid: fall_time(k.y - SPAWN_Y, GRAVITY) for lid, k in keys.items()}
    time_offset = max(lead_for.values(), default=0.0)

    # Phase 3-C: schedule a drop for every note so it lands on the beat.
    spawns: list[ScheduledSpawn] = []
    last_spawn_for_key: dict[int, float] = {}
    for ev in notes:
        lid = _lane_id(ev.midi_note, fold)
        key = keys[lid]
        hit_time = ev.time_sec + time_offset
        spawn_time = hit_time - lead_for[lid]
        # Deduplicate near-identical spawns on the same lane (<0.05 s apart).
        prev = last_spawn_for_key.get(lid)
        if prev is not None and abs(spawn_time - prev) < 0.05:
            continue
        last_spawn_for_key[lid] = spawn_time
        spawns.append(ScheduledSpawn(spawn_time=spawn_time, spawn_x=key.x,
                                     hit_time=hit_time, key=key))

    spawns.sort(key=lambda s: s.spawn_time)
    print(f"[Phase 3] done — {len(keys)} keys ({'pitch-class folded' if fold else 'per-pitch'}), "
          f"{len(spawns)} scheduled drops (algorithm: {algorithm}, lead {time_offset:.2f}s).")
    return Layout(keys=list(keys.values()), spawns=spawns,
                  key_by_note=keys, time_offset=time_offset)
