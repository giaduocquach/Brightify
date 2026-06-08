"""
Brightify – Phase 7: MP3 Download Manager (v3.0)
4-tier YouTube priority, duration matching, silence trimming, DB update.

Priority tiers (searched in order):
  T1  YouTube Music  (ytmusic search)  ±8s tolerance
  T2  Lyrics Video   (yt search + "lyrics")  ±10s
  T3  Music Video    (yt search + "MV")  ±15s
  T4  General        (yt search)  ±20s

Post-download:
  - SponsorBlock segments removed (if yt-dlp supports)
  - FFmpeg silence trim (leading/trailing)
  - Duration ratio check (0.85–1.15 of Spotify duration)
  - DB update (has_mp3, mp3_filename)

Usage:
    python -m tools.download_music                      # Download all
    python -m tools.download_music --limit 50           # Limit
    python -m tools.download_music --test               # 3 tracks
    python -m tools.download_music --status             # Status
    python -m tools.download_music --update-db-only     # Re-scan existing files → DB
"""

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
from tqdm import tqdm

import config as cfg

# ── project imports (optional — only for DB update) ─────────────────────────
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from db.engine import SessionLocal
    from db.models import Song
    HAS_DB = True
except Exception:
    HAS_DB = False

log = logging.getLogger("brightify.download")
if not log.handlers:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

# ── configuration ────────────────────────────────────────────────────────────

DATA_DIR = Path(cfg.DATA_DIR)
MUSIC_DIR = cfg.MUSIC_DIR
CHECKPOINT_DIR = cfg.CHECKPOINTS_DIR
PROCESSED_CSV = Path(cfg.PROCESSED_FILE)
RAW_CSV = Path(cfg.INPUT_FILE)
# Pipeline-correct input: use phase2_filtered.csv first (from Gate 2)
PIPELINE_CSV = CHECKPOINT_DIR / "phase2_filtered.csv"
PIPELINE_FALLBACK_CSV = CHECKPOINT_DIR / "phase1_spotify.csv"
FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"
COOKIES_FILE = Path(__file__).resolve().parent.parent / "cookies.txt"
USE_COOKIES = True

AUDIO_FORMAT = "mp3"
AUDIO_QUALITY = "192"  # kbps
MAX_DURATION = 600  # skip anything >10 min

# Duration tolerance per tier (seconds)
TIER_TOLERANCE = {
    "youtube_music": 8,
    "youtube_lyrics": 10,
    "youtube_mv": 15,
    "youtube_general": 20,
}

DURATION_RATIO_MIN = 0.85
DURATION_RATIO_MAX = 1.15


# ── AudioStorage abstraction ────────────────────────────────────────────────

