// Copyright (c) 2026
//
// Access to rekordbox 6/7 master.db via SQLCipher.
// Derives the passphrase from rekordboxAgent's options.json.

use anyhow::{Context, Result};
use blowfish::Blowfish;
use cipher::{BlockDecrypt, KeyInit, generic_array::GenericArray};
use rusqlite::Connection;
use serde::Serialize;
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Serialize)]
pub struct MasterDbTrack {
    pub title: String,
    pub artist: String,
    pub mix_name: Option<String>,
    pub album: Option<String>,
    pub genre: Option<String>,
    pub key: Option<String>,
    pub bpm: Option<f64>,
    pub duration_sec: Option<u32>,
    pub label: Option<String>,
    pub play_count: u16,
    pub isrc: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct HistoryTrack {
    pub position: u32,
    #[serde(flatten)]
    pub track: MasterDbTrack,
}

#[derive(Debug, Serialize)]
pub struct HistorySession {
    pub name: String,
    pub tracks: Vec<HistoryTrack>,
}

#[derive(Debug, Serialize)]
pub struct HistoryExport {
    pub sessions: Vec<HistorySession>,
}

/// Location of a database and its passphrase.
pub struct LibraryLocation {
    pub master_db: PathBuf,
    pub passphrase: String,
    pub source: String, // "rekordbox 6", "rekordbox 7", "rbxport"
}

/// Auto-detect the library: rekordbox 6/7 first, then rbxport.
pub fn detect_library() -> Result<LibraryLocation> {
    // Rekordbox 6/7 — same agent path on macOS
    let rb_agent = shellexpand::tilde(
        "~/Library/Application Support/Pioneer/rekordboxAgent/storage/options.json"
    ).into_owned();

    if let Ok(loc) = detect_from(&PathBuf::from(&rb_agent), "rekordbox") {
        return Ok(loc);
    }

    // rbxport fallback — check RBXPORT_OPTIONS env var or default path
    if let Ok(rbx_home) = std::env::var("RBXPORT_OPTIONS") {
        if let Ok(loc) = detect_from(&PathBuf::from(&rbx_home), "rbxport") {
            return Ok(loc);
        }
    }
    // Default rbxport path
    let rbx_default = shellexpand::tilde(
        "~/Library/Application Support/Pioneer/rbxport/storage/options.json"
    ).into_owned();
    if let Ok(loc) = detect_from(&PathBuf::from(&rbx_default), "rbxport") {
        return Ok(loc);
    }

    anyhow::bail!(
        "No library found. Looked for:\n  - rekordbox 6/7 agent at {}\n  - rbxport at {}",
        rb_agent, rbx_default
    )
}

/// Derive the passphrase and find the database from an options.json.
fn detect_from(options_path: &Path, label: &str) -> Result<LibraryLocation> {
    if !options_path.exists() {
        anyhow::bail!("options.json not found at {}", options_path.display());
    }

    let opts_raw = fs::read_to_string(options_path)
        .context("Failed to read options.json")?;
    let opts: serde_json::Value = serde_json::from_str(&opts_raw)
        .context("Failed to parse options.json")?;

    let options = opts["options"].as_array()
        .context("options.json: missing 'options' array")?;

    let db_path = options.iter()
        .find(|o| o[0].as_str() == Some("db-path"))
        .and_then(|o| o[1].as_str())
        .context("options.json: missing 'db-path' field")?;

    let dp_b64 = options.iter()
        .find(|o| o[0].as_str() == Some("dp"))
        .and_then(|o| o[1].as_str())
        .context("options.json: missing 'dp' field")?;

    let passphrase = derive_passphrase(dp_b64)?;

    Ok(LibraryLocation {
        master_db: PathBuf::from(db_path),
        passphrase,
        source: match label {
            "rekordbox" => {
                let ver = opts["defaults"]["app_ver"].as_str().unwrap_or("?");
                format!("rekordbox {}", ver)
            }
            _ => label.to_string(),
        },
    })
}

/// Decrypt the dp field from options.json to get the SQLCipher passphrase.
fn derive_passphrase(dp_b64: &str) -> Result<String> {
    let data = base64::Engine::decode(
        &base64::engine::general_purpose::STANDARD, dp_b64.trim()
    ).context("Failed to base64 decode dp field")?;

    if data.is_empty() || data.len() % 8 != 0 {
        anyhow::bail!("dp decodes to {} bytes, not block-aligned", data.len());
    }

    let key = b"ZOwUlUZYqe9Rdm6j";
    let cipher: Blowfish = Blowfish::new_from_slice(key)
        .map_err(|e| anyhow::anyhow!("Failed to init Blowfish cipher: {}", e))?;

    let mut blocks: Vec<GenericArray<u8, _>> = data
        .chunks_exact(8)
        .map(|chunk| *GenericArray::from_slice(chunk))
        .collect();

    cipher.decrypt_blocks(&mut blocks);

    let decrypted: Vec<u8> = blocks.iter().flat_map(|b| b.as_slice()).copied().collect();

    // Trim trailing NULs and whitespace (matching rbxport's approach).
    let end = decrypted.iter()
        .rposition(|b| !b.is_ascii_whitespace() && *b != 0)
        .map_or(0, |i| i + 1);
    let passphrase = String::from_utf8(decrypted[..end].to_vec())
        .context("Decrypted passphrase is not valid UTF-8")?;

    Ok(passphrase)
}

/// Open the master.db and return a connection.
fn open_master_db() -> Result<(Connection, LibraryLocation)> {
    let loc = detect_library()?;
    eprintln!("  Source: {} ({})", loc.source, loc.master_db.display());

    let conn = Connection::open_with_flags(
        &loc.master_db,
        rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY | rusqlite::OpenFlags::SQLITE_OPEN_NO_MUTEX,
    ).context("Failed to open master.db")?;

    conn.pragma_update(None, "cipher", "sqlcipher").context("PRAGMA cipher failed")?;
    conn.pragma_update(None, "legacy", 4).context("PRAGMA legacy failed")?;
    conn.pragma_update(None, "key", &*loc.passphrase).context("PRAGMA key failed")?;

    // Verify it's readable
    conn.query_row("SELECT COUNT(*) FROM djmdContent", [], |_| Ok(()))
        .context("Failed to read from master.db — wrong passphrase or corrupt database")?;

    Ok((conn, loc))
}

/// Extract full history from master.db.
pub fn extract_history() -> Result<HistoryExport> {
    let (conn, _loc) = open_master_db()?;

    // --- Artists ---
    let mut artist_map: HashMap<String, String> = HashMap::new();
    {
        let mut stmt = conn.prepare("SELECT ID, Name FROM djmdArtist")?;
        for r in stmt.query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })? {
            let (id, name) = r?;
            if !name.is_empty() {
                artist_map.insert(id, name);
            }
        }
    }
    eprintln!("  Loaded {} artists", artist_map.len());

    // --- Albums ---
    let mut album_map: HashMap<String, String> = HashMap::new();
    {
        let mut stmt = conn.prepare("SELECT ID, Name FROM djmdAlbum")?;
        for r in stmt.query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })? {
            let (id, name) = r?;
            if !name.is_empty() {
                album_map.insert(id, name);
            }
        }
    }
    eprintln!("  Loaded {} albums", album_map.len());

    // --- Genres ---
    let mut genre_map: HashMap<String, String> = HashMap::new();
    {
        let mut stmt = conn.prepare("SELECT ID, Name FROM djmdGenre")?;
        for r in stmt.query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })? {
            let (id, name) = r?;
            if !name.is_empty() {
                genre_map.insert(id, name);
            }
        }
    }
    eprintln!("  Loaded {} genres", genre_map.len());

    // --- Labels ---
    let mut label_map: HashMap<String, String> = HashMap::new();
    {
        let mut stmt = conn.prepare("SELECT ID, Name FROM djmdLabel")?;
        for r in stmt.query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })? {
            let (id, name) = r?;
            if !name.is_empty() {
                label_map.insert(id, name);
            }
        }
    }
    eprintln!("  Loaded {} labels", label_map.len());

    // --- Keys ---
    let mut key_map: HashMap<String, String> = HashMap::new();
    {
        let mut stmt = conn.prepare("SELECT ID, ScaleName FROM djmdKey")?;
        for r in stmt.query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })? {
            let (id, name) = r?;
            if !name.is_empty() {
                key_map.insert(id, name);
            }
        }
    }
    eprintln!("  Loaded {} keys", key_map.len());

    // --- Tracks (djmdContent) ---
    let mut track_map: HashMap<String, MasterDbTrack> = HashMap::new();
    {
        let mut stmt = conn.prepare(
            "SELECT ID, Title, COALESCE(ArtistID, '') as ArtistID, \
             COALESCE(AlbumID, '') as AlbumID, COALESCE(GenreID, '') as GenreID, \
             COALESCE(KeyID, '') as KeyID, BPM, Length, \
             COALESCE(LabelID, '') as LabelID, DJPlayCount, Commnt, ISRC \
             FROM djmdContent WHERE ID IS NOT NULL"
        )?;
        for r in stmt.query_map([], |row| {
            let id: String = row.get(0)?;
            let title: String = row.get(1)?;
            let artist_id: String = row.get(2)?;
            let album_id: Option<String> = row.get(3)?;
            let genre_id: Option<String> = row.get(4)?;
            let key_id: Option<String> = row.get(5)?;
            let bpm: Option<f64> = row.get(6)?;
            let length: Option<f64> = row.get(7)?;
            let label_id: Option<String> = row.get(8)?;
            let play_count: Option<i64> = row.get(9)?;
            let comment: Option<String> = row.get(10)?;
            let isrc: Option<String> = row.get(11)?;

            let artist = artist_map.get(&artist_id).cloned().unwrap_or_default();
            let album = album_id.as_ref().and_then(|id| album_map.get(id)).cloned();
            let genre = genre_id.as_ref().and_then(|id| genre_map.get(id)).cloned();
            let key = key_id.as_ref().and_then(|id| key_map.get(id)).cloned();
            let label = label_id.as_ref().and_then(|id| label_map.get(id)).cloned();

            let isrc = isrc.filter(|s| !s.is_empty());

            // Detect mix name from comment or title
            let mix_name = comment.and_then(|c| {
                let c = c.trim().to_string();
                if c.is_empty() { None } else { Some(c) }
            });

            Ok((id, MasterDbTrack {
                title,
                artist,
                mix_name,
                album,
                genre,
                key,
                bpm: bpm.map(|b| b / 100.0),
                duration_sec: length.map(|l| l as u32),
                label,
                play_count: play_count.unwrap_or(0) as u16,
                isrc,
            }))
        })? {
            let (id, track) = r?;
            track_map.insert(id, track);
        }
    }
    eprintln!("  Loaded {} tracks", track_map.len());

    // --- History playlists ---
    let mut sessions: Vec<HistorySession> = Vec::new();
    {
        let mut hstmt = conn.prepare(
            "SELECT ID, Name FROM djmdHistory ORDER BY ID"
        )?;
        let history_list: Vec<(String, String)> = hstmt.query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })?.filter_map(|r| r.ok()).collect();

        for (history_id, history_name) in &history_list {
            let mut entries: Vec<(u32, String)> = Vec::new();
            {
                let mut estmt = conn.prepare(
                    "SELECT TrackNo, ContentID FROM djmdSongHistory \
                     WHERE HistoryID = ?1 ORDER BY TrackNo"
                )?;
                for r in estmt.query_map([history_id.as_str()], |row| {
                    Ok((
                        row.get::<_, i64>(0).unwrap_or(0) as u32,
                        row.get::<_, String>(1)?,
                    ))
                })? {
                    let (track_no, content_id) = r?;
                    entries.push((track_no, content_id));
                }
            }

            if entries.is_empty() {
                continue;
            }

            let tracks: Vec<HistoryTrack> = entries
                .into_iter()
                .enumerate()
                .filter_map(|(pos, (_, content_id))| {
                    track_map.get(&content_id).map(|track| HistoryTrack {
                        position: pos as u32 + 1,
                        track: MasterDbTrack {
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
                sessions.push(HistorySession {
                    name: history_name.clone(),
                    tracks,
                });
            }
        }
    }

    eprintln!("  Extracted {} history sessions", sessions.len());

    Ok(HistoryExport { sessions })
}