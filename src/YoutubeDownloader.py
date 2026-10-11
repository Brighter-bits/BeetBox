#!/usr/bin/env python3
"""
Look up a track on MusicBrainz (fallback: YouTube), skip if already downloaded,
otherwise download the audio from YouTube as mp3 and embed the album cover
(from the Cover Art Archive).

Usage:
    python fetch_music.py "Get Lucky - Random Access Memories - Daft Punk"
Input is "Title - Album - Artist". If it doesn't parse, the raw string is searched on YouTube.
"""
import os
import re
import sys

import musicbrainzngs as mb
import requests
from mutagen.id3 import APIC, ID3, ID3NoHeaderError
from yt_dlp import YoutubeDL

MUSIC_DIR = os.path.expanduser("./Music")
DURATION_TOLERANCE = 5  # seconds; only used to warn about a dubious YouTube match
MIN_SCORE = 80          # MusicBrainz match score (0-100); below this, fall back to YouTube

# MusicBrainz requires an identifying User-Agent. Put a real contact here.
# (musicbrainzngs throttles itself to 1 request/second by default.)
mb.set_useragent("fetch_music", "0.1", "PUTANEMAILHERE")


# ---------- helpers ----------

def safe(name):
    """Strip characters that are bad in filenames (and '%', which breaks yt-dlp templates)."""
    return re.sub(r'[\\/:*?"<>|%]', "_", name).strip()


def path_for(stem):
    return os.path.join(MUSIC_DIR, safe(stem) + ".mp3")


def have(stem):
    return os.path.exists(path_for(stem))


# ---------- search ----------

def parse_query(query):
    """'Title - Album - Artist' -> (title, album, artist), or None if it doesn't fit."""
    parts = [p.strip() for p in query.rsplit(" - ", 2)]  # rsplit: the title itself may contain " - "
    return tuple(parts) if len(parts) == 3 and all(parts) else None


def search_musicbrainz(title, album, artist):
    """Return the top MusicBrainz recording as a dict, or None (also None on any failure)."""
    try:
        recs = mb.search_recordings(
            limit=5, recording=title, release=album, artist=artist
        )["recording-list"]
    except Exception as e:  # network error, 503 rate limit...
        print(f"MusicBrainz search failed ({e}); falling back to YouTube")
        return None
    if not recs or int(recs[0].get("ext:score", 0)) < MIN_SCORE:
        return None
    r = recs[0]
    return {
        "title": r["title"],
        "artist": r["artist-credit-phrase"],
        "duration": int(r["length"]) / 1000 if r.get("length") else None,
        "releases": r.get("release-list", []),
        "album": album,
    }


def search_youtube(query, n=5):
    """Return up to n flat results (id, title, duration, ...) without downloading anything."""
    with YoutubeDL({"quiet": True, "extract_flat": True}) as ydl:
        info = ydl.extract_info(f"ytsearch{n}:{query}", download=False)
    return info["entries"]


# ---------- cover art ----------

def fetch_image(url):
    """Return (bytes, mime) or None."""
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
    except requests.RequestException:
        return None
    return r.content, r.headers.get("Content-Type", "image/jpeg")


def find_cover(releases, album, max_releases=5):
    """Try the Cover Art Archive for the releases (and their release groups) the recording is on."""
    def rank(rel):  # the requested album first, then official albums; sort is stable
        rg = rel.get("release-group", {})
        return (
            rel.get("title", "").lower() != album.lower(),
            rg.get("primary-type") != "Album",
            rel.get("status") != "Official",
        )

    urls = []
    for rel in sorted(releases, key=rank)[:max_releases]:
        rg = rel.get("release-group", {}).get("id")
        if rg:  # a release-group URL resolves to the front cover of any release in the group
            urls.append(f"https://coverartarchive.org/release-group/{rg}/front-500")
        urls.append(f"https://coverartarchive.org/release/{rel['id']}/front-500")

    for url in dict.fromkeys(urls):  # dedupe, keep order
        img = fetch_image(url)
        if img:
            return img
    return None


def embed_cover(mp3_path, image):
    data, mime = image
    try:
        tags = ID3(mp3_path)
    except ID3NoHeaderError:
        tags = ID3()
    tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=data))  # type 3 = front cover
    tags.save(mp3_path, v2_version=3)  # ID3v2.3 is the most widely supported


# ---------- download ----------

def download_audio(video_id, stem):
    opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(MUSIC_DIR, safe(stem)) + ".%(ext)s",
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"}
        ],
        "quiet": True,
    }
    with YoutubeDL(opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={video_id}"])


# ---------- main flow ----------

def fetch(query):
    os.makedirs(MUSIC_DIR, exist_ok=True)

    parsed = parse_query(query)
    if not parsed:
        print(f"expected 'Title - Album - Artist', got: {query!r}")
    track = search_musicbrainz(*parsed) if parsed else None
    if track:
        # MusicBrainz gave us a canonical name -> check for duplicates BEFORE hitting YouTube.
        stem = f"{track['artist']} - {track['title']}"
        if have(stem):
            print(f"already have: {stem}")
            return path_for(stem)

        candidates = search_youtube(f"{stem} audio")
        if not candidates:
            print(f"no YouTube match for: {stem}")
            return None

        if track["duration"]:
            # Pick the YouTube result whose length is closest to the recording's.
            video = min(candidates, key=lambda v: abs((v.get("duration") or 0) - track["duration"]))
            diff = abs((video.get("duration") or 0) - track["duration"])
            if diff > DURATION_TOLERANCE:
                print(f"warning: best match is {diff:.0f}s off: {video['title']}")
        else:
            video = candidates[0]  # MusicBrainz has no length for this recording

        cover = find_cover(track["releases"], track["album"])
    else:
        # MusicBrainz found nothing -> take the top YouTube hit.
        yt_query = f"{parsed[2]} {parsed[0]}" if parsed else query  # "Artist Title"
        candidates = search_youtube(yt_query, n=1)
        if not candidates:
            print(f"nothing found for: {query}")
            return None
        video = candidates[0]
        stem = video["title"]
        if have(stem):
            print(f"already have: {stem}")
            return path_for(stem)
        cover = None

    # No Cover Art Archive hit (or no MusicBrainz match): use the YouTube thumbnail (16:9).
    cover = cover or fetch_image(f"https://i.ytimg.com/vi/{video['id']}/hqdefault.jpg")

    print(f"downloading: {stem}")
    download_audio(video["id"], stem)
    if cover:
        embed_cover(path_for(stem), cover)
    else:
        print("no cover art found")
    return path_for(stem)


if __name__ == "__main__":
    for q in sys.argv[1:]:
        fetch(q)