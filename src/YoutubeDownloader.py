#!/usr/bin/env python3
"""
Look up a track on MusicBrainz, find the exactly matching audio on YouTube, skip if
already downloaded, otherwise download it as mp3 and embed the album cover.

Usage:
    python fetch_music.py "Get Lucky - Random Access Memories - Daft Punk"
Input is "Title - Album - Artist". Nothing is downloaded unless a YouTube result passes
every check in check_candidate(); if nothing passes, the rejections are printed instead.
"""
import os
import re
import sys
import unicodedata

import musicbrainzngs as mb
import requests
from mutagen.id3 import APIC, ID3, ID3NoHeaderError
from yt_dlp import YoutubeDL

MUSIC_DIR = os.path.expanduser("./Music")
DURATION_TOLERANCE = 5          # seconds; max length difference vs the MusicBrainz recording
MAX_UNKNOWN_DURATION = 15 * 60  # if MusicBrainz has no length, reject anything longer (loops, mixes)

# Words that mark a different version of the song. A YouTube result containing one is rejected
# unless the word is also in the title/album you asked for.
BAD_WORDS = {"live", "cover", "remix", "karaoke", "instrumental", "acoustic", "slowed", "sped",
             "reverb", "nightcore", "8d", "mashup", "boosted", "reaction", "tutorial", "edit"}

# MusicBrainz requires an identifying User-Agent. Put a real contact here.
# (musicbrainzngs throttles itself to 1 request/second by default.)
mb.set_useragent("fetch_music", "0.1", "you@example.com")


# ---------- helpers ----------

def safe(name):
    """Strip characters that are bad in filenames (and '%', which breaks yt-dlp templates)."""
    return re.sub(r'[\\/:*?"<>|%]', "_", name).strip()


def path_for(stem):
    return os.path.join(MUSIC_DIR, safe(stem) + ".mp3")


def existing(stem):
    """Case-insensitive lookup, so 'daft punk - get lucky.mp3' counts as already downloaded."""
    want = (safe(stem) + ".mp3").lower()
    for f in os.listdir(MUSIC_DIR):
        if f.lower() == want:
            return os.path.join(MUSIC_DIR, f)
    return None


def norm(s):
    """Casefold, strip accents and punctuation: "Don’t Stop (Live)" -> "don t stop live"."""
    s = unicodedata.normalize("NFKD", s.casefold().replace("&", " and "))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(re.sub(r"[\W_]+", " ", s).split())


def contains(hay, needle):
    """Whole-word containment of two already-normalised strings."""
    return bool(needle) and f" {needle} " in f" {hay} "


def similar(a, b):
    return contains(a, b) or contains(b, a)


def artist_forms(artist):
    """Normalised full artist string plus the part before 'feat.', commas, '&', 'and', 'x'."""
    first = re.split(r",|;|&|\band\b|\bfeat\b|\bft\b|\bfeaturing\b|\bx\b",
                     artist, maxsplit=1, flags=re.I)[0]
    return {norm(artist), norm(first)} - {""}


def parse_query(query):
    """'Title - Album - Artist' -> (title, album, artist), or None if it doesn't fit."""
    parts = [p.strip() for p in query.rsplit(" - ", 2)]  # rsplit: the title itself may contain " - "
    return tuple(parts) if len(parts) == 3 and all(parts) else None


# ---------- MusicBrainz ----------

def search_musicbrainz(title, album, artist):
    """Return the recording matching title (exactly, ignoring case/punctuation), album AND artist.

    Returns None if no result matches all three. The top search hit is NOT trusted on its own.
    """
    try:
        recs = mb.search_recordings(
            limit=25, recording=title, release=album, artist=artist
        )["recording-list"]
    except Exception as e:  # network error, 503 rate limit...
        print(f"MusicBrainz search failed ({e})")
        return None

    for r in recs:
        credit = norm(r.get("artist-credit-phrase", ""))
        releases = r.get("release-list", [])
        if (norm(r["title"]) == norm(title)
                and any(contains(credit, a) for a in artist_forms(artist))
                and any(similar(norm(rel.get("title", "")), norm(album)) for rel in releases)):
            return {
                "title": r["title"],
                "artist": r["artist-credit-phrase"],
                "duration": int(r["length"]) / 1000 if r.get("length") else None,
                "releases": releases,
            }
    return None


