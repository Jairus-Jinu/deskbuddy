# DeskBuddy voice pipeline (laptop prototype)

The brain half of DeskBuddy, running on your laptop today instead of an ESP32.
It does what the finished robot will do, minus the wake-word and the physical
mic/speaker:

```
mic  ->  Whisper STT  ->  LLM reply  ->  Piper TTS  ->  speaker
          (Groq, cloud)   (Groq, cloud)  (local, offline)
```

**Why this stack:** Groq's free tier has no project-approval gate and very
fast Whisper, and Piper synthesises speech locally — so only the small
audio/text calls leave your machine, and there is no per-turn TTS cost. That is
also the cheapest shape for the eventual ESP32 build.

## Setup

```sh
cd tools/voice-pipeline
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env      # then paste a free key from https://console.groq.com/keys
```

The Piper voice (~63 MB) downloads on first run into
`~/.local/share/piper/voices/` and is reused after that.

## Use

```sh
.venv/bin/python main.py doctor          # verify key, Piper voice, mic, tools
.venv/bin/python smoke_test.py           # offline checks, no key or network
.venv/bin/python main.py say "hello there"
.venv/bin/python main.py ask "what's the plan today?"
.venv/bin/python main.py chat            # typed conversation, remembers context
.venv/bin/python main.py voice           # the real loop: Enter to talk, it replies
.venv/bin/python main.py voice --rounds 3 --seconds 6
```

On PipeWire/Arch, `pactl list short sources | grep input` lists mics and
`pactl list short sinks` lists speakers; pass one with `--mic` / `--speaker`.

## Providers

Pick the backend with `DESKBUDDY_PROVIDER` (or `--provider`):

| Provider | STT | LLM | TTS |
|---|---|---|---|
| `groq` (default) | Groq `whisper-large-v3-turbo` | Groq `openai/gpt-oss-20b` | local Piper |
| `gemini` | Gemini | Gemini | Gemini |

Model names are env-overridable (`DESKBUDDY_STT_MODEL`, `DESKBUDDY_LLM_MODEL`,
`DESKBUDDY_TTS_VOICE`). Set `DESKBUDDY_TTS_ENGINE=groq` to use a Groq-hosted
voice instead of Piper (simpler, but not local).

## Layout

| File | Role |
|---|---|
| `main.py` | CLI: doctor / say / ask / chat / voice |
| `voice_pipeline/audio.py` | record + play WAV, silence check (arecord/aplay or ffmpeg) |
| `voice_pipeline/providers.py` | the three capability Protocols (STT, LLM, TTS) |
| `voice_pipeline/groq_brain.py` | Groq STT + LLM, optional Groq TTS |
| `voice_pipeline/piper_tts.py` | local Piper TTS with voice auto-download |
| `voice_pipeline/brain.py` | Gemini implementation + shared prompt/limits |
| `voice_pipeline/factory.py` | provider selection |
| `voice_pipeline/pipeline.py` | turn loop and short-term memory |

## What changes when the hardware arrives

- `audio.py` capture/playback is replaced by INMP441 I2S in + MAX98357A out —
  the WAV format at the boundary stays the same
- `pipeline.py`'s `listen_and_reply` gets triggered by the wake-word detector
  instead of the Enter key
- Piper is C, so it can run next to the ESP32 later; the ESP32 will POST audio
  to a small local service running this code rather than calling Groq directly

## Costs (list price, Sep 2026)

Whisper-turbo is $0.04/hour of audio and `gpt-oss-20b` is $0.075/$0.30 per 1M
tokens — a short turn is a fraction of a paisa, and the free tier covers
prototyping. TTS is free because it runs locally. See
`../../docs/research/04-voice-findings.md` for the original comparison.
