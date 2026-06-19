"""CLI for rekord2spotify."""

import sys
from pathlib import Path

import click

from .extractor import (
    extract_history,
    get_latest_session,
    get_session_by_name,
    find_usb_drives,
)
from .tracklist import format_tracklist, format_session_list


def _resolve_usb_path(path):
    """Auto-detect USB if not provided."""
    if path:
        return path

    usb_drives = find_usb_drives()
    if not usb_drives:
        click.echo("No rekordbox USB drives found.", err=True)
        click.echo("Plug in a USB or specify --path", err=True)
        sys.exit(1)

    if len(usb_drives) == 1:
        click.echo(f"Drive: {usb_drives[0]}")
        return usb_drives[0]

    click.echo("Multiple drives:", err=True)
    for d in usb_drives:
        click.echo(f"  {d}", err=True)
    sys.exit(1)


def _load_sessions(source_type, path):
    """Load sessions from USB or local database."""
    if source_type == "local":
        from .rekordbox_db import extract_history_local, find_master_db
        db_path = path or find_master_db()
        if not db_path:
            click.echo("Rekordbox 6/7 master.db not found.", err=True)
            click.echo("Expected: ~/Library/Pioneer/rekordbox/master.db", err=True)
            sys.exit(1)
        data = extract_history_local(db_path)
    else:
        path = _resolve_usb_path(path)
        data = extract_history(path)

    return data.get("sessions", [])


def _resolve_session(sessions, session):
    """Resolve session by index, name, or 'latest'."""
    if not sessions:
        click.echo("No history sessions found.", err=True)
        sys.exit(1)

    if session is None or session == "latest":
        s = get_latest_session({"sessions": sessions})
        if not s:
            click.echo("No sessions found.", err=True)
            sys.exit(1)
        return s

    # Try numeric index (1-based)
    try:
        idx = int(session) - 1
        if 0 <= idx < len(sessions):
            return sessions[idx]
    except ValueError:
        pass

    # Try exact name
    s = get_session_by_name({"sessions": sessions}, session)
    if s:
        return s

    # Try partial match
    session_lower = session.lower()
    for s in sessions:
        if session_lower in s["name"].lower():
            return s

    click.echo(f"Session '{session}' not found.", err=True)
    click.echo(format_session_list(sessions), err=True)
    sys.exit(1)


# Shared options
_path_option = click.option("--path", "-p", default=None, help="Path to USB or master.db")
_session_arg = click.argument("session", required=False)


@click.group()
@click.version_option(version="0.1.0")
@click.option("--source", "-s", "source_type",
              type=click.Choice(["usb", "local"]), default="usb",
              help="Data source: usb (default) or local (rekordbox 6/7)")
@click.pass_context
def main(ctx, source_type):
    """rekord2spotify — export rekordbox history as tracklists or Spotify playlists.

    \b
    USB mode (plug in your drive):
      rekord2spotify show
      rekord2spotify export
      rekord2spotify playlist

    \b
    Rekordbox 6/7 local database:
      rekord2spotify --source local show
      rekord2spotify --source local export
      rekord2spotify --source local playlist
    """
    ctx.ensure_object(dict)
    ctx.obj["source_type"] = source_type


@main.command()
@_path_option
@click.pass_context
def show(ctx, path):
    """Show all history sessions."""
    sessions = _load_sessions(ctx.obj["source_type"], path)

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
@click.pass_context
def export(ctx, path, session, details, output):
    """Export a session as a text tracklist.

    SESSION: number (1 = first), name, or omit for latest.

    \b
    Examples:
      rekord2spotify export
      rekord2spotify export 2
      rekord2spotify export -d
      rekord2spotify export -o my_set.txt
    """
    sessions = _load_sessions(ctx.obj["source_type"], path)
    session_data = _resolve_session(sessions, session)
    text = format_tracklist(session_data, include_details=details)

    if output:
        Path(output).write_text(text + "\n")
        click.echo(f"Saved to {output}")
    else:
        click.echo(text)


@main.command()
@_path_option
@_session_arg
@click.option("--name", "-n", default=None, help="Playlist name")
@click.option("--dry-run", is_flag=True, help="Search but don't create playlist")
@click.pass_context
def playlist(ctx, path, session, name, dry_run):
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
    sessions = _load_sessions(ctx.obj["source_type"], path)
    session_data = _resolve_session(sessions, session)

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
