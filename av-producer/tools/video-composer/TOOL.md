---
name: video-composer
description: Assemble final video from images, audio, BGM, and subtitles using ffmpeg.
---

# Video Composer

Assembles all production assets into final video with subtitle overlay (ASS format), audio mixing, and Ken Burns transitions.

## Parameters

- **mode** (string, required) — "illustrated" (images + audio) or "subtitle" (text + audio)
- **chapters_json** (string, required) — JSON of chapters with audio_path, image_paths/image_path, narration_text
- **bgm_path** (string, optional) — Background music file
- **bgm_volume** (float, optional) — BGM volume 0-1 (default: 0.15)
- **output_path** (string, required) — Final video path
- **resolution** (string, optional) — Output resolution (default: 1920x1080)

## Cost

Free (local ffmpeg)
