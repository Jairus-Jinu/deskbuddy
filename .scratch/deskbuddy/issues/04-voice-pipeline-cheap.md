Status: resolved
Type: research
Labels: wayfinder:research

## Answer

INMP441 mic (₹149–299) + MAX98357A amp (₹150–350) are Dupont-wire easy on shared I2S; all 2026 wake-word stacks need ESP32-S3 + PSRAM (N16R8 ~₹1,299). Cheapest turn is all-Gemini ≈ ₹0.21–₹0.27 (free tier), ~2–5s end-to-end latency, with a ₹5–20 GPIO-button push-to-talk fallback. Full facts: `../research/04-voice-findings.md`.

## Question

What is the cheapest reliable voice pipeline for an ESP32-class DeskBuddy with wake-word always-listening (INMP441/SPH0645 mic + MAX98357A speaker) plus cloud STT → LLM → TTS? Compare: on-device wake-word (Edge Impulse / ESP-Skainet / MicroWakeWord) vs streaming to laptop vs cloud wake-word; and which STT/LLM/TTS APIs are cheapest/easiest from India in 2026 (Gemini, OpenAI, Whisper API, etc.). Include mic/speaker wiring and latency expectations.

Blocked by: 01
