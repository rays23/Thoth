"""Thoth-Worker: transkribiert einzelne YouTube-Videos über HTTP (Aufrufer: n8n).

Reihenfolge je Video: Untertitel in der Originalsprache, sonst Whisper per API
(Groq, dann OpenAI). Ergebnis ist eine Markdown-Datei im Archiv und die JSON-Antwort.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import re
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import captions
import whisper_api

logger = logging.getLogger("thoth-worker")

ARCHIVE_DIR = Path(os.environ.get("ARCHIVE_DIR", "/archive"))
TOKEN = os.environ["WORKER_TOKEN"]
PORT = int(os.environ.get("PORT", "8765"))
CHUNK_SECONDS = int(os.environ.get("CHUNK_SECONDS", "2400"))
PAUSE_BETWEEN_JOBS = float(os.environ.get("PAUSE_BETWEEN_JOBS", "3"))
MAX_BODY_BYTES = 64 * 1024
PARAGRAPH_SECONDS = 60

_JOB_LOCK = threading.Lock()
_ID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})|^([A-Za-z0-9_-]{11})$")
_STAMP_RE = re.compile(r"\*\*\[\d{2}:\d{2}:\d{2}\]\*\* ")


class WorkerError(Exception):
    """Fehler mit Angabe der Stufe (meta, captions, audio, whisper, rate_limited)."""

    def __init__(self, stage: str, detail: str) -> None:
        super().__init__(f"{stage}: {detail}")
        self.stage = stage
        self.detail = detail


def parse_video_id(raw: str) -> str | None:
    match = _ID_RE.search(raw.strip())
    if not match:
        return None
    return match.group(1) or match.group(2)


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def slugify(title: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9ÄÖÜäöüß]+", "-", title).strip("-")
    return slug[:60] or "video"


def pick_caption_language(meta: dict, hint: str = "") -> str | None:
    """Spur der gesprochenen Sprache wählen.

    YouTube führt bei Automatikuntertiteln viele Spuren '<Sprache>-orig', in beliebiger Reihenfolge.
    Verlässlich ist nur die deklarierte Sprache des Videos. Ohne Angabe gibt es keine Wahl (Whisper erkennt selbst).
    """
    manual = meta.get("subtitles") or {}
    auto = meta.get("automatic_captions") or {}
    declared = (hint or meta.get("language") or "").strip()
    base = declared.split("-")[0]
    if not declared:
        return next(iter(manual), None)
    for candidate in (declared, base):
        if candidate in manual:
            return candidate
    for candidate in (f"{declared}-orig", f"{base}-orig", declared, base):
        if candidate in auto:
            return candidate
    return None


def _overlap_words(previous: list[str], current: list[str]) -> int:
    """Länge des längsten Wortüberlapps (Ende von previous gleich Anfang von current)."""
    for size in range(min(len(previous), len(current)), 0, -1):
        if previous[-size:] == current[:size] and (size >= 3 or size == len(current)):
            return size
    return 0


def trim_overlaps(segments: list[dict]) -> list[dict]:
    """Automatikuntertitel wiederholen die letzte Phrase im nächsten Segment; Wiederholungen entfernen."""
    out: list[dict] = []
    previous: list[str] = []
    for seg in segments:
        words = seg["text"].split()
        kept = words[_overlap_words(previous, words):]
        previous = words
        if kept:
            out.append({**seg, "text": " ".join(kept)})
        elif out:
            out[-1] = {**out[-1], "end": seg["end"]}
    return out


def build_markdown(meta: dict, segments: list[dict], source: str, language: str, liked_at: str) -> str:
    published = meta.get("upload_date") or ""
    if len(published) == 8:
        published = f"{published[:4]}-{published[4:6]}-{published[6:]}"
    front = {
        "title": meta.get("title") or "",
        "channel": meta.get("channel") or meta.get("uploader") or "",
        "url": f"https://www.youtube.com/watch?v={meta['id']}",
        "video_id": meta["id"],
        "published": published,
        "duration_s": int(meta.get("duration") or 0),
        "language": language,
        "source": source,
        "liked_at": liked_at,
        "transcribed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    lines = ["---"] + [f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in front.items()]
    lines += ["---", "", f"# {front['title']}", ""]
    paragraph_start = None
    buffer: list[str] = []
    for seg in segments:
        if paragraph_start is None:
            paragraph_start = seg["start"]
        elif seg["start"] - paragraph_start >= PARAGRAPH_SECONDS:
            lines.append(f"**[{format_timestamp(paragraph_start)}]** {' '.join(buffer)}")
            lines.append("")
            paragraph_start, buffer = seg["start"], []
        buffer.append(seg["text"])
    if buffer:
        lines.append(f"**[{format_timestamp(paragraph_start or 0)}]** {' '.join(buffer)}")
    return "\n".join(lines) + "\n"


def frontmatter_value(markdown: str, key: str) -> str:
    match = re.search(rf'^{re.escape(key)}: (.*)$', markdown, re.M)
    if not match:
        return ""
    try:
        return str(json.loads(match.group(1)))
    except json.JSONDecodeError:
        return match.group(1).strip('"')


def plain_text(markdown: str) -> str:
    body = markdown.split("\n---\n", 1)[-1]
    body = "\n".join(line for line in body.splitlines() if not line.startswith("# "))
    return _STAMP_RE.sub("", body).strip()


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise WorkerError("timeout", f"{cmd[0]} nach {timeout} s abgebrochen") from error


@lru_cache(maxsize=1)
def yt_dlp_version() -> str:
    return _run(["yt-dlp", "--version"], 20).stdout.strip()


def fetch_meta(video_id: str) -> dict:
    url = f"https://www.youtube.com/watch?v={video_id}"
    result = _run(["yt-dlp", "--dump-single-json", "--skip-download", "--no-playlist", "--no-warnings", url], 120)
    if result.returncode != 0:
        raise WorkerError("meta", result.stderr.strip()[-300:])
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise WorkerError("meta", "yt-dlp lieferte kein gültiges JSON") from error


def download_captions(video_id: str, language: str, workdir: Path) -> Path | None:
    cmd = [
        "yt-dlp", "--write-subs", "--write-auto-subs", "--sub-langs", language, "--sub-format", "vtt",
        "--skip-download", "--no-playlist", "--no-warnings",
        "--output", str(workdir / video_id), f"https://www.youtube.com/watch?v={video_id}",
    ]
    try:
        result = _run(cmd, 120)
    except WorkerError as error:
        logger.warning("Untertitel-Abruf für %s abgebrochen: %s", video_id, error)
        return None
    found = sorted(workdir.glob(f"{video_id}.*.vtt"))
    if not found and result.returncode != 0:
        logger.warning("Keine Untertitel für %s (yt-dlp: %s)", video_id, result.stderr.strip()[-200:])
    return found[0] if found else None


def download_audio(video_id: str, workdir: Path) -> Path:
    cmd = [
        "yt-dlp", "-f", "bestaudio", "-x", "--audio-format", "mp3",
        "--postprocessor-args", "ExtractAudio:-ar 16000 -ac 1 -b:a 48k",
        "--no-playlist", "--no-warnings",
        "--output", str(workdir / f"{video_id}.%(ext)s"), f"https://www.youtube.com/watch?v={video_id}",
    ]
    result = _run(cmd, 900)
    audio = workdir / f"{video_id}.mp3"
    if result.returncode != 0 or not audio.exists():
        raise WorkerError("audio", result.stderr.strip()[-300:] or "keine Audiodatei")
    return audio


def split_audio(audio: Path, duration: int, workdir: Path) -> list[tuple[Path, float]]:
    if duration <= CHUNK_SECONDS:
        return [(audio, 0.0)]
    pattern = workdir / "part_%03d.mp3"
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(audio),
        "-f", "segment", "-segment_time", str(CHUNK_SECONDS), "-c", "copy", str(pattern),
    ]
    result = _run(cmd, 300)
    if result.returncode != 0:
        raise WorkerError("audio", f"ffmpeg-Aufteilung fehlgeschlagen: {result.stderr.strip()[-200:]}")
    parts = sorted(workdir.glob("part_*.mp3"))
    return [(part, float(index * CHUNK_SECONDS)) for index, part in enumerate(parts)]


def whisper_transcribe(audio: Path, duration: int, workdir: Path) -> tuple[list[dict], str]:
    backend, key = whisper_api.load_api_key()
    if not backend:
        raise WorkerError("whisper", "kein Whisper-Schlüssel gesetzt")
    endpoint = whisper_api._GROQ_ENDPOINT if backend == "groq" else whisper_api._OPENAI_ENDPOINT
    model = whisper_api._GROQ_MODEL if backend == "groq" else whisper_api._OPENAI_MODEL
    segments: list[dict] = []
    for part, offset in split_audio(audio, duration, workdir):
        try:
            response = whisper_api._post_whisper(endpoint, key, model, part)
        except RuntimeError as error:
            stage = "rate_limited" if " 429" in str(error) else "whisper"
            raise WorkerError(stage, str(error)[:300]) from error
        for seg in whisper_api._segments_from_response(response):
            segments.append({**seg, "start": round(seg["start"] + offset, 2), "end": round(seg["end"] + offset, 2)})
    if not segments:
        raise WorkerError("whisper", "keine Segmente erhalten")
    return segments, backend


def find_existing(video_id: str) -> Path | None:
    return next(iter(sorted(ARCHIVE_DIR.glob(f"transkripte/*/{video_id}-*.md"))), None)


def process(payload: dict) -> dict:
    video_id = parse_video_id(str(payload.get("url") or payload.get("video_id") or ""))
    if not video_id:
        raise ValueError("url oder video_id fehlt oder ist ungültig")
    liked_at = str(payload.get("liked_at") or "")

    existing = find_existing(video_id)
    if existing:
        markdown = existing.read_text(encoding="utf-8")
        return {
            "status": "cached", "video_id": video_id, "title": frontmatter_value(markdown, "title"),
            "channel": frontmatter_value(markdown, "channel"), "published": frontmatter_value(markdown, "published"),
            "source": frontmatter_value(markdown, "source"), "path": str(existing), "text": plain_text(markdown),
        }

    with tempfile.TemporaryDirectory(dir="/tmp") as raw_dir:
        workdir = Path(raw_dir)
        meta = fetch_meta(video_id)
        if meta.get("is_live") or meta.get("live_status") in ("is_upcoming", "is_live"):
            raise WorkerError("meta", "Livestream oder Premiere noch nicht abgeschlossen")
        duration = int(meta.get("duration") or 0)
        language = pick_caption_language(meta, str(payload.get("language") or ""))
        segments, source = None, ""
        if language:
            vtt = download_captions(video_id, language, workdir)
            if vtt:
                segments, source = trim_overlaps(captions.parse_vtt(vtt)), f"captions:{language}"
        if not segments:
            audio = download_audio(video_id, workdir)
            segments, backend = whisper_transcribe(audio, duration, workdir)
            source = f"whisper:{backend}"
        spoken = language or str(payload.get("language") or "") or meta.get("language") or ""
        markdown = build_markdown(meta, segments, source, spoken, liked_at)

    year = str(meta.get("upload_date") or "")[:4]
    if not (year.isascii() and year.isdigit() and len(year) == 4):
        year = "0000"
    target = ARCHIVE_DIR / "transkripte" / year / f"{video_id}-{slugify(meta.get('title') or '')}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_target = target.with_suffix(".md.tmp")
    temp_target.write_text(markdown, encoding="utf-8")
    temp_target.replace(target)
    time.sleep(PAUSE_BETWEEN_JOBS)
    return {
        "status": "ok", "video_id": video_id, "title": meta.get("title") or "",
        "channel": meta.get("channel") or "", "published": meta.get("upload_date") or "",
        "duration_s": duration, "source": source, "path": str(target), "text": plain_text(markdown),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "ThothWorker/1.0"
    timeout = 60  # Sekunden für das Lesen der Anfrage, damit hängende Clients keinen Thread belegen

    def log_message(self, fmt: str, *args) -> None:
        logger.info("%s %s", self.address_string(), fmt % args)

    def _send(self, code: int, body: dict) -> None:
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        return hmac.compare_digest(header.encode("utf-8", "replace"), f"Bearer {TOKEN}".encode("utf-8"))

    def do_GET(self) -> None:
        if self.path != "/health":
            self._send(404, {"error": "nicht gefunden"})
            return
        self._send(200, {"status": "ok", "yt_dlp": yt_dlp_version(), "whisper_key": whisper_api.load_api_key()[0] or "keiner"})

    def do_POST(self) -> None:
        if self.path != "/transcribe":
            self._send(404, {"error": "nicht gefunden"})
            return
        if not self._authorized():
            self._send(401, {"error": "nicht autorisiert"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY_BYTES:
            self._send(400, {"error": "ungültige Körpergröße"})
            return
        try:
            payload = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            self._send(400, {"error": "kein gültiges JSON"})
            return
        try:
            with _JOB_LOCK:
                self._send(200, process(payload))
        except ValueError as error:
            self._send(400, {"error": str(error)})
        except WorkerError as error:
            code = 429 if error.stage == "rate_limited" else 502
            logger.warning("Job fehlgeschlagen: %s", error)
            self._send(code, {"error": error.detail, "stage": error.stage})
        except Exception:
            logger.exception("Unerwarteter Fehler")
            self._send(500, {"error": "interner Fehler", "stage": "unknown"})


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    logger.info("Thoth-Worker lauscht auf Port %d, Archiv %s", PORT, ARCHIVE_DIR)
    server.serve_forever()


if __name__ == "__main__":
    main()
