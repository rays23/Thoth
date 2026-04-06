import logging
import subprocess
from pathlib import Path

import config

logger = logging.getLogger(__name__)


def ensure_audio_dir():
    config.TEMP_AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def audio_path_for(video_id):
    return config.TEMP_AUDIO_DIR / f"{video_id}.m4a"


def is_downloaded(video_id):
    path = audio_path_for(video_id)
    return path.exists() and path.stat().st_size > 0


def download_audio(video_id, url=None):
    ensure_audio_dir()

    if is_downloaded(video_id):
        logger.info(f"  Audio already cached: {video_id}")
        return audio_path_for(video_id)

    if url is None:
        url = f"https://www.youtube.com/watch?v={video_id}"

    output_path = audio_path_for(video_id)
    output_template = str(config.TEMP_AUDIO_DIR / f"{video_id}.%(ext)s")

    cmd = [
        "yt-dlp",
        "--extract-audio",
        "--audio-format", "m4a",
        "--audio-quality", "0",
        "--no-playlist",
        "--no-warnings",
        "--output", output_template,
        url,
    ]

    logger.info(f"  Downloading audio: {video_id}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            logger.error(f"  yt-dlp failed for {video_id}: {result.stderr[:300]}")
            return None

        if output_path.exists():
            logger.info(f"  Downloaded: {output_path.name} ({output_path.stat().st_size // 1024}KB)")
            return output_path

        # yt-dlp may have used a different extension, find the actual file
        candidates = list(config.TEMP_AUDIO_DIR.glob(f"{video_id}.*"))
        if candidates:
            actual = candidates[0]
            logger.info(f"  Downloaded: {actual.name} ({actual.stat().st_size // 1024}KB)")
            return actual

        logger.error(f"  Download completed but file not found for {video_id}")
        return None

    except subprocess.TimeoutExpired:
        logger.error(f"  Download timeout for {video_id}")
        return None
    except FileNotFoundError:
        logger.error("  yt-dlp not found. Install: pip install yt-dlp")
        return None


def cleanup_audio(video_id):
    for f in config.TEMP_AUDIO_DIR.glob(f"{video_id}.*"):
        f.unlink()
        logger.debug(f"  Cleaned up: {f.name}")
