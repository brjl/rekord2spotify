"""Spotify integration: search tracks and create playlists."""

import os
import re
from pathlib import Path
from typing import Optional

import spotipy
from spotipy.oauth2 import SpotifyOAuth


def _load_credentials():
    """Load Spotify credentials from environment or .env. Call once."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def _check_credentials() -> bool:
    _load_credentials()
    return bool(os.environ.get("SPOTIPY_CLIENT_ID") and os.environ.get("SPOTIPY_CLIENT_SECRET"))


def _get_spotify_client() -> spotipy.Spotify:
    _load_credentials()
    client_id = os.environ.get("SPOTIPY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET")
    redirect_uri = os.environ.get("SPOTIPY_REDIRECT_URI", "http://localhost:8888/callback")

    if not client_id or not client_secret:
        raise RuntimeError("Spotify credentials not found. Set SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET in .env")

    return spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope="playlist-modify-public playlist-modify-private",
            cache_path=str(Path.home() / ".rekord2spotify_token"),
        )
    )


def search_track(sp: spotipy.Spotify, artist: str, title: str,
                 isrc: Optional[str] = None,
                 duration_sec: Optional[int] = None) -> Optional[str]:
    """Search for a track on Spotify. Returns URI or None.

    Strategy: ISRC → exact 'artist:"X" track:"Y"' → fuzzy substring match.
    """
    # ISRC exact match
    if isrc:
        try:
            results = sp.search(q=f"isrc:{isrc}", type="track", limit=1)
            items = results["tracks"]["items"]
            if items:
                return items[0]["uri"]
        except Exception:
            pass

    clean_artist = _clean_artist(artist)
    clean_title = _clean_title(title)

    # Exact artist + title search
    try:
        query = f'artist:"{clean_artist}" track:"{clean_title}"'
        results = sp.search(q=query, type="track", limit=5)
        items = results["tracks"]["items"]

        if duration_sec and items:
            best = _best_by_duration(items, duration_sec)
            if best:
                return best
        if items:
            return items[0]["uri"]
    except Exception:
        pass

    # Fuzzy fallback
    try:
        results = sp.search(q=f"{clean_artist} {clean_title}", type="track", limit=10)
        for item in results["tracks"]["items"]:
            item_artist = item["artists"][0]["name"].lower()
            item_title = item["name"].lower()
            if (clean_artist.lower() in item_artist or item_artist in clean_artist.lower()) and \
               (clean_title.lower() in item_title or item_title in clean_title.lower()):
                return item["uri"]
    except Exception:
        pass

    return None


def search_tracks_batch(sp: spotipy.Spotify, tracks: list) -> list:
    """Search for multiple tracks. Returns [(position, uri, title, artist), ...]."""
    results = []
    for i, entry in enumerate(tracks):
        uri = search_track(
            sp,
            entry.get("artist", "Unknown Artist"),
            entry.get("title", "Unknown Track"),
            entry.get("isrc"),
            entry.get("duration_sec"),
        )
        if uri:
            results.append((
                entry.get("position", i + 1),
                uri,
                entry.get("title", ""),
                entry.get("artist", ""),
            ))
    return results


def create_spotify_playlist(sp: spotipy.Spotify, name: str,
                             matches: list, description: str = "") -> str:
    """Create a Spotify playlist and return its URL.

    Args:
        matches: List of (position, uri, title, artist) tuples
    """
    user_id = sp.current_user()["id"]
    playlist = sp.user_playlist_create(user_id, name, public=False, description=description)

    uris = [uri for _, uri, _, _ in matches]
    for i in range(0, len(uris), 100):
        sp.playlist_add_items(playlist["id"], uris[i:i + 100])

    return playlist["external_urls"]["spotify"]


def _clean_title(title: str) -> str:
    title = re.sub(r"\s*[-–(]\s*(Original|Extended|Radio)\s*(Mix|Edit|Version)\s*[)-]?\s*$",
                   "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*\(feat\..*?\)", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*\[.*?\]$", "", title)
    return title.strip()


def _clean_artist(artist: str) -> str:
    if "," in artist:
        artist = artist.split(",")[0]
    artist = re.sub(r"\s+feat\.\s+.*", "", artist, flags=re.IGNORECASE)
    artist = re.sub(r"\s+ft\.\s+.*", "", artist, flags=re.IGNORECASE)
    return artist.strip()


def _best_by_duration(items: list, target_sec: int) -> Optional[str]:
    """Find the best match by duration (±10s)."""
    best_uri, best_diff = None, float("inf")
    for item in items:
        diff = abs((item.get("duration_ms", 0) / 1000) - target_sec)
        if diff < 10.0 and diff < best_diff:
            best_uri, best_diff = item["uri"], diff
    return best_uri
