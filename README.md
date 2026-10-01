# DeskBuddy 

A DIY desktop companion robot: a movable head that tracks your movement, dual round-LCD reactive eyes, and a wake-word voice companion powered by cloud AI. Built cheap in India on an ESP32-S3 — no Raspberry Pi needed.

## What it does (v1 goal)

- **Tracks you** — pan-tilt head follows motion (PIR sweep) or your face (USB webcam + laptop OpenCV)
- **Reactive eyes** — two 1.28" round GC9A01 LCDs that blink, look around, and show moods (happy / curious / listening / thinking / sleepy)
- **Talks to you** — wake-word always-listening mic → cloud STT → LLM → TTS → speaker, ~2–5s per turn for ~₹0.25

## Current status

Planning phase — research tickets resolved (see `docs/research/`), architecture + build decisions open as GitHub issues. See [docs/HARDWARE.md](docs/HARDWARE.md) for the living parts list and wiring.

## Quick links

- [Hardware, wiring & parts](docs/HARDWARE.md) — parts table with India pricing, pin maps, power
- [Research findings](docs/research/) — camera vs PIR, eyes, voice pipeline
- [Planning map](.scratch/deskbuddy/map.md) — wayfinder destination, decisions, fog
- [Issues](../../issues) — step-by-step work items

## Repo layout

```
deskbuddy/
├── README.md
├── docs/
│   ├── HARDWARE.md        # living parts + wiring doc (updated as the build evolves)
│   └── research/          # sourced findings: tracking, eyes, voice
├── tools/
│   └── voice-pipeline/    # laptop-hosted STT -> LLM -> TTS prototype (runs today)
├── firmware/              # ESP32-S3 code (coming)
├── .scratch/deskbuddy/    # wayfinder map + decision tickets
└── .gitignore
```

## Try it now (no hardware needed)

The voice brain runs on your laptop today — mic in, Gemini, speaker out:

```sh
cd tools/voice-pipeline
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env    # paste a free key from https://aistudio.google.com/apikey
.venv/bin/python smoke_test.py   # offline checks
.venv/bin/python main.py doctor  # verify audio + key
.venv/bin/python main.py voice   # talk to it
```

See [tools/voice-pipeline/README.md](tools/voice-pipeline/README.md).

## Roadmap (issues)

Work them in order — #1 unblocks #2–#5, all unblock #6.

1. [#1 Brain + voice architecture](https://github.com/Jairus-Jinu/deskbuddy/issues/1) — ESP32-S3 vs laptop-assisted split
2. [#2 Tracking verdict](https://github.com/Jairus-Jinu/deskbuddy/issues/2) — PIR sweep vs webcam + laptop
3. [#3 Dual round LCD eyes bring-up](https://github.com/Jairus-Jinu/deskbuddy/issues/3)
4. [#4 Cheap voice pipeline build](https://github.com/Jairus-Jinu/deskbuddy/issues/4)
5. [#5 Head mechanics + power + chassis](https://github.com/Jairus-Jinu/deskbuddy/issues/5)
6. [#6 Behavior spec + build order](https://github.com/Jairus-Jinu/deskbuddy/issues/6)
