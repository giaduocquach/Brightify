"""
ETL seed: Load existing CSV/JSON/NPY data into Brightify database.
Run once after migrations to populate tables.
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as cfg
from db.engine import engine, SessionLocal
from db.models import (
    Base, Artist, Album, Mood, Song,
    SongArtist, SongEmbedding,
)

DATA_DIR = Path(cfg.DATA_DIR)


def seed_moods(session):
    """Seed Russell's Circumplex mood quadrants."""
    moods = [
        ("Q1", "Happy/Excited", "happy", 0.75, 0.75),
        ("Q1", "Happy/Excited", "excited", 0.80, 0.85),
        ("Q1", "Happy/Excited", "joyful", 0.85, 0.70),
        ("Q2", "Angry/Tense", "angry", 0.30, 0.80),
        ("Q2", "Angry/Tense", "tense", 0.25, 0.75),
        ("Q2", "Angry/Tense", "energetic", 0.45, 0.90),
        ("Q3", "Sad/Melancholic", "sad", 0.25, 0.30),
        ("Q3", "Sad/Melancholic", "depressed", 0.15, 0.25),
        ("Q3", "Sad/Melancholic", "melancholic", 0.30, 0.35),
        ("Q4", "Calm/Peaceful", "calm", 0.65, 0.35),
        ("Q4", "Calm/Peaceful", "peaceful", 0.70, 0.30),
        ("Q4", "Calm/Peaceful", "relaxed", 0.75, 0.25),
    ]
    for q, qname, label, v, e in moods:
        existing = session.query(Mood).filter_by(mood_label=label).first()
        if not existing:
            session.add(Mood(quadrant=q, quadrant_name=qname,
                                mood_label=label, valence_center=v, energy_center=e))
    session.commit()
    print(f"  ✓ Moods: {session.query(Mood).count()} rows")


def seed_artists(session, df, artist_images):
    """Seed artists from CSV + artist_images.json + artist CSV (bulk upsert)."""
    artists = {}

    # Load artist CSV for thumbnail_url fallback
    artist_csv = Path(cfg.PHASE1_ARTISTS_FILE)
    artist_thumbs = {}
    if artist_csv.exists():
        adf = pd.read_csv(artist_csv)
        for _, arow in adf.iterrows():
            a_id = arow.get("artist_id")
            thumb = arow.get("thumbnail_url")
            if pd.notna(a_id) and pd.notna(thumb):
                artist_thumbs[str(a_id).strip()] = str(thumb)

    for _, row in df.iterrows():
        aid = row.get("primary_artist_id")
        if pd.notna(aid) and aid not in artists:
            artists[aid] = {"name": row.get("primary_artist", "Unknown")}

        all_ids = str(row.get("artist_ids", "")).split(",")
        all_names = str(row.get("artists", "")).split(",")
        for i, a_id in enumerate(all_ids):
            a_id = a_id.strip()
            if a_id and a_id not in artists:
                name = all_names[i].strip() if i < len(all_names) else "Unknown"
                artists[a_id] = {"name": name}

    for name, data in artist_images.items():
        for aid, info in artists.items():
            if info["name"].lower() == name.lower():
                info["image_url"] = data.get("image_url")
                info["genres"] = data.get("genres", [])
                info["followers"] = data.get("followers", 0)
                info["popularity"] = data.get("popularity", 0)
                break

    # Fallback: use artist CSV thumbnail_url if no image from artist_images.json
    for aid, info in artists.items():
        if not info.get("image_url") and aid in artist_thumbs:
            info["image_url"] = artist_thumbs[aid]

    # Bulk upsert in batches of 500
    rows = []
    for aid, info in artists.items():
        rows.append({
            "artist_id": aid,
            "name": info["name"],
            "genres": info.get("genres", []),
            "followers": info.get("followers", 0),
            "popularity": info.get("popularity", 0),
            "image_url": info.get("image_url"),
            "has_image": bool(info.get("image_url")),
        })

    for i in range(0, len(rows), 500):
        batch = rows[i:i+500]
        stmt = pg_insert(Artist).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=["artist_id"],
            set_={
                "name": stmt.excluded.name,
                "genres": stmt.excluded.genres,
                "followers": stmt.excluded.followers,
                "popularity": stmt.excluded.popularity,
                "image_url": stmt.excluded.image_url,
                "has_image": stmt.excluded.has_image,
            }
        )
        session.execute(stmt)
    session.commit()
    print(f"  ✓ Artists: {len(rows)} upserted / {session.query(Artist).count()} total")


