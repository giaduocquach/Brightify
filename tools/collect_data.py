#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  Vietnamese Music Data Collector v12.0  —  Spotify Artists + YTMusic Tracks  ║
║  Spotify → artist discovery ONLY (genre-validated, curated metadata)         ║
║  YTMusic → track collection, MP3, lyrics (no artist discovery from YT)      ║
║                                                                             ║
║  Pipeline:                                                                  ║
║    0. Spotify search + playlist + track mining → genre-validated artists     ║
║    1. YTMusic artist resolution (search channelId for Spotify artists)       ║
║    2. YTMusic track collection (get_artist → get_album → all tracks)         ║
║    3. Featured artist discovery from track credits + collect their tracks    ║
║    4. Vietnamese filter + dedup + export                                    ║
║                                                                             ║
║  Usage:                                                                      ║
║    python -m tools.collect_data                       # Full pipeline         ║
║    python -m tools.collect_data --phase collect       # Phase 1 only          ║
║    python -m tools.collect_data --phase lyrics        # Lyrics only           ║
║    python -m tools.collect_data --resume              # Resume checkpoint     ║
║    python -m tools.collect_data --status              # Current progress      ║
║    python -m tools.collect_data --max-tracks 5000     # Limit tracks          ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import re
import csv
import json
import time
import random
import string
import logging
import argparse
import subprocess
import unicodedata
import threading
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Set, Any
from datetime import datetime
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import pandas as pd
from tqdm import tqdm
from difflib import SequenceMatcher

# LRCLIB: sử dụng REST API trực tiếp (không cần package bên thứ 3)
HAS_LRCLIB = True  # always available via requests

try:
    from langdetect import detect as langdetect_detect
    HAS_LANGDETECT = True
except ImportError:
    HAS_LANGDETECT = False

try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
    HAS_SPOTIPY = True
except ImportError:
    HAS_SPOTIPY = False

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import warnings
warnings.filterwarnings("ignore")

logging.getLogger("urllib3").setLevel(logging.WARNING)


def _add_default_timeout(original_request, timeout=30):
    """Wrap a requests.Session.request to enforce a default timeout."""
    import functools
    @functools.wraps(original_request)
    def wrapper(*args, **kwargs):
        kwargs.setdefault("timeout", timeout)
        return original_request(*args, **kwargs)
    return wrapper

# ============================================================================
# CONFIGURATION
# ============================================================================
class Config:
    """Tập trung toàn bộ cấu hình"""

    # --- Output paths ---
    BASE_DIR = Path(__file__).parent.parent  # project root
    DATA_DIR = BASE_DIR / "data"
    LOGS_DIR = BASE_DIR / "logs"
    CHECKPOINT_DIR = BASE_DIR / "checkpoints"
    LYRICS_BACKUP = DATA_DIR / "lyrics_backup.json"
    MUSIC_DIR = BASE_DIR / "music_files"
    LOG_FILE = LOGS_DIR / "collect_data.log"

    # --- Rate limiting ---
    # Spotify rolling 30-second window rate limit (developer.spotify.com/documentation/web-api/concepts/rate-limits)
    # Development mode has a low limit — we target ~60 calls per 30s window to stay safe.
    SPOTIFY_DELAY = 0.3           # Base delay between Spotify API calls (seconds)
    SPOTIFY_MAX_CALLS_PER_30S = 25  # Max API calls in rolling 30-second window (conservative for dev mode)
    YTMUSIC_DELAY = 0.1           # ytmusicapi rate limit (minimal, no auth needed)
    LRCLIB_DELAY = 0.12
    BACKOFF_BASE = 2.0
    BACKOFF_MAX = 60.0

    # --- Spotify genre filtering ---
    # Vietnamese genres on Spotify — artist is VN if ANY genre matches
    SPOTIFY_VN_GENRES = {
        'v-pop', 'vietnamese hip hop', 'vietnam indie', 'vinahouse',
        'vietnamese pop', 'vietnamese r&b', 'vietnamese electronic',
        'vietnamese trap', 'vietnamese drill', 'vietnamese lo-fi',
    }
    # These genre keywords (substring match) confirm Vietnamese artist
    SPOTIFY_VN_GENRE_KEYWORDS = ('viet', 'v-pop', 'vpop', 'vina')
    # Genres to reject — old-genre / bolero / children
    SPOTIFY_REJECT_GENRES = {
        'bolero', 'vietnamese bolero', 'nhac vang',
    }
    SPOTIFY_REJECT_GENRE_KEYWORDS = ('bolero', 'nhạc vàng', 'cải lương', 'dân ca')
    # Foreign genres — reject artists with ONLY these genres (no VN genre)
    SPOTIFY_FOREIGN_GENRES = {
        'k-pop', 'j-pop', 'j-rock', 'anime', 'c-pop', 'mandopop', 'cantopop',
        'french rap', 'french pop', 'p-pop', 'opm', 'kundiman', 't-pop',
        'gufeng', 'chinese r&b', 'chinese hip hop', 'chinese indie',
        'taiwanese indie', 'taiwanese pop', 'thai pop', 'indian pop',
        'latin pop', 'reggaeton', 'k-rap', 'j-rap',
    }
    MAX_RETRIES = 30               # Allow many retries (progressive backoff handles timing)
    RETRY_BACKOFF_START = 5.0      # Initial wait on 429 (seconds)
    RETRY_BACKOFF_MULTIPLIER = 1.5 # Multiply backoff each consecutive 429
    RETRY_BACKOFF_CAP = 60.0       # Maximum backoff per retry (seconds)
    RETRY_GIVE_UP_AFTER = 0        # 0 = never give up, keep retrying forever
    BAN_SLEEP_CYCLE = 45           # When all apps are 429'd (rolling window), sleep then retry

    STRATEGY_COOLDOWN = 5
    API_CALL_LIMIT = 25_000
    ROTATION_BATCH_SIZE = 10       # Calls per app before proactive rotation (lower = better distribution)

    # --- 429 recovery ---
    # When ALL apps are continuously 429'd for this long, raise SpotifyRateLimitBan
    # so the caller can skip the current item and try the next one.
    # The pipeline NEVER fully stops — it skips failed items and continues.
    MAX_CONTINUOUS_429_SECONDS = 600  # 10 minutes of non-stop 429 = skip this item

    # --- Vietnamese detection ---
    VIETNAMESE_UNIQUE_CHARS = set(
        "ăắằẳẵặâấầẩẫậđêếềểễệôốồổỗộơớờởỡợưứừửữự"
        "ĂẮẰẲẴẶÂẤẦẨẪẬĐÊẾỀỂỄỆÔỐỒỔỖỘƠỚỜỞỠỢƯỨỪỬỮỰ"
    )
    VIETNAMESE_ALL_DIACRITICS = set(
        "áàảãạăắằẳẵặâấầẩẫậđéèẻẽẹêếềểễệ"
        "íìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵ"
        "ÁÀẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬĐÉÈẺẼẸÊẾỀỂỄỆ"
        "ÍÌỈĨỊÓÒỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÚÙỦŨỤƯỨỪỬỮỰÝỲỶỸỴ"
    )

    FOREIGN_CHAR_RANGES = [
        (0xAC00, 0xD7AF),   # Korean Hangul syllables
        (0x1100, 0x11FF),   # Korean Jamo
        (0x3040, 0x309F),   # Japanese Hiragana
        (0x30A0, 0x30FF),   # Japanese Katakana
        (0x4E00, 0x9FFF),   # CJK Unified Ideographs
        (0x0E00, 0x0E7F),   # Thai
        (0x0400, 0x04FF),   # Cyrillic
        (0x0600, 0x06FF),   # Arabic
        (0x0900, 0x097F),   # Devanagari (Hindi)
        (0x0980, 0x09FF),   # Bengali
    ]


# ============================================================================
# LOGGING
# ============================================================================
def setup_logging():
    """Thiết lập logging với file + console"""
    Config.CHECKPOINT_DIR.mkdir(exist_ok=True)
    Config.LOGS_DIR.mkdir(exist_ok=True)

    logger = logging.getLogger("collector")
    logger.setLevel(logging.DEBUG)

    # File handler
    fh = logging.FileHandler(Config.LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    ))

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


log = setup_logging()


class CheckpointManager:
    """Quản lý checkpoint – lưu/khôi phục tiến trình"""

    def __init__(self, checkpoint_dir: Path = None):
        self.dir = checkpoint_dir or Config.CHECKPOINT_DIR
        self.dir.mkdir(exist_ok=True)

    def save(self, name: str, data: Any):
        path = self.dir / f"{name}.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, default=str)
            log.debug(f"  💾 Checkpoint saved: {name}")
        except Exception as e:
            log.error(f"  ❌ Lỗi save checkpoint {name}: {e}")

    def load(self, name: str) -> Any:
        path = self.dir / f"{name}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.error(f"  ❌ Lỗi load checkpoint {name}: {e}")
            return None

    def exists(self, name: str) -> bool:
        return (self.dir / f"{name}.json").exists()

    def save_tracks(self, tracks: Dict[str, dict]):
        self.save("tracks_collected", {
            "count": len(tracks),
            "timestamp": datetime.now().isoformat(),
            "tracks": tracks,
        })

    def load_tracks(self) -> Dict[str, dict]:
        data = self.load("tracks_collected")
        if data and "tracks" in data:
            log.info(f"  📂 Loaded {data['count']} tracks from checkpoint ({data['timestamp']})")
            return data["tracks"]
        return {}

    def save_dataframe(self, name: str, df: pd.DataFrame):
        path = self.dir / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        log.debug(f"  💾 DataFrame checkpoint: {name} ({len(df)} rows)")

    def load_dataframe(self, name: str) -> Optional[pd.DataFrame]:
        path = self.dir / f"{name}.csv"
        if path.exists():
            df = pd.read_csv(path, encoding="utf-8-sig")
            log.info(f"  📂 Loaded DataFrame {name}: {len(df)} rows")
            return df
        return None


# ============================================================================
# SPOTIFY RATE LIMITER
# ============================================================================
class SpotifyRateLimitBan(Exception):
    """Raised when a single API call fails for > MAX_CONTINUOUS_429_SECONDS.

    This does NOT stop the pipeline. Callers catch this per-item (per-query,
    per-artist) and skip to the next item. The pipeline continues.
    """
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(
            f"Spotify 429 for {retry_after}s continuously. "
            f"Skipping this item and trying next."
        )


class SpotifyRateLimiter:
    """Sliding-window rate limiter for Spotify API calls with progressive backoff.

    Key insight: Spotify's Retry-After header often says 86400s (24h) for dev-mode
    apps, but the actual rate limit is a rolling 30-second window. Retrying every
    5-10s with progressive backoff works — data comes through despite the scary header.

    Behavior:
    - Tracks calls in a rolling 30-second window
    - Proactively throttles BEFORE hitting the limit
    - On 429: uses progressive backoff (5s -> 7.5s -> 11s -> ... -> 60s max)
    - IGNORES Retry-After header values (logs them for info only)
    - After 3 consecutive 429s, tries rotating to next Spotify app
    - Only gives up after 15 minutes of solid 429 failures (RETRY_GIVE_UP_AFTER)

    Fix for spotipy 2.25.2: patches urllib3 Retry to disable all retries,
    so 429 goes through HTTPError path and headers are preserved for logging.
    """

    def __init__(self, credentials_list: list, max_per_30s: int = None):
        """
        Args:
            credentials_list: list of (client_id, client_secret) tuples.
            max_per_30s: max API calls per rolling 30-second window.
        """
        if not credentials_list:
            raise ValueError("No Spotify credentials provided")
        self._credentials = credentials_list
        self._max_per_30s = max_per_30s or Config.SPOTIFY_MAX_CALLS_PER_30S
        # Per-app call time tracking (independent sliding windows)
        self._app_call_times: dict[int, deque] = {i: deque() for i in range(len(credentials_list))}
        self._call_times: deque = self._app_call_times[0]  # reference to current app's deque
        self._total_calls = 0
        self._app_total_calls: dict[int, int] = {i: 0 for i in range(len(credentials_list))}
        self._consecutive_429s = 0
        self._current_idx = 0
        self._calls_since_rotation = 0  # counter for proactive rotation
        self._sp = self._build_client(0, credentials_list=self._credentials)

    @staticmethod
    def _build_client(idx=0, credentials_list=None):
        """Build a raw spotipy.Spotify client for the given credential index.

        CRITICAL FIX: After spotipy builds the session, we patch the urllib3 Retry
        object to set total=0 and respect_retry_after_header=False.

        Why: urllib3 hard-codes 429 in RETRY_AFTER_STATUS_CODES and will retry ANY
        response with a Retry-After header, even when 429 is not in status_forcelist.
        This causes spotipy to catch a RetryError (not HTTPError), which strips the
        response headers — making it impossible to read Retry-After values.

        With the patched Retry(total=0, respect_retry_after_header=False):
        - ALL HTTP errors go through requests' HTTPError path
        - spotipy catches HTTPError and creates SpotifyException WITH response.headers
        - Our _call() can then read Retry-After accurately (e.g., 86400 for 24h ban)
        - Our _call() handles ALL retry logic (429, 5xx, connection errors)
        """
        if credentials_list is None:
            raise ValueError("credentials_list required")
        from urllib3.util.retry import Retry as UrllibRetry

        client_id, client_secret = credentials_list[idx]
        auth = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
        sp = spotipy.Spotify(
            auth_manager=auth,
            requests_timeout=20,
            retries=0,
            backoff_factor=0,
        )
        # Patch: disable ALL urllib3 retries so 429 goes through HTTPError path
        no_retry = UrllibRetry(
            total=0,
            status=0,
            respect_retry_after_header=False,
        )
        for prefix in ('https://', 'http://'):
            sp._session.get_adapter(prefix).max_retries = no_retry
        return sp

    def _init_client(self, idx):
        """Initialize the spotipy client at credential index idx."""
        self._sp = SpotifyRateLimiter._build_client(
            idx, credentials_list=self._credentials
        )
        self._current_idx = idx
        # Point _call_times to this app's deque
        self._call_times = self._app_call_times[idx]
        self._calls_since_rotation = 0

    def _rotate_client(self) -> bool:
        """Switch to next available Spotify app. Returns True if rotated."""
        if len(self._credentials) <= 1:
            return False
        next_idx = (self._current_idx + 1) % len(self._credentials)
        if next_idx == self._current_idx:
            return False  # wrapped around
        log.warning(f"  Rotating to Spotify app #{next_idx + 1}/{len(self._credentials)}")
        self._init_client(next_idx)
        self._consecutive_429s = 0
        time.sleep(random.uniform(0.3, 1.0))  # brief pause before using new app
        return True

    def _proactive_rotate(self) -> bool:
        """Proactively rotate to the app with the most rest time.

        Called after every ROTATION_BATCH_SIZE calls to distribute load.
        Picks the app whose last call was longest ago (most rested).
        """
        if len(self._credentials) <= 1:
            return False

        now = time.time()
        best_idx = -1
        best_rest_time = -1

        for i in range(len(self._credentials)):
            if i == self._current_idx:
                continue
            app_deque = self._app_call_times[i]
            # Clean expired entries
            while app_deque and app_deque[0] < now - 30:
                app_deque.popleft()
            calls_in_window = len(app_deque)
            # Pick app with fewest calls in window (most capacity)
            # If tied, pick the one whose last call was oldest
            last_call = app_deque[-1] if app_deque else 0
            rest_time = now - last_call if last_call else 999
            # Score: lower calls = better; more rest = better
            score = (self._max_per_30s - calls_in_window) * 100 + rest_time
            if score > best_rest_time:
                best_rest_time = score
                best_idx = i

        if best_idx < 0:
            return False

        # Check if best app has capacity
        best_deque = self._app_call_times[best_idx]
        if len(best_deque) >= self._max_per_30s * 0.9:
            # Best alternative is also near limit — stay on current
            return False

        old_idx = self._current_idx
        old_calls = len(self._call_times)
        self._init_client(best_idx)
        new_calls = len(self._call_times)
        log.info(f"  Proactive rotation: app #{old_idx + 1}({old_calls} in window) "
                 f"→ app #{best_idx + 1}({new_calls} in window) "
                 f"[total: {self._total_calls} calls]")
        time.sleep(random.uniform(0.15, 0.5))  # brief pause
        return True

    @property
    def total_calls(self) -> int:
        return self._total_calls

    def _throttle(self):
        """Proactively wait if approaching the rolling 30s window limit.

        With multiple apps: proactively rotates after ROTATION_BATCH_SIZE calls
        to distribute load and avoid hitting any single app's rate limit.
        """
        # --- Proactive rotation (before rate-limit check) ---
        self._calls_since_rotation += 1
        if (len(self._credentials) > 1
                and self._calls_since_rotation >= Config.ROTATION_BATCH_SIZE):
            self._proactive_rotate()

        now = time.time()
        # Remove calls outside the 30-second window
        while self._call_times and self._call_times[0] < now - 30:
            self._call_times.popleft()

        calls_in_window = len(self._call_times)

        if calls_in_window >= self._max_per_30s:
            # At limit — try rotating to another app first
            if len(self._credentials) > 1 and self._proactive_rotate():
                # Switched to a less-loaded app, re-check its window
                now = time.time()
                while self._call_times and self._call_times[0] < now - 30:
                    self._call_times.popleft()
                calls_in_window = len(self._call_times)

            if calls_in_window >= self._max_per_30s:
                # Still at limit (all apps busy) — wait it out
                oldest = self._call_times[0]
                wait = oldest + 30 - now + random.uniform(1.0, 3.0)
                if wait > 0:
                    log.debug(f"  Rate limiter: app #{self._current_idx + 1} "
                              f"{calls_in_window}/{self._max_per_30s} calls in window, "
                              f"cooling {wait:.1f}s")
                    time.sleep(wait)
                    now = time.time()
                    while self._call_times and self._call_times[0] < now - 30:
                        self._call_times.popleft()
        elif calls_in_window >= self._max_per_30s * 0.8:
            # Approaching limit — add extra delay
            time.sleep(random.uniform(0.3, 0.8))
        else:
            # Well below limit — minimal jittered delay
            time.sleep(random.uniform(0.08, 0.2))

        self._call_times.append(time.time())
        self._total_calls += 1
        self._app_total_calls[self._current_idx] = self._app_total_calls.get(self._current_idx, 0) + 1

        # Periodic stats logging (every 100 calls)
        if self._total_calls % 100 == 0:
            stats = ', '.join(f"#{i+1}:{self._app_total_calls.get(i, 0)}"
                              for i in range(len(self._credentials)))
            log.info(f"  API call stats — total: {self._total_calls}, per-app: [{stats}]")

    def _call(self, method_name: str, *args, **kwargs):
        """Call a Spotify API method with rate limiting and progressive backoff.

        On 429: uses progressive backoff (5s -> 7.5s -> 11s -> ... -> 60s max)
        instead of trusting Spotify's Retry-After header, which often says 86400s
        (24h) even though the actual rolling window is only 30 seconds.

        NEVER gives up — when all apps are 429'd, sleeps BAN_SLEEP_CYCLE (2min)
        then retries all apps in round-robin until one succeeds.
        """
        last_err = None
        first_429_time = None  # Track when 429s started

        attempt = 0
        while True:  # Never give up
            method = getattr(self._sp, method_name)
            self._throttle()
            try:
                result = method(*args, **kwargs)
                self._consecutive_429s = 0  # Reset on success
                if first_429_time:
                    elapsed = time.time() - first_429_time
                    log.info(f"  429 resolved after {elapsed:.0f}s — continuing")
                return result

            except spotipy.exceptions.SpotifyException as e:
                last_err = e
                if e.http_status == 429:
                    self._consecutive_429s += 1
                    attempt += 1

                    # Read Retry-After for logging only (we do NOT trust large values)
                    header_retry_after = 5
                    if hasattr(e, 'headers') and e.headers:
                        try:
                            header_retry_after = int(e.headers.get('Retry-After', 5))
                        except (ValueError, TypeError):
                            pass

                    # Track when 429s started
                    if first_429_time is None:
                        first_429_time = time.time()
                    elapsed_429 = time.time() - first_429_time

                    # Check timeout — if stuck for too long, skip this item
                    if elapsed_429 > Config.MAX_CONTINUOUS_429_SECONDS:
                        log.warning(
                            f"  429 timeout: {elapsed_429:.0f}s > "
                            f"{Config.MAX_CONTINUOUS_429_SECONDS}s. "
                            f"Skipping this call (total calls: {self._total_calls})"
                        )
                        raise SpotifyRateLimitBan(retry_after=int(elapsed_429))

                    # Try rotating through ALL other apps before backing off
                    rotated = False
                    if len(self._credentials) > 1 and self._consecutive_429s >= 2:
                        start_idx = self._current_idx
                        for _ in range(len(self._credentials) - 1):
                            if self._rotate_client():
                                rotated = True
                                # Quick test on new app
                                try:
                                    test_method = getattr(self._sp, method_name)
                                    result = test_method(*args, **kwargs)
                                    self._consecutive_429s = 0
                                    log.info(f"  App #{self._current_idx + 1} succeeded after rotation")
                                    return result
                                except spotipy.exceptions.SpotifyException as e2:
                                    if e2.http_status == 429:
                                        log.warning(f"  App #{self._current_idx + 1} also 429'd")
                                        continue
                                    else:
                                        raise
                            else:
                                break
                        # All apps tried and failed — wait and retry
                        if rotated:
                            log.warning(
                                f"  ALL {len(self._credentials)} apps are 429'd "
                                f"({elapsed_429:.0f}s total, "
                                f"Retry-After={header_retry_after}s ignored). "
                                f"Sleeping {Config.BAN_SLEEP_CYCLE}s then retrying..."
                            )
                            time.sleep(Config.BAN_SLEEP_CYCLE)
                            # Reset to first app after sleep
                            self._init_client(0)
                            self._consecutive_429s = 0
                            continue

                    # Single-app backoff
                    backoff = min(
                        Config.RETRY_BACKOFF_START * (Config.RETRY_BACKOFF_MULTIPLIER ** (self._consecutive_429s - 1)),
                        Config.RETRY_BACKOFF_CAP
                    )
                    wait = backoff + random.uniform(1, 5)

                    log.warning(
                        f"  429 (app #{self._current_idx + 1}, "
                        f"retry {self._consecutive_429s}, attempt {attempt}). "
                        f"Header Retry-After={header_retry_after}s (ignored). "
                        f"Backoff={wait:.0f}s. "
                        f"429s for {elapsed_429:.0f}s — will keep retrying"
                    )
                    time.sleep(wait)

                elif e.http_status in (500, 502, 503):
                    attempt += 1
                    wait = (2 ** min(attempt, 5)) + random.uniform(1, 4)
                    log.warning(f"  Server error {e.http_status}. Retrying in {wait:.0f}s "
                                f"(attempt {attempt})")
                    time.sleep(wait)
                else:
                    raise

            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                    requests.exceptions.ReadTimeout) as e:
                last_err = e
                attempt += 1
                wait = (2 ** min(attempt, 5)) + random.uniform(1, 4)
                log.warning(f"  Connection error: {type(e).__name__}. "
                            f"Retrying in {wait:.0f}s (attempt {attempt})")
                time.sleep(wait)

    # ------ Proxy common Spotify API methods ------
    def search(self, *args, **kwargs):
        return self._call("search", *args, **kwargs)

    def artists(self, *args, **kwargs):
        return self._call("artists", *args, **kwargs)

    def artist(self, *args, **kwargs):
        return self._call("artist", *args, **kwargs)

    def playlist_items(self, *args, **kwargs):
        return self._call("playlist_items", *args, **kwargs)

    def playlist(self, *args, **kwargs):
        return self._call("playlist", *args, **kwargs)

    def artist_top_tracks(self, *args, **kwargs):
        return self._call("artist_top_tracks", *args, **kwargs)

    def album_tracks(self, *args, **kwargs):
        return self._call("album_tracks", *args, **kwargs)

    def tracks(self, *args, **kwargs):
        return self._call("tracks", *args, **kwargs)


