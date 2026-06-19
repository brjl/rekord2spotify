"""CLI for rekord2spotify."""

import sys
import click
from pathlib import Path

from .extractor import extract_history, list_sessions, get_latest_session
from .tracklist import format_tracklist, format_session_summary


@click.group()
@click.version_option(version="0.1.0")
def main():
    """Export rekordbox USB history as tracklists or Spotify playlists.

    Reads export.pdb directly from your rekordbox-exported USB drive.
    """
    pass


@main.command()
@click.argument("path", type=click.Path(exists=True))
def list(path):
    """List all history sessions found on a USB drive.

    PATH can be the USB mount point or direct path to export.pdb.
    """
    try:
        data = extract_history(path)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    sessions = list_sessions(data)
    click.echo(format_session_summary(sessions))


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--session", "-s", default="latest",
              help="Session name (e.g. 'HISTORY 001') or 'latest'")
@click.option("--details", "-d", is_flag=True,
              help="Include BPM, key, and duration")
@click.option("--output", "-o", type=click.Path(),
              help="Write to file instead of stdout")
def export(path, session, details, output):
    """Export a history session as a text tracklist.

    Example:
        rekord2spotify export /Volumes/USB_DRIVE
        rekord2spotify export /Volumes/USB_DRIVE -s "HISTORY 003" -d
    """
    try:
        data = extract_history(path)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if session == "latest":
        session_data = get_latest_session(data)
    else:
        from .extractor import get_session_by_name
        session_data = get_session_by_name(data, session)

    if not session_data:
        click.echo(f"Session '{session}' not found.", err=True)
        avail = [s["name"] for s in data.get("sessions", [])]
        if avail:
            click.echo(f"Available: {', '.join(avail)}", err=True)
        sys.exit(1)

    text = format_tracklist(session_data, include_details=details)

    if output:
        Path(output).write_text(text + "\n")
        click.echo(f"Tracklist written to {output}")
    else:
        click.echo(text)


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--session", "-s", default="latest",
              help="Session name (e.g. 'HISTORY 001') or 'latest'")
@click.option("--name", "-n", default=None,
              help="Name for the Spotify playlist (default: session name)")
@click.option("--dry-run", is_flag=True,
              help="Search tracks but don't create playlist")
def playlist(path, session, name, dry_run):
    """Create a Spotify playlist from a history session.

    Requires Spotify API credentials:
      SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET environment variables
      or a .env file in the current directory.

    Example:
        rekord2spotify playlist /Volumes/USB_DRIVE
        rekord2spotify playlist /Volumes/USB_DRIVE -s "HISTORY 002" -n "My Set"
        rekord2spotify playlist /Volumes/USB_DRIVE --dry-run
    """
    try:
        data = extract_history(path)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if session == "latest":
        session_data = get_latest_session(data)
    else:
        from .extractor import get_session_by_name
        session_data = get_session_by_name(data, session)

    if not session_data:
        click.echo(f"Session '{session}' not found.", err=True)
        avail = [s["name"] for s in data.get("sessions", [])]
        if avail:
            click.echo(f"Available: {', '.join(avail)}", err=True)
        sys.exit(1)

    tracks = session_data["tracks"]
    click.echo(f"Session: {session_data['name']} — {len(tracks)} tracks")
    click.echo()

    # Import Spotify module only when needed (so list/export work without creds)
    from .spotify import _get_spotify_client, search_tracks_batch, create_spotify_playlist

    try:
        sp = _get_spotify_client()
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    click.echo("Matching tracks to Spotify...")
    matches = search_tracks_batch(sp, tracks)

    click.echo()
    matched_count = len(matches)
    click.echo(f"Matched {matched_count}/{len(tracks)} tracks")

    unmatched = len(tracks) - matched_count
    if unmatched > 0:
        click.echo(f"⚠ {unmatched} track(s) could not be found on Spotify")

    if dry_run or matched_count == 0:
        if dry_run:
            click.echo("\nDry run — no playlist created.")
        return

    # Create playlist
    playlist_name = name or session_data["name"]
    description = f"Exported from {session_data['name']} via rekord2spotify"

    try:
        url = create_spotify_playlist(sp, playlist_name, matches, description)
        click.echo(f"\n✅ Playlist created: {url}")
    except Exception as e:
        click.echo(f"\nError creating playlist: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()