# Research 02 — Tracking: camera ≤₹500 vs PIR fallback (FACTS ONLY)

Date: 2026-09-30. Prices in INR, incl. GST where stated. Checked 2026-09-30; Indian store stock flips fast.
Scope: facts for ticket 01. No architecture decision made here.

## 1. ESP32-CAM — India price + face-detection usability

### 1a. Prices

| Store | Product | Price (30 Sep 2026) | Stock | Source |
|---|---|---|---|---|
| Robokits | ESP32-CAM WiFi+BT + OV3660 (RKI-1459) | **₹582** | Out of stock (page live) | https://robokits.co.in/iot-wireless-solutions/iot-internet-of-things/iot-esp-module/esp32-cam-development-board-wifi-bluetooth-with-ov3660-camera-module |
| Robosap | ESP32-CAM OV2640/OV3660 (random), board only | **₹761.10 incl. GST** (₹645 + GST) | In stock (2 nos) | https://robosap.in/product/esp32-cam-camera-development-board-ov2640-2-megapixels/ |
| Robu.in | ESP32-CAM WiFi+BT OV2640 2MP (AI-Thinker style) | Listing exists; price not retrievable (page timed out / JS-rendered on fetch) — typically ₹600–750 band per Robokits/Robosap comps | Unknown | https://robu.in/product/esp32-cam-wifi-module-bluetooth-with-ov2640-camera-module-2mp/ |
| Amazon.in | ESP32-CAM OV2640 + CH340 USB-serial bundle (UNO Compatible seller) | **₹1,999** (M.R.P. ₹3,998) | In stock | https://www.amazon.in/ESP32-CAM-Wireless-Applications-Monitoring-Compatible/dp/B0FHFYJB5G and search https://www.amazon.in/esp32-cam-module/s?k=esp32+cam+module |

Hidden extras (fact, affects ₹500 budget):
- Bare ESP32-CAM has **no USB**; flashing needs FTDI/USB-TTL or ESP32-CAM-MB baseboard (Robosap notes "TF Card and USB-to-TTL programmer are usually sold separately"): https://robosap.in/product/esp32-cam-camera-development-board-ov2640-2-megapixels/
- Random Nerd Tutorials wiring guide confirms GPIO0-to-GND flashing ritual + FTDI at 5V: https://randomnerdtutorials.com/esp32-cam-video-streaming-face-recognition-arduino-ide/
- Robokits cross-sell shows FT232RL USB-TTL adapter at **₹87**: https://robokits.co.in/iot-wireless-solutions/iot-internet-of-things/iot-esp-module/esp32-cam-development-board-wifi-bluetooth-with-ov3660-camera-module (customers-also-purchased section)

Board specs (all from store spec tables): ESP32-S dual-core up to 240 MHz, 520 KB SRAM + ~4 MB PSRAM, 802.11b/g/n + BT/BLE, OV2640 or OV3660, microSD slot, 5 V recommended: https://robokits.co.in/iot-wireless-solutions/iot-internet-of-things/iot-esp-module/esp32-cam-development-board-wifi-bluetooth-with-ov3660-camera-module and https://robosap.in/product/esp32-cam-camera-development-board-ov2640-2-megapixels/

### 1b. Is on-board face detection usable for head tracking?

Primary sources:
- Espressif ESP-WHO framework (face detection/recognition platform): https://github.com/espressif/esp-who
- ESP-WHO docs: https://documentation.espressif.com/esp-who/master/README.md
- ESP-WHO examples folder: https://github.com/espressif/esp-who/tree/master/examples

Facts:
- ESP-WHO **exists and is official**, with Human Face Detection / Recognition / Pedestrian / QR examples: https://github.com/espressif/esp-who (Overview section).
- **Current master targets ESP32-S3 / ESP32-P4 boards** (ESP32-S3-EYE, ESP32-S3-Korvo-2, ESP32-P4 Function EV Board); classic ESP32/ESP32-S2 examples "not available in this branch currently — old branch release/v1.1.0": https://github.com/espressif/esp-who (What's-new + Supported-boards table).
- Arduino `CameraWebServer` example **previously** shipped face detection+recognition; Random Nerd Tutorials notes "**the latest version of the example no longer covers face detection and recognition**": https://randomnerdtutorials.com/esp32-cam-video-streaming-face-recognition-arduino-ide/
- Practical limits reported on ESP32-CAM (AI-Thinker, OV2640): face functions need a **PSRAM board**, **good lighting**, low resolution (**select CIF or lower / QVGA 320×240** before enabling), stream runs **~4–5 fps MJPEG** (serial log `MJPG: ... 4.8fps`), enrollment is fragile (must hold still; "Enroll face does nothing" and Guru-Meditation crashes widely reported in comments): https://randomnerdtutorials.com/esp32-cam-video-streaming-face-recognition-arduino-ide/ (article body + comment thread)
- Board ships with weak on-board WiFi antenna; streaming stalls attributed to signal; 5 V supply (not 3.3 V from weak FTDI) repeatedly required: https://randomnerdtutorials.com/esp32-cam-video-streaming-face-recognition-arduino-ide/ (comments/troubleshooting discussion)

