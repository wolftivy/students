#!/usr/bin/env python3
"""Sync content/videos/*.md from the channel's YouTube "Videos" tab.

YouTube is the source of truth for front matter (title, date, description):
this script regenerates every file it manages (any content/videos/*.md with
JSON front matter containing a youtube_id) from the current channel listing,
and removes ones for videos that are no longer there. Files that aren't JSON
front matter (e.g. hand authored ones) are left alone.

The page body is treated differently: it's a manually-added transcript, not
something YouTube provides, so it's preserved across re-syncs. It's tracked
by youtube_id rather than filename, so it survives even if the video's title
(and therefore its generated slug) changes.

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


def parse_managed(md_file):
    """Return (front_matter, body) if md_file is one this script manages, else None."""
    try:
        text = md_file.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("{"):
        return None
    try:
        front, end = json.JSONDecoder().raw_decode(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(front, dict) or "youtube_id" not in front:
        return None
    return front, text[end:].lstrip("\n")


def is_managed(md_file):
    return parse_managed(md_file) is not None


def main():
    if subprocess.run(["which", "yt-dlp"], capture_output=True).returncode != 0:
        print("yt-dlp not found. Install it with: brew install yt-dlp", file=sys.stderr)
        sys.exit(1)

    channel_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CHANNEL_URL
    videos = fetch_videos(channel_url)

    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    managed_before = {f for f in CONTENT_DIR.glob("*.md") if is_managed(f)}

    transcripts = {}
    for f in managed_before:
        front, body = parse_managed(f)
        if body.strip():
            transcripts[front["youtube_id"]] = body

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
        content = json.dumps(front_matter, indent=2, ensure_ascii=False) + "\n"
        transcript = transcripts.get(video_id, "").strip()
        if transcript:
            content += "\n" + transcript + "\n"

        path = CONTENT_DIR / f"{slug}.md"
        path.write_text(content, encoding="utf-8")
        written.add(path)

    removed = managed_before - written
    for f in removed:
        f.unlink()

    print(f"Synced {len(written)} video(s) from {channel_url}")
    if transcripts:
        print(f"Preserved {len(transcripts)} existing transcript(s)")
    if removed:
        print(f"Removed {len(removed)} video(s) no longer on the channel: " + ", ".join(f.name for f in removed))


if __name__ == "__main__":
    main()
