---
name: tts-generator
description: Convert narration text to speech audio using ElevenLabs API.
---

# TTS Generator

Converts text to speech using ElevenLabs. Supports multiple voices and languages (English and Chinese).

## Parameters

- **text** (string, required) — Narration text to convert
- **output_path** (string, required) — File path to save audio
- **voice_id** (string, optional) — ElevenLabs voice ID
- **model_id** (string, optional) — ElevenLabs model (default: eleven_multilingual_v2)

## Cost

Per character pricing via ElevenLabs API