Net fact for ticket 01: face detection on classic ESP32-CAM is **demo-grade (low-fps, low-res, light-sensitive, deprecated example path)**; maintained ESP-WHO path has moved to S3/P4. Usable for "rough head blob → pan servo" experiments, not robust face lock.

## 2. Cheapest USB webcam (laptop-assisted OpenCV path)

| Product | Price | Key specs | Source |
|---|---|---|---|
| Frontech FT-2251/2251 480p USB webcam | **₹569** (MRP ₹1,100, −48%) | 640×480, 30 fps, built-in mic, LED, auto white balance, plug-and-play USB, for laptop/PC | https://www.amazon.in/FRONTECH-Digital-Interface-Streaming-2251/dp/B0C6LTXKRS and search https://www.amazon.in/best-budget-webcam/s?k=best+budget+webcam |
| Same model price history | low ₹489 / avg ₹568 / high ₹790 | Confirms ₹569 is normal street price | https://pricehistory.app/p/frontech-digital-webcam-built-mic-led-lights-hgvj19Q2 |
| Flipkart listing (same family FT-2252) | ~₹1,399 (costlier channel) | 640×480, 30 fps, mic, LED | https://www.flipkart.com/frontech-ft-2252-usb-webcam-640x480-resolution-30fps-frame-rate-built-in-mic-led-lights-0-31-webcam-built-in-microphone-night-vision-connectivity/p/itm297babb393e6e |

Latency trade-off (facts):
- USB webcam to laptop is a **wired 30 fps UVC stream** (spec above) → OpenCV (Haar/MediaPipe) runs on laptop CPU at full frame rate; no WiFi MJPEG hop.
- ESP32-CAM path is a **WiFi MJPEG stream at ~4–5 fps** with documented lag/freezes ("image lags/shows lots of latency" is a listed troubleshooting symptom class): https://randomnerdtutorials.com/esp32-cam-video-streaming-face-recognition-arduino-ide/ (troubleshooting section + comments)
- Cost fact: webcam needs **no programmer, no flashing ritual, no PSRAM caveats**; needs a laptop present (assumption for ticket 01).

## 3. PIR (HC-SR501) + SG90 pan-sweep fallback

### 3a. HC-SR501 price

| Store | Price | Stock | Source |
|---|---|---|---|
| Robokits (RKI-1370) | **₹55 (sale, was ₹63)** | Out of stock | https://robokits.co.in/sensors/ir-and-pir-sensors/pir-motion-detection-sensor-module-hc-sr501 |
| Robocraze | **₹73 (was ₹85)** | Sold out at fetch time | https://robocraze.com/products/hcsr501-pir-motion-sensor-passive-infrared-sensor |
| Robu.in | Listing exists; price JS-gated (fetch returned title only) | Unknown | https://robu.in/product/pir-motion-sensor-detector-module-hc-sr501/ ; also https://robu.in/product/hc-sr501-pir-with-jumper-for-trigger/ |
| Street band | **~₹55–150** incl. GST across the three stores above | — | links above |

### 3b. Wiring simplicity (primary-spec sources)

- **3 pins only: VCC → 5 V, GND → GND, OUT → digital pin** (e.g. Arduino D8); OUT is 3.3 V TTL: HIGH = motion, LOW = idle: https://lastminuteengineers.com/pir-sensor-arduino-tutorial/ (Pinout + Arduino-wiring sections)
- Operating window **4.5–12/20 V** (regulator + reverse-polarity diode on board), draw **<2 mA** (Robocraze specs 0.06 mA avg): https://lastminuteengineers.com/pir-sensor-arduino-tutorial/ and https://robocraze.com/products/hcsr501-pir-motion-sensor-passive-infrared-sensor
- Two on-board pots: **sensitivity (3–7 m)** and **on-time delay (~1 s–3 min)**; H/L jumper = single vs retriggerable trigger: https://lastminuteengineers.com/pir-sensor-arduino-tutorial/
- Robokits spec: 5 V, 6 m range, 3.3 V output, 60 s settling, 32×24×26 mm: https://robokits.co.in/sensors/ir-and-pir-sensors/pir-motion-detection-sensor-module-hc-sr501
- Gotchas for ticket 01: **30–60 s power-on settle** (ignore output), **~2 s lockout** after output falls, needs retrigger (H) mode for occupancy: https://lastminuteengineers.com/pir-sensor-arduino-tutorial/

### 3c. SG90 servo (pan axis)

