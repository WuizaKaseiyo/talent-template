"""Video clip generation tool for AV novel production.

Uses PiAPI's Kling image-to-video API to convert static images
into short AI-generated video clips with motion.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from langchain_core.tools import tool
from loguru import logger

_PIAPI_BASE = "https://api.piapi.ai/api/v1"
_PIAPI_TASK_URL = f"{_PIAPI_BASE}/task"
_PIAPI_UPLOAD_URL = "https://upload.theapi.app/api/ephemeral_resource"
_POLL_INTERVAL = 5  # seconds
_MAX_POLL_ATTEMPTS = 60  # 5 min max wait
_COST_PER_CLIP = {"5": 0.13, "10": 0.26}
_VALID_DURATIONS = {"5", "10"}
_USER_AGENT = "OneManCompany-Production/1.0"


def _piapi_request(
    url: str, api_key: str, payload: dict | None = None, method: str = "POST",
) -> tuple[dict | None, str | None]:
    """Make a request to the PiAPI endpoint."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": _USER_AGENT,
    }
    data = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw), None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return None, f"HTTP {e.code}: {body[:500]}"
    except Exception as e:
        return None, str(e)


def _image_to_data_url(image_path: str) -> str:
    """Read a local image and return a base64 data URL."""
    data = Path(image_path).read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    # Detect format from magic bytes
    if data[:4] == b"\x89PNG":
        mime = "image/png"
    elif data[:2] == b"\xff\xd8":
        mime = "image/jpeg"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        mime = "image/png"
    return f"data:{mime};base64,{b64}"