# ============================================================================
# VIETNAMESE DETECTION
# ============================================================================
class VietnameseDetector:
    """
    Phát hiện text tiếng Việt bằng nhiều phương pháp kết hợp:
    1. Ký tự đặc trưng tiếng Việt (đ, ă, ơ, ư, ê, ô + dấu kết hợp)
    2. Regex patterns cho từ tiếng Việt phổ biến
    3. langdetect (optional fallback)
    """

    COMMON_VN_WORDS = re.compile(
        r'\b(?:'
        r'yêu|thương|nhớ|buồn|vui|tình|đời|người|'
        r'trái tim|hạnh phúc|cô đơn|chia tay|quên|mưa|nắng|'
        r'giấc mơ|sài gòn|hà nội|việt nam|'
        r'lòng|đêm|ngày|trăng|biển|'
        r'không|những|được|đến|đã|rồi|thôi|'
        r'nơi|đây|hãy|khóc|xinh|đẹp|'
        r'xin lỗi|yêu thương|nhạc|bài hát|'
        r'phải|cùng|lắm|thật|nữa|mình|'
        r'cũng|vẫn|chưa|bao giờ|luôn|từng'
        r')\b',
        re.IGNORECASE | re.UNICODE
    )

    # Garbage artist name patterns: dates, pure numbers, view counts, parse artifacts
    GARBAGE_NAME_RE = re.compile(
        r'^(?:'
        r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}(?:,?\s*\d{4})?|'  # Mon DD[, YYYY]
        r'\d{1,2}/\d{1,2}(?:/\d{2,4})?|'                                          # DD/MM[/YYYY]
        r'\d{4}-\d{2}(?:-\d{2})?|'                                                 # YYYY-MM[-DD]
        r'\d{1,2}\s+(?:tháng|thg)\s+\d{1,4}|'                                      # Vietnamese date
        r'(?:Thg|Tháng)\s+\d{1,2}|'                                                # Thg N
        r'\d[\d.,]*\s*[KMBkmb]?\s*(?:views?|lượt\s*xem|subscribers?|'
        r'người\s*đăng\s*ký|người\s*theo\s*dõi)\s*|'                               # View/subscriber counts
        r'\d(?:\s+\d)+|'                                                            # Spaced digits: 1 9 6 7
        r'[\d,\.]+|'                                                                # Pure numbers
        r'(?:&|and)\s+.+'                                                           # Parse artifacts: "& Bach"
        r')$',
        re.IGNORECASE
    )

    # Non-Vietnamese diacritics (European: German, French, Nordic, etc.)
    NON_VN_DIACRITICS = set(
        'äëïöüÿñçøåæœß'
        'ÄËÏÖÜŸÑÇØÅÆŒ'
    )

    # Diacritics shared between Vietnamese and French/other Romance languages
    # These alone (é è ê à ù ô â î û) do NOT prove Vietnamese
    SHARED_FRENCH_VN_DIACRITICS = set(
        'éèêàùôâîûÉÈÊÀÙÔÂÎÛ'
        'áíóúýÁÍÓÚÝ'  # acute accents shared with Spanish/Portuguese
    )

    # Circumflex vowels shared with French/Portuguese — NOT uniquely Vietnamese
    # Vietnamese uses these but also adds tone marks (ấ ầ ẩ ẫ ậ ế ề ể ễ ệ ố ồ ổ ỗ ộ)
    # Plain â ê ô alone appear in Portuguese (Antônio, Bethânia) and French (château)
    SHARED_CIRCUMFLEX_CHARS = set('âêôÂÊÔ')

    # Non-artist channel patterns — aggregation/compilation channels, not performing artists
    NON_ARTIST_CHANNEL_RE = re.compile(
        r'^(?:'
        r'.*\b(?:Channel|Kênh)(?:\s+.*)?|'          # Vie Channel, BLUESEA channel
        r'.*\bTV$|'                                     # Guitar Coffee TV
        r'.*\bMedia$|'                                  # CT Media, MeMe Media
        r'.*\bMedia\s+Music$|'                          # NH4T Media Music
        r'.*\bRemix$|'                                  # H2O Remix, Air Remix, Beta Remix
        r'.*\bVinahouse$|'                              # H2O Vinahouse
        r'.*\bRecords$|'                                # Luna Đào Records, ICM RECORDS
        r'.*\bEntertainment$|'                          # MT Entertainment
        r'.*\bProduction[s]?$|'                         # Productions
        r'.*\bCover$|'                                  # Trạm Cover
        r'.*\bKaraoke\b.*|'                             # Karaoke channels
        r'Nhạc Sống\b.*|'                               # Nhạc Sống VN365
        r'.*\bMixes?$'                                  # CT Mixes
        r')$',
        re.IGNORECASE
    )

    # Known foreign artists that slip through due to shared diacritics (â ê ô)
    FOREIGN_ARTISTS_BLOCKLIST = {
        # Brazilian / Portuguese
        'antônio carlos jobim', 'tom jobim', 'maria bethânia', 'caetano veloso',
        'gilberto gil', 'gal costa', 'elis regina', 'vinícius de moraes',
        'djavan', 'chico buarque', 'joão gilberto', 'nara leão',
        'jorge ben jor', 'milton nascimento', 'marisa monte', 'seu jorge',
        'ana carolina', 'roberto carlos', 'ivan lins', 'toquinho',
        'paulinho da viola', 'jorge ben', 'tim maia', 'alceu valença',
        'geraldo azevedo', 'zé ramalho', 'lenine', 'arnaldo antunes',
        'adriana calcanhotto', 'cássia eller', 'leny andrade', 'rosa passos',
        'elza soares', 'ney matogrosso', 'jair rodrigues', 'beth carvalho',
        'clara nunes', 'cartola', 'luiz gonzaga', 'hermeto pascoal',
        'egberto gismonti', 'baden powell', 'dorival caymmi',
        'ary barroso', 'pixinguinha', 'choro rasgado',
        # French
        'edith piaf', 'charles aznavour', 'jacques brel', 'serge gainsbourg',
        'jean-jacques goldman', 'françoise hardy', 'france gall',
        'claude françois', 'michel sardou', 'alain souchon',
        'francis cabrel', 'renaud', 'georges brassens', 'léo ferré',
        'yves montand', 'dalida', 'mireille mathieu', 'charles trenet',
        'joe dassin', 'patrick bruel', 'zaz', 'stromae',
        # Balkan (Bosnian/Serbian) — uses Đ like Vietnamese
        'đani', 'djani', 'emir đurović', 'emir djurovic',
        # Finnish / Nordic
        'typerä typerä mies',
        # Classical / Symphony orchestras
        'hcmc conservatory symphony orchestra',
    }

    CHILDREN_ARTIST_PATTERNS = re.compile(
        r'(?:'
        r'Thiếu Nhi|Nhi Đồng|Nhạc Thiếu Nhi|'
        r'Góc Nhạc Thiếu Nhi|'
        r'Tốp Ca\b|Tốp ca CLBTN|'
        r'Bé [A-ZÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬĐÊẾỀỂỄỆÔỐỒỔỖỘƠỚỜỞỠỢƯỨỪỬỮỰ][a-zàáảãạăắằẳẵặâấầẩẫậđêếềểễệôốồổỗộơớờởỡợưứừửữự]+|'
        r'Giai Điệu Tuổi Thơ|Mầm Chồi Lá|Xuân Mai|Rain Kids|'
        r'Tuổi Thơ|Mầm Non'
        r')',
        re.IGNORECASE | re.UNICODE
    )
    CHILDREN_ALBUM_PATTERNS = re.compile(
        r'(?:'
        r'Thiếu Nhi|Nhi Đồng|Trẻ Em|Mầm Non|'
        r'Bé Học|Bé Hát|Bé Yêu|'
        r'Kids|Children|Nursery|Lullaby'
        r')',
        re.IGNORECASE | re.UNICODE
    )
    CHILDREN_TRACK_PATTERNS = re.compile(
        r'(?:'
        r'Thiếu Nhi|Nhi Đồng|'
        r'Bé Ơi|Bé Yêu Ơi|'
        # English nursery rhymes / children's songs
        r'\bMary Had A Little\b|\bFive Little Ducks?\b|'
        r'\bIf You.re Happy\b|\bSkip To My Lou\b|'
        r'\bMuffin Man\b|\bThis Old Man\b|'
        r'\bLittle Indian\b|\bFarmer In The Dell\b|'
        r'\bTwinkle Twinkle\b|\bHumpty Dumpty\b|'
        r'\bJack And Jill\b|\bBaa Baa Black\b|'
        r'\bHickory Dickory\b|\bItsy Bitsy\b|'
        r'\bOld MacDonald\b|\bThree Blind Mice\b|'
        r'\bHot Cross Bun\b|\bWheels On The Bus\b|'
        r'\bI Went To School\b|\bLondon Bridge Is Falling\b|'
        r'\bTen Little Indian\b|\bThis Is The Way\b|'
        r'\bMy Bonnie\b|\bRed River Valley\b'
        r')',
        re.IGNORECASE | re.UNICODE
    )

    KNOWN_ARTISTS = {
        # ── V-Pop Mainstream (active 2015-2026) ──
        'sơn tùng mtp', 'sơn tùng m-tp', 'son tung mtp',
        'đen vâu', 'hà anh tuấn',
        'đông nhi', 'bích phương', 'chi pu', 'hòa minzy', 'erik',
        'min', 'soobin hoàng sơn', 'soobin', 'isaac',
        'đức phúc', 'hương tràm', 'hương giang', 'bùi anh tuấn',
        'vũ cát tường', 'hari won', 'trọng hiếu',
        'phan mạnh quỳnh', 'trúc nhân', 'bảo thy',
        'khởi my', 'kelvin khánh',
        'ngô kiến huy', 'quốc thiên',

        # ── V-Pop 2009-2014 era (modern pop, not old-genre) ──
        'uyên linh', 'thanh duy', 'đinh hương',
        'khổng tú quỳnh', 'maya', 'will', 'will 365',
        'la thăng', 'v.music', 'uni5',
        'đinh mạnh ninh',
        'yanbi', 'mr.t', 'loren kid', 'pti',
        'emily', 'hakoota dũng hà', 'st.319',

        # ── V-Pop / Ballad (2018-2026) ──
        'hoàng thùy linh', 'amee', 'orange', 'mono', 'lyly',
        'tóc tiên', 'phương ly', 'bảo anh', 'anh tú',
        'nguyễn trần trung quân', 'hoàng dũng', 'thái đinh',
        'vũ.', 'mr siro', 'only c', 'vương anh tú', 'andiez',
        'nguyễn hải phong', 'hoàng tôn', 'wendy thảo',
        'jsol', 'đỗ hoàng dương', 'quân a.p', 'hải tú', 'tăng duy tân',
        'phùng khánh linh', 'suni hạ linh', '365daband',
        'wren evans', 'dương domic', 'quang hùng masterd',
        'ali hoàng dương', 'juky san', 'vũ thảo my', 'bùi công nam',
        'tăng phúc', 'lâm bảo ngọc', 'tiên cookie',
        'hứa kim tuyền', 'phạm anh duy', 'dương hoàng yến', 'hà nhi',
        'cara', 'trịnh thăng bình',
        'khắc hưng', 'dick',
        'rhyder', 'rtee', 'han sara',
        # ── Tây Nguyên Sound ──
        'tây nguyên sound', 'lil wuyn', 'double2t',
        'nhật hoàng', 'hải đăng doo',
        'tùng tea', 'pc', 'tofutns', '1ng', 'namlee',

        # ── Bạn Có Tài Mà (BCTM) ──
        'bạn có tài mà', 'ngắn', 'anh khơ me',
        'chúc hỷ', 'ngọc dolil', 'nasty5', 'ron phan',
        'công hòa', 'dopvz', 'an khán', 'megashock',

        # ── Hip-Hop / Rap — Rap Việt S1-S4 + Scene ──
        'karik', 'binz', 'suboi', 'wowy', 'rhymastic', 'justatee',
        'đạt g', 'masew', 'pháo',
        'tlinh', 'rpt mck', 'obito', 'wxrdie',
        'andree right hand', 'low g', 'hieuthuhai', 'coldzy',
        'b ray', 'kimmese', 'qnt',
        'dế choắt', 'gducky', 'ricky star', 'seachains',
        'blacka', 'b-wine', '24k.right', 'liu grace',
        'robber', 'gill', '16 typh', 'tage', 'lăng ld',
        'gonzo', 'thành draw', 'hurrykng', 'smo',
        'pháp kiều', 'mikelodic', 'ogenus', 'tez',
        'yuno bigboi', 'dlow', 'manbo',
        'dangrangto', 'coolkid', 'lk', 'datmaniac',
        'nah', 'sol7', '14 casper', 'young h',
        'freaky', 'pjpo', '2can', 'phúc du',
        "lil' knight", 'mai âm nhạc', 'xám',
        'tiêu minh phụng', 'vsoul',

        # ── Nhóm nhạc / Collectives ──
        'spacespeakers', 'cá hồi hoang', 'da lab',
        'ngọt', 'chillies', 'gerdnang', '95g',
        'hustlang', 'lộn xộn band',

        # ── EDM / Electronic / Producer ──
        'touliver', 'slimv', 'hoaprox',
        'onionn', 'duongk',
        'grey d',

        # ── Underground / Indie ──
        'the flob', '7uppercuts', 'madihu',

        # ── R&B / Soul ──
        'ciin', 'grey d', 'vũ.', 'hoàng dũng', 'phùng khánh linh',
        'suni hạ linh', 'hà nhi', 'juky san', 'lyly',

        # ── Anh Trai Say Hi / Anh Trai Vượt Ngàn Chông Gai ──
        'hieuthuhai', 'đức phúc', 'isaac', 'erik', 'quang hùng masterd',
        'rhyder', 'dương domic', 'pháo', 'negav',
        'hùng huỳnh', 'dương edward', 'anh tú atus',
        'song luân', 'quang trung', 'đỗ phú quí',
        'st sơn thạch', 'cường seven', 'trọng hiếu',

        # ── Rap Việt Gen Z (2022-2026) ──
        'hustlang robber', 'rap nhà làm', '24k.right',
        'lật mặt', 'dick', 'tez', 'rtee',
        'bình gold', 'lil wuyn', 'sol7', 'vsoul',
        'khói', 'nah', '2can', 'freaky',
        'kidz', 'shiki', 'lê hiếu',
        'tvk', 'type.r', 'lục lăng', 'nâu',

        # ── Pop / Ballad GenZ (2021-2026) ──
        'tăng duy tân', 'wren evans', 'mono', 'amee',
        'Orange', 'miu lê', 'min', 'chi pu',
        'trung quân', 'anh tú', 'han sara', 'lâm bảo ngọc',
        'myra trần', 'dương hoàng yến', 'cara',
        'phạm anh duy', 'thái đinh', 'andiez',
        'da lab', 'chillies', 'ngọt', 'cá hồi hoang',
        'hoàng thùy linh', 'bích phương', 'mỹ anh',
        'hoàng dũng', 'đông nhi',
        'tlinh', 'pháo', 'suboi', 'liu grace',

        # ── EDM / Producer GenZ ──
        'hoaprox', 'nimbia', 'minsicko', 'get weird',
        'onionn', 'duongk', 'slimv', 'touliver',
        'masew', 'k-icm',

        # ── Nhạc Sĩ / Producers (active, GenZ-relevant) ──
        'hứa kim tuyền', 'khắc hưng',
        'tiên cookie', 'vương anh tú', 'phan mạnh quỳnh',
        'nguyễn minh cường', 'đỗ hiếu', 'nguyễn hồng thuận',
        'nguyễn hải phong',

        # ── Spotify VN Chart Top 200 (March 2026) — newly added ──
        'hngle', 'vstra', 'marzuz', 'puppy',
        'shartnuss', 'nhonho', 'rio', 'fishy', 'maydays',
        'ronboogz', 'lil zpoet', 'w/n', 'đặng vĩnh thịnh',
        'quang đăng trần', 'buitruonglinh', 'dfoxie37',
        't.r.i', 'vương bình', 'kai đinh', '52hz',
        'việt anh', 'đức trường', 'ánh sáng aza',
        'f47', 'đỗ hoàng long', 'dab', 'luxuyen',
        'minh đinh', 'tia', 'solmee', 'monstar',
        'nguyễn trọng tài', 'bon nghiêm', 'changg',
        'táo', 'tyronee', 'lou hoàng', 'nhâm phương nam',
        'cloud 5', 'kha', 'jaykii',
        'thành luke', 'kun', 'emcee l',
        'emcee l (da lab)', 'hino', 'koo',
        'jey b', 'lamoon', 'donal', 'tuann',
        'hoàng rob', 'lê thiện hiếu', 'only c',
        'quân a.p', 'quang hùng masterd',
        'bảo anh', 'phương ly', 'tóc tiên',
        'trọng nhân', 'tiểu mỹ', 'f47 cover',
        'w/n', '2pillz', 'antransax', 'new$oulz',
        'helinn', 'hà an huy', 'muộii',
        'muộii (starry night)', 'badbies',
        'vũ phụng tiên', 'hoangkiet', 'itsnk',
        'dyteller', 'suzie mk', 'zer nguyễn',
        'mechill', 'hipz', 'v#', 'anh bằng',
        'công dương', '30 pictures',
        'nguyễn lâm thảo tâm',

        # ── Expanded from Spotify VN Charts 2026 + Wikipedia V-Pop ──
        'mason nguyen', 'khoi vu', 'khoi vũ',
        'ân ngờ', 'bigdaddy', 'big daddy', 'jun phạm',
        'wean', 'wean le', 'jaysonlei', 'trung trần',
        'nhism', 'phankeo', 'tr.d',
        'teugyungboy', 'teuyungboy', 'ann nguyễn',
        'lelarec',
        'noo phước thịnh', 'noo phuoc thinh',

        # ── Thêm nghệ sĩ từ Spotify VN historical charts (2019-2026) ──
        'hoàng duyên', 'trang', 'trang hàn',
        'phan duy anh', 'thiều bảo trâm',
        'nguyên hà', 'hồ ngọc hà',
        'bùi lan hương', 'mỹ anh',
        'hoàng yến chibi', 'phạm quỳnh anh',
        'thùy chi', 'văn mai hương',
        # Rap / underground trending 2023-2026
        'kewtiie', 'phát hồ', 'right',
        'pjnboys', 'rtrt', 'sol',
        'bích phương', 'chipu', 'đỗ hoàng dương',
        '95g', 'gerdnang',

        # ── Newly added: young / indie / rap (from research 2026-04) ──
        'bray', 'yp', 'goku',  # Rap Việt / King of Rap
        '$eth', 'krazynoise', 'nger',  # Underground rap
        'rpt groovie', 'sol bass', '16brt',  # Underground / new gen
        'thái vg',  # Rap Việt coach
        # Producer, trending chart collabs
        'pinny', 'minh huy',  # New trending 2026
        'ari',  # Collab Hngle chart hit
        # Band mới
        'lộn xộn band', 'cá hồi hoang',
        # Acoustic / Indie
        'thịnh suy', 'hải sâm', 'phạm đình thái ngân',
        'nguyên., ', 'the cassette',
        # Show contestants / Rising stars
        'dương edward', 'hùng huỳnh',
        'đỗ phú quí', 'st sơn thạch',
        'song luân', 'quang trung',
        'captain boy', 'vsoulization',
        'phạm thanh hà', 'anh quân (atsh)',

        # ── Expansion 2026-04 — seed artists added to whitelist ──
        # V-Pop Mainstream thêm
        'jack', 'j97', 'jack j97', 'hồ ngọc hà', 'hari won',
        'miu lê', 'minh hằng', 'gil lê', 'khởi my',
        'phạm quỳnh anh', 'thùy chi', 'hương giang',
        'lou hoàng', 'hoàng yến chibi', 'khổng tú quỳnh',
        'trang pháp', 'ái phương', 'will', 'emily',
        'nguyên hà', 'mỹ anh', 'phương vy', 'phương mỹ chi',
        'nam cường', 'đinh hương', 'maya', 'wendy thảo',
        'sĩ thanh', 'hạnh sino', 'mlee', '365daband',
        'hiền thục', 'kelvin khánh', 'ninh dương lan ngọc',
        # V-Pop GenZ thêm
        'hoàng duyên', 'thiều bảo trâm', 'thiều bảo trang',
        'châu đăng khoa', 'changmie', 'xesi', 'osad',
        'w/n', 'hải sâm', 'phát hồ', 'monstar',
        '52hz', 't.r.i', 'lynk lee', 'thái trinh',
        'kai đinh', 'hoàng rob', 'hải tú', 'tiểu mỹ',
        'nhâm phương nam', 'kha', 'lamoon', 'donal',
        'tuann', 'hino', 'cloud 5', 'helinn',
        'muộii', 'vũ phụng tiên', 'solmee', 'phí phương anh',
        # Band / Groups thêm
        'uni5', 'la thăng', 'v.music', 'lipb', 'lime',
        'the flob', '7uppercuts', 'the cassette',
        'spacespeakers', 'sgo48', 'st.319',
        # Rap thêm
        'pjnboys', '2pillz', 'nger', '$eth',
        'krazynoise', 'yp', 'goku', 'rpt groovie', '16brt',
        'thái vg', 'khói', 'type.r', 'lục lăng',
        'nâu', 'shiki', 'emcee l',
        'tiêu minh phụng', 'vũ duy khánh', 'tvk',
        'kewtiie', 'right', 'rtrt', 'sol', 'pjpo',
        "lil' knight", 'yanbi', 'mr.t', 'loren kid',
        # EDM / Producer thêm
        'nimbia', 'dtap', 'get looze', 'dustee', 'duongk', 'tinle',
        # TV Show thêm
        'cao bá hưng', 'gia nghi', 'đông hùng', 'bảo trâm',
        'anh khang', 'bảo kun', 'đinh mạnh ninh', 'trà my',
        'trương thảo nhi',
        # Charts VN
        'hngle', 'vstra', 'marzuz', 'ronboogz', 'lil zpoet',
        'quang đăng trần', 'buitruonglinh', 'dfoxie37',
        'vương bình', 'đặng vĩnh thịnh', 'luxuyen', 'minh đinh',
        'đỗ hoàng long', 'dab', 'bon nghiêm', 'changg',
        'táo', 'tyronee', 'thành luke', 'kun', 'koo',
        'vct', 'trung quân idol',
        'jey b', 'suzie mk', 'zer nguyễn', 'hipz', 'ân ngờ',
        'mason nguyen', 'khoi vu', 'jaysonlei', 'trung trần',
        'nhism', 'phankeo', 'lelarec', 'ann nguyễn',
        'fishy', 'maydays', 'rio', 'nhonho', 'shartnuss',
        'puppy', 'việt anh', 'đức trường', 'tia',
        'new$oulz', 'antransax', 'badbies', 'hoangkiet', 'itsnk',
        'dyteller', '30 pictures', 'nguyễn lâm thảo tâm', 'pinny',
        'hà okio', 'nguyễn minh cường', 'đỗ hiếu',
        'nguyễn hồng thuận', 'nguyễn hải phong', 'nguyễn trọng tài',
        'phạm toàn thắng', '95g', 'gerdnang', 'hustlang',
        'crazytown', 'd.u.n.g', 'nguyễn phi hùng', 'trà my idol',
        'đinh tiến đạt', 'song luân', 'nicky', 'đỗ phú quí',
        'dương edward',

        # ── Indie / Bedroom Pop / Singer-Songwriter (bổ sung 2026) ──
        # Những nghệ sĩ indie/GenZ thật sự phổ biến nhưng chưa có trong list
        'nân',              # indie ballad; rất phổ biến với GenZ 2022-2024
        'tiên tiên',        # indie; "Say You Do", vẫn active 2020s
        'phương my',        # indie/bedroom pop; rising 2021-2024
        'beepbeepchild',    # indie/lo-fi; trending underground 2023-2024
        'tanny ng',         # underground indie; collab scene 2022-2024
        'hoa vinh',         # Tây Nguyên-influenced; "Thích Mình Duyên" viral 2022
        'thoại nghi',       # indie/ballad GenZ; emerging 2023-2024

        # ── GenZ Pop Mainstream (bổ sung) ──
        'hiền hồ',          # ballad/R&B; rất phổ biến 2020-2024
        'phương anh idol',  # Vietnam Idol 2023; mainstream rising

        # ── Rap / Hip-Hop (layer bổ sung 2024-2026) ──
        'mck',              # MCK solo profile (khác "rpt mck" group đã có)
        'nhat nguyen',      # Irish-Vietnamese rapper; "Staying" viral 2021
        'ozn',              # underground producer/rapper collab 2022-2024
        'fntastic',         # underground rap collab 2022-2024
        'the thien',        # emerging pop/indie 2024
        'nakim',            # underground rap 2023-2024
        'loathecreed',      # underground rap/trap 2023-2024

        # ── Expansion 2026-06 — recent awards, charts, and TV breakouts ──
        'nguyễn hùng', 'nguyen hung',
        'sơn.k', 'son.k',
        'mylina',
        'saabirose',
        'chi xê', 'chi xe',
        'đào tử a1j', 'dao tu a1j', 'a1j',
        'olew', 'o.lew',

        # ── Anh Trai Say Hi 2024-2025 / Rap Việt finalists ──
        'captain', 'captain boy',
        'gin tuấn kiệt', 'gin tuan kiet',
        'vũ thịnh', 'vu thinh',
        'thái ngân', 'thai ngan',
        'cody nam võ', 'cody nam vo', 'codynamvo',
        'bùi duy ngọc', 'bui duy ngoc',
        'hải nam', 'hai nam',
        'ryn lee', 'otis', 'congb',
        'đỗ nam sơn', 'do nam son',
        'lohan', 'dillan hoàng phan', 'dillan hoang phan',
        'jey b', 'jaysonlei',
        '7dnight', 'danmy',
        'huỳnh công hiếu', 'huynh cong hieu',
        'kellie', 'hoàng anh', 'hoang anh',

        # ── Active 9x-era artists with current Gen Z reach ──
        'khắc việt', 'khac viet',
        'hồ quang hiếu', 'ho quang hieu',
        'lê bảo bình', 'le bao binh',
        'hải sâm', 'hai sam', 'haisam',
        'châu khải phong', 'chau khai phong',
        'đình dũng', 'dinh dung',
        'đinh tùng huy', 'dinh tung huy',
        'huy vạc', 'huy vac',
        'mỹ mỹ', 'my my',
        'võ hạ trâm', 'vo ha tram',

    }

    # Artist-level blocklists contain historical data-quality decisions and
    # must not reject newer releases from artists who are currently active.
    # Tracks by these artists still pass the normal year, popularity, seasonal,
    # children, foreign-language, version, and profanity filters.
    CURRENT_ARTISTS = {
        # Anh Trai Say Hi 2024
        'hieuthuhai', 'wean', 'công dương', 'cong duong',
        'anh tú atus', 'anh tu atus', 'anh tú', 'anh tu',
        'quang hùng masterd', 'quang hung masterd',
        'lou hoàng', 'lou hoang', 'quang trung', 'jsol',
        'đỗ phú quí', 'do phu qui', 'đỗ phú quý', 'do phu quy',
        'song luân', 'song luan', 'gin tuấn kiệt', 'gin tuan kiet',
        'quân a.p', 'quan a.p', 'hùng huỳnh', 'hung huynh',
        'nicky', 'tage', 'hải đăng doo', 'hai dang doo',
        'dương domic', 'duong domic', 'pháp kiều', 'phap kieu',
        'ali hoàng dương', 'ali hoang duong', 'negav',
        'captain', 'captain boy', 'hurrykng',
        'phạm đình thái ngân', 'pham dinh thai ngan', 'thái ngân', 'thai ngan',
        'phạm anh duy', 'pham anh duy', 'isaac', 'đức phúc', 'duc phuc',
        'erik', 'rhyder', 'quang anh rhyder', 'vũ thịnh', 'vu thinh',

        # Anh Trai Say Hi 2025
        'ngô kiến huy', 'ngo kien huy', 'buitruonglinh',
        'cody nam võ', 'cody nam vo', 'codynamvo',
        'vương bình', 'vuong binh', 'rio', 'karik', 'b ray', 'bray',
        'ryn lee', 'khoi vu', 'khôi vũ', 'bùi duy ngọc', 'bui duy ngoc',
        'phúc du', 'phuc du', 'hải nam', 'hai nam',
        'hustlang robber', 'robber', 'ogenus', 'otis', 'congb',
        'đỗ nam sơn', 'do nam son', 'lohan', 'sơn.k', 'son.k',
        'dillan hoàng phan', 'dillan hoang phan',
        'vũ cát tường', 'vu cat tuong', 'bigdaddy', 'big daddy',
        'tez', 'jey b', 'nhâm phương nam', 'nham phuong nam',
        'gill', 'jaysonlei', 'mason nguyen', 'mason nguyễn',

        # Rap Việt season 1-4 finalists
        'dế choắt', 'de choat', 'gducky', 'g.ducky',
        'rpt mck', 'mck', 'tlinh', 'gonzo', 'rpt gonzo',
        'thành draw', 'thanh draw', 'ricky star', 'lăng ld', 'lang ld',
        'seachains', 'blacka', 'b-wine', 'bwine', 'vsoul', 'v soul',
        "lil' wuyn", 'lil wuyn', 'hoàng anh', 'hoang anh', 'kellie', 'dlow',
        'double2t', 'double 2t', '24k.right', '24k right',
        'liu grace', 'huỳnh công hiếu', 'huynh cong hieu',
        'mikelodic', 'smo', 'pháp kiều', 'phap kieu',
        'coolkid', 'danmy', 'manbo', '7dnight', 'saabirose',

        # Current chart/mainstream artists and active 9x-era catalog
        'sơn tùng mtp', 'sơn tùng m-tp', 'son tung mtp',
        'đen vâu', 'den vau', 'soobin', 'soobin hoàng sơn',
        'đông nhi', 'dong nhi', 'tóc tiên', 'toc tien',
        'miu lê', 'miu le', 'trung quân', 'trung quan',
        'văn mai hương', 'van mai huong', 'hương tràm', 'huong tram',
        'quốc thiên', 'quoc thien', 'jun phạm', 'jun pham',
        'cường seven', 'cuong seven', 'khắc việt', 'khac viet',
        'hồ quang hiếu', 'ho quang hieu', 'lê bảo bình', 'le bao binh',
        'châu khải phong', 'chau khai phong', 'đình dũng', 'dinh dung',
        'đinh tùng huy', 'dinh tung huy', 'huy vạc', 'huy vac',
        'phương mỹ chi', 'phuong my chi', 'mỹ anh', 'my anh',
        'mỹ mỹ', 'my my', 'lâm bảo ngọc', 'lam bao ngoc',
        'hà nhi', 'ha nhi', 'võ hạ trâm', 'vo ha tram',
        'hải sâm', 'hai sam', 'haisam',
        'noo phước thịnh', 'noo phuoc thinh', 'bích phương', 'bich phuong',
        'bảo anh', 'bao anh', 'hòa minzy', 'hoa minzy',
        'hoàng thùy linh', 'hoang thuy linh',
    }

    # ── OLD-GENRE ARTIST BLOCKLIST ──
    # Bolero, Nhạc Vàng, Hải Ngoại, Dân Ca, Nhạc Trịnh, Trữ Tình, Cải Lương
    # These artists are real but outside GenZ scope → block at collection time
    OLD_GENRE_BLOCKLIST = {
        # Nhạc Vàng / Bolero / Trữ Tình
        'hương lan', 'đàm vĩnh hưng', 'dam vinh hung', 'mạnh quỳnh',
        'khưu huy vũ', 'ngọc sơn', 'tuấn vũ', 'trường vũ', 'chế linh',
        'chế thanh', 'elvis phương', 'như quỳnh', 'don hồ', 'bằng kiều',
        'quang lê', 'khánh ly', 'quách tuấn du', 'thanh ngân',
        'ân thiên vỹ', 'bằng cường', 'cẩm ly', 'bảo yến',
        'ngọc lan', 'anh thơ', 'quang dũng', 'hồ quang lộc',
        'phi nhung', 'lệ quyên',
        'thanh hà', 'mỹ linh', 'thu phương',
        'thanh lam', 'hồng nhung', 'tùng dương', 'tuấn ngọc',
        'trịnh công sơn', 'phú quang', 'trần tiến', 'trần lập',
        'phạm hồng phước', 'phương thanh',
        'lê cát trọng lý', 'trần thu hà', 'dương triệu vũ',
        'lương bích hữu', 'thanh bùi',
        'quang hà',
        # Hải Ngoại
        'lynda trang đài', 'don hồ', 'thanh tuyền', 'giao linh',
        'hoàng oanh', 'duy khánh', 'sơn tuyền', 'nguyên vũ',
        'nhật trường', 'duy quang', 'thanh lan', 'elvis phương',
        'thế sơn', 'nguyễn hưng', 'minh tuyết', 'phi bằng',
        'vũ khanh', 'nhật hạ', 'chung tử lưu', 'tâm đoan',
        'lý thu thảo', 'mai lệ quyên', 'đoàn minh',
        'tuan tu hai ngoai', 'dao phi duong', 'da thao my',
        'dam vinh hung',
        'nguyen van chung', 'luu chi vy', 'huynh nguyen cong bang',
        'duong trieu vu', 'son ca', 'thanh vinh', 'thanh ha',
        # 'da lab' removed — Da LAB is a modern band
        # Nhạc Đỏ / Cách Mạng
        'nsnd thanh hoa', 'trọng tấn', 'tân nhàn', 'quang thọ', 'thu hiền',
        # Cải Lương / Ca Cổ
        'ca cổ kiếp tằm', 'ngọc huyền', 'vũ linh',
        # Dân Ca / Quê Hương
        'thu hiền', 'trọng thanh', 'hồng phượng', 'kiều nga',
        # More old-genre artists from data analysis
        'bạch duy sơn', 'mỹ nhung', 'thanh hương', 'nguyễn hồng ân',
        'lâm hoàng nghĩa', 'ánh như', 'mai tuấn', 'quang lập',
        'sơn ca', 'hơi thở blues', 'mỹ linh', 'hồng phượng',
        'nguyễn hồng giang', 'hồng quyên', 'huỳnh thật',
        'phan đinh tùng', 'hồ quốc bửu',
        'diễm trang', 'võ hoàng lâm', 'trường kha', 'candy ngọc hà',
        'huệ ngọc nhã', 'trọng tấn', 'hamlet trương', 'ngọc huyền',
        'mỹ huyền', 'ngọc hân', 'phương thanh', 'mỹ hạnh',
        'ngọc anh', 'lệ thu', 'thiên đình', 'đan phương',
        'thu hiền', 'tâm đoan', 'yến khoa', 'sơn tuyền',
        'trọng thanh', 'chung tử lưu', 'nguyên vũ', 'lý thu thảo',
        'văn hương', 'hồng nhung', 'quang lê', 'lynda trang đài',
        'đoàn minh', 'quốc hùng', 'minh vương m4u', 'phi nhung',
        'lâm chấn kiệt', 'diễm thùy', 'nguyễn thành viên',
        'mai lệ quyên', 'tuấn ngọc',
        'lý tuấn kiệt', 'tường nguyên', 'diệu đan', 'mộng thi',
        'sơn hạ', 'đinh quốc cường', 'trường lê', 'tuấn khương',
        'thùy hương', 'vũ tuấn', 'lưu chí vỹ', 'diệu anh',
        'hồ trung dũng', 'thương võ', 'ngọc thảo', 'hana cẩm tiên',
        'tú quyên', 'như hoa', 'phương anh', 'hạ vân',
        'ngọc kiều oanh', 'vũ yến ngọc', 'dạ thảo my',
        'quốc chinh', 'trương khải minh', 'hà thanh tâm',
        'diệu hương', 'phượng mai', 'thiên trường',
        'lương gia hùng', 'thiên dũng', 'nhật trường',
        'hồ việt trung', 'lê gia bảo', 'thanh lam',
        'nb3 hoài bảo', 'nhật tinh anh', 'oanh tạ',
        'quang bình', 'khánh bình', 'đào anh thư',
        'thành đạt', 'kim tuyền', 'vũ hoàng', 'trường sơn',
        'khánh đơn', 'võ minh lê', 'thùy dương', 
        'linh hương luz',
        # From Phase 1 analysis — old-genre that slipped through
        'đình văn', 'hà phương', 'vinh tuấn', 'huy vũ', 'diễm liên',
        'bảo huy', 'dư anh', 'yến ly', 'hùng cường', 'trang hương',
        'hamlet trương', 'hiệp ca', 'khắc đông', 'đạt villa',
        'ngọc phụng', 'trung ruồi', 'đào nguyên ánh',
        # ── v12.0 data analysis — old-genre / trữ tình / quê hương (>50 tracks) ──
        'mai quốc huy', 'long nhật', 'mắt ngọc', 'nhóm mắt ngọc',
        'chiến thắng', 'sĩ phú', 'đan nguyên', 'lưu bích',
        'kasim hoàng vũ', 'châu gia kiệt', 'chế khanh',
        'la sương sương', 'băng châu', 'hồ lệ thu',
        'trường thanh', 'trịnh nam phương', 'trang anh thơ',
        'hồng trúc', 'ngọc hương', 'tiết duy hòa',
        'trang mỹ dung', 'huỳnh nhật huy', 'chu bin',
        'phi nguyễn', 'đinh kiến phong', 'anh ba trứng',
        'quốc đại', 'lưu hồng', 'sơn hà',
        'gia tiến', 'trương nguyên', 'đặng thái hiển',
        'đoàn lâm', 'mai hương', 'ngọc minh',
        'trung tự', 'trần thái hòa', 'mai tiến đạt',
        'lâm bảo phi', 'huy cường', 'ngọc huệ',
        'thúy huyền', 'võ thanh linh', 'lệ hằng',
        'hồng hạnh', 'ngọc liên', 'châu tuấn',
        'thúy hằng', 'trương phi hùng', 'quang sơn',
        'đặng thế luân', 'thu hường', 'giang thuỳ linh',
        'tạ quang thắng', 'quý dương', 'thu hương',
        'nhật linh', 'quốc cường', 'quỳnh trang',
        'ngọc bích', 'bùi thu huyền',
        'phương phương thảo', 'nhật trung',
        'du thiện', 'thanh vũ', 'duy trường',
        'giang trường', 'trung hậu', 'lý diệu linh',
        'dương đình trí', 'linh nguyễn', 'nhật hào',
        'thái hiền', 'lê tuấn', 'hạnh nguyên',
        'vũ duy long', 'mộc anh', 'họa mi',
        'trung nghĩa', 'tố my', 'ngọc diệu',
        'sỹ đan', 'lê anh dũng', 'duy cường',
        'mạnh đình', 'duy phương', 'mai kiều',
        'thanh thanh hiền', 'kỳ anh', 'nguyễn hoàng nam',
        'hồ quang 8', 'đặng trí trung',
        'nguyễn đức', 'hoa nguyễn', 'quỳnh giang',
        'chế phong', 'dạ nhật yến', 'trang hạ',
        'quốc khanh', 'đan phong', 'tuấn anh',
        'lê ngọc thúy', 'minh trường', 'bảo hưng',
        'từ như tài', 'dương thanh sang', 'lê mỹ hương',
        'tài nguyễn', 'dương quốc hưng', 'đức long',
        'hoàng hải', 'nhật vũ', 'phạm hoài nam',
        'diệu hiền', 'long hồ', 'ngọc hạ',
        'sa huỳnh', 'duy khương', 'thanh thanh',
        'thanh ngọc', 'phương mỹ hạnh',
        'trizzie phương trinh', 'quân bảo',
        'tuấn quang', 'mộc san',
        'hồng ngọc', 'phương thùy',
        'lương tùng quang', 'thúy khanh',
        'phong đạt', 'giang hồng ngọc',
        'kim ny ngọc', 'bích thảo', 'anna yến phượng',
        'cao vũ', 'tú na', 'ngọc hải',
        'thiên tú', 'chí thiện', 'diệu thắm',
        'mỹ lệ', 'khánh ngọc',
        'vương cây', 'ngọc khang', 'quang trường',
        'cẩm như', 'châu ngọc tiên',
        'đạt long vinh', 'thiên bảo', 'dương nhất linh',
        'khang việt', 'lê duy mạnh',
        'trọng phúc', 'bảo hân', 'yuki huy nam',
        'jin tuấn nam', 'kiwi ngô mai trang',
        'lâm chấn hải', 'lâm băng phương', 'huyền anh',
        'như bee', 'mây trắng',
        'thủy lê', 'ánh tuyết',
        'tuấn chung', 'nhật kim anh',
        'nguyễn derek duy', 'tuấn hùng',
        'phương ý', 'lương quý tuấn', 'quý nhỏ',
        'đỗ thụy khanh', 'vũ như nguyệt', 'đào phi dương',
        'khả hiệp', 'nal',
        'phú quí', 'lã phong lâm', 'lương viết quang',
        'bùi thúy', 'la quỳnh',
        'lê thu hiền', 'tam hổ', 'huyền tranng',
        'hoàng lê vi', 'xuân nghi', 'bảo vân',
        'chú gián nhỏ', 'vương bảo nam',
         'đăng khoa',
        'phương thủy', 'đoan trang',
        'anh thư', 'kim tử long',
        'hương thủy', 'lưu chấn long',
        'nguyễn kiều oanh', 'tống gia vỹ',
        'lê thu thảo', 'mạnh hùng', 'chế minh',
        'chu duyên', 'diệu kiên',
        'đình dũng',
        'ngọc tân', 'lee ken',
         'nhã uyên',
        'khương hùng', 'văn tài',
        'nguyễn thạc bảo ngọc', 'huyền zoe', 'cao sỹ hùng',
        'hoàng ly', 'phượng vũ', 'út nhị mino',
        'long hải', 'mỹ tình', 'phương lam',
        'phạm khánh hưng', 'trịnh tuấn vỹ',
        'phúc bồ',
        'đỗ hiệp', 
        # ── old bolero/trữ tình/nhạc đỏ additions ──
        'kha thi', 'sỹ ben', 'sy ben', 'như hảo', 'nhu hao',
        # ── v15.0 — comprehensive old/cải lương/bolero/nhạc đỏ/thánh ca cleanup ──
        'tốp nữ', 'tốp nam nữ', 'tam ca 3a', 'tam ca thế hệ mới',
        'tứ ca ngẫu nhiên', 'anh bằng', 'nhóm mtv', '5 dòng kẻ', 'năm dòng kẻ',
        'kim tiểu long', 'vũ luân', 'mỹ châu', 'lệ thủy',
        'minh cảnh', 'minh phụng', 'bạch tuyết', 'út bạch lan',
        'thành được', 'học viện cải lương', 'thanh tuấn',
        'hồ minh đương', 'trọng hữu', 'minh vương',
        'cẩm tiên', 'thành lộc', 'võ ngọc quyền',
        'phong trần', 'thanh hải', 'tấn giao', 'tấn tài',
        'thanh kim huệ', 'thanh nga', 'hồng nga',
        'nsưt thanh sang', 'cvvc nhật nguyên', 'hữu phước',
        'nsưt thuý hường', 'nsnd minh thu', 'nsnd thúy hường',
        'nsut ngọc bích', 'ns thuý hường',
        'anh dũng', 'hoàng việt trang', 'trịnh nam sơn',
        'dạ hương', 'tuấn cường', 'quách tấn du',
        'vân trường', 'y phụng', 'đoàn phi',
        'cam thơ', 'tấn đạt', 'khắc dũng',
        'thúy đạt', 'kiều diễm', 'thanh phương',
        'ngọc yến', 'kim cương', 'thọ hùng',
        'quang hào', 'tiến thành', 'duy thường',
        'tố hà', 'huyền trang sao mai', 'thuý cải',
        'phi thúy hạnh', 'quang đại', 'thụy long', 'mai thảo',
        'uyển my', 'ngô thanh vân',
        # ── v16.0 — user-specified + audit cleanup ──
        'vu van', 'tuyết mai', 'quỳnh như', 'lâm hùng',
        'phạm hiền', 'vũ trà', 'tấn sang', 'phạm kỳ',
        'ba trọng', 'khanh dan', 'candy hoàng hoa',
        'lương hồng quế', 'trịnh ngọc huyền', 'lương hồng huệ',
        'kim thúy', 'hà bửu tân', 'sơn trung',
        'nguyễn đình tuấn dũng', 'vũ minh đức', 'đinh huy',
        'như hiền', 'đức việt', 'lương tuấn',
        'như mai', 'vy vân',
        'thanh hiếu', 'tú linh', 'thu giang', 'cao minh',
        'hoàng vinh', 'minh thành', 'bảo trâm',
        'trung anh', 'duy sang', 'thế dân',
        'thái bảo', 'thanh cường', 'a páo',
        'ca đoàn ngàn khơi', 'vương dzung', 'reddy',
        'thái khiết linh', 'thế phương vbk', 'techno',
        'ngọc quỳnh', 'yuniboo', 'gia huy', 'khánh du',
        'khánh đăng', 'release', 'nha ngoc',
        'trần thụy kim anh', 'lan anh', 'đại vệ',
        'nguyễn hữu chiến thắng', 'thành phú',
        'duy khoa', 'phan hoàng tâm',
        # ── v12.0 additional old-genre catches ──
        'saka trương tuyền', 'cẩm vân',
        'phương hồng quế', 'lâm nhật tiến', 'thùy trang',
        'châu thanh', 'bùi trung đẳng',
        'thanh nhường', 'nhật kim anh',
        'bùi đức thịnh', 'đăng khoa',
        # ── v12.1 expanded — remaining old-genre from CSV analysis ──
        'trần mai anh', 'hương ly', 
        'duy tuấn',
        'nguyễn hồng nhung', 'du thiên',
        'nguyễn văn chung', 
        'trần nhật quang', 'nhã phương',
        'thảo my',
        'lân nhã', 'phương diễm huyền',
        'lâm chấn huy',
        'lương thuỳ linh',
        'tina ngọc lan', 'trịnh vĩnh trinh', 'sương sương',
        'trung đức', 'nhật phong', 'binie',
        'y phương', 'lâm chấn khang',
         'trịnh xuân mười', 'đặng tuấn vũ',
        'khả tú', 'đức chính', 'johnny dũng',
        'bảo ngọc', 'ngô viết trung', 'mai tiến dũng',
        'lương thuỳ linh', 'hoàng diễn', 'leon vũ',
        'hải đăng', 'hằng bingboong', 'bảo nam', 'nhã ca',
        'trang', 'xuân hoà', 'hoàng đệ', 'danh tuấn trung',
        'nguyễn thắng', 'phạm linh phương', 'tuấn quỳnh',
        'mai ngọc khánh', 'cẩm loan', 'chú mười ba',
        'đông nguyễn', 'thái thảo', 'trọng thuỷ',
        'lê cường', 'thanh thu', 'viên thu hường',
        'hoàng đồng', 'đặng hồng nhung', 'hoa mi',
        'tố uyên', 'minh nguyệt', 'mai lệ huyền',
        'quốc vũ', 'đỗ tú tài', 'phương thảo',
        'duy vũ', 'oanh nguyễn',
        'công tuấn', 'quỳnh lan', 'tường quân',
        'khánh linh', 'việt quang', 'bảo trung', 'bảo trân',
        'dật hanh', 'lâm bửu hòa', 'lương quốc việt',
        'trịnh thiên ân', 'hiền ngân', 'trịnh lam',
        'thế bảo', 'khải ca', 'thành đại siêu',
        'chữa lành', 'nhã vân', 'figdee',
        'thiện tâm chi bảo',
        'diễm quỳnh', 'mai trần lâm', 'hà anh',
        'ngọc quý', 'ngô khải anh', 'võ kiều vân',
        'ngọc khuê', 'hoàng thục linh', 'trần mỹ ngọc',
        'thạch dũng', 'nguyễn minh anh', 'giang tử',
        'vân sơn', 'mai thanh sơn', 'hà thơ',
        'quỳnh vi', 'anny hằng', 'ngọc ngữ',
        'đinh đại vũ', 'bình yên',
        'st. angelic choir',
        # Non-artist foreign channels
        'mc jessica do escadão', 'dj bulico cachorrão',
        'da ponte pra cá', 'mc mn', 'dj gr',
        'mc renatinho falcão', 'dj tg beats',
        'mc davi cpr', 'mc lipivox', 'mc fabinho da osk',
        'dj vini da zo', 'dj tubarão zs', 'dj lucão zs',
        'dj gordonsk', 'dj chico oficial', 'dj brunin js',
        'dj azevedo original', 'dj v-easier',
        'dj henrique de são mateus', 'dj daniel fernandes',
        'dustin ngo 春風', 'the dreamland',
        'hót the vdm', 'the hotel lobby',
        'mc gw', 'dj scatolim',
        # ── v13.1 — old-gen / nhạc vàng / trữ tình from Phase 1 analysis ──
        'quách thành danh', 'phạm thanh thảo', 'ngọc ký',
        'nguyễn hữu thái hòa', 'trung kiên', 'đặng thanh tuyền',
        'trúc lam', 'cát tiên', 'vũ quốc bình', 'mai khôi',
        'mtv band', 'thu huyền', 'tiến dũng', 'hoang rapper',
        'an hiếu', 'dương nhân trung', 'trần trung đức',
        # ── v14.1 — Phase 1 expansion cleanup (2026-04-05) ──
        'lê minh trung', 'an nhiên', 'trà my idol', 'tra my idol',
        'kyo york',
        'du thiên', 'du thien',
        'phúc bồ', 'phuc bo',
        'đại nhân', 'đan nguyên', 'dan nguyen',
        'minh tuyết', 'minh tuyet',
        # ── v14.2 — Phase 1 CSV analysis: old-genre / bolero / trữ tình / nhạc vàng ──
        'lưu ánh loan', 'luu anh loan',
        'phương dung', 'phuong dung',  # pre-1975 nhạc vàng
        'đông đào', 'dong dao',  # bolero/trữ tình
        'minh thu',  # old-genre acoustic
        'dương ngọc thái', 'duong ngoc thai',  # bolero
        'vũ thắng lợi', 'vu thang loi',  # nhạc đỏ/old
        'minh thuận', 'minh thuan',  # old pop (deceased)
        'đức tuấn', 'duc tuan',  # nhạc xưa/acoustic
        'ngọc linh',  # 80s-90s nhạc trẻ
        'duy mạnh', 'duy manh',  # nhạc vàng
        'tô thanh phương', 'to thanh phuong',  # bolero
        'lê như', 'le nhu',  # bolero
        'hồ phương liên', 'ho phuong lien',  # bolero
        'như ý', 'nhu y',  # old
        'lê vĩnh toàn', 'le vinh toan',  # old
        'thu hằng',  # trữ tình
        'hạ vy', 'ha vy',  # old
        'diễm hân', 'diem han',  # old
        'nhất sinh', 'nhat sinh',  # old
        'yến thanh', 'yen thanh',  # old
        'jimmii nguyễn', 'jimmii nguyen',  # 90s nhạc trẻ
        'ngũ cung', 'ngu cung',  # old group
        'lý hải', 'ly hai',  # old pop/movie
        'quốc bảo', 'quoc bao',  # old nhạc sĩ
        'vĩnh thuyên kim',  # old
        'dáng kiều', 'dang kieu',  # old
        'lê vũ', 'le vu',  # bolero
        'tài linh', 'tai linh',  # cải lương
        'lê sang', 'le sang',  # bolero
        'mai thiên vân', 'mai thien van',  # hải ngoại
        'băng tâm', 'bang tam',  # hải ngoại
        'sỹ luân', 'sy luan',  # old
        'lương bằng quang', 'luong bang quang',  # old
        'lưu trúc ly', 'luu truc ly',  # bolero
        'ngọc giàu', 'ngoc giau',  # cải lương NSND
        'quế trân', 'que tran',  # cải lương
        'như loan', 'nhu loan',  # old
        'chu thúy quỳnh',  # old
        'lương thế minh',  # old
        'hồng mơ', 'hong mo',  # old
        'minh huyền', 'minh huyen',  # old
        'tường khuê',  # old
        'đào duy quý',  # old
        'ngọc mai', 'ngoc mai',  # old
        'tăng nhật tuệ',  # old
        'bằng chương',  # old
        'phương cẩm ngọc',  # old
        'phương trang',  # old
        'hoàng thơ',  # old
        'dương 565',  # old
        'anh rồng',  # old
        'tần khánh',  # old
        'vũ thanh vân',  # old
        'minh huy',  # old
        'đức trí', 'duc tri',  # nhạc sĩ old
        'nguyễn hồng thuận',  # nhạc sĩ old
        'bức tường',  # old rock band
        'phương linh',  # old
        'diễm sương',  # old
        'tống hạo nhiên',  # old
        'huynh phi tien', 'huỳnh phi tiễn',  # old
        'trần sang',  # bolero
        'thanh hằng',  # model, not singer
        'phương vy', 'phuong vy',  # old pop
        'jee trần',  # old
        'lê hồng',  # old
        'cvvc nguyễn văn khởi',  # cải lương
        'nsưt đào vũ thanh',  # NSƯT old
        'nsưt lê tứ',  # NSƯT old
        'hồ văn cường', 'ho van cuong',  # bolero young
        'thanh thảo', 'thanh thao',  # 2000s early pop
        'khánh phương', 'khanh phuong',  # 2000s pop
        'thu thủy', 'thu thuy',  # 2000s pop
        'nguyên hà', 'nguyen ha',  # old acoustic
        'đổng lan', 'đồng lan',  # old jazz
        # ── v17.0 — strict modern-only: block ALL old-gen (pre-2013 fame) ──
        # 90s-2000s pop idols / divas / ballad singers
        'đan trường', 'dan truong', 'lam trường', 'lam truong',
        'ưng hoàng phúc', 'ung hoang phuc',
        'mỹ tâm', 'my tam', 'hồ quỳnh hương', 'ho quynh huong',
        'quang vinh', 'cao thái sơn', 'cao thai son',
        'thu minh', 'đăng khôi', 'dang khoi',
        'thủy tiên', 'thuy tien', 'bảo thy', 'bao thy',
        'lê hiếu', 'le hieu', 'yanbi',
        'lưu hương giang', 'luu huong giang',
        'quỳnh nga', 'quynh nga',
        'wanbi tuấn anh', 'wanbi tuan anh',
        'nathan lee', 'minh hằng', 'minh hang',
        'ông cao thắng', 'ong cao thang',
        'hà trần', 'ha tran', 'lil knight', "lil' knight",
        '365daband', 'the men',
        'hoài lâm', 'hoai lam', 'quốc thiên', 'quoc thien',
        'isaac', 'cường seven', 'cuong seven',
        'hari won', 'nhật thủy', 'nhat thuy',
        'ngô kiến huy', 'ngo kien huy',
        'akira phan', 'khởi my', 'khoi my',
        'đông nhi', 'dong nhi',

        'tóc tiên', 'toc tien', 'miu lê', 'miu le',
        'trịnh thăng bình', 'trinh thang binh',
        'trung quân', 'trung quan', 'trung quân idol',
        'văn mai hương', 'van mai huong',
        'uyên linh', 'uyen linh',
        'hương tràm', 'huong tram',
        'đinh mạnh ninh', 'dinh manh ninh',
        'thái trinh', 'thai trinh',
        'song luân', 'song luan',
        'khắc việt', 'khac viet',
        'hồ quang hiếu', 'ho quang hieu',
        'maya', 'jun phạm', 'jun pham',
        'dương hoàng yến', 'duong hoang yen',
        'gil lê', 'gil le', 'lưu hưng',
        # Nhạc trẻ sến / bolero-adjacent / old nhạc trẻ
        'vũ duy khánh', 'vu duy khanh',
        'lê bảo bình', 'le bao binh',
        'gin tuấn kiệt', 'gin tuan kiet',
        'tuấn đạt', 'tuan dat',
        'huy vạc', 'huy vac',
        'dương hiếu nghĩa', 'duong hieu nghia',
        'vina uyển my', 'vina uyen my',
        'datkaa', 'bảo kun', 'bao kun',
        'đinh tùng huy', 'dinh tung huy',
        'đình phong', 'dinh phong',
        'tuấn khoa', 'tuan khoa',
        'aki ngọc duy', 'aki ngoc duy',
        'only c', 'đông thiên đức', 'dong thien duc',
        'hoàng tôn', 'hoang ton',
        'jaykii', 'huyr',
        'khải đăng', 'khai dang',
        'kuun đức nam', 'kuun duc nam',
        'nguyễn phước hoàn', 'nguyen phuoc hoan',
        'lynk lee', 'lê thiện hiếu', 'le thien hieu',
        'phạm anh duy', 'pham anh duy',
        'vũ thảo my', 'vu thao my',
        'huỳnh james', 'huynh james',
        'lê hoàng (tm1981)',
        'mỹ mỹ', 'my my', 'trang pháp', 'trang phap',
        'khaly nguyễn', 'khaly nguyen',
        # ── v18.0 — thorough cleanup: obscure / non-famous / old-era artists ──
        'đức thịnh', 'duc thinh', 'hải sâm', 'hai sam',
        'tiến minh', 'tien minh', 'hoàng hải dương', 'hoang hai duong',
        'hạnh sino', 'hanh sino', 'minh tiến', 'minh tien',
        'chuột sấm sét', 'chuot sam set', 'bảo yến rosie', 'bao yen rosie',
        'huỳnh tú', 'huynh tu', 'minh tốc & lam',
        'hải sâm', 'the fillin', 'anh thư phan', 'anh thu phan',
        'dlblack', 'yến tatoo', 'yen tatoo', 'emma nhất khanh',
        'phankeo', 'chuột sấm sét', 'blackbi',
        'hoàng hải dương', 'vĩnh hoàng', 'vinh hoang',
        # v18.1 — user-flagged
        'mèow lạc', 'meow lac', 'hồng lụa', 'hong lua',
        'lil shady', 'phạm hoàng anh', 'pham hoang anh',
        'a.c xuân tài', 'a.c xuan tai',
        'mingji', 'miky đóng tune',
        'addy trần', 'addy tran',
    }

    # ── NON-ARTIST CHANNEL / COMPILATION BLOCKLIST ──
    # Keyword-based: any artist name containing these words is a channel, not an artist
    NON_ARTIST_CHANNEL_KEYWORDS = re.compile(
        r'(?i)(?:'
        r'\b(?:music|nhạc|mix|remix|organ|guitar|guitarist|piano|hòa tấu|beat|'
        r'disco|lofi|lo-fi|chill|studio|karaoke|acoustic|instrumental|'
        r'cover|compilation|tuyển tập|tổng hợp|collection|playlist|'
        r'trending|official|tv|media|entertainment|production|records|'
        r'channel|kênh|vinahouse|deep|không lời|bolero|trữ tình|'
        r'club|rising|sped|thu âm|hợp ca|tốp ca|hầu ca)\b'
        r'|'
        r'\bAI\b'  # "Nhạc AI", "Âm Nhạc Ai" etc.
        r'|'
        r'_singer\b'  # "Thái Hằng Nga_Singer" etc.
        r')',
    )

    # Explicit non-artist channel blocklist — names that don't match keyword patterns
    NON_ARTIST_CHANNEL_BLOCKLIST = {
        # Remix / DJ / EDM channels
        'luân phan', 'luanphan', 'orinn', 'orinn sped', 'bmz', 'hhd', 'tlong',
        'icm', 'lâm triệu minh', 'mochiii', 'dunghoangpham',
        'h2o houselak', 'h2o edm', 'h2o remix',
        # Remix / Compilation spam channels (v13.1)
        'ha live', 'bảo trân đặng', 'fm band',
        'cao nam thanh', 'xuân đức', 'dương minh tuấn', 'phạm lịch',
        # Remix / Cover / Lofi channels (v13.2)
        'kiều thơ mellow', 'không gian cảm xúc', 'great team',
        'fenni phan ngân', 'quang chợ lầm', 'pinky vanh',
        'gold mk', 'moi dj',
        # Spam accounts (80%+ zero-pop, avg_pop < 2) (v13.2)
        'tmons', 'jenni-sonic', 'vương thiên tuấn',
        'nguyen dinh thanh tam', 'dc tâm', 'tan khanh',
        'đỗ phú quí', 'julysoul', 'ron phan', 'ognam',
        'vu tram anh', 'young milo', 'nqp', 'tdz', 'huyh',
        # Propaganda / Military music (v13.2)
        'oplus band',
        # MC / Host / Non-musician (v13.2)
        'host nguyên khang',
        # Healing / Meditation channels (v13.2)
        'helios healing space',
        # Compilation / Aggregation channels
        'edm 95 club', 'ballad rb', 'beeboss', 'vpop rising',
        'ngọc ánh sáng', 'hyperrecords', 'melomix',
        # TV shows / Reality shows
        'rap việt', 'the masked singer', 'tỏa sáng sao đôi',
        'toả sáng ước mơ',
        # Recording studios / Labels
        'flypro thu âm việt',
        # Group singing / Old groups
        'tam ca áo trắng',
        # Non-VN content channels
        'trần hữu tuấn bách',
        # Channel-like names
        'thái hằng nga_singer',
        'sped up +84',
        # ── v14.1 — foreign artists with common VN names / wrong YTMusic matches ──
        'captain', 'captain boy',  # South African artist
        'tony d',  # German/UK rapper
        'triple d',  # South African group
        'double x',  # foreign group
        'the wind',  # K-pop group
        'the sheep', 'machiot',  # remix/cover channels

        'bongos ikwue',  # Nigerian artist
        'christopher wong',  # non-VN
        'elizabeth tan',  # Malaysian
        "good ol' boyz",  # foreign
        'love fluxos',  # Brazilian
        'garrett crosby',  # foreign
        'hosier',  # foreign
        'fabrica de beats cl',  # Brazilian
        'brabo gator',  # foreign
        'rindan',  # foreign
        'hitstory',  # producer/channel
        'mmusic',  # channel
        'cm1x',  # remix channel
        'acv',  # channel
        'zlab',  # channel
        'vovanduc',  # channel
        # ── v14.2 — non-artist entries from CSV analysis ──
        'nhiều ca sĩ', 'nhieu ca si',  # compilation label
        'chị đẹp đạp gió rẽ sóng', 'chi dep dap gio re song',  # TV show
        'liên quân mobile',  # game
        'vina bất diệt',  # compilation channel
        'tốp nam',  # generic group label
        'nhóm la thăng',  # old group
        'nhóm lạc việt',  # old group
        'cam philharmonic',  # orchestra
        'openShare',  # channel
        'ian rees',  # foreign
        'feliks alvin',  # foreign
        'magazine',  # UK post-punk band
        # ── v14.3 — Non-music / comedians / TV hosts ──
        'mc 12', 'trấn thành', 'trường giang', 'bb trần',
        'huỳnh lập', 'tiến luật', 'tự long', 'thành trung',
        'nsưt thoại mỹ', 'nsnd bạch tuyết', 'nsưt kim tiểu long',
        'gia đình lâm vỹ dạ - hứa minh đạt',
        'cát phượng', 'lâm vỹ dạ', 'chí tài', 'khả như', 'kiều oanh',
        # ── v14.3 — Foreign artists that slipped through VN filter ──
        'south park mexican', 'juan gotti', 'chriss vogt',
        'gasca zurli', 'antoneus maximus', 'ted park',
        'two maloka', 'sonaone', 'herbalife',
        'teodora', 'nik makino', 'ralphie reese',
        'megashock', 'raditori', 'mimetals', 'lemese',
        'orkestrated', 'mal delayz', 'almighty hova',
        'kevin krissen', 'various artist',
        # ── v14.4 — User-flagged: not matching criteria ──
        'hạ vi', 'la cà band', 'nguyễn thúc thùy tiên',
        'xuân phú', 'anh thuý', 'trần lê',
        'tiêu châu như quỳnh', 'huyền anh',
        'kỳ phương uyên', 'phù sa', 'đào đức', 'kim ngọc',
        'ái xuân', 'rich anh tuấn', 'bujur phương',
        'hoàng vũ', 'kim ngân', 'hàn thái tú', 'bảo uyên',
        'trà ngọc hằng', 'cao cẩm tú', 'bích diễm', 'trí hải',
        'khánh phong', 'thanh hưng idol', 'thanh hùng',
        'clubb', 'j-rich', 'trapbhp', 'dbaola',
        'pak band', 'unlimited band',
        'trương thảo nhi', 'minh thuý', 'hạo thiên',
        'hoàng long vũ', 'liêu chấn hải', 'tina ho',
        'hùng quân', 'ngọc kayla', 'lala trần',
        'nguyễn vĩ', 'na ngọc anh', 'duy khiêm',
        'bá thắng', 'trương quỳnh anh', 'bích ngân',
        'bích tuyền', 'hoàng lệ tố', 'nguyên khôi',
        'bảo jen', 'tam', 'sino', 'jonc', 'mr.sâu',
        'tố ny', 'dongbaby', 'tieu son', 'helen trần',
        'đoàn minh sang', 'kiun gia tuấn', 'hồ tuấn anh',
        'hoàng yếu', 'đức anh', 'du uyên', 'khánh duy',
        'đông quân', 'anh đức', 'mai diễm mu',
        'trần hồng kiệt', 'hiếu rock', 'saily q',
        'changmin hoàng', 'trần nhuận vinh', 'quốc huy',
        'ý lan', 'lê quang ninh', 'đan lê', 'phương loan',
        'ngọc thuỷ', 'my lan', 'ngọc thuý',
        'ngọc khánh chi', 'trần tuấn lương',
        'việt anh avatar', 'bác sĩ hải', 'vũ tuấn hùng',
        'trần mạnh cường', 'kprox', 'omg3q',
        'hiền mai', 'quinn hiền mai', 'mekong pictures',
        'han khoi', 'lâm tuấn pha', 'quốc mạnh',
        'hồ bích ngọc', 'nguyen nam', 'brian huỳnh anh',
        'lay minh', 'ý nhi', 'hoàng nam', 'nam khánh',
        'hoàng thiên long', 'lập nguyễn', 'thảo trang',
        'đông hùng', 'đỗ hoàng long', 'huyền trần',
        'trịnh tú trung', 'loki bảo long', 'thiện nhân',
        'phương yến linh', 'tronie', 'tuấn hii',
        'lilgee phạm', 'võ ê vo', 'ngân ngân',
        'đinh hoàng quốc', 'tezzy', 'dang minh',
        'dex', 'gia quý', 'huỳnh văn',
        'thoại nghi', 'ngọc phước', 'billy100',
        'tedd', 'giang trang', 'liêm hiếu',
        'cece trương', 'bùi dương thái hà',
        'flo d', 'bro6ty', 'vink', 'shanhao',
        'vũ đặng quốc việt', 'trần nghĩa',
        'đông hùng idol', 'hải yến idol',
        'yến tattoo', 'huyền tâm môn',
        'vu trung quan', 'uyên pím', 'tú anh',
        'gác mái', 'ngọc kara', 'thương', 'quochung',
        'tổng đài', 'đinh khánh ly', 'lys',
        'hồ văn quý', 'youngd', 'trần thanh cường',
        'huyền trang', 'thỉm', 'chem',
        'nhất nguyễn', 'nhật nguyễn', 'nguyên jenda',
        'rin9', 'kira', 'keyo', 'kiều loan',
        'nguyễn thương', 'vũ khánh dương', 'xệ xệ',
        'trí quang', 'lập nguyên starboiz',
        'linzy', 'nie', 'gokky', 'kiều chi',
        'xôn nguyễn', 'anne', 'sang',
        'nguyễn minh xuân ái', 'the mèo', 'the sans',
        'bon ma', 'quỳnh anh', 'thúy nga',
        'pb live band', 'mtk bach cong khanh',
        'bon nguyễn', 'vân du', 'tâm minhon',
        'hồng kiệt', 'be phuong uyen',
        'nguyễn thúc thuỳ tiên ft. erik (prod. by fillinus)',
        'kiên ứng', 'lam anh', 'dinh bao',
        'nguyệt anh', 'nguyệt ánh', 'ngọc châu',
        'yến trang', 'hòa hiệp', 'việt dzũng', 'bạch yến',
        'thanh mai', 'quốc anh', 'huy phương',
        'giáng thu', 'thiên minh', 'liên bỉnh phát',
        'trương thế vinh', 'đỗ hoàng hiệp', 'hà lê',
        'duy nhất', 'hiền vk', 'châu kỳ', 'ni ni',
        'mai hậu', 'dương trường giang', 'sam',
        'quờ', 'đậu tất đạt', 'thanh danh', 'huỳnh anh',
        'nhật minh', 'nguyễn ngọc kim cương',
        'thạch linh', 'hoàng hồng ngọc', 'lâm vũ',
        'khánh loan', 'quang hiếu', 'khánh thi',
        'don nguyễn', 'phương trinh', 'phan hieu kien',
        'phan ngọc luân', 'quang toàn', 'hoàng nhung',
        'tuyết', 'dế choắt (dc)', 'luny vũ duy anh',
        'tân trần', 'chun', 'cao tùng anh', 'đỗ hiếu',
        'glam', 'tuấn khanh', 'tuấn hoàng',
        'hannie', 'radio band', 'dan chi',
        'vân shi', 'sky', 'dustee', 'dang nguyen',
        'quang minh', 'lâm chí khanh', 'đình bảo',
        'vinahuy', 'nhậm phương nam', 'huyên trân',
        'quang linh', 'châu ngọc hà',
        'nguyễn phi hùng', 'vy oanh',
        'phạm quỳnh anh', 'vương anh tú', 'thanh long',
        'cao duy', 'charmy pham',
        'v.music', 'oplus', 'vân anh',
        'hà nhi', 'blacka', 'myan', 'p.shi',
        'jackt', 'robber', 'công hoà', 'chỉ hoa',
        'nah', 'thanh duy', 'jang nguyễn',
        'f47', 'vo ha tram',
        'võ hạ trâm',
        'sara lưu', 'sara luu', 'phương uyên',
        'phương uyển', 'lê minh', 'lập nguyên',
        'greend', 'shin hồng vịnh', 'yến nhi',
        'junki trần hoà', 'junki trần hòa',
        'minh aanh', 'thùy chi',
        # ── Bolero / trữ tình / old-genre that slipped through ──
        'duy hưng', 'anh khang', 'phước lộc', 'song thư',
        'minh trí', 'triệu minh', 'hoàng mỹ an', 'kim thành',
        'thy dung', 'quế vân', 'nam cường', 'hoàng y nhung',
        'đoàn thúy trang', 'đinh trang', 'wendy thảo',
        'phạm nguyên ngọc', 'kelvin khánh',
        'lê trọng hiếu', 'hoài thanh', 'chung thanh duy',
        'huy nam (a#)', 'huy nam',
        'nhật hoàng', 'minh quân',
        # ── Non-music: actors/influencers/comedians ──
        'diệu nhi', 'diệp lâm anh', 'ninh dương lan ngọc',
        'ninh dương story', 'châu bùi', 'quỳnh anh shyn',
        'huyền anh (bà tưng)', 'huyền anh', 'linh ka',
        'huyền baby', 'đại mèo', 'sĩ thanh',
        'nsưt cao minh', 'tim', 'ca ca', 'fanny',
        # ── Foreign artists that slipped through ──
        'atitude consciente', 'dan fensom', 'calum scott',
        'lenny cooper', 'shotgun shane', 'chris turner',
        'nick strand', 'orkestrated',
        # ── Entertainment/comedy channels ──
        'bác sĩ mập hồng', 'chó phú quốc', 'rắn cạp đuôi', 'hoàng lụt',
    }

    # Track-level garbage patterns — filter at track title level
    TRACK_GARBAGE_RE = re.compile(
        r'(?i)(?:'
        r'\bkaraoke\b|\bbeat\b|\bhòa tấu\b|\binstrumental\b'
        r'|\bnhạc không lời\b|\bnhạc chuông\b|\bringtone\b'
        r'|\bparody\b|\bliên khúc\b|\bmedley\b'
        r')',
    )

    # Live/concert track title patterns — skip during collection
    TRACK_LIVE_RE = re.compile(
        r'(?i)(?:'
        r'\bconcert edition\b|\bconcert version\b'
        r'|\blive session\b|\blive at\b|\bliveshow\b|\blive show\b'
        r'|\bin concert\b|\bminishow\b|\bmoodshow\b'
        r')',
    )

    # Remix variant pattern — for dedup (same base song, different remix)
    REMIX_VARIANT_RE = re.compile(
        r'\s*[\(\[](.*?(?:remix|lofi|lo-fi|acoustic|piano ver|rock version|drill|'
        r'house|vinahouse|edm|ballad ver|short version|cover version|chill|'
        r'speed up|slowed|reverb|mashup|version)[^\)\]]*)\s*[\)\]]',
        re.IGNORECASE
    )

    # Bosnian/Serbian Đ detection — these languages use Đ but NOT other VN chars
    BALKAN_INDICATORS = re.compile(
        r'(?i)(?:\bš\b|[čćžšđ]{2,}|\bje\b.*\bme\b|\bse\b.*\bne\b|'
        r'\bvolim\b|\bmoja\b|\btvoj\b|\bsamo\b|\bljub\b|\bbrat\b|'
        r'\bžen\b|\bprav\b|\bsvet\b|\bnoć\b|\bdan[aeiou]?\b)',
        re.IGNORECASE
    )

    @classmethod
    def has_foreign_chars(cls, text: str) -> bool:
        count = 0
        for ch in text:
            cp = ord(ch)
            for rng_start, rng_end in Config.FOREIGN_CHAR_RANGES:
                if rng_start <= cp <= rng_end:
                    count += 1
                    if count >= 2:
                        return True
                    break
        return False

    @classmethod
    def is_garbage_name(cls, name: str) -> bool:
        """Check if artist name is a date, number, or view count."""
        return bool(cls.GARBAGE_NAME_RE.match(name.strip()))

    @classmethod
    def has_non_vn_diacritics(cls, text: str) -> bool:
        """Check if text contains European diacritics that are NOT Vietnamese."""
        return bool(cls.NON_VN_DIACRITICS & set(text))

    @classmethod
    def has_vietnamese_chars(cls, text: str) -> bool:
        return bool(Config.VIETNAMESE_UNIQUE_CHARS & set(text))

    @classmethod
    def has_truly_unique_vn_chars(cls, text: str) -> bool:
        """Check for Vietnamese chars that do NOT appear in Portuguese/French.
        Plain â ê ô are shared; ă đ ơ ư + combining forms (ấ ầ ế ề ố ồ etc.) are unique."""
        vn_found = Config.VIETNAMESE_UNIQUE_CHARS & set(text)
        if not vn_found:
            return False
        truly_unique = vn_found - cls.SHARED_CIRCUMFLEX_CHARS
        return bool(truly_unique)

    @classmethod
    def has_vietnamese_diacritics(cls, text: str) -> bool:
        return bool(Config.VIETNAMESE_ALL_DIACRITICS & set(text))

    @classmethod
    def has_common_vn_words(cls, text: str) -> bool:
        return bool(cls.COMMON_VN_WORDS.search(text.lower()))

    _KNOWN_ARTISTS_NORMALIZED = {a.replace(' ', '').replace('-', ''): a for a in KNOWN_ARTISTS}
    _CURRENT_ARTISTS_STRIPPED = None

    @classmethod
    def is_known_artist(cls, artist_names: List[str]) -> bool:
        for name in artist_names:
            cleaned = name.lower().strip()
            if cleaned in cls.KNOWN_ARTISTS:
                return True
            normalized = cleaned.replace(' ', '').replace('-', '')
            if normalized in cls._KNOWN_ARTISTS_NORMALIZED:
                return True
        return False

    @classmethod
    def is_current_artist(cls, artist_names: List[str]) -> bool:
        """Return True for an exact current-artist name or normalized alias."""
        if cls._CURRENT_ARTISTS_STRIPPED is None:
            cls._CURRENT_ARTISTS_STRIPPED = {
                cls._strip_vn_diacritics(name) for name in cls.CURRENT_ARTISTS
            }
        for name in artist_names:
            cleaned = str(name or '').lower().strip()
            if cleaned in cls.CURRENT_ARTISTS:
                return True
            if cls._strip_vn_diacritics(cleaned) in cls._CURRENT_ARTISTS_STRIPPED:
                return True
        return False

    @classmethod
    def is_current_old_genre_overlap(cls, artist_names: List[str]) -> bool:
        """Current artist whose name also exists in the historical old list."""
        if not cls.is_current_artist(artist_names):
            return False
        stripped_old = cls._get_stripped_blocklist()
        return any(
            cls._strip_vn_diacritics(str(name or "")) in stripped_old
            for name in artist_names
        )

    # Pre-computed stripped blocklist for fuzzy matching (lazy init)
    _NON_ARTIST_BLOCKLIST_STRIPPED = None

    @classmethod
    def _get_non_artist_stripped_blocklist(cls):
        if cls._NON_ARTIST_BLOCKLIST_STRIPPED is None:
            cls._NON_ARTIST_BLOCKLIST_STRIPPED = {
                cls._strip_vn_diacritics(n)
                for n in cls.NON_ARTIST_CHANNEL_BLOCKLIST
            }
        return cls._NON_ARTIST_BLOCKLIST_STRIPPED

    @classmethod
    def is_non_artist_channel(cls, artist_name: str) -> bool:
        """Check if artist name matches a non-artist channel pattern.
        Uses regex patterns, keyword matching, AND explicit blocklist
        (with diacritics-stripped fuzzy matching)."""
        name = artist_name.strip()
        name_lower = name.lower()
        # Exact current artists override stale or ambiguous channel entries.
        if cls.is_current_artist([artist_name]):
            return False
        # Explicit blocklist (exact match) — checked FIRST, overrides whitelist
        if name_lower in cls.NON_ARTIST_CHANNEL_BLOCKLIST:
            return True
        # Diacritics-stripped blocklist (fuzzy match)
        if cls._strip_vn_diacritics(name_lower) in cls._get_non_artist_stripped_blocklist():
            return True
        # If known artist AND not in blocklist → safe
        if cls.is_known_artist([artist_name]):
            return False
        # Original regex patterns (ending in Channel, TV, Media, etc.)
        if cls.NON_ARTIST_CHANNEL_RE.match(name):
            return True
        # Keyword-based: name CONTAINS channel-indicator words
        if cls.NON_ARTIST_CHANNEL_KEYWORDS.search(name):
            return True
        return False

    # Pre-computed: strip diacritics for fuzzy blocklist matching
    @staticmethod
    def _strip_vn_diacritics(text: str) -> str:
        """Remove Vietnamese diacritics for fuzzy matching.
        'Hồ Quang Hiếu' → 'ho quang hieu', 'Đăng Khôi' → 'dang khoi'"""
        import unicodedata
        # Đ/đ → D/d (special case, not handled by NFD)
        text = text.replace('Đ', 'D').replace('đ', 'd')
        # NFD decompose → remove combining marks → NFC
        nfd = unicodedata.normalize('NFD', text)
        stripped = ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')
        return stripped.lower().strip()

    _OLD_GENRE_BLOCKLIST_STRIPPED = None  # lazy init

    @classmethod
    def _get_stripped_blocklist(cls):
        if cls._OLD_GENRE_BLOCKLIST_STRIPPED is None:
            cls._OLD_GENRE_BLOCKLIST_STRIPPED = {
                cls._strip_vn_diacritics(name) for name in cls.OLD_GENRE_BLOCKLIST
            }
        return cls._OLD_GENRE_BLOCKLIST_STRIPPED

    @classmethod
    def is_old_genre_blocked(cls, artist_names: List[str]) -> bool:
        """Check if any artist is in the old-genre blocklist (bolero/nhạc vàng/hải ngoại).
        Matches both with-diacritics and stripped-diacritics versions."""
        stripped_bl = cls._get_stripped_blocklist()
        for name in artist_names:
            # Exempt only this current artist. Other credited artists still
            # need to be checked so a modern + old-genre collaboration does
            # not bypass the filter.
            if cls.is_current_artist([name]):
                continue
            cleaned = name.lower().strip()
            # Exact match (with diacritics)
            if cleaned in cls.OLD_GENRE_BLOCKLIST:
                return True
            # Fuzzy match (stripped diacritics)
            if cls._strip_vn_diacritics(name) in stripped_bl:
                return True
        return False

    # Foreign DJ/MC pattern — Brazilian MC/DJ artists that slip through
    FOREIGN_DJ_MC_RE = re.compile(
        r'(?i)^(?:MC|Mc|mc|DJ|Dj|dj)\s+'
        r'(?!12\b|LongB\b|Wiz\b|IQ\b)'
        r'[A-Z]',
    )

    @classmethod
    def is_foreign_artist_pattern(cls, name: str) -> bool:
        """Check if artist name matches foreign artist patterns (Brazilian MC/DJ etc)."""
        if cls.is_known_artist([name]):
            return False
        n = name.strip()
        # Brazilian MC/DJ: "MC Jessica do escadão", "DJ Bulico Cachorrão"
        if cls.FOREIGN_DJ_MC_RE.match(n):
            # Allow if name has Vietnamese chars
            if cls.has_truly_unique_vn_chars(n):
                return False
            return True
        # "Da Ponte Pra Cá" style — Portuguese prepositions
        if re.search(r'\b(?:do|da|dos|das|pra|pro|cá|lá|não|cachorrão|escadão|favela|baile|funk)\b', n, re.IGNORECASE):
            if not cls.has_truly_unique_vn_chars(n):
                return True
        return False

    @classmethod
    def is_foreign_blocked(cls, artist_names: List[str]) -> bool:
        """Check if any artist is in the foreign artist blocklist or matches foreign patterns."""
        for name in artist_names:
            if name.lower().strip() in cls.FOREIGN_ARTISTS_BLOCKLIST:
                return True
            if cls.is_foreign_artist_pattern(name):
                return True
        return False

    @classmethod
    def is_garbage_track(cls, track_name: str) -> bool:
        """Check if track title contains garbage patterns (karaoke, beat, instrumental, live)."""
        return bool(cls.TRACK_GARBAGE_RE.search(track_name) or cls.TRACK_LIVE_RE.search(track_name))

    @classmethod
    def detect_langdetect(cls, text: str) -> bool:
        if not HAS_LANGDETECT or len(text) < 10:
            return False
        try:
            return langdetect_detect(text) == "vi"
        except Exception:
            return False

    @classmethod
    def is_children_music(cls, track_name: str, artist: str, album: str) -> bool:
        if cls.CHILDREN_ARTIST_PATTERNS.search(artist):
            return True
        if cls.CHILDREN_ALBUM_PATTERNS.search(album):
            return True
        if cls.CHILDREN_TRACK_PATTERNS.search(track_name):
            return True
        return False

    @classmethod
    def _has_only_shared_diacritics(cls, text: str) -> bool:
        """Check if ALL diacritics in text are shared with French/Spanish (é è ê à á etc.)
        i.e., no uniquely-Vietnamese diacritics like ắ ằ ẻ ẽ ẹ ố ồ etc."""
        diacritics_found = set(c for c in text if c in Config.VIETNAMESE_ALL_DIACRITICS)
        if not diacritics_found:
            return True  # no diacritics at all
        # If every diacritical char is in the shared set, text could be French/Spanish
        return diacritics_found.issubset(cls.SHARED_FRENCH_VN_DIACRITICS)

    @classmethod
    def is_vietnamese(cls, track_name: str, artist_names: List[str],
                      album_name: str = "",
                      discovered_artists: set = None) -> Tuple[bool, str]:
        """
        Xác định bài hát có phải tiếng Việt không (v5 — blocks Portuguese/Brazilian leak).
        Returns: (is_vietnamese, reason)
        """
        # Strip " - Topic" suffix from artist names for cleaner detection
        clean_names = [re.sub(r'\s*-\s*Topic$', '', n).strip() for n in artist_names]
        combined_text = f"{track_name} {' '.join(clean_names)} {album_name}"

        # -3. Old-genre artist blocklist — checked FIRST, overrides whitelist
        #     (bolero, nhạc vàng, hải ngoại, old-gen pop, nhạc trẻ sến, etc.)
        if cls.is_old_genre_blocked(clean_names):
            return False, "old_genre_blocked"

        # 0. Known artist — whitelisted names bypass remaining filters
        #    BUT: for short ASCII-only names (jack, min, erik) that could collide
        #    with foreign artists, require Vietnamese evidence from track/album
        if cls.is_known_artist(clean_names):
            primary = clean_names[0].lower().strip() if clean_names else ""
            is_ascii_short = len(primary) <= 5 and all(ord(c) < 128 for c in primary if not c.isspace())
            if is_ascii_short:
                # Require at least one VN indicator from track/album text
                track_album_text = f"{track_name} {album_name}"
                if (cls.has_vietnamese_chars(track_album_text)
                        or cls.has_common_vn_words(track_album_text)
                        or cls.has_vietnamese_diacritics(track_album_text)):
                    return True, "known_artist"
                # else: fall through to normal detection pipeline
            else:
                return True, "known_artist"

        # -2. Foreign artist blocklist (Brazilian, French, etc.)
        if cls.is_foreign_blocked(clean_names):
            return False, "foreign_blocked"

        # -1. Garbage names: dates, numbers, view counts, parse artifacts
        for name in clean_names:
            if cls.is_garbage_name(name):
                return False, "garbage_artist_name"

        # 0a. Foreign chars (Korean/Japanese/Chinese/Thai/Cyrillic/Arabic/Hindi)
        if cls.has_foreign_chars(combined_text):
            if not cls.has_truly_unique_vn_chars(combined_text):
                return False, "foreign_chars"

        # 0b. Non-Vietnamese European diacritics (German, French umlaut, Nordic)
        if cls.has_non_vn_diacritics(combined_text):
            if not cls.has_truly_unique_vn_chars(combined_text):
                return False, "non_vn_diacritics"

        # 1. Truly unique Vietnamese chars (đ, ă, ơ, ư + combining forms like ắ ằ ớ ờ ứ ừ)
        #    Plain â ê ô are shared with French/Portuguese — NOT sufficient alone
        #    BUT: Đ (D-stroke) is also used in Bosnian/Serbian → check Balkan indicators
        if cls.has_truly_unique_vn_chars(combined_text):
            vn_unique = (Config.VIETNAMESE_UNIQUE_CHARS & set(combined_text)) - cls.SHARED_CIRCUMFLEX_CHARS
            # If the ONLY unique char is Đ/đ, check for Balkan language
            if vn_unique <= {'đ', 'Đ'}:
                if cls.BALKAN_INDICATORS.search(combined_text):
                    return False, "balkan_language"
            return True, "vietnamese_chars"

        # 1b. â ê ô present but only with VN context (common words or many diacritics)
        if cls.has_vietnamese_chars(combined_text):
            # Has â/ê/ô — accept only if combined with common VN words
            if cls.has_common_vn_words(combined_text):
                return True, "vietnamese_chars"

        # 2b. Discovered VN artists (dynamic)
        if discovered_artists:
            primary = clean_names[0].strip().lower() if clean_names else ""
            if primary in discovered_artists:
                return True, "discovered_artist"

        # 3. Multiple VN diacritics (≥3) — but ONLY if they include uniquely-VN chars
        #    Shared chars (é è ê à á ù ô â) alone do NOT prove Vietnamese (could be French)
        vn_diac_count = sum(1 for c in combined_text if c in Config.VIETNAMESE_ALL_DIACRITICS)
        if vn_diac_count >= 3:
            if not cls.has_non_vn_diacritics(combined_text):
                if not cls._has_only_shared_diacritics(combined_text):
                    return True, "diacritics_multiple"

        # 4. Common VN words (confirmed — need ≥2 matches or unique VN diacritics)
        if cls.has_common_vn_words(track_name):
            matches = cls.COMMON_VN_WORDS.findall(combined_text.lower())
            if len(matches) >= 2:
                return True, "common_words_confirmed"
            if vn_diac_count >= 1 and not cls._has_only_shared_diacritics(combined_text):
                return True, "common_words_confirmed"

        # 5. langdetect — only trust if there are uniquely-VN diacritics
        if cls.detect_langdetect(combined_text):
            if not cls.has_non_vn_diacritics(combined_text):
                if not cls._has_only_shared_diacritics(combined_text):
                    return True, "langdetect"

        # 6. langdetect on track_name — strictest gate
        if len(track_name.strip()) >= 10:
            try:
                if cls.detect_langdetect(track_name):
                    if cls.has_common_vn_words(track_name):
                        if not cls.has_non_vn_diacritics(combined_text):
                            return True, "langdetect_confirmed"
            except Exception:
                pass

        return False, "not_vietnamese"


