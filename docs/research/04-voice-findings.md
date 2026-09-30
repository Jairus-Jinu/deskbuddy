# Ticket 04 — Cheap Voice Pipeline with Wake-Word: Findings (facts only, no architecture decision)

Scope: cheapest reliable ESP32-class voice pipeline for DeskBuddy (INMP441 mic + MAX98357A speaker, on-device wake-word, cloud STT → LLM → TTS, India sourcing). Each bullet cites its primary source. Prices checked 30 Sep 2026; INR prices fluctuate — re-check at buy time.

## 1. Mic (INMP441 I2S) + speaker (MAX98357A I2S) wiring, India price, beginner difficulty

### INMP441 I2S microphone module
- What it is: omnidirectional MEMS mic with bottom port, digital output, 24-bit I2S interface (slave serial-data port, 64 SCK cycles per WS stereo frame; L/R pin selects left vs right channel). ([TDK InvenSense INMP441 datasheet PDF](https://product.tdk.com/system/files/dam/doc/product/sw_piezo/mic/mems-mic/data_sheet/inmp441.pdf))
- Module pins: VDD, GND, SD (serial data out), WS (word select / LRCLK), SCK (serial clock / BCLK), L/R (channel select: GND = left, 3V3 = right). ([Random Nerd Tutorials — ESP32 + INMP441 pinout](https://randomnerdtutorials.com/esp32-inmp441-i2s-microphone-arduino/))
- Proven ESP32-S3 wiring (Arduino, `driver/i2s.h`, 16 kHz, 32-bit words, ONLY_LEFT when L/R=GND): L/R→GND, WS→GPIO40, SCK→GPIO42, SD→GPIO41, GND→GND, VDD→3V3. I2S GPIOs are flexible — any safe GPIO works. ([Random Nerd Tutorials — wiring table + code](https://randomnerdtutorials.com/esp32-inmp441-i2s-microphone-arduino/))
- Power: module VDD runs on 3.3V from the ESP32 board (do NOT feed 5V). ([Random Nerd Tutorials — wiring table](https://randomnerdtutorials.com/esp32-inmp441-i2s-microphone-arduino/))
- India price: INMP441 I2S module listed on Robu.in ([product page](https://robu.in/product/inmp441-mems-high-precision-omnidirectional-microphone-module-i2s/)); Amazon.in price history shows ₹149–₹299 range (recent ~₹249–₹299). ([Pricehistory Amazon.in tracker 1](https://pricehistory.app/p/inmp441-omnidirectional-mems-microphone-module-digital-i2s-8CmtTmQ2), [tracker 2](https://pricehistory.app/p/inmp441-mems-digital-microphone-module-high-sensitivity-6PQYsAce))
- Beginner difficulty: LOW — 5–6 Dupont wires, no soldering if pre-soldered header version is bought; working Arduino example exists verbatim (RMS / waveform / clap). Gotcha: some cheap modules ship unsoldered (e.g. Robu square variant notes "unsoldered" — [page](https://robu.in/product/square-omnidirectional-microphone-module-unsoldered/)), so order the soldered-header version.

### MAX98357A I2S DAC + amp module
- What it is: I2S digital input → DAC → mono Class-D amp on one board; drives 4Ω/8Ω speaker directly (spec 8Ω 1.8W / 4Ω 2.5W at 12 dB gain; supply 3.3–5V; sample rates 8–96 kHz). ([DFRobot DFR0954 wiki — spec table](https://wiki.dfrobot.com/dfr0954/))
- Module pins: VCC, GND, DIN (I2S data in), BCLK (bit clock), LRC/WS (frame clock), SD (shutdown + channel select by voltage/resistance), GAIN (3/6/9/12/15 dB; default 9 dB unconnected), SPK+/SPK− to speaker. ([DFRobot DFR0954 wiki — pinout](https://wiki.dfrobot.com/dfr0954/))
- ESP32 wiring: VCC→5V (or 3V3), GND→GND, DIN/BCLK/LRC→3 free GPIOs via ESP32 I2S-out; leave SD unconnected (mixed default) or pull per channel table; GAIN default 9 dB is fine to start. ([DFRobot DFR0954 wiki](https://wiki.dfrobot.com/dfr0954/), [Adafruit MAX98357 guide PDF](https://cdn-learn.adafruit.com/downloads/pdf/adafruit-max98357-i2s-class-d-mono-amp.pdf), [MakerGuides ESP32+MAX98357A](https://www.makerguides.com/playing-audio-with-esp32-and-max98357/))
- Speaker needed in addition: any 4Ω 3W (or 8Ω 1–3W) small speaker; module output is mono. ([DFRobot wiki — SPK pins 4Ω/8Ω <3W](https://wiki.dfrobot.com/dfr0954/))
- India price: MAX98357A breakout listed on Robu.in ([SmartElex breakout](https://robu.in/product/smartelex-i2s-audio-breakout-max98357a/), [plug-and-play variant](https://robu.in/product/bgamax98357a-i2s-amplifier-breakout-module/)); IndiaMART lists MAX98357A module at ~₹112/piece (Mumbai supplier — [listing](https://www.indiamart.com/proddetail/max98357a-module-2854328308555.html)); Amazon.in carries 2-packs ([search](https://www.amazon.in/max98357/s?k=max98357)). Budget ~₹150–₹350 for one module depending on seller.
- Beginner difficulty: LOW — same Dupont-wire level as the mic; no analog circuitry. Gotchas: (a) mic and speaker need SEPARATE I2S peripherals/pins (mic = I2S RX, amp = I2S TX — both supported on ESP32 per [ESP-IDF I2S docs via RNT](https://randomnerdtutorials.com/esp32-inmp441-i2s-microphone-arduino/)); (b) SD pin left floating = mixed mono, which is what you want — don't ground it (ground = shutdown per [DFRobot wiki](https://wiki.dfrobot.com/dfr0954/)).

### Board note (needed for §2): get an ESP32-S3 with PSRAM
- ESP32-S3 DevKit with 16MB flash + 8MB PSRAM (N16R8) listed on Robu.in ([product page](https://robu.in/product/esp32-s3-devkit-esp32-s3-wroom-1-n16r8/)); Amazon.in shows ESP32-S3 N16R8 dev board ~₹1,299 (MRP ₹1,949). ([Amazon.in esp32-s3 search](https://www.amazon.in/esp32-s3/s?k=esp32+s3))
- Plain ESP32 (no PSRAM) is cheaper but cannot run the recommended 2026 wake-word stacks (see §2) — the ~₹300–500 premium for S3+PSRAM is the single most important parts choice in this ticket's fact set.

## 2. On-device wake-word options in 2026 (ESP32 vs ESP32-S3 + PSRAM)

### ESP-Skainet / ESP-SR WakeNet (Espressif official)
- What it is: Espressif's voice assistant lib — WakeNet wake-word engine + speech-commands, inside the ESP-SR / AFE (audio front-end) pipeline. ([esp-skainet GitHub](https://github.com/espressif/esp-skainet), [ESP-SR WakeNet S3 docs](https://docs.espressif.com/projects/esp-sr/en/latest/esp32s3/wake_word_engine/README.html))
- Chip support: WakeNet9 supports ESP32, ESP32-S3, ESP32-P4; WakeNet9l improves fast-speech pickup; ESP32-S3 is the recommended chip ("latest models will be deployed on ESP32-S3 first… high-speed octal SPI PSRAM"). ([esp-skainet README](https://github.com/espressif/esp-skainet), [ESP-SR WakeNet README](https://docs.espressif.com/projects/esp-sr/en/latest/esp32s3/wake_word_engine/README.html))
- RAM cost (measured, ESP32-S3): WakeNet9 2-ch = 16 KB internal + 324 KB PSRAM, 3.0 ms/frame; full AFE (AEC+VAD+WakeNet) single-mic configs need ~49–60 KB internal + ~740–815 KB PSRAM and ~9–13% of one core for feed + ~10% fetch. Dual-mic configs need ~1.15–1.24 MB PSRAM. Net: PSRAM is effectively mandatory. ([ESP-SR S3 benchmark](https://docs.espressif.com/projects/esp-sr/en/latest/esp32s3/benchmark/README.html))
- Accuracy (Espressif's own test, ESP32-S3-Korvo, WakeNet9 "Alexa", 1 m / 3 m): ~98% quiet, ~96% stationary noise, ~94% speech noise; false-trigger rate ~once per 12 h. ([ESP-SR S3 benchmark — performance test](https://docs.espressif.com/projects/esp-sr/en/latest/esp32s3/benchmark/README.html))
- Custom wake words: possible via Espressif's "Speech Wake-up Solution Customization Process" (vendor-trained, not DIY-in-an-afternoon). ([ESP-SR WakeNet README — customization link](https://docs.espressif.com/projects/esp-sr/en/latest/esp32s3/wake_word_engine/README.html))
- UX trade-off: best noise/AEC handling of the three (full AFE with AEC+VAD), most professional fixed-phrase accuracy, but heaviest setup (ESP-IDF, model flashing per [flash-models doc](https://docs.espressif.com/projects/esp-sr/en/latest/esp32s3/wake_word_engine/README.html)) and least beginner-friendly custom-word path.

### MicroWakeWord (ESPHome)
- What it is: open-source streaming wake-word lib (int8 TFLite, MixConv, 16 kHz mono → 40 features/10 ms, inference every 30 ms) by Kevin Ahrendt / now Open Home Foundation; ESPHome's on-device wake-word component. ([micro-wake-word GitHub](https://github.com/OHF-Voice/micro-wake-word), [author page](https://www.kevinahrendt.com/micro-wake-word), [ESPHome micro_wake_word docs](https://esphome.io/components/micro_wake_word/))
- Chip support: built for ESP32-S3 ("suitable for ESP32-S3 devices" — [author page](https://www.kevinahrendt.com/micro-wake-word); platform markets "ESP32-S3, ESPHome" — [microwakeword.com](https://microwakeword.com/)). Plain ESP32 is NOT a supported target for current models. ESPHome exposes PSRAM task-stack option (`task_stack_in_psram`, requires the [PSRAM component](https://esphome.io/components/psram/)). ([ESPHome micro_wake_word docs](https://esphome.io/components/micro_wake_word/))
- Model size signal: example v2 model JSON needs `tensor_arena_size: 22860` bytes per model + VAD model; YAML supports probability cutoff / sliding-window tuning and `stop_after_detection`. ([ESPHome micro_wake_word docs](https://esphome.io/components/micro_wake_word/))
- Pre-trained words available from [esphome/micro-wake-word-models](https://github.com/esphome/micro-wake-word-models) (e.g. okay_nabu, hey_mycroft); training a NEW custom word is explicitly "intended for advanced users… requires experimentation" with the Piper-sample-generator + notebook flow. ([micro-wake-word README](https://github.com/OHF-Voice/micro-wake-word))
- UX trade-off: easiest path IF you accept a stock wake word + ESPHome voice-assistant pipeline (`on_wake_word_detected → voice_assistant.start` per [ESPHome example](https://esphome.io/components/micro_wake_word/)); tunable false-accept/reject via cutoff + window + optional VAD model. Custom-word training is the hardest of the three for a beginner.

### Edge Impulse (keyword spotting)
- What it is: hosted TinyML studio (data collect → DSP → train → EON-compiled ESP32 firmware); community ESP32-S3 wake-word templates exist. ([Edge Impulse keyword-spotting template example](https://github.com/klumw/wakeword), [ESP32-S3 TinyML guide](https://openelab.io/blogs/learn/esp32-s3-tinyml-image-audio-sensor-models))
- Chip support: ESP32-S3 target (S3 required in practice for audio models; plain ESP32 fits only tiny models — see EON RAM-optimization being Enterprise-only below).
- Price: Developer plan $0/month (3 private projects, ≤3 collaborators, 60 min compute/job, community support); production/external distribution needs Enterprise custom pricing (up to 1000 units internal deployment on production subscription). ([Edge Impulse pricing](https://www.edgeimpulse.com/pricing))
- UX trade-off: most flexible (any custom word, visual data pipeline) and best learning tool, but model quality depends entirely on YOUR dataset; most effort of the three; EON Compiler RAM-optimized mode and full tuner search space are Enterprise-only. ([Edge Impulse pricing — feature table](https://www.edgeimpulse.com/pricing))

### 2026 bottom-line facts (no recommendation — ticket 01 decides)
- All three practical paths require ESP32-S3 + PSRAM; none is recommended on plain ESP32 in 2026.
- Fixed-phrase accuracy crown (vendor-measured): ESP-SR WakeNet9 (~98% quiet, 1 false trigger/12 h). MicroWakeWord optimizes false-accepts/hour on ambient clips during training. Edge Impulse quality = your data.
- Custom-word ease (inverse): Edge Impulse tooling (easiest to attempt) > ESP-Skainet vendor customization > MicroWakeWord DIY training (explicitly advanced).

## 3. Cloud STT → LLM → TTS: cheapest reliable path from India (per-minute math + free tiers)

Convention: DeskBuddy turns are short (~10 s mic clip up, ~10–15 s speech back, ~a few hundred LLM tokens). Per-minute rates below are provider list prices; divide by ~4–6 for a per-turn estimate. $1 ≈ ₹83–₹90 (note rate assumed at build time).

### STT comparison
| Provider / model | List price (primary source) | Free tier (primary source) | ~Cost per 10-s turn |
|---|---|---|---|
| Gemini 3.5 Transcribe (batch/file) | $2.00/1M audio-input tokens ≈ **$0.003/min** audio + $12.00/1M text-output ≈ $0.002/min text → blended **~$0.005/min**. ([Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)) | Free tier listed (free input+output tokens; rate limits apply). ([Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)) | ~$0.0008 (~₹0.07) |
| Gemini 3.5 Transcribe Live (streaming) | ≈ **~$0.009/min blended** (page's own estimate). ([Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)) | Free tier listed. ([Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)) | ~$0.0015 (~₹0.13) |
| OpenAI `gpt-4o-mini-transcribe` | **$0.003/min** estimated. ([OpenAI pricing](https://developers.openai.com/api/docs/pricing)) | No free tier (API is pay-per-use). | ~$0.0005 (~₹0.04) — cheapest STT per minute |
| OpenAI `gpt-4o-transcribe` / Whisper Large | **$0.006/min** estimated. ([OpenAI pricing](https://developers.openai.com/api/docs/pricing)) | No free tier. | ~$0.001 (~₹0.09) |
| OpenAI `gpt-transcribe` (newer/cheapest) | **$0.0045/min** estimated. ([OpenAI pricing](https://developers.openai.com/api/docs/pricing)) | No free tier. | ~$0.00075 (~₹0.06) |
| Deepgram Nova-3 monolingual | Streaming **$0.0048/min** (promo; regular $0.0077), pre-recorded **$0.0043/min**. ([Deepgram pricing](https://deepgram.com/pricing)) | **$200 free credit**, no card required. ([Deepgram pricing](https://deepgram.com/pricing)) | ~$0.0008 (~₹0.07) |
| Deepgram Nova-3 multilingual (Hindi/Hinglish) | Streaming **$0.0058/min**, pre-recorded **$0.0052/min**. ([Deepgram pricing](https://deepgram.com/pricing)) | Same $200 credit. | ~$0.001 (~₹0.08) |

- Reliability notes: Deepgram Nova-3 is the accuracy pick for noisy/far-field + 45+ languages incl. auto language detection ([Deepgram pricing page](https://deepgram.com/pricing)); Gemini Transcribe adds diarization/timestamps/vocab biasing ([Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)); OpenAI mini-transcribe is cheapest/min but English-leaning vs Nova-3 multilingual.
- India angle: all three bill in USD by card; Gemini's free tier and Deepgram's $200 credit make both effectively free during build/test; none lists India-specific pricing.

### LLM comparison (the reply brain — tiny cost vs STT/TTS)
| Provider / model | List price (primary source) | Free tier | ~Cost per turn (~500 in + 150 out tokens) |
|---|---|---|---|
| Gemini 2.5 Flash-Lite | $0.10 in / $0.40 out per 1M (text). ([Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)) | Free tier. | ~$0.0001 (~₹0.01) — cheapest LLM |
| Gemini 2.5 Flash | $0.30 in / $2.50 out per 1M. ([Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)) | Free tier + 500 RPD grounding. | ~$0.0005 (~₹0.04) |
| OpenAI `gpt-6-luna` (current cheapest flagships page) | $0.10 in / $0.50 out per 1M short-context. ([OpenAI pricing](https://developers.openai.com/api/docs/pricing)) | No free tier. | ~$0.0001 (~₹0.01) |

- Fact: LLM cost is ~10× smaller than STT+TTS per turn — optimize STT/TTS choice first.

### TTS comparison
| Provider / model | List price (primary source) | Free tier | ~Cost per 10-s reply (~150 chars) |
|---|---|---|---|
| Gemini 3.8 Flash-Lite TTS | $0.50/1M text-in + $6.00/1M audio-out ≈ **$0.0015 per 10 s audio**. ([Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)) | Free tier. | ~$0.0015 (~₹0.13) — cheapest TTS |
| Gemini 3.8 Flash TTS | $9.00/1M audio-out ≈ **$0.00225 per 10 s**. ([Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)) | Free tier. | ~$0.0023 (~₹0.19) |
| Deepgram Aura-1 / Aura-2 / Flux | $0.0150 / $0.030 / $0.045 per 1k chars. ([Deepgram pricing](https://deepgram.com/pricing)) | $200 credit covers. | Aura-1: ~$0.0023 (~₹0.19); Aura-2: ~$0.0045 (~₹0.38) |
| OpenAI TTS | Current price list is token-based audio models (see [OpenAI pricing](https://developers.openai.com/api/docs/pricing)); legacy per-char list ($15/1M chars tts-1 class) per secondary trackers ([InWorld 2026 TTS comparison](https://inworld.ai/resources/best-text-to-speech-apis), [AwesomeAgents leaderboard](https://awesomeagents.ai/leaderboards/ai-voice-speech-leaderboard/)) — VERIFY on the live pricing page at build time, OpenAI renames models frequently. | No free tier. | If $15/1M chars: ~$0.0023 (~₹0.19) |

### Cheapest-combo arithmetic (facts, not a decision)
- All-Gemini (Transcribe $0.005/min + Flash-Lite LLM + Flash-Lite TTS $0.0015/10 s): ≈ **$0.0025–$0.003 per turn ≈ ₹0.21–₹0.27**, inside free tier while prototyping. Sources: [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing).
- OpenAI mini-transcribe + cheap LLM + cheap TTS: ≈ **$0.003–$0.004 per turn**, no free tier. Source: [OpenAI pricing](https://developers.openai.com/api/docs/pricing).
- Deepgram Nova-3 + any LLM + Aura-1: ≈ **$0.004 per turn**, covered by $200 credit (≈ 40,000+ turns). Source: [Deepgram pricing](https://deepgram.com/pricing).
- Hindi/Hinglish note: prefer multilingual STT (Nova-3 multilingual $0.0058/min streaming; Gemini Transcribe auto language detection) over English-only models. ([Deepgram pricing](https://deepgram.com/pricing), [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing))

## 4. Latency expectation + push-to-talk fallback

### Latency budget (engineering estimate from primary numbers, India broadband assumed)
- Wake-word detect (on-device): one WakeNet9 frame = 3.0 ms, 32 ms frame length ([ESP-SR benchmark](https://docs.espressif.com/projects/esp-sr/en/latest/esp32s3/benchmark/README.html)); MicroWakeWord infers every 30 ms ([micro-wake-word README](https://github.com/OHF-Voice/micro-wake-word)). Practical trigger-to-action: **~50–200 ms** after keyword end (smoothing window per [WakeNet README](https://docs.espressif.com/projects/esp-sr/en/latest/esp32s3/wake_word_engine/README.html) / `sliding_window_size` per [ESPHome docs](https://esphome.io/components/micro_wake_word/)).
- Upload 5–10 s clip (ESP32 Wi-Fi, India home broadband): **~0.3–1 s**.
- Cloud STT: **~0.5–1.5 s** (batch/file slower than Live/streaming endpoints: Gemini Live Transcribe vs Transcribe priced separately per [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing); Deepgram Flux targets "ultra-low latency" streaming per [Deepgram pricing](https://deepgram.com/pricing)).
- LLM reply (short prompt, Flash-class): **~0.5–1.5 s**.
- TTS synth + download + first audio out of MAX98357A: **~0.5–1.5 s**.
- **End-to-end push-wake → speech: typically ~2–5 s on this pipeline; ~1.5–2.5 s with streaming STT + short replies; 5–8 s+ on slow Wi-Fi or long replies.** (Arithmetic from the components above, not a vendor SLA — ticket 01 should set the UX target, e.g. eyes "thinking" state to cover the gap.)
- Live/full-duplex APIs (Gemini Live $0.005–$0.018/min audio; OpenAI GPT-Live $0.05/min; Deepgram Voice Agent $0.05–$0.163/min — [Gemini](https://ai.google.dev/gemini-api/docs/pricing), [OpenAI](https://developers.openai.com/api/docs/pricing), [Deepgram](https://deepgram.com/pricing)) cut turn latency but cost 5–30× per minute vs the batch pipeline — facts only.

### Push-to-talk fallback (if wake-word fails)
- Mechanism: a physical button (or capacitive touch pad) on DeskBuddy = "talk now" — bypasses wake-word entirely: button press → record fixed window (e.g. 6–8 s) or record-while-held → same STT→LLM→TTS pipeline → play on MAX98357A.
- Why reliable: zero ML involved; same proven INMP441 I2S capture path as §1 ([RNT code](https://randomnerdtutorials.com/esp32-inmp441-i2s-microphone-arduino/)); ESPHome natively supports start/stop semantics (`micro_wake_word.start/stop`, `voice_assistant.start` per [ESPHome docs](https://esphome.io/components/micro_wake_word/)) so PTT and wake-word can share one pipeline.
- Recommended wiring fact: use any free GPIO with internal pull-up + debounce (the RNT clap example already demonstrates threshold/gap/cooldown timing logic adaptable to a button — [code](https://randomnerdtutorials.com/esp32-inmp441-i2s-microphone-arduino/)); add a mute/PTT LED indicator for the always-listening privacy concern (map.md open question).
- Cost: one tactile button ≈ ₹5–₹20; zero cloud-cost difference (same APIs per §3).

---
*Sources are linked inline per claim. No architecture chosen — ticket 01 decides.*
