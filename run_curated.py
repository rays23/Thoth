#!/usr/bin/env python3
"""Transcribe curated Michael van de Poppe strategy/TA videos."""

import sys
import logging

sys.path.insert(0, ".")
import config
import pipeline
import downloader
import state
import transcriber

from googleapiclient.discovery import build

VIDEO_IDS = [
    "x6fzzdxOG8w",  # Crucial Tips If You Want To Start Trading ALTCOINS
    "EbiwCB4N1Lg",  # Crucial Beginners Mistakes To Avoid Trading Crypto
    "QKVaTEFM-tI",  # Crucial Tips To Avoid Huge Losses
    "qBVJEmMx490",  # Beginners Tips For Trading Crypto: Rookie Mistakes
    "4__pRepvbYQ",  # HOW TO TRADE BITCOIN: A GUIDE TO MAXIMUM GAINS
    "3UyVaS-kwsg",  # How To Trade Altcoins When Prices Go Crazy
    "MioAH4YSHsY",  # The Best Altcoin Trading Strategy This Bull Cycle
    "gjJrdrMwn4s",  # Crypto 101 Course: From Basics To Mastery
    "4DN2NpBp-7U",  # The Ultimate Strategy To Trade Altcoins in A Bull Cycle
    "3Blq4-ZVViM",  # Bitcoin Bear Market: 6 Lessons To Survive
    "AOJy4MSVq-8",  # Top Basic Indicators to Use While Trading
    "JBaK1XoGBTc",  # Top 3 Beginners Tips When You Start in Crypto
    "5VE3NsDoD8o",  # Why Most Crypto Day Traders Get It Wrong
    "gj6K5c2Dc-E",  # My Winning Crypto Day Trading Strategy Revealed
    "4U89QuGfNMk",  # My BIGGEST Trading Lesson From Near Bankruptcy
]

CHANNEL_NAME = "Michael van de Poppe"


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    config.validate()

    youtube = build("youtube", "v3", developerKey=config.YOUTUBE_API_KEY)
    resp = youtube.videos().list(part="snippet", id=",".join(VIDEO_IDS)).execute()

    videos = []
    for item in resp.get("items", []):
        videos.append({
            "video_id": item["id"],
            "title": item["snippet"]["title"],
            "published_at": item["snippet"]["publishedAt"],
            "description": item["snippet"].get("description", "")[:500],
            "url": f"https://www.youtube.com/watch?v={item['id']}",
        })

    id_order = {vid: i for i, vid in enumerate(VIDEO_IDS)}
    videos.sort(key=lambda v: id_order.get(v["video_id"], 999))

    print(f"\n=== Thoth: {len(videos)} curated videos ===")
    print(f"  Channel: {CHANNEL_NAME}")
    print(f"  Model EN:    {config.WHISPER_MODEL_EN}")
    print(f"  Model Multi: {config.WHISPER_MODEL_MULTI}\n")

    result = pipeline.process_videos(videos, CHANNEL_NAME)

    print(f"\n=== Ergebnis ===")
    print(f"  Transkribiert: {result['processed']}")
    print(f"  Übersprungen:  {result['skipped']}")
    print(f"  Fehler:        {result['failed']}")


if __name__ == "__main__":
    main()
