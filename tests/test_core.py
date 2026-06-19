"""Tests for tracklist formatting and extractor parsing."""

import json
import sys
from pathlib import Path

# Add parent to path for test imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from rekord2spotify.extractor import list_sessions, get_latest_session, get_session_by_name
from rekord2spotify.tracklist import format_tracklist, format_session_summary


def load_mock():
    """Load the mock history JSON fixture."""
    mock_path = Path(__file__).parent / "mock_history.json"
    with open(mock_path) as f:
        return json.load(f)


def test_list_sessions():
    data = load_mock()
    sessions = list_sessions(data)
    assert len(sessions) == 2
    assert sessions[0] == ("HISTORY 001", 3)
    assert sessions[1] == ("HISTORY 002", 2)
    print("✓ list_sessions")


def test_get_latest_session():
    data = load_mock()
    session = get_latest_session(data)
    assert session is not None
    assert session["name"] == "HISTORY 002"
    assert len(session["tracks"]) == 2
    print("✓ get_latest_session")


def test_get_session_by_name():
    data = load_mock()
    session = get_session_by_name(data, "HISTORY 001")
    assert session is not None
    assert session["name"] == "HISTORY 001"
    assert len(session["tracks"]) == 3
    assert get_session_by_name(data, "NONEXISTENT") is None
    print("✓ get_session_by_name")


def test_format_session_summary():
    sessions = [("HISTORY 001", 3), ("HISTORY 002", 2)]
    text = format_session_summary(sessions)
    assert "HISTORY 001" in text
    assert "3 tracks" in text
    assert "HISTORY 002" in text
    assert "2 tracks" in text
    print("✓ format_session_summary")

    # Empty case
    assert "No history" in format_session_summary([])


def test_format_tracklist():
    data = load_mock()
    session = data["sessions"][0]

    text = format_tracklist(session)
    assert "HISTORY 001" in text
    assert "deadmau5 — Strobe" in text
    assert "Eric Prydz — Opus" in text
    assert "01. " in text
    assert "02. " in text
    assert "03. " in text
    print("✓ format_tracklist (basic)")

    # With details
    text_detail = format_tracklist(session, include_details=True)
    assert "128.0 BPM" in text_detail
    assert "F#m" in text_detail
    assert "10:32" in text_detail  # 632 sec = 10:32
    print("✓ format_tracklist (with details)")


def test_empty_session():
    empty = {"sessions": []}
    assert list_sessions(empty) == []
    assert get_latest_session(empty) is None
    print("✓ empty data handling")


def test_track_field_access():
    """Verify track fields are accessible with all expected keys."""
    data = load_mock()
    track = data["sessions"][0]["tracks"][0]

    # These are the fields our Rust extractor emits
    assert "position" in track
    assert "track" in track
    t = track["track"]
    assert "title" in t
    assert "artist" in t
    assert "bpm" in t
    assert "key" in t
    assert "isrc" in t
    assert "play_count" in t
    assert "album" in t

    # Fields that can be null
    assert t["isrc"] is not None or True  # can be null
    print("✓ track field structure")


if __name__ == "__main__":
    test_list_sessions()
    test_get_latest_session()
    test_get_session_by_name()
    test_format_session_summary()
    test_format_tracklist()
    test_empty_session()
    test_track_field_access()
    print("\n✅ All tests passed!")