def seed_albums(session, df):
    """Seed albums from CSV (bulk upsert)."""
    albums = {}
    for _, row in df.iterrows():
        aid = row.get("album_id")
        if pd.notna(aid) and aid not in albums:
            rd = str(row.get("album_release_date", ""))
            year = None
            if rd and len(rd) >= 4:
                try:
                    year = int(rd[:4])
                except ValueError:
                    pass
            thumb = row.get("thumbnail_url") if pd.notna(row.get("thumbnail_url")) else None
            albums[aid] = {
                "album_id": aid,
                "name": row.get("album_name", "Unknown"),
                "album_type": row.get("album_type"),
                "release_date": rd if rd else None,
                "release_year": year,
                "total_tracks": int(row["album_total_tracks"]) if pd.notna(row.get("album_total_tracks")) else None,
                "image_url_large": row.get("image_url_large") if pd.notna(row.get("image_url_large")) else thumb,
                "image_url_medium": row.get("image_url_medium") if pd.notna(row.get("image_url_medium")) else thumb,
                "image_url_small": row.get("image_url_small") if pd.notna(row.get("image_url_small")) else None,
            }

    rows = list(albums.values())
    for i in range(0, len(rows), 500):
        batch = rows[i:i+500]
        stmt = pg_insert(Album).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=["album_id"],
            set_={
                "name": stmt.excluded.name,
                "album_type": stmt.excluded.album_type,
                "release_date": stmt.excluded.release_date,
                "release_year": stmt.excluded.release_year,
                "total_tracks": stmt.excluded.total_tracks,
                "image_url_large": stmt.excluded.image_url_large,
                "image_url_medium": stmt.excluded.image_url_medium,
                "image_url_small": stmt.excluded.image_url_small,
            }
        )
        session.execute(stmt)
    session.commit()
    print(f"  ✓ Albums: {len(rows)} upserted / {session.query(Album).count()} total")


