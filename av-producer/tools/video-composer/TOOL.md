---
name: video-composer
description: Assemble final video from images, audio, BGM, and subtitles using ffmpeg.
---

# Video Composer

Assembles all production assets into final video using ffmpeg. Supports crossfade transitions, audio mixing, and subtitle overlays.

## Usage

Provide lists of image/video paths, audio paths, and optional BGM and subtitle paths. Produces a single composed video file.

## Parameters

- **image_paths** (list, optional) — List of image file paths (for illustrated format)
- **video_paths** (list, optional) — List of video clip paths (for animated format)
- **audio_paths** (list, required) — List of narration audio file paths
- **bgm_path** (string, optional) — Background music file path
- **subtitle_path** (string, optional) — Subtitle file path (SRT format)
- **output_path** (string, required) — File path to save the final video

## Cost

Free (local ffmpeg)
