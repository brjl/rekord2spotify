"""Import playlists exported from Rekordbox (text/M3U8/CSV/TSV)."""

import csv
import io
import re
from pathlib import Path
from typing import List, Optional


def import_playlist(filepath: str, session_name: Optional[str] = None) -> dict:
    """Import a playlist file. Returns dict with 'sessions' key."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    content = _read_encoded(path)
    lines = content.strip().split("\n")
    if not lines:
        return {"sessions": []}

    if lines[0].strip().upper() == "#EXTM3U":
        tracks = _parse_m3u(lines)
    elif "\t" in lines[0] and ("Track Title" in lines[0] or "Artist" in lines[0]):
        tracks = _parse_rekordbox_tsv(lines)
    else:
        tracks = _parse_text(lines)

    name = session_name or path.stem
    return _build_result(name, tracks)


def _read_encoded(path: Path) -> str:
    """Read file with auto-encoding detection (rekordbox uses UTF-16)."""
    for enc in ["utf-16", "utf-8-sig", "utf-8", "latin-1"]:
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return path.read_bytes().decode("utf-16", errors="replace")


def _build_result(name: str, tracks: List[dict]) -> dict:
    """Build the standard sessions output format."""
    return {
        "sessions": [{
            "name": name,
            "tracks": [
                {
                    "position": i + 1,
                    "title": t.get("title", "Unknown Track"),
                    "artist": t.get("artist", "Unknown Artist"),
                    "bpm": t.get("bpm"),
                    "key": t.get("key"),
                    "duration_sec": t.get("duration_sec"),
                    "genre": t.get("genre"),
                    "album": t.get("album"),
                    "isrc": t.get("isrc"),
                    "play_count": 0,
                }
                for i, t in enumerate(tracks)
            ]
        }]
    }


def _parse_m3u(lines: List[str]) -> List[dict]:
    """Parse M3U/M3U8 playlist format."""
    tracks = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = Path(line).stem
        artist, title = _split_artist_title(name)
        tracks.append({"artist": artist, "title": title})
    return tracks


def _parse_rekordbox_tsv(lines: List[str]) -> List[dict]:
    """Parse Rekordbox tab-separated export format.

    Columns: #, Artwork, Track Title, Artist, Album, Genre, BPM, Rating, Time, Key, Date Added
    """
    tracks = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or ("Track Title" in line and "Artist" in line):
            continue

        cols = line.split("\t")
        if len(cols) < 5:
            continue

        title = cols[2].strip()
        artist = cols[3].strip()
        album = cols[4].strip() or None
        genre = cols[5].strip() or None
        key = cols[9].strip() or None

        # Some tracks embed artist in the title column
        if not artist and " - " in title:
            artist, title = title.split(" - ", 1)
            artist, title = artist.strip(), title.strip()

        bpm = _parse_float(cols[6])
        duration = _parse_time(cols[8])

        tracks.append({
            "artist": artist or "Unknown Artist",
            "title": title or "Unknown Track",
            "album": album,
            "genre": genre,
            "bpm": bpm,
            "duration_sec": duration,
            "key": key,
        })

    return tracks


def _parse_text(lines: List[str]) -> List[dict]:
    """Parse plain text playlist (one track per line)."""
    tracks = []
    for line in lines:
        line = line.strip()
        if not line or line[0] in "=#-":
            continue
        if line.upper() in ("HISTORY", "TRACKLIST", "PLAYLIST"):
            continue

        line = re.sub(r"^\d+[\.\)\-]\s*", "", line)
        artist, title = _split_artist_title(line)
        tracks.append({"artist": artist, "title": title})
    return tracks


def _split_artist_title(text: str) -> tuple:
    """Split 'Artist - Title' into (artist, title)."""
    for sep in [" — ", " – ", " - "]:
        if sep in text:
            a, t = text.split(sep, 1)
            return a.strip(), t.strip()
    if "\t" in text:
        a, t = text.split("\t", 1)
        return a.strip(), t.strip()
    return "Unknown Artist", text.strip()


def _parse_float(s: str) -> Optional[float]:
    try:
        return float(s.strip()) if s.strip() else None
    except ValueError:
        return None


def _parse_time(s: str) -> Optional[int]:
    try:
        parts = s.strip().split(":")
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        pass
    return None