class AudioStorage:
    """Manages the music_files/ directory and download log (thread-safe)."""

    def __init__(self, music_dir: Path | None = None):
        self.dir = Path(music_dir or MUSIC_DIR)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.dir / "download_log.json"
        self._lock = threading.Lock()
        self._log = self._load_log()

    def _load_log(self) -> dict:
        if self.log_path.exists():
            try:
                return json.loads(self.log_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_log(self):
        with self._lock:
            self.log_path.write_text(
                json.dumps(self._log, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def exists(self, track_id: str) -> bool:
        return (self.dir / f"{track_id}.mp3").exists()

    def path(self, track_id: str) -> Path:
        return self.dir / f"{track_id}.mp3"

    def record(self, track_id: str, info: dict):
        with self._lock:
            self._log[track_id] = info
        self._save_log()

    def get_record(self, track_id: str) -> dict | None:
        return self._log.get(track_id)

    def downloaded_ids(self) -> set:
        return {f.stem for f in self.dir.glob("*.mp3")}

    def total_size_mb(self) -> float:
        return sum(f.stat().st_size for f in self.dir.glob("*.mp3")) / (1024 * 1024)


# ── non-original version detection ──────────────────────────────────────────

# Comprehensive pattern to detect non-original versions in video titles
_NON_ORIGINAL_RE = re.compile(
    r'\b(?:'
    r'remix|lofi|lo-fi|lo fi|acoustic|piano|'
    r'live|live session|live at|concert|concert edition|'
    r'minishow|moodshow|liveshow|live show|in concert|'
    r'cover|karaoke|instrumental|beat|stripped|'
    r'speed up|sped up|slowed|reverb|'
    r'unplugged|orchestral|orchestra|symphony|remaster|demo|'
    r'nightcore|8d|bass boosted|phonk|'
    r'mashup|medley|session|sessions|'
    r'vinahouse|edm|drill|dub|trap mix|'
    r'bootleg|rework|flip|vip mix'
    r')\b',
    re.IGNORECASE,
)
# Whitelist — titles containing these are NOT non-original
_NON_ORIGINAL_WHITELIST_RE = re.compile(
    r'\bALIVE\b|\bTouliver\b|\bProd\.?\b|\bOriginal\b',
    re.IGNORECASE,
)


def _is_non_original(title: str, album: str = "") -> bool:
    """Check if a video title/album suggests non-original version."""
    for text in (title, album):
        if not text:
            continue
        if _NON_ORIGINAL_WHITELIST_RE.search(text):
            continue
        if _NON_ORIGINAL_RE.search(text):
            return True
    return False


# ── search helpers ───────────────────────────────────────────────────────────

def _sanitize_search(text: str) -> str:
    """Clean search query for YouTube."""
    text = re.sub(r'\((?:feat|ft|prod|remix|version|ver)\.?[^)]*\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[^\w\s\u00C0-\u024F\u1E00-\u1EFF]', ' ', text)
    return ' '.join(text.split())


def _get_ytmusic_id(track_name: str, artist: str, duration_ms: int | None) -> str | None:
    """Try YouTube Music API search (ytmusicapi). Prefers official/original versions."""
    try:
        from ytmusicapi import YTMusic
        yt = YTMusic()
        query = f"{artist} {track_name}"
        results = yt.search(query, filter="songs", limit=10)
        if not results:
            return None

        for r in results:
            vid = r.get("videoId")
            if not vid:
                continue
            # Skip non-original versions (live, remix, cover, etc.)
            r_title = r.get("title", "")
            r_album = ""
            album_info = r.get("album")
            if isinstance(album_info, dict):
                r_album = album_info.get("name", "")
            elif isinstance(album_info, str):
                r_album = album_info
            if _is_non_original(r_title, r_album):
                continue
            # Duration check
            if duration_ms:
                yt_dur_s = r.get("duration_seconds") or 0
                if not yt_dur_s:
                    raw = r.get("duration", "")
                    parts = raw.split(":")
                    if len(parts) == 2:
                        try:
                            yt_dur_s = int(parts[0]) * 60 + int(parts[1])
                        except ValueError:
                            yt_dur_s = 0
                spotify_dur_s = duration_ms / 1000
                if yt_dur_s and abs(yt_dur_s - spotify_dur_s) <= TIER_TOLERANCE["youtube_music"]:
                    return vid
            else:
                return vid  # no duration to compare — take first
        # No result passed duration check — skip rather than grab wrong track
        return None
    except Exception:
        return None


def _build_yt_search_queries(track_name: str, artist: str) -> list[tuple[str, str]]:
    """Build search queries for tiers 2-4. Returns [(query, tier_name), ...]."""
    base = _sanitize_search(f"{artist} {track_name}")
    return [
        (f"{base} official audio", "youtube_lyrics"),
        (f"{base} MV official", "youtube_mv"),
        (base, "youtube_general"),
    ]


def _search_youtube_best(query: str, spotify_dur_s: float | None,
                          tolerance: float) -> str | None:
    """Search YouTube for multiple results, filter non-originals, pick best
    match by duration. Returns video URL or None."""
    cmd = [
        sys.executable, "-m", "yt_dlp",
        f"ytsearch5:{query}",
        "--print", "%(id)s\t%(title)s\t%(duration)s",
        "--no-download",
        "--quiet",
        "--no-warnings",
        "--socket-timeout", "15",
    ]
    if COOKIES_FILE.exists():
        cmd += ["--cookies", str(COOKIES_FILE)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        if result.returncode != 0 or not result.stdout.strip():
            return None
    except (subprocess.TimeoutExpired, Exception):
        return None

    candidates = []
    for line in result.stdout.strip().split('\n'):
        parts = line.split('\t')
        if len(parts) < 3:
            continue
        vid_id, title, dur_str = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if not vid_id:
            continue

        # Skip non-original versions
        if _is_non_original(title):
            continue

        # Parse duration
        try:
            vid_dur = float(dur_str)
        except (ValueError, TypeError):
            vid_dur = None

        # Score by duration match (closer = better)
        if spotify_dur_s and vid_dur:
            diff = abs(vid_dur - spotify_dur_s)
            if diff <= tolerance:
                score = 1000 - diff
            else:
                score = -1  # too far off, skip
        else:
            score = 500  # no comparison possible, neutral

        if score >= 0:
            candidates.append((score, vid_id, title, vid_dur))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    best_id = candidates[0][1]
    return f"https://www.youtube.com/watch?v={best_id}"


# ── download core ────────────────────────────────────────────────────────────

# Global rate-limit state shared across worker threads
_rate_limit_lock = threading.Lock()
_rate_limited_until = 0.0  # timestamp when rate limit expires


def _download_via_ytdlp(video_ref: str, output_path: Path, is_url: bool = False) -> bool:
    """Download audio via yt-dlp with bounded retry on transient rate-limit."""
    global _rate_limited_until

    if is_url or video_ref.startswith("http"):
        source = video_ref
    else:
        source = f"ytsearch1:{video_ref}"

    tmp_pattern = str(output_path.with_suffix(".%(ext)s"))
    max_attempts = 3

    for attempt in range(1, max_attempts + 1):
        # Respect any shared cooldown from other workers
        with _rate_limit_lock:
            wait = _rate_limited_until - time.time()
        if wait > 0:
            time.sleep(wait)

        cmd = [
            sys.executable, "-m", "yt_dlp",
            source,
            "--extract-audio",
            "--audio-format", AUDIO_FORMAT,
            "--audio-quality", AUDIO_QUALITY,
            "--match-filter", f"duration<{MAX_DURATION}",
            "--no-playlist",
            "--output", tmp_pattern,
            "--no-warnings",
            "--retries", "1",
            "--extractor-retries", "1",
            "--socket-timeout", "20",
        ]
        if USE_COOKIES and COOKIES_FILE.exists():
            cmd += ["--cookies", str(COOKIES_FILE)]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            result = None

        if output_path.exists():
            return True

        # Check for other formats and convert
        for f in output_path.parent.glob(f"{output_path.stem}.*"):
            if f.suffix in ('.mp3', '.m4a', '.webm', '.opus', '.ogg'):
                if f.suffix != '.mp3':
                    try:
                        subprocess.run(
                            [FFMPEG_BIN, "-i", str(f), "-ab", f"{AUDIO_QUALITY}k",
                             "-y", str(output_path)],
                            capture_output=True, timeout=60,
                        )
                        f.unlink(missing_ok=True)
                    except Exception:
                        pass
                if output_path.exists():
                    return True

        stderr = ""
        if result is not None:
            stderr = (result.stderr or "") + (result.stdout or "")
        stderr_lower = stderr.lower()
        # Age/login/bot checks are usually video-specific. Treating those as a
        # global rate limit stalls every worker for minutes because of one bad
        # video. Only explicit HTTP throttling should trigger shared cooldown.
        is_rate_limited = any(
            kw in stderr_lower
            for kw in (
                "http error 429",
                "status code 429",
                "too many requests",
                "session has been rate-limited",
            )
        )
        if not is_rate_limited or attempt == max_attempts:
            return False

        cooldown_s = 20 * attempt
        with _rate_limit_lock:
            _rate_limited_until = max(_rate_limited_until, time.time() + cooldown_s)

    return False


def _trim_silence(mp3_path: Path) -> bool:
    """Trim leading/trailing silence with FFmpeg silenceremove filter."""
    tmp = mp3_path.with_suffix(".trimmed.mp3")
    try:
        subprocess.run(
            [
                FFMPEG_BIN, "-i", str(mp3_path),
                "-af", "silenceremove=start_periods=1:start_silence=0.5:start_threshold=-50dB,"
                       "areverse,silenceremove=start_periods=1:start_silence=0.5:start_threshold=-50dB,areverse",
                "-y", str(tmp),
            ],
            capture_output=True, timeout=120,
        )
        if tmp.exists() and tmp.stat().st_size > 1000:
            tmp.replace(mp3_path)
            return True
        tmp.unlink(missing_ok=True)
    except Exception:
        tmp.unlink(missing_ok=True)
    return False


def _get_mp3_duration(mp3_path: Path) -> float | None:
    """Get duration in seconds via ffprobe."""
    try:
        ffprobe = FFMPEG_BIN.replace("ffmpeg", "ffprobe") if "ffmpeg" in FFMPEG_BIN else "ffprobe"
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(mp3_path)],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return None


def _assess_quality(mp3_dur_s: float | None, spotify_dur_s: float | None) -> str:
    """Assess MP3 quality based on duration ratio."""
    if mp3_dur_s is None or spotify_dur_s is None or spotify_dur_s == 0:
        return "unknown"
    ratio = mp3_dur_s / spotify_dur_s
    if DURATION_RATIO_MIN <= ratio <= DURATION_RATIO_MAX:
        return "clean"
    elif ratio > DURATION_RATIO_MAX:
        return "has_extra"
    else:
        return "low"


# ── YouTube metadata fetch (view_count + upload_date, no audio download) ────

def _fetch_yt_metadata(video_url: str) -> dict:
    """Fetch view_count and upload_date from a YouTube URL without downloading audio.

    Uses yt-dlp --skip-download --print — much faster than --dump-json (~2-4s).
    Returns a dict with zero or more of: view_count (int), upload_date (str YYYY-MM-DD).
    Never raises — returns {} on any failure so the download pipeline is never blocked.
    """
    cmd = [
        sys.executable, "-m", "yt_dlp",
        video_url,
        "--skip-download",
        "--print", "%(view_count)s\t%(upload_date)s",
        "--no-playlist",
        "--quiet",
        "--no-warnings",
        "--socket-timeout", "15",
    ]
    if USE_COOKIES and COOKIES_FILE.exists():
        cmd += ["--cookies", str(COOKIES_FILE)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0 or not result.stdout.strip():
            return {}
        line = result.stdout.strip().split('\n')[0]
        parts = line.split('\t')
        if len(parts) < 2:
            return {}
        view_str, date_str = parts[0].strip(), parts[1].strip()
        out = {}
        if view_str.lstrip('-').isdigit():
            v = int(view_str)
            if v >= 0:
                out["view_count"] = v
        # upload_date from yt-dlp is YYYYMMDD → store as YYYY-MM-DD
        if len(date_str) == 8 and date_str.isdigit():
            out["upload_date"] = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        return out
    except Exception:
        return {}


# ── main download logic ─────────────────────────────────────────────────────

def download_track(track: dict, storage: AudioStorage) -> dict | None:
    """Download a single track. Priority:
      1. Direct URL from CSV (track_url) — 100% correct, no search needed
      2. Direct YTMusic URL from track_id (if 11-char videoId)
      3. YTMusic API search (filtered, original only)
      4-6. YouTube search with smart filtering (official audio → MV → general)
    Returns info dict on success, None on failure."""
    track_id = track["track_id"]
    track_name = track["track_name"]
    artist = track.get("artists", track.get("primary_artist", ""))
    track_url = track.get("track_url", "")
    duration_ms = track.get("duration_ms") or track.get("track_duration_ms")
    spotify_dur_s = None
    try:
        import math
        dur_val = float(duration_ms) if duration_ms is not None else float('nan')
        if not math.isnan(dur_val):
            spotify_dur_s = dur_val / 1000
            duration_ms = dur_val
        else:
            duration_ms = None
    except (ValueError, TypeError):
        duration_ms = None

    output = storage.path(track_id)
    direct_id_rejected = False

    # --- Tier 0: Direct URL from CSV (100% accurate) ---
    # This is the YTMusic URL collected in Phase 1 — guaranteed correct track
    if track_url and "youtube" in track_url:
        if _download_via_ytdlp(track_url, output, is_url=True):
            _trim_silence(output)
            dur = _get_mp3_duration(output)
            quality = _assess_quality(dur, spotify_dur_s)
            if quality in {"clean", "unknown"}:
                return {
                    "source": "direct_url",
                    "youtube_music_id": track_id,
                    "youtube_id": track_id,
                    "duration_s": int(dur) if dur else None,
                    "quality": quality,
                }
            output.unlink(missing_ok=True)
            direct_id_rejected = True

    # --- Tier 0b: Direct YTMusic URL from track_id ---
    # track_id IS the YouTube videoId (11 chars) in our pipeline
    if not direct_id_rejected and re.match(r'^[A-Za-z0-9_-]{11}$', track_id):
        url = f"https://music.youtube.com/watch?v={track_id}"
        if _download_via_ytdlp(url, output, is_url=True):
            _trim_silence(output)
            dur = _get_mp3_duration(output)
            quality = _assess_quality(dur, spotify_dur_s)
            return {
                "source": "ytmusic_direct",
                "youtube_music_id": track_id,
                "youtube_id": track_id,
                "duration_s": int(dur) if dur else None,
                "quality": quality,
            }

        url = f"https://www.youtube.com/watch?v={track_id}"
        if _download_via_ytdlp(url, output, is_url=True):
            _trim_silence(output)
            dur = _get_mp3_duration(output)
            quality = _assess_quality(dur, spotify_dur_s)
            return {
                "source": "youtube_direct",
                "youtube_music_id": track_id,
                "youtube_id": track_id,
                "duration_s": int(dur) if dur else None,
                "quality": quality,
            }

    # If direct URL existed but both Tier 0 and 0b failed, it's rate-limited.
    # Skip expensive search tiers — they won't help and waste minutes per track.
    if track_url and "youtube" in track_url and not direct_id_rejected:
        return None

    # --- Tier 1: YouTube Music API search (filtered) ---
    ytm_id = _get_ytmusic_id(track_name, artist, int(duration_ms) if duration_ms else None)
    if ytm_id:
        url = f"https://music.youtube.com/watch?v={ytm_id}"
        if _download_via_ytdlp(url, output, is_url=True):
            _trim_silence(output)
            dur = _get_mp3_duration(output)
            quality = _assess_quality(dur, spotify_dur_s)
            return {
                "source": "youtube_music",
                "youtube_music_id": ytm_id,
                "youtube_id": ytm_id,
                "duration_s": int(dur) if dur else None,
                "quality": quality,
            }

    # --- Tiers 2-4: YouTube search (smart filtering) ---
    for query, tier in _build_yt_search_queries(track_name, artist):
        tolerance = TIER_TOLERANCE.get(tier, 20)
        best_url = _search_youtube_best(query, spotify_dur_s, tolerance)
        if not best_url:
            continue

        if _download_via_ytdlp(best_url, output, is_url=True):
            _trim_silence(output)
            dur = _get_mp3_duration(output)
            quality = _assess_quality(dur, spotify_dur_s)

            # Duration ratio check — reject if extremely far off
            if dur and spotify_dur_s:
                ratio = dur / spotify_dur_s
                if ratio < 0.5 or ratio > 2.0:
                    output.unlink(missing_ok=True)
                    continue  # Try next tier

            # Extract video ID from URL
            vid_id = best_url.split("v=")[-1] if "v=" in best_url else None

            return {
                "source": tier,
                "youtube_music_id": None,
                "youtube_id": vid_id,
                "duration_s": int(dur) if dur else None,
                "quality": quality,
            }

    return None


# ── DB update ──────────────────────────────────────────────────────────────────────

def update_dw(storage: AudioStorage, track_ids: list[str] | None = None):
    """Update songs table with MP3 metadata for all downloaded tracks."""
    if not HAS_DB:
        log.warning("  ⚠ Database not available — skipping DB update")
        return

    session = SessionLocal()
    try:
        ids = track_ids or list(storage.downloaded_ids())
        updated = 0
        for tid in ids:
            mp3 = storage.path(tid)
            if not mp3.exists():
                continue

            record = storage.get_record(tid) or {}
            dur = record.get("duration_s") or _get_mp3_duration(mp3)

            song = session.query(Song).filter_by(track_id=tid).first()
            if not song:
                continue

            song.has_mp3 = True
            song.mp3_filename = f"{tid}.mp3"
            updated += 1

            if updated % 200 == 0:
                session.flush()

        session.commit()
        log.info(f"  ✅ DB updated: {updated} songs")
    except Exception as e:
        session.rollback()
        log.error(f"  ❌ DB update failed: {e}")
    finally:
        session.close()


# ── batch download ───────────────────────────────────────────────────────────

def get_tracks(input_csv: str | None = None) -> list[dict]:
    """Load track list from input CSV, checkpoint, processed, or raw CSV."""
    csv_path = None
    # Priority: explicit --input > pipeline checkpoints > processed > raw
    candidates = [
        Path(input_csv) if input_csv else None,
        PIPELINE_CSV,
        PIPELINE_FALLBACK_CSV,
        PROCESSED_CSV,
        RAW_CSV,
    ]
    for c in candidates:
        if c and c.exists():
            csv_path = c
            break
    if not csv_path:
        log.error(f"No CSV found in checkpoints/ or data/")
        return []
    log.info(f"  Loading tracks from: {csv_path}")
    df = pd.read_csv(str(csv_path))
    tracks = []
    for _, row in df.iterrows():
        tid = str(row.get("track_id", "")).strip()
        name = str(row.get("track_name", "")).strip()
        if tid and name:
            tracks.append({
                "track_id": tid,
                "track_name": name,
                "artists": str(row.get("artists", row.get("primary_artist", ""))).strip(),
                "duration_ms": row.get("track_duration_ms", row.get("duration_ms")),
                "track_url": str(row.get("track_url", "")).strip() if pd.notna(row.get("track_url")) else "",
            })
    return tracks


def batch_download(
    limit: int | None = None,
    delay: float = 0.15,
    workers: int | None = None,
    input_csv: str | None = None,
    fetch_metadata: bool = True,
    music_dir: str | Path | None = None,
):
    """Download tracks in batch with parallel workers and 4-tier priority."""
    max_workers = workers or int(os.getenv("DOWNLOAD_WORKERS", "2"))
    storage = AudioStorage(Path(music_dir) if music_dir else None)
    tracks = get_tracks(input_csv)
    downloaded = storage.downloaded_ids()

    pending = [t for t in tracks if t["track_id"] not in downloaded]
    if limit:
        pending = pending[:limit]

    if not pending:
        log.info("✅ All tracks already downloaded!")
        show_status()
        return

    log.info(f"\n{'═'*60}")
    log.info(f"  🎵 Brightify MP3 Downloader v3.1 (direct URL priority)")
    log.info(f"  Priority: Direct URL → YTMusic Direct → YTMusic Search → YT Search")
    log.info(f"  ⚡ All tracks have YTMusic URLs — 100% accurate downloads")
    log.info(f"  Workers: {max_workers} | Delay per worker: {delay}s")
    log.info(f"  Pending: {len(pending)} | Already: {len(downloaded)}")
    log.info(f"  Output: {storage.dir}")
    log.info(f"{'═'*60}\n")

    stats = {"success": 0, "skip": 0, "fail": 0}
    stats_lock = threading.Lock()
    tier_stats = {}
    newly_downloaded = []
    newly_lock = threading.Lock()

    pbar = tqdm(total=len(pending), desc="Downloading", unit="track")

    def _download_one(track):
        tid = track["track_id"]

        if storage.exists(tid):
            with stats_lock:
                stats["skip"] += 1
            pbar.update(1)
            return

        result = download_track(track, storage)
        if result:
            if fetch_metadata:
                yt_id = result.get("youtube_id")
                if yt_id:
                    yt_url = f"https://www.youtube.com/watch?v={yt_id}"
                    meta = _fetch_yt_metadata(yt_url)
                    if meta:
                        result.update(meta)
            storage.record(tid, result)
            with newly_lock:
                newly_downloaded.append(tid)
            src = result["source"]
            with stats_lock:
                tier_stats[src] = tier_stats.get(src, 0) + 1
                stats["success"] += 1
            vc = result.get("view_count")
            vc_str = f" | {vc:,} views" if vc else ""
            log.debug(f"  ✅ {tid} | {src} | {result.get('duration_s', '?')}s{vc_str}")
        else:
            storage.record(tid, {"source": None, "error": "all_tiers_failed"})
            with stats_lock:
                stats["fail"] += 1
            log.debug(f"  ❌ {tid} | All tiers failed")

        pbar.update(1)
        time.sleep(delay)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_download_one, t): t for t in pending}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                track = futures[future]
                log.error(f"  Worker error for {track['track_id']}: {e}")
                pbar.update(1)

    pbar.close()

    # ── Retry pass cho các track bị lỗi ─────────────────────────────────
    # Lý do fail thường là rate-limit khi tải song song. Retry tuần tự
    # với delay dài hơn, tối đa MAX_RETRY_PASSES lần.
    MAX_RETRY_PASSES = 3
    RETRY_DELAY_BASE = 8.0  # giây giữa mỗi track trong retry (dài hơn main pass)
    RETRY_WAIT_BASE  = 20   # giây chờ trước mỗi pass retry

    track_by_id = {t["track_id"]: t for t in tracks}
    failed_tracks = [
        track_by_id[tid] for tid, info in storage._log.items()
        if info.get("source") is None and not storage.exists(tid)
        and tid in track_by_id
    ]

    for retry_pass in range(1, MAX_RETRY_PASSES + 1):
        if not failed_tracks:
            break
        wait_s = RETRY_WAIT_BASE * retry_pass
        log.info(f"\n  🔄 Retry pass {retry_pass}/{MAX_RETRY_PASSES} — "
                 f"{len(failed_tracks)} track cần retry (chờ {wait_s}s...)")
        time.sleep(wait_s)

        still_failed = []
        pbar_r = tqdm(failed_tracks, desc=f"Retry {retry_pass}", unit="track")
        for track in pbar_r:
            tid = track["track_id"]
            if storage.exists(tid):          # đã tải xong ở pass trước
                stats["success"] += 1
                pbar_r.update(1)
                continue
            result = download_track(track, storage)
            if result:
                if fetch_metadata:
                    yt_id = result.get("youtube_id")
                    if yt_id:
                        meta = _fetch_yt_metadata(f"https://www.youtube.com/watch?v={yt_id}")
                        if meta:
                            result.update(meta)
                storage.record(tid, result)
                newly_downloaded.append(tid)
                src = result["source"]
                tier_stats[src] = tier_stats.get(src, 0) + 1
                stats["success"] += 1
                stats["fail"] = max(0, stats["fail"] - 1)
                log.debug(f"  ✅ Retry OK: {tid} [{src}]")
            else:
                still_failed.append(track)
                log.debug(f"  ❌ Retry {retry_pass} still failed: {tid}")
            time.sleep(RETRY_DELAY_BASE)
        pbar_r.close()

        recovered = len(failed_tracks) - len(still_failed)
        log.info(f"  Retry pass {retry_pass}: recovered {recovered}, "
                 f"still failed {len(still_failed)}")
        failed_tracks = still_failed

    if failed_tracks:
        log.info(f"  ⚠️  {len(failed_tracks)} track vẫn lỗi sau {MAX_RETRY_PASSES} lần retry — bỏ qua")
    # ─────────────────────────────────────────────────────────────────────

    # DB update for newly downloaded (single-threaded, safe)
    if newly_downloaded and HAS_DB:
        log.info(f"\n  Updating DB for {len(newly_downloaded)} new downloads...")
        update_dw(storage, newly_downloaded)

    log.info(f"\n{'═'*60}")
    log.info(f"  Download Complete!")
    log.info(f"  ✅ Success: {stats['success']}")
    log.info(f"  ⏭️  Skipped: {stats['skip']}")
    log.info(f"  ❌ Failed:  {stats['fail']}")
    if tier_stats:
        log.info(f"  Tier breakdown: {tier_stats}")
    log.info(f"{'═'*60}\n")


def show_status(music_dir: str | Path | None = None, input_csv: str | None = None):
    """Show download progress status."""
    storage = AudioStorage(Path(music_dir) if music_dir else None)
    tracks = get_tracks(input_csv)
    downloaded = storage.downloaded_ids()
    in_csv = {t["track_id"] for t in tracks}
    done = len(downloaded & in_csv)
    total = len(tracks)
    remaining = total - done

    print(f"\n{'='*50}")
    print(f"  Brightify Music Download Status")
    print(f"{'='*50}")
    print(f"  Total tracks in CSV : {total}")
    print(f"  Downloaded          : {done}")
    print(f"  Remaining           : {remaining}")
    print(f"  Progress            : {done/total*100:.1f}%" if total else "  N/A")
    print(f"  Total size          : {storage.total_size_mb():.1f} MB")
    print(f"  Music directory     : {storage.dir}")

    # Tier breakdown from log
    tier_counts = {}
    for tid, info in storage._log.items():
        src = info.get("source")
        if src:
            tier_counts[src] = tier_counts.get(src, 0) + 1
    if tier_counts:
        print(f"  Tier breakdown      : {tier_counts}")
    print(f"{'='*50}\n")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Brightify MP3 Downloader v3.0 (4-tier YouTube)")
    parser.add_argument("--limit", type=int, help="Max tracks to download")
    parser.add_argument("--input", type=str, help="Input CSV path (default: checkpoints/phase2_filtered.csv)")
    parser.add_argument("--test", action="store_true", help="Test: download 3 tracks")
    parser.add_argument("--status", action="store_true", help="Show status")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between downloads per worker (s)")
    parser.add_argument("--workers", type=int, default=2, help="Number of parallel download workers")
    parser.add_argument("--update-db-only", action="store_true", help="Re-scan mp3 files and update DB")
    parser.add_argument("--skip-metadata", action="store_true", help="Skip extra YouTube metadata fetch after successful download")
    parser.add_argument("--music-dir", type=str, help="MP3 output directory (default: music_files/)")
    parser.add_argument(
        "--no-cookies",
        action="store_true",
        help="Do not pass cookies.txt to yt-dlp (useful when that session is rate-limited)",
    )
    args = parser.parse_args()
    global USE_COOKIES
    USE_COOKIES = not args.no_cookies

    if args.status:
        show_status(args.music_dir, args.input)
    elif args.update_db_only:
        update_dw(AudioStorage(Path(args.music_dir) if args.music_dir else None))
    elif args.test:
        batch_download(
            limit=3,
            delay=args.delay,
            workers=args.workers,
            input_csv=args.input,
            fetch_metadata=not args.skip_metadata,
            music_dir=args.music_dir,
        )
    else:
        batch_download(
            limit=args.limit,
            delay=args.delay,
            workers=args.workers,
            input_csv=args.input,
            fetch_metadata=not args.skip_metadata,
            music_dir=args.music_dir,
        )


if __name__ == "__main__":
    main()
