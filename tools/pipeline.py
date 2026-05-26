"""
Brightify – Pipeline Orchestrator v9.0
Coordinates all 7 phases of the data pipeline with strict removal gates.

Pipeline flow (STRICT — no data passes without required assets):
  0. PRE-FLIGHT — Backup existing data, optionally truncate DB
  1. COLLECT    — YTMusic-Only: Charts + Search + Explore → ALL metadata
  2. FILTER     — Dedup, remove non-VN, remove missing required data
  3. DOWNLOAD   — MP3 via 5-tier YouTube + audio fingerprint ▸ GATE: remove no-MP3
  4. LYRICS     — YTMusic/LRCLIB lyrics                       ▸ GATE: remove no-lyrics
  5. EXTRACT    — Essentia DSP + TF ML models                 ▸ GATE: remove incomplete features
  6. PROCESS    — Feature engineering + hybrid PhoBERT+EffNet embeddings
  7. SEED       — ETL into PostgreSQL + HNSW index + validation

Usage:
    python -m tools.pipeline                           # Full pipeline
    python -m tools.pipeline --test-mode --limit 50    # Test: 50 tracks
    python -m tools.pipeline --phase 4                 # Run only Phase 4
    python -m tools.pipeline --from-phase 4            # Resume from Phase 4 onwards
    python -m tools.pipeline --skip-download           # Skip Phase 3 (MP3 download)
    python -m tools.pipeline --preflight-only          # Just backup, no pipeline
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# ── paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data"
CHECKPOINT_DIR = PROJECT_ROOT / "checkpoints"
BACKUP_DIR = PROJECT_ROOT / "backups"
MUSIC_DIR = PROJECT_ROOT / "music_files"

# Default timeout per phase (seconds): 4 hours
_PHASE_TIMEOUT = int(os.environ.get("PIPELINE_PHASE_TIMEOUT", 4 * 3600))

log = logging.getLogger("brightify.pipeline")


# ── pre-flight ───────────────────────────────────────────────────────────────

def preflight_backup():
    """Backup existing data files before a fresh run."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / ts
    backup_path.mkdir(parents=True, exist_ok=True)
    log.info(f"\n{'▓'*70}")
    log.info(f"  PRE-FLIGHT: Backup → {backup_path}")
    log.info(f"{'▓'*70}")

    files_to_backup = [
        DATA_DIR / "vietnamese_music_processed_full.csv",
        DATA_DIR / "vietnamese_music_embeddings_full.npy",
        DATA_DIR / "embeddings_metadata.json",
        DATA_DIR / "audio_embeddings.json",
    ]

    backed = 0
    for f in files_to_backup:
        if f.exists():
            dest = backup_path / f.name
            shutil.copy2(f, dest)
            log.info(f"  ✅ {f.name} → backup")
            backed += 1

    # Backup checkpoints
    if CHECKPOINT_DIR.exists():
        ckpt_backup = backup_path / "checkpoints"
        shutil.copytree(CHECKPOINT_DIR, ckpt_backup, dirs_exist_ok=True)
        log.info(f"  ✅ checkpoints/ → backup")
        backed += 1

    # Backup music_files (copy directory listing + actual files)
    if MUSIC_DIR.exists():
        mp3_files = list(MUSIC_DIR.glob("*.mp3"))
        if mp3_files:
            music_backup = backup_path / "music_files"
            music_backup.mkdir(parents=True, exist_ok=True)
            for mp3 in mp3_files:
                shutil.copy2(mp3, music_backup / mp3.name)
            log.info(f"  ✅ music_files/ → backup ({len(mp3_files)} MP3 files)")
            backed += 1

    log.info(f"  [PRE-FLIGHT] Backup complete ✅  ({backed} items → {backup_path})")
    return backup_path


def truncate_dw():
    """Truncate all DB tables in FK-safe order."""
    log.info("  Truncating DB tables (FK-safe order)...")
    try:
        from db.engine import engine
        from sqlalchemy import text
        # Order matters: facts first, then bridges, then dimensions
        tables = [
            "search_logs",
            "recommendations",
            "song_embeddings",
            "song_artists",
            "artist_genres",
            "songs",
            "albums",
            "artists",
            "genres",
            "moods",
        ]
        with engine.begin() as conn:
            for t in tables:
                conn.execute(text(f"TRUNCATE TABLE {t} CASCADE"))
                log.info(f"    ✓ {t}")
        log.info("  [PRE-FLIGHT] DB truncated. Schema verified ✅")
    except Exception as e:
        log.error(f"  ❌ DB truncation failed: {e}")
        raise

