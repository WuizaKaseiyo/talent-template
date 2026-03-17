"""Image generation tool for AV novel production.

Uses OpenRouter with google/gemini-3.1-flash-image-preview model.
Reuses the proven multi-attempt strategy from the existing image_generation asset tool.
Falls back to placeholder if API key is not set.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import struct
import urllib.error
import urllib.request
import zlib
from pathlib import Path

from langchain_core.tools import tool
from loguru import logger

_MODEL = "google/gemini-3.1-flash-image-preview"
_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
_USER_AGENT = "OneManCompany-Production/1.0"

# Gemini Flash image generation is very cheap
_COST_PER_IMAGE = 0.005


def _post_json(url: str, headers: dict, payload: dict, timeout: int = 60) -> tuple[dict | None, str | None]:
    """POST JSON and return (json_body, error)."""
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw), None
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return None, f"HTTP {e.code}: {body_text[:800]}"
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON response: {e}"
    except Exception as e:  # network errors, timeouts
        return None, str(e)


def _decode_data_url(data_url: str) -> tuple[bytes | None, str]:
    """Decode data:image/...;base64,... into bytes."""
    if not data_url.startswith("data:image/") or "," not in data_url:
        return None, ""
    header, payload = data_url.split(",", 1)
    mime = header.split(";")[0][5:].strip() or "image/png"
    try:
        return base64.b64decode(payload), mime
    except Exception:  # malformed base64
        return None, ""


def _decode_base64(payload: str) -> bytes | None:
    """Decode base64 payload (supports missing padding)."""
    text = payload.strip()
    if not text:
        return None
    try:
        return base64.b64decode(text, validate=True)
    except Exception:
        pad = "=" * (-len(text) % 4)
        try:
            return base64.b64decode(text + pad)
        except Exception:
            return None


def _download_image(url: str) -> tuple[bytes | None, str]:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
            mime = resp.headers.get_content_type() or "image/png"
            return data, mime
    except Exception:  # download failure is non-fatal, we try next extraction
        return None, ""


def _iter_values(obj):
    """Yield (key, value) pairs recursively for dict/list trees."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from _iter_values(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_values(item)


def _extract_image_bytes(response_json: dict) -> tuple[bytes | None, str]:
    """Try to extract generated image bytes from multiple response layouts."""
    # 1) OpenAI Images style
    data = response_json.get("data")
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            b64_payload = item.get("b64_json") or item.get("image_base64")
            if isinstance(b64_payload, str):
                decoded = _decode_base64(b64_payload)
                if decoded:
                    return decoded, "image/png"
            url = item.get("url") or item.get("image_url")
            if isinstance(url, str):
                if url.startswith("data:image/"):
                    decoded, mime = _decode_data_url(url)
                    if decoded:
                        return decoded, mime
                elif url.startswith(("http://", "https://")):
                    downloaded, mime = _download_image(url)
                    if downloaded:
                        return downloaded, mime

    # 2) Recursive scan for common fields
    base64_keys = {"b64_json", "image_base64", "base64", "b64"}
    url_keys = {"image_url", "url"}
    for key, value in _iter_values(response_json):
        if key in base64_keys and isinstance(value, str):
            decoded = _decode_base64(value)
            if decoded:
                return decoded, "image/png"
        if key in url_keys:
            url_value = ""
            if isinstance(value, str):
                url_value = value
            elif isinstance(value, dict) and isinstance(value.get("url"), str):
                url_value = value["url"]
            if url_value.startswith("data:image/"):
                decoded, mime = _decode_data_url(url_value)
                if decoded:
                    return decoded, mime
            elif url_value.startswith(("http://", "https://")):
                downloaded, mime = _download_image(url_value)
                if downloaded:
                    return downloaded, mime
        if isinstance(value, str) and "data:image/" in value:
            m = re.search(r"(data:image/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=_-]+)", value)
            if m:
                decoded, mime = _decode_data_url(m.group(1))
                if decoded:
                    return decoded, mime

    return None, ""


def _mime_to_ext(mime: str) -> str:
    return {
        "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif",
    }.get(mime.lower(), ".png")


def _call_openrouter(prompt: str, output_path: str) -> dict:
    """Call OpenRouter Gemini Flash image generation."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return {"status": "error", "error": "OPENROUTER_API_KEY not set"}

    base_url = os.environ.get("OPENROUTER_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": _USER_AGENT,
        "X-Title": os.environ.get("OPENROUTER_APP_NAME", "OneManCompany"),
        "HTTP-Referer": os.environ.get("OPENROUTER_HTTP_REFERER", "http://localhost:8000"),
    }

    attempts = [
        ("chat.text", f"{base_url}/chat/completions", {
            "model": _MODEL,
            "messages": [{"role": "user", "content": prompt}],
        }),
        ("chat.multimodal", f"{base_url}/chat/completions", {
            "model": _MODEL,
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        }),
        ("responses", f"{base_url}/responses", {
            "model": _MODEL, "input": prompt,
        }),
    ]

    errors: list[str] = []
    for attempt_name, url, payload in attempts:
        resp_json, err = _post_json(url, headers, payload)
        if err:
            errors.append(f"{attempt_name}: {err}")
            continue
        assert resp_json is not None
        image_bytes, image_mime = _extract_image_bytes(resp_json)
        if image_bytes:
            out = Path(output_path)
            if not out.suffix:
                out = out.with_suffix(_mime_to_ext(image_mime))
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(image_bytes)
            return {
                "status": "ok",
                "image_path": str(out),
                "cost_usd": _COST_PER_IMAGE,
                "model": _MODEL,
                "bytes": len(image_bytes),
            }
        snippet = json.dumps(resp_json, ensure_ascii=False)[:400]
        errors.append(f"{attempt_name}: no image found, response={snippet}")

    return {
        "status": "error",
        "error": f"All {len(attempts)} attempts failed",
        "details": errors,
    }


def _generate_placeholder(prompt: str, output_path: str) -> dict:
    """Fallback: generate a colored placeholder PNG."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    h = int(hashlib.md5(prompt.encode()).hexdigest()[:6], 16)
    r, g, b = (h >> 16) & 0xFF, (h >> 8) & 0xFF, h & 0xFF
    raw = struct.pack("B", 0) + struct.pack("BBB", r, g, b)

    def png_chunk(chunk_type, data):
        c = chunk_type + data
        crc = zlib.crc32(c) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + c + struct.pack(">I", crc)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    idat = png_chunk(b"IDAT", zlib.compress(raw))
    iend = png_chunk(b"IEND", b"")
    Path(output_path).write_bytes(sig + ihdr + idat + iend)
    return {"status": "ok", "image_path": output_path, "cost_usd": 0.0}


@tool
def image_generator(
    prompt: str,
    style: str = "cinematic",
    aspect_ratio: str = "16:9",
    output_path: str = "",
) -> dict:
    """Generate an illustration image from a text prompt using AI.

    Uses OpenRouter with Gemini Flash image model.

    Args:
        prompt: Detailed image description.
        style: Art style (cinematic, anime, comic, realistic).
        aspect_ratio: Output aspect ratio.
        output_path: Where to save the generated image.

    Returns:
        Dict with image_path, cost_usd, and status.
    """
    if not output_path:
        return {"status": "error", "error": "output_path is required"}

    full_prompt = f"Generate a {style} illustration in {aspect_ratio} aspect ratio: {prompt}"

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return {"status": "error", "error": "OPENROUTER_API_KEY not set"}

    logger.info(f"image_generator: calling OpenRouter ({_MODEL})")
    return _call_openrouter(full_prompt, output_path)
