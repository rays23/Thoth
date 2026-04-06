import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import config

logger = logging.getLogger(__name__)

_model = None
_transcribe_fn = None


def load_model():
    global _model, _transcribe_fn

    if _transcribe_fn is not None:
        return

    if config.WHISPER_BACKEND == "mlx":
        import mlx_whisper

        logger.info(f"Using MLX backend with model '{config.WHISPER_MODEL}' (Apple Silicon GPU)")
        _transcribe_fn = lambda path, **kw: mlx_whisper.transcribe(
            str(path),
            path_or_hf_repo=config.WHISPER_MODEL,
            **kw,
        )
    else:
        import whisper

        logger.info(f"Loading OpenAI Whisper model '{config.WHISPER_MODEL}'...")
        _model = whisper.load_model(config.WHISPER_MODEL)
        _transcribe_fn = lambda path, **kw: _model.transcribe(str(path), **kw)

    logger.info("Model ready.")


def transcribe_audio(audio_path, video_meta):
    load_model()

    decode_options = {"verbose": False}
    if config.WHISPER_LANGUAGE:
        decode_options["language"] = config.WHISPER_LANGUAGE

    logger.info(f"  Transcribing: {audio_path.name}")
    result = _transcribe_fn(audio_path, **decode_options)

    transcript_text = result.get("text", "").strip()
    detected_language = result.get("language", "unknown")
    segments = [
        {
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text"].strip(),
        }
        for seg in result.get("segments", [])
    ]

    logger.info(f"  Transcribed: {len(segments)} segments, language={detected_language}")

    return {
        "video_id": video_meta["video_id"],
        "title": video_meta["title"],
        "channel": video_meta.get("channel_name", ""),
        "published_at": video_meta.get("published_at", ""),
        "url": video_meta["url"],
        "language": detected_language,
        "model": config.WHISPER_MODEL,
        "transcribed_at": datetime.now(timezone.utc).isoformat(),
        "segments": segments,
        "text": transcript_text,
    }


def save_transcript(transcript_data, channel_name):
    channel_dir = config.OUTPUT_DIR / _safe_dirname(channel_name)
    channel_dir.mkdir(parents=True, exist_ok=True)

    base_name = _safe_filename(transcript_data["title"], transcript_data["video_id"])

    # TXT
    txt_path = channel_dir / f"{base_name}.txt"
    txt_path.write_text(transcript_data["text"], encoding="utf-8")

    # JSON
    json_path = channel_dir / f"{base_name}.json"
    json_path.write_text(
        json.dumps(transcript_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info(f"  Saved: {txt_path.name} + {json_path.name}")
    return txt_path, json_path


def _safe_filename(title, video_id, max_len=80):
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
    safe = safe.strip()[:max_len].rstrip("_. ")
    if not safe:
        safe = video_id
    return f"{safe}_{video_id}"


def _safe_dirname(name):
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in name)
    return safe.strip() or "unknown_channel"