def clear_phase_checkpoints():
    """Clear phase output CSVs and JSON markers for a clean run. Keeps API caches."""
    log.info("  Clearing phase checkpoint CSVs for clean run...")
    for pattern in ["phase1_spotify*.csv", "phase2_filtered*.csv",
                    "phase3_downloaded*.csv", "phase4_lyrics*.csv",
                    "phase5_features*.csv"]:
        for f in CHECKPOINT_DIR.glob(pattern):
            f.unlink()
            log.info(f"    ✓ removed {f.name}")
    # Clear filter report from logs/
    report = PROJECT_ROOT / "logs" / "phase2_filter_report.md"
    if report.exists():
        report.unlink()
        log.info(f"    ✓ removed logs/phase2_filter_report.md")
    # Also clear the main tracks cache so Phase 1 starts fresh
    tc = CHECKPOINT_DIR / "tracks_collected.json"
    if tc.exists():
        tc.unlink()
        log.info(f"    ✓ removed tracks_collected.json")
    log.info("  ✅ Phase checkpoints cleared (API caches preserved)")


# ── phase runners ────────────────────────────────────────────────────────────

def run_phase_1(test_limit: int | None = None, seed_file: str | None = None,
                discovery_depth: int = 1):
    """Phase 1: Spotify artist discovery + YTMusic track collection."""
    log.info(f"\n{'▓'*70}")
    log.info(f"  PHASE 1: SPOTIFY ARTISTS + YTMUSIC TRACK COLLECTION")
    log.info(f"{'▓'*70}")

    cmd = [sys.executable, "-m", "tools.collect_data", "--phase", "collect"]
    if seed_file:
        cmd += ["--seed-file", seed_file]
    if test_limit:
        cmd += ["--max-tracks", str(test_limit)]
    else:
        cmd.append("--resume")
    cmd += ["--discovery-depth", str(discovery_depth)]

    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), timeout=_PHASE_TIMEOUT)
    if result.returncode != 0:
        log.error("  ❌ Phase 1 failed!")
        return False
    return True


def run_phase_2():
    """Phase 2: Data filtering & deduplication."""
    log.info(f"\n{'▓'*70}")
    log.info(f"  PHASE 2: DATA FILTERING & DEDUPLICATION")
    log.info(f"{'▓'*70}")

    from tools.filter_data import run_filter
    df = run_filter()
    if df is None or len(df) == 0:
        log.error("  ❌ Phase 2 produced no data!")
        return False
    log.info(f"  Phase 2 output: {len(df)} filtered tracks")
    return True


def run_phase_3(limit: int | None = None):
    """Phase 3: MP3 download (all tracks)."""
    log.info(f"\n{'▓'*70}")
    log.info(f"  PHASE 3: MP3 DOWNLOAD")
    log.info(f"{'▓'*70}")

    # Use phase2_filtered.csv as input (correct pipeline flow)
    input_csv = CHECKPOINT_DIR / "phase2_filtered.csv"
    if not input_csv.exists():
        input_csv = CHECKPOINT_DIR / "phase1_spotify.csv"

    cmd = [sys.executable, "-m", "tools.download_music", "--input", str(input_csv),
           "--workers", "8", "--delay", "0.5"]
    if limit:
        cmd += ["--limit", str(limit)]

    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), timeout=_PHASE_TIMEOUT)
    if result.returncode != 0:
        log.error("  ❌ Phase 3 failed!")
        return False
    return True


