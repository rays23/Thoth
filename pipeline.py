import logging

import config
import downloader
import state
import transcriber

logger = logging.getLogger(__name__)


def process_videos(videos, channel_name, dry_run=False):
    total = len(videos)
    skipped = 0
    processed = 0
    failed = 0

    for i, video in enumerate(videos, 1):
        video_id = video["video_id"]
        title = video["title"]
        prefix = f"[{i}/{total}]"

        if state.is_processed(video_id):
            logger.info(f"{prefix} Skipping (already processed): {title}")
            skipped += 1
            continue

        if dry_run:
            logger.info(f"{prefix} [DRY RUN] Would process: {title}")
            continue

        logger.info(f"{prefix} Processing: {title}")

        # Download
        audio_path = downloader.download_audio(video_id, video["url"])
        if audio_path is None:
            logger.error(f"{prefix} Download failed, skipping: {title}")
            failed += 1
            continue

        # Transcribe
        try:
            video_meta = {**video, "channel_name": channel_name}
            transcript = transcriber.transcribe_audio(audio_path, video_meta)
        except Exception as e:
            logger.error(f"{prefix} Transcription failed: {e}")
            failed += 1
            continue

        # Save
        try:
            transcriber.save_transcript(transcript, channel_name)
        except Exception as e:
            logger.error(f"{prefix} Save failed: {e}")
            failed += 1
            continue

        # Mark processed
        state.mark_processed(video_id, title, channel_name)
        processed += 1

        # Cleanup audio if configured
        if not config.KEEP_AUDIO:
            downloader.cleanup_audio(video_id)

    return {
        "total": total,
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
    }
