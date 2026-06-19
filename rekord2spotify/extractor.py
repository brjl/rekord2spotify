"""Calls the Rust rekord-extract binary and returns parsed JSON."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional, List


def find_extractor_binary() -> str:
    """Find the rekord-extract binary."""
    # Development layout (next to this package)
    dev_path = Path(__file__).parent.parent / "extractor" / "target" / "release" / "rekord-extract"
    if dev_path.exists():
        return str(dev_path)

    # Installed via cargo or in PATH
    which = shutil.which("rekord-extract")
    if which:
        return which

    raise FileNotFoundError(
        "Could not find rekord-extract binary.\n"
        "Build it with: cd extractor && cargo build --release"
    )


def extract_history(path: str) -> dict:
    """Run rekord-extract and return parsed JSON.

    Args:
        path: USB mount point or direct path to export.pdb

    Returns:
        dict with 'sessions' key containing history data
    """
    result = subprocess.run(
        [find_extractor_binary(), path],
        capture_output=True, text=True, timeout=60,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Extractor failed (exit {result.returncode}):\n{result.stderr}")

    output = result.stdout.strip()
    if not output:
        raise RuntimeError("Extractor produced no output")

    return json.loads(output)


def get_latest_session(data: dict) -> Optional[dict]:
    """Get the most recent history session."""
    sessions = data.get("sessions", [])
    return sessions[-1] if sessions else None


def find_usb_drives() -> List[str]:
    """Find mounted USB drives containing PIONEER/rekordbox/export.pdb."""
    volumes = Path("/Volumes")
    if not volumes.exists():
        return []

    skip = {"Macintosh HD", "Recovery", "Preboot", "VM"}
    return [
        str(entry)
        for entry in sorted(volumes.iterdir())
        if entry.is_dir()
        and entry.name not in skip
        and (entry / "PIONEER" / "rekordbox" / "export.pdb").exists()
    ]
