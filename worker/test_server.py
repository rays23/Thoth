"""Tests für die reinen Funktionen des Thoth-Workers."""
import http.client
import json
import os
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

os.environ["WORKER_TOKEN"] = "test-token"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import server  # noqa: E402


def test_parse_video_id_accepts_urls_and_plain_ids():
    assert server.parse_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=5s") == "dQw4w9WgXcQ"
    assert server.parse_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert server.parse_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert server.parse_video_id("https://example.com/nichts") is None


def test_format_timestamp_pads_hours_minutes_seconds():
    assert server.format_timestamp(0) == "00:00:00"
    assert server.format_timestamp(3725.9) == "01:02:05"


def test_pick_caption_language_prefers_manual_then_declared_original():
    assert server.pick_caption_language({"language": "de", "subtitles": {"de": [{}], "en": [{}]}}) == "de"
    assert server.pick_caption_language({"language": "fr", "automatic_captions": {"fr": [{}], "en": [{}]}}) == "fr"
    assert server.pick_caption_language({}) is None


def test_pick_caption_language_ignores_unrelated_orig_tracks():
    auto = {"ar-orig": [{}], "bn-orig": [{}], "en-orig": [{}], "de-DE-orig": [{}], "en": [{}]}
    assert server.pick_caption_language({"language": "en-US", "automatic_captions": auto}) == "en-orig"
    assert server.pick_caption_language({"language": "de-DE", "automatic_captions": auto}) == "de-DE-orig"
    assert server.pick_caption_language({"automatic_captions": auto}, hint="en") == "en-orig"
    assert server.pick_caption_language({"automatic_captions": auto}) is None
    assert server.pick_caption_language({"language": "ja", "automatic_captions": auto}) is None


def test_markdown_roundtrip_gives_plain_text_without_stamps():
    meta = {"id": "dQw4w9WgXcQ", "title": "Test: Ein Titel", "channel": "Kanal", "upload_date": "20260102", "duration": 130}
    segments = [
        {"start": 0.0, "end": 5.0, "text": "Erster Satz."},
        {"start": 30.0, "end": 35.0, "text": "Zweiter Satz."},
        {"start": 75.0, "end": 80.0, "text": "Dritter Satz."},
    ]
    markdown = server.build_markdown(meta, segments, "captions:de", "de", "2026-01-03T10:00:00Z")
    assert 'published: "2026-01-02"' in markdown
    assert "**[00:01:15]** Dritter Satz." in markdown
    assert server.plain_text(markdown) == "Erster Satz. Zweiter Satz.\n\nDritter Satz."


def test_trim_overlaps_removes_repeated_phrase_between_cues():
    segments = [
        {"start": 0.0, "end": 2.0, "text": "eins zwei drei vier"},
        {"start": 2.0, "end": 4.0, "text": "zwei drei vier fünf sechs"},
        {"start": 4.0, "end": 5.0, "text": "fünf sechs"},
    ]
    trimmed = server.trim_overlaps(segments)
    assert [s["text"] for s in trimmed] == ["eins zwei drei vier", "fünf sechs"]
    assert trimmed[-1]["end"] == 5.0


def test_trim_overlaps_keeps_short_coincidences():
    segments = [
        {"start": 0.0, "end": 1.0, "text": "das ist gut"},
        {"start": 1.0, "end": 2.0, "text": "gut gemacht heute"},
    ]
    assert [s["text"] for s in server.trim_overlaps(segments)] == ["das ist gut", "gut gemacht heute"]


def test_frontmatter_value_reads_json_encoded_strings():
    meta = {"id": "dQw4w9WgXcQ", "title": 'Mit "Anführungszeichen"', "channel": "Kanal", "upload_date": "20260102", "duration": 10}
    markdown = server.build_markdown(meta, [{"start": 0.0, "end": 1.0, "text": "Text."}], "captions:de", "de", "")
    assert server.frontmatter_value(markdown, "title") == 'Mit "Anführungszeichen"'
    assert server.frontmatter_value(markdown, "source") == "captions:de"
    assert server.frontmatter_value(markdown, "fehlt") == ""


