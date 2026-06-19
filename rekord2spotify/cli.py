"""rekord2spotify — export rekordbox USB history as tracklists or Spotify playlists."""

import os
import sys
from pathlib import Path

import questionary

from .extractor import (
    extract_history,
    get_latest_session,
    find_usb_drives,
)
from .importer import import_playlist
from .tracklist import format_tracklist, format_session_list


def main():
    """Interactive entry point."""
    print()
    questionary.print(" rekord2spotify", style="bold")
    print(" ──────────────")
    print()

    # Step 1: Where's the history?
    sources = _build_source_list()
    choice = questionary.select("Where's your history?", choices=sources).ask()
    if choice is None:
        return

    # Step 2: Load sessions
    sessions = _load_from_choice(choice)

    if not sessions:
        questionary.print("No history sessions found.", style="bold red")
        return

    # Step 3: Pick session(s)
    picked = _pick_sessions(sessions)
    if not picked:
        return

    # Step 4: What to do?
    _handle_output(picked)


def _build_source_list():
    """Build list of available sources."""
    sources = []

    usb = find_usb_drives()
    for drive in usb:
        name = Path(drive).name
        sources.append(questionary.Choice(
            title=f"💾 USB drive: {name} ({drive})",
            value=("usb", drive)
        ))

    if not usb:
        sources.append(questionary.Choice(
            title="💾 USB drive (none detected — plug one in)",
            value=("usb_none", None),
            disabled="No USB drives found"
        ))

    sources.append(questionary.Choice(
        title="🖥  Rekordbox 5 on this computer (export a history file first)",
        value=("rekordbox5", None)
    ))

    sources.append(questionary.Choice(
        title="📁 Import from file (text, M3U, or Rekordbox export)",
        value=("file", None)
    ))

    return sources


def _load_from_choice(choice):
    """Load sessions from the chosen source."""
    source_type, path = choice

    if source_type == "usb":
        questionary.print(f"\nReading {path} ...", style="dim")
        data = extract_history(path)
        return data.get("sessions", [])

    elif source_type == "usb_none":
        questionary.print("No USB drive found.", style="bold red")
        return []

    elif source_type == "rekordbox5":
        questionary.print("\nRekordbox 5 stores history inside the app.")
        questionary.print("You need to export it first:\n")
        questionary.print("  In rekordbox: right-click a history playlist")
        questionary.print("  → Export Playlist → choose text format")
        questionary.print("  (Use the 'Export for KUVO' option for best results)\n")

        # Try to find recent exports
        recent = _find_recent_exports()
        choices = []
        for f in recent:
            choices.append(questionary.Choice(
                title=f"📄 {f.name} ({_time_ago(f)})",
                value=str(f)
            ))
        choices.append(questionary.Choice(
            title="📂 Choose another file...",
            value="__browse__"
        ))

        filepath = questionary.select(
            "Found these recent exports.\nPick one or choose another file:",
            choices=choices
        ).ask()

        if filepath is None:
            return []
        if filepath == "__browse__":
            filepath = questionary.path(
                "Path to exported file:",
                only_directories=False,
            ).ask()
            if not filepath:
                return []

        questionary.print(f"\nImporting {Path(filepath).name} ...", style="dim")
        data = import_playlist(filepath)
        return data.get("sessions", [])

    elif source_type == "file":
        filepath = questionary.path(
            "Path to file (text, M3U, or Rekordbox export):",
            only_directories=False,
        ).ask()
        if not filepath:
            return []

        questionary.print(f"\nImporting {Path(filepath).name} ...", style="dim")
        data = import_playlist(filepath)
        return data.get("sessions", [])

    return []


