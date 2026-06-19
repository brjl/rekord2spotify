# rekord2spotify

Export rekordbox USB history as text tracklists or Spotify playlists.

Reads `export.pdb` directly from your rekordbox-exported USB drive — no need to open the rekordbox app.

## How it works

```
USB Stick (/Volumes/MY_USB)
  └── PIONEER/rekordbox/export.pdb
         │
         ▼
  [rekord-extract]  Rust binary, parses PDB → JSON
         │
         ▼
  [rekord2spotify]  Python CLI
         │
         ├── list     Show all history sessions
         ├── export   Text tracklist output
         └── playlist Create Spotify playlist
```

## Quick Start

### 1. Build the Rust extractor

```bash
make build
# Or: cd extractor && cargo build --release
```

### 2. Install the Python CLI

```bash
make install
source .venv/bin/activate
```

### 3. List sessions on your USB

```bash
rekord2spotify list /Volumes/USB_DRIVE
```

### 4. Export a session as text

```bash
rekord2spotify export /Volumes/USB_DRIVE       # latest session
rekord2spotify export /Volumes/USB_DRIVE -s "HISTORY 001"
rekord2spotify export /Volumes/USB_DRIVE -d     # include BPM, key, duration
rekord2spotify export /Volumes/USB_DRIVE -o my_set.txt
```

### 5. Create a Spotify playlist

First, set up Spotify API credentials:

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create an app
3. Go to Settings → Redirect URIs → Add `http://localhost:8888/callback`
4. Create a `.env` file in your project directory:

```
SPOTIPY_CLIENT_ID=your-client-id-here
SPOTIPY_CLIENT_SECRET=your-client-secret-here
SPOTIPY_REDIRECT_URI=http://localhost:8888/callback
```

Then:

```bash
rekord2spotify playlist /Volumes/USB_DRIVE
rekord2spotify playlist /Volumes/USB_DRIVE -s "HISTORY 002" -n "My Amazing Set"
rekord2spotify playlist /Volumes/USB_DRIVE --dry-run   # check matches first
```

On first run, it'll open a browser for Spotify OAuth login. Credentials are cached at `~/.rekord2spotify_token`.

## Spotify Matching

The tool tries three strategies to find tracks on Spotify:

1. **ISRC match** — exact match by International Standard Recording Code (most reliable, if rekordbox has it)
2. **Artist + Title exact** — precise `artist:"Name" track:"Title"` search
3. **Fuzzy match** — general search with substring verification

If a duration is available, it also verifies the match is within ±10 seconds.

Unmatched tracks are reported so you can add them manually.

## Requirements

- **Rust** (for building the extractor)
- **Python 3.8+** with pip
- **Spotify Developer account** (free, for playlist creation)
- **Rekordbox-exported USB drive** with playback history

## Project Structure

```
rekord2spotify/
├── extractor/              # Rust binary (PDB → JSON)
│   ├── Cargo.toml
│   └── src/main.rs
├── rekordcrate-local/      # Patched rekordcrate (pub fields)
├── rekord2spotify/         # Python package
│   ├── cli.py              # Click CLI (list, export, playlist)
│   ├── extractor.py        # Calls Rust binary, parses JSON
│   ├── spotify.py          # Spotify search + playlist creation
│   └── tracklist.py        # Text formatting
├── tests/                  # Test fixtures and tests
├── pyproject.toml
├── setup.py
└── Makefile
```

## License

MIT