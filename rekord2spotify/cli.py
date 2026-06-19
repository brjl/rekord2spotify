"""CLI for rekord2spotify."""

import sys
from pathlib import Path

import click

from .extractor import (
    extract_history,
    list_sessions,
    get_latest_session,
    get_session_by_name,
    find_usb_drives,
)
from .tracklist import format_tracklist, format_session_summary, format_session_list


def _resolve_path(path):
    """Resolve path: auto-detect USB if not provided, otherwise use given path."""
    if path:
        return path

    usb_drives = find_usb_drives()
    if not usb_drives:
        click.echo("No rekordbox USB drives found.", err=True)
        click.echo("Plug in a USB or use: rekord2spotify show --path /Volumes/DRIVE")
        sys.exit(1)

    if len(usb_drives) == 1:
        drive = usb_drives[0]
        click.echo(f"Drive: {drive}")
        return drive

    click.echo("Multiple drives found. Pick one:")
    for d in usb_drives:
        click.echo(f"  rekord2spotify show --path {d}")
    sys.exit(1)


def _resolve_session(data, session):
    """Resolve session by index, name, or 'latest'."""
    sessions = data.get("sessions", [])
    if not sessions:
        click.echo("No history sessions found.", err=True)
        sys.exit(1)

    if session is None or session == "latest":
        session_data = get_latest_session(data)
        if not session_data:
            click.echo("No sessions found.", err=True)
            sys.exit(1)
        return session_data

    # Try numeric index (1-based)
    try:
        idx = int(session) - 1
        if 0 <= idx < len(sessions):
            return sessions[idx]
    except ValueError:
        pass

    # Try exact name match
    session_data = get_session_by_name(data, session)
    if session_data:
        return session_data

    # Try partial name match (case-insensitive)
    session_lower = session.lower()
    for s in sessions:
        if session_lower in s["name"].lower():
            return s

    # Not found
    click.echo(f"Session '{session}' not found.", err=True)
    click.echo(format_session_list(sessions), err=True)
    sys.exit(1)


# Shared options
_path_option = click.option(
    "--path", "-p", default=None,
    help="Path to USB drive or export.pdb (auto-detected if omitted)"
)
_session_arg = click.argument("session", required=False)


@click.group()
@click.version_option(version="0.1.0")
def main():
    """rekord2spotify — export rekordbox USB history as tracklists or Spotify playlists.

    Plug in your rekordbox USB and run:

    \b
        rekord2spotify show         # list sessions
        rekord2spotify export       # text tracklist (latest session)
        rekord2spotify export 2     # export session #2
        rekord2spotify playlist     # create Spotify playlist
    """
    pass


@main.command()
@_path_option
def show(path):
    """Show all history sessions on a USB drive."""
    path = _resolve_path(path)
    data = extract_history(path)
    sessions = data.get("sessions", [])

    if not sessions:
        click.echo("No history sessions found.")
        return

    click.echo(f"\n{len(sessions)} session(s)\n")
    click.echo(format_session_list(sessions, include_preview=True))


@main.command()
@_path_option
@_session_arg
@click.option("--details", "-d", is_flag=True, help="Include BPM, key, and duration")
@click.option("--output", "-o", type=click.Path(), help="Write to file")
def export(path, session, details, output):
    """Export a session as a text tracklist.

    SESSION: number (1 = first), name, or omit for latest.

    \b
    Examples:
      rekord2spotify export
      rekord2spotify export 2
      rekord2spotify export 1 -d
      rekord2spotify export -o my_set.txt
    """
    path = _resolve_path(path)
    data = extract_history(path)
    session_data = _resolve_session(data, session)

    text = format_tracklist(session_data, include_details=details)

    if output:
        Path(output).write_text(text + "\n")
        click.echo(f"Saved to {output}")
    else:
        click.echo(text)


@main.command()
@_path_option
@_session_arg
@click.option("--name", "-n", default=None, help="Playlist name (default: session name)")
@click.option("--dry-run", is_flag=True, help="Search but don't create playlist")
def playlist(path, session, name, dry_run):
    """Create a Spotify playlist from a history session.

    SESSION: number (1 = first), name, or omit for latest.

    One-time Spotify setup:
      1. Go to https://developer.spotify.com/dashboard
      2. Create an app + add http://localhost:8888/callback as redirect URI
      3. Create .env with SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET

    \b
    Examples:
      rekord2spotify playlist
      rekord2spotify playlist 2
      rekord2spotify playlist -n "My Set"
      rekord2spotify playlist --dry-run
    """
    path = _resolve_path(path)
    data = extract_history(path)
    session_data = _resolve_session(data, session)

    tracks = session_data["tracks"]
    session_name = session_data["name"]
    click.echo(f"\n{session_name} — {len(tracks)} tracks\n")

    from .spotify import (
        _get_spotify_client,
        search_tracks_batch,
        create_spotify_playlist,
        _check_credentials,
    )

    if not _check_credentials():
        click.echo("Spotify credentials not set up.\n")
        click.echo("Quick setup:")
        click.echo("  1. Go to https://developer.spotify.com/dashboard")
        click.echo("  2. Create an app (name it 'rekord2spotify')")
        click.echo("  3. In Settings, add Redirect URI: http://localhost:8888/callback")
        click.echo("  4. Copy Client ID and Client Secret")
        click.echo("  5. Create .env file:")
        click.echo("       echo 'SPOTIPY_CLIENT_ID=YOUR_ID' >> .env")
        click.echo("       echo 'SPOTIPY_CLIENT_SECRET=YOUR_SECRET' >> .env")
        click.echo("\nThen run: rekord2spotify playlist")
        sys.exit(1)

    sp = _get_spotify_client()

    click.echo("Searching Spotify...")
    matches = search_tracks_batch(sp, tracks)
    click.echo()

    matched = len(matches)
    total = len(tracks)
    pct = int(matched / total * 100) if total else 0
    click.echo(f"Matched: {matched}/{total} ({pct}%)")

    unmatched = total - matched
    if unmatched:
        click.echo(f"Not found: {unmatched}")

    if dry_run:
        click.echo("\n(Dry run — no playlist created)")
        return

    if matched == 0:
        click.echo("\nNo tracks found on Spotify.")
        return

    playlist_name = name or session_name
    description = f"Exported from {session_name} via rekord2spotify"

    try:
        url = create_spotify_playlist(sp, playlist_name, matches, description)
        click.echo(f"\n  {playlist_name}")
        click.echo(f"  {url}")
    except Exception as e:
        click.echo(f"\nError: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
