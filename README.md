# rekord2spotify

Interactive CLI to export rekordbox history as tracklists or Spotify playlists.

```
$ rekord2spotify

 rekord2spotify
 ---------------

? Where's your history?
  > 💾 USB: MY_USB (/Volumes/MY_USB)
    🖥  Rekordbox 6/7 on this computer (direct database read)
    📁 Import from file (text, M3U, or Rekordbox export)
```

## Sources

| Source | How |
|---|---|
| **Rekordbox 6/7** | Direct master.db access via `--source local`. No export needed. Reads your entire play history. |
| **rbxport** | Auto-detected. Works with rbxport-managed libraries. |
| **USB drive** | Plug in, auto-detected. Reads play history written by CDJs. |
| **Rekordbox 5** | Export a playlist in-app once (right-click → Export → text), then auto-found via Spotlight. |
| **Import file** | Any text, M3U, M3U8, CSV, or Rekordbox TSV export. |

## How master.db access works

The Rust extractor reads your encrypted rekordbox database directly — no in-app export needed.

1. Finds the rekordbox agent's `options.json` (rekordbox 6/7 use the same path on macOS)
2. Derives the SQLCipher passphrase via Blowfish decryption
3. Opens `master.db` and queries your full play history
4. Falls back to rbxport if no rekordbox library is found

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

**Rekordbox 6/7 users:** Nothing to do. Your history is read directly from the database.

**Rekordbox 5 users:** In rekordbox, right-click a history playlist → Export Playlist → text format (the KUVO option). Files are auto-detected by Spotlight.

## Spotify (requires Premium)

Create `.env` with credentials from https://developer.spotify.com/dashboard:

```
SPOTIPY_CLIENT_ID=your-id
SPOTIPY_CLIENT_SECRET=your-secret
```

Then pick "Create Spotify playlist" in the app. First run opens a browser for OAuth.

## Requirements

- Rust (to build the extractor)
- Python 3.8+
- Rekordbox 6/7, rbxport, or a USB export — or Rekordbox 5 exported text files
- Spotify Premium (for playlist creation only — printing and file export work without)

## Notes

- USB history is cleared when you sync with Rekordbox. Read it before syncing.
- Rekordbox 5 stores history locally in a proprietary format (`datafile.edb`) that has not been reverse-engineered. The in-app export is the workaround.
- Rekordbox 6/7 direct database access uses the same agent key derivation as rbxport — no third-party Python dependency needed.