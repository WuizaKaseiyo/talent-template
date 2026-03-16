---
name: Media Production
description: End-to-end audio-visual novel production — from script to final video output.
---

# Media Production

Orchestrate the full production pipeline for illustrated audio novels.

## Guidelines

- Process chapters sequentially: generate image, generate TTS audio, then compose video
- Maintain visual consistency across chapters using style_reference from the script
- Generate BGM once per episode, matching the genre and mood
- Use video_clip_generator for dynamic scenes; use static images for dialogue-heavy scenes
- Always validate all assets exist before final video composition
- Output both illustrated format (images/clips + audio) and subtitle format when requested
