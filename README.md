# Thoth

> Named after the Egyptian god of writing and knowledge.

**Automated YouTube channel transcription pipeline** — extracts videos from YouTube channels, downloads audio, and transcribes them locally using Whisper models.

## What it does

1. **Extract** — Fetches video URLs from YouTube channels via the YouTube Data API
2. **Download** — Downloads audio tracks using yt-dlp
3. **Transcribe** — Runs local speech-to-text using whisper.cpp / OpenAI Whisper
4. **Store** — Saves transcripts as TXT and JSON files

## Features

- Fully automated end-to-end pipeline
- Local transcription (no cloud API needed)
- Configurable Whisper model size
- Output as TXT and structured JSON
- Incremental processing (skip already-transcribed videos)
- Channel management with saved presets

## Requirements

- Python 3.11+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [whisper.cpp](https://github.com/ggerganov/whisper.cpp) or [openai-whisper](https://github.com/openai/whisper)
- YouTube Data API v3 key

## Setup

```bash
# Clone
git clone https://github.com/rays23/Thoth.git
cd Thoth

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your YouTube API key and preferences
```

## Usage

```bash
# Transcribe all videos from a channel
python thoth.py --channel <CHANNEL_ID>

# Limit to latest N videos
python thoth.py --channel <CHANNEL_ID> --limit 10

# Dry run (show what would be processed)
python thoth.py --channel <CHANNEL_ID> --dry-run
```

## Output

Transcripts are saved to the `output/` directory:

```
output/
  channel-name/
    video-title.txt          # Plain text transcript
    video-title.json         # Structured JSON with metadata
```

## License

MIT