- Product: TowerPro SG90 9 g micro servo, **180° rotation, ~1.2 kg-cm torque** (Robu.in category + product pages): https://robu.in/product/towerpro-sg90-9g-mini-servo-9-gram/ and https://robu.in/product-category/towerpro-servo-motor/
- Price data points: **4-pack ₹610 on Amazon.in (~₹152/unit)**: https://www.amazon.in/Super-Debug-TowerPro-Rotation-Robotics/dp/B083HL1WZ1 ; single-unit Robu/Robokits/Flipkart listings exist (Robu page fetch returned title-only, JS price) — budget **~₹150–200/single** by 4-pack math; exact Robu single price needs re-check at purchase time: https://robu.in/product/towerpro-sg90-9g-mini-servo-9-gram/
- Drive fact (standard, for ticket 01): single PWM signal wire + 5 V/GND; Arduino `Servo` library example; no position feedback to controller.

### 3d. Why PIR+sweep can't do face lock

- PIR is a **binary motion detector**: differential pyroelectric element + Fresnel lens fires on *change* in IR, output HIGH/LOW only — **no position, no identity, no face coordinates**: https://lastminuteengineers.com/pir-sensor-arduino-tutorial/ (How-it-works section)
- Coverage is a **wide cone (~110–120°, 3–7 m)** with zones, not a pixel frame — a sweep can only "wave until PIR fires," giving **±tens-of-degrees** presence, never a face box: range/angle specs https://lastminuteengineers.com/pir-sensor-arduino-tutorial/ and https://robokits.co.in/sensors/ir-and-pir-sensors/pir-motion-detection-sensor-module-hc-sr501
- Still person = invisible (no IR *change*); pets/drafts cause false fires; delay/lockout seconds make closed-loop tracking unstable: https://lastminuteengineers.com/pir-sensor-arduino-tutorial/ (lockout + power-on-delay sections)

## 4. Budget-≈₹500 facts (beginner, code-skilled, no hardware experience)

No recommendation — arithmetic only:
- **PIR (~₹55–73) + SG90 (~₹150–200) ≈ ₹205–275** + shipping → fits ₹500 even with jumpers/breadboard. Sources: §3a + §3c links.
- **ESP32-CAM board alone ₹582–761** → already at/over ₹500 before programmer (~₹87+), shipping, 5 V supply. Sources: §1a links.
- **USB webcam ₹569** → ~₹70 over sensor budget but **₹0 programmer/flashing cost** if a laptop is already on the desk; easiest wiring (one USB plug). Source: §2 links.
- Skill facts: PIR wiring = 3 wires + example sketch (https://lastminuteengineers.com/pir-sensor-arduino-tutorial/); ESP32-CAM = flashing ritual + WiFi + PSRAM/resolution caveats (https://randomnerdtutorials.com/esp32-cam-video-streaming-face-recognition-arduino-ide/); webcam = plug-and-play per Amazon spec (https://www.amazon.in/FRONTECH-Digital-Interface-Streaming-2251/dp/B0C6LTXKRS).

## Source URL index (every claim above traces to one of these)

1. https://robokits.co.in/iot-wireless-solutions/iot-internet-of-things/iot-esp-module/esp32-cam-development-board-wifi-bluetooth-with-ov3660-camera-module
2. https://robosap.in/product/esp32-cam-camera-development-board-ov2640-2-megapixels/
3. https://robu.in/product/esp32-cam-wifi-module-bluetooth-with-ov2640-camera-module-2mp/
4. https://www.amazon.in/ESP32-CAM-Wireless-Applications-Monitoring-Compatible/dp/B0FHFYJB5G
5. https://www.amazon.in/esp32-cam-module/s?k=esp32+cam+module
6. https://github.com/espressif/esp-who
7. https://documentation.espressif.com/esp-who/master/README.md
8. https://github.com/espressif/esp-who/tree/master/examples
9. https://randomnerdtutorials.com/esp32-cam-video-streaming-face-recognition-arduino-ide/
10. https://www.amazon.in/FRONTECH-Digital-Interface-Streaming-2251/dp/B0C6LTXKRS
11. https://www.amazon.in/best-budget-webcam/s?k=best+budget+webcam
12. https://pricehistory.app/p/frontech-digital-webcam-built-mic-led-lights-hgvj19Q2
13. https://www.flipkart.com/frontech-ft-2252-usb-webcam-640x480-resolution-30fps-frame-rate-built-in-mic-led-lights-0-31-webcam-built-in-microphone-night-vision-connectivity/p/itm297babb393e6e
14. https://robokits.co.in/sensors/ir-and-pir-sensors/pir-motion-detection-sensor-module-hc-sr501
15. https://robocraze.com/products/hcsr501-pir-motion-sensor-passive-infrared-sensor
16. https://robu.in/product/pir-motion-sensor-detector-module-hc-sr501/
17. https://robu.in/product/hc-sr501-pir-with-jumper-for-trigger/
18. https://lastminuteengineers.com/pir-sensor-arduino-tutorial/
19. https://robu.in/product/towerpro-sg90-9g-mini-servo-9-gram/
20. https://robu.in/product-category/towerpro-servo-motor/
21. https://www.amazon.in/Super-Debug-TowerPro-Rotation-Robotics/dp/B083HL1WZ1
