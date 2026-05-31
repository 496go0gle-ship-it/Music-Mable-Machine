# Music Marble Machine Generator

A fully-automated **Pythagoras-switch / Wintergatan-style** music machine:
steel balls fall down lanes, strike wall-mounted piano keys, and play a song
in sync — rendered offscreen and exported as an MP4 with audio.

## How it works (phases)

| Phase | Module | Job |
|-------|--------|-----|
| 0 | (setup) | Environment audit & install |
| 1 | `src/style_analyzer.py` | Visual style: built-in preset or Claude-Vision extraction from a reference image |
| 2 | `src/music_parser.py` | Music → `NoteEvent` list (video URL via yt-dlp+librosa, audio file, sheet image via Claude Vision, or built-in demo melody) |
| 3 | `src/layout.py` | Lane/key placement + ball-drop scheduling so each ball lands on its beat |
| 4 | `src/physics.py` | pymunk world, balls, static key segments, collision detection |
| 5 | `src/sound.py` | Per-note sample bank (sine+ADSR, custom WAV, or clips from source audio) |
| 6 | `src/renderer.py` | Offscreen drawing: background patterns, glowing balls, key flashes, particles, vignette, motion-blur trails |
| 7 | `src/sound.py` (`render_mixdown`) | Mix all notes into one WAV, time-aligned to the visuals |
| 8 | `src/video_export.py` | ffmpeg muxes frames + audio → H.264/AAC MP4 |
| 9 | `src/video_export.py` (`verify_output`) | ffprobe checks the result has video+audio and a real duration |
| 10 | hooks | `export_midi`, `record_section`, `load_custom_instrument`, `set_layout_algorithm`, `apply_style_preset` |

`src/main.py` orchestrates all phases and is the entry point.

## Install

```bash
pip install -r requirements.txt --break-system-packages
# ffmpeg must also be on PATH:
#   macOS:  brew install ffmpeg
#   Debian: apt-get install ffmpeg -y
```

## Run

```bash
# Demo melody (no input needed) — produces marble_machine_output.mp4
python src/main.py

# From a video/audio URL (downloads audio with yt-dlp):
python src/main.py --music-source "https://www.youtube.com/watch?v=XXXX"

# From a local audio file or a sheet-music image:
python src/main.py --music-source ./song.wav
python src/main.py --music-source ./score.png        # needs ANTHROPIC_API_KEY

# Pick a style preset, or extract style from a reference image:
python src/main.py --preset retro_wood
python src/main.py --style-image ./ref.png           # needs ANTHROPIC_API_KEY

# Layout variants and output path:
python src/main.py --algorithm cascade --output out.mp4
```

### Inputs (the "INPUTS" block from the prompt)

| Variable | Flag / env | Notes |
|----------|------------|-------|
| `STYLE_IMAGE` | `--style-image` / `STYLE_IMAGE` | Optional. Blank → use `--preset`. URL or local path. |
| `MUSIC_SOURCE` | `--music-source` / `MUSIC_SOURCE` | URL, audio file, or sheet image. Blank → built-in demo melody. |
| `OUTPUT_VIDEO` | `--output` / `OUTPUT_VIDEO` | Defaults to `marble_machine_output.mp4`. |

### Environment

- `ANTHROPIC_API_KEY` — required only for Claude-Vision style extraction or
  sheet-music transcription. Everything else works without it.

## Single-ball model (Pythagoras-switch)

By default one marble travels a designed path and strikes a key at the exact
moment each note sounds (`src/trajectory.py`). Keys are placed wherever the
ball is at each note time, so every hit is guaranteed and locked to the audio;
the camera scrolls to follow the marble like a vertical marble run. Notes too
close for one ball to strike are thinned, and the audio mixes only the struck
notes so every sound matches a visible hit.

## Styles

- `concrete_marble` — light concrete wall, chrome-bolted glossy colour bars,
  glossy marble, soft shadows (spicy.motion reference).
- `glow_3d` — emissive glowing bars with cyan edge-glow + faux-3D depth, glass
  marble, vibrant gradient backdrop (toward the Blender "music ball" look).
- `neon_dark`, `signal_90s`, `minimal_white`, `retro_wood` — flat 2D looks.

```bash
python src/main.py --music-source audio/source.wav --preset glow_3d --title "HANABI"
```

## Roadmap → true 3D

The faux-3D depth/emission here is a 2.5D approximation. The next step is a
real 3D pipeline (Blender `bpy` with Cycles/Eevee, or three.js headless):
keep `trajectory.py` to drive marble + key transforms, but render PBR
materials, real emission, depth-of-field and shadows instead of layered
sprites.

## Design notes

- **Sync model:** balls are dropped straight down each lane and the audio
  mixdown places every note at the same time the ball reaches its key, so
  audio and visuals stay locked regardless of physics-integrator drift. A
  single global lead offset guarantees the first ball can spawn at *t ≥ 0*.
- **Headless:** `SDL_VIDEODRIVER=dummy`; frames are written to disk one at a
  time and never held in memory.
- **Lane tidiness:** with more than `MAX_LANES` unique pitches (common for
  pitch-tracked audio), lanes are folded by pitch class (one per note name)
  and keys are sized to the lane spacing so they never overlap. Each note
  still plays its own pitch in the audio mixdown. Balls are kicked off the key
  on impact so they fall away instead of piling up.
- **Resilience:** yt-dlp failures fall back to the demo melody; a missing API
  key falls back to the chosen preset; if balls ever tunnel through keys the
  key elasticity is bumped and the render retried; if frame drawing is slow
  the output is auto-downgraded to 960×540.

## Licensing

Audio fetched via yt-dlp is assumed to be for private use. Verify rights
before any commercial use.