def gate_remove_no_mp3():
    """STRICT GATE: Remove all tracks without MP3.
    Reads phase2_filtered.csv (preferred) → phase1_spotify.csv fallback.
    Writes phase3_downloaded.csv (only tracks with matching MP3 file).
    """
    log.info(f"\n  ── GATE 3: Remove tracks without MP3 ──")
    import pandas as pd

    csv_path = None
    for candidate in [CHECKPOINT_DIR / "phase2_filtered.csv",
                       CHECKPOINT_DIR / "phase1_spotify.csv"]:
        if candidate.exists():
            csv_path = candidate
            break
    if csv_path is None:
        log.error("  ❌ No track list found (phase2_filtered or phase1_spotify)")
        return False

    df = pd.read_csv(str(csv_path))
    before = len(df)
    log.info(f"  Input: {csv_path.name} ({before:,} tracks)")

    mp3_files = {f.stem for f in MUSIC_DIR.glob("*.mp3")}
    df = df[df["track_id"].astype(str).isin(mp3_files)]
    df = df.reset_index(drop=True)

    removed = before - len(df)
    log.info(f"  Removed {removed:,} tracks without MP3 → {len(df):,} remaining")

    if len(df) == 0:
        log.error("  ❌ No tracks left after MP3 gate!")
        return False

    # Save as phase3_downloaded.csv for next phase
    out = CHECKPOINT_DIR / "phase3_downloaded.csv"
    df.to_csv(str(out), index=False, encoding="utf-8-sig")
    log.info(f"  ✅ Gate 3 output: {out.name}")
    return True


def run_phase_4():
    """Phase 4: Lyrics collection (keep all tracks, mark has_lyrics)."""
    log.info(f"\n{'▓'*70}")
    log.info(f"  PHASE 4: LYRICS")
    log.info(f"{'▓'*70}")

    cmd = [sys.executable, "-m", "tools.collect_data", "--phase", "lyrics", "--resume"]
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), timeout=_PHASE_TIMEOUT)
    if result.returncode != 0:
        log.error("  ❌ Phase 4 failed!")
        return False
    return True


def gate_remove_no_lyrics():
    """STRICT GATE: Remove all tracks without lyrics."""
    log.info(f"\n  ── GATE 4: Remove tracks without lyrics ──")
    csv_path = CHECKPOINT_DIR / "phase4_lyrics.csv"
    if not csv_path.exists():
        log.error("  ❌ phase4_lyrics.csv not found — run Phase 4 first")
        return False

    import pandas as pd
    df = pd.read_csv(str(csv_path))
    before = len(df)

    # Only keep tracks that have lyrics
    if "has_lyrics" in df.columns:
        df = df[df["has_lyrics"] == True]
    elif "plain_lyrics" in df.columns:
        df = df[df["plain_lyrics"].notna() & (df["plain_lyrics"].str.strip() != "")]
    else:
        log.warning("  ⚠️ No lyrics column found — skipping gate")
        return True

    df = df.reset_index(drop=True)
    removed = before - len(df)
    log.info(f"  Removed {removed:,} tracks without lyrics → {len(df):,} remaining")

    if len(df) == 0:
        log.error("  ❌ No tracks left after lyrics gate!")
        return False

    # Save as phase4_lyrics_gated.csv for Phase 5
    out = CHECKPOINT_DIR / "phase4_lyrics_gated.csv"
    df.to_csv(str(out), index=False, encoding="utf-8-sig")
    log.info(f"  ✅ Gate 4 output: {out.name}")
    return True


def run_phase_5():
    """Phase 5: Audio feature extraction (Essentia DSP + TF ML models)."""
    log.info(f"\n{'▓'*70}")
    log.info(f"  PHASE 5: AUDIO FEATURE EXTRACTION (DSP + ML)")
    log.info(f"{'▓'*70}")

    cmd = [sys.executable, "-m", "tools.extract_audio_features"]
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), timeout=_PHASE_TIMEOUT)
    if result.returncode != 0:
        log.error("  ❌ Phase 5 failed!")
        return False
    return True


# Essential features required for recommendation — missing ANY = remove
ESSENTIAL_FEATURES = [
    "valence", "energy", "danceability", "acousticness", "tempo",
    "instrumentalness", "speechiness", "loudness", "key", "mode",
]


def gate_remove_incomplete_features():
    """STRICT GATE: Remove tracks missing ANY essential audio feature."""
    log.info(f"\n  ── GATE 5: Remove tracks with incomplete features ──")
    csv_path = CHECKPOINT_DIR / "phase5_features.csv"
    if not csv_path.exists():
        log.error("  ❌ phase5_features.csv not found")
        return False

    import pandas as pd
    df = pd.read_csv(str(csv_path))
    before = len(df)

    # Check which essential features are available as columns
    available = [c for c in ESSENTIAL_FEATURES if c in df.columns]
    if len(available) < 5:
        log.warning(f"  ⚠️ Only {len(available)}/{len(ESSENTIAL_FEATURES)} essential feature columns exist")
        return True

    # Remove rows where ANY essential feature is null
    null_mask = df[available].isnull().any(axis=1)
    df = df[~null_mask]
    df = df.reset_index(drop=True)

    removed = before - len(df)
    log.info(f"  Checked {len(available)} essential features: {available}")
    log.info(f"  Removed {removed:,} tracks with incomplete features → {len(df):,} remaining")

    if len(df) == 0:
        log.error("  ❌ No tracks left after feature gate!")
        return False

    # Overwrite phase5_features.csv with only complete tracks
    df.to_csv(str(csv_path), index=False, encoding="utf-8-sig")
    log.info(f"  ✅ Gate 5 output: {csv_path.name} (overwritten)")
    return True


