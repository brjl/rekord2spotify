"""Import playlists exported from Rekordbox (text/M3U8/CSV)."""

from pathlib import Path
from typing import List, Dict, Optional


def import_playlist(filepath: str, session_name: Optional[str] = None) -> dict:
    """Import a playlist file exported from Rekordbox.

    Supports:
    - Plain text: one track per line, "Artist - Title" or "Artist — Title"
    - M3U/M3U8: standard playlist format
    - Rekordbox text export: standard rekordbox text format

    Returns dict with 'sessions' key matching the USB extractor format.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    # Try common rekordbox encodings
    for enc in ["utf-16", "utf-8-sig", "utf-8", "latin-1"]:
        try:
            content = path.read_text(encoding=enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    else:
        # Last resort: read binary and decode
        content = path.read_bytes().decode("utf-16", errors="replace")

    if not session_name:
        session_name = path.stem

    # Detect format
    lines = content.strip().split("\n")
    if not lines:
        return {"sessions": []}

    if lines[0].strip().upper() == "#EXTM3U":
        tracks = _parse_m3u(lines)
    elif "\t" in lines[0] and ("Track Title" in lines[0] or "Artist" in lines[0]):
        tracks = _parse_rekordbox_tsv(lines)
    elif "," in lines[0] and _looks_like_csv(lines[0]):
        tracks = _parse_csv(lines)
    else:
        tracks = _parse_text(lines)

    return {
        "sessions": [{
            "name": session_name,
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
        # Line is a filepath - extract artist/title from filename
        path = Path(line)
        name = path.stem
        artist, title = _split_artist_title(name)
        tracks.append({"artist": artist, "title": title})
    return tracks


def _parse_rekordbox_tsv(lines: List[str]) -> List[dict]:
    """Parse Rekordbox tab-separated export format.

    Header: #  Artwork  Track Title  Artist  Album  Genre  BPM  Rating  Time  Key  Date Added
    """
    tracks = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Skip header
        if "Track Title" in line and "Artist" in line:
            continue

        cols = line.split("\t")
        if len(cols) < 5:
            continue

        # Columns: 0=#, 1=Artwork, 2=Track Title, 3=Artist, 4=Album, 5=Genre, 6=BPM, 7=Rating, 8=Time, 9=Key, 10=Date Added
        title = cols[2].strip()
        artist = cols[3].strip()
        album = cols[4].strip() or None
        genre = cols[5].strip() or None
        bpm_str = cols[6].strip()
        time_str = cols[8].strip()
        key = cols[9].strip() or None

        # Some tracks have artist embedded in title column (col 3 empty)
        if not artist and " - " in title:
            parts = title.split(" - ", 1)
            artist, title = parts[0].strip(), parts[1].strip()

        tracks.append({
            "artist": artist,
            "title": title,
            "album": album,
            "genre": genre,
            "bpm": bpm,
            "duration_sec": duration_sec,
            "key": key,
        })

    return tracks


def _parse_csv(lines: List[str]) -> List[dict]:
    """Parse CSV format (rekordbox can export CSV)."""
    import csv, io
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    tracks = []
    for row in reader:
        # Normalize column names
        row_lower = {k.lower().strip(): v for k, v in row.items()}
        title = row_lower.get("title") or row_lower.get("track title") or row_lower.get("name", "Unknown Track")
        artist = row_lower.get("artist") or row_lower.get("artist name", "Unknown Artist")
        tracks.append({"artist": artist, "title": title})
    return tracks


def _parse_text(lines: List[str]) -> List[dict]:
    """Parse plain text playlist format.

    Common formats:
    - "Artist - Title"
    - "Artist — Title" (em dash)
    - "01. Artist - Title"
    - "Artist - Title (Remix)"
    """
    import re

    tracks = []
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Skip headers/separators
        if line.startswith("=") or line.startswith("#") or line.startswith("-"):
            continue
        if line.upper() in ("HISTORY", "TRACKLIST", "PLAYLIST"):
            continue

        # Remove leading track numbers like "01. " or "1. " or "01 - "
        line = re.sub(r"^\d+[\.\)\-]\s*", "", line)

        artist, title = _split_artist_title(line)
        tracks.append({"artist": artist, "title": title})

    return tracks


def _split_artist_title(text: str) -> tuple:
    """Split 'Artist - Title' or 'Artist — Title' into (artist, title)."""
    import re

    # Try em dash first
    for sep in [" — ", " – ", " - "]:
        if sep in text:
            parts = text.split(sep, 1)
            return parts[0].strip(), parts[1].strip()

    # Try tab
    if "\t" in text:
        parts = text.split("\t", 1)
        return parts[0].strip(), parts[1].strip()

    # Fallback: return as-is
    return "Unknown Artist", text.strip()


def _looks_like_csv(line: str) -> bool:
    """Heuristic: does this line look like a CSV header?"""
    lower = line.lower()
    csv_indicators = ["artist", "title", "track", "name", "bpm", "genre"]
    return sum(1 for ind in csv_indicators if ind in lower) >= 2