# ============================================================================
# PLAYLIST DISCOVERY COLLECTOR v10.0 — YTMusic-Only
# ============================================================================
class PlaylistDiscoveryCollector:
    """
    v12.0: Spotify artists + YTMusic tracks.

    Flow:
      Step 0: Spotify search + playlist + track mining → genre-validated artists
      Step 1: Resolve Spotify artists on YTMusic → get channelId
      Step 2: Collect ALL tracks via YTMusic (get_artist → get_album)
      Step 3: Discover featured artists from track credits + collect their tracks
      Step 4: Vietnamese filter + dedup + export
    """

    PARALLEL_WORKERS = 16  # Number of parallel YTMusic sessions

    def __init__(self):
        self._yt = None
        self.tracks = {}          # videoId → track data (from YTMusic)
        self.artists = {}         # normalized_key → {name, yt_channel_id, ...}
        self.visited_yt_channels = set()
        self.visited_yt_albums = set()
        self.api_calls = 0
        self._lock = threading.Lock()  # thread-safe access
        self.existing_track_ids = self._load_existing_track_ids()

    @staticmethod
    def _load_existing_track_ids() -> set[str]:
        """Load active and intentionally removed IDs to avoid recollection."""
        candidates = [
            Config.BASE_DIR / "data" / "vietnamese_music_processed_full.csv",
            Config.BASE_DIR / "checkpoints" / "phase5_features.csv",
            Config.BASE_DIR / "checkpoints" / "phase3_downloaded.csv",
            Config.BASE_DIR / "checkpoints" / "phase2_filtered.csv",
        ]
        candidates.extend(
            sorted(
                (Config.BASE_DIR / "data").glob("filtered_out_tracks_*.csv"),
                reverse=True,
            )[:2]
        )

        existing_ids: set[str] = set()
        for csv_path in candidates:
            if not csv_path.exists():
                continue
            try:
                ids = pd.read_csv(csv_path, usecols=["track_id"])["track_id"]
                existing_ids.update(
                    value
                    for value in ids.astype(str)
                    if value and value.lower() not in {"nan", "none"}
                )
            except Exception as exc:
                log.debug(f"  Could not load existing IDs from {csv_path}: {exc}")

        if existing_ids:
            log.info(
                f"  Skip-existing: loaded {len(existing_ids):,} active/rejected track IDs"
            )
        return existing_ids

    @staticmethod
    def _create_yt_instance():
        """Create a new YTMusic instance with 30s timeout."""
        from ytmusicapi import YTMusic
        yt = YTMusic()
        yt._session.request = _add_default_timeout(yt._session.request, timeout=30)
        return yt

    @property
    def yt(self):
        if self._yt is None:
            try:
                self._yt = self._create_yt_instance()
            except Exception as e:
                log.warning(f"  ytmusicapi init failed: {e}")
                self._yt = False
        return self._yt if self._yt is not False else None

    def _yt_delay(self, seconds=None):
        time.sleep(seconds or Config.YTMUSIC_DELAY)
        self.api_calls += 1

    def _is_valid_artist(self, name: str) -> bool:
        """Check if artist name passes ALL validation gates before adding to pool.
        Returns True only for real Vietnamese artists (not channels, old-genre, foreign, garbage)."""
        if not name or len(name.strip()) < 2:
            return False
        if VietnameseDetector.is_garbage_name(name):
            return False
        if VietnameseDetector.is_non_artist_channel(name):
            return False
        if VietnameseDetector.is_old_genre_blocked([name]):
            return False
        if VietnameseDetector.is_foreign_blocked([name]):
            return False
        is_vn, _ = VietnameseDetector.is_vietnamese(name, [name], "")
        return is_vn

    @staticmethod
    def _normalize_artist_key(name: str) -> str:
        """Normalize artist name for dedup (lower, strip, collapse variants)."""
        key = name.lower().strip()
        # Normalize common spelling variants
        key = key.replace("-", " ").replace(".", "").replace("'", "")
        # Collapse multiple spaces
        key = re.sub(r'\s+', ' ', key)
        return key

    # ------------------------------------------------------------------
    # Spotify helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _create_spotify_client():
        """Create a rate-limited Spotify client with multi-app credential rotation.

        Loads all SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET pairs from .env:
          - SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET  (primary)
          - SPOTIFY_CLIENT_ID_2 / SPOTIFY_CLIENT_SECRET_2  (secondary)
          - SPOTIFY_CLIENT_ID_N / SPOTIFY_CLIENT_SECRET_N  (up to 9)

        Returns a SpotifyRateLimiter with app rotation (or None if no credentials).
        """
        if not HAS_SPOTIPY:
            return None

        credentials = []
        # Primary credentials
        id1 = os.getenv("SPOTIFY_CLIENT_ID")
        secret1 = os.getenv("SPOTIFY_CLIENT_SECRET")
        if id1 and secret1:
            credentials.append((id1, secret1))
        # Additional credentials (_2 through _9)
        for i in range(2, 10):
            id_n = os.getenv(f"SPOTIFY_CLIENT_ID_{i}")
            secret_n = os.getenv(f"SPOTIFY_CLIENT_SECRET_{i}")
            if id_n and secret_n:
                credentials.append((id_n, secret_n))

        if not credentials:
            log.warning("  No Spotify credentials found in .env")
            return None

        log.info(f"  Found {len(credentials)} Spotify app(s) in .env")

        # Try each credential until one works (or accept rate-limited one)
        last_limiter = None
        for start_idx in range(len(credentials)):
            try:
                rate_limited = SpotifyRateLimiter(credentials)
                rate_limited._init_client(start_idx)
                # Quick connectivity test
                rate_limited.search(q="test", type="artist", limit=1)
                log.info(f"  Spotify app #{start_idx + 1} ready "
                         f"(rate limit: {Config.SPOTIFY_MAX_CALLS_PER_30S} calls/30s)")
                return rate_limited
            except SpotifyRateLimitBan:
                log.warning(f"  Spotify app #{start_idx + 1} is rate-limited on test, "
                            f"but will retry during collection (progressive backoff)")
                last_limiter = rate_limited  # Keep it — may work later
                continue
            except spotipy.exceptions.SpotifyException as e:
                if e.http_status == 429:
                    log.warning(f"  Spotify app #{start_idx + 1} got 429 on test, "
                                f"but will retry during collection (progressive backoff)")
                    last_limiter = rate_limited
                    continue
                log.warning(f"  Spotify app #{start_idx + 1} failed: {e}, trying next...")
                continue
            except Exception as e:
                log.warning(f"  Spotify app #{start_idx + 1} failed: {e}, trying next...")
                continue

        # If all apps got 429 but we have a client, return it — progressive backoff
        # will handle retries during actual data collection
        if last_limiter is not None:
            log.warning("  All Spotify apps rate-limited on connectivity test, "
                        "but returning client — progressive backoff will retry")
            return last_limiter

        log.error("  All Spotify apps failed (credential errors)!")
        return None

    @staticmethod
    def _is_spotify_vn_genre(genres: list) -> bool:
        """Check if Spotify genres indicate a Vietnamese artist."""
        for g in genres:
            gl = g.lower()
            if gl in Config.SPOTIFY_VN_GENRES:
                return True
            if any(kw in gl for kw in Config.SPOTIFY_VN_GENRE_KEYWORDS):
                return True
        return False

    @staticmethod
    def _is_spotify_reject_genre(genres: list) -> bool:
        """Check if Spotify genres indicate old-genre / bolero to reject."""
        for g in genres:
            gl = g.lower()
            if gl in Config.SPOTIFY_REJECT_GENRES:
                return True
            if any(kw in gl for kw in Config.SPOTIFY_REJECT_GENRE_KEYWORDS):
                return True
        return False

    @staticmethod
    def _is_spotify_foreign_genre(genres: list) -> bool:
        """Check if artist has ONLY foreign genres (no VN genre).
        Returns True if should reject (foreign-only)."""
        if not genres:
            return False
        has_vn = PlaylistDiscoveryCollector._is_spotify_vn_genre(genres)
        if has_vn:
            return False  # Has VN genre — keep even if also has foreign
        has_foreign = any(g.lower() in Config.SPOTIFY_FOREIGN_GENRES for g in genres)
        return has_foreign

    def _add_spotify_artist(self, name: str, spotify_id: str, genres: list,
                            popularity: int, discovery: str, followers: int = 0,
                            image_url: str = None):
        """Add an artist discovered from Spotify to self.artists.
        Returns True if added (new + valid), False if skipped."""
        if not name or len(name.strip()) < 2:
            return False
        key = self._normalize_artist_key(name)
        if key in self.artists:
            # Already known — just enrich with Spotify ID
            if spotify_id and not self.artists[key].get("spotify_id"):
                self.artists[key]["spotify_id"] = spotify_id
                self.artists[key]["spotify_genres"] = genres
                self.artists[key]["spotify_popularity"] = popularity
            if image_url and not self.artists[key].get("image_url"):
                self.artists[key]["image_url"] = image_url
            return False

        # Genre-based validation (Spotify's major advantage)
        if genres:
            # Reject old-genre artists
            if self._is_spotify_reject_genre(genres):
                return False
            # Reject foreign-only genres (k-pop, j-rock, c-pop, etc.)
            if self._is_spotify_foreign_genre(genres):
                return False
            # Accept confirmed VN genres
            if self._is_spotify_vn_genre(genres):
                # Still check basic blocklists
                if VietnameseDetector.is_garbage_name(name):
                    return False
                if VietnameseDetector.is_non_artist_channel(name):
                    return False
                if VietnameseDetector.is_foreign_blocked([name]):
                    return False
                if VietnameseDetector.is_old_genre_blocked([name]):
                    return False
                # Reject CJK/foreign character names even with VN genre
                if VietnameseDetector.has_foreign_chars(name):
                    return False
                self.artists[key] = {
                    "name": name,
                    "yt_channel_id": None,
                    "discovery": discovery,
                    "spotify_id": spotify_id,
                    "spotify_genres": genres,
                    "spotify_popularity": popularity,
                    "spotify_followers": followers,
                    "image_url": image_url,
                }
                return True

        # No VN genre tag — fall back to full validation
        # First try name-only detection
        if self._is_valid_artist(name):
            self.artists[key] = {
                "name": name,
                "yt_channel_id": None,
                "discovery": discovery,
                "spotify_id": spotify_id,
                "spotify_genres": genres,
                "spotify_popularity": popularity,
                "spotify_followers": followers,
                "image_url": image_url,
            }
            return True

        # Name alone didn't confirm VN — try searching tracks for context
        # Many VN artists have ASCII names (HIEUTHUHAI, tlinh, MIN) but VN track titles
        # Uses search API (artist_top_tracks is dead since March 2026)
        # Only enabled for Strategy D (known artists) to save API calls
        if spotify_id and getattr(self, '_enable_track_fallback', False) and hasattr(self, '_spotify_client_ref'):
            try:
                sp = self._spotify_client_ref
                results = sp.search(
                    q=f'artist:"{name}"', type='track',
                    market='VN', limit=5,
                )
                tracks = results.get('tracks', {}).get('items', [])
                vn_track_count = 0
                for t in tracks[:5]:
                    # Verify correct artist
                    track_artist_ids = {a.get('id') for a in (t.get('artists') or [])}
                    if spotify_id not in track_artist_ids:
                        continue
                    t_name = t.get("name", "")
                    album_name = (t.get("album") or {}).get("name", "")
                    is_vn, _ = VietnameseDetector.is_vietnamese(t_name, [name], album_name)
                    if is_vn:
                        vn_track_count += 1
                if vn_track_count >= 2:
                    # Basic blocklist checks
                    if VietnameseDetector.is_garbage_name(name):
                        return False
                    if VietnameseDetector.is_non_artist_channel(name):
                        return False
                    if VietnameseDetector.is_old_genre_blocked([name]):
                        return False
                    if VietnameseDetector.is_foreign_blocked([name]):
                        return False
                    self.artists[key] = {
                        "name": name,
                        "yt_channel_id": None,
                        "discovery": discovery,
                        "spotify_id": spotify_id,
                        "spotify_genres": genres,
                        "spotify_popularity": popularity,
                        "spotify_followers": followers,
                        "image_url": image_url,
                    }
                    return True
            except Exception:
                pass

        return False

    # ------------------------------------------------------------------
    # STEP 0: Spotify Artist Discovery (v13.0 — Spotify only, strategies A/B/D)
    # ------------------------------------------------------------------
    def discover_artists_from_spotify(self, ckpt=None, resume=False):
        """Discover Vietnamese artists using Spotify metadata API.

        Uses Client Credentials flow (no user login needed).
        Spotify provides curated artist metadata with genre tags,
        making it far more reliable than YTMusic for artist validation.

        Discovery sources (v13.0 — Spotify only):
          A. Search Vietnamese music queries (type='artist', market='VN')
          B. Mine V-Pop / Vietnamese playlists → extract all artists
          D. Lookup KNOWN_ARTISTS whitelist → find Spotify IDs + validate

        Rate limiting (per developer.spotify.com/documentation/web-api/concepts/rate-limits):
          - Rolling 30-second window, max ~50 calls/window
          - SpotifyRateLimiter handles throttling, backoff, 429 responses
          - Per-strategy checkpointing for resume on rate limit ban
        """
        log.info(f"\n{'='*70}")
        log.info(f"  Step 0: Spotify → Vietnamese Artist Discovery")
        log.info(f"{'='*70}")

        # Load strategy progress for resume
        strategy_state = {}
        if resume and ckpt:
            if ckpt.exists("spotify_artists"):
                saved = ckpt.load("spotify_artists")
                if saved:
                    self.artists = saved
                    log.info(f"  Resumed {len(self.artists)} artists from Spotify checkpoint")
            strategy_state = ckpt.load("discovery_strategy_state") or {}

        sp = self._create_spotify_client()
        if not sp:
            log.warning("  Spotify not available — falling back to YTMusic-only discovery")
            return

        self._spotify_client_ref = sp  # used by _add_spotify_artist top-track fallback
        before = len(self.artists)

        try:
            # ══════════════════════════════════════════════════════════
            # A: Search Vietnamese music queries (type='artist')
            # ══════════════════════════════════════════════════════════
            if not strategy_state.get("a_done"):
                self._strategy_a_artist_search(sp, ckpt)
                strategy_state["a_done"] = True
                if ckpt:
                    ckpt.save("spotify_artists", self.artists)
                    ckpt.save("discovery_strategy_state", strategy_state)
                log.info(f"  Cooldown {Config.STRATEGY_COOLDOWN}s between strategies...")
                time.sleep(Config.STRATEGY_COOLDOWN)
            else:
                log.info(f"  A: Skipped (already completed in previous run)")

            # ══════════════════════════════════════════════════════════
            # B: Mine Vietnamese playlists
            # ══════════════════════════════════════════════════════════
            if not strategy_state.get("b_done"):
                self._strategy_b_playlist_mining(sp, ckpt)
                strategy_state["b_done"] = True
                if ckpt:
                    ckpt.save("spotify_artists", self.artists)
                    ckpt.save("discovery_strategy_state", strategy_state)
                log.info(f"  Cooldown {Config.STRATEGY_COOLDOWN}s between strategies...")
                time.sleep(Config.STRATEGY_COOLDOWN)
            else:
                log.info(f"  B: Skipped (already completed in previous run)")

            # ══════════════════════════════════════════════════════════
            # D: Lookup KNOWN_ARTISTS whitelist on Spotify
            # ══════════════════════════════════════════════════════════
            if not strategy_state.get("d_done"):
                # Enable track-based VN detection for known artists
                # (disabled during A/B to save API calls)
                self._enable_track_fallback = True
                self._strategy_d_known_artists(sp, ckpt)
                self._enable_track_fallback = False
                strategy_state["d_done"] = True
                if ckpt:
                    ckpt.save("spotify_artists", self.artists)
                    ckpt.save("discovery_strategy_state", strategy_state)
            else:
                log.info(f"  D: Skipped (already completed in previous run)")

        except Exception as e:
            log.error(f"\n  Unexpected error during discovery: {e}")
            if ckpt:
                ckpt.save("spotify_artists", self.artists)
                ckpt.save("discovery_strategy_state", strategy_state)

        # ── Summary ──
        total_added = len(self.artists) - before
        log.info(f"\n  Spotify Discovery Summary (v13.0 — strategies A/B/D):")
        log.info(f"    Total artists: {len(self.artists)} (+{total_added} new)")
        if hasattr(sp, 'total_calls'):
            log.info(f"    Spotify API calls: {sp.total_calls}")

        with_vn_genre = sum(
            1 for v in self.artists.values()
            if v.get("spotify_genres") and self._is_spotify_vn_genre(v["spotify_genres"])
        )
        with_any_genre = sum(1 for v in self.artists.values() if v.get("spotify_genres"))
        log.info(f"    With VN genre tag: {with_vn_genre}")
        log.info(f"    With any genre tag: {with_any_genre}")

        if ckpt:
            ckpt.save("spotify_artists", self.artists)
            # Clear strategy state so next full run starts fresh
            strategy_state_path = ckpt.dir / "discovery_strategy_state.json"
            if strategy_state_path.exists():
                strategy_state_path.unlink()

    # ------------------------------------------------------------------
    # Strategy A: Artist Search
    # ------------------------------------------------------------------
    def _strategy_a_artist_search(self, sp, ckpt=None):
        """Search Vietnamese music queries to discover artists.

        Uses combined type='artist,track' search to get BOTH artist results
        AND extract artists from track results in a single API call.
        Spotify search limit is 0-10.  We do 1 page per query to save quota
        (Spotify dev apps have low daily limits).
        """
        before = len(self.artists)

        artist_queries = [
            # ── Core Vietnamese genre keywords (highest signal) ──
            "v-pop", "vpop", "vietnamese pop", "vietnamese hip hop",
            "vietnam indie", "vinahouse", "vietnamese r&b",
            "vietnamese electronic", "vietnamese trap", "vietnamese drill",
            "vietnamese lo-fi",
            # ── Vietnamese language queries ──
            "nhạc trẻ", "nhạc Việt", "ca sĩ Việt Nam", "nghệ sĩ Việt",
            "nhạc sĩ Việt Nam", "ca sĩ trẻ Việt Nam",
            "rap Việt", "rapper Việt Nam", "hip hop Việt",
            "R&B Việt", "pop Việt", "indie Việt",
            "underground Việt", "EDM Việt", "nhạc điện tử Việt",
            # ── Game shows / TV (important discovery source) ──
            "Anh Trai Say Hi", "Anh Trai Vượt Ngàn Chông Gai",
            "Rap Việt", "The Masked Singer Vietnam",
            "The Voice Vietnam", "Vietnam Idol",
            "King of Rap", "Bạn Có Tài Mà",
            # ── Trending / viral ──
            "nhạc hot GenZ Việt", "TikTok Việt",
            "nhạc viral Việt", "vpop trending",
            "nhạc Việt mới nhất", "nhạc Việt trending",
            # ── Mood / genre sub-categories ──
            "ballad Việt", "nhạc chill Việt", "lo-fi Việt",
            "acoustic Việt", "nhạc buồn Việt",
            "nhạc dance Việt", "nhạc remix Việt",
            "edm việt nam", "deep house việt",
            "trap việt nam", "drill việt nam",
            "r&b việt nam", "indie việt nam",
            # ── English queries ──
            "vietnamese singer", "vietnam music",
            "vietnamese artist", "v-pop artist",
            "vietnamese rapper", "vietnamese band",
            "vietnam top hits", "vietnamese new music",
            # ── Regional ──
            "tây nguyên sound", "underground sài gòn",
            "underground hà nội",
            # ── Additional ──
            "nhạc trẻ việt nam", "top nghệ sĩ việt nam",
            "nhạc việt hot nhất", "nghệ sĩ trẻ việt nam",
            "producer việt nam", "dj việt nam",
            "bảng xếp hạng nhạc Việt", "top 100 nhạc Việt",
            "city pop việt", "phonk việt",
            # ── Chart / Award-based discovery ──
            "Zing Music Awards", "Làn Sóng Xanh",
            "Cống Hiến", "WeChoice Awards ca sĩ",
            "Billboard Vietnam", "Top 50 Vietnam",
            "ZingChart", "NhacCuaTui",
            # ── Năm cụ thể (tín hiệu mạnh cho nhạc hiện đại) ──
            "vpop 2023", "vpop 2024", "vpop 2025",
            "nhạc Việt 2024", "nhạc Việt 2025",
            # ── Genre còn thiếu ──
            "bedroom pop Việt", "indie pop Việt Nam",
            "singer songwriter Việt", "neo soul Việt Nam",
            "chill r&b Việt Nam", "alternative Việt Nam",
            # ── Platform / trend signal ──
            "nhạc hot TikTok Việt", "nhạc viral Việt 2024",
            # ── Scene underground bổ sung ──
            "underground rap Hà Nội", "underground rap Sài Gòn",
            "underground hiphop Việt 2024",
        ]

        # Combined artist+track search: 1 API call returns BOTH types
        # This means 86 queries × 1 call = 86 calls (not 86 × 5 = 430)
        SEARCH_LIMIT = 10

        log.info(f"  A: Searching {len(artist_queries)} queries "
                 f"(combined artist+track, limit={SEARCH_LIMIT})...")
        track_artist_ids = set()  # Collect artist IDs from tracks for batch lookup

        for query in tqdm(artist_queries, desc="Strategy A: artist+track search"):
            try:
                results = sp.search(
                    q=query, type="artist,track", market="VN",
                    limit=SEARCH_LIMIT,
                )
                # --- Extract from artist results ---
                for a in results.get("artists", {}).get("items", []):
                    if not a:
                        continue
                    name = a.get("name", "").strip()
                    sid = a.get("id", "")
                    genres = a.get("genres", [])
                    pop = a.get("popularity", 0)
                    followers = (a.get("followers") or {}).get("total", 0)
                    images = a.get("images") or []
                    img_url = images[0]["url"] if images else None
                    self._add_spotify_artist(
                        name, sid, genres, pop,
                        "spotify_search", followers, img_url,
                    )
                # --- Extract artist IDs from track results ---
                for track in results.get("tracks", {}).get("items", []):
                    if not track:
                        continue
                    for art in (track.get("artists") or []):
                        art_id = art.get("id")
                        if art_id:
                            track_artist_ids.add(art_id)
            except SpotifyRateLimitBan:
                raise
            except Exception as e:
                log.warning(f"  Search error for '{query}': {e}")

        # Batch-fetch artist details from track discoveries (50 per call)
        # Remove IDs we already have
        existing_sids = {v.get("spotify_id") for v in self.artists.values() if v.get("spotify_id")}
        new_artist_ids = track_artist_ids - existing_sids
        if new_artist_ids:
            log.info(f"  A: Batch-fetching {len(new_artist_ids)} new artists from tracks...")
            id_list = list(new_artist_ids)
            for i in range(0, len(id_list), 50):
                batch = id_list[i:i+50]
                try:
                    result = sp.artists(batch)
                    for a in (result.get("artists") or []):
                        if not a:
                            continue
                        name = a.get("name", "").strip()
                        sid = a.get("id", "")
                        genres = a.get("genres", [])
                        pop = a.get("popularity", 0)
                        followers = (a.get("followers") or {}).get("total", 0)
                        images = a.get("images") or []
                        img_url = images[0]["url"] if images else None
                        self._add_spotify_artist(
                            name, sid, genres, pop,
                            "spotify_track_search", followers, img_url,
                        )
                except SpotifyRateLimitBan:
                    raise
                except Exception as e:
                    log.warning(f"  Batch artist error: {e}")

        after_a = len(self.artists) - before
        log.info(f"  A: +{after_a} artists from {len(artist_queries)} combined searches "
                 f"({len(track_artist_ids)} track artist IDs, "
                 f"{len(new_artist_ids)} new batch-fetched)")

    # ------------------------------------------------------------------
    # Strategy B: Track Search Mining (supplementary — different queries from A)
    # ------------------------------------------------------------------
    def _strategy_b_playlist_mining(self, sp, ckpt=None):
        """Discover MORE artists via track-oriented queries not in Strategy A.

        Strategy A already does combined artist+track search.  This strategy
        uses track-specific queries (playlist names, year-based, mood-based)
        that differ from A's artist-oriented queries.

        1 API call per query (limit=10, combined artist+track).
        """
        before_b = len(self.artists)

        track_queries = [
            # ── Playlist-style names (track-oriented) ──
            "Thiên hạ nghe gì", "Hot Hits Vietnam",
            "V-Pop không thể thiếu", "V-Sound ngay lúc này",
            "Nhạc Việt Mới", "V-Pop Rising",
            "Rap Việt Hay Nhất", "Ballad Việt Hay Nhất",
            "Chill Hits Vietnam", "Love Pop Vietnam",
            "Trending Vietnam", "Viral Hits Vietnam",
            "New Music Friday Vietnam",
            "Đường Đua V-Pop", "Nhạc Trẻ Hay Nhất",
            "Rap Việt All Stars", "Nhạc Việt Triệu View",
            # ── Year + mood queries (not in A) ──
            "nhạc Việt 2024", "nhạc Việt 2025", "nhạc Việt 2026",
            "bài hát Việt hay nhất", "hit Việt Nam",
            "nhạc trữ tình Việt", "nhạc tình cảm Việt",
            "duet Việt Nam", "nhạc cover Việt",
            "nhạc phim Việt", "OST Việt Nam",
            "nhạc Việt triệu view", "nhạc Việt hay nhất mọi thời đại",
        ]

        SEARCH_LIMIT = 10

        log.info(f"  B: Mining {len(track_queries)} track queries (limit={SEARCH_LIMIT})...")
        track_artist_ids = set()

        for query in tqdm(track_queries, desc="Strategy B: track search mining"):
            try:
                results = sp.search(
                    q=query, type="track", market="VN",
                    limit=SEARCH_LIMIT,
                )
                items = results.get("tracks", {}).get("items", [])
                if not items:
                    continue
                for track in items:
                    if not track:
                        continue
                    for art in (track.get("artists") or []):
                        art_id = art.get("id")
                        if art_id:
                            track_artist_ids.add(art_id)
            except SpotifyRateLimitBan:
                log.warning(f"  B: 429 timeout on query '{query}' — skipping, continuing...")
            except Exception as e:
                log.warning(f"  Track search error for '{query}': {e}")

        # Batch-fetch artist details — only new IDs
        existing_sids = {v.get("spotify_id") for v in self.artists.values() if v.get("spotify_id")}
        new_ids = track_artist_ids - existing_sids
        if new_ids:
            log.info(f"  B: Batch-fetching {len(new_ids)} new artists from tracks...")
            id_list = list(new_ids)
            for i in range(0, len(id_list), 50):
                batch = id_list[i:i+50]
                try:
                    result = sp.artists(batch)
                    for a in (result.get("artists") or []):
                        if not a:
                            continue
                        name = a.get("name", "").strip()
                        sid = a.get("id", "")
                        genres = a.get("genres", [])
                        pop = a.get("popularity", 0)
                        followers = (a.get("followers") or {}).get("total", 0)
                        images = a.get("images") or []
                        img_url = images[0]["url"] if images else None
                        self._add_spotify_artist(
                            name, sid, genres, pop,
                            "spotify_track_search", followers, img_url,
                        )
                except SpotifyRateLimitBan:
                    log.warning(f"  B: 429 timeout on batch — skipping, continuing...")
                except Exception as e:
                    log.warning(f"  Batch artist error: {e}")

        after_b = len(self.artists) - before_b
        log.info(f"  B: +{after_b} artists from track search "
                 f"({len(track_artist_ids)} unique artist IDs, "
                 f"{len(new_ids)} new)")

    # ------------------------------------------------------------------
    # Strategy D: Known Artist Lookup
    # ------------------------------------------------------------------
    def _strategy_d_known_artists(self, sp, ckpt=None):
        """Look up KNOWN_ARTISTS whitelist on Spotify for IDs + metadata.

        These are verified Vietnamese artists — but still apply genre/blocklist checks.
        """
        log.info(f"  D: Looking up {len(VietnameseDetector.KNOWN_ARTISTS)} known artists...")
        before_d = len(self.artists)
        known_found = 0

        known_unique = set()
        for ka in VietnameseDetector.KNOWN_ARTISTS:
            key = self._normalize_artist_key(ka)
            if key not in known_unique and key not in self.artists:
                known_unique.add(key)

        for ka_key in tqdm(sorted(known_unique), desc="Strategy D: known artist lookup"):
            try:
                results = sp.search(
                    q=f"artist:{ka_key}", type="artist", market="VN", limit=5,
                )
                for a in results.get("artists", {}).get("items", []):
                    found_key = self._normalize_artist_key(a.get("name", ""))
                    if found_key == ka_key or ka_key in found_key or found_key in ka_key:
                        name = a.get("name", "").strip()
                        sid = a.get("id", "")
                        genres = a.get("genres", [])
                        pop = a.get("popularity", 0)
                        followers = (a.get("followers") or {}).get("total", 0)
                        images = a.get("images") or []
                        img_url = images[0]["url"] if images else None
                        added = self._add_spotify_artist(
                            name, sid, genres, pop,
                            "spotify_known_lookup", followers, img_url,
                        )
                        if added:
                            known_found += 1
                        break
            except SpotifyRateLimitBan:
                    log.warning(f"  D: 429 timeout on known artist '{ka_key}' — skipping, continuing...")
            except Exception as e:
                    log.debug(f"  Known artist lookup error for '{ka_key}': {e}")

        after_d = len(self.artists) - before_d
        log.info(f"  D: +{after_d} artists from known artist lookup ({known_found} matched)")

    # ------------------------------------------------------------------
    # STEP 0b: Spotify Track Collection (v13.0 — replaces YTMusic tracks)
    # ------------------------------------------------------------------
    def collect_tracks_from_spotify(self, ckpt=None, resume=False, max_tracks=None,
                                     reuse_client=False, max_pages=None):
        """Collect tracks for each discovered artist via Spotify search.

        Since artist_albums() and artist_top_tracks() are dead (404 since March 2026),
        we use sp.search(q='artist:"name"', type='track', market='VN') and verify
        artist_id in track.artists to ensure correctness.

        Rate limiting handled by SpotifyRateLimiter wrapper.
        Checkpoints every 50 artists for resume capability.
        """
        if reuse_client and hasattr(self, '_spotify_client_ref') and self._spotify_client_ref:
            sp = self._spotify_client_ref
            log.info("  Reusing Spotify client from discovery phase")
        else:
            sp = self._create_spotify_client()
        if not sp:
            log.warning("  Spotify not available for track collection!")
            return

        log.info(f"\n{'='*70}")
        log.info(f"  Step 1: Spotify Track Collection (v13.0)")
        log.info(f"{'='*70}")

        if resume and ckpt:
            saved_tracks = ckpt.load_tracks()
            if saved_tracks:
                self.tracks.update(saved_tracks)
                log.info(f"  Resumed {len(self.tracks)} tracks from checkpoint")

        # Collect artists with spotify_id
        artists_with_sid = [
            (k, v) for k, v in self.artists.items()
            if v.get("spotify_id")
        ]
        log.info(f"  Collecting tracks for {len(artists_with_sid)} artists with Spotify ID")

        before = len(self.tracks)
        checkpoint_counter = 0
        max_pages_per_artist = max_pages or 20  # 20 pages × 10 = 200 tracks per artist

        try:
            for key, info in tqdm(artists_with_sid, desc="Spotify track collection"):
                artist_name = info["name"]
                artist_sid = info["spotify_id"]

                try:
                    # Fill missing artist image from first track's album art
                    # (avoid sp.artist() call — saves 1 API call per artist)
                    fill_image = not info.get("image_url")

                    for page in range(max_pages_per_artist):
                        offset = page * 10
                        results = sp.search(
                            q=f'artist:"{artist_name}"',
                            type="track", market="VN",
                            limit=10, offset=offset,
                        )

                        items = results.get("tracks", {}).get("items", [])
                        if not items:
                            break

                        found_any = False
                        for track in items:
                            # Verify the correct artist is in this track
                            track_artist_ids = {a.get("id") for a in (track.get("artists") or [])}
                            if artist_sid not in track_artist_ids:
                                continue

                            spotify_track_id = track.get("id")
                            if not spotify_track_id:
                                continue
                            if spotify_track_id in self.tracks:
                                continue
                            if spotify_track_id in self.existing_track_ids:
                                continue  # already processed in a previous pipeline run

                            found_any = True

                            # Fill artist image from first matching track's album art
                            if fill_image:
                                album_imgs = (track.get("album") or {}).get("images") or []
                                if album_imgs:
                                    info["image_url"] = album_imgs[0]["url"]
                                    fill_image = False

                            # Build track dict compatible with filter_vietnamese()
                            track_artists = []
                            for a in (track.get("artists") or []):
                                track_artists.append({
                                    "name": a.get("name", "").strip(),
                                    "id": a.get("id", ""),
                                })

                            album = track.get("album") or {}
                            album_images = album.get("images") or []

                            duration_ms = track.get("duration_ms", 0)

                            self.tracks[spotify_track_id] = {
                                "videoId": spotify_track_id,  # compat key
                                "title": track.get("name", "").strip(),
                                "artists": track_artists,
                                "album": {
                                    "name": (album.get("name") or "").strip(),
                                    "id": album.get("id", ""),
                                    "browseId": album.get("id", ""),
                                    "type": album.get("album_type", ""),
                                    "year": (album.get("release_date") or "")[:4],
                                },
                                "thumbnails": album_images,
                                "duration": None,
                                "duration_seconds": duration_ms // 1000 if duration_ms else None,
                                "isExplicit": track.get("explicit", False),
                                "isAvailable": True,
                                # Spotify-specific metadata
                                "spotify_track_id": spotify_track_id,
                                "spotify_track_url": (track.get("external_urls") or {}).get("spotify", ""),
                                "preview_url": track.get("preview_url"),
                                "track_popularity": track.get("popularity", 0),
                                "release_date": album.get("release_date", ""),
                            }

                        # Stop paginating if no matching tracks on this page
                        if not found_any:
                            break

                except SpotifyRateLimitBan:
                    log.warning(f"  429 timeout for '{artist_name}' — skipping to next artist")
                except Exception as e:
                    log.debug(f"  Track collection error for '{artist_name}': {e}")

                checkpoint_counter += 1
                if ckpt and checkpoint_counter % 50 == 0:
                    ckpt.save_tracks(self.tracks)
                    log.info(f"  Checkpoint: {len(self.tracks)} tracks saved")

        except Exception as e:
            log.error(f"\n  Unexpected error during track collection: {e}")
            if ckpt:
                ckpt.save_tracks(self.tracks)

        added = len(self.tracks) - before
        log.info(f"  Collected +{added} tracks (total: {len(self.tracks)})")
        if hasattr(sp, 'total_calls'):
            log.info(f"  Spotify API calls: {sp.total_calls}")

        if ckpt:
            ckpt.save_tracks(self.tracks)

    # ------------------------------------------------------------------
    # STEP 1: YTMusic Charts + Explore + Search → seed artist pool
    # (v13.0 — kept for reference, no longer called in main pipeline)
    # ------------------------------------------------------------------
    def discover_artists_from_ytmusic(self, ckpt=None, resume=False):
        """Primary artist seeding via YTMusic charts, explore, and search.
        No Spotify dependency — 100% ytmusicapi."""
        if not self.yt:
            log.warning("  ytmusicapi not available!")
            return

        log.info(f"\n{'='*70}")
        log.info(f"  Step 1: YTMusic → Artist Discovery (Charts + Explore + Search)")
        log.info(f"{'='*70}")

        if resume and ckpt and ckpt.exists("artists_discovered"):
            saved = ckpt.load("artists_discovered")
            if saved:
                self.artists = saved
                log.info(f"  Resumed {len(self.artists)} artists from checkpoint")
                return

        before = len(self.artists)

        # --- A: Chart artists from YTMusic VN ---
        try:
            charts = self.yt.get_charts(country="VN")
            if "artists" in charts:
                artist_items = charts["artists"]
                if isinstance(artist_items, dict):
                    artist_items = artist_items.get("items", [])
                for item in (artist_items or []):
                    name = item.get("title", item.get("name", "")).strip()
                    browse_id = item.get("browseId")
                    if name and browse_id:
                        key = self._normalize_artist_key(name)
                        if key not in self.artists:
                            if self._is_valid_artist(name):
                                self.artists[key] = {
                                    "name": name,
                                    "yt_channel_id": browse_id,
                                    "discovery": "yt_charts",
                                }
            # Extract artists from chart songs/videos
            for section in ("songs", "videos", "trending"):
                items = charts.get(section)
                if isinstance(items, dict):
                    items = items.get("items", [])
                for item in (items or []):
                    for artist in (item.get("artists") or []):
                        name = artist.get("name", "").strip()
                        aid = artist.get("id")
                        if name:
                            key = self._normalize_artist_key(name)
                            if key not in self.artists:
                                if self._is_valid_artist(name):
                                    self.artists[key] = {
                                        "name": name,
                                        "yt_channel_id": aid,
                                        "discovery": "yt_charts",
                                    }
        except Exception as e:
            log.debug(f"  YT Charts error: {e}")

        chart_count = len(self.artists) - before
        log.info(f"  Charts: +{chart_count} artists")

        # --- B: Explore page (new_videos, moods_and_genres) ---
        try:
            explore = self.yt.get_explore()
            if explore:
                # new_videos: list of dicts with title/artists/videoId
                new_videos = explore.get("new_videos", [])
                if isinstance(new_videos, list):
                    for item in new_videos:
                        for artist in (item.get("artists") or []):
                            name = artist.get("name", "").strip()
                            aid = artist.get("id")
                            if name:
                                key = self._normalize_artist_key(name)
                                if key not in self.artists:
                                    if self._is_valid_artist(name):
                                        self.artists[key] = {
                                            "name": name,
                                            "yt_channel_id": aid,
                                            "discovery": "yt_explore",
                                        }
            self._yt_delay(0.15)
        except Exception as e:
            log.debug(f"  YT Explore error: {e}")

        explore_count = len(self.artists) - before - chart_count
        log.info(f"  Explore: +{explore_count} artists")

        # --- C: Search Vietnamese songs → extract artists ---
        song_queries = [
            # V-Pop / Nhạc trẻ
            "nhạc trẻ hay nhất", "nhạc trẻ hot 2025", "nhạc trẻ hot 2026",
            "vpop hot 2025", "vpop hot 2026", "vpop hot 2024",
            "nhạc Việt trending", "nhạc Việt mới nhất",
            # Ballad
            "ballad Việt hay", "ballad Việt 2025",
            # Rap / Hip-hop
            "rap Việt hay nhất", "rap Việt hot 2025", "rap Việt hot 2026",
            "hip hop Việt", "rap Việt underground",
            # R&B / Pop / Genres
            "R&B Việt hay", "R&B Việt hot",
            "pop Việt hay nhất", "pop Việt trending",
            "indie Việt hay", "nhạc chill Việt",
            "underground Việt", "EDM Việt",
            "acoustic Việt hay",
            # Nhạc đỏ / Cách mạng
            "nhạc cách mạng hay", "nhạc đỏ bất hủ",
            # Nhạc phim / OST
            "nhạc phim Việt Nam hay", "nhạc phim Việt",
            # Anh Trai / Game shows
            "Anh Trai Say Hi", "Anh Trai Vượt Ngàn Chông Gai",
            "Rap Việt mùa 4",
            # GenZ / Trending
            "nhạc TikTok Việt hay", "nhạc TikTok 2025",
            "nhạc trending TikTok Việt", "nhạc hot GenZ",
            "lo-fi Việt hay", "lo-fi chill Việt",
            "drill Việt", "trap Việt hay",
            "nhạc Việt viral", "vpop trending 2025",
            # Nhạc Việt theo năm
            "nhạc Việt 2023 hay", "nhạc Việt 2024 hay",
            "nhạc Việt 2025 hay", "vpop hay nhất 2023",
        ]

        for query in tqdm(song_queries, desc="YTMusic song search → artists"):
            try:
                results = self.yt.search(query, filter="songs", limit=50)
                for r in (results or []):
                    for artist in (r.get("artists") or []):
                        name = artist.get("name", "").strip()
                        aid = artist.get("id")
                        if not name:
                            continue
                        key = self._normalize_artist_key(name)
                        if key not in self.artists:
                            if self._is_valid_artist(name):
                                self.artists[key] = {
                                    "name": name,
                                    "yt_channel_id": aid,
                                    "discovery": "ytmusic_search",
                                }
                self._yt_delay(0.1)
            except Exception as e:
                log.debug(f"  YTMusic search error for '{query}': {e}")

        # --- D: Search for artist profiles directly ---
        artist_queries = [
            "vpop", "nhạc trẻ việt nam", "rap việt",
            "nhạc việt", "underground việt", "R&B việt",
            "pop việt", "indie việt", "EDM việt",
            "ca sĩ việt nam", "nghệ sĩ việt", "nhạc sĩ việt nam",
            "hot vpop artist", "vietnamese singer",
            "rapper việt nam", "ca sĩ GenZ việt",
            "TikTok singer vietnam", "vpop idol",
        ]

        for query in tqdm(artist_queries, desc="YTMusic artist search"):
            try:
                results = self.yt.search(query, filter="artists", limit=50)
                for r in (results or []):
                    name = r.get("artist", r.get("title", "")).strip()
                    browse_id = r.get("browseId")
                    if not name or not browse_id:
                        continue
                    key = self._normalize_artist_key(name)
                    if key not in self.artists:
                        if self._is_valid_artist(name):
                            self.artists[key] = {
                                "name": name,
                                "yt_channel_id": browse_id,
                                "discovery": "ytmusic_search",
                            }
                self._yt_delay(0.1)
            except Exception as e:
                log.debug(f"  YTMusic artist search error for '{query}': {e}")

        # NOTE: Mood category playlist scanning happens in Step 4
        # (discover_from_yt_charts → _discover_from_ytmusic_moods)
        # which discovers both tracks AND artists — no need to duplicate here.

        added = len(self.artists) - before
        log.info(f"  YTMusic discovery: +{added} artists seeded (total: {len(self.artists)})")
        if ckpt:
            ckpt.save("artists_discovered", self.artists)

    # ------------------------------------------------------------------
    # STEP 2: Resolve artists on YTMusic + discover related artists (PARALLEL)
    # ------------------------------------------------------------------
    def _resolve_one_artist(self, yt_instance, key, info):
        """Worker: resolve one artist, return (key, updates_dict, related_list).
        Name matching: exact → normalized → diacritics-stripped → substring/prefix → first result."""
        updates = {}
        related = []
        try:
            results = yt_instance.search(info["name"], filter="artists", limit=5)
            if not results:
                return (key, updates, related)

            browse_id = None
            target_lower = info["name"].lower().strip()
            target_norm = self._normalize_artist_key(info["name"])
            target_stripped = VietnameseDetector._strip_vn_diacritics(info["name"])

            # Pass 1: exact or normalized match
            for r in results:
                r_name = r.get("artist", r.get("title", "")).strip()
                r_lower = r_name.lower().strip()
                r_norm = self._normalize_artist_key(r_name)
                if r_lower == target_lower or r_norm == target_norm:
                    browse_id = r.get("browseId")
                    break

            # Pass 1b: diacritics-stripped match (YTMusic often returns ASCII names)
            # e.g. "Hà Anh Tuấn" vs "Ha Anh Tuan", "Hương Tràm" vs "Huong Tram"
            if not browse_id:
                target_nospace = target_stripped.replace(" ", "")
                for r in results:
                    r_name = r.get("artist", r.get("title", "")).strip()
                    r_stripped = VietnameseDetector._strip_vn_diacritics(r_name)
                    # Match with diacritics stripped, also try without spaces
                    # (handles "Chipu" vs "Chi Pu", "16brt" vs "16 BrT")
                    if r_stripped == target_stripped or \
                       r_stripped.replace(" ", "") == target_nospace:
                        browse_id = r.get("browseId")
                        break

            # Pass 2: substring/prefix match (e.g., "Đen Vâu" → "Đen")
            if not browse_id:
                for r in results:
                    r_name = r.get("artist", r.get("title", "")).strip()
                    r_norm = self._normalize_artist_key(r_name)
                    r_stripped = VietnameseDetector._strip_vn_diacritics(r_name)
                    # Accept if one is a prefix of the other (with or without diacritics)
                    if ((r_norm in target_norm or target_norm in r_norm) and len(r_norm) >= 2) or \
                       ((r_stripped in target_stripped or target_stripped in r_stripped) and len(r_stripped) >= 2):
                        browse_id = r.get("browseId")
                        break

            # Pass 3: first result as fallback (only if reasonably similar)
            if not browse_id and results:
                first_name = results[0].get("artist", results[0].get("title", "")).strip()
                first_norm = self._normalize_artist_key(first_name)
                first_stripped = VietnameseDetector._strip_vn_diacritics(first_name)
                if first_norm == target_norm or first_stripped == target_stripped:
                    browse_id = results[0].get("browseId")

            if not browse_id:
                return (key, updates, related)

            updates["yt_channel_id"] = browse_id

            try:
                artist_info = yt_instance.get_artist(browse_id)
                updates["yt_thumbnails"] = artist_info.get("thumbnails", [])
                updates["yt_subscribers"] = artist_info.get("subscribers")
                updates["yt_description"] = (artist_info.get("description") or "")[:200]

                for rel in artist_info.get("related", {}).get("results", []):
                    rel_name = rel.get("title", rel.get("name", "")).strip()
                    rel_browse = rel.get("browseId")
                    if rel_name:
                        related.append((rel_name, rel_browse))
            except Exception as e:
                log.debug(f"  get_artist error for {info['name']}: {e}")

        except Exception as e:
            log.debug(f"  YTMusic search error for {info['name']}: {e}")

        return (key, updates, related)

    def resolve_artists_on_ytmusic(self, ckpt=None, resume=False):
        """Search YTMusic for each artist → get channelId + related artists.
        Uses parallel workers for speed."""
        if not self.yt:
            log.warning("  ytmusicapi not available!")
            return

        log.info(f"\n{'='*70}")
        log.info(f"  Step 2: YTMusic Artist Resolution ({self.PARALLEL_WORKERS} workers)")
        log.info(f"{'='*70}")

        completed = set()
        if resume and ckpt and ckpt.exists("ytmusic_resolution_done"):
            saved = ckpt.load("ytmusic_resolution_done")
            if saved:
                completed = set(saved)

        new_related = {}
        to_process = [(k, v) for k, v in self.artists.items() if k not in completed]
        log.info(f"  Processing {len(to_process)} artists ({len(completed)} already done)")

        # Create worker pool
        yt_pool = []
        for _ in range(self.PARALLEL_WORKERS):
            try:
                yt_pool.append(self._create_yt_instance())
            except Exception:
                pass
        if not yt_pool:
            log.warning("  Failed to create YTMusic worker instances!")
            return

        with ThreadPoolExecutor(max_workers=len(yt_pool)) as executor:
            futures = {}
            for idx, (key, info) in enumerate(to_process):
                yt_inst = yt_pool[idx % len(yt_pool)]
                fut = executor.submit(self._resolve_one_artist, yt_inst, key, info)
                futures[fut] = key

            pbar = tqdm(total=len(futures), desc="YTMusic resolution")
            done_count = 0
            for future in as_completed(futures):
                try:
                    key, updates, related_list = future.result()
                    if updates:
                        self.artists[key].update(updates)
                    for rel_name, rel_browse in related_list:
                        rel_key = self._normalize_artist_key(rel_name)
                        if rel_key not in self.artists and rel_key not in new_related:
                            is_vn, _ = VietnameseDetector.is_vietnamese(
                                rel_name, [rel_name], ""
                            )
                            if is_vn:
                                new_related[rel_key] = {
                                    "name": rel_name,
                                    "yt_channel_id": rel_browse,
                                    "discovery": "ytmusic_related",
                                }
                    completed.add(key)
                except Exception as e:
                    log.debug(f"  Worker error: {e}")

                pbar.update(1)
                done_count += 1

                if ckpt and done_count % 100 == 0:
                    ckpt.save("ytmusic_resolution_done", list(completed))
                    ckpt.save("artists_discovered", self.artists)
            pbar.close()

        # Merge related artists
        self.artists.update(new_related)
        if ckpt:
            ckpt.save("ytmusic_resolution_done", list(completed))
            ckpt.save("artists_discovered", self.artists)

        resolved = sum(1 for a in self.artists.values() if a.get("yt_channel_id"))
        log.info(f"  Resolved {resolved}/{len(self.artists)} artists on YTMusic")
        log.info(f"  Discovered {len(new_related)} related Vietnamese artists")

    # ------------------------------------------------------------------
    # STEP 2.5: YTMusic song-related → discover similar artists (PARALLEL)
    # ------------------------------------------------------------------
    def _watch_playlist_worker(self, yt_instance, vid):
        """Worker: get watch playlist for a video, return found artists."""
        found = []
        try:
            watch = yt_instance.get_watch_playlist(vid)
            if watch:
                for track in (watch.get("tracks") or []):
                    for artist in (track.get("artists") or []):
                        name = artist.get("name", "").strip()
                        browse_id = artist.get("id")
                        if name:
                            found.append((name, browse_id))
        except Exception as e:
            log.debug(f"  Song-related error for {vid}: {e}")
        return found

    def discover_via_song_related(self, ckpt=None, max_songs=500):
        """Use get_watch_playlist() to discover similar artists from YTMusic.
        Samples tracks from already-collected songs to find new artists.
        Uses parallel workers."""
        if not self.yt:
            log.warning("  ytmusicapi not available!")
            return

        log.info(f"\n{'='*70}")
        log.info(f"  Step 2.5: YTMusic Song-Related Discovery ({self.PARALLEL_WORKERS} workers)")
        log.info(f"{'='*70}")

        before = len(self.artists)

        # Sample one song per artist using parallel search
        sample_tracks = []
        yt_pool = []
        for _ in range(self.PARALLEL_WORKERS):
            try:
                yt_pool.append(self._create_yt_instance())
            except Exception:
                pass

        # Collect sample videoIds (sequential — lightweight)
        for key, info in self.artists.items():
            if len(sample_tracks) >= max_songs:
                break
            try:
                results = self.yt.search(info["name"], filter="songs", limit=1)
                if results:
                    vid = results[0].get("videoId")
                    if vid:
                        sample_tracks.append(vid)
            except Exception:
                pass
            if len(sample_tracks) >= max_songs:
                break

        log.info(f"  Sampling {len(sample_tracks)} songs for related discovery")

        # Parallel watch playlist processing
        with ThreadPoolExecutor(max_workers=len(yt_pool)) as executor:
            futures = {}
            for idx, vid in enumerate(sample_tracks):
                yt_inst = yt_pool[idx % len(yt_pool)]
                futures[executor.submit(self._watch_playlist_worker, yt_inst, vid)] = vid

            pbar = tqdm(total=len(futures), desc="Song-related")
            for future in as_completed(futures):
                try:
                    found_artists = future.result()
                    for name, browse_id in found_artists:
                        key = self._normalize_artist_key(name)
                        if key not in self.artists:
                            is_vn, _ = VietnameseDetector.is_vietnamese(
                                name, [name], ""
                            )
                            if is_vn:
                                self.artists[key] = {
                                    "name": name,
                                    "yt_channel_id": browse_id,
                                    "discovery": "ytmusic_song_related",
                                }
                except Exception:
                    pass
                pbar.update(1)
            pbar.close()

        added = len(self.artists) - before
        log.info(f"  Song-related: +{added} new artists (total: {len(self.artists)})")
        if ckpt:
            ckpt.save("artists_discovered", self.artists)

    # ------------------------------------------------------------------
    # STEP 3: Collect ALL tracks via YTMusic (PARALLEL)
    # ------------------------------------------------------------------
    # Pattern to detect live/concert albums — skip during collection
    _LIVE_ALBUM_SKIP_RE = re.compile(
        r'\b(?:live|concert|liveshow|live show|session|sessions|dạ khúc)\b',
        re.IGNORECASE,
    )
    _LIVE_ALBUM_KEEP_RE = re.compile(
        r'\bALIVE\b|\bTouliver\b|\bProd\.?\b',
        re.IGNORECASE,
    )

    @classmethod
    def _is_live_album_name(cls, name: str) -> bool:
        if not name:
            return False
        if cls._LIVE_ALBUM_KEEP_RE.search(name):
            return False
        return bool(cls._LIVE_ALBUM_SKIP_RE.search(name))

    def _collect_artist_tracks(self, yt_instance, channel_id, artist_name):
        """Worker: collect all tracks for one artist. Returns list of (track, artist_name)."""
        collected = []
        albums_seen = set()
        seen_vids = set()  # dedup videoIds within this artist

        try:
            artist_info = yt_instance.get_artist(channel_id)

            # --- Collect from songs list ---
            songs_data = artist_info.get("songs", {})
            songs_browse = songs_data.get("browseId")
            got_full_songs = False

            # Prefer full songs list (has duration_seconds) over initial results
            if songs_browse:
                try:
                    full_songs = yt_instance.get_playlist(songs_browse, limit=None)
                    if full_songs and full_songs.get("tracks"):
                        for song in full_songs["tracks"]:
                            vid = song.get("videoId")
                            if vid and vid not in seen_vids:
                                seen_vids.add(vid)
                                collected.append((song, artist_name))
                        got_full_songs = True
                except Exception:
                    pass

            # Fallback: use initial results only if full list wasn't available
            if not got_full_songs and songs_data.get("results"):
                for song in songs_data["results"]:
                    vid = song.get("videoId")
                    if vid and vid not in seen_vids:
                        seen_vids.add(vid)
                        collected.append((song, artist_name))

            # --- Collect from albums + singles ---
            for album_type in ["albums", "singles"]:
                albums_data = artist_info.get(album_type, {})
                album_list = albums_data.get("results", [])

                # Get full album list
                album_browse = albums_data.get("browseId")
                album_params = albums_data.get("params")
                if album_browse and album_params:
                    try:
                        full_albums = yt_instance.get_artist_albums(
                            album_browse, album_params, limit=None
                        )
                        if full_albums:
                            album_list = full_albums
                    except Exception:
                        pass

                for album in album_list:
                    album_browse_id = album.get("browseId")
                    if not album_browse_id:
                        continue
                    # Thread-safe album dedup
                    with self._lock:
                        if album_browse_id in self.visited_yt_albums:
                            continue
                        self.visited_yt_albums.add(album_browse_id)
                    if album_browse_id in albums_seen:
                        continue
                    albums_seen.add(album_browse_id)

                    try:
                        album_data = yt_instance.get_album(album_browse_id)
                        if album_data and album_data.get("tracks"):
                            album_title = album_data.get("title", "")
                            # Skip live/concert albums
                            if self._is_live_album_name(album_title):
                                log.debug(f"  Skipping live album: {album_title}")
                                continue
                            album_meta = {
                                "name": album_title,
                                "browseId": album_browse_id,
                                "year": album_data.get("year"),
                                "type": album_data.get("type", album_type.rstrip("s")),
                                "thumbnails": album_data.get("thumbnails", []),
                                "trackCount": album_data.get("trackCount"),
                            }
                            for track in album_data["tracks"]:
                                vid = track.get("videoId")
                                if vid and vid not in seen_vids:
                                    seen_vids.add(vid)
                                    track["_album_info"] = album_meta
                                    collected.append((track, artist_name))
                    except Exception as e:
                        log.debug(f"  get_album error for {album_browse_id}: {e}")

        except Exception as e:
            log.debug(f"  Artist track collection error for {artist_name}: {e}")

        return collected

    def collect_tracks_from_ytmusic(self, ckpt=None, resume=False, max_tracks=None):
        """For each artist with yt_channel_id: get songs, albums → all tracks.
        Uses parallel workers for speed."""
        if not self.yt:
            log.warning("  ytmusicapi not available!")
            return

        log.info(f"\n{'='*70}")
        log.info(f"  Step 3: YTMusic Track Collection ({self.PARALLEL_WORKERS} workers)")
        log.info(f"{'='*70}")

        if resume and ckpt:
            saved_tracks = ckpt.load_tracks()
            if saved_tracks:
                self.tracks.update(saved_tracks)
                log.info(f"  Resumed {len(self.tracks)} tracks from checkpoint")

        artists_with_yt = [(k, v) for k, v in self.artists.items()
                          if v.get("yt_channel_id") and v["yt_channel_id"] not in self.visited_yt_channels]
        log.info(f"  Collecting tracks for {len(artists_with_yt)} artists")

        before = len(self.tracks)
        early_exit = False

        # Create worker YTMusic instances
        yt_pool = []
        for _ in range(self.PARALLEL_WORKERS):
            try:
                yt_pool.append(self._create_yt_instance())
            except Exception:
                pass
        if not yt_pool:
            log.warning("  Failed to create YTMusic worker instances!")
            return

        log.info(f"  Created {len(yt_pool)} parallel YTMusic sessions")
        checkpoint_counter = 0

        def _submit_artist(executor, yt_idx, key, info):
            channel_id = info["yt_channel_id"]
            with self._lock:
                if channel_id in self.visited_yt_channels:
                    return None
                self.visited_yt_channels.add(channel_id)
            yt_inst = yt_pool[yt_idx % len(yt_pool)]
            return executor.submit(self._collect_artist_tracks, yt_inst, channel_id, info["name"])

        with ThreadPoolExecutor(max_workers=len(yt_pool)) as executor:
            futures = {}
            for idx, (key, info) in enumerate(artists_with_yt):
                fut = _submit_artist(executor, idx, key, info)
                if fut:
                    futures[fut] = key

            pbar = tqdm(total=len(futures), desc="YTMusic tracks")
            for future in as_completed(futures):
                try:
                    collected = future.result()
                    for track, artist_name in collected:
                        self._add_ytmusic_track(track, artist_name)
                except Exception as e:
                    log.debug(f"  Worker error: {e}")

                pbar.update(1)
                checkpoint_counter += 1

                # Checkpoint periodically
                if ckpt and checkpoint_counter % 50 == 0:
                    ckpt.save_tracks(self.tracks)

                # Early exit if max_tracks reached
                if max_tracks and len(self.tracks) >= max_tracks * 3:
                    log.info(f"  Early exit: {len(self.tracks)} tracks collected (target: {max_tracks})")
                    early_exit = True
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
            pbar.close()

        added = len(self.tracks) - before
        log.info(f"  Collected +{added} tracks (total: {len(self.tracks)})")
        if ckpt:
            ckpt.save_tracks(self.tracks)

    def _add_ytmusic_track(self, track, primary_artist_name=""):
        """Add a single track from YTMusic data to self.tracks."""
        vid = track.get("videoId")
        if not vid or vid in self.tracks or vid in self.existing_track_ids:
            return False

        # Skip unavailable tracks
        if track.get("isAvailable") is False:
            return False

        # Skip tracks without a title
        title = (track.get("title") or "").strip()
        if not title:
            return False

        artists = track.get("artists") or []
        if not artists and primary_artist_name:
            artists = [{"name": primary_artist_name, "id": None}]

        # Clean artist names: strip " - Topic" suffix, filter garbage names
        # Known artists bypass garbage filter
        cleaned_artists = []
        for a in artists:
            name = (a.get("name") or "").strip()
            name = re.sub(r'\s*-\s*Topic$', '', name).strip()
            if not name:
                continue
            if VietnameseDetector.is_garbage_name(name):
                # Keep if it's a known Vietnamese artist
                if not VietnameseDetector.is_known_artist([name]):
                    continue
            cleaned_artists.append({**a, "name": name})

        if not cleaned_artists:
            return False

        album_info = track.get("_album_info", {})
        album_from_track = track.get("album") or {}
        if isinstance(album_from_track, str):
            album_from_track = {"name": album_from_track}

        # Merge album info: prefer _album_info (from get_album), fallback to inline
        album = album_info if album_info else album_from_track

        self.tracks[vid] = {
            "videoId": vid,
            "title": title,
            "artists": cleaned_artists,
            "album": album,
            "thumbnails": track.get("thumbnails") or album.get("thumbnails", []),
            "duration": track.get("duration"),
            "duration_seconds": track.get("duration_seconds"),
            "isExplicit": track.get("isExplicit", False),
            "isAvailable": track.get("isAvailable", True),
            "trackNumber": track.get("trackNumber"),
        }
        return True

    # ------------------------------------------------------------------
    # STEP 4: YTMusic Charts Vietnam + mood playlists
    # ------------------------------------------------------------------
    def discover_from_yt_charts(self, ckpt=None):
        """Get trending Vietnamese tracks from YouTube Music Charts."""
        if not self.yt:
            log.warning("  ytmusicapi not available, skipping YT Charts")
            return

        log.info(f"\n{'='*70}")
        log.info(f"  Step 4: YouTube Music Charts (Vietnam)")
        log.info(f"{'='*70}")

        before = len(self.tracks)

        try:
            charts = self.yt.get_charts(country="VN")
        except Exception as e:
            log.warning(f"  YT Charts API error: {e}")
            return

        # VN Charts structure: videos=[{title, playlistId}], artists=[...]
        # Fetch tracks from chart video playlists
        if "videos" in charts:
            video_items = charts["videos"]
            if isinstance(video_items, list):
                for item in video_items:
                    pl_id = item.get("playlistId")
                    if pl_id:
                        try:
                            pl_data = self.yt.get_playlist(pl_id, limit=None)
                            if pl_data and pl_data.get("tracks"):
                                for track in pl_data["tracks"]:
                                    self._add_ytmusic_track(track)
                            self._yt_delay(0.15)
                        except Exception as e:
                            log.debug(f"  Chart playlist error: {e}")
                    elif item.get("videoId"):
                        self._add_ytmusic_track(item)
            elif isinstance(video_items, dict) and video_items.get("items"):
                for item in video_items["items"]:
                    self._add_ytmusic_track(item)

        # songs/trending sections (available for some countries, not VN)
        for section_name in ("songs", "trending"):
            section = charts.get(section_name)
            if not section:
                continue
            items = section.get("items", []) if isinstance(section, dict) else section
            for item in (items or []):
                self._add_ytmusic_track(item)

        # Chart artists → add to artist pool
        if "artists" in charts:
            artist_items = charts["artists"]
            if isinstance(artist_items, dict):
                artist_items = artist_items.get("items", [])
            for artist_item in (artist_items or [])[:30]:
                name = artist_item.get("title", artist_item.get("name", ""))
                browse_id = artist_item.get("browseId")
                if name:
                    key = self._normalize_artist_key(name)
                    if key not in self.artists:
                        if self._is_valid_artist(name):
                            self.artists[key] = {
                                "name": name,
                                "yt_channel_id": browse_id,
                                "discovery": "yt_charts",
                            }

        added = len(self.tracks) - before
        log.info(f"  YT Charts: +{added} tracks (total: {len(self.tracks)})")

        # YTMusic mood/genre playlists for broader coverage
        self._discover_from_ytmusic_moods()

    def _discover_from_ytmusic_moods(self):
        """Discover tracks from YTMusic mood/genre playlists.
        Uses get_mood_categories() API + search-based playlists.
        NOTE: v13.0 — This method is kept for reference but no longer called in run_pipeline."""
        if not self.yt:
            return

        log.info(f"  Discovering tracks from YTMusic mood/genre playlists...")
        before_tracks = len(self.tracks)
        before_artists = len(self.artists)

        # === Part A: Official Mood Categories API ===
        try:
            mood_cats = self.yt.get_mood_categories()
            if mood_cats:
                log.info(f"  Found {len(mood_cats)} mood/genre categories")
                for category_group, playlists in mood_cats.items():
                    for pl_info in (playlists or []):
                        params = pl_info.get("params")
                        if not params:
                            continue
                        try:
                            mood_playlists = self.yt.get_mood_playlists(params)
                            for pl in (mood_playlists or []):
                                pl_id = pl.get("playlistId")
                                if not pl_id:
                                    continue
                                try:
                                    pl_data = self.yt.get_playlist(pl_id, limit=None)
                                    if pl_data and pl_data.get("tracks"):
                                        for track in pl_data["tracks"]:
                                            self._add_ytmusic_track(track)
                                            # Also discover artists — Vietnamese only
                                            for artist in (track.get("artists") or []):
                                                name = artist.get("name", "").strip()
                                                if name:
                                                    key = self._normalize_artist_key(name)
                                                    if key not in self.artists:
                                                        if self._is_valid_artist(name):
                                                            self.artists[key] = {
                                                                "name": name,
                                                                "yt_channel_id": artist.get("id"),
                                                                "discovery": "ytmusic_mood",
                                                            }
                                    self._yt_delay(0.15)
                                except Exception as e:
                                    log.debug(f"  Mood playlist {pl_id} error: {e}")
                            self._yt_delay(0.1)
                        except Exception as e:
                            log.debug(f"  get_mood_playlists error: {e}")
        except Exception as e:
            log.debug(f"  get_mood_categories error: {e}")

        # === Part B: Vietnamese search-based playlists ===
        vn_playlist_queries = [
            "nhạc trẻ hay nhất", "nhạc trẻ hot 2025", "nhạc trẻ hot 2026",
            "vpop hot", "vpop hay nhất", "vpop playlist",
            "rap Việt hay nhất", "rap Việt hot",
            "ballad Việt hay", "R&B Việt hay",
            "nhạc chill Việt", "acoustic Việt hay",
            "indie Việt hay", "pop Việt hot",
            "underground Việt", "EDM Việt",
            "nhạc Việt mới 2025", "nhạc Việt mới 2026",
            "nhạc TikTok Việt", "nhạc trending GenZ Việt",
            "lo-fi Việt playlist", "vpop 2024 playlist",
        ]

        for query in vn_playlist_queries:
            try:
                results = self.yt.search(query, filter="playlists", limit=20)
                for item in (results or []):
                    browse_id = item.get("browseId")
                    if not browse_id:
                        continue
                    try:
                        pl_data = self.yt.get_playlist(browse_id, limit=None)
                        if pl_data and pl_data.get("tracks"):
                            for track in pl_data["tracks"]:
                                self._add_ytmusic_track(track)
                        self._yt_delay(0.15)
                    except Exception as e:
                        log.debug(f"  YTMusic playlist {browse_id} error: {e}")
                self._yt_delay(0.1)
            except Exception as e:
                log.debug(f"  YTMusic playlist search '{query}' error: {e}")

        added_tracks = len(self.tracks) - before_tracks
        added_artists = len(self.artists) - before_artists
        log.info(f"  YTMusic mood playlists: +{added_tracks} tracks, +{added_artists} artists (total: {len(self.tracks)} tracks)")

    # ------------------------------------------------------------------
    # STEP 5: Discover featured artists from track credits
    # ------------------------------------------------------------------
    def discover_featured_artists(self, ckpt=None):
        """Find new Vietnamese artists from track credits.
        Skips compound names, non-artist channels, foreign blocked, no-ID."""
        log.info(f"\n{'='*70}")
        log.info(f"  Step 5: Discovering featured Vietnamese artists")
        log.info(f"{'='*70}")

        candidate_artists = {}
        compound_re = re.compile(r',\s+|\s+and\s+|\s+&\s+', re.IGNORECASE)

        for vid, track in self.tracks.items():
            for artist in track.get("artists", []):
                name = artist.get("name", "").strip()
                aid = artist.get("id")
                if not name or not aid:
                    continue
                # Skip compound names
                if compound_re.search(name):
                    continue
                # Skip non-artist channels
                if VietnameseDetector.is_non_artist_channel(name):
                    continue
                key = self._normalize_artist_key(name)
                if key not in self.artists and key not in candidate_artists:
                    if self._is_valid_artist(name):
                        candidate_artists[key] = {
                            "name": name,
                            "yt_channel_id": aid,
                            "discovery": "featured",
                        }

        log.info(f"  Found {len(candidate_artists)} new Vietnamese featured artists")
        self.artists.update(candidate_artists)
        if ckpt:
            ckpt.save("artists_discovered", self.artists)

        return list(candidate_artists.keys())

    # ------------------------------------------------------------------
    # FILTER & EXPORT
    # ------------------------------------------------------------------
    def filter_vietnamese(self):
        """Filter only Vietnamese tracks + data quality checks.
        v7.2: filters non-artist channels, children's music, foreign artists,
            old-genre artists, garbage tracks, remix variant dedup,
            tracks with no artist ID, deduplicates by (title, primary_artist),
            release year filter, duration cap, spam artist detection."""
        log.info(f"\n{'='*70}")
        log.info(f"  Filtering Vietnamese tracks from {len(self.tracks)} total")
        log.info(f"{'='*70}")

        vn_tracks = {}
        reasons = defaultdict(int)
        skipped = defaultdict(int)
        seen_title_artist = set()  # for deduplication
        seen_base_song_artist = defaultdict(int)  # remix variant dedup

        for vid, track in tqdm(self.tracks.items(), desc="Filtering"):
            # Data quality: skip tracks without title
            title = track.get("title", "").strip()
            if not title:
                skipped["no_title"] += 1
                continue

            # Data quality: skip tracks without artists
            artists_list = track.get("artists", [])
            if not artists_list:
                skipped["no_artists"] += 1
                continue

            # Data quality: primary artist must have a channelId (no orphan tracks)
            primary_artist = artists_list[0] if artists_list else {}
            primary_id = primary_artist.get("id")
            if not primary_id:
                skipped["no_artist_id"] += 1
                continue

            # Data quality: skip extreme durations
            dur_s = track.get("duration_seconds")
            if dur_s is None and track.get("duration"):
                parts = str(track["duration"]).split(":")
                try:
                    if len(parts) == 2:
                        dur_s = int(parts[0]) * 60 + int(parts[1])
                    elif len(parts) == 3:
                        dur_s = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                except ValueError:
                    pass
            if dur_s is not None:
                if dur_s < 10:
                    skipped["too_short"] += 1
                    continue
                if dur_s > 600:
                    skipped["too_long_10min"] += 1
                    continue

            # Data quality: skip tracks released before 2009
            release_date = track.get("release_date", "")
            if release_date and len(release_date) >= 4:
                try:
                    year = int(release_date[:4])
                    if year < 2009:
                        skipped["pre_2009"] += 1
                        continue
                except ValueError:
                    pass

            artist_names = [a.get("name", "") for a in artists_list]
            primary_name = artist_names[0] if artist_names else ""
            album = track.get("album", {})
            album_name = album.get("name", "") if isinstance(album, dict) else str(album)

            # Skip non-artist channels (Remix, Media, TV, Cover, etc.)
            if VietnameseDetector.is_non_artist_channel(primary_name):
                skipped["non_artist_channel"] += 1
                continue

            # Skip old-genre artists (bolero, nhạc vàng, hải ngoại, etc.)
            if VietnameseDetector.is_old_genre_blocked(artist_names):
                skipped["old_genre_blocked"] += 1
                continue

            # Skip garbage tracks (karaoke, beat, instrumental, hòa tấu, parody)
            if VietnameseDetector.is_garbage_track(title):
                skipped["garbage_track"] += 1
                continue

            # Skip children's music
            if VietnameseDetector.is_children_music(title, primary_name, album_name):
                skipped["children_music"] += 1
                continue

            # Exact dedup by (title, primary_artist) — keep first occurrence
            dedup_key = (title.lower().strip(), primary_name.lower().strip())
            if dedup_key in seen_title_artist:
                skipped["duplicate"] += 1
                continue

            # Remix variant dedup: keep max 3 versions of same base song per artist
            base_title = VietnameseDetector.REMIX_VARIANT_RE.sub('', title).strip()
            base_key = (base_title.lower(), primary_name.lower().strip())
            if base_title.lower() != title.lower().strip():
                # This is a remix/variant — cap at 3 per base song
                if seen_base_song_artist[base_key] >= 3:
                    skipped["remix_variant_excess"] += 1
                    continue

            is_vn, reason = VietnameseDetector.is_vietnamese(
                title, artist_names, album_name,
            )
            if is_vn:
                seen_title_artist.add(dedup_key)
                seen_base_song_artist[base_key] += 1
                vn_tracks[vid] = track
                reasons[reason] += 1

        log.info(f"  Filtered: {len(self.tracks)} → {len(vn_tracks)} Vietnamese tracks")
        if skipped:
            for skip_reason, count in sorted(skipped.items(), key=lambda x: -x[1]):
                log.info(f"     ⛔ {skip_reason}: {count}")
        for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
            log.info(f"     ✓ {reason}: {count}")
        return vn_tracks

    def tracks_to_dataframe(self, tracks=None):
        """Convert tracks to DataFrame (v13.0 — Spotify-centric).
        Supports both Spotify and YTMusic track formats for backward compat."""
        if tracks is None:
            tracks = self.tracks

        rows = []
        for vid, track in tracks.items():
            try:
                artists = track.get("artists") or []
                album = track.get("album") or {}
                if isinstance(album, str):
                    album = {"name": album}

                # Best thumbnail: largest available
                thumbnails = track.get("thumbnails") or []
                thumbnail_url = None
                if isinstance(thumbnails, list) and thumbnails:
                    thumb = thumbnails[-1]  # largest
                    thumbnail_url = thumb.get("url") if isinstance(thumb, dict) else thumb

                # Parse duration
                duration_s = track.get("duration_seconds")
                if duration_s is None and track.get("duration"):
                    parts = str(track["duration"]).split(":")
                    try:
                        if len(parts) == 2:
                            duration_s = int(parts[0]) * 60 + int(parts[1])
                        elif len(parts) == 3:
                            duration_s = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                    except ValueError:
                        pass

                primary_artist = artists[0].get("name", "") if artists else ""
                primary_artist_id = artists[0].get("id", "") if artists else ""
                artist_info = self.artists.get(
                    self._normalize_artist_key(primary_artist),
                    {},
                )

                # Determine track URL (Spotify or YTMusic)
                spotify_url = track.get("spotify_track_url", "")
                if spotify_url:
                    track_url = spotify_url
                else:
                    track_url = f"https://music.youtube.com/watch?v={vid}"

                # Release year: prefer explicit "year" field, fall back to release_date prefix
                _year_raw = track.get("year") or track.get("release_date", "")
                _year = str(_year_raw)[:4] if _year_raw else None
                try:
                    _year = str(int(_year)) if _year and _year.isdigit() and int(_year) > 1900 else None
                except (ValueError, TypeError):
                    _year = None

                row = {
                    "track_id": vid,
                    "track_name": track.get("title", ""),
                    "artists": ", ".join(a.get("name", "") for a in artists),
                    "artist_ids": ", ".join(a.get("id", "") for a in artists if a.get("id")),
                    "primary_artist": primary_artist,
                    "primary_artist_id": primary_artist_id,
                    "album_name": album.get("name", "") or None,
                    "album_id": album.get("browseId", album.get("id", "")) or None,
                    "track_duration_ms": (duration_s * 1000) if duration_s else None,
                    "track_explicit": track.get("isExplicit", False),
                    "track_url": track_url,
                    "thumbnail_url": thumbnail_url,
                    # Metadata for year filter (Filter 6g) and popularity filter (8/8c)
                    "year": _year,
                    "release_date": track.get("release_date", "") or None,
                    "track_popularity": track.get("track_popularity") or track.get("popularity") or None,
                    "artist_popularity": artist_info.get("spotify_popularity"),
                    "artist_genres": ", ".join(artist_info.get("spotify_genres") or []),
                }
                rows.append(row)
            except Exception as e:
                log.debug(f"  Error converting track {vid}: {e}")

        df = pd.DataFrame(rows)
        log.info(f"  DataFrame: {len(df)} rows x {len(df.columns)} columns")
        return df

    def artists_to_dataframe(self):
        """Export artist metadata to DataFrame (v14.1 — Spotify + YTMusic).
        Uses Spotify ID or YTMusic channelId as artist_id.
        Filters out compound names, no ID at all, non-artist channels,
        foreign blocked, old-genre blocked."""
        rows = []
        compound_re = re.compile(r',\s+|\s+and\s+|\s+&\s+', re.IGNORECASE)
        skipped_compound = 0
        skipped_no_id = 0
        skipped_channel = 0
        skipped_foreign = 0
        skipped_old_genre = 0
        skipped_foreign_chars = 0

        for key, info in self.artists.items():
            name = info.get("name", key)
            spotify_id = info.get("spotify_id", "")
            yt_channel_id = info.get("yt_channel_id", "")

            # Use Spotify ID if available, otherwise YTMusic channel ID
            artist_id = spotify_id or yt_channel_id
            if not artist_id:
                skipped_no_id += 1
                continue

            # Skip compound artist names (multiple people)
            if compound_re.search(name):
                skipped_compound += 1
                continue

            # Skip non-artist channels
            if VietnameseDetector.is_non_artist_channel(name):
                skipped_channel += 1
                continue

            # Skip foreign blocked artists
            if VietnameseDetector.is_foreign_blocked([name]):
                skipped_foreign += 1
                continue

            # Skip old-genre blocked artists
            if VietnameseDetector.is_old_genre_blocked([name]):
                skipped_old_genre += 1
                continue

            # Skip CJK/foreign character names
            if VietnameseDetector.has_foreign_chars(name):
                skipped_foreign_chars += 1
                continue

            # Thumbnail: Spotify image_url > YTMusic thumbnail
            image_url = info.get("image_url")
            if not image_url:
                yt_thumbs = info.get("yt_thumbnails")
                if yt_thumbs and isinstance(yt_thumbs, list):
                    last = yt_thumbs[-1]
                    image_url = last.get("url") if isinstance(last, dict) else last

            rows.append({
                "artist_id": artist_id,
                "artist_name": name,
                "thumbnail_url": image_url,
                "spotify_popularity": info.get("spotify_popularity"),
                "spotify_followers": info.get("spotify_followers"),
                "spotify_genres": ", ".join(info.get("spotify_genres") or []),
                "discovery_source": info.get("discovery", ""),
            })

        log.debug(f"  Artists export: {len(rows)} kept, skipped: {skipped_no_id} no_id, "
                   f"{skipped_compound} compound, {skipped_channel} channel, "
                   f"{skipped_foreign} foreign, {skipped_old_genre} old_genre, "
                   f"{skipped_foreign_chars} foreign_chars")
        return pd.DataFrame(rows)