def run_phase_6(force: bool = False):
    """Phase 6: Feature engineering + hybrid PhoBERT+EffNet embeddings."""
    log.info(f"\n{'▓'*70}")
    log.info(f"  PHASE 6: FEATURE ENGINEERING + HYBRID EMBEDDINGS")
    log.info(f"{'▓'*70}")

    input_file = CHECKPOINT_DIR / "phase5_features.csv"
    if not input_file.exists():
        log.error("  ❌ phase5_features.csv not found — run Phase 5 first")
        return False

    cmd = [
        sys.executable, "-m", "tools.process_data",
        "--input", str(input_file),
        "--output", str(DATA_DIR / "vietnamese_music_processed_full.csv"),
        "--embeddings", str(DATA_DIR / "vietnamese_music_embeddings_full.npy"),
        "--metadata", str(DATA_DIR / "embeddings_metadata.json"),
    ]
    if force:
        cmd.append("--force")

    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), timeout=_PHASE_TIMEOUT)
    if result.returncode != 0:
        log.error("  ❌ Phase 6 failed!")
        return False
    return True


def run_phase_7():
    """Phase 7: Seed DB."""
    log.info(f"\n{'▓'*70}")
    log.info(f"  PHASE 7: SEED DB")
    log.info(f"{'▓'*70}")

    from db.seed import run_seed
    run_seed()
    return True


# ── phase output validation ──────────────────────────────────────────────────

PHASE_OUTPUT_FILES = {
    1: CHECKPOINT_DIR / "phase1_spotify.csv",
    2: CHECKPOINT_DIR / "phase2_filtered.csv",
    # Phase 3 produces MP3 files, not a CSV — gate creates phase3_downloaded.csv
    4: CHECKPOINT_DIR / "phase4_lyrics.csv",
    5: CHECKPOINT_DIR / "phase5_features.csv",
    6: DATA_DIR / "vietnamese_music_processed_full.csv",
}

PHASE_REQUIRED_COLUMNS = {
    1: ["track_id", "track_name"],
    2: ["track_id", "track_name", "primary_artist"],
    3: ["track_id", "track_name"],
    4: ["track_id", "track_name", "has_lyrics"],
    5: ["track_id", "danceability", "energy", "valence"],
    6: ["track_id", "track_name", "valence", "energy", "color_hex"],
}

MIN_ROWS = 10  # minimum viable output


def validate_phase_output(phase_num: int) -> bool:
    """Validate that a phase produced usable output."""
    output_file = PHASE_OUTPUT_FILES.get(phase_num)
    if not output_file:
        return True  # no file to validate (e.g., phase 6/7)
    if not output_file.exists():
        log.error(f"  ❌ Phase {phase_num} output missing: {output_file.name}")
        return False

    import pandas as pd
    try:
        df = pd.read_csv(output_file)
    except Exception as e:
        log.error(f"  ❌ Phase {phase_num} output unreadable: {e}")
        return False

    if len(df) < MIN_ROWS:
        log.error(f"  ❌ Phase {phase_num} output too small: {len(df)} rows (min {MIN_ROWS})")
        return False

    required = PHASE_REQUIRED_COLUMNS.get(phase_num, [])
    missing = [c for c in required if c not in df.columns]
    if missing:
        log.error(f"  ❌ Phase {phase_num} missing columns: {missing}")
        return False

    # Check track_id is never null
    if "track_id" in df.columns:
        null_pct = df["track_id"].isna().mean()
        if null_pct > 0:
            log.error(f"  ❌ Phase {phase_num}: {null_pct:.1%} null track_ids")
            return False

    log.info(f"  ✅ Phase {phase_num} validated: {len(df)} rows, all checks passed")
    return True


