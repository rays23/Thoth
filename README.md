# Thoth

> Named after the Egyptian god of writing and knowledge.

**Automated YouTube channel transcription pipeline** — extracts videos from YouTube channels, downloads audio, and transcribes them locally using OpenAI Whisper.

## What it does

1. **Extract** — Fetches video URLs from YouTube channels via the YouTube Data API
2. **Download** — Downloads audio tracks using yt-dlp
3. **Transcribe** — Runs local speech-to-text using OpenAI Whisper
4. **Store** — Saves transcripts as TXT and structured JSON files

## Features

- Fully automated end-to-end pipeline
- Local transcription — no cloud API needed, your data stays on your machine
- Configurable Whisper model (tiny → large-v3)
- Output as plain text and structured JSON with timestamps
- Incremental processing — skips already-transcribed videos
- Interactive channel selection with saved presets
- Dry-run mode for previewing

## Requirements

- Python 3.11+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [openai-whisper](https://github.com/openai/whisper)
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
# Transcribe videos from a channel (interactive selection)
python thoth.py transcribe

# Transcribe by channel ID
python thoth.py transcribe --channel <CHANNEL_ID> --name "Channel Name"

# Limit to latest N videos
python thoth.py transcribe --channel <CHANNEL_ID> --limit 10

# Dry run (preview without downloading/transcribing)
python thoth.py transcribe --channel <CHANNEL_ID> --dry-run

# Override Whisper model
python thoth.py transcribe --channel <CHANNEL_ID> --model small

# List saved channels
python thoth.py channels

# Show processing statistics
python thoth.py status
```

## Output

Transcripts are saved to the `output/` directory:

```
output/
  Channel_Name/
    Video_Title_abc123.txt       # Plain text transcript
    Video_Title_abc123.json      # Structured JSON with metadata
```

### JSON format

```json
{
  "video_id": "abc123",
  "title": "Video Title",
  "channel": "Channel Name",
  "published_at": "2026-01-15T00:00:00Z",
  "url": "https://www.youtube.com/watch?v=abc123",
  "language": "en",
  "model": "large-v3",
  "transcribed_at": "2026-04-06T14:30:00Z",
  "segments": [
    {"start": 0.0, "end": 4.5, "text": "Hello and welcome..."}
  ],
  "text": "Full transcript text..."
}
```

## Configuration

See `.env.example` for all options:

| Variable | Default | Description |
|----------|---------|-------------|
| `YOUTUBE_API_KEY` | (required) | YouTube Data API v3 key |
| `WHISPER_MODEL` | `large-v3` | Whisper model size |
| `WHISPER_LANGUAGE` | (auto) | Force language detection |
| `WHISPER_DEVICE` | `cpu` | `cpu`, `cuda`, or `mps` |
| `OUTPUT_DIR` | `output` | Transcript output directory |
| `KEEP_AUDIO` | `false` | Keep downloaded audio files |

## License

MIT
