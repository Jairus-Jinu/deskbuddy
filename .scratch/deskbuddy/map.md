# DeskBuddy Map

> GitHub Issues is the working tracker: https://github.com/Jairus-Jinu/deskbuddy/issues
> This file is the offline mirror of the planning map.

## Destination

A buildable v1 spec for DeskBuddy — movable tracking head + dual round-LCD reactive eyes + wake-word voice companion (cloud-assisted to keep cost/compute low) — with parts list in India pricing, wiring, software stack, and step-by-step build order a coder with no hardware experience can execute from.

## Notes

- Domain: DIY companion robot (ESP32-class, servos, LCD eyes, mic/speaker, camera/PIR, cloud LLM+STT+TTS).
- Budget steer: no Raspberry Pi (too costly); target Arduino-cheap; camera only if ~≤₹500 else PIR/motion fallback; already locked: two round LCD eyes, wake-word always-listening, cloud OK (not fully offline).
- User: some coding, no hardware experience. Optimize spec for beginner wiring, cheap India sourcing (Robu, Robokits, Amazon.in), minimal soldering.
- Skills every session should consult: `grilling` + `domain-modeling` for HITL tickets; `research` (primary sources only) for AFK tickets; `prototype` if eye/behavior fidelity questions arise.
- Conventions: GitHub issues are the tracker (labels `wayfinder:*`, native blocked-by wiring); this file is the offline mirror.

## Decisions so far

<!-- one line per closed ticket: gist + link; detail lives in the ticket -->

- [Tracking: camera vs PIR](./issues/02-tracking-camera-vs-pir.md): no camera fits ₹500; PIR+sweep ≈₹205–275 (no face lock) or ₹569 USB webcam + laptop for real face lock.
- [Dual round LCD eyes](./issues/03-dual-round-lcd-eyes.md): 2× GC9A01 at ₹800–₹1,300/pair, TFT_eSPI Animated_Eyes_2, plain ESP32 suffices for eyes alone.
- [Cheap voice pipeline](./issues/04-voice-pipeline-cheap.md): INMP441 + MAX98357A easy; wake-word needs ESP32-S3 + PSRAM (~₹1,299); all-Gemini ≈₹0.21–0.27/turn.
- [DeskBuddy repo + docs pushed]: README, docs/HARDWARE.md, docs/research/ live on GitHub; issues #1–#6 opened with native blocking.

## Not yet specified

- Body/chassis build method (3D-print vs acrylic/cardboard) and head pan-tilt mechanics for 2x round LCD weight.
- Power strategy (USB-powered vs Li-ion + charging) and cable management for moving head.
- Eye expression set + emotion engine (what triggers happy/sleepy/curious/listening/thinking).
- Companion personality + conversation memory (name, tone, languages: English/Hindi/Hinglish?).
- Wake-word choice and false-trigger handling in a desk room.
- Privacy/safety: camera + always-listening mic on desk — mute switch, LED indicator.

## Out of scope

- Fully-offline on-device LLM/STT/TTS (ruled out: too heavy for Arduino-class budget; cloud-assisted chosen).
- Raspberry Pi 5 standalone brain (ruled out: cost).
- Single-screen or OLED eye variants (ruled out: dual round LCDs locked).
- Push-to-talk as primary interaction (ruled out: wake-word locked for v1, though may survive as fallback).

## Open GitHub issues

- #1 Brain + voice architecture (frontier)
- #2 Tracking verdict — blocked by #1
- #3 Dual round LCD eyes bring-up — blocked by #1
- #4 Cheap voice pipeline build — blocked by #1
- #5 Head mechanics + power + chassis — blocked by #1
- #6 Behavior spec + build order — blocked by #1–#5