# ============================================================================
# LYRICS COLLECTOR v6.0 (YTMusic primary -> YTMusic search -> LRCLIB fallback)
# ============================================================================
class LyricsCollector:
    """
    Lyrics collection with YTMusic as PRIMARY source (synced with MP3 source).
    Tier 1: YTMusic lyrics via existing videoId (direct match).
    Tier 2: YTMusic search → try alternative videoId with lyrics.
    Tier 3: LRCLIB exact/search fallback.
    Parallelized with per-worker YTMusic instances.
    """

    LRCLIB_URL = "https://lrclib.net/api"
    LYRICS_WORKERS = 10  # Parallel worker count

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "BrightifyMusicCollector/9.0",
        })
        self.stats = defaultdict(int)
        self._stats_lock = threading.Lock()
        self._ytmusic = None

    @property
    def ytmusic(self):
        if self._ytmusic is None:
            try:
                from ytmusicapi import YTMusic
                self._ytmusic = YTMusic()
            except Exception:
                self._ytmusic = False
        return self._ytmusic if self._ytmusic is not False else None

    @staticmethod
    def _create_yt_instance():
        """Create independent YTMusic instance for a worker thread."""
        try:
            from ytmusicapi import YTMusic
            yt = YTMusic()
            yt._session.headers.update({"User-Agent": "BrightifyLyricsWorker/9.0"})
            if hasattr(yt, '_session') and hasattr(yt._session, 'timeout'):
                yt._session.timeout = 30
            return yt
        except Exception:
            return None

    def fetch_all(self, df, existing=None, checkpoint_mgr=None,
                  checkpoint_interval=200):
        """Fetch lyrics for all tracks in DataFrame — parallelized."""
        if existing is None:
            existing = {}
        lyrics_dict = dict(existing)
        lyrics_lock = threading.Lock()

        tasks = []
        for _, row in df.iterrows():
            tid = row.get("track_id")
            if not tid or tid in lyrics_dict:
                continue
            if pd.isna(row.get("track_name")):
                continue
            tasks.append({
                "track_id": tid,
                "track_name": str(row["track_name"]),
                "artist_name": self._get_artist(row),
                "album_name": str(row.get("album_name", "")),
                "duration_ms": row.get("track_duration_ms"),
                "ytmusic_video_id": row.get("ytmusic_video_id") if pd.notna(row.get("ytmusic_video_id")) else None,
            })

        log.info(f"\n{'='*70}")
        log.info(f"  Fetching lyrics: {len(tasks)} tracks ({self.LYRICS_WORKERS} workers, skipping {len(existing)} done)")
        log.info(f"{'='*70}")

        # Create per-worker YTMusic instances
        yt_instances = []
        for _ in range(self.LYRICS_WORKERS):
            yt = self._create_yt_instance()
            if yt:
                yt_instances.append(yt)

        if not yt_instances:
            log.warning("  No YTMusic instances created, falling back to sequential")
            yt_instances = [self.ytmusic] if self.ytmusic else []

        checkpoint_count = [0]  # mutable for closure

        pbar = tqdm(total=len(tasks), desc="Lyrics")

        def _lyrics_worker(task, yt_inst):
            """Worker: fetch lyrics for one task with a dedicated YTMusic instance."""
            result = self._fetch_one_threaded(task, yt_inst)
            with lyrics_lock:
                if result:
                    lyrics_dict[task["track_id"]] = result
                else:
                    # Record not-found so resume skips them
                    lyrics_dict[task["track_id"]] = {
                        "has_lyrics": False, "plain_lyrics": None,
                        "synced_lyrics": None, "lyrics_source": None,
                    }
                checkpoint_count[0] += 1
                if checkpoint_mgr and checkpoint_count[0] % checkpoint_interval == 0:
                    checkpoint_mgr.save("lyrics", lyrics_dict)
            pbar.update(1)
            return task["track_id"], result

        with ThreadPoolExecutor(max_workers=len(yt_instances)) as executor:
            futures = []
            for i, task in enumerate(tasks):
                yt_inst = yt_instances[i % len(yt_instances)]
                futures.append(executor.submit(_lyrics_worker, task, yt_inst))
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    log.debug(f"  Lyrics worker error: {e}")

        pbar.close()

        if checkpoint_mgr:
            checkpoint_mgr.save("lyrics", lyrics_dict)

        # ── Retry pass cho track thiếu lyrics ────────────────────────────
        # Lý do fail: YTMusic rate-limit khi fetch song song. Retry tuần tự
        # với delay lớn hơn, tối đa 3 lần.
        LYRICS_MAX_RETRY  = 3
        LYRICS_RETRY_WAIT = 15   # giây chờ trước mỗi pass
        LYRICS_RETRY_DELAY = 1.5 # giây giữa mỗi track trong retry

        tasks_by_id = {t["track_id"]: t for t in tasks}

        for retry_pass in range(1, LYRICS_MAX_RETRY + 1):
            failed_ids = [
                tid for tid, data in lyrics_dict.items()
                if not data.get("has_lyrics") and tid in tasks_by_id
            ]
            if not failed_ids:
                break

            wait_s = LYRICS_RETRY_WAIT * retry_pass
            log.info(f"  🔄 Lyrics retry {retry_pass}/{LYRICS_MAX_RETRY} — "
                     f"{len(failed_ids)} track thiếu lyrics (chờ {wait_s}s...)")
            import time as _t; _t.sleep(wait_s)

            # Dùng fresh YTMusic instance cho retry để tránh session stale
            retry_yt = self._create_yt_instance() or (yt_instances[0] if yt_instances else None)
            if not retry_yt:
                log.warning("  Không tạo được YTMusic instance cho retry — dừng")
                break

            recovered = 0
            for tid in tqdm(failed_ids, desc=f"Lyrics retry {retry_pass}"):
                task = tasks_by_id[tid]
                result = self._fetch_one_threaded(task, retry_yt)
                with lyrics_lock:
                    if result and result.get("has_lyrics"):
                        lyrics_dict[tid] = result
                        recovered += 1
                    # else: giữ nguyên entry has_lyrics=False
                _t.sleep(LYRICS_RETRY_DELAY)

            log.info(f"  Lyrics retry {retry_pass}: recovered {recovered}, "
                     f"still missing {len(failed_ids) - recovered}")
            if checkpoint_mgr:
                checkpoint_mgr.save("lyrics", lyrics_dict)

        still_missing = sum(1 for d in lyrics_dict.values() if not d.get("has_lyrics"))
        if still_missing:
            log.info(f"  ⚠️  {still_missing} track vẫn thiếu lyrics sau {LYRICS_MAX_RETRY} lần retry")
        # ─────────────────────────────────────────────────────────────────

        self._print_stats()
        return lyrics_dict

    def _fetch_one_threaded(self, task, yt_inst):
        """Fetch lyrics with a specific YTMusic instance (thread-safe)."""
        with self._stats_lock:
            self.stats["total"] += 1

        # Tier 1: YTMusic via existing videoId
        result = self._fetch_ytmusic_with_inst(task, yt_inst)
        if result:
            with self._stats_lock:
                self.stats["success"] += 1
                self.stats["ytmusic"] += 1
            return result

        # Tier 2: YTMusic search → find alternative videoId with lyrics
        result = self._fetch_ytmusic_search_with_inst(task, yt_inst)
        if result:
            with self._stats_lock:
                self.stats["success"] += 1
                self.stats["ytmusic_search"] += 1
            return result

        # Tier 3: LRCLIB
        result = self._fetch_lrclib(task)
        if result:
            with self._stats_lock:
                self.stats["success"] += 1
                self.stats["lrclib"] += 1
            return result

        with self._stats_lock:
            self.stats["not_found"] += 1
        return None

    def _fetch_ytmusic_with_inst(self, task, yt_inst):
        """Tier 1: YouTube Music lyrics via existing videoId (thread-safe)."""
        if not yt_inst:
            return None
        video_id = task.get("ytmusic_video_id")
        if not video_id:
            video_id = task.get("track_id")
        if not video_id:
            return None
        return self._extract_ytmusic_lyrics_with_inst(video_id, task["track_name"], yt_inst)

    def _fetch_ytmusic_search_with_inst(self, task, yt_inst):
        """Tier 2: Search YTMusic for alternative videoId with lyrics (thread-safe)."""
        if not yt_inst:
            return None
        try:
            query = f"{task['track_name']} {task['artist_name']}"
            tried_ids = {task.get("ytmusic_video_id"), task.get("track_id")}

            # Try songs filter first (limit=10 for better coverage)
            for search_filter in ("songs", "videos"):
                try:
                    results = yt_inst.search(query, filter=search_filter, limit=10)
                except Exception:
                    continue
                if not results:
                    continue
                for r in results:
                    vid = r.get("videoId")
                    if not vid or vid in tried_ids:
                        continue
                    result_artists = ", ".join(
                        artist.get("name", "")
                        for artist in (r.get("artists") or [])
                        if isinstance(artist, dict)
                    )
                    if not self._search_result_matches(
                        task,
                        r.get("title", ""),
                        result_artists,
                    ):
                        continue
                    tried_ids.add(vid)
                    result = self._extract_ytmusic_lyrics_with_inst(vid, task["track_name"], yt_inst)
                    if result:
                        result["lyrics_source"] = "ytmusic_search"
                        return result
                    time.sleep(Config.YTMUSIC_DELAY)
        except Exception as e:
            log.debug(f"  YTMusic search lyrics error for '{task['track_name']}': {e}")
        return None

    def _extract_ytmusic_lyrics_with_inst(self, video_id, track_name, yt_inst):
        """Extract lyrics using a specific YTMusic instance (thread-safe)."""
        max_retries = 2
        for attempt in range(max_retries):
            try:
                watch = yt_inst.get_watch_playlist(video_id)
                lyrics_browse_id = watch.get("lyrics")
                if not lyrics_browse_id:
                    return None

                synced_lyrics = None
                plain_lyrics = None

                try:
                    timed = yt_inst.get_lyrics(lyrics_browse_id, timestamps=True)
                    if timed and timed.get("lyrics"):
                        if timed.get("hasTimestamps") and isinstance(timed["lyrics"], list):
                            synced_lines = []
                            plain_lines = []
                            for line in timed["lyrics"]:
                                text = getattr(line, 'text', str(line)) if not isinstance(line, str) else line
                                start = getattr(line, 'start_time', None)
                                if start is not None:
                                    mins = int(start / 60000)
                                    secs = (start % 60000) / 1000
                                    synced_lines.append(f"[{mins:02d}:{secs:05.2f}] {text}")
                                plain_lines.append(text if isinstance(text, str) else str(text))
                            synced_lyrics = "\n".join(synced_lines) if synced_lines else None
                            plain_lyrics = "\n".join(plain_lines)
                        else:
                            plain_lyrics = timed["lyrics"] if isinstance(timed["lyrics"], str) else str(timed["lyrics"])
                except Exception:
                    pass

                if not plain_lyrics:
                    try:
                        plain = yt_inst.get_lyrics(lyrics_browse_id, timestamps=False)
                        if plain and plain.get("lyrics"):
                            plain_lyrics = plain["lyrics"]
                    except Exception:
                        pass

                if plain_lyrics:
                    return {
                        "lrclib_id": None,
                        "plain_lyrics": plain_lyrics,
                        "synced_lyrics": synced_lyrics,
                        "instrumental": False,
                        "has_lyrics": True,
                        "lyrics_source": "ytmusic",
                    }
                return None

            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(Config.BACKOFF_BASE * (attempt + 1))
                    continue
                log.debug(f"  YTMusic lyrics error for '{track_name}': {e}")
                return None

    def _fetch_lrclib(self, task):
        """Fallback: LRCLIB exact match + search."""
        try:
            time.sleep(Config.LRCLIB_DELAY)  # rate-limit LRCLIB requests
            duration_sec = int(task["duration_ms"] / 1000) if task.get("duration_ms") else None

            if duration_sec:
                params = {
                    "track_name": task["track_name"],
                    "artist_name": task["artist_name"],
                    "album_name": task.get("album_name", ""),
                    "duration": duration_sec,
                }
                resp = self.session.get(f"{self.LRCLIB_URL}/get", params=params, timeout=10)
                if resp.status_code == 200:
                    result = resp.json()
                    if self._search_result_matches(
                        task,
                        result.get("trackName", ""),
                        result.get("artistName", ""),
                    ):
                        return self._format_lrclib(result)

            params = {
                "track_name": task["track_name"],
                "artist_name": task["artist_name"],
            }
            resp = self.session.get(f"{self.LRCLIB_URL}/search", params=params, timeout=10)
            if resp.status_code == 200:
                results = resp.json()
                for result in results or []:
                    if self._search_result_matches(
                        task,
                        result.get("trackName", ""),
                        result.get("artistName", ""),
                    ):
                        return self._format_lrclib(result)
        except Exception as e:
            log.debug(f"  LRCLIB error for '{task['track_name']}': {e}")
        return None

    @staticmethod
    def _normalize_lyrics_match(value) -> str:
        text = VietnameseDetector._strip_vn_diacritics(str(value or ""))
        text = re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", text)
        text = re.sub(r"\b(?:feat|ft|featuring)\b.*$", " ", text)
        return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())

    @classmethod
    def _search_result_matches(
        cls,
        task: dict,
        result_title: str,
        result_artists: str,
    ) -> bool:
        expected_title = cls._normalize_lyrics_match(task.get("track_name", ""))
        candidate_title = cls._normalize_lyrics_match(result_title)
        if not expected_title or not candidate_title:
            return False
        title_ratio = SequenceMatcher(
            None,
            expected_title,
            candidate_title,
            autojunk=False,
        ).ratio()
        title_match = (
            expected_title == candidate_title
            or title_ratio >= 0.90
        )
        if not title_match:
            return False

        expected_artist = cls._normalize_lyrics_match(task.get("artist_name", ""))
        candidate_artist = cls._normalize_lyrics_match(result_artists)
        if not expected_artist or not candidate_artist:
            return True
        expected_tokens = set(expected_artist.split())
        candidate_tokens = set(candidate_artist.split())
        return bool(expected_tokens & candidate_tokens)

    def _format_lrclib(self, data):
        return {
            "lrclib_id": data.get("id"),
            "plain_lyrics": data.get("plainLyrics"),
            "synced_lyrics": data.get("syncedLyrics"),
            "instrumental": data.get("instrumental", False),
            "has_lyrics": bool(data.get("plainLyrics") or data.get("syncedLyrics")),
            "lyrics_source": "lrclib",
        }

    def _get_artist(self, row):
        artist = row.get("primary_artist") or row.get("artists", "")
        if pd.isna(artist):
            return ""
        return str(artist).split(",")[0].strip()

    def _print_stats(self):
        total = self.stats["total"]
        success = self.stats["success"]
        rate = (success / total * 100) if total else 0
        log.info(f"\n  Lyrics Stats:")
        log.info(f"     Total: {total}")
        log.info(f"     Success: {success} ({rate:.1f}%)")
        log.info(f"       YTMusic (direct): {self.stats.get('ytmusic', 0)}")
        log.info(f"       YTMusic (search): {self.stats.get('ytmusic_search', 0)}")
        log.info(f"       LRCLIB:           {self.stats.get('lrclib', 0)}")
        log.info(f"     Not found: {self.stats['not_found']}")

    @staticmethod
    def merge_lyrics(df, lyrics_dict):
        """Merge lyrics into DataFrame."""
        rows = [{"track_id": tid, **data} for tid, data in lyrics_dict.items()]
        df_lyrics = pd.DataFrame(rows)

        overlap_cols = [c for c in df_lyrics.columns if c in df.columns and c != "track_id"]
        if overlap_cols:
            df = df.drop(columns=overlap_cols, errors="ignore")

        df_merged = df.merge(df_lyrics, on="track_id", how="left")
        df_merged["has_lyrics"] = df_merged["has_lyrics"].fillna(False)
        df_merged["instrumental"] = df_merged["instrumental"].fillna(False)

        log.info(f"  After lyrics merge: {df_merged.shape}")
        log.info(f"     Tracks with lyrics: {df_merged['has_lyrics'].sum()}")
        return df_merged


