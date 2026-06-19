"""Spotify integration: search tracks and create playlists."""

import spotipy
from spotipy.oauth2 import SpotifyOAuth
from typing import Optional
import os
from pathlib import Path


def _get_spotify_client() -> spotipy.Spotify:
    """Create an authenticated Spotify client.

    Requires SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, and
    SPOTIPY_REDIRECT_URI environment variables or a .env file.
    """
    # Try loading from .env
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    client_id = os.environ.get("SPOTIPY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET")
    redirect_uri = os.environ.get("SPOTIPY_REDIRECT_URI", "http://localhost:8888/callback")

    if not client_id or not client_secret:
        raise RuntimeError(
            "Spotify API credentials not found.\n\n"
            "1. Go to https://developer.spotify.com/dashboard\n"
            "2. Create an app\n"
            "3. Click 'Settings' > 'Redirect URIs' > Add 'http://localhost:8888/callback'\n"
            "4. Set environment variables:\n"
            "     export SPOTIPY_CLIENT_ID='your-client-id'\n"
            "     export SPOTIPY_CLIENT_SECRET='your-client-secret'\n"
            "   Or create a .env file in your project directory"
        )

    scope = "playlist-modify-public playlist-modify-private"

    return spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope,
            cache_path=str(Path.home() / ".rekord2spotify_token"),
        )
    )


def search_track(sp: spotipy.Spotify, artist: str, title: str,
                 isrc: Optional[str] = None,
                 duration_sec: Optional[int] = None) -> Optional[str]:
    """Search for a track on Spotify and return its URI.

    Matching strategy (in order):
    1. ISRC exact match (most reliable)
    2. artist:title exact search
    3. Fuzzy search (artist + title as general query)

    Args:
        sp: Authenticated Spotify client
        artist: Artist name
        title: Track title
        isrc: ISRC code if available
        duration_sec: Duration in seconds for verification

    Returns:
        Spotify track URI or None if not found
    """
    # Strategy 1: ISRC match
    if isrc:
        try:
            results = sp.search(q=f'isrc:{isrc}', type='track', limit=1)
            items = results['tracks']['items']
            if items:
                return items[0]['uri']
        except Exception:
            pass

    # Strategy 2: Exact artist + title
    # Remove common noise from titles for better matching
    clean_title = _clean_title_for_search(title)
    clean_artist = _clean_artist_for_search(artist)

    try:
        query = f'artist:"{clean_artist}" track:"{clean_title}"'
        results = sp.search(q=query, type='track', limit=5)
        items = results['tracks']['items']

        if items:
            # If we have duration, find best match
            if duration_sec:
                best = _find_best_duration_match(items, duration_sec)
                if best:
                    return best

            # Otherwise return first result
            return items[0]['uri']
    except Exception:
        pass

    # Strategy 3: Fuzzy search
    try:
        query = f'{clean_artist} {clean_title}'
        results = sp.search(q=query, type='track', limit=10)
        items = results['tracks']['items']

        # Try to find a good match
        for item in items:
            item_artist = item['artists'][0]['name'].lower()
            item_title = item['name'].lower()
            # Both artist and title must be substring matches
            if (clean_artist.lower() in item_artist or item_artist in clean_artist.lower()) and \
               (clean_title.lower() in item_title or item_title in clean_title.lower()):
                return item['uri']
    except Exception:
        pass

    return None


def search_tracks_batch(sp: spotipy.Spotify, tracks: list) -> list:
    """Search for multiple tracks. Returns list of (position, spotify_uri, title, artist).

    Prints progress as it searches.
    """
    results = []
    for i, entry in enumerate(tracks):
        track = entry.get("track", {})
        artist = track.get("artist", "Unknown Artist")
        title = track.get("title", "Unknown Track")
        isrc = track.get("isrc")
        duration = track.get("duration_sec")

        position = entry.get("position", i + 1)
        print(f"  [{position}/{len(tracks)}] Searching: {artist} — {title} ...", end=" ")

        uri = search_track(sp, artist, title, isrc, duration)

        if uri:
            print("✓")
            results.append((position, uri, title, artist))
        else:
            print("✗ not found")

    return results


def create_spotify_playlist(sp: spotipy.Spotify, name: str,
                             spotify_uris: list,
                             description: str = "") -> str:
    """Create a Spotify playlist and add tracks.

    Args:
        sp: Authenticated Spotify client
        name: Playlist name
        spotify_uris: List of Spotify track URIs (in desired order)
        description: Optional playlist description

    Returns:
        URL of the created playlist
    """
    user = sp.current_user()
    user_id = user['id']

    playlist = sp.user_playlist_create(
        user=user_id,
        name=name,
        public=False,  # Private by default
        description=description,
    )

    # Add tracks in batches of 100 (Spotify API limit)
    uris_only = [u for _, u, _, _ in spotify_uris]
    for i in range(0, len(uris_only), 100):
        batch = uris_only[i:i + 100]
        sp.playlist_add_items(playlist['id'], batch)

    return playlist['external_urls']['spotify']


def _clean_title_for_search(title: str) -> str:
    """Clean a track title for better Spotify search matching."""
    # Remove common suffixes that hurt matching
    # Strip " - Original Mix", " (Original Mix)", etc.
    import re
    title = re.sub(r'\s*[-–(]\s*(Original|Extended|Radio)\s*(Mix|Edit|Version)\s*[)-]?\s*$',
                   '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*\(feat\..*?\)', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*\[.*?\]$', '', title)
    return title.strip()


def _clean_artist_for_search(artist: str) -> str:
    """Clean an artist name for better Spotify search matching."""
    # Handle "Artist A, Artist B" -> just use first artist
    if ',' in artist:
        artist = artist.split(',')[0]
    # Handle "Artist A feat. Artist B" -> just main artist
    import re
    artist = re.sub(r'\s+feat\.\s+.*', '', artist, flags=re.IGNORECASE)
    artist = re.sub(r'\s+ft\.\s+.*', '', artist, flags=re.IGNORECASE)
    return artist.strip()


def _find_best_duration_match(items: list, target_sec: int) -> Optional[str]:
    """From a list of Spotify track results, find the best duration match."""
    best_match = None
    best_diff = float('inf')

    for item in items:
        item_duration_ms = item.get('duration_ms', 0)
        item_duration_sec = item_duration_ms / 1000
        diff = abs(item_duration_sec - target_sec)

        # Must be within 10 seconds
        if diff < 10.0 and diff < best_diff:
            best_diff = diff
            best_match = item['uri']

    return best_match