def seed_songs(session, df, mood_map):
    """Seed songs from processed CSV."""
    mp3_dir = cfg.MUSIC_DIR
    art_dir = cfg.ALBUM_ART_DIR

    new_count = 0
    update_count = 0
    for _, row in df.iterrows():
        tid = row["track_id"]
        existing = session.query(Song).filter_by(track_id=tid).first()

        # Check media availability
        mp3_file = mp3_dir / f"{tid}.mp3"
        has_mp3 = mp3_file.exists()

        art_file = art_dir / f"{tid}.jpg"
        thumb = row.get("thumbnail_url")
        has_art = art_file.exists() or (pd.notna(row.get("image_url_medium")) and str(row.get("image_url_medium")).startswith("http")) or (pd.notna(thumb) and str(thumb).startswith("http"))

        # Resolve arousal: prefer DEAM value; fall back to energy (same 0-1 scale)
        arousal_raw = row.get("arousal")
        if pd.notna(arousal_raw):
            arousal_val = float(arousal_raw)
        else:
            energy_raw = row.get("energy")
            arousal_val = float(energy_raw) if pd.notna(energy_raw) else 0.5

        # Resolve color_hex: required; fall back to neutral indigo
        color_hex_val = row.get("color_hex")
        color_hex_val = str(color_hex_val) if pd.notna(color_hex_val) else "#6366f1"

        # Resolve mood_quadrant: required; re-derive if missing/unknown
        mq = row.get("mood_quadrant")
        if pd.isna(mq) or str(mq) == "Unknown":
            v = float(row.get("valence", 0.5) or 0.5)
            a = arousal_val
            if v >= 0.5 and a >= 0.5:
                mq = "Q1: Happy/Excited"
            elif v < 0.5 and a >= 0.5:
                mq = "Q2: Angry/Tense"
            elif v < 0.5 and a < 0.5:
                mq = "Q3: Sad/Melancholic"
            else:
                mq = "Q4: Calm/Peaceful"

        # Map mood_quadrant to mood_id
        mood_id = mood_map.get(mq)

        # Build column values dict
        song_data = dict(
            track_name=row["track_name"],
            album_id=row.get("album_id") if pd.notna(row.get("album_id")) else None,
            primary_artist_id=row.get("primary_artist_id") if pd.notna(row.get("primary_artist_id")) else None,
            primary_artist_name=row.get("primary_artist") if pd.notna(row.get("primary_artist")) else None,
            popularity=int(row.get("track_popularity", 0)),
            duration_ms=int(row["track_duration_ms"]) if pd.notna(row.get("track_duration_ms")) else None,
            explicit=bool(row.get("track_explicit", False)),
            track_url=row.get("track_url") if pd.notna(row.get("track_url")) else None,
            image_url_large=row.get("image_url_large") if pd.notna(row.get("image_url_large")) else (row.get("thumbnail_url") if pd.notna(row.get("thumbnail_url")) else None),
            image_url_medium=row.get("image_url_medium") if pd.notna(row.get("image_url_medium")) else (row.get("thumbnail_url") if pd.notna(row.get("thumbnail_url")) else None),
            image_url_small=row.get("image_url_small") if pd.notna(row.get("image_url_small")) else None,
            has_art=has_art,
            # Audio features
            danceability=float(row["danceability"]) if pd.notna(row.get("danceability")) else None,
            energy=float(row["energy"]) if pd.notna(row.get("energy")) else None,
            key=int(row["key"]) if pd.notna(row.get("key")) else None,
            loudness=float(row["loudness"]) if pd.notna(row.get("loudness")) else None,
            loudness_lufs=float(row["loudness_lufs"]) if pd.notna(row.get("loudness_lufs")) else None,
            mode=int(row["mode"]) if pd.notna(row.get("mode")) else None,
            # Smart Crossfade Phase 3 — cue points + downbeats
            fade_out_cue_s=float(row["fade_out_cue_s"]) if pd.notna(row.get("fade_out_cue_s")) else None,
            fade_in_cue_s=float(row["fade_in_cue_s"]) if pd.notna(row.get("fade_in_cue_s")) else None,
            downbeat_times_json=row.get("downbeat_times_json") if pd.notna(row.get("downbeat_times_json")) else None,
            speechiness=float(row["speechiness"]) if pd.notna(row.get("speechiness")) else None,
            acousticness=float(row["acousticness"]) if pd.notna(row.get("acousticness")) else None,
            instrumentalness=float(row["instrumentalness"]) if pd.notna(row.get("instrumentalness")) else None,
            liveness=float(row["liveness"]) if pd.notna(row.get("liveness")) else None,
            valence=float(row["valence"]) if pd.notna(row.get("valence")) else None,
            tempo=float(row["tempo"]) if pd.notna(row.get("tempo")) else None,
            time_signature=int(row["time_signature"]) if pd.notna(row.get("time_signature")) else None,
            # ML-predicted features
            arousal=arousal_val,
            timbre_bright=float(row["timbre_bright"]) if pd.notna(row.get("timbre_bright")) else None,
            # Lyrics
            plain_lyrics=row.get("plain_lyrics") if pd.notna(row.get("plain_lyrics")) else None,
            synced_lyrics=row.get("synced_lyrics") if pd.notna(row.get("synced_lyrics")) else None,
            instrumental=bool(row.get("instrumental", False)),
            has_lyrics=bool(row.get("has_lyrics", False)),
            lyrics_cleaned=row.get("lyrics_cleaned") if pd.notna(row.get("lyrics_cleaned")) else None,
            # Processed features
            color_hex=color_hex_val,
            sentiment_compound=float(row["sentiment_compound"]) if pd.notna(row.get("sentiment_compound")) else None,
            sentiment_positive=float(row["sentiment_positive"]) if pd.notna(row.get("sentiment_positive")) else None,
            sentiment_neutral=float(row["sentiment_neutral"]) if pd.notna(row.get("sentiment_neutral")) else None,
            sentiment_negative=float(row["sentiment_negative"]) if pd.notna(row.get("sentiment_negative")) else None,
            sentiment_category=row.get("sentiment_category") if pd.notna(row.get("sentiment_category")) else None,
            mood_quadrant=mq,
            mood_id=mood_id,
            has_mp3=has_mp3,
            mp3_filename=f"{tid}.mp3" if has_mp3 else None,
        )

        if existing:
            # Update existing song with latest data
            for col, val in song_data.items():
                setattr(existing, col, val)
            update_count += 1
        else:
            song = Song(track_id=tid, **song_data)
            session.add(song)
            new_count += 1

        # Flush in batches
        if (new_count + update_count) % 500 == 0:
            session.flush()
            print(f"    ... {new_count + update_count} songs flushed")

    session.commit()
    print(f"  ✓ Songs: {new_count} new, {update_count} updated / {session.query(Song).count()} total")