# ============================================================================
# STATISTICS DASHBOARD
# ============================================================================
def print_statistics(df: pd.DataFrame):
    """In thống kê tổng hợp chi tiết"""
    log.info(f"\n{'='*70}")
    log.info(f"  THỐNG KÊ TỔNG HỢP")
    log.info(f"{'='*70}")

    log.info(f"\n  📁 Dataset shape: {df.shape}")
    log.info(f"  🎵 Total tracks: {len(df)}")
    if len(df) == 0:
        log.info("  No data to report.")
        return
    if "primary_artist" in df.columns:
        log.info(f"  🎤 Unique artists: {df['primary_artist'].nunique()}")
    if "album_id" in df.columns:
        log.info(f"  💿 Unique albums: {df['album_id'].nunique()}")

    # Duration
    if "track_duration_ms" in df.columns:
        dur_min = df["track_duration_ms"].dropna() / 60000
        log.info(f"\n  ⏱️  Duration (minutes):")
        log.info(f"     Mean: {dur_min.mean():.2f}")
        log.info(f"     Median: {dur_min.median():.2f}")

    # Audio features
    audio_cols = ["danceability", "energy", "valence", "acousticness", "tempo"]
    available = [c for c in audio_cols if c in df.columns]
    if available:
        log.info(f"\n  🎶 Audio Features (mean):")
        for col in available:
            log.info(f"     {col}: {df[col].dropna().mean():.3f}")

    # Lyrics
    if "has_lyrics" in df.columns:
        has = df["has_lyrics"].sum()
        log.info(f"\n  📝 Lyrics: {has}/{len(df)} ({has/len(df)*100:.1f}%)")

    # MP3
    music_dir = Config.MUSIC_DIR
    if music_dir.exists():
        mp3_count = len(list(music_dir.glob("*.mp3")))
        total_mb = sum(f.stat().st_size for f in music_dir.glob("*.mp3")) / (1024*1024)
        log.info(f"\n  🎵 MP3 files: {mp3_count} ({total_mb:.1f} MB)")

    # Year distribution
    if "album_release_date" in df.columns:
        df_temp = df.copy()
        df_temp["year"] = pd.to_numeric(df_temp["album_release_date"], errors="coerce")
        if df_temp["year"].notna().any():
            log.info(f"\n  📅 Top years:")
            top_years = df_temp["year"].dropna().astype(int).value_counts().sort_index(ascending=False).head(10)
            for year, count in top_years.items():
                log.info(f"     {year}: {count} tracks")

    # Top artists
    log.info(f"\n  🎤 Top 15 artists:")
    for artist, count in df["primary_artist"].value_counts().head(15).items():
        log.info(f"     {artist}: {count}")

    log.info(f"\n{'='*70}")


