#!/usr/bin/env python3
"""Sync content/videos/*.md from the channel's YouTube "Videos" tab.

YouTube is the source of truth: this script regenerates every file it
manages (any content/videos/*.md with JSON front matter containing a
youtube_id) from the current channel listing, and removes ones for videos
that are no longer there. Files that aren't JSON front matter (e.g. hand
authored ones) are left alone.

Usage:
    python3 scripts/sync_youtube.py [channel_url]
"""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_CHANNEL_URL = "https://www.youtube.com/@the_students_media/videos"
CONTENT_DIR = Path(__file__).resolve().parent.parent / "content" / "videos"


def slugify(title):
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "video"


def fetch_videos(channel_url):
    proc = subprocess.run(
        ["yt-dlp", "--dump-json", "--no-warnings", "--ignore-errors", channel_url],
        capture_output=True,
        text=True,
    )
    videos = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            videos.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if not videos:
        print("yt-dlp returned no videos, aborting without touching local content.", file=sys.stderr)
        if proc.stderr:
            print(proc.stderr.strip(), file=sys.stderr)
        sys.exit(1)
    return videos


def is_managed(md_file):
    try:
        text = md_file.read_text(encoding="utf-8")
    except OSError:
        return False
    if not text.startswith("{"):
        return False
    try:
        front, _ = json.JSONDecoder().raw_decode(text)
    except json.JSONDecodeError:
        return False
    return isinstance(front, dict) and "youtube_id" in front


def main():
    if subprocess.run(["which", "yt-dlp"], capture_output=True).returncode != 0:
        print("yt-dlp not found. Install it with: brew install yt-dlp", file=sys.stderr)
        sys.exit(1)

    channel_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CHANNEL_URL
    videos = fetch_videos(channel_url)

    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    managed_before = {f for f in CONTENT_DIR.glob("*.md") if is_managed(f)}

    used_slugs = {}
    written = set()
    for v in videos:
        video_id = v.get("id")
        title = v.get("title") or video_id
        description = (v.get("description") or "").strip()
        upload_date = v.get("upload_date")
        date = datetime.strptime(upload_date, "%Y%m%d").strftime("%Y-%m-%d") if upload_date else ""

        slug = slugify(title)
        if slug in used_slugs and used_slugs[slug] != video_id:
            slug = f"{slug}-{video_id[-6:]}"
        used_slugs[slug] = video_id

        front_matter = {
            "title": title,
            "date": date,
            "youtube_id": video_id,
            "description": description,
        }
        path = CONTENT_DIR / f"{slug}.md"
        path.write_text(json.dumps(front_matter, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.add(path)

    removed = managed_before - written
    for f in removed:
        f.unlink()

    print(f"Synced {len(written)} video(s) from {channel_url}")
    if removed:
        print(f"Removed {len(removed)} video(s) no longer on the channel: " + ", ".join(f.name for f in removed))


if __name__ == "__main__":
    main()