@pytest.fixture()
def live_server(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "ARCHIVE_DIR", tmp_path)
    monkeypatch.setattr(server, "PAUSE_BETWEEN_JOBS", 0)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[1], tmp_path
    httpd.shutdown()
    thread.join(timeout=5)


def _bearer() -> str:
    return "Bearer " + server.TOKEN


def _post(port, body, auth, raw_length=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    connection.putrequest("POST", "/transcribe")
    connection.putheader("Content-Type", "application/json")
    if auth is not None:
        connection.putheader("Authorization", auth)
    payload = body.encode("utf-8")
    connection.putheader("Content-Length", raw_length if raw_length is not None else str(len(payload)))
    connection.endheaders(payload)
    response = connection.getresponse()
    return response.status, json.loads(response.read() or b"{}")


def test_http_rejects_missing_wrong_and_non_ascii_credentials(live_server):
    port, _ = live_server
    assert _post(port, "{}", None)[0] == 401
    assert _post(port, "{}", "Bearer " + "x" * 12)[0] == 401
    assert _post(port, "{}", "Bearer é")[0] == 401


def test_http_validates_body_and_paths(live_server):
    port, _ = live_server
    assert _post(port, "{}", _bearer(), raw_length="abc")[0] == 400
    assert _post(port, "kein json", _bearer())[0] == 400
    assert _post(port, "{}", _bearer())[0] == 400
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    connection.request("GET", "/unbekannt")
    assert connection.getresponse().status == 404


def test_http_returns_cached_transcript_without_calling_youtube(live_server, monkeypatch):
    port, archive = live_server
    meta = {"id": "dQw4w9WgXcQ", "title": "Titel", "channel": "Kanal", "upload_date": "20260102", "duration": 10}
    target = archive / "transkripte" / "2026" / "dQw4w9WgXcQ-Titel.md"
    target.parent.mkdir(parents=True)
    target.write_text(server.build_markdown(meta, [{"start": 0.0, "end": 1.0, "text": "Gespeichert."}], "captions:en-orig", "en", ""), encoding="utf-8")
    monkeypatch.setattr(server, "fetch_meta", lambda _id: pytest.fail("darf nicht aufgerufen werden"))
    status, body = _post(live_server[0], json.dumps({"video_id": "dQw4w9WgXcQ"}), _bearer())
    assert status == 200 and body["status"] == "cached"
    assert body["source"] == "captions:en-orig" and body["text"] == "Gespeichert."


def test_process_uses_safe_year_folder_for_invalid_upload_date(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "ARCHIVE_DIR", tmp_path)
    monkeypatch.setattr(server, "PAUSE_BETWEEN_JOBS", 0)
    meta = {"id": "dQw4w9WgXcQ", "title": "Titel", "upload_date": "../ab", "duration": 10, "language": "en",
            "automatic_captions": {"en-orig": [{}]}}
    monkeypatch.setattr(server, "fetch_meta", lambda _id: meta)

    def fake_captions(video_id, language, workdir):
        vtt = workdir / f"{video_id}.{language}.vtt"
        vtt.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nHallo Welt\n", encoding="utf-8")
        return vtt

    monkeypatch.setattr(server, "download_captions", fake_captions)
    result = server.process({"video_id": "dQw4w9WgXcQ"})
    assert Path(result["path"]).parent == tmp_path / "transkripte" / "0000"
    assert result["text"] == "Hallo Welt"


def test_run_maps_timeouts_to_worker_error(monkeypatch):
    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="yt-dlp", timeout=1)

    monkeypatch.setattr(server.subprocess, "run", raise_timeout)
    with pytest.raises(server.WorkerError) as error:
        server._run(["yt-dlp", "--version"], 1)
    assert error.value.stage == "timeout"


def test_split_audio_keeps_short_files_whole(tmp_path):
    audio = tmp_path / "a.mp3"
    assert server.split_audio(audio, 600, tmp_path) == [(audio, 0.0)]


def test_slugify_limits_length_and_strips_symbols():
    assert server.slugify("Hallo, Welt! Ärger?") == "Hallo-Welt-Ärger"
    assert len(server.slugify("x" * 200)) == 60
    assert server.slugify("???") == "video"