# ============================================================================
# RUN PIPELINE v13.0 (Spotify-only: Artists + Tracks from Spotify, YTMusic for lyrics/MP3)
# ============================================================================
def run_pipeline(args):
    """Pipeline v13.0 — Spotify artist discovery + Spotify track collection.
    YTMusic used only for lyrics (Phase 4) and MP3 download (Phase 7)."""
    phase = getattr(args, 'phase', 'all')

    # --output-root: override ALL output directories
    output_root = getattr(args, 'output_root', None)
    if output_root:
        root = Path(output_root)
        Config.CHECKPOINT_DIR = root / "checkpoints"
        Config.DATA_DIR = root / "data"
        Config.LOGS_DIR = root / "logs"
        Config.MUSIC_DIR = root / "music_files"
        Config.LYRICS_BACKUP = root / "data" / "lyrics_backup.json"
        for d in [Config.CHECKPOINT_DIR, Config.DATA_DIR, Config.LOGS_DIR,
                  Config.MUSIC_DIR]:
            d.mkdir(parents=True, exist_ok=True)
        log.info(f"  Output root: {root}")

    ckpt_dir_override = getattr(args, 'checkpoint_dir', None)
    if ckpt_dir_override:
        Config.CHECKPOINT_DIR = Path(ckpt_dir_override)
        Config.CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    data_dir_override = getattr(args, 'data_dir', None)
    if data_dir_override:
        Config.DATA_DIR = Path(data_dir_override)
        Config.DATA_DIR.mkdir(parents=True, exist_ok=True)

    ckpt = CheckpointManager()
    phase = getattr(args, "phase", "all")
    resume = getattr(args, "resume", False)
    max_tracks = getattr(args, "max_tracks", None)
    discovery_depth = getattr(args, "discovery_depth", 1)
    seed_file = getattr(args, "seed_file", None)
    max_pages = getattr(args, "max_pages", None)

    log.info(f"\n{'='*70}")
    log.info(f"  Vietnamese Music Data Collector v14.0 — YTMusic Seed + Spotify Discovery")
    log.info(f"  Seed mode: YTMusic | Discovery mode: Spotify | Lyrics: YTMusic | MP3: yt-dlp")
    log.info(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"  Phase: {phase} | Resume: {resume}")
    if seed_file:
        log.info(f"  Seed file: {seed_file}")
    if max_tracks:
        log.info(f"  Max tracks: {max_tracks}")
    log.info(f"{'='*70}")

    # ================================================================
    # PHASE: Re-filter (apply updated filters on existing raw data)
    # ================================================================
    if phase == "filter":
        log.info(f"\n\n{'='*70}")
        log.info(f"  RE-FILTER: Applying updated filters on existing raw data")
        log.info(f"{'='*70}")

        raw_tracks = ckpt.load("tracks_collected")
        raw_artists = ckpt.load("spotify_artists")
        if not raw_tracks:
            log.error("  No raw tracks found (tracks_collected.json). Run --phase collect first.")
            return
        # Handle wrapped format: {"count": N, "tracks": {...}}
        if isinstance(raw_tracks, dict) and "tracks" in raw_tracks:
            raw_tracks = raw_tracks["tracks"]
        log.info(f"  Loaded {len(raw_tracks)} raw tracks from checkpoint")

        collector = PlaylistDiscoveryCollector()
        collector.tracks = raw_tracks
        if raw_artists:
            collector.artists = raw_artists
            log.info(f"  Loaded {len(raw_artists)} artists from checkpoint")

        vn_tracks = collector.filter_vietnamese()
        df_collect = collector.tracks_to_dataframe(vn_tracks)

        ts = datetime.now().strftime("%Y%m%d")
        ckpt.save_dataframe(f"phase1_spotify_{ts}", df_collect)
        ckpt.save_dataframe("phase1_spotify", df_collect)

        df_artists = collector.artists_to_dataframe()
        ckpt.save_dataframe("phase1_artists", df_artists)

        log.info(f"\n  RE-FILTER COMPLETE: {len(df_collect)} Vietnamese tracks, {len(df_artists)} artists")
        log.info(f"  (was {len(raw_tracks)} raw → {len(df_collect)} filtered)")

        # Continue to lyrics if needed
        if phase == "filter":
            # Print stats and exit
            print_statistics(df_collect)
            return

    # ================================================================
    # PHASE 1: Artist Discovery + Track Collection
    # ================================================================
    df_collect = None
    if phase in ("all", "spotify", "collect"):
        log.info(f"\n\n{'='*70}")
        log.info(f"  PHASE 1: ARTIST DISCOVERY + TRACK COLLECTION")
        log.info(f"{'='*70}")

        collector = PlaylistDiscoveryCollector()
        t_start = time.time()

        try:
            if seed_file:
                # === SEED MODE: load artists from file, use YTMusic ===
                seed_path = Path(seed_file)
                if not seed_path.exists():
                    log.error(f"  Seed file not found: {seed_file}")
                    return
                seed_entries = []
                for line in seed_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    # Support "ArtistName::channelId" format for explicit channel mapping
                    if "::" in line:
                        parts = line.split("::", 1)
                        seed_entries.append((parts[0].strip(), parts[1].strip()))
                    else:
                        seed_entries.append((line, None))
                # Deduplicate seed names (case-insensitive)
                seen_keys = set()
                unique_entries = []
                for name, ch_id in seed_entries:
                    key = collector._normalize_artist_key(name)
                    if key not in seen_keys:
                        seen_keys.add(key)
                        unique_entries.append((name, ch_id))
                seed_names = [e[0] for e in unique_entries]

                log.info(f"  Loaded {len(seed_names)} unique seed artists from {seed_file}")
                for name, ch_id in unique_entries:
                    key = collector._normalize_artist_key(name)
                    collector.artists[key] = {
                        "name": name,
                        "yt_channel_id": ch_id,
                        "discovery": "seed_file",
                    }

                # Step 1: Resolve seed artists on YouTube Music → channelIds
                log.info(f"\n  Resolving seed artists on YouTube Music...")
                yt = collector.yt
                if not yt:
                    log.error("  ytmusicapi not available — cannot proceed")
                    return

                yt_pool = []
                for _ in range(collector.PARALLEL_WORKERS):
                    try:
                        yt_pool.append(collector._create_yt_instance())
                    except Exception:
                        pass
                if not yt_pool:
                    log.error("  Failed to create YTMusic instances")
                    return

                resolved_count = 0
                # Count pre-resolved artists (those with explicit channel IDs from seed file)
                pre_resolved = sum(1 for v in collector.artists.values() if v.get("yt_channel_id"))
                resolved_count += pre_resolved
                if pre_resolved:
                    log.info(f"  {pre_resolved} artists pre-resolved with explicit channel IDs")

                with ThreadPoolExecutor(max_workers=len(yt_pool)) as executor:
                    futures = {}
                    for idx, name in enumerate(seed_names):
                        key = collector._normalize_artist_key(name)
                        info = collector.artists[key]
                        if info.get("yt_channel_id"):
                            continue  # already has channel ID from seed file
                        yt_inst = yt_pool[idx % len(yt_pool)]
                        fut = executor.submit(collector._resolve_one_artist, yt_inst, key, info)
                        futures[fut] = key

                    for future in tqdm(as_completed(futures), total=len(futures), desc="YTMusic artist resolution"):
                        try:
                            key, updates, _related = future.result()
                            if updates:
                                collector.artists[key].update(updates)
                                if updates.get("yt_channel_id"):
                                    resolved_count += 1
                        except Exception as e:
                            log.debug(f"  Resolution error: {e}")

                log.info(f"  Resolved {resolved_count}/{len(seed_names)} seed artists on YTMusic")
                unresolved = [v["name"] for v in collector.artists.values()
                              if not v.get("yt_channel_id")]
                if unresolved:
                    log.warning(f"  Unresolved artists ({len(unresolved)}): {', '.join(unresolved[:20])}")

                # Step 2: Collect tracks from YouTube Music (songs + albums + singles)
                collector.collect_tracks_from_ytmusic(ckpt=ckpt, resume=resume, max_tracks=max_tracks)

                # Step 3: Featured artist discovery loop
                # Discover Vietnamese artists from track credits and collect their tracks
                for depth in range(discovery_depth):
                    new_keys = collector.discover_featured_artists(ckpt=ckpt)
                    if not new_keys:
                        log.info(f"  Discovery depth {depth+1}: no new featured artists found")
                        break
                    # Resolve new artists on YTMusic
                    log.info(f"  Discovery depth {depth+1}: resolving {len(new_keys)} new featured artists...")
                    new_resolved = 0
                    with ThreadPoolExecutor(max_workers=len(yt_pool)) as executor:
                        feat_futures = {}
                        for idx, key in enumerate(new_keys):
                            info = collector.artists[key]
                            if info.get("yt_channel_id"):
                                new_resolved += 1
                                continue  # already resolved from track credits
                            yt_inst = yt_pool[idx % len(yt_pool)]
                            fut = executor.submit(collector._resolve_one_artist, yt_inst, key, info)
                            feat_futures[fut] = key

                        for future in tqdm(as_completed(feat_futures), total=len(feat_futures),
                                           desc=f"Featured artist resolution (depth {depth+1})"):
                            try:
                                key, updates, _ = future.result()
                                if updates:
                                    collector.artists[key].update(updates)
                                    if updates.get("yt_channel_id"):
                                        new_resolved += 1
                            except Exception as e:
                                log.debug(f"  Featured resolution error: {e}")

                    log.info(f"  Discovery depth {depth+1}: resolved {new_resolved}/{len(new_keys)} featured artists")
                    if new_resolved == 0:
                        break
                    # Collect tracks for newly discovered artists
                    collector.collect_tracks_from_ytmusic(ckpt=ckpt, resume=resume, max_tracks=max_tracks)
            else:
                # === DISCOVERY MODE: Spotify-only (v13.0) ===
                # Step 0: Spotify → Vietnamese artist discovery (strategies A/B/D)
                collector.discover_artists_from_spotify(ckpt=ckpt, resume=resume)

                # Step 1: Collect tracks via Spotify search
                # Reuse discovery client to avoid re-auth + wasted test call
                log.info(f"  Cooldown 5s before track collection...")
                time.sleep(5)
                collector.collect_tracks_from_spotify(
                    ckpt=ckpt, resume=resume, max_tracks=max_tracks,
                    reuse_client=True, max_pages=max_pages,
                )

        except (SpotifyRateLimitBan, Exception) as e:
            log.error(f"\n  {'='*60}")
            log.error(f"  COLLECTION ERROR — pipeline continuing with collected data")
            log.error(f"  {e}")
            log.error(f"  {'='*60}")
            # Still process whatever we collected so far
            if not collector.tracks:
                return

        # Step 6: Vietnamese filter
        vn_tracks = collector.filter_vietnamese()

        df_collect = collector.tracks_to_dataframe(vn_tracks)

        elapsed = time.time() - t_start
        log.info(f"\n  Collection took {elapsed/60:.1f} minutes")
        log.info(f"  Total raw tracks: {len(collector.tracks)}")
        log.info(f"  Vietnamese tracks: {len(df_collect)}")
        log.info(f"  Artists: {len(collector.artists)}")
        log.info(f"  API calls: {collector.api_calls}")

        ts = datetime.now().strftime("%Y%m%d")
        ckpt.save_dataframe(f"phase1_spotify_{ts}", df_collect)
        ckpt.save_dataframe("phase1_spotify", df_collect)

        # Export artist CSV with proper metadata and thumbnails
        df_artists = collector.artists_to_dataframe()
        ckpt.save_dataframe("phase1_artists", df_artists)
        log.info(f"  Exported {len(df_artists)} artists to phase1_artists.csv")

        # NOTE: Artist images use Spotify CDN URLs (i.scdn.co) — no download needed.
        # Album art uses Spotify album image URLs — usable directly via HTTPS.

        log.info(f"\n  PHASE 1 COMPLETE: {len(df_collect)} Vietnamese tracks, {len(df_artists)} artists")

    # Load from checkpoint if needed
    if df_collect is None:
        if phase == "lyrics":
            for ckpt_name in ("phase3_downloaded", "phase2_filtered", "phase1_spotify"):
                df_collect = ckpt.load_dataframe(ckpt_name)
                if df_collect is not None:
                    log.info(f"  Lyrics input: {ckpt_name}.csv ({len(df_collect)} tracks)")
                    break
        else:
            df_collect = ckpt.load_dataframe("phase1_spotify")

        if df_collect is None:
            log.error("  No Phase 1 data found. Run --phase collect first.")
            return

    # ================================================================
    # PHASE 4: Lyrics (YTMusic primary -> LRCLIB fallback)
    # ================================================================
    df_lyrics = None
    if phase in ("all", "lyrics"):
        log.info(f"\n\n{'='*70}")
        log.info(f"  PHASE 4: LYRICS (YTMusic primary -> YTMusic search -> LRCLIB fallback)")
        log.info(f"{'='*70}")

        lyrics_collector = LyricsCollector()
        existing_lyrics = ckpt.load("lyrics") or {}

        lyrics_dict = lyrics_collector.fetch_all(
            df_collect,
            existing=existing_lyrics,
            checkpoint_mgr=ckpt,
            checkpoint_interval=200,
        )

        with open(Config.LYRICS_BACKUP, "w", encoding="utf-8") as f:
            json.dump(lyrics_dict, f, ensure_ascii=False, indent=2)

        df_lyrics = LyricsCollector.merge_lyrics(df_collect, lyrics_dict)
        with_lyrics = df_lyrics["has_lyrics"].sum() if "has_lyrics" in df_lyrics.columns else 0
        df_lyrics = df_lyrics.reset_index(drop=True)

        log.info(f"  PHASE 4: {len(df_lyrics)} tracks | with lyrics: {with_lyrics}")

        ts = datetime.now().strftime("%Y%m%d")
        ckpt.save_dataframe(f"phase4_lyrics_{ts}", df_lyrics)
        ckpt.save_dataframe("phase4_lyrics", df_lyrics)

    if df_lyrics is None:
        df_lyrics = ckpt.load_dataframe("phase4_lyrics")
        if df_lyrics is None:
            df_lyrics = df_collect

    # ================================================================
    # PRINT STATISTICS
    # ================================================================
    log.info(f"\n\n{'='*70}")
    log.info(f"  SAVING FINAL DATASET")
    log.info(f"{'='*70}")

    df_final = df_lyrics

    if df_final is None or len(df_final) == 0:
        log.error("  No tracks collected. All Spotify apps may be rate-limited.")
        log.error("  Wait for the ban to expire and re-run.")
        return None

    print_statistics(df_final)

    log.info(f"\n{'='*70}")
    log.info(f"  PIPELINE COLLECTION COMPLETE!")
    log.info(f"  Total: {len(df_final)} tracks (metadata from Spotify)")
    log.info(f"{'='*70}")

    return df_final


