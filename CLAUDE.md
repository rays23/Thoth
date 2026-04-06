# Thoth — Projekt-Konventionen

## Was ist Thoth?
Automatisierte YouTube-Channel-Transkriptions-Pipeline. Extrahiert Videos aus YouTube-Channels, lädt Audio herunter und transkribiert lokal mit Whisper.

## Tech Stack
- Python 3.11+
- openai-whisper (lokale Transkription)
- yt-dlp (Audio-Download)
- YouTube Data API v3 (Video-Metadaten)

## Architektur
- `thoth.py` — CLI Entrypoint
- `config.py` — Konfiguration aus .env
- `channels.py` — Channel-Verwaltung + interaktive Auswahl
- `fetcher.py` — YouTube API Video-Extraktion
- `downloader.py` — yt-dlp Audio-Download
- `transcriber.py` — Whisper Transkription
- `pipeline.py` — Orchestrierung fetch→download→transcribe→store
- `state.py` — Tracking verarbeiteter Videos

## Konventionen
- Immutable data: Neue Objekte statt Mutation
- Alle Config über .env / config.py — keine hardcoded Werte
- Secrets nur über Umgebungsvariablen
- Output in `output/<channel-name>/` als TXT + JSON
- State in `processed_videos.json`
