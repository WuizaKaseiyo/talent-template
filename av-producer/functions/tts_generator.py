"""ElevenLabs TTS tool for AV novel production."""

from __future__ import annotations

import os
from pathlib import Path

import httpx
from langchain_core.tools import tool
from loguru import logger

ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech"
DEFAULT_VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # "Adam"
DEFAULT_MODEL_ID = "eleven_multilingual_v2"
COST_PER_CHAR = 0.30 / 1000


async def _call_elevenlabs(
    text: str,
    voice_id: str,
    model_id: str,
    output_path: str,
    stability: float = 0.5,
    similarity_boost: float = 0.75,
    style: float = 0.4,
    speed: float = 1.0,
) -> dict:
    """Call ElevenLabs TTS API and save audio to output_path."""
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        return {"status": "error", "error": "ELEVENLABS_API_KEY not set"}

    url = f"{ELEVENLABS_API_URL}/{voice_id}"
    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
        },
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, headers=headers, json=payload)

    if resp.status_code != 200:
        return {"status": "error", "error": f"ElevenLabs API {resp.status_code}: {resp.text[:200]}"}

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_bytes(resp.content)

    file_size = len(resp.content)
    duration_seconds = max(file_size / (128 * 1024 / 8), 0.1)
    cost_usd = len(text) * COST_PER_CHAR

    return {
        "status": "ok",
        "audio_path": output_path,
        "duration_seconds": round(duration_seconds, 2),
        "cost_usd": round(cost_usd, 4),
    }


@tool
def tts_generator(
    text: str,
    voice_id: str = "",
    voice_style: str = "confident_male",
    model_id: str = DEFAULT_MODEL_ID,
    stability: float = 0.5,
    similarity_boost: float = 0.75,
    speed: float = 1.0,
    output_path: str = "",
) -> dict:
    """Generate text to speech audio using ElevenLabs API.

    Args:
        text: The text to convert to speech.
        voice_id: ElevenLabs voice ID. Defaults to confident male voice.
        voice_style: Voice preset name (used if voice_id is empty).
        model_id: ElevenLabs model ID.
        stability: Voice stability (0-1).
        similarity_boost: Voice similarity boost (0-1).
        speed: Speech speed multiplier.
        output_path: Where to save the audio file.

    Returns:
        Dict with audio_path, duration_seconds, cost_usd, and status.
    """
    import asyncio

    if not voice_id:
        voice_id = DEFAULT_VOICE_ID

    if not output_path:
        return {"status": "error", "error": "output_path is required"}

    coro = _call_elevenlabs(
        text=text, voice_id=voice_id, model_id=model_id, output_path=output_path,
        stability=stability, similarity_boost=similarity_boost, speed=speed,
    )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    # Already in an event loop — run in a new thread
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result(timeout=120)
