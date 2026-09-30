Status: open
Type: grilling
Labels: wayfinder:grilling

## Question

What is the cheapest viable brain + voice architecture for DeskBuddy v1 given: no Raspberry Pi, Arduino-class budget, dual round LCD eyes, wake-word always-listening, cloud-assisted AI allowed, builder has code experience but no hardware experience?

Decide: ESP32 vs ESP32-S3 vs Arduino + ESP32-CAM combo vs ESP32 + laptop/phone assist. Where does each job run (servo PWM, eye rendering, face/motion detection, mic capture, wake-word, STT/LLM/TTS, speaker output)? What is the fallback if fully-on-device wake-word proves too heavy?