def show_status():
    """Show current collection status."""
    ckpt = CheckpointManager()

    print(f"\n{'='*60}")
    print(f"  Collection Status (v12.0 Spotify Artists + YTMusic Tracks)")
    print(f"{'='*60}")

    for name in ["spotify_artists", "tracks_collected", "artists_discovered",
                  "ytmusic_resolution_done",
                  "phase1_spotify", "phase4_lyrics"]:
        if ckpt.exists(name):
            csv_path = ckpt.dir / f"{name}.csv"
            json_path = ckpt.dir / f"{name}.json"
            if csv_path.exists():
                rows = sum(1 for _ in open(csv_path)) - 1
                print(f"  [x] {name}: {rows} rows")
            elif json_path.exists():
                size = json_path.stat().st_size / (1024*1024)
                print(f"  [x] {name}: {size:.1f} MB")
            else:
                print(f"  [x] {name}: exists")
        else:
            print(f"  [ ] {name}: not started")

    if Config.MUSIC_DIR.exists():
        count = len(list(Config.MUSIC_DIR.glob("*.mp3")))
        total_mb = sum(f.stat().st_size for f in Config.MUSIC_DIR.glob("*.mp3")) / (1024*1024)
        print(f"  MP3: {count} files ({total_mb:.1f} MB)")

    final_csv = Config.CHECKPOINT_DIR / "phase1_spotify.csv"
    if final_csv.exists():
        rows = sum(1 for _ in open(final_csv)) - 1
        print(f"  Phase 1 CSV: {rows} tracks")

    print(f"{'='*60}\n")