def seed_song_artists(session, df):
    """Seed song_artists from CSV (bulk upsert)."""
    rows = []
    for _, row in df.iterrows():
        tid = row["track_id"]
        primary_aid = row.get("primary_artist_id")

        all_ids = str(row.get("artist_ids", "")).split(",")
        for a_id in all_ids:
            a_id = a_id.strip()
            if not a_id:
                continue
            rows.append({
                "track_id": tid,
                "artist_id": a_id,
                "is_primary": (a_id == primary_aid),
            })

    for i in range(0, len(rows), 500):
        batch = rows[i:i+500]
        stmt = pg_insert(SongArtist).values(batch)
        stmt = stmt.on_conflict_do_nothing()
        session.execute(stmt)

    session.commit()
    print(f"  ✓ Song-Artist links: {len(rows)} upserted")


def seed_embeddings(session):
    """Seed song_embeddings from NPY + metadata JSON (bulk upsert)."""
    emb_file = DATA_DIR / "vietnamese_music_embeddings_full.npy"
    meta_file = DATA_DIR / "embeddings_metadata.json"

    if not emb_file.exists() or not meta_file.exists():
        print("  ⚠ Embeddings files not found, skipping")
        return

    embeddings = np.load(str(emb_file))
    with open(meta_file) as f:
        meta = json.load(f)

    track_ids = meta.get("track_ids", [])
    if len(track_ids) != embeddings.shape[0]:
        print(f"  ⚠ Mismatch: {len(track_ids)} IDs vs {embeddings.shape[0]} vectors")
        return

    existing_song_ids = {str(tid) for (tid,) in session.query(Song.track_id).all()}
    model_name = meta.get("model", "vinai/phobert-base")
    rows = []
    skipped_missing_song = 0
    for i, tid in enumerate(track_ids):
        tid = str(tid)
        if tid not in existing_song_ids:
            skipped_missing_song += 1
            continue
        rows.append({
            "track_id": tid,
            "embedding": embeddings[i].tolist(),
            "model_name": model_name,
        })

    for i in range(0, len(rows), 500):
        batch = rows[i:i+500]
        stmt = pg_insert(SongEmbedding).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=["track_id"],
            set_={
                "embedding": stmt.excluded.embedding,
                "model_name": stmt.excluded.model_name,
            }
        )
        session.execute(stmt)

    session.commit()
    print(f"  ✓ Embeddings: {len(rows)} upserted / {session.query(SongEmbedding).count()} total")
    if skipped_missing_song:
        print(f"    skipped {skipped_missing_song} embeddings for tracks not present in songs")


# Vector columns that may be bulk-seeded from a .npy aligned to the processed CSV.
# Allowlist — the column name is interpolated into the UPDATE, so it must never
# come from outside this module.
_SEEDABLE_VECTOR_COLUMNS = {"e5_embedding", "muq_embedding"}


def _seed_vector_column(session, npy_name, column, label):
    """Bulk-populate ``song_embeddings.<column>`` from ``data/<npy_name>``.

    The .npy is row-aligned to ``vietnamese_music_processed_full.csv``, so row i
    maps to that CSV's i-th track_id. Only rows already present in song_embeddings
    are updated; the vector is written via pgvector's ``::vector`` cast.
    """
    from psycopg2.extras import execute_values

    if column not in _SEEDABLE_VECTOR_COLUMNS:
        raise ValueError(f"refusing to seed unknown vector column {column!r}")

    emb_file = DATA_DIR / npy_name
    csv_file = DATA_DIR / "vietnamese_music_processed_full.csv"
    if not emb_file.exists():
        print(f"  ⚠ {npy_name} not found, skipping {label} seed")
        return

    emb = np.load(str(emb_file))
    track_ids = pd.read_csv(str(csv_file), usecols=["track_id"])["track_id"].astype(str).tolist()
    if len(track_ids) != emb.shape[0]:
        print(f"  ⚠ Mismatch: {len(track_ids)} track_ids vs {emb.shape[0]} vectors")
        return

    existing = {str(t) for (t,) in session.query(SongEmbedding.track_id).all()}
    pairs = [(t, "[" + ",".join(f"{x:.6f}" for x in emb[i]) + "]")
             for i, t in enumerate(track_ids) if t in existing]

    cur = session.connection().connection.cursor()
    execute_values(
        cur,
        f"UPDATE song_embeddings se SET {column} = d.v::vector "
        "FROM (VALUES %s) AS d(tid, v) WHERE se.track_id = d.tid",
        pairs, template="(%s, %s)", page_size=500,
    )
    session.commit()
    n = session.query(SongEmbedding).filter(getattr(SongEmbedding, column).isnot(None)).count()
    print(f"  ✓ {column}: {n}/{session.query(SongEmbedding).count()} populated")


