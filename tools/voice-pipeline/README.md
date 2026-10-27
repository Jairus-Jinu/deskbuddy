# DeskBuddy voice pipeline (laptop prototype)

The brain half of DeskBuddy, running on your laptop today instead of an ESP32.
Say **"choom"** and then just talk — no key press, no fixed recording window:

```
         "choom" ──▶ wake word ──▶ conversation stays open until it goes quiet
                                        │
   mic ──▶ VAD endpointing ──▶ Whisper STT ──▶ Groq LLM (streamed)
                                                    │
                                    sentence 1 ──▶ Kokoro ──▶ speaker
                                    sentence 2 ──▶ Kokoro ──▶ speaker
```

**Why this stack:**

- **Kokoro** for speech. Local, offline, free, Apache-2.0, and much warmer than
  Piper's default voice — the old "boring and monotone" complaint.
- **Groq** for STT + LLM. No project-approval gate, fast Whisper, and the reply
  streams back token by token so the first sentence is spoken while the model
  is still writing the second.
- **Silero VAD** (2.3 MB ONNX, run directly — no PyTorch) decides when you
  started and stopped talking.
- **Vosk** for the wake word: a small model whose decoder is locked to a few
  words. "choom" is not in its vocabulary, but it already hears the word as
  "chum"/"choon", so those are the grammar entries.

## Setup

```sh
cd tools/voice-pipeline
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env      # then paste a free key from https://console.groq.com/keys
```

Models download on first use and are cached under `~/.cache/deskbuddy/`:

| Model | Size | Used for |
|---|---|---|
| `kokoro-v1.0.onnx` + voices | ~340 MB | speech output |
| `silero_vad.onnx` | 2.3 MB | speech detection |
| vosk small en-us | ~68 MB | the "choom" wake word |

## Use

```sh
.venv/bin/python main.py doctor          # verify key, voice, wake word, mic, speaker
.venv/bin/python main.py devices         # list audio devices
.venv/bin/python test_conversation.py    # offline checks, no mic, no key

.venv/bin/python main.py converse        # hands-free: say "choom", then talk
.venv/bin/python main.py say "hello there"
.venv/bin/python main.py ask "what's the plan today?"
.venv/bin/python main.py chat            # typed conversation, remembers context
.venv/bin/python main.py voice           # old push-to-talk loop (Enter per turn)
```

### `converse` options

| Flag | Default | Meaning |
|---|---|---|
| `--wake-word` | `choom` | phrase that opens a conversation (`DESKBUDDY_WAKE_WORD`) |
| `--no-wake-word` | off | always listening; no phrase needed |
| `--silence-ms` | `800` | pause length that ends your turn |
| `--session-timeout` | `45` | quiet seconds before "choom" is needed again |
| `--barge-in` | off | let you talk over a reply to cut it off |
| `--max-turns` | ∞ | stop after N answered turns |
| `--near-field` | off | only answer voices louder than the room (see below) |

## The wake word

`choom` is not a stock wake word, and the two obvious engines were measured
and rejected:

- **openWakeWord** ships only alexa / hey jarvis / hey mycroft / timer /
  weather. A custom word needs a training run against thousands of clips.
- **sherpa-onnx's keyword spotter** can spell any word in phonemes, so it
  looked ideal — but on identical clean audio it only detected the word 4
  times out of 6 depending on how much silence came before it, and never with
  classroom noise behind it.

Vosk runs a small ASR model with its decoder restricted to a word list. The
catch: "choom" is not in its vocabulary and unknown words are silently
dropped. It already hears the word as **"chum"/"choon"**, so those are the
grammar entries (`HOMOPHONES` in `wake_word.py`).

To use a different word, add the near-miss spellings the recognizer produces:

```sh
.venv/bin/python test_choom.py --what-heard   # prints what it thinks you said
```

## Test the wake word on its own

```sh
.venv/bin/python test_choom.py
```

This prints a live mic bar and what the recognizer hears, so a near-miss is
visible instead of silent. It uses the same detector as `converse`.

## Working in a noisy room

A classroom is a hard environment for this, and it is worth being precise
about why.

**The wake word holds up well.** It matches on *content*, not loudness. In a
busy classroom with people talking continuously it produced **zero false
triggers over 20 seconds**, and it fires reliably on the word itself.

