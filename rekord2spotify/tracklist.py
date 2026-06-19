"""Text tracklist formatting."""

def format_tracklist(session: dict, include_details: bool = False) -> str:
    """Format a history session as a readable text tracklist."""
    lines = [session["name"], "=" * len(session["name"]), ""]

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


def _truncate(s: str, n: int = 60) -> str:
    return s if len(s) <= n else s[:n-3] + "..."


def format_session_list(sessions: list, include_preview: bool = False) -> str:
    """Format a numbered list of sessions, optionally with track previews."""
    lines = []
    for i, session in enumerate(sessions, 1):
        name = session["name"]
        tracks = session.get("tracks", [])
        lines.append(f"  [{i}] {name} — {len(tracks)} tracks")

        if include_preview and tracks:
            f = tracks[0]
            l = tracks[-1]
            fa = f.get("artist", "?")
            ft = f.get("title", "?")
            la = l.get("artist", "?")
            lt = l.get("title", "?")
            lines.append(f"      {_truncate(fa + ' — ' + ft)}")
            lines.append(f"      {_truncate(la + ' — ' + lt)}")

    return "\n".join(lines)
