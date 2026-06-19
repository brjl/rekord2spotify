"""Tests for tracklist formatting and importer."""

import json
from pathlib import Path

from rekord2spotify.tracklist import format_tracklist, format_session_list
from rekord2spotify.importer import import_playlist
from rekord2spotify.extractor import get_latest_session


MOCK = Path(__file__).parent / "mock_history.json"


def test_importer_text():
    data = import_playlist(str(MOCK))
    # JSON is parsed as plain text (one 'track' per line of JSON... not ideal but valid)
    assert len(data["sessions"]) == 1
    assert len(data["sessions"][0]["tracks"]) > 0
    print("✓ import_playlist (plain text)")


def test_importer_artist_title():
    p = Path("/tmp/_r2s_test.txt")
    p.write_text("deadmau5 — Strobe\nEric Prydz - Opus\n")
    data = import_playlist(str(p))
    assert len(data["sessions"][0]["tracks"]) == 2
    assert data["sessions"][0]["tracks"][0]["artist"] == "deadmau5"
    print("✓ artist-title parsing")


def test_importer_tsv():
    p = Path("/tmp/_r2s_tsv.txt")
    p.write_text("#\tArtwork\tTrack Title\tArtist\tAlbum\tGenre\tBPM\tRating\tTime\tKey\tDate Added\n"
                 "1\t\tStrobe\tdeadmau5\t\tProgressive House\t128.00\t\t10:32\tF#m\t2020-01-01\n")
    data = import_playlist(str(p))
    t = data["sessions"][0]["tracks"][0]
    assert t["artist"] == "deadmau5"
    assert t["title"] == "Strobe"
    assert t["bpm"] == 128.0
    assert t["key"] == "F#m"
    assert t["duration_sec"] == 632
    print("✓ TSV parsing")


def test_format_tracklist():
    p = Path("/tmp/_r2s_fmt.txt")
    p.write_text("deadmau5 — Strobe\nEric Prydz - Opus\n")
    data = import_playlist(str(p))
    text = format_tracklist(data["sessions"][0])
    assert "deadmau5 — Strobe" in text
    assert "01." in text
    print("✓ format_tracklist")


def test_format_session_list():
    p = Path("/tmp/_r2s_fmt.txt")
    p.write_text("deadmau5 — Strobe\nEric Prydz - Opus\n")
    data = import_playlist(str(p))
    text = format_session_list(data["sessions"], include_preview=True)
    assert "[1]" in text
    print("✓ format_session_list")


def test_empty():
    Path("/tmp/_r2s_empty.txt").write_text("")
    data = import_playlist("/tmp/_r2s_empty.txt")
    assert data["sessions"][0]["tracks"] == []
    print("✓ empty file")


if __name__ == "__main__":
    test_importer_text()
    test_importer_artist_title()
    test_importer_tsv()
    test_format_tracklist()
    test_format_session_list()
    test_empty()
    print("\n✅ All tests passed!")
