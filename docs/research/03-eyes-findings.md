# Ticket 03 findings — dual round LCD eyes (GC9A01 1.28", 240x240 SPI)

Scope: facts only. No behavior/expression decisions (that's ticket 06).

## 1. Exact part + India price + SPI pins + dual wiring

**Part:** 1.28" round IPS TFT LCD, 240×240 px, driver IC GC9A01 (some listings write GC9A01A — same family),
4-wire SPI, 65K RGB (16-bit) / 262K (18-bit), visible area Φ32.4 mm, PCB ≈ 40.4×37.5 mm (Φ37.5 mm).
- Specs (resolution, driver, SPI, dimensions, pin functions VCC/GND/DIN/CLK/CS/DC/RST/BL):
  https://www.waveshare.com/1.28inch-LCD-Module.htm
- Guide confirming 240×240, GC9A01, SPI, 3.3V VCC/logic:
  https://www.studiopieters.nl/gc9a01/
- Module types: Waveshare-style (onboard regulator, 3.3V/5V supply OK) vs bare modules
  (no regulator, strictly 3.3V logic; needs level shifter on 5V Arduinos):
  https://dronebotworkshop.com/gc9a01/

**India sourcing + price (per piece, verified 2026-09-30 via page fetch; GST-inclusive):**
- Makerbazar 1.28" GC9A01 round SPI module — **₹399** (₹338.13 + 18% GST), 7-pin, ~16 g:
  https://makerbazar.in/products/1-28-inch-round-tft-lcd-display-gc9a01-spi-module
- Probots 1.28" GC9A01 round IPS SPI module — **₹649** (₹550 + ₹99 GST), 8-pin unsoldered, QC-passed:
  https://probots.co.in/round-ips-color-display-module-gc9a01-1-28-inch.html
- Robu.in listing confirmed (JS-rendered price, check live page before budgeting; same part family):
  https://robu.in/product/128-inch-tft-lcd-display-module-round-240240-gc9a01-driver-spi-interface-with-soldering/
  Second Robu variant (red PCB): https://robu.in/product/128-inch-tft-display-module-240240-gc9a01-driver-spi-interface-red/
- Amazon.in listings confirmed (prices fluctuate; check live):
  https://www.amazon.in/1-28inch-Display-Resolution-Interface-Raspberry/dp/B08VGT2T42
  https://www.amazon.in/Display-Interface-Compatible-Raspberry-Tutorials/dp/B0FF426FCF
- Budget rule: 2 eyes = 2× unit price → **~₹800 (Makerbazar) to ~₹1,300 (Probots)** before shipping/headers/wires.

**SPI pins (module side → ESP32):**
| Module pin | Meaning | ESP32 (typical) |
|---|---|---|
| VCC | power | 3.3V (bare modules ONLY 3.3V) |
| GND | ground | GND |
| SCL/CLK | SPI clock | GPIO18 (HW VSPI SCK) |
| SDA/DIN | SPI MOSI (note: NOT I2C despite SDA/SCL labels) | GPIO23 (HW VSPI MOSI) |
| RES/RST | reset, low-active | GPIO4 (or any GPIO) |
| DC (A0) | data/command select (high=data, low=command) | GPIO2 or GPIO16 (any GPIO; pick per setup file) |
| CS | chip select, low-active | see dual wiring |
| BL/BLK | backlight (tie 3.3V = always on, or PWM pin for dimming) | 3.3V or PWM GPIO (e.g. GPIO15) |
| MISO | not used (display is write-only) | leave unconnected |
- Pin table + ESP32 example wiring (VCC 3.3V, SCL→18, SDA→23, RES→4, DC→2, CS→5, BLK→15):
  https://www.studiopieters.nl/gc9a01/
- Alternate ESP32 wiring used for TFT_eSPI (MOSI 23, SCLK 18, CS 22, DC 16, RST 4):
  https://dronebotworkshop.com/gc9a01/
- Waveshare official pin definitions (VCC/GND/DIN/CLK/CS/DC/RST/BL):
  https://www.waveshare.com/1.28inch-LCD-Module.htm

**Dual-display wiring (verified pattern): share everything except CS.**
- All lines in parallel (MOSI, SCLK, DC, RST, BL, VCC, GND); only CS is per-display
  (eye-1 CS GPIO22, eye-2 CS GPIO21 in the DroneBot demo):
  https://dronebotworkshop.com/gc9a01/
- LovyanGFX dual-panel example: one shared SPI bus (SCLK 18, MOSI 23, shared DC 33),
  per-panel CS (21 and 5) + per-panel RST (19 and 4), `bus_shared = true`:
  https://github.com/lovyan03/LovyanGFX/discussions/254
- Probots FAQ confirms multi-display on one SPI bus with unique CS per display:
  https://probots.co.in/round-ips-color-display-module-gc9a01-1-28-inch.html
- Practical: keep jumper wires short; 20+ loose breadboard wires cap usable SPI speed
  (60–70 MHz dual vs 80 MHz single reported): https://github.com/lovyan03/LovyanGFX/discussions/254

## 2. ESP32 vs ESP32-S3 driving TWO GC9A01s

**Library support (both chips supported by both libraries):**
- TFT_eSPI supports GC9A01 and ESP32 / S2 / S3 / C3; DMA (SPI) on ESP32 and S3
  (not on C3/S2); GC9A01 explicitly in supported-controller list:
  https://github.com/Bodmer/TFT_eSPI
- TFT_eSPI news: ESP32-S3 DMA works with ESP-IDF > 2.0.14 / Arduino-ESP32 3.3.6
  (uses SPI_DMA_CH_AUTO); S3 board setups shipped in library:
  https://github.com/Bodmer/TFT_eSPI
- LovyanGFX feature list: multi-display simultaneous use, DMA, ESP32-optimized:
  https://github.com/lovyan03/LovyanGFX
- 2026 assessment: TFT_eSPI still the staple; LovyanGFX favored for newer controllers
  and DMA handling — either drives dual GC9A01:
  https://electricalflux.com/mcu-peripherals/diy-lcd-screen-esp32-tft-character-wiring
- TFT_eSPI called "industry standard for GC9A01" with font/sprite support:
  https://probots.co.in/round-ips-color-display-module-gc9a01-1-28-inch.html

**Which library for a beginner:** TFT_eSPI — it ships the dual-eye demo
(`examples/Generic/Animated_Eyes_2`) with a documented `config.h`
(CS pins, rotation, joystick/blink pins, AUTOBLINK/TRACKING flags):
https://dronebotworkshop.com/gc9a01/ and https://github.com/Bodmer/TFT_eSPI
LovyanGFX dual setup requires hand-written bus/panel structs (flexible, but more code):
https://github.com/lovyan03/LovyanGFX/discussions/254

**SPI frequency:**
- GC9A01-class SPI TFTs clock up to ~80 MHz on ESP32 (40 MHz ESP8266-class, 55 MHz STM32
  reference values from TFT_eSPI-family docs): https://github.com/IcingTomato/TFT_eSPI_GC9A01
- Measured dual-screen LovyanGFX on breadboard: ~80 MHz single, ~60–70 MHz dual;
  example config uses `freq_write = 60 MHz`, `freq_read = 16 MHz`:
  https://github.com/lovyan03/LovyanGFX/discussions/254
- TFT_eSPI on ESP32-S3 + GC9A01 needed ~27 MHz + HSPI port on one user's breadboard
  without DMA; enable DMA for full speed:
  https://github.com/Bodmer/TFT_eSPI/discussions/2233
- Beginner setting: start 27–40 MHz, raise toward 60–80 MHz only with short solid wiring.

**Achievable FPS (blink/look):**
- Math: one full 240×240×16-bit frame = 115,200 bytes ≈ 0.92 Mbit;
  at 40 MHz ≈ ~43 fps theoretical per eye for full-frame pushes, halved when two eyes
  are updated sequentially — so full-screen animation is SPI-bound, not CPU-bound.
- Practice: eye code does NOT push full frames; it redraws a ~128×128 eye window
  (see `setAddrWindow(...,128,128)` centering note) + sprites, so blink/look/saccade
  motion is smooth (visibly fluid in both demos below) at modest SPI clocks:
  https://dronebotworkshop.com/gc9a01/ (comments: Rodolfo/Tuttle threads)
- Demos proving smooth dual-eye motion on plain ESP32 + TFT_eSPI:
  https://github.com/thelastoutpostworkshop/ESP32LCDRound240x240Eyes and
  https://dronebotworkshop.com/gc9a01/
- ESP32 vs S3 verdict for eyes alone: plain ESP32 (WROOM/WROVER) is enough;
  S3 preferred when the same brain also does camera/voice (more RAM, USB-OTG,
  DMA) — cross-check with ticket 01's brain choice. No eye-specific S3 requirement found.

**RAM:**
- Sprite cost: 16-bit sprite = 2×W×H bytes; 8-bit = W×H; 1-bit = W×H/8:
  https://github.com/Bodmer/TFT_eSPI
- Without PSRAM, ESP32 fits ~200×200 16-bit sprite (~80 KB); full 240×240×16-bit
  framebuffer = 115,200 bytes per eye (230 KB for two) needs PSRAM
  (WROVER / S3 with PSRAM) or partial-window/sprites:
  https://github.com/Bodmer/TFT_eSPI
- Eye graphics tables ("HUGE graphics tables for various eyes") live in flash;
  enable only one eye style (`defaultEye.h` etc.) to save flash:
  https://dronebotworkshop.com/gc9a01/
- GC9A01 chip has 129,600 bytes GRAM (240×240 area):
  https://www.lcdwiki.com/res/MSP1281/GC9A01_Datasheet_REV.1.0.pdf and
  https://buydisplay.com/download/ic/GC9A01A.pdf

## 3. Reusable open-source eye code (beginner-friendly)

1. TFT_eSPI built-in `Animated_Eyes_1` / `Animated_Eyes_2` (dual GC9A01 + config.h,
   eye styles: default/dragon/cat/goat/owl/terminator…): https://github.com/Bodmer/TFT_eSPI
   (walkthrough with wiring + config edits): https://dronebotworkshop.com/gc9a01/
2. thelastoutpostworkshop ESP32 + dual GC9A01 uncanny-eye port + YouTube wiring tutorial
   (117★, TFT_eSPI): https://github.com/thelastoutpostworkshop/ESP32LCDRound240x240Eyes
3. Adafruit "Animated Electronic Eyes" learn guide — the original uncanny-eyes project
   (concept, wiring logic, eye-rendering approach; Teensy/M0/M4-era, concepts reused
   by ESP32 ports): https://learn.adafruit.com/animated-electronic-eyes/overview
4. Instructables "TFT Animated Eyes" — 3-step ESP32 + TFT_eSPI beginner build
   (ST7735 screens, same codebase pattern ports to GC9A01):
   https://www.instructables.com/TFT-Animated-Eyes/
5. CyberRobotEyesTFT — simpler cartoon robo-eyes for ESP32+TFT (moods, auto-blink,
   double-buffered; easier to read than photorealistic uncanny eyes):
   https://github.com/Cyb3rPre4cher/CyberRobotEyesTFT
6. AZ-Delivery ESP32 + 2× GC9A01 animated-eyes project page (beginner wiring + TFT_eSPI config):
   https://www.az-delivery.de/en/products/aminierte-augen-projekt
7. Grobot animations — lightweight spring-physics robot eyes for ESP32 + TFT_eSPI
   (single-function-call API): https://projecthub.arduino.cc/tanmay_wankar/abbc33b9-9695-4064-935e-b2d713090a80

## 4. Gotchas

- **3.3V logic only (bare modules):** not 5V-tolerant; run VCC + signals at 3.3V.
  Sources: https://www.studiopieters.nl/gc9a01/ ("not 5V tolerant"),
  https://dronebotworkshop.com/gc9a01/ (bare variant = 3.3V only, Uno needs level shifter),
  https://probots.co.in/round-ips-color-display-module-gc9a01-1-28-inch.html
  (strictly 3.3V; level shifter required on 5V Unos; multi-CS sharing OK).
  Exception: Waveshare-style boards accept 3.3V/5V supply (onboard regulator) —
  check the specific listing: https://www.waveshare.com/1.28inch-LCD-Module.htm
- **SDA/SCL labels ≠ I2C.** On GC9A01 modules SDA=MOSI/DIN, SCL=SCLK — it is SPI:
  https://dronebotworkshop.com/gc9a01/
- **Backlight current:** ~20 mA at full brightness per Probots FAQ
  (BLK→3.3V always-on, or PWM pin for dimming):
  https://probots.co.in/round-ips-color-display-module-gc9a01-1-28-inch.html ;
  budget ~50–100 mA worst-case per module (logic+backlight), i.e. ~100–200 mA
  for two eyes on the 3.3V rail — fine on USB-powered ESP32 dev boards, but don't
  hang them on a weak LDO pin. (Module-level 100 mA figure for an ESP32+GC9A01
  combo board: https://www.ecer.com/corp/details-uuuc47q-p16hnvb-esp32-display-tool-gc9a01-driver-chip-100ma-power-consumption-about-20g-weight.html)
- **Weight/mounting on servo head:** module ≈ 16 g (Makerbazar spec:
  https://makerbazar.in/products/1-28-inch-round-tft-lcd-display-gc9a01-spi-module)
  to ~20 g with headers; two eyes ≈ 32–40 g + wires/mount. Glass is round but PCB
  is square — design a circular cutout hiding PCB edges (tip:
  https://www.studiopieters.nl/gc9a01/). Center mass on the pan-servo horn, leave
  cable slack/service loop for head movement, use M2 standoffs/screws, route the
  shared SPI bundle as one loom with two short CS tails. (Servo-torque sizing itself
  belongs to ticket 05.)
- **Wiring reliability:** MISO unused; CS low-active; DC high=data/low=command;
  RST low-active (Waveshare pin table: https://www.waveshare.com/1.28inch-LCD-Module.htm).
  Long/breadboard wiring forces lower SPI clocks; solder headers cleanly (bridged SPI
  pads = no init — Probots safety notes:
  https://probots.co.in/round-ips-color-display-module-gc9a01-1-28-inch.html).
- **Beginner traps:** TFT_eSPI driver/pins are set in `User_Setup.h` (not in the sketch);
  uncomment `GC9A01_DRIVER`, comment out ILI9341 default:
  https://dronebotworkshop.com/gc9a01/ ; some sellers ship unsoldered headers
  (soldering required): https://probots.co.in/round-ips-color-display-module-gc9a01-1-28-inch.html
