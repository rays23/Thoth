import json
import logging

from googleapiclient.discovery import build

import config

logger = logging.getLogger(__name__)


def load_channels():
    if not config.CHANNELS_FILE.exists():
        return []
    with open(config.CHANNELS_FILE, "r") as f:
        return json.load(f)


def save_channels(channels):
    with open(config.CHANNELS_FILE, "w") as f:
        json.dump(channels, f, indent=2, ensure_ascii=False)


def add_channel(channel_id, name):
    channels = load_channels()
    if any(c["id"] == channel_id for c in channels):
        logger.info(f"Channel '{name}' already saved.")
        return channels
    channels.append({"id": channel_id, "name": name})
    save_channels(channels)
    logger.info(f"Channel '{name}' saved.")
    return channels


def remove_channel(channel_id):
    channels = load_channels()
    channels = [c for c in channels if c["id"] != channel_id]
    save_channels(channels)
    return channels


def lookup_channel(youtube, query):
    request = youtube.search().list(
        part="snippet",
        q=query,
        type="channel",
        maxResults=5,
    )
    response = request.execute()
    results = []
    for item in response.get("items", []):
        results.append({
            "id": item["snippet"]["channelId"],
            "name": item["snippet"]["title"],
            "description": item["snippet"]["description"][:120],
        })
    return results


def select_channel_interactive(youtube):
    channels = load_channels()

    if channels:
        print("\n=== Gespeicherte Channels ===")
        for i, ch in enumerate(channels, 1):
            print(f"  [{i}] {ch['name']} ({ch['id']})")
        print(f"  [n] Neuen Channel suchen")
        print()

        choice = input("Auswahl: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(channels):
            selected = channels[int(choice) - 1]
            return selected["id"], selected["name"]

    query = input("Channel-Name oder Handle eingeben: ").strip()
    if not query:
        return None, None

    results = lookup_channel(youtube, query)
    if not results:
        print("Keine Channels gefunden.")
        return None, None

    print("\n=== Suchergebnisse ===")
    for i, r in enumerate(results, 1):
        print(f"  [{i}] {r['name']}")
        print(f"      {r['description']}")
    print()

    choice = input("Channel auswählen (Nummer): ").strip()
    if not choice.isdigit() or not (1 <= int(choice) <= len(results)):
        return None, None

    selected = results[int(choice) - 1]
    save_choice = input(f"'{selected['name']}' speichern? [j/n]: ").strip().lower()
    if save_choice in ("j", "y", "ja", "yes"):
        add_channel(selected["id"], selected["name"])

    return selected["id"], selected["name"]


def build_youtube_client():
    return build("youtube", "v3", developerKey=config.YOUTUBE_API_KEY)
