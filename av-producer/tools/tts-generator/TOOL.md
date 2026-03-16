---
name: tts-generator
description: Convert narration text to speech audio using ElevenLabs API.
---

# TTS Generator

Converts narration text to speech audio using the ElevenLabs text-to-speech API.

## Usage

Provide narration text and an output path. Optionally specify voice ID and language.

## Parameters

- **text** (string, required) — Narration text to convert to speech
- **output_path** (string, required) — File path to save the audio file
- **voice_id** (string, optional) — ElevenLabs voice ID
- **language** (string, optional) — Language code (default: en)

## Cost

Per character pricing via ElevenLabs API
