---
name: video-clip-generator
description: Generate AI video clips from static images using PiAPI/Kling image-to-video.
---

# Video Clip Generator

Transforms static illustrations into AI-animated video clips using PiAPI/Kling image-to-video API.

## Usage

Provide a source image path and optional motion prompt. Generates a 5s or 10s video clip.

## Parameters

- **image_path** (string, required) — Path to source image
- **prompt** (string, optional) — Motion/animation description
- **duration** (string, optional) — "5" or "10" seconds (default: "5")
- **output_path** (string, required) — File path to save the video clip

## Cost

$0.13 per 5s clip, $0.26 per 10s clip
