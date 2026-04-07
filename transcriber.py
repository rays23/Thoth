import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import config

logger = logging.getLogger(__name__)

_models = {}


def _get_transcribe_fn(model_repo):
    if model_repo in _models:
        return _models[model_repo]

    if config.WHISPER_BACKEND == "mlx":
        import mlx_whisper

        logger.info(f"Loading MLX model: {model_repo}")
        fn = lambda path, **kw: mlx_whisper.transcribe(
            str(path),
            path_or_hf_repo=model_repo,
            **kw,
        )
    else:
        import whisper

        logger.info(f"Loading OpenAI Whisper model: {model_repo}")
        model = whisper.load_model(model_repo)
        fn = lambda path, **kw: model.transcribe(str(path), **kw)

    _models[model_repo] = fn
    logger.info(f"Model ready: {model_repo}")
    return fn


def _detect_language(audio_path):
    """Quick language detection using the multilingual turbo model."""
    import mlx_whisper

    logger.info(f"  Detecting language: {audio_path.name}")
    result = mlx_whisper.transcribe(
        str(audio_path),
        path_or_hf_repo=config.WHISPER_MODEL_MULTI,
        word_timestamps=False,
        verbose=False,
        clip_timestamps=[0],
        no_speech_threshold=0.6,
    )
    lang = result.get("language", "en")
    logger.info(f"  Detected language: {lang}")
    return lang


def transcribe_audio(audio_path, video_meta):
    if config.WHISPER_LANGUAGE:
        lang = config.WHISPER_LANGUAGE
    else:
        lang = _detect_language(audio_path)

    # English → distil (fast), everything else → turbo (multilingual)
    if lang == "en":
        model_repo = config.WHISPER_MODEL_EN
    else:
        model_repo = config.WHISPER_MODEL_MULTI

    logger.info(f"  Using model: {model_repo} (lang={lang})")
    transcribe_fn = _get_transcribe_fn(model_repo)

    decode_options = {"verbose": False, "language": lang}

    logger.info(f"  Transcribing: {audio_path.name}")
    result = transcribe_fn(audio_path, **decode_options)

    transcript_text = result.get("text", "").strip()
    detected_language = result.get("language", lang)
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
        "model": model_repo,
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
    safe = "".join(c if c.isalnum() or c in " -_" else "" for c in title)
    safe = safe.strip()[:max_len].rstrip("_. ")
    if not safe:
        safe = video_id
    return f"{safe}_{video_id}"


def _safe_dirname(name):
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in name)
    return safe.strip() or "unknown_channel"
