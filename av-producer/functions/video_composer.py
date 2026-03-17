"""Video composition tool for AV novel production.

Assembles images, audio narration, subtitles, and BGM into final video
using ffmpeg subprocess calls. Two modes: illustrated and subtitle.

Illustrated mode supports multiple images per chapter with Ken Burns
(zoompan) effects and crossfade transitions between scenes.
"""

from __future__ import annotations

import json
import random
import subprocess
import shutil
from pathlib import Path

from langchain_core.tools import tool
from loguru import logger


def _get_audio_duration(audio_path: str) -> float:
    """Get audio duration in seconds via ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return 30.0


def _zoompan_filter(input_idx: int, seq_idx: int, duration: float, width: int, height: int, variant: int = 0) -> str:
    """Generate a zoompan filter with Ken Burns effect for one image.

    Args:
        input_idx: ffmpeg input index (may have gaps due to audio inputs)
        seq_idx: sequential index for filter label naming (0, 1, 2, ...)

    Different variants produce different movement styles:
      0 = slow zoom in (center)
      1 = slow zoom out
      2 = pan left to right with slight zoom
      3 = pan right to left with slight zoom
    """
    fps = 25
    total_frames = int(duration * fps)

    if variant % 4 == 0:
        zp = (
            f"zoompan=z='min(zoom+0.0008,1.4)'"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={total_frames}:s={width}x{height}:fps={fps}"
        )
    elif variant % 4 == 1:
        zp = (
            f"zoompan=z='if(eq(on,0),1.4,max(zoom-0.0008,1.0))'"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={total_frames}:s={width}x{height}:fps={fps}"
        )
    elif variant % 4 == 2:
        zp = (
            f"zoompan=z='1.2'"
            f":x='(iw/zoom-{width})*on/{total_frames}'"
            f":y='ih/2-(ih/zoom/2)'"
            f":d={total_frames}:s={width}x{height}:fps={fps}"
        )
    else:
        zp = (
            f"zoompan=z='1.2'"
            f":x='(iw/zoom-{width})*(1-on/{total_frames})'"
            f":y='ih/2-(ih/zoom/2)'"
            f":d={total_frames}:s={width}x{height}:fps={fps}"
        )

    return f"[{input_idx}:v]scale={width*2}:-1,{zp},setsar=1[zv{seq_idx}]"


def _build_illustrated_ffmpeg_cmd(
    chapters: list[dict],
    output_path: str,
    bgm_path: str = "",
    resolution: str = "1920x1080",
) -> list[str]:
    """Build ffmpeg command for illustrated mode with Ken Burns + crossfade.

    Supports two input types per chapter:
      - video_paths: list of video clip files (AI-generated) — concatenated directly
      - image_paths/image_path: list of static images — zoompan Ken Burns effect applied
    Priority: video_paths > image_paths > image_path
    """
    width, height = resolution.split("x")
    w, h = int(width), int(height)
    cmd = ["ffmpeg", "-y"]
    xfade_duration = 0.5

    # Collect all visual segments and audio inputs
    # Each segment is either a video clip or an image with zoompan
    segments = []  # (input_idx, duration, segment_type, variant)
    #   segment_type: "video" or "image"
    audio_input_indices = []
    input_idx = 0

    for ch in chapters:
        audio_path = ch["audio_path"]
        ch_duration = _get_audio_duration(audio_path)

        # Check for video clips first (priority over images)
        video_paths = ch.get("video_paths", [])
        if video_paths:
            per_clip = ch_duration / len(video_paths)
            for vp in video_paths:
                cmd.extend(["-i", vp])
                segments.append((input_idx, per_clip, "video", 0))
                input_idx += 1
        else:
            # Fall back to image paths
            image_paths = ch.get("image_paths", [])
            if not image_paths:
                single = ch.get("image_path", "")
                image_paths = [single] if single else []

            if not image_paths:
                # Add audio anyway, skip visual
                cmd.extend(["-i", audio_path])
                audio_input_indices.append(input_idx)
                input_idx += 1
                continue

            num_images = len(image_paths)
            per_image = ch_duration / num_images

            for j, img_path in enumerate(image_paths):
                cmd.extend(["-loop", "1", "-i", img_path])
                variant = (len(segments) + j) % 4
                segments.append((input_idx, per_image, "image", variant))
                input_idx += 1

        cmd.extend(["-i", audio_path])
        audio_input_indices.append(input_idx)
        input_idx += 1

    if not segments:
        return ["echo", "No visual inputs to compose"]

    # Build filter_complex
    filter_parts = []

    # 1. Process each segment based on type
    for seq_idx, (inp_idx, dur, seg_type, variant) in enumerate(segments):
        if seg_type == "image":
            filter_parts.append(_zoompan_filter(inp_idx, seq_idx, dur, w, h, variant))
        else:
            # Video clip: scale to target resolution and fps, trim to allocated duration
            filter_parts.append(
                f"[{inp_idx}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=25,"
                f"trim=duration={dur:.2f},setpts=PTS-STARTPTS[zv{seq_idx}]"
            )

    # 2. Chain xfade transitions between all segments
    if len(segments) == 1:
        final_video = "[zv0]"
    else:
        running_offset = 0.0
        prev_label = "zv0"
        for i in range(1, len(segments)):
            _, prev_dur, _, _ = segments[i - 1]
            running_offset += prev_dur - xfade_duration
            out_label = f"xf{i}" if i < len(segments) - 1 else "outv"
            filter_parts.append(
                f"[{prev_label}][zv{i}]xfade=transition=fade"
                f":duration={xfade_duration}:offset={running_offset:.2f}[{out_label}]"
            )
            prev_label = out_label
        final_video = "[outv]"

    # 3. Overlay subtitles on the composed video
    subtitles = []
    running_time = 0.0
    for ch in chapters:
        sub_text = (ch.get("subtitle_text") or ch.get("narration_text") or "").strip()
        ch_dur = _get_audio_duration(ch["audio_path"])
        if sub_text:
            subtitles.append((running_time, running_time + ch_dur, sub_text))
        running_time += ch_dur

    if subtitles:
        # Generate ASS subtitle file for proper text wrapping and CJK support
        import platform
        import tempfile
        if platform.system() == "Darwin":
            fontname = "STHeiti"
        else:
            fontname = "Noto Sans CJK SC"

        ass_content = (
            "[Script Info]\nScriptType: v4.00+\nPlayResX: {w}\nPlayResY: {h}\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Default,{fontname},26,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
            "0,0,0,0,100,100,0,0,1,2,1,2,30,30,40,1\n\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        ).format(w=w, h=h)

        for t_start, t_end, text in subtitles:
            def _fmt_ts(s):
                hrs = int(s // 3600)
                mins = int((s % 3600) // 60)
                secs = int(s % 60)
                cs = int((s % 1) * 100)
                return f"{hrs}:{mins:02d}:{secs:02d}.{cs:02d}"
            clean = text.replace("\n", "\\N")
            ass_content += f"Dialogue: 0,{_fmt_ts(t_start)},{_fmt_ts(t_end)},Default,,0,0,0,,{clean}\n"

        ass_file = tempfile.NamedTemporaryFile(mode='w', suffix='.ass', delete=False, encoding='utf-8')
        ass_file.write(ass_content)
        ass_file.close()

        # Apply subtitles filter
        src_label = final_video.strip("[]")
        escaped_ass = ass_file.name.replace(":", "\\:").replace("'", "\\'")
        filter_parts.append(
            f"[{src_label}]ass='{escaped_ass}'[subout]"
        )
        final_video = "[subout]"

    # 3b. Concat all chapter audio
    a_labels = "".join(f"[{idx}:a]" for idx in audio_input_indices)
    filter_parts.append(f"{a_labels}concat=n={len(audio_input_indices)}:v=0:a=1[outa]")

    # 4. Mix BGM if available
    if bgm_path and Path(bgm_path).exists():
        cmd.extend(["-i", bgm_path])
        filter_parts.append(f"[{input_idx}:a]volume=0.15[bgm]")
        filter_parts.append("[outa][bgm]amix=inputs=2:duration=first[finala]")
        audio_map = "[finala]"
    else:
        audio_map = "[outa]"

    cmd.extend(["-filter_complex", ";".join(filter_parts)])
    cmd.extend(["-map", final_video, "-map", audio_map])
    cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "23"])
    cmd.extend(["-c:a", "aac", "-b:a", "192k"])
    cmd.extend(["-shortest", "-movflags", "+faststart", output_path])
    return cmd


def _build_subtitle_ffmpeg_cmd(
    chapters: list[dict],
    output_path: str,
    bgm_path: str = "",
    resolution: str = "1920x1080",
) -> list[str]:
    """Build ffmpeg command for subtitle mode (text + audio on dark bg)."""
    cmd = ["ffmpeg", "-y"]
    cmd.extend(["-f", "lavfi", "-i", f"color=c=0x1a1a2e:s={resolution}:r=24"])
    audio_inputs = []

    for i, ch in enumerate(chapters):
        cmd.extend(["-i", ch["audio_path"]])
        audio_inputs.append(f"[{i+1}:a]")

    filter_parts = [f"{''.join(audio_inputs)}concat=n={len(chapters)}:v=0:a=1[outa]"]

    if bgm_path and Path(bgm_path).exists():
        bgm_idx = 1 + len(chapters)
        cmd.extend(["-i", bgm_path])
        filter_parts.append(f"[{bgm_idx}:a]volume=0.15[bgm]")
        filter_parts.append("[outa][bgm]amix=inputs=2:duration=first[finala]")
        audio_map = "[finala]"
    else:
        audio_map = "[outa]"

    cmd.extend(["-filter_complex", ";".join(filter_parts)])
    cmd.extend(["-map", "0:v", "-map", audio_map])
    cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "23"])
    cmd.extend(["-c:a", "aac", "-b:a", "192k"])
    cmd.extend(["-shortest", output_path])
    return cmd


@tool
def video_composer(
    mode: str,
    chapters_json: str,
    bgm_path: str = "",
    bgm_volume: float = 0.15,
    output_path: str = "",
    resolution: str = "1920x1080",
) -> dict:
    """Assemble chapter images, audio, and subtitles into a final video.

    Args:
        mode: 'illustrated' (images + audio) or 'subtitle' (text + audio).
        chapters_json: JSON string of chapters list. Each dict has:
            image_path (single) or image_paths (list), audio_path, subtitle_text.
        bgm_path: Path to background music file (optional).
        bgm_volume: BGM volume 0-1 (default 0.15).
        output_path: Where to save the video.
        resolution: Output resolution (default 1920x1080).

    Returns:
        Dict with video_path, duration_seconds, and status.
    """
    if not output_path:
        return {"status": "error", "error": "output_path is required"}

    if not shutil.which("ffmpeg"):
        return {"status": "error", "error": "ffmpeg not found. Install with: brew install ffmpeg"}

    try:
        chapters = json.loads(chapters_json)
    except json.JSONDecodeError as e:
        return {"status": "error", "error": f"Invalid chapters_json: {e}"}

    if not chapters:
        return {"status": "error", "error": "chapters list is empty"}

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if mode == "illustrated":
        cmd = _build_illustrated_ffmpeg_cmd(chapters, output_path, bgm_path, resolution)
    elif mode == "subtitle":
        cmd = _build_subtitle_ffmpeg_cmd(chapters, output_path, bgm_path, resolution)
    else:
        return {"status": "error", "error": f"Unknown mode: {mode}. Use 'illustrated' or 'subtitle'."}

    logger.info(f"video_composer: mode={mode}, chapters={len(chapters)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            return {"status": "error", "error": f"ffmpeg failed: {result.stderr[:500]}"}
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": "ffmpeg timed out (600s)"}

    duration = 0.0
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", output_path],
            capture_output=True, text=True, timeout=10,
        )
        duration = float(probe.stdout.strip())
    except Exception:
        logger.debug("ffprobe duration detection failed, defaulting to 0.0")

    return {
        "status": "ok",
        "video_path": output_path,
        "duration_seconds": round(duration, 2),
    }
