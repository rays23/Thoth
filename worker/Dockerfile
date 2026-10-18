FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# yt-dlp braucht für YouTube eine JavaScript-Laufzeit (deno)
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

RUN pip install --no-cache-dir "yt-dlp[default]" python-dotenv

ENV HOME=/tmp \
    XDG_CACHE_HOME=/tmp/.cache \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY captions.py config.py whisper_api.py server.py /app/
RUN mkdir -p /app/.audio_cache /app/.video_cache && chown -R 99:100 /app/.audio_cache /app/.video_cache

# yt-dlp bleibt bewusst unversioniert: YouTube ändert sich ständig, ein Neubau zieht die aktuelle Fassung.
# 99:100 entspricht nobody:users auf Unraid, damit das Archiv beschreibbar bleibt
USER 99:100
EXPOSE 8765
HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=8)"
CMD ["python", "server.py"]
