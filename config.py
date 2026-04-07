import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Required ---
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

# --- Whisper ---
WHISPER_MODEL_EN = os.getenv("WHISPER_MODEL_EN", "mlx-community/distil-whisper-large-v3")
WHISPER_MODEL_MULTI = os.getenv("WHISPER_MODEL_MULTI", "mlx-community/whisper-large-v3-turbo")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "")  # empty = auto-detect
WHISPER_BACKEND = os.getenv("WHISPER_BACKEND", "mlx")  # "mlx" or "openai"

# --- Output ---
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "output"))
KEEP_AUDIO = os.getenv("KEEP_AUDIO", "false").lower() in ("true", "1", "yes")

# --- Processing ---
YOUTUBE_BATCH_SIZE = int(os.getenv("YOUTUBE_BATCH_SIZE", "50"))
RATE_LIMIT_DELAY = float(os.getenv("RATE_LIMIT_DELAY", "0.5"))

# --- Paths ---
BASE_DIR = Path(__file__).parent
CHANNELS_FILE = BASE_DIR / "channels.json"
STATE_FILE = BASE_DIR / "processed_videos.json"
LOGS_DIR = BASE_DIR / "logs"
TEMP_AUDIO_DIR = BASE_DIR / ".audio_cache"

REQUIRED_VARS = {
    "YOUTUBE_API_KEY": YOUTUBE_API_KEY,
}


def validate():
    missing = [name for name, val in REQUIRED_VARS.items() if not val]
    if missing:
        print(f"ERROR: Missing required environment variables: {', '.join(missing)}")
        print("Copy .env.example to .env and fill in the values.")
        sys.exit(1)


def summary():
    print("=== Thoth Configuration ===")
    print(f"  YouTube API Key:  {'***' + YOUTUBE_API_KEY[-4:] if len(YOUTUBE_API_KEY) > 4 else '(not set)'}")
    print(f"  Whisper EN:       {WHISPER_MODEL_EN}")
    print(f"  Whisper Multi:    {WHISPER_MODEL_MULTI}")
    print(f"  Whisper Language: {WHISPER_LANGUAGE or '(auto-detect)'}")
    print(f"  Whisper Backend:  {WHISPER_BACKEND}")
    print(f"  Output Dir:       {OUTPUT_DIR}")
    print(f"  Keep Audio:       {KEEP_AUDIO}")
    print(f"  Batch Size:       {YOUTUBE_BATCH_SIZE}")
    print(f"  Rate Limit Delay: {RATE_LIMIT_DELAY}s")


if __name__ == "__main__":
    validate()
    summary()
