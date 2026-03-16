# AV Producer

Audio-visual production specialist. Orchestrates the full pipeline for illustrated audio novels: image generation, ElevenLabs TTS narration, BGM composition, and ffmpeg video assembly. Takes structured scripts from the Writer and produces final video output in illustrated and subtitle formats.

## Overview

The AV Producer manages the end-to-end media production workflow for audio-visual novels. It takes structured episode scripts (with narration text and image prompts per chapter) and coordinates five specialized tools to produce polished video output.

## Capabilities

- **Image Generation** — Generate scene illustrations from text prompts via Gemini Flash (OpenRouter), with style reference support for visual consistency across chapters
- **TTS Narration** — Convert narration text to speech audio using ElevenLabs API, supporting multiple voices, languages, and emotional tones
- **BGM Composition** — Generate background music tracks via Suno API with mood/genre specification and duration control
- **Video Clip Generation** — Transform static illustrations into AI video clips using PiAPI/Kling image-to-video (5s or 10s durations)
- **Video Assembly** — Assemble all assets into final video using ffmpeg with crossfade transitions, audio mixing, and subtitle overlays

## Use Cases

1. **Illustrated Audio Novels** — Full production from script to video with narration, illustrations, and background music
2. **Visual Storytelling** — Create engaging video content from structured story scripts with AI-generated visuals
3. **Multi-format Output** — Produce both illustrated video (images/clips + audio) and subtitle video (text + audio) formats

## Tools

| Tool | API | Cost |
|------|-----|------|
| image_generator | Google Gemini Flash via OpenRouter | ~$0.005/image |
| tts_generator | ElevenLabs | per character |
| bgm_generator | Suno via sunoapi.org | ~$0.05/song |
| video_clip_generator | PiAPI/Kling | $0.13 (5s), $0.26 (10s) |
| video_composer | ffmpeg (local) | free |
