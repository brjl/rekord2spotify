use anyhow::{Context, Result};
use fallible_iterator::FallibleIterator;
use rekordcrate::device::DeviceExportLoader;
use rekordcrate::pdb::*;
use serde::Serialize;
use std::collections::HashMap;
use std::path::Path;

#[derive(Debug, Serialize)]
struct TrackInfo {
    title: String,
    artist: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    mix_name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    album: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    genre: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    key: Option<String>,
    bpm: Option<f64>,
    duration_sec: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    label: Option<String>,
    play_count: u16,
    #[serde(skip_serializing_if = "Option::is_none")]
    isrc: Option<String>,
}

#[derive(Debug, Serialize)]
struct HistoryTrack {
    position: u32,
    #[serde(flatten)]
    track: TrackInfo,
}

#[derive(Debug, Serialize)]
struct HistorySession {
    name: String,
    tracks: Vec<HistoryTrack>,
}

#[derive(Debug, Serialize)]
struct HistoryExport {
    sessions: Vec<HistorySession>,
}

fn main() -> Result<()> {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 2 {
        eprintln!("Usage: rekord-extract <path-to-USB-or-export.pdb>");
        eprintln!("  e.g.  rekord-extract /Volumes/USB_DRIVE");
        eprintln!("  e.g.  rekord-extract /Volumes/USB_DRIVE/PIONEER/rekordbox/export.pdb");
        std::process::exit(1);
    }

    let input_path = Path::new(&args[1]);

    // Auto-detect: if given a directory, append PIONEER/rekordbox/export.pdb
    let pdb_path = if input_path.is_dir() {
        input_path.join("PIONEER").join("rekordbox").join("export.pdb")
    } else {
        input_path.to_path_buf()
    };

    if !pdb_path.exists() {
        anyhow::bail!(
            "export.pdb not found at {}. Is this a rekordbox-exported USB drive?",
            pdb_path.display()
        );
    }

    eprintln!("Reading {} ...", pdb_path.display());

    let export = extract_history(&pdb_path).context("Failed to extract history")?;
    let json = serde_json::to_string_pretty(&export)?;
    println!("{}", json);
    Ok(())
}