def _find_recent_exports():
    """Find recently modified rekordbox export files."""
    recent = []
    dirs = [Path.home() / "Documents", Path.home() / "Desktop", Path.home() / "Downloads"]
    for d in dirs:
        if not d.exists():
            continue
        try:
            entries = sorted(d.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        except (PermissionError, OSError):
            continue
        for f in entries:
            if f.suffix.lower() in (".txt", ".m3u", ".m3u8", ".csv") and f.stat().st_size > 100:
                # Quick check if it looks like a playlist
                try:
                    first_bytes = f.read_bytes()[:50]
                    if b"#EXTM3U" in first_bytes or b"Track Title" in first_bytes or b"Artist" in first_bytes:
                        recent.append(f)
                except Exception:
                    pass
            if len(recent) >= 5:
                break
        if len(recent) >= 5:
            break
    return recent


def _time_ago(path):
    """Human-readable time ago."""
    import time
    diff = time.time() - path.stat().st_mtime
    if diff < 60:
        return "just now"
    if diff < 3600:
        return f"{int(diff/60)}m ago"
    if diff < 86400:
        return f"{int(diff/3600)}h ago"
    return f"{int(diff/86400)}d ago"


def _pick_sessions(sessions):
    """Let user pick one session, all, or latest."""
    print()
    questionary.print(f"{len(sessions)} session(s)\n", style="bold")
    print(format_session_list(sessions, include_preview=True))
    print()

    choices = [
        questionary.Choice(title="Latest session", value="latest"),
        questionary.Choice(title="All sessions", value="all"),
    ]
    for i, s in enumerate(sessions, 1):
        choices.append(questionary.Choice(
            title=f"  {s['name']} — {len(s['tracks'])} tracks",
            value=i - 1
        ))

    choice = questionary.select("Pick a session:", choices=choices).ask()
    if choice is None:
        return []

    if choice == "latest":
        s = get_latest_session({"sessions": sessions})
        return [s] if s else []
    elif choice == "all":
        return sessions
    else:
        return [sessions[choice]]


def _handle_output(sessions):
    """Ask user what to do with selected sessions."""
    total_tracks = sum(len(s["tracks"]) for s in sessions)
    if len(sessions) == 1:
        label = f"{sessions[0]['name']} — {total_tracks} tracks"
    else:
        label = f"{len(sessions)} sessions — {total_tracks} tracks"

    print()
    questionary.print(label, style="bold")
    print()

    action = questionary.select(
        "What do you want?",
        choices=[
            questionary.Choice(title="📋 Print tracklist", value="print"),
            questionary.Choice(title="💾 Save to file", value="save"),
            questionary.Choice(title="🟢 Create Spotify playlist(s)", value="spotify"),
            questionary.Choice(title="All three", value="all"),
        ]
    ).ask()

    if action is None:
        return

    do_print = action in ("print", "all")
    do_save = action in ("save", "all")
    do_spotify = action in ("spotify", "all")

    # Spotify check once
    sp = None
    if do_spotify:
        try:
            from .spotify import _get_spotify_client, search_tracks_batch, create_spotify_playlist, _check_credentials
            if not _check_credentials():
                questionary.print("\nSpotify not set up.", style="bold red")
                questionary.print("Create a .env file with SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET")
                questionary.print("Get them at: https://developer.spotify.com/dashboard\n")
                return
            sp = _get_spotify_client()
        except Exception as e:
            questionary.print(f"\nSpotify error: {e}", style="bold red")
            return

    for session in sessions:
        name = session["name"]
        tracks = session["tracks"]

        if do_print:
            print()
            print(format_tracklist(session, include_details=True))

        if do_save:
            filename = f"{name}.txt".replace(" ", "_")
            Path(filename).write_text(format_tracklist(session, include_details=True) + "\n")
            questionary.print(f"  Saved {filename}")

        if do_spotify and sp:
            questionary.print(f"\n  Searching Spotify for {name} ...", style="dim")
            matches = search_tracks_batch(sp, tracks)
            if not matches:
                questionary.print(f"  No tracks matched on Spotify.", style="bold red")
                continue

            print()
            questionary.print(f"  Matched {len(matches)}/{len(tracks)} tracks")
            url = create_spotify_playlist(sp, name, matches, f"Exported from {name} via rekord2spotify")
            questionary.print(f"  {url}", style="bold green")


if __name__ == "__main__":
    main()
