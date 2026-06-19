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
        title = entry.get("title", "Unknown Track")
        artist = entry.get("artist", "Unknown Artist")

        line = f"{i:02d}. {artist} — {title}"

        if include_details:
            details = []
            if entry.get("bpm"):
                details.append(f"{entry['bpm']:.1f} BPM")
            if entry.get("key"):
                details.append(entry["key"])
            if entry.get("duration_sec"):
                m, s = divmod(entry["duration_sec"], 60)
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


def format_session_list(sessions: list, include_preview: bool = False) -> str:
    """Format a numbered list of sessions, optionally with track previews.

    Args:
        sessions: List of session dicts (from extractor JSON)
        include_preview: Show first and last track of each session

    Returns:
        Formatted string
    """
    lines = []
    for i, session in enumerate(sessions, 1):
        name = session["name"]
        tracks = session.get("tracks", [])
        count = len(tracks)

        if include_preview and tracks:
            first = tracks[0]
            last = tracks[-1]
            first_str = f"{first.get('artist', '?')} — {first.get('title', '?')}"
            last_str = f"{last.get('artist', '?')} — {last.get('title', '?')}"
            # Truncate long names
            if len(first_str) > 60:
                first_str = first_str[:57] + "..."
            if len(last_str) > 60:
                last_str = last_str[:57] + "..."
            lines.append(f"  [{i}] {name} — {count} tracks")
            lines.append(f"      {first_str}")
            lines.append(f"      {last_str}")
        else:
            lines.append(f"  [{i}] {name} — {count} tracks")

    return "\n".join(lines)