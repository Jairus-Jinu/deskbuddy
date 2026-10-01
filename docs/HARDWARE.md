# DeskBuddy Hardware — parts, wiring & connections

> Living doc — updated every time parts arrive, wiring changes, or new ideas land.
> Last updated: 2026-09-30 (planning phase, research-resolved values).

## Locked decisions

- Brain: **ESP32-S3 + PSRAM** (N16R8) — all 2026 wake-word stacks require it; plain ESP32/Arduino can't do on-device wake-word
- Eyes: **2× GC9A01 1.28" round SPI LCD** (240×240), TFT_eSPI `Animated_Eyes_2`
- Voice: **INMP441 mic + MAX98357A speaker**, cloud STT → LLM → TTS (all-Gemini cheapest)
- Tracking: **undecided** — PIR sweep (cheap, no face lock) vs USB webcam + laptop (real face lock); see §Tracking

## Parts list (India, Sep 2026 — re-check at buy time)

| Part | Spec | Qty | ₹ each | Source |
|---|---|---|---|---|
| ESP32-S3 DevKit N16R8 | 16MB flash + 8MB PSRAM | 1 | ~1,299 | Robu.in / Amazon.in |
| Round LCD GC9A01 1.28" | 240×240 SPI | 2 | 399–649 | Makerbazar ₹399 / Probots ₹649 |
| INMP441 mic module | I2S, soldered-header version | 1 | 149–299 | Robu.in |
| MAX98357A amp module | I2S DAC + mono Class-D | 1 | 150–350 | Robu.in / IndiaMART |
| Speaker | 4Ω 3W (or 8Ω 1–3W), mono | 1 | ~100–200 | Amazon.in |
| SG90 servos | 9g, 180°, ~1.2 kg-cm | 2 | ~150–200 | 4-pack ₹610 Amazon.in |
| HC-SR501 PIR | motion sensor (if PIR path) | 1 | 55–73 | Robokits / Robocraze |
| USB webcam Frontech FT-2251 | 480p/30fps + mic (if webcam path) | 1 | ~569 | Amazon.in |
| Tactile button | push-to-talk fallback + mute | 2 | 5–20 | local |
| Breadboard + Dupont wires | short wires (SPI speed!) | 1 set | ~200 | Amazon.in |
| 5V supply | USB / 5V 2A adapter | 1 | on hand | — |

**Rough total:** ~₹2,800–3,800 (PIR path) / ~₹3,300–4,300 (webcam path), excl. chassis + shipping.

## Wiring

### Eyes — 2× GC9A01 on one SPI bus (share all, separate CS)

| Module pin | → ESP32-S3 | Notes |
|---|---|---|
| VCC | 3.3V | bare modules STRICTLY 3.3V, not 5V-tolerant |
| GND | GND | common ground |
| SCL/CLK | GPIO18 | HW SPI SCK |
| SDA/DIN | GPIO23 | HW SPI MOSI (label ≠ I2C!) |
| RES/RST | GPIO4 (shared or per-eye 19/4) | low-active |
| DC | GPIO2 or 33 (shared) | high=data, low=command |
| CS eye-1 | GPIO22 | low-active, per-eye unique |
| CS eye-2 | GPIO21 | low-active, per-eye unique |
| BL/BLK | 3.3V or PWM GPIO15 | tie high = always on; PWM for dimming |
| MISO | — | leave unconnected (write-only) |

Start SPI at 27–40 MHz, raise toward 60–80 MHz only with short solid wiring.
TFT_eSPI: set `GC9A01_DRIVER` in `User_Setup.h`, start from `Animated_Eyes_2`.

### Voice — mic + speaker on separate I2S peripherals

INMP441 (I2S RX): L/R→GND, WS→GPIO40, SCK→GPIO42, SD→GPIO41, VDD→3V3 (NOT 5V).
MAX98357A (I2S TX): VCC→5V (or 3V3), DIN/BCLK/LRC→3 free GPIOs, leave SD floating (mixed mono — don't ground it, ground = shutdown), GAIN default 9 dB fine.

### Servos + sensors

- SG90 pan/tilt: signal → PWM GPIOs, 5V + GND from supply (not the 3.3V rail); common ground with ESP32.
- HC-SR501 PIR: VCC→5V, GND→GND, OUT→digital GPIO (3.3V TTL: HIGH = motion). 30–60s power-on settle, H-mode (retriggerable). 3–7 m range, ~110° cone.
- Buttons: GPIO + internal pull-up + debounce; one PTT, one mute with LED indicator.

## Power

USB-powered v1 (5V 2A): servos + amp on 5V, logic/eyes/mic on 3.3V rail. Budget ~100–200 mA for both eyes. Battery (Li-ion + charging) is future work — see open issues.

## Tracking options (verdict pending)

- **PIR + pan sweep:** 3 wires, demo in an afternoon, but binary motion only — no face lock, blind to still people, ±tens-of-degrees accuracy.
- **USB webcam + laptop OpenCV:** 30fps wired UVC, real face box → servo angles, zero flashing ritual. Needs laptop on desk.
- **ESP32-CAM on-board:** ruled impractical — ₹582–761 + programmer, QVGA ~5fps, deprecated face example, ESP-WHO moved to S3/P4.

## Changelog

- 2026-09-30: created from research tickets 02/03/04 (tracking, eyes, voice findings).
- 2026-09-30: repo pushed + issues #1–#6 opened; parts/wiring mirrored from research findings. Update this file on every part arrival, wiring change, or new idea.
- 2026-09-30: `tools/voice-pipeline/` added — laptop-hosted STT→LLM→TTS prototype (Gemini, uses laptop mic/speaker). No hardware required; the cloud half of the voice path is now testable.
- 2026-09-30: voice stack switched to **Groq (Whisper STT + LLM) + local Piper TTS** after the Gemini project was denied access (403 on every generation call, key otherwise valid). Rationale: Groq has no project-approval gate and a real free tier; Piper is local, offline and free, which is the cheaper shape for the ESP32 build. All three stages verified live on the laptop.
  - Groq quirk: `llama-3.3-70b-versatile` is Enterprise-only; `openai/gpt-oss-20b` is the free-tier default. gpt-oss is a *reasoning* model — it bills thinking tokens against `max_tokens`, so the reply call uses `max_tokens=1200` + `reasoning_effort="low"` or it returns empty content.
  - Piper quirk: `synthesize_wav()` sets WAV sample-width before channels, which Python 3.14 rejects — `piper_tts.py` writes the header from the first audio chunk instead.
