# rekord2spotify

Interactive CLI to export rekordbox history as tracklists or Spotify playlists.

```
$ rekord2spotify

 rekord2spotify
 ──────────────

? Where's your history?
  > 💾 USB: MY_USB (/Volumes/MY_USB)
    🖥  Rekordbox 5 on this computer (export a history file first)
    📁 Import from file (text, M3U, or Rekordbox export)
```

## Sources

| Source | How |
|---|---|
| **USB drive** | Plug in, auto-detected. Reads play history written by CDJs |
| **Rekordbox 5** | Export a playlist in-app once (right-click → Export → text), then auto-found via Spotlight |
| **Rekordbox 6/7** | Direct database access via `--source local` (requires pyrekordbox) |
| **Import file** | Any text, M3U, M3U8, CSV, or Rekordbox TSV export |

## Install

```bash
git clone git@github.com:brjl/rekord2spotify.git
cd rekord2spotify

# Build Rust extractor
cd extractor && cargo build --release && cd ..

# Install Python CLI
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

Just run `rekord2spotify` — it walks you through everything.

**Rekordbox 5 users:** In rekordbox, right-click a history playlist → Export Playlist → text format (the KUVO option). Files are auto-detected by Spotlight. Only needed once per session you want to export.

## Spotify (requires Premium)

Create `.env` with credentials from https://developer.spotify.com/dashboard:

```
SPOTIPY_CLIENT_ID=your-id
SPOTIPY_CLIENT_SECRET=your-secret
```

Then pick "Create Spotify playlist" in the app. First run opens a browser for OAuth.

## Requirements

- Rust (to build the PDB extractor)
- Python 3.8+
- Rekordbox-exported USB drive, or Rekordbox 5 exported text files
- Spotify Premium (for playlist creation only — printing and file export work without)

## Notes

- USB history is cleared when you sync with Rekordbox. Read it before syncing.
- Rekordbox 5 stores history locally in a proprietary format (`datafile.edb`) that has not been reverse-engineered. The in-app export is the workaround.
- Rekordbox 6/7 direct database access is available if installed.