fn extract_history(pdb_path: &Path) -> Result<HistoryExport> {
    // DeviceExportLoader expects the USB root (parent of PIONEER dir)
    // If we got a PDB file path, work backwards
    let device_root = pdb_path
        .parent()                    // rekordbox/
        .and_then(|p| p.parent())   // PIONEER/
        .and_then(|p| p.parent())   // device root
        .context("Could not determine device root from PDB path. Expected .../PIONEER/rekordbox/export.pdb")?;

    let loader = DeviceExportLoader::new(device_root.to_path_buf());
    let mut db = loader.open_pdb_non_persistent()?;

    // Collect all tables (each iter_rows borrows db mutably, so we clone out)
    eprintln!("  Loading tracks...");
    let raw_tracks: Vec<Track> = db
        .iter_rows::<Track>()?
        .map(|t| Ok(t.clone()))
        .collect()?;

    eprintln!("  Loading artists...");
    let raw_artists: Vec<Artist> = db
        .iter_rows::<Artist>()?
        .map(|a| Ok(a.clone()))
        .collect()?;

    eprintln!("  Loading genres...");
    let raw_genres: Vec<Genre> = db.iter_rows::<Genre>()?.map(|g| Ok(g.clone())).collect()?;

    eprintln!("  Loading labels...");
    let raw_labels: Vec<Label> = db.iter_rows::<Label>()?.map(|l| Ok(l.clone())).collect()?;

    eprintln!("  Loading keys...");
    let raw_keys: Vec<Key> = db.iter_rows::<Key>()?.map(|k| Ok(k.clone())).collect()?;

    eprintln!("  Loading albums...");
    let raw_albums: Vec<Album> = db
        .iter_rows::<Album>()?
        .map(|a| Ok(a.clone()))
        .collect()?;

    eprintln!("  Loading history playlists...");
    let history_playlists: Vec<HistoryPlaylist> = db
        .iter_rows::<HistoryPlaylist>()?
        .map(|h| Ok(h.clone()))
        .collect()?;

    eprintln!("  Loading history entries...");
    let history_entries: Vec<HistoryEntry> = db
        .iter_rows::<HistoryEntry>()?
        .map(|h| Ok(h.clone()))
        .collect()?;

    eprintln!(
        "  Found: {} tracks, {} artists, {} genres, {} labels, {} keys, {} albums",
        raw_tracks.len(),
        raw_artists.len(),
        raw_genres.len(),
        raw_labels.len(),
        raw_keys.len(),
        raw_albums.len(),
    );
    eprintln!(
        "  History: {} sessions, {} total entries",
        history_playlists.len(),
        history_entries.len(),
    );

    if history_playlists.is_empty() {
        eprintln!("  No history sessions found on this device.");
        return Ok(HistoryExport { sessions: vec![] });
    }

    // Build lookup maps
    let artist_map: HashMap<u32, String> = raw_artists
        .iter()
        .filter_map(|a| {
            let name = a.offsets.inner.name.to_string();
            if name.is_empty() { None } else { Some((a.id.0, name)) }
        })
        .collect();

    let genre_map: HashMap<u32, String> = raw_genres
        .iter()
        .map(|g| (g.id.0, g.name.to_string()))
        .collect();

    let label_map: HashMap<u32, String> = raw_labels
        .iter()
        .map(|l| (l.id.0, l.name.to_string()))
        .collect();

    let key_map: HashMap<u32, String> = raw_keys
        .iter()
        .map(|k| (k.id.0, k.name.to_string()))
        .collect();

    let album_map: HashMap<u32, String> = raw_albums
        .iter()
        .filter_map(|a| {
            let name = a.offsets.inner.name.to_string();
            if name.is_empty() { None } else { Some((a.id.0, name)) }
        })
        .collect();

    // Build track lookup
    let track_map: HashMap<u32, TrackInfo> = raw_tracks
        .iter()
        .map(|t| {
            let title = t.offsets.inner.title.to_string();
            let artist_name = artist_map
                .get(&t.artist_id.0)
                .cloned()
                .unwrap_or_else(|| "Unknown Artist".to_string());
            let mix_name = {
                let s = t.offsets.inner.mix_name.to_string();
                if s.is_empty() { None } else { Some(s) }
            };
            let album = album_map.get(&t.album_id.0).cloned();
            let genre = genre_map.get(&t.genre_id.0).cloned();
            let key = key_map.get(&t.key_id.0).cloned();
            let label = label_map.get(&t.label_id.0).cloned();
            let bpm = if t.tempo > 0 {
                Some(t.tempo as f64 / 100.0)
            } else {
                None
            };
            let isrc = {
                let s = t.offsets.inner.isrc.to_string();
                if s.is_empty() { None } else { Some(s) }
            };

            (
                t.id.0,
                TrackInfo {
                    title,
                    artist: artist_name,
                    mix_name,
                    album,
                    genre,
                    key,
                    bpm,
                    duration_sec: if t.duration > 0 {
                        Some(t.duration as u32)
                    } else {
                        None
                    },
                    label,
                    play_count: t.play_count,
                    isrc,
                },
            )
        })
        .collect();

    // Build playlist name lookup
    let playlist_names: HashMap<u32, String> = history_playlists
        .iter()
        .map(|h| (h.id.0, h.name.to_string()))
        .collect();

    // Group entries by playlist_id
    let mut entries_by_playlist: HashMap<u32, Vec<(u32, u32)>> = HashMap::new();
    for entry in &history_entries {
        entries_by_playlist
            .entry(entry.playlist_id.0)
            .or_default()
            .push((entry.track_id.0, entry.entry_index));
    }

    // Build sessions sorted by playlist ID (chronological)
    let mut playlist_ids: Vec<u32> = entries_by_playlist.keys().copied().collect();
    playlist_ids.sort();

    let mut sessions: Vec<HistorySession> = Vec::new();
    for playlist_id in playlist_ids {
        let name = playlist_names
            .get(&playlist_id)
            .cloned()
            .unwrap_or_else(|| format!("HISTORY {}", playlist_id));

        let mut entries = entries_by_playlist.remove(&playlist_id).unwrap_or_default();
        entries.sort_by_key(|(_, idx)| *idx);

        let tracks: Vec<HistoryTrack> = entries
            .iter()
            .enumerate()
            .filter_map(|(pos, (track_id, _))| {
                track_map.get(track_id).map(|track| HistoryTrack {
                    position: pos as u32 + 1,
                    track: TrackInfo {
                        title: track.title.clone(),
                        artist: track.artist.clone(),
                        mix_name: track.mix_name.clone(),
                        album: track.album.clone(),
                        genre: track.genre.clone(),
                        key: track.key.clone(),
                        bpm: track.bpm,
                        duration_sec: track.duration_sec,
                        label: track.label.clone(),
                        play_count: track.play_count,
                        isrc: track.isrc.clone(),
                    },
                })
            })
            .collect();

        if !tracks.is_empty() {
            sessions.push(HistorySession { name, tracks });
        }
    }

    sessions.sort_by_key(|s| s.name.clone());

    Ok(HistoryExport { sessions })
}