def _upload_image_to_piapi(image_path: str, api_key: str) -> tuple[str, str | None]:
    """Upload a local image to PiAPI's ephemeral file hosting and return (url, error)."""
    data = Path(image_path).read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    ext = Path(image_path).suffix.lstrip(".") or "png"
    if ext not in ("jpg", "jpeg", "png", "webp"):
        ext = "png"
    file_name = f"image.{ext}"

    payload = json.dumps({"file_name": file_name, "file_data": b64}).encode("utf-8")
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "User-Agent": _USER_AGENT,
    }
    req = urllib.request.Request(_PIAPI_UPLOAD_URL, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
        url = (body.get("data") or {}).get("url", "")
        if url:
            return url, None
        return "", f"No URL in upload response: {body}"
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return "", f"Upload HTTP {e.code}: {err_body[:300]}"
    except Exception as e:
        return "", str(e)


def _download_video(url: str, output_path: str) -> bool:
    """Download video file from URL."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as fh:
                while chunk := resp.read(1 << 16):
                    fh.write(chunk)
        return True
    except Exception as e:
        logger.warning(f"Failed to download video: {e}")
        return False


def _generate_with_piapi(image_path: str, prompt: str, duration: str, output_path: str) -> dict:
    """Generate video clip using PiAPI Kling image-to-video."""
    api_key = os.environ.get("PIAPI_API_KEY", "").strip()
    if not api_key:
        return {"status": "error", "error": "PIAPI_API_KEY not set"}

    # Upload image to PiAPI ephemeral hosting to get an HTTP URL
    logger.info("video_clip_generator: uploading image to PiAPI file hosting")
    image_url, upload_err = _upload_image_to_piapi(image_path, api_key)
    if upload_err:
        # Fall back to data URL if upload fails
        logger.warning(f"video_clip_generator: upload failed ({upload_err}), falling back to data URL")
        image_url = _image_to_data_url(image_path)
    else:
        logger.info(f"video_clip_generator: image uploaded to {image_url}")

    payload = {
        "model": "kling",
        "task_type": "video_generation",
        "input": {
            "image_url": image_url,
            "prompt": prompt,
            "duration": int(duration),
            "aspect_ratio": "16:9",
            "mode": "std",
            "version": "2.1",
        },
        "config": {
            "service_mode": "public",
        },
    }

    logger.info(f"video_clip_generator: submitting PiAPI task (duration={duration}s)")
    resp, err = _piapi_request(_PIAPI_TASK_URL, api_key, payload)
    if err:
        return {"status": "error", "error": f"PiAPI submit failed: {err}"}

    # Extract task_id — handle multiple response shapes
    task_id = ""
    if resp:
        task_id = (
            resp.get("task_id", "")
            or (resp.get("data") or {}).get("task_id", "")
        )
    if not task_id:
        return {"status": "error", "error": f"No task_id in PiAPI response: {resp}"}

    # Poll for completion
    logger.info(f"video_clip_generator: polling PiAPI task {task_id}")
    poll_url = f"{_PIAPI_TASK_URL}/{task_id}"
    for attempt in range(_MAX_POLL_ATTEMPTS):
        time.sleep(_POLL_INTERVAL)
        status_resp, status_err = _piapi_request(poll_url, api_key, method="GET")
        if status_err:
            logger.warning(f"video_clip_generator: poll error: {status_err}")
            continue

        if not status_resp:
            continue

        # Handle multiple response nesting patterns
        task_data = status_resp.get("data", status_resp)
        status = (task_data.get("status", "") or "").lower()

        if status in ("failed", "error"):
            error_msg = task_data.get("error", "") or task_data.get("message", "unknown error")
            return {"status": "error", "error": f"PiAPI generation failed: {error_msg}"}

        if status in ("completed", "done", "success"):
            # Extract video URL — try multiple paths
            output_data = task_data.get("output", {})
            video_url = (
                output_data.get("video_url", "")
                or output_data.get("url", "")
                or task_data.get("video_url", "")
            )
            if not video_url:
                # Try nested results list
                results = output_data.get("results", []) or task_data.get("results", [])
                if results and isinstance(results, list):
                    video_url = results[0].get("url", "") or results[0].get("video_url", "")

            if video_url and _download_video(video_url, output_path):
                return {
                    "status": "ok",
                    "video_path": output_path,
                    "duration_seconds": float(duration),
                    "cost_usd": _COST_PER_CLIP[duration],
                    "task_id": task_id,
                }
            return {"status": "error", "error": f"Video URL missing or download failed. task_data: {str(task_data)[:300]}"}

    return {"status": "error", "error": f"PiAPI generation timed out after {_MAX_POLL_ATTEMPTS * _POLL_INTERVAL}s"}


def _generate_with_ffmpeg_kenburns(image_path: str, duration: str, output_path: str) -> dict:
    """Fallback: generate a Ken Burns zoom/pan video clip from image using ffmpeg."""
    import subprocess
    import shutil

    if not shutil.which("ffmpeg"):
        return {"status": "error", "error": "ffmpeg not found for fallback"}

    dur = int(duration)
    fps = 25
    total_frames = dur * fps
    # Slow zoom-in with slight pan
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", image_path,
        "-vf", (
            f"scale=3840:-1,"
            f"zoompan=z='min(zoom+0.002,1.8)'"
            f":x='iw/2-(iw/zoom/2)+sin(on/{total_frames}*3.14)*50'"
            f":y='ih/2-(ih/zoom/2)'"
            f":d={total_frames}:s=1920x1080:fps={fps},"
            f"format=yuv420p"
        ),
        "-t", str(dur),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-movflags", "+faststart",
        output_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            return {"status": "error", "error": f"ffmpeg failed: {result.stderr[:300]}"}
        return {
            "status": "ok",
            "video_path": output_path,
            "duration_seconds": float(dur),
            "cost_usd": 0.0,
            "method": "ffmpeg_kenburns_fallback",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@tool
def video_clip_generator(
    image_path: str,
    prompt: str,
    duration: str = "5",
    output_path: str = "",
) -> dict:
    """Generate a short AI video clip from a static image using Kling.

    Takes an image (from image_generator) and a motion description,
    then produces a 5 or 10 second video clip with AI-generated motion.

    Args:
        image_path: Path to the source image (PNG/JPG).
        prompt: Motion description, e.g. "camera slowly zooms in, character turns head".
        duration: Clip length — "5" or "10" seconds.
        output_path: Where to save the output video (MP4).

    Returns:
        Dict with video_path, duration_seconds, cost_usd, and status.
    """
    if not output_path:
        return {"status": "error", "error": "output_path is required"}

    if duration not in _VALID_DURATIONS:
        return {"status": "error", "error": f"Invalid duration '{duration}'. Must be '5' or '10'."}

    if not Path(image_path).exists():
        return {"status": "error", "error": f"Image not found: {image_path}"}

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    return _generate_with_piapi(image_path, prompt, duration, output_path)
