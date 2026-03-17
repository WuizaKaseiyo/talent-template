"""BGM generation tool for AV novel production.

Uses Suno API (via sunoapi.org) for AI music generation.
Falls back to silent audio if SUNO_API_KEY is not set.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from langchain_core.tools import tool
from loguru import logger

_SUNO_API_BASE = "https://api.sunoapi.org/api/v1"
_SUNO_GENERATE_URL = f"{_SUNO_API_BASE}/generate"
_SUNO_STATUS_URL = f"{_SUNO_API_BASE}/generate/record-info"
_POLL_INTERVAL = 5  # seconds
_MAX_POLL_ATTEMPTS = 60  # 5 min max wait
_COST_PER_GENERATION = 0.05  # ~$0.05 per song


def _suno_request(url: str, api_key: str, payload: dict | None = None, method: str = "POST") -> tuple[dict | None, str | None]:
    """Make a request to the Suno API."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
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
    except Exception as e:  # network errors
        return None, str(e)


def _download_audio(url: str, output_path: str) -> bool:
    """Download audio file from URL."""
    req = urllib.request.Request(url, headers={"User-Agent": "OneManCompany-Production/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(resp.read())
        return True
    except Exception as e:
        logger.warning(f"Failed to download audio: {e}")
        return False


def _generate_with_suno(genre: str, duration_seconds: float, output_path: str) -> dict:
    """Generate music using Suno API."""
    api_key = os.environ.get("SUNO_API_KEY", "").strip()
    if not api_key:
        return {"status": "error", "error": "SUNO_API_KEY not set"}

    # Suno generates ~2 min songs. Use instrumental mode for BGM.
    payload = {
        "prompt": f"Instrumental {genre} background music, cinematic, no vocals",
        "customMode": True,
        "style": genre.replace("_", " "),
        "title": f"BGM - {genre}",
        "instrumental": True,
        "model": "V4",
    }

    logger.info(f"bgm_generator: calling Suno API (genre={genre})")
    resp, err = _suno_request(_SUNO_GENERATE_URL, api_key, payload)
    if err:
        return {"status": "error", "error": f"Suno generate failed: {err}"}
    if not resp or resp.get("code") != 200:
        return {"status": "error", "error": f"Suno API error: {resp}"}

    task_id = resp.get("taskId", "")
    if not task_id:
        return {"status": "error", "error": f"No taskId in Suno response: {resp}"}

    # Poll for completion
    logger.info(f"bgm_generator: polling Suno task {task_id}")
    for attempt in range(_MAX_POLL_ATTEMPTS):
        time.sleep(_POLL_INTERVAL)
        status_url = f"{_SUNO_STATUS_URL}?taskId={task_id}"
        status_resp, status_err = _suno_request(status_url, api_key, method="GET")
        if status_err:
            logger.warning(f"bgm_generator: poll error: {status_err}")
            continue

        if not status_resp or status_resp.get("code") != 200:
            continue

        suno_data = status_resp.get("data", {}).get("sunoData", [])
        if not suno_data:
            continue

        # Check first song (Suno generates 2, we take the first)
        song = suno_data[0]
        if song.get("status") == "complete":
            audio_url = song.get("audioUrl", "")
            if audio_url and _download_audio(audio_url, output_path):
                actual_duration = song.get("duration", duration_seconds)
                # Trim to requested duration if needed
                if actual_duration > duration_seconds and shutil.which("ffmpeg"):
                    trimmed = output_path + ".trimmed.mp3"
                    try:
                        subprocess.run(
                            ["ffmpeg", "-y", "-i", output_path, "-t", str(duration_seconds), "-c", "copy", trimmed],
                            capture_output=True, timeout=30, check=True,
                        )
                        Path(trimmed).replace(output_path)
                    except Exception as e:
                        logger.warning(f"bgm_generator: trim failed: {e}")

                return {
                    "status": "ok",
                    "audio_path": output_path,
                    "duration_seconds": min(actual_duration, duration_seconds),
                    "cost_usd": _COST_PER_GENERATION,
                    "suno_task_id": task_id,
                }

        if song.get("errorMessage"):
            return {"status": "error", "error": f"Suno generation failed: {song['errorMessage']}"}

    return {"status": "error", "error": f"Suno generation timed out after {_MAX_POLL_ATTEMPTS * _POLL_INTERVAL}s"}


def _generate_silent_audio(duration_seconds: float, output_path: str) -> dict:
    """Fallback: generate a silent audio file using ffmpeg."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if shutil.which("ffmpeg"):
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                 "-t", str(duration_seconds), "-q:a", "9", output_path],
                capture_output=True, timeout=30, check=True,
            )
            return {
                "status": "ok",
                "audio_path": output_path,
                "duration_seconds": duration_seconds,
                "cost_usd": 0.0,
            }
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.warning(f"ffmpeg silent audio failed: {e}")

    # Minimal fallback
    Path(output_path).write_bytes(b"\xff\xfb\x90\x00" * max(1, int(duration_seconds * 26)))
    return {
        "status": "ok",
        "audio_path": output_path,
        "duration_seconds": duration_seconds,
        "cost_usd": 0.0,
    }


@tool
def bgm_generator(
    genre: str,
    duration_seconds: float,
    output_path: str = "",
) -> dict:
    """Generate background music matching a genre and duration.

    Uses Suno AI for music generation. Falls back to silent audio
    if SUNO_API_KEY is not set.

    Args:
        genre: Music genre/mood (e.g., 'tense_cinematic', 'romantic').
        duration_seconds: Target duration in seconds.
        output_path: Where to save the audio file.

    Returns:
        Dict with audio_path, duration_seconds, cost_usd, and status.
    """
    if not output_path:
        return {"status": "error", "error": "output_path is required"}

    if os.environ.get("SUNO_API_KEY", "").strip():
        result = _generate_with_suno(genre, duration_seconds, output_path)
        if result["status"] == "ok":
            return result
        logger.warning(f"bgm_generator: Suno failed, falling back to silent: {result.get('error')}")

    logger.info("bgm_generator: using silent audio fallback (no API key)")
    return _generate_silent_audio(duration_seconds, output_path)
