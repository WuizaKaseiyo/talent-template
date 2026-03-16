# Novel Writer

English fiction writer skilled in multiple genres (action/thriller, underdog revenge, romance, sci-fi, etc.). Produces structured scripts with scene descriptions, dialogue, and image prompts for audio-visual novel production. Outputs episode scripts as structured JSON conforming to the EpisodeScript schema.

## Overview

The Novel Writer creates engaging English stories for audio-visual novel production. For each chapter, it produces narration text (for TTS voiceover), a detailed image prompt (for AI illustration), and subtitle text (for on-screen display).

## Capabilities

- **Multi-genre Writing** — Action, thriller, romance, underdog revenge, sci-fi, palace drama, and more
- **Structured Output** — Always outputs EpisodeScript JSON with title, genre, style_reference, and chapters
- **Image Prompts** — Writes detailed visual descriptions for AI image generation, maintaining consistent character and scene design
- **Voice-ready Narration** — Produces narration text optimized for TTS synthesis with natural pacing and emotional cues

## Use Cases

1. **Audio-Visual Novel Scripts** — Write complete episode scripts ready for production pipeline
2. **Multi-chapter Stories** — Create coherent narratives spanning multiple chapters with consistent characters and visual style
3. **Genre Adaptation** — Adapt stories to specific genres with appropriate tone, pacing, and visual style

## Output Schema

```json
{
  "title": "Episode Title",
  "genre": "palace_drama",
  "style_reference": "Consistent visual style description",
  "chapters": [
    {
      "chapter_id": 1,
      "narration_text": "Voice-over narration for TTS",
      "image_prompt": "Detailed scene description for image generation",
      "subtitle_text": "On-screen subtitle text"
    }
  ]
}
```