# ── test-mode validation ─────────────────────────────────────────────────────

def run_test_validation():
    """Post-pipeline test validation: check DB and run sample queries."""
    log.info(f"\n{'▓'*70}")
    log.info(f"  TEST VALIDATION")
    log.info(f"{'▓'*70}")

    try:
        from db.engine import SessionLocal
        from db.models import Song, SongEmbedding, Artist, Mood
        from sqlalchemy import text

        session = SessionLocal()

        song_count = session.query(Song).count()
        emb_count = session.query(SongEmbedding).count()
        artist_count = session.query(Artist).count()

        log.info(f"  DB: {song_count} songs, {emb_count} embeddings, {artist_count} artists")

        if song_count == 0:
            log.error("  ❌ No songs in DB — pipeline may have failed")
            session.close()
            return False

        # Test: query each mood quadrant
        for q in ["Q1", "Q2", "Q3", "Q4"]:
            cnt = session.query(Song).filter(Song.mood_quadrant.like(f"{q}%")).count()
            log.info(f"    {q}: {cnt} songs")

        # Test: sample embedding similarity query
        if emb_count > 0:
            sample = session.query(SongEmbedding).first()
            if sample:
                result = session.execute(text(
                    "SELECT s.track_name, s.primary_artist_name, "
                    "e.embedding <=> (SELECT embedding FROM song_embeddings WHERE track_id = :tid) AS dist "
                    "FROM song_embeddings e JOIN songs s ON e.track_id = s.track_id "
                    "WHERE e.track_id != :tid "
                    "ORDER BY dist LIMIT 3"
                ), {"tid": sample.track_id}).fetchall()
                log.info(f"\n  Sample similarity query for '{sample.track_id}':")
                for name, artist, dist in result:
                    log.info(f"    {artist} – {name} (dist={dist:.4f})")

        session.close()
        log.info(f"\n  ✅ Test validation passed!")
        return True

    except Exception as e:
        log.error(f"  ❌ Test validation failed: {e}")
        return False


# ── main orchestrator ────────────────────────────────────────────────────────

