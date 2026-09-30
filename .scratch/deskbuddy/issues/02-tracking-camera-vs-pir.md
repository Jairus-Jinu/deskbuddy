Status: resolved
Type: research
Labels: wayfinder:research

## Answer

No camera fits ₹500. ESP32-CAM board alone is ₹582–₹761 (+₹87 programmer, 30 Sep 2026) and its on-board face detection is demo-grade (QVGA, ~5fps, deprecated example path; ESP-WHO moved to S3/P4). Cheapest workable paths: PIR HC-SR501 (₹55–73) + SG90 (~₹150–200) ≈ ₹205–275 total for motion-sweep (no face lock), or Frontech USB webcam ₹569 if a laptop is on the desk (30fps UVC + OpenCV = real face lock, zero flashing). Full facts: `../research/02-tracking-findings.md`.

## Question

Can movement tracking be done with a camera at ~≤₹500 in India (ESP32-CAM or cheap USB webcam for laptop-assist), or should v1 fall back to PIR/ultrasonic motion-follow with no face lock? Survey current India pricing (Robu, Robokits, Amazon.in, 2026) and beginner feasibility (ESP32-CAM face detection quality, wiring pain, laptop OpenCV alternative).

Blocked by: 01