def seed_e5_embeddings(session):
    """Populate e5_embedding (multilingual-e5-large, 1024-dim lyrics — the active
    lyrics signal). The legacy 768-dim `embedding` column is left untouched."""
    _seed_vector_column(session, "lyrics_e5large.npy", "e5_embedding", "e5")


def seed_muq_embeddings(session):
    """Populate muq_embedding (MuQ, 1024-dim audio — the dominant similar-song
    signal, weight 0.76), enabling pgvector ANN candidate retrieval."""
    _seed_vector_column(session, "muq_embeddings.npy", "muq_embedding", "MuQ")


def run_seed():
    """Main ETL entry point."""
    print("=" * 60)
    print("Brightify Database – ETL Seed")
    print("=" * 60)

    # Load data files
    processed_file = DATA_DIR / "vietnamese_music_processed_full.csv"
    if not processed_file.exists():
        print(f"ERROR: {processed_file} not found!")
        sys.exit(1)

    print(f"\nLoading processed CSV...")
    df = pd.read_csv(str(processed_file))
    print(f"  {len(df)} rows, {len(df.columns)} columns")

    # Load artist images
    artist_images = {}
    ai_file = DATA_DIR / "artist_images.json"
    if ai_file.exists():
        with open(ai_file) as f:
            artist_images = json.load(f)
        print(f"  {len(artist_images)} artist images loaded")

    session = SessionLocal()
    try:
        print("\n1. Seeding moods...")
        seed_moods(session)

        print("\n2. Seeding artists...")
        seed_artists(session, df, artist_images)

        print("\n3. Seeding albums...")
        seed_albums(session, df)

        print("\n4. Seeding songs...")
        # Build mood_quadrant → mood_id map (full quadrant string → first mood_id)
        moods = session.query(Mood).all()
        mood_map = {}
        for m in moods:
            if m.quadrant not in mood_map:
                mood_map[m.quadrant] = m.mood_id
            full_key = f"{m.quadrant}: {m.quadrant_name}"
            if full_key not in mood_map:
                mood_map[full_key] = m.mood_id
        seed_songs(session, df, mood_map)

        print("\n5. Seeding song-artist bridges...")
        seed_song_artists(session, df)

        print("\n6. Seeding embeddings...")
        seed_embeddings(session)
        print("\n6b. Seeding e5-large lyrics embeddings (active, 1024-dim)...")
        seed_e5_embeddings(session)
        print("\n6c. Seeding MuQ audio embeddings (active, 1024-dim)...")
        seed_muq_embeddings(session)

        # 8. Create HNSW index for fast similarity search
        print("\n7. Creating HNSW vector index...")
        create_hnsw_index(session)

        # 8b. Ensure pg_trgm extension and trigram indexes
        print("\n7b. Creating trigram indexes for text search...")
        ensure_trigram_indexes(session)

        # 9. Post-seed validation
        print("\n8. Post-seed validation...")
        post_seed_validation(session)

        # Summary
        print("\n" + "=" * 60)
        print("ETL COMPLETE – Summary:")
        print(f"  Artists:    {session.query(Artist).count()}")
        print(f"  Albums:     {session.query(Album).count()}")
        print(f"  Songs:      {session.query(Song).count()}")
        print(f"  Moods:      {session.query(Mood).count()}")
        print(f"  Embeddings: {session.query(SongEmbedding).count()}")
        print("=" * 60)

    except Exception as e:
        session.rollback()
        print(f"\nERROR during seed: {e}")
        raise
    finally:
        session.close()