# ---------- YouTube matching ----------

def search_youtube(query, n=8):
    """Return up to n flat results (id, title, channel, duration, ...) without downloading."""
    with YoutubeDL({"quiet": True, "extract_flat": True}) as ydl:
        info = ydl.extract_info(f"ytsearch{n}:{query}", download=False)
    return info["entries"]


def check_candidate(v, title, album, artist, duration):
    """Cheap checks on one flat search result. Returns (passed, reason_if_not)."""
    vt = norm(v.get("title") or "")
    ch = norm(v.get("channel") or v.get("uploader") or "")

    if not contains(vt, norm(title)):
        return False, "title doesn't match"
    if not any(contains(f"{vt} {ch}", a) for a in artist_forms(artist)):
        return False, "artist not in title or channel"
    bad = (set(vt.split()) & BAD_WORDS) - set(norm(f"{title} {album}").split())
    if bad:
        return False, "other version: " + ", ".join(sorted(bad))

    d = v.get("duration")
    if duration:
        if d is None or abs(d - duration) > DURATION_TOLERANCE:
            return False, f"length {d}s vs expected {duration:.0f}s"
    elif d and d > MAX_UNKNOWN_DURATION:
        return False, f"too long ({d}s)"
    return True, ""


def is_topic_for_album(v, album):
    """Strongest check: an auto-generated '<Artist> - Topic' upload whose description names the album."""
    if not norm(v.get("channel") or v.get("uploader") or "").endswith(" topic"):
        return False
    try:
        with YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={v['id']}", download=False)
    except Exception:
        return False
    text = norm(f"{info.get('album') or ''} {info.get('description') or ''}")
    return contains(text, norm(album))


def find_video(title, album, artist, duration):
    """Return (video, how, rejections). video is None unless a result passes every check."""
    found = {}
    for q in (f"{artist} {title} {album}", f"{artist} {title}"):
        for v in search_youtube(q):
            found.setdefault(v["id"], v)

    ok, rejected = [], []
    for v in found.values():
        passed, why = check_candidate(v, title, album, artist, duration)
        if passed:
            ok.append(v)
        else:
            rejected.append(f"{v.get('title')!r} ({why})")

    # Tier 1: Topic upload confirmed against the album.
    for v in ok:
        if is_topic_for_album(v, album):
            return v, "verified (Topic upload, album matches)", rejected
    # Tier 2: passed title/artist/version/length checks; closest length wins.
    if ok:
        best = min(ok, key=lambda v: abs(v["duration"] - duration) if duration else 0)
        return best, "matched on title, artist and length", rejected
    return None, None, rejected


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
        return None
    title, album, artist = parsed

    track = search_musicbrainz(title, album, artist)
    if track:
        stem, duration = f"{track['artist']} - {track['title']}", track["duration"]
        if duration is None:
            print("MusicBrainz has no length for this recording; skipping the length check")
    else:
        print("no exact MusicBrainz match; matching YouTube on title/artist only (no length check)")
        stem, duration = f"{artist} - {title}", None

    path = existing(stem)
    if path:
        print(f"already have: {path}")
        return path

    video, how, rejected = find_video(title, album, artist, duration)
    if not video:
        print(f"no YouTube result passed the checks for {stem}; nothing downloaded. Rejected:")
        for r in rejected:
            print(f"  - {r}")
        return None
    print(f"{how}: {video['title']!r} -> {stem}")

    cover = find_cover(track["releases"], album) if track else None
    # No Cover Art Archive hit (or no MusicBrainz match): use the YouTube thumbnail (16:9).
    cover = cover or fetch_image(f"https://i.ytimg.com/vi/{video['id']}/hqdefault.jpg")

    download_audio(video["id"], stem)
    path = path_for(stem)
    if cover:
        embed_cover(path, cover)
    else:
        print("no cover art found")
    return path


if __name__ == "__main__":
    for q in sys.argv[1:]:
        fetch(q)