import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import config

logger = logging.getLogger(__name__)

_model = None


def load_model():
    global _model
    if _model is not None:
        return _model

    import whisper

    logger.info(f"Loading Whisper model '{config.WHISPER_MODEL}' on '{config.WHISPER_DEVICE}'...")
    _model = whisper.load_model(config.WHISPER_MODEL, device=config.WHISPER_DEVICE)
    logger.info("Model loaded.")
    return _model


def transcribe_audio(audio_path, video_meta):
    model = load_model()

    decode_options = {}
    if config.WHISPER_LANGUAGE:
        decode_options["language"] = config.WHISPER_LANGUAGE

    logger.info(f"  Transcribing: {audio_path.name}")
    result = model.transcribe(
        str(audio_path),
        **decode_options,
        verbose=False,
    )

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
