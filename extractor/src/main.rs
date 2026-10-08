mod master_db;

use anyhow::{Context, Result};
use fallible_iterator::FallibleIterator;
use rekordcrate::device::DeviceExportLoader;
use rekordcrate::pdb::*;
use std::collections::HashMap;
use std::path::Path;

use master_db::{HistoryExport, HistorySession, HistoryTrack, MasterDbTrack};

fn main() -> Result<()> {
    let args: Vec<String> = std::env::args().collect();

    if args.len() >= 3 && args[1] == "--source" && args[2] == "local" {
        eprintln!("Reading rekordbox master.db ...");
        let export = master_db::extract_history()?;
        let json = serde_json::to_string_pretty(&export)?;
        println!("{}", json);
        return Ok(());
    }

    if args.len() < 2 {
        eprintln!("Usage: rekord-extract <path-to-USB-or-export.pdb>");
        eprintln!("       rekord-extract --source local");
        std::process::exit(1);
    }

    let input_path = Path::new(&args[1]);
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
    extract_history_pdb(&pdb_path)
}

fn extract_history_pdb(pdb_path: &Path) -> Result<()> {
    let device_root = pdb_path
        .parent().and_then(|p| p.parent()).and_then(|p| p.parent())
        .context("Could not determine device root from PDB path")?;

    let loader = DeviceExportLoader::new(device_root.to_path_buf());
    let mut db = loader.open_pdb_non_persistent()?;

    let raw_tracks: Vec<Track> = db.iter_rows::<Track>()?.map(|t| Ok(t.clone())).collect()?;
    let raw_artists: Vec<Artist> = db.iter_rows::<Artist>()?.map(|a| Ok(a.clone())).collect()?;
    let raw_genres: Vec<Genre> = db.iter_rows::<Genre>()?.map(|g| Ok(g.clone())).collect()?;
    let raw_labels: Vec<Label> = db.iter_rows::<Label>()?.map(|l| Ok(l.clone())).collect()?;
    let raw_keys: Vec<Key> = db.iter_rows::<Key>()?.map(|k| Ok(k.clone())).collect()?;
    let raw_albums: Vec<Album> = db.iter_rows::<Album>()?.map(|a| Ok(a.clone())).collect()?;
    let history_playlists: Vec<HistoryPlaylist> = db.iter_rows::<HistoryPlaylist>()?.map(|h| Ok(h.clone())).collect()?;
    let history_entries: Vec<HistoryEntry> = db.iter_rows::<HistoryEntry>()?.map(|h| Ok(h.clone())).collect()?;

    eprintln!("  Found: {} tracks, {} history sessions, {} entries",
        raw_tracks.len(), history_playlists.len(), history_entries.len());

    if history_playlists.is_empty() {
        println!("{}", serde_json::to_string_pretty(&HistoryExport { sessions: vec![] })?);
        return Ok(());
    }

    let artist_map: HashMap<u32, String> = raw_artists.iter()
        .filter_map(|a| { let n = a.offsets.inner.name.to_string(); if n.is_empty() { None } else { Some((a.id.0, n)) } })
        .collect();
    let genre_map: HashMap<u32, String> = raw_genres.iter().map(|g| (g.id.0, g.name.to_string())).collect();
    let label_map: HashMap<u32, String> = raw_labels.iter().map(|l| (l.id.0, l.name.to_string())).collect();
    let key_map: HashMap<u32, String> = raw_keys.iter().map(|k| (k.id.0, k.name.to_string())).collect();
    let album_map: HashMap<u32, String> = raw_albums.iter()
        .filter_map(|a| { let n = a.offsets.inner.name.to_string(); if n.is_empty() { None } else { Some((a.id.0, n)) } })
        .collect();

    let track_map: HashMap<u32, MasterDbTrack> = raw_tracks.iter().map(|t| {
        let title = t.offsets.inner.title.to_string();
        let artist = artist_map.get(&t.artist_id.0).cloned().unwrap_or_default();
        let mix_name = { let s = t.offsets.inner.mix_name.to_string(); if s.is_empty() { None } else { Some(s) } };
        let isrc = { let s = t.offsets.inner.isrc.to_string(); if s.is_empty() { None } else { Some(s) } };
        (t.id.0, MasterDbTrack {
            title, artist, mix_name, isrc,
            album: album_map.get(&t.album_id.0).cloned(),
            genre: genre_map.get(&t.genre_id.0).cloned(),
            key: key_map.get(&t.key_id.0).cloned(),
            label: label_map.get(&t.label_id.0).cloned(),
            bpm: if t.tempo > 0 { Some(t.tempo as f64 / 100.0) } else { None },
            duration_sec: if t.duration > 0 { Some(t.duration as u32) } else { None },
            play_count: t.play_count,
        })
    }).collect();

    let playlist_names: HashMap<u32, String> = history_playlists.iter()
        .map(|h| (h.id.0, h.name.to_string())).collect();

    let mut entries_by_playlist: HashMap<u32, Vec<(u32, u32)>> = HashMap::new();
    for e in &history_entries {
        entries_by_playlist.entry(e.playlist_id.0).or_default().push((e.track_id.0, e.entry_index));
    }

    let mut pids: Vec<u32> = entries_by_playlist.keys().copied().collect();
    pids.sort();

    let mut sessions: Vec<HistorySession> = Vec::new();
    for pid in pids {
        let name = playlist_names.get(&pid).cloned().unwrap_or_else(|| format!("HISTORY {}", pid));
        let mut entries = entries_by_playlist.remove(&pid).unwrap_or_default();
        entries.sort_by_key(|(_, idx)| *idx);
        let tracks: Vec<HistoryTrack> = entries.iter().enumerate().filter_map(|(pos, (tid, _))| {
            track_map.get(tid).map(|t| HistoryTrack {
                position: pos as u32 + 1,
                track: MasterDbTrack {
                    title: t.title.clone(), artist: t.artist.clone(), mix_name: t.mix_name.clone(),
                    album: t.album.clone(), genre: t.genre.clone(), key: t.key.clone(),
                    bpm: t.bpm, duration_sec: t.duration_sec, label: t.label.clone(),
                    play_count: t.play_count, isrc: t.isrc.clone(),
                },
            })
        }).collect();
        if !tracks.is_empty() {
            sessions.push(HistorySession { name, tracks });
        }
    }
    sessions.sort_by_key(|s| s.name.clone());

    let json = serde_json::to_string_pretty(&HistoryExport { sessions })?;
    println!("{}", json);
    Ok(())
}