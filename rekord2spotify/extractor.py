"""Calls the Rust rekord-extract binary and returns parsed JSON."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


def find_extractor_binary() -> str:
    """Find the rekord-extract binary. Searches common locations."""
    # Check next to this package (development layout)
    dev_path = Path(__file__).parent.parent / "extractor" / "target" / "release" / "rekord-extract"
    if dev_path.exists():
        return str(dev_path)

    # Check Cargo install path
    cargo_bin = Path.home() / ".cargo" / "bin" / "rekord-extract"
    if cargo_bin.exists():
        return str(cargo_bin)

    # Check PATH
    for d in os.environ.get("PATH", "").split(os.pathsep):
        p = Path(d) / "rekord-extract"
        if p.exists():
            return str(p)

    raise FileNotFoundError(
        "Could not find rekord-extract binary.\n"
        "Build it with: cd extractor && cargo build --release"
    )


def extract_history(path: str) -> dict:
    """Run rekord-extract on the given path and return parsed JSON.

    Args:
        path: USB mount point or direct path to export.pdb

    Returns:
        dict with 'sessions' key containing history data
    """
    binary = find_extractor_binary()

    result = subprocess.run(
        [binary, path],
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        # Stderr has progress info, stdout has JSON
        raise RuntimeError(
            f"Extractor failed (exit {result.returncode}):\n{result.stderr}"
        )

    # The extractor writes progress to stderr, JSON to stdout
    output = result.stdout.strip()
    if not output:
        raise RuntimeError("Extractor produced no output")

    return json.loads(output)


def get_latest_session(data: dict) -> Optional[dict]:
    """Get the most recent history session."""
    sessions = data.get("sessions", [])
    if not sessions:
        return None
    # Sessions are sorted by name, last is most recent
    return sessions[-1]


def get_session_by_name(data: dict, name: str) -> Optional[dict]:
    """Get a specific history session by name (e.g. 'HISTORY 001')."""
    for session in data.get("sessions", []):
        if session["name"] == name:
            return session
    return None


def list_sessions(data: dict) -> list:
    """Return list of (name, track_count) tuples."""
    return [(s["name"], len(s["tracks"])) for s in data.get("sessions", [])]