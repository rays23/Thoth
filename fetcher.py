import logging
import time

import config

logger = logging.getLogger(__name__)


def get_upload_playlist_id(channel_id):
    return "UU" + channel_id[2:]


def fetch_videos(youtube, channel_id, limit=None):
    playlist_id = get_upload_playlist_id(channel_id)
    videos = []
    next_page_token = None
    batch_num = 0

    logger.info(f"Fetching videos from playlist {playlist_id}...")

    while True:
        batch_num += 1
        max_results = min(config.YOUTUBE_BATCH_SIZE, 50)

        request = youtube.playlistItems().list(
            part="snippet",
            playlistId=playlist_id,
            maxResults=max_results,
            pageToken=next_page_token,
        )
        response = request.execute()

        items = response.get("items", [])
        logger.info(f"  [Batch {batch_num}] Loaded {len(items)} videos")

        for item in items:
            snippet = item["snippet"]
            video_id = snippet.get("resourceId", {}).get("videoId")
            if not video_id:
                continue

            title = snippet.get("title", "")
            if title in ("Deleted video", "Private video"):
                logger.debug(f"  Skipping {title}: {video_id}")
                continue

            videos.append({
                "video_id": video_id,
                "title": title,
                "published_at": snippet.get("publishedAt", ""),
                "description": snippet.get("description", "")[:500],
                "url": f"https://www.youtube.com/watch?v={video_id}",
            })

            if limit and len(videos) >= limit:
                logger.info(f"Reached limit of {limit} videos.")
                return videos

        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break

        time.sleep(config.RATE_LIMIT_DELAY)

    logger.info(f"Found {len(videos)} videos total.")
    return videos
