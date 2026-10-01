# DeskBuddy voice pipeline (laptop prototype)

The brain half of DeskBuddy, running on your laptop today instead of an ESP32.
It does exactly what the finished robot will do, minus the wake-word and the
physical mic/speaker:

```
mic  ->  STT (Gemini)  ->  LLM reply (Gemini)  ->  TTS (Gemini)  ->  speaker
```

Why build it now: this is the part with real unknowns (latency, voice quality,
cost, conversation feel). The hardware is the easy part once this works.

## Setup

```sh
cd tools/voice-pipeline
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env      # then paste your key from https://aistudio.google.com/apikey
```

## Use

```sh
.venv/bin/python main.py doctor          # verify audio + key before anything else
.venv/bin/python main.py say "hello there"
.venv/bin/python main.py ask "what's the plan today?"
.venv/bin/python main.py chat            # typed conversation, remembers context
.venv/bin/python main.py voice           # the real loop: Enter to talk, it replies
.venv/bin/python main.py voice --rounds 3 --seconds 6
```

On PipeWire/Arch, `pactl list short sources | grep input` shows mic devices and
`pactl list short sinks` shows speakers; pass one with `--mic` / `--speaker`.

## Layout

| File | Role |
|---|---|
| `main.py` | CLI: doctor / say / ask / chat / voice |
| `voice_pipeline/audio.py` | record + play WAV, silence check (arecord/aplay or ffmpeg) |
| `voice_pipeline/brain.py` | the three Gemini stages, model + voice config |
| `voice_pipeline/pipeline.py` | turn loop and short-term memory |
| `.env.example` | key + model overrides |

## What changes when the hardware arrives

- `audio.py` capture/playback is replaced by INMP441 I2S in + MAX98357A out — the
  WAV format at the boundary stays the same
- `pipeline.py`'s `listen_and_reply` gets triggered by the wake-word detector
  instead of the Enter key
- `brain.py` stays almost as-is: the ESP32 will POST audio to a small local
  service running this same code, or call Gemini directly if it has PSRAM headroom

## Costs (list price, Sep 2026)

One short turn ≈ ₹0.21–0.27 on the all-Gemini path, covered by the free tier
while prototyping. See `../../docs/research/04-voice-findings.md`.