def create_hnsw_index(session):
    """Create HNSW index on song_embeddings for fast cosine similarity search."""
    try:
        # Drop existing index if any, then create HNSW
        session.execute(text(
            "DROP INDEX IF EXISTS ix_song_embedding_hnsw"
        ))
        session.execute(text(
            "CREATE INDEX ix_song_embedding_hnsw ON song_embeddings "
            "USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        ))
        session.commit()
        print("  ✓ HNSW index created (m=16, ef_construction=64)")
    except Exception as e:
        session.rollback()
        print(f"  ⚠ HNSW index creation failed: {e}")
        print("    (Non-fatal – linear scan will be used as fallback)")


def ensure_trigram_indexes(session):
    """Ensure pg_trgm extension and GIN trigram indexes for text search."""
    try:
        session.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        session.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_artist_name_trgm "
            "ON artists USING gin (name gin_trgm_ops)"
        ))
        session.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_song_track_name_trgm "
            "ON songs USING gin (track_name gin_trgm_ops)"
        ))
        session.commit()
        print("  ✓ Trigram indexes created (artists.name, songs.track_name)")
    except Exception as e:
        session.rollback()
        print(f"  ⚠ Trigram index creation failed: {e}")
        print("    (Non-fatal – standard LIKE queries will be used as fallback)")


def post_seed_validation(session):
    """Validate DB integrity after seeding."""
    issues = 0

    # Row counts
    song_count = session.query(Song).count()
    emb_count = session.query(SongEmbedding).count()
    artist_count = session.query(Artist).count()
    album_count = session.query(Album).count()

    print(f"  Songs: {song_count} | Embeddings: {emb_count} | Artists: {artist_count} | Albums: {album_count}")

    if emb_count < song_count:
        gap = song_count - emb_count
        print(f"  ⚠ {gap} songs missing embeddings")
        issues += 1

    # FK integrity: all song album_ids exist in albums
    orphan_albums = session.execute(text(
        "SELECT COUNT(*) FROM songs s "
        "LEFT JOIN albums a ON s.album_id = a.album_id "
        "WHERE s.album_id IS NOT NULL AND a.album_id IS NULL"
    )).scalar()
    if orphan_albums > 0:
        print(f"  ⚠ {orphan_albums} songs reference non-existent albums")
        issues += 1

    # FK integrity: all song primary_artist_ids exist in artists
    orphan_artists = session.execute(text(
        "SELECT COUNT(*) FROM songs s "
        "LEFT JOIN artists a ON s.primary_artist_id = a.artist_id "
        "WHERE s.primary_artist_id IS NOT NULL AND a.artist_id IS NULL"
    )).scalar()
    if orphan_artists > 0:
        print(f"  ⚠ {orphan_artists} songs reference non-existent artists")
        issues += 1

    # Mood quadrant coverage: at least 1 song in each quadrant
    quadrants = session.execute(text(
        "SELECT mood_quadrant, COUNT(*) as cnt FROM songs "
        "WHERE mood_quadrant IS NOT NULL GROUP BY mood_quadrant ORDER BY mood_quadrant"
    )).fetchall()
    print(f"  Mood quadrants: {', '.join(f'{q}: {c}' for q, c in quadrants)}")
    if len(quadrants) < 4:
        print(f"  ⚠ Only {len(quadrants)} quadrants have songs (expected 4)")
        issues += 1

    # Critical columns must never be NULL (NOT NULL enforced at DB level after migration 017)
    for col in ("color_hex", "arousal", "mood_quadrant"):
        null_count = session.execute(
            text(f"SELECT COUNT(*) FROM songs WHERE {col} IS NULL")
        ).scalar()
        if null_count > 0:
            print(f"  ⚠ {null_count} songs have NULL {col} — run migration 017 or re-seed")
            issues += 1
        else:
            print(f"  ✓ {col}: no NULLs")

    # HNSW index active check
    hnsw_check = session.execute(text(
        "SELECT indexname FROM pg_indexes WHERE tablename = 'song_embeddings' "
        "AND indexname = 'ix_song_embedding_hnsw'"
    )).fetchone()
    if hnsw_check:
        print(f"  ✓ HNSW index active")
    else:
        print(f"  ⚠ HNSW index not found")
        issues += 1

    if issues == 0:
        print(f"  ✅ All validation checks passed!")
    else:
        print(f"  ⚠ {issues} issue(s) found — review above")


if __name__ == "__main__":
    run_seed()