**A volume-based "near-field" filter does not work here.** The intuitive fix —
only answer voices that are much louder than the room — was measured and
rejected: the room's background peaked at ~9 dB above its own floor while the
laptop speaker only reached ~5 dB at normal volume. Any threshold that rejects
the room also rejects the person at the desk. The gate remains available
(`--near-field --min-snr N`) for genuinely quiet rooms.

**Microphone gain was the real bug.** This laptop's mic was at 81% gain and
clipping at full scale on ordinary room sound — 7.5% of samples pinned at the
maximum. Clipped speech is not loud speech, it is *unintelligible*: every peak
flattens to the same value, so the recognizer hears mush. `doctor` now detects
sustained clipping and tells you the fix. If the wake word stops working, check
this first:

```sh
pactl set-source-volume @DEFAULT_SOURCE@ 25%
```

**What also matters:** how loud you are relative to everyone else at the
microphone. Sitting close to the laptop and speaking normally gives a much
better signal-to-noise ratio than any software setting. If false triggers do
become a problem, raise the keyword threshold in `wake_word.py`
(`WakeWord(threshold=0.1)` is more sensitive, higher is stricter).

## Providers

Pick the backend with `DESKBUDDY_PROVIDER` (or `--provider`):

| Provider | STT | LLM | TTS |
|---|---|---|---|
| `groq` (default) | Groq `whisper-large-v3-turbo` | Groq `openai/gpt-oss-20b` | local Kokoro |
| `gemini` | Gemini | Gemini | Gemini |

`DESKBUDDY_TTS_ENGINE` switches the voice: `kokoro` (default), `piper`
(local, flatter), or `groq` (cloud Orpheus — needs terms accepted at
console.groq.com first).

Model names are env-overridable (`DESKBUDDY_STT_MODEL`, `DESKBUDDY_LLM_MODEL`,
`DESKBUDDY_TTS_VOICE`). The Gemini path does not stream yet, so it loses the
first-sentence head start.

## Layout

| File | Role |
|---|---|
| `main.py` | CLI: doctor / devices / say / ask / chat / converse / voice |
| `voice_pipeline/conversation.py` | the hands-free loop: wake word, turns, sentence streaming |
| `voice_pipeline/audio_io.py` | live mic + speaker streams (sounddevice) |
| `voice_pipeline/vad.py` | Silero VAD wrapper and turn detector |
| `voice_pipeline/wake_word.py` | sherpa-onnx keyword spotter, model download |
| `voice_pipeline/kokoro_tts.py` | local Kokoro voice |
| `voice_pipeline/level.py` | noise floor + optional near-field gate |
| `voice_pipeline/groq_brain.py` | Groq STT + streaming LLM |
| `voice_pipeline/piper_tts.py` | the original Piper voice (still selectable) |
| `voice_pipeline/brain.py` | Gemini implementation + shared prompt |
| `voice_pipeline/pipeline.py` | the old Enter-per-turn loop (`voice`) |
| `test_conversation.py` | offline tests — sentence splitting, turn logic, streaming |

## Measured on this laptop

Intel Iris Xe, 8 cores, Python 3.14, no GPU:

| Step | Time |
|---|---|
| Kokoro first sentence | 0.7 s for ~2 s of audio |
| Kokoro model load (cached) | 1.7 s, once per session |
| Wake word model load | 0.7 s |
| Groq STT (2 s clip) | 0.25 s |
| Groq LLM first token | 0.45 s |
| End of speech → first audio | ~1.2 s |

## What changes when the hardware arrives

- `audio_io.py`'s capture/playback is replaced by INMP441 I2S in + MAX98357A
  out — the 16 kHz mono boundary stays the same
- the wake word moves on-device (microWakeWord on the ESP32-S3) or the board
  streams to this service
- Kokoro is ONNX, so it can stay on the laptop; the ESP32 will POST audio here
  rather than calling Groq directly

## Costs (list price, Sep 2026)

Whisper-turbo is $0.04/hour of audio and `gpt-oss-20b` is $0.075/$0.30 per 1M
tokens — a short turn is a fraction of a paisa, and the free tier covers
prototyping. TTS is free because it runs locally.
