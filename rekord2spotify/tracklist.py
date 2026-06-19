"""Text tracklist formatting."""

from typing import Optional


def format_tracklist(session: dict, include_details: bool = False) -> str:
    """Format a history session as a readable text tracklist.

    Args:
        session: Dict with 'name' and 'tracks' keys
        include_details: Include BPM, key, duration if True

    Returns:
        Formatted multi-line string
    """
    lines = [f"{session['name']}", "=" * len(session["name"]), ""]

    for i, entry in enumerate(session.get("tracks", []), 1):
        track = entry.get("track", {})
        title = track.get("title", "Unknown Track")
        artist = track.get("artist", "Unknown Artist")

        line = f"{i:02d}. {artist} — {title}"

        if include_details:
            details = []
            if track.get("bpm"):
                details.append(f"{track['bpm']:.1f} BPM")
            if track.get("key"):
                details.append(track["key"])
            if track.get("duration_sec"):
                m, s = divmod(track["duration_sec"], 60)
                details.append(f"{m}:{s:02d}")
            if details:
                line += f"  [{', '.join(details)}]"

        lines.append(line)

    return "\n".join(lines)


def format_session_summary(sessions: list) -> str:
    """Format a summary of all history sessions.

    Args:
        sessions: List of (name, track_count) tuples

    Returns:
        Formatted string listing all sessions
    """
    if not sessions:
        return "No history sessions found."

    lines = ["History Sessions:", "=" * 17, ""]
    for name, count in sessions:
        lines.append(f"  {name} — {count} tracks")
    return "\n".join(lines)