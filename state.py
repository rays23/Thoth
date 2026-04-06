import json
import logging
from datetime import datetime, timezone

import config

logger = logging.getLogger(__name__)


def load_state():
    if not config.STATE_FILE.exists():
        return {}
    with open(config.STATE_FILE, "r") as f:
        return json.load(f)


def save_state(state):
    with open(config.STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def is_processed(video_id):
    state = load_state()
    return video_id in state


def mark_processed(video_id, title, channel_name):
    state = load_state()
    state[video_id] = {
        "title": title,
        "channel": channel_name,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }
    save_state(state)


def get_stats():
    state = load_state()
    if not state:
        return {"total": 0, "channels": {}}

    channels = {}
    for entry in state.values():
        ch = entry.get("channel", "unknown")
        channels[ch] = channels.get(ch, 0) + 1

    return {
        "total": len(state),
        "channels": channels,
    }
