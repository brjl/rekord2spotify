"""rekord2spotify — export rekordbox USB history as tracklists or Spotify playlists."""

import subprocess
import time
from pathlib import Path

import questionary

from .extractor import extract_history, get_latest_session, find_usb_drives
from .importer import import_playlist
from .tracklist import format_tracklist, format_session_list


def main():
    """Interactive entry point."""
    print()
    questionary.print(" rekord2spotify", style="bold")
    print(" ──────────────")
    print()

    choice = questionary.select(
        "Where's your history?",
        choices=_build_sources()
    ).ask()
    if not choice:
        return

    sessions = _load(choice)
    if not sessions:
        questionary.print("No history sessions found.", style="bold red")
        return

    picked = _pick(sessions)
    if not picked:
        return

    _output(picked)


def _build_sources():
    sources = []
    usb = find_usb_drives()
    for d in usb:
        sources.append(questionary.Choice(
            title=f"💾 USB: {Path(d).name} ({d})",
            value=("usb", d)
        ))
    if not usb:
        sources.append(questionary.Choice(
            title="💾 USB (none detected)",
            value=("usb_none", None),
            disabled="No USB drives found"
        ))
    sources.append(questionary.Choice(
        title="🖥  Rekordbox 5 (export a history file first)",
        value=("r5", None)
    ))
    sources.append(questionary.Choice(
        title="📁 Import from file",
        value=("file", None)
    ))
    return sources


def _load(choice):
    source, path = choice

    if source == "usb":
        questionary.print(f"\nReading {path} ...", style="dim")
        return extract_history(path).get("sessions", [])

    if source == "usb_none":
        return []

    if source == "r5":
        return _load_r5()

    if source == "file":
        return _load_file()

    return []


def _load_r5():
    questionary.print("\nRekordbox 5 stores history inside the app.")
    questionary.print("You need to export it first:\n")
    questionary.print("  In rekordbox: right-click any history playlist")
    questionary.print("  → Export Playlist → choose text format")
    questionary.print("  (Use the 'Export for KUVO' option for best results)\n")

    choices = []
    for f in _find_history_exports():
        choices.append(questionary.Choice(
            title=f"📄 {f.name} ({_time_ago(f)})",
            value=str(f)
        ))
    choices.append(questionary.Choice(
        title="📂 Choose another file or paste path...",
        value="__browse__"
    ))

    filepath = questionary.select("Pick an export file:", choices=choices).ask()
    if not filepath:
        return []
    if filepath == "__browse__":
        filepath = questionary.path("Path to exported file:", only_directories=False).ask()
        if not filepath:
            return []

    return _import_file(filepath)


def _load_file():
    filepath = questionary.path(
        "Path to file (text, M3U, or Rekordbox export):",
        only_directories=False,
    ).ask()
    if not filepath:
        return []
    return _import_file(filepath)


def _import_file(filepath):
    questionary.print(f"\nImporting {Path(filepath).name} ...", style="dim")
    return import_playlist(filepath).get("sessions", [])


def _find_history_exports():
    """Find 'HISTORY*.txt' files via Spotlight (bypasses macOS folder permissions)."""
    try:
        result = subprocess.run(
            ["mdfind", "kMDItemDisplayName == 'HISTORY*' && kMDItemContentType == 'public.plain-text'"],
            capture_output=True, text=True, timeout=5
        )
        paths = [Path(p.strip()) for p in result.stdout.strip().split("\n") if p.strip()]
        paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return [p for p in paths if p.exists() and p.stat().st_size > 100][:8]
    except Exception:
        return []


def _time_ago(path):
    diff = time.time() - path.stat().st_mtime
    if diff < 60:       return "just now"
    if diff < 3600:     return f"{int(diff/60)}m ago"
    if diff < 86400:    return f"{int(diff/3600)}h ago"
    return f"{int(diff/86400)}d ago"


def _pick(sessions):
    print()
    questionary.print(f"{len(sessions)} session(s)\n", style="bold")
    print(format_session_list(sessions, include_preview=True))
    print()

    choices = [
        questionary.Choice("Latest", "latest"),
        questionary.Choice(f"All ({len(sessions)})", "all"),
    ]
    for i, s in enumerate(sessions, 1):
        choices.append(questionary.Choice(
            f"  {s['name']} — {len(s['tracks'])} tracks",
            i - 1
        ))

    choice = questionary.select("Pick a session:", choices=choices).ask()
    if choice is None:
        return []
    if choice == "latest":
        s = get_latest_session({"sessions": sessions})
        return [s] if s else []
    if choice == "all":
        return sessions
    return [sessions[choice]]


def _output(sessions):
    total = sum(len(s["tracks"]) for s in sessions)
    label = f"{sessions[0]['name']} — {total} tracks" if len(sessions) == 1 else f"{len(sessions)} sessions — {total} tracks"
    print()
    questionary.print(label, style="bold")
    print()

    action = questionary.select("What do you want?", choices=[
        questionary.Choice("📋 Print tracklist", "print"),
        questionary.Choice("💾 Save to file", "save"),
        questionary.Choice("🟢 Create Spotify playlist(s)", "spotify"),
        questionary.Choice("All three", "all"),
    ]).ask()
    if not action:
        return

    do_print = action in ("print", "all")
    do_save = action in ("save", "all")
    do_spotify = action in ("spotify", "all")

    sp = None
    if do_spotify:
        from .spotify import _get_spotify_client, search_tracks_batch, create_spotify_playlist, _check_credentials
        if not _check_credentials():
            questionary.print("\nSpotify not set up.", style="bold red")
            questionary.print("Create .env with SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET")
            questionary.print("Get them at: https://developer.spotify.com/dashboard\n")
            return
        sp = _get_spotify_client()

    for session in sessions:
        name, tracks = session["name"], session["tracks"]

        if do_print:
            print(f"\n{format_tracklist(session, include_details=True)}")

        if do_save:
            filename = f"{name}.txt".replace(" ", "_")
            Path(filename).write_text(format_tracklist(session, include_details=True) + "\n")
            questionary.print(f"  Saved {filename}")

        if sp:
            questionary.print(f"\n  Searching Spotify for {name} ...", style="dim")
            matches = search_tracks_batch(sp, tracks)
            if not matches:
                questionary.print("  No tracks matched.", style="bold red")
                continue
            questionary.print(f"  Matched {len(matches)}/{len(tracks)}")
            url = create_spotify_playlist(sp, name, matches, f"Exported from {name}")
            questionary.print(f"  {url}", style="bold green")


if __name__ == "__main__":
    main()