# ============================================================================
# CLI
# ============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Vietnamese Music Data Collector v13.0 (Spotify Artists + Spotify Tracks — No Limits)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m tools.collect_data                       # Full pipeline
  python -m tools.collect_data --phase collect       # Phase 1: Discover + Collect
  python -m tools.collect_data --phase filter        # Re-filter existing data (no API calls)
  python -m tools.collect_data --phase lyrics        # Lyrics (YTMusic + LRCLIB)
  python -m tools.collect_data --resume              # Resume from checkpoint
  python -m tools.collect_data --status              # Show progress
  python -m tools.collect_data --max-tracks 100      # Limit tracks (test mode)
        """,
    )
    parser.add_argument(
        "--phase",
        choices=["all", "collect", "spotify", "lyrics", "filter"],
        default="all",
        help="Run specific phase (default: all). 'spotify' is alias for 'collect'. "
             "'filter' re-applies filters on existing raw data without re-collecting.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last checkpoint",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current progress",
    )
    parser.add_argument(
        "--max-tracks",
        type=int,
        default=None,
        help="Limit maximum tracks",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Max pages per artist for track collection (default: 20, each page=10 tracks)",
    )
    parser.add_argument(
        "--discovery-depth",
        type=int,
        default=2,
        help="Depth for featured artist discovery (default: 2)",
    )
    parser.add_argument(
        "--output-root",
        type=str,
        default=None,
        help="Root directory for ALL outputs",
    )
    parser.add_argument(
        "--checkpoint-dir",
        type=str,
        default=None,
        help="Custom checkpoint directory",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Custom data output directory",
    )
    parser.add_argument(
        "--seed-file",
        type=str,
        default=None,
        help="Path to seed artists file (one artist per line). "
             "When provided, ONLY these artists are collected (no discovery).",
    )

    args = parser.parse_args()

    if args.status:
        show_status()
        return

    run_pipeline(args)


if __name__ == "__main__":
    main()
