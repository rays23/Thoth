"""Transcribe audio via Groq or OpenAI Whisper API.

Pure stdlib — no SDK needed. Prefers Groq (cheaper, faster), falls back to
OpenAI. Returns segments in the same shape as captions.parse_vtt.
Ported from bradautomates/claude-video.
"""
from __future__ import annotations

import io
import json
import logging
import mimetypes
import os
import shutil
import subprocess
import urllib.error
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

import config

logger = logging.getLogger(__name__)

_GROQ_ENDPOINT = "https://api.groq.com/openai/v1/audio/transcriptions"
_GROQ_MODEL = "whisper-large-v3"
_OPENAI_ENDPOINT = "https://api.openai.com/v1/audio/transcriptions"
_OPENAI_MODEL = "whisper-1"


def load_api_key() -> tuple[str, str] | tuple[None, None]:
    """Return (backend, api_key). Prefers Groq, falls back to OpenAI."""
    candidates = [
        ("GROQ_API_KEY", "groq", config.GROQ_API_KEY),
        ("OPENAI_API_KEY", "openai", config.OPENAI_API_KEY),
    ]
    for _, backend, value in candidates:
        if value:
            return backend, value
    return None, None


def extract_audio(video_path: Path, out_path: Path) -> Path:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found. Install with: brew install ffmpeg")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video_path.resolve()),
        "-vn", "-acodec", "libmp3lame",
        "-ar", "16000", "-ac", "1", "-b:a", "64k",
        str(out_path.resolve()),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed: {result.stderr.strip()}")
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise RuntimeError("ffmpeg produced no audio — video may have no audio track")
    return out_path


def _build_multipart(fields: dict[str, str], file_path: Path) -> tuple[bytes, str]:
    boundary = f"----ThothBoundary{uuid.uuid4().hex}"
    eol = b"\r\n"
    buf = io.BytesIO()

    for name, value in fields.items():
        buf.write(f"--{boundary}".encode()); buf.write(eol)
        buf.write(f'Content-Disposition: form-data; name="{name}"'.encode()); buf.write(eol)
        buf.write(eol)
        buf.write(str(value).encode()); buf.write(eol)

    mimetype = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    buf.write(f"--{boundary}".encode()); buf.write(eol)
    buf.write(
        f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"'.encode()
    ); buf.write(eol)
    buf.write(f"Content-Type: {mimetype}".encode()); buf.write(eol)
    buf.write(eol)
    buf.write(file_path.read_bytes()); buf.write(eol)
    buf.write(f"--{boundary}--".encode()); buf.write(eol)

    return buf.getvalue(), f"multipart/form-data; boundary={boundary}"


def _post_whisper(endpoint: str, api_key: str, model: str, audio_path: Path) -> dict:
    body, content_type = _build_multipart(
        {"model": model, "response_format": "verbose_json", "timestamp_granularities[]": "segment"},
        audio_path,
    )
    req = Request(endpoint, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", content_type)
    # Cloudflare vor Groq lehnt die Standardkennung "Python-urllib" mit Fehler 1010 ab.
    req.add_header("User-Agent", "Thoth/1.0 (+https://github.com/rays23/Thoth)")

    try:
        with urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_err = e.read().decode("utf-8", errors="ignore")[:300]
        raise RuntimeError(f"Whisper API error {e.code}: {body_err}") from e


def _segments_from_response(data: dict) -> list[dict]:
    out = []
    for seg in data.get("segments") or []:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        out.append({
            "start": round(float(seg.get("start") or 0.0), 2),
            "end": round(float(seg.get("end") or 0.0), 2),
            "text": text,
        })
    if not out:
        full = (data.get("text") or "").strip()
        if full:
            out.append({"start": 0.0, "end": 0.0, "text": full})
    return out


def transcribe(video_path: Path) -> tuple[list[dict], str] | tuple[None, None]:
    """Transcribe via API. Returns (segments, backend) or (None, None) if no key."""
    backend, api_key = load_api_key()
    if not backend:
        return None, None

    audio_out = video_path.with_suffix(".api_audio.mp3")
    try:
        logger.info(f"  Extracting audio for Whisper API ({backend})…")
        audio_path = extract_audio(video_path, audio_out)
        size_kb = audio_path.stat().st_size / 1024
        logger.info(f"  Audio: {size_kb:.0f} kB — uploading to {backend}…")

        endpoint = _GROQ_ENDPOINT if backend == "groq" else _OPENAI_ENDPOINT
        model = _GROQ_MODEL if backend == "groq" else _OPENAI_MODEL

        response = _post_whisper(endpoint, api_key, model, audio_path)
        segments = _segments_from_response(response)

        if not segments:
            raise RuntimeError("Whisper API returned no segments")

        logger.info(f"  Transcribed {len(segments)} segments via {backend}")
        return segments, backend
    except Exception as e:
        logger.warning(f"  Whisper API failed ({backend}): {e}")
        return None, None
    finally:
        if audio_out.exists():
            audio_out.unlink()