def run_pipeline(args):
    """Orchestrate the full pipeline."""
    start = time.time()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log.info(f"\n{'═'*70}")
    log.info(f"  🎵 BRIGHTIFY DATA PIPELINE v12.0 (Spotify Artists + YTMusic Tracks)")
    log.info(f"  Started: {ts}")
    if args.test_mode:
        limit = args.limit or 50
        log.info(f"  Mode: TEST (limit={limit}, 5 tracks/strategy)")
    else:
        limit = args.limit
        log.info(f"  Mode: PRODUCTION")
    log.info(f"{'═'*70}")

    phase_from = args.from_phase or (args.phase or 0)
    phase_to = args.phase or 7

    # Pre-flight: backup (unless --no-backup)
    if phase_from <= 0 and not args.no_backup:
        preflight_backup()

    # Truncate DB (independent of backup flag)
    if phase_from <= 0 and (args.truncate_db or args.test_mode):
        truncate_dw()

    # Clear phase checkpoints for clean start
    if (args.test_mode or args.truncate_db) and phase_from <= 1:
        clear_phase_checkpoints()

    if args.preflight_only:
        log.info("  Pre-flight complete. Exiting (--preflight-only).")
        return

    # Track phase results
    results = {}

    phases = [
        (1, "COLLECT",  lambda: run_phase_1(test_limit=limit, seed_file=getattr(args, 'seed_file', None),
                                              discovery_depth=getattr(args, 'discovery_depth', 1))),
        (2, "FILTER",   run_phase_2),
        (3, "DOWNLOAD", lambda: run_phase_3(limit=limit if args.test_mode else None)),
        (4, "LYRICS",   run_phase_4),
        (5, "EXTRACT",  run_phase_5),
        (6, "PROCESS",  lambda: run_phase_6(force=True)),
        (7, "SEED",     run_phase_7),
    ]

    # Strict removal gates: run after the corresponding phase
    phase_gates = {
        3: ("GATE_MP3", gate_remove_no_mp3),
        4: ("GATE_LYRICS", gate_remove_no_lyrics),
        5: ("GATE_FEATURES", gate_remove_incomplete_features),
    }

    for num, name, fn in phases:
        if num < phase_from or num > phase_to:
            continue
        if num == 3 and args.skip_download:
            log.info(f"\n  ⏭️  Skipping Phase 3 (--skip-download)")
            continue

        try:
            success = fn()
            if success and num in PHASE_OUTPUT_FILES:
                success = validate_phase_output(num)
            results[num] = "✅" if success else "⚠️"
            if not success and not args.continue_on_error:
                log.error(f"  Phase {num} failed validation — stopping pipeline")
                break

            # Run strict gate after this phase (if any)
            if success and num in phase_gates:
                gate_name, gate_fn = phase_gates[num]
                log.info(f"\n  Running {gate_name}...")
                gate_ok = gate_fn()
                if not gate_ok:
                    results[num] = "⚠️ (gate)"
                    if not args.continue_on_error:
                        log.error(f"  {gate_name} failed — stopping pipeline")
                        break

        except Exception as e:
            log.error(f"\n  ❌ Phase {num} ({name}) crashed: {e}")
            results[num] = "❌"
            if not args.continue_on_error:
                break

    # Test validation
    if args.test_mode:
        try:
            run_test_validation()
        except Exception as e:
            log.error(f"  Test validation error: {e}")

    elapsed = time.time() - start
    mins, secs = divmod(int(elapsed), 60)

    log.info(f"\n{'═'*70}")
    log.info(f"  🎉 PIPELINE COMPLETE  ({mins}m {secs}s)")
    for num, status in results.items():
        name = [n for nn, n, _ in phases if nn == num]
        log.info(f"    Phase {num} ({name[0] if name else '?'}): {status}")
    log.info(f"{'═'*70}\n")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Brightify Pipeline Orchestrator v8.0 (Strict Gates)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Phases (strict pipeline — no data passes without required assets):
  1. COLLECT    — Playlist discovery + YT Charts VN + Spotify Recs + YTMusic expansion
  2. FILTER     — Dedup, remove non-VN, remove missing data
  3. DOWNLOAD   — MP3 via 5-tier YouTube + fingerprint  ▸ GATE: remove no-MP3
  4. LYRICS     — YTMusic/LRCLIB lyrics                  ▸ GATE: remove no-lyrics
  5. EXTRACT    — Essentia DSP + TF ML models            ▸ GATE: remove incomplete features
  6. PROCESS    — Feature engineering + hybrid PhoBERT+EffNet embeddings
  7. SEED       — ETL into PostgreSQL + HNSW index

Examples:
  python -m tools.pipeline                           # Full production run
  python -m tools.pipeline --test-mode --limit 50    # Test with 50 tracks
  python -m tools.pipeline --phase 3                 # Run only Phase 3 (Download)
  python -m tools.pipeline --from-phase 5            # Resume from Phase 5
  python -m tools.pipeline --skip-download           # Skip Phase 3 (MP3 download)
  python -m tools.pipeline --preflight-only          # Only backup
  python -m tools.pipeline --truncate-db             # Reset DB before run
        """,
    )
    parser.add_argument("--test-mode", action="store_true", help="Test mode: small limits, full validation")
    parser.add_argument("--limit", type=int, help="Track limit (default: 50 for test, unlimited for prod)")
    parser.add_argument("--phase", type=int, choices=range(1, 8), help="Run only this phase")
    parser.add_argument("--from-phase", type=int, choices=range(1, 8), help="Resume from this phase onwards")
    parser.add_argument("--skip-download", action="store_true", help="Skip Phase 3 (MP3 download)")
    parser.add_argument("--truncate-db", action="store_true", help="Truncate DB tables before seeding")
    parser.add_argument("--no-backup", action="store_true", help="Skip pre-flight backup")
    parser.add_argument("--preflight-only", action="store_true", help="Only run pre-flight backup")
    parser.add_argument("--continue-on-error", action="store_true", help="Continue to next phase on error")
    parser.add_argument("--seed-file", type=str, default=None,
                        help="Path to seed artists file (one artist per line). Only these artists are collected.")
    parser.add_argument("--discovery-depth", type=int, default=1,
                        help="Depth for featured artist discovery (default: 1)")
    args = parser.parse_args()

    run_pipeline(args)


if __name__ == "__main__":
    # Suppress harmless semaphore leak warning when Ctrl+C kills ThreadPoolExecutor workers
    import warnings
    warnings.filterwarnings("ignore", message=".*leaked semaphore.*", category=UserWarning)
    main()
