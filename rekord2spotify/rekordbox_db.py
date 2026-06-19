"""Read history from Rekordbox 6/7 local master.db database.

Requires pyrekordbox: pip install pyrekordbox
"""

from typing import Optional, Dict, List
from pathlib import Path


def find_master_db() -> Optional[str]:
    """Find the Rekordbox 6/7 master.db file."""
    locations = [
        Path.home() / "Library" / "Pioneer" / "rekordbox" / "master.db",
        Path.home() / "Library" / "Application Support" / "Pioneer" / "rekordbox" / "master.db",
    ]
    for loc in locations:
        if loc.exists():
            return str(loc)
    return None


def extract_history_local(db_path: Optional[str] = None) -> dict:
    """Extract history from Rekordbox 6/7 local database.

    Args:
        db_path: Path to master.db (auto-detected if None)

    Returns:
        Dict with 'sessions' key, same format as USB extractor
    """
    try:
        from pyrekordbox import Rekordbox6Database
    except ImportError:
        raise RuntimeError(
            "pyrekordbox is required for local database access.\n"
            "Install it: pip install pyrekordbox"
        )

    path = db_path or find_master_db()
    if not path or not Path(path).exists():
        raise FileNotFoundError(
            "Rekordbox 6/7 master.db not found.\n"
            "Expected at: ~/Library/Pioneer/rekordbox/master.db\n"
            "This feature requires Rekordbox 6 or later."
        )

    db = Rekordbox6Database(path)

    # Get all history entries with content and artist relationships
    from pyrekordbox.db6.tables import DjmdHistory, DjmdContent, DjmdArtist

    history_query = (
        db.query(DjmdHistory)
        .order_by(DjmdHistory.DateCreated)
    )
    history_entries = history_query.all()

    if not history_entries:
        return {"sessions": []}

    # Group by playlist/session
    # Rekordbox 6 history entries have a PlaylistID that groups them into sessions
    sessions_map: Dict[int, dict] = {}
    track_ids_seen: set = set()

    for entry in history_entries:
        playlist_id = getattr(entry, 'PlaylistID', None) or 0
        
        if playlist_id not in sessions_map:
            sessions_map[playlist_id] = {
                "name": f"HISTORY {len(sessions_map) + 1:03d}",
                "tracks": [],
            }
        
        content_id = getattr(entry, 'ContentID', None)
        if content_id is None or content_id in track_ids_seen:
            continue
        track_ids_seen.add(content_id)

        # Get content (track) info
        content = db.get_content(ID=content_id)
        if content is None:
            continue

        title = getattr(content, 'Title', 'Unknown Track') or 'Unknown Track'
        
        # Get artist name
        artist_name = "Unknown Artist"
        try:
            artist = content.Artist
            if artist:
                artist_name = artist.Name or "Unknown Artist"
        except Exception:
            pass

        # Get additional metadata
        bpm = None
        try:
            tempo = getattr(content, 'BPM', None)
            if tempo:
                bpm = float(tempo) / 100.0 if tempo > 100 else float(tempo)
        except Exception:
            pass

        duration_sec = getattr(content, 'Length', None)
        key_name = None
        try:
            key_name = getattr(content, 'Key', None)
            if hasattr(key_name, 'ScaleName'):
                key_name = key_name.ScaleName
        except Exception:
            pass

        genre_name = None
        try:
            genre = content.Genre
            if genre:
                genre_name = genre.Name
        except Exception:
            pass

        album_name = None
        try:
            album = content.Album
            if album:
                album_name = album.Name
        except Exception:
            pass

        sessions_map[playlist_id]["tracks"].append({
            "position": len(sessions_map[playlist_id]["tracks"]) + 1,
            "title": title,
            "artist": artist_name,
            "bpm": bpm,
            "duration_sec": int(duration_sec) if duration_sec else None,
            "key": key_name,
            "genre": genre_name,
            "album": album_name,
            "play_count": getattr(content, 'PlayCount', 0) or 0,
        })

    # Convert to sorted session list
    sessions = sorted(sessions_map.values(), key=lambda s: s["name"])

    return {"sessions": sessions}