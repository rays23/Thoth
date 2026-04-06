#!/usr/bin/env python3
"""Thoth — Automated YouTube channel transcription pipeline."""

import argparse
import logging
import sys

import config
import channels
import fetcher
import pipeline
import state


def setup_logging(verbose=False):
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)

    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Console
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(formatter)

    # File
    from datetime import datetime
    log_file = config.LOGS_DIR / f"thoth_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(console)
    root.addHandler(file_handler)


def cmd_transcribe(args):
    config.validate()
    youtube = channels.build_youtube_client()

    channel_id = args.channel
    channel_name = args.name

    if not channel_id:
        channel_id, channel_name = channels.select_channel_interactive(youtube)
        if not channel_id:
            print("Kein Channel ausgewählt. Abbruch.")
            sys.exit(1)

    if not channel_name:
        channel_name = channel_id

    print(f"\n=== Thoth Transcription Pipeline ===")
    print(f"  Channel:  {channel_name} ({channel_id})")
    print(f"  Model:    {config.WHISPER_MODEL}")
    print(f"  Limit:    {args.limit or 'all'}")
    print(f"  Dry Run:  {args.dry_run}")
    print()

    # Fetch videos
    videos = fetcher.fetch_videos(youtube, channel_id, limit=args.limit)
    if not videos:
        print("Keine Videos gefunden.")
        return

    # Run pipeline
    result = pipeline.process_videos(videos, channel_name, dry_run=args.dry_run)

    # Summary
    print(f"\n=== Ergebnis ===")
    print(f"  Videos gesamt:     {result['total']}")
    print(f"  Transkribiert:     {result['processed']}")
    print(f"  Übersprungen:      {result['skipped']}")
    print(f"  Fehlgeschlagen:    {result['failed']}")
    if not args.dry_run and result["processed"] > 0:
        print(f"  Output:            {config.OUTPUT_DIR}/")


def cmd_channels(args):
    saved = channels.load_channels()
    if not saved:
        print("Keine gespeicherten Channels.")
        return
    print("\n=== Gespeicherte Channels ===")
    for ch in saved:
        print(f"  {ch['name']} — {ch['id']}")


def cmd_status(args):
    stats = state.get_stats()
    if stats["total"] == 0:
        print("Noch keine Videos verarbeitet.")
        return
    print(f"\n=== Thoth Status ===")
    print(f"  Videos gesamt: {stats['total']}")
    print(f"  Channels:")
    for name, count in sorted(stats["channels"].items(), key=lambda x: -x[1]):
        print(f"    {name}: {count}")


def main():
    parser = argparse.ArgumentParser(
        prog="thoth",
        description="Thoth — Automated YouTube channel transcription pipeline",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    subparsers = parser.add_subparsers(dest="command")

    # transcribe
    p_transcribe = subparsers.add_parser("transcribe", help="Transcribe videos from a channel")
    p_transcribe.add_argument("-c", "--channel", help="YouTube Channel ID")
    p_transcribe.add_argument("-n", "--name", help="Channel name (for output directory)")
    p_transcribe.add_argument("-l", "--limit", type=int, help="Max number of videos to process")
    p_transcribe.add_argument("--dry-run", action="store_true", help="Preview without downloading/transcribing")
    p_transcribe.add_argument("--model", help="Override Whisper model")

    # channels
    subparsers.add_parser("channels", help="List saved channels")

    # status
    subparsers.add_parser("status", help="Show processing statistics")

    args = parser.parse_args()
    setup_logging(verbose=args.verbose)

    if args.command == "transcribe":
        if hasattr(args, "model") and args.model:
            config.WHISPER_MODEL = args.model
        cmd_transcribe(args)
    elif args.command == "channels":
        cmd_channels(args)
    elif args.command == "status":
        cmd_status(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
