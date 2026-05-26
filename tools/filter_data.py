"""
Brightify – Phase 2: Data Filtering & Deduplication

Reads Phase 1 output (phase1_spotify.csv) and produces a clean, deduplicated
dataset with only Vietnamese tracks that have essential metadata.

Filters applied (in order):
  1. Remove rows missing track_id or track_name
  2. Remove duplicate track_ids (keep highest popularity)
  3. Remove duplicate name+artist combinations (keep highest popularity)
  4. Remove tracks shorter than 30s or longer than 360s (6 minutes)
  5. Verify Vietnamese (re-run VietnameseDetector v2 as safety net)
  6. Remove children's music (nhạc thiếu nhi)
  7. Remove foreign-language dominant tracks (CJK/Korean/Thai > VN chars)
  8. Clear lyrics for tracks without MP3 (consistency gate)
  9. Remove tracks missing essential audio features (post-Phase 5)

Output: checkpoints/phase2_filtered.csv

Usage:
    python -m tools.filter_data                          # default
    python -m tools.filter_data --input path/to/csv      # custom input
    python -m tools.filter_data --report                 # print report only
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

CHECKPOINT_DIR = PROJECT_ROOT / "checkpoints"
LOGS_DIR = PROJECT_ROOT / "logs"
DEFAULT_INPUT = CHECKPOINT_DIR / "phase1_spotify.csv"
DEFAULT_OUTPUT = CHECKPOINT_DIR / "phase2_filtered.csv"
REPORT_PATH = LOGS_DIR / "phase2_filter_report.md"

# Minimum required columns — tracks missing these are dropped
REQUIRED_COLUMNS = ["track_id", "track_name", "primary_artist"]

# Duration bounds (milliseconds)
MIN_DURATION_MS = 30_000    # 30 seconds
MAX_DURATION_MS = 360_000   # 6 minutes


def run_filter(input_path: Path | None = None,
               output_path: Path | None = None,
               report_path: Path | None = None) -> pd.DataFrame:
    """Run all filters and return the cleaned DataFrame."""
    input_path = Path(input_path or DEFAULT_INPUT)
    output_path = Path(output_path or DEFAULT_OUTPUT)
    report_path = Path(report_path or REPORT_PATH)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n{'▓' * 70}")
    print(f"  PHASE 2: DATA FILTERING & DEDUPLICATION")
    print(f"{'▓' * 70}")
    print(f"  Input : {input_path}")
    print(f"  Output: {output_path}")

    if not input_path.exists():
        # Fallback: reconstruct from tracks_collected.json checkpoint
        json_fallback = CHECKPOINT_DIR / "tracks_collected.json"
        if json_fallback.exists():
            print(f"  ⚠️ {input_path.name} not found — reconstructing from tracks_collected.json")
            import json
            with open(json_fallback, "r", encoding="utf-8") as f:
                raw = json.load(f)
            tracks = raw.get("tracks", raw) if isinstance(raw, dict) and "tracks" in raw else raw
            from tools.collect_data import PlaylistDiscoveryCollector
            collector = PlaylistDiscoveryCollector.__new__(PlaylistDiscoveryCollector)
            collector.tracks = tracks
            df_raw = collector.tracks_to_dataframe(tracks)
            df_raw.to_csv(str(input_path), index=False)
            print(f"  ✅ Reconstructed {len(df_raw):,} tracks → {input_path.name}")
        else:
            raise FileNotFoundError(f"Input not found: {input_path} (no JSON fallback either)")

    df = pd.read_csv(str(input_path))
    initial = len(df)
    print(f"  Loaded: {initial:,} tracks")

    report_lines = [
        f"# Brightify Phase 2 – Filter Report",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Input: `{input_path.name}` — **{initial:,}** rows\n",
    ]

    # ── 1. Drop rows missing required columns ────────────────────────────
    before = len(df)
    for col in REQUIRED_COLUMNS:
        if col in df.columns:
            df = df.dropna(subset=[col])
            df = df[df[col].astype(str).str.strip() != ""]
    removed = before - len(df)
    msg = f"[Filter 1] Missing required fields: removed {removed:,} → {len(df):,}"
    print(f"  {msg}")
    report_lines.append(msg)

    # ── 2. Dedup by track_id ─────────────────────────────────────────────
    before = len(df)
    pop_col = "track_popularity" if "track_popularity" in df.columns else "popularity"
    if pop_col in df.columns:
        df = df.sort_values(pop_col, ascending=False)
    df = df.drop_duplicates(subset=["track_id"], keep="first")
    removed = before - len(df)
    msg = f"[Filter 2] Duplicate track_id: removed {removed:,} → {len(df):,}"
    print(f"  {msg}")
    report_lines.append(msg)

    # ── 2b. Normalize artist names (ASCII → diacritics) ──────────────────
    # When YTMusic returns "Ha Anh Tuan" and "Hà Anh Tuấn" for the same
    # artist, this step standardizes all to the diacritics version (the one
    # with the most tracks is chosen as canonical).
    if "primary_artist" in df.columns:
        import unicodedata as _ud_norm

        def _strip_vn(text: str) -> str:
            text = text.replace('Đ', 'D').replace('đ', 'd')
            nfd = _ud_norm.normalize('NFD', text)
            return ''.join(c for c in nfd if _ud_norm.category(c) != 'Mn').lower().strip()

        def _has_vn_diacritics(text: str) -> bool:
            vn = set('àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡ'
                      'ùúụủũưừứựửữỳýỵỷỹđÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄ'
                      'ÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ')
            return bool(vn & set(text))

        # Group all artist name variants by their stripped form
        artist_counts = df['primary_artist'].value_counts()
        stripped_groups: dict[str, list[tuple[str, int]]] = {}
        for name, count in artist_counts.items():
            key = _strip_vn(str(name))
            if key not in stripped_groups:
                stripped_groups[key] = []
            stripped_groups[key].append((str(name), count))

        # Build a mapping: variant → canonical name
        # Priority: (1) version with VN diacritics, (2) most tracks
        name_map: dict[str, str] = {}
        for key, variants in stripped_groups.items():
            if len(variants) <= 1:
                continue
            # Prefer version with diacritics; among those, pick with most tracks
            with_diacritics = [(n, c) for n, c in variants if _has_vn_diacritics(n)]
            if with_diacritics:
                canonical = max(with_diacritics, key=lambda x: x[1])[0]
            else:
                canonical = max(variants, key=lambda x: x[1])[0]
            for name, _ in variants:
                if name != canonical:
                    name_map[name] = canonical

        # --- Pass 2: group by primary_artist_id ---
        # Same artist ID can have different display names (e.g. "RPT MCK" vs "MCK").
        # Pick canonical per ID: prefer diacritics, then most tracks.
        if 'primary_artist_id' in df.columns:
            id_counts: dict[str, list[tuple[str, int]]] = {}
            for aid, sub in df.groupby('primary_artist_id'):
                aid = str(aid).strip()
                if not aid:
                    continue
                for name, cnt in sub['primary_artist'].value_counts().items():
                    id_counts.setdefault(aid, []).append((str(name), int(cnt)))

            for aid, variants in id_counts.items():
                if len(variants) <= 1:
                    continue
                with_d = [(n, c) for n, c in variants if _has_vn_diacritics(n)]
                canonical = max(with_d, key=lambda x: x[1])[0] if with_d else max(variants, key=lambda x: x[1])[0]
                for name, _ in variants:
                    if name != canonical:
                        name_map[name] = canonical

        if name_map:
            # Apply mapping to primary_artist
            df['primary_artist'] = df['primary_artist'].replace(name_map)
            # Also update the artists column (comma-separated list)
            if 'artists' in df.columns:
                def _fix_artists_col(artists_str: str) -> str:
                    parts = [a.strip() for a in str(artists_str).split(',')]
                    return ', '.join(name_map.get(p, p) for p in parts)
                df['artists'] = df['artists'].apply(_fix_artists_col)
            # Update primary_artist_id to match canonical artist
            if 'primary_artist_id' in df.columns:
                # Build canonical_id: for each canonical name, use the most common ID
                canonical_ids: dict[str, str] = {}
                for name in set(name_map.values()):
                    rows = df[df['primary_artist'] == name]
                    if len(rows) > 0:
                        vc = rows['primary_artist_id'].value_counts()
                        if len(vc) > 0:
                            canonical_ids[name] = vc.index[0]
                # Apply: all rows with a canonical name get the canonical ID
                for canon_name, canon_id in canonical_ids.items():
                    mask = df['primary_artist'] == canon_name
                    df.loc[mask, 'primary_artist_id'] = canon_id

            msg = f"[Filter 2b] Artist name normalization: unified {len(name_map):,} variant names"
            print(f"  {msg}")
            report_lines.append(msg)
        else:
            msg = "[Filter 2b] Artist name normalization: no variants found"
            print(f"  {msg}")
            report_lines.append(msg)

    # ── 3. Dedup by name+artist (diacritics-normalized) ────────────────
    before = len(df)
    if "track_name" in df.columns and "primary_artist" in df.columns:
        import unicodedata as _ud3

        def _norm_dedup(text: str) -> str:
            """Strip Vietnamese diacritics + lowercase + collapse spaces for dedup."""
            text = text.replace('Đ', 'D').replace('đ', 'd')
            nfd = _ud3.normalize('NFD', text)
            stripped = ''.join(c for c in nfd if _ud3.category(c) != 'Mn')
            return ' '.join(stripped.lower().split())

        df["_n"] = df["track_name"].astype(str).apply(_norm_dedup)
        df["_a"] = df["primary_artist"].astype(str).apply(_norm_dedup)
        df = df.drop_duplicates(subset=["_n", "_a"], keep="first")
        df = df.drop(columns=["_n", "_a"])
    removed = before - len(df)
    msg = f"[Filter 3] Duplicate name+artist (diacritics-normalized): removed {removed:,} → {len(df):,}"
    print(f"  {msg}")
    report_lines.append(msg)

    # ── 4. Duration bounds ───────────────────────────────────────────────
    dur_col = "track_duration_ms" if "track_duration_ms" in df.columns else "duration_ms"
    if dur_col in df.columns:
        before = len(df)
        df[dur_col] = pd.to_numeric(df[dur_col], errors="coerce")
        # Keep tracks with NaN duration (will get real duration from MP3 later)
        has_dur = df[dur_col].notna()
        in_range = df[dur_col].between(MIN_DURATION_MS, MAX_DURATION_MS)
        df = df[~has_dur | in_range]
        removed = before - len(df)
        msg = f"[Filter 4] Duration out of range (<30s or >6m): removed {removed:,} → {len(df):,}"
        print(f"  {msg}")
        report_lines.append(msg)

    # ── 5. Vietnamese re-verification (with discovered-artist protection) ─
    before = len(df)
    try:
        from tools.collect_data import VietnameseDetector
        from collections import Counter

        # Build "discovered VN artists": artists with ≥3 tracks containing
        # unique Vietnamese characters (ă, â, đ, ê, ô, ơ, ư + diacritics).
        # These are genuine VN artists whose English-titled tracks should be kept.
        artist_vn_count = Counter()
        for _, row in df.iterrows():
            track_name = str(row.get("track_name", ""))
            artist = str(row.get("primary_artist", "")).strip().lower()
            if artist and artist != "nan" and VietnameseDetector.has_vietnamese_chars(track_name):
                artist_vn_count[artist] += 1
        discovered_vn_artists = {a for a, c in artist_vn_count.items() if c >= 3}
        print(f"    (discovered {len(discovered_vn_artists):,} VN artists with ≥3 VN-char tracks)")

        keep_mask = []
        recovered = 0
        for _, row in df.iterrows():
            artist_names = str(row.get("artists", row.get("primary_artist", ""))).split(", ")
            album_name = str(row.get("album_name", ""))
            is_vn, reason = VietnameseDetector.is_vietnamese(
                str(row.get("track_name", "")), artist_names, album_name,
                discovered_artists=discovered_vn_artists,
            )
            if not is_vn:
                # Extra safety: discovered artist protection for edge cases
                primary = str(row.get("primary_artist", "")).strip().lower()
                if primary in discovered_vn_artists:
                    is_vn = True
                    recovered += 1
            keep_mask.append(is_vn)
        df = df[keep_mask]
        if recovered:
            print(f"    (recovered {recovered} tracks via discovered-artist protection)")
    except ImportError:
        print("  ⚠️ Could not import VietnameseDetector — skipping VN re-check")
    removed = before - len(df)
    msg = f"[Filter 5] Non-Vietnamese re-check: removed {removed:,} → {len(df):,}"
    print(f"  {msg}")
    report_lines.append(msg)

    # ── 6. Children's music filter ───────────────────────────────────────
    before = len(df)
    try:
        from tools.collect_data import VietnameseDetector
        keep_mask = []
        for _, row in df.iterrows():
            track_name = str(row.get("track_name", ""))
            artist = str(row.get("primary_artist", row.get("artists", "")))
            album = str(row.get("album_name", ""))
            is_child = VietnameseDetector.is_children_music(track_name, artist, album)
            keep_mask.append(not is_child)
        df = df[keep_mask]
    except ImportError:
        print("  ⚠️ Could not import VietnameseDetector — skipping children filter")
    removed = before - len(df)
    msg = f"[Filter 6] Children's music: removed {removed:,} → {len(df):,}"
    print(f"  {msg}")
    report_lines.append(msg)

    # ── 6b. Non-artist channel filter ────────────────────────────────────
    # Remove tracks from compilation channels, remix channels, TV shows, etc.
    before = len(df)
    try:
        from tools.collect_data import VietnameseDetector
        keep_mask = []
        for _, row in df.iterrows():
            artist = str(row.get("primary_artist", "")).strip()
            is_channel = VietnameseDetector.is_non_artist_channel(artist)
            keep_mask.append(not is_channel)
        df = df[keep_mask]
    except ImportError:
        print("  ⚠️ Could not import VietnameseDetector — skipping channel filter")
    removed = before - len(df)
    msg = f"[Filter 6b] Non-artist channels: removed {removed:,} → {len(df):,}"
    print(f"  {msg}")
    report_lines.append(msg)

    # ── 6c. Old-genre artist filter ──────────────────────────────────────
    # Remove tracks from bolero/nhạc vàng/trữ tình/quê hương artists
    before = len(df)
    try:
        from tools.collect_data import VietnameseDetector
        keep_mask = []
        for _, row in df.iterrows():
            artist = str(row.get("primary_artist", "")).strip()
            is_old = VietnameseDetector.is_old_genre_blocked([artist])
            keep_mask.append(not is_old)
        df = df[keep_mask]
    except ImportError:
        print("  ⚠️ Could not import VietnameseDetector — skipping old-genre filter")
    removed = before - len(df)
    msg = f"[Filter 6c] Old-genre artists: removed {removed:,} → {len(df):,}"
    print(f"  {msg}")
    report_lines.append(msg)

    # ── 6d. Remove ALL non-original versions ──────────────────────────
    # Drop every track that is a remix, cover, live, lofi, acoustic,
    # piano, version, remake, OST, soundtrack, etc.
    before = len(df)
    try:
        import re as _re

        # Variant keywords — use \b word-boundaries to avoid false
        # positives (e.g. "Touliver" must NOT match "live").
        _VKW = (
            r'remix|lofi|lo-fi|lo fi|acoustic|piano|'
            r'live|live session|live at|'
            r'minishow|moodshow|liveshow|in concert|concert|'
            r'session|sessions|deep cuts|'
            r'version|ver\.|speed up|sped up|slowed|reverb|'
            r'mashup|rapcoustic|drill|house|vinahouse|edm|ballad ver|cover|chill|'
            r'extended|instrumental|karaoke|beat|stripped|'
            r'unplugged|orchestral|orchestra|symphony|remaster|demo|radio edit|'
            r'rework|flip|bootleg|vip mix|dub|trap|future bass|'
            r'tropical|deep house|progressive|hardstyle|techno|'
            r'nightcore|8d|bass boosted|phonk|uk garage|'
            r'rock version|tiktok|original soundtrack|'
            r'remake|bonus track|bonus|film version|short version'
        )

        # 1) Parenthesized / bracketed: "Song (Remix)" or "Song [Lofi]"
        _VAR_PAREN = _re.compile(
            r'[\(\[][^\)\]]*\b(?:' + _VKW + r')\b[^\)\]]*[\)\]]',
            _re.IGNORECASE,
        )
        # 2) Dash-separated: "Song - Remix", "Song - SS Remix"
        _VAR_DASH = _re.compile(
            r'\s+-\s+(?:[A-Za-z0-9\u00C0-\u024F\s]*\s+)?'
            r'\b(?:' + _VKW + r')\b',
            _re.IGNORECASE,
        )
        # 3) Bare suffix: "SONG NAME REMIX"
        _VAR_SUFFIX = _re.compile(
            r'\s+(?:remix|lofi|acoustic|karaoke|cover|instrumental|remaster)\s*$',
            _re.IGNORECASE,
        )
        # 4) Trailing ", Live" at end of title (catches "- From …, Live")
        _VAR_TRAILING_LIVE = _re.compile(
            r',\s*Live\s*$', _re.IGNORECASE,
        )
        # 5) Soundtrack: (From "..."), (Theme Song From ...), OST
        _VAR_FROM = _re.compile(
            r'[\(\[](?:Theme\s+Song\s+)?[Ff]rom\s+\S',
            _re.IGNORECASE,
        )
        _VAR_OST = _re.compile(
            r'\bOST\b|Original\s+(?:Motion\s+Picture\s+)?Soundtrack',
            _re.IGNORECASE,
        )
        # 7) Mashup/Medley/Liên Khúc at start of title
        _VAR_MASHUP_PREFIX = _re.compile(
            r'^(?:Mashup|Medley|Liên Khúc)\b',
            _re.IGNORECASE,
        )

        def _is_variant(title: str) -> bool:
            return bool(
                _VAR_PAREN.search(title)
                or _VAR_DASH.search(title)
                or _VAR_SUFFIX.search(title)
                or _VAR_TRAILING_LIVE.search(title)
                or _VAR_FROM.search(title)
                or _VAR_OST.search(title)
                or _VAR_MASHUP_PREFIX.search(title)
            )

        # Live/concert album detection — remove tracks from live albums
        _LIVE_ALBUM_RE = _re.compile(
            r'\b(?:live|concert|liveshow|live show|session|sessions|dạ khúc)\b',
            _re.IGNORECASE,
        )
        # Whitelist album names that contain these words but are NOT live
        _LIVE_ALBUM_WHITELIST = _re.compile(
            r'\bALIVE\b|\bTouliver\b|\bProd\.?\b',
            _re.IGNORECASE,
        )

        def _is_live_album(album_name: str) -> bool:
            if not album_name or album_name == 'nan':
                return False
            if _LIVE_ALBUM_WHITELIST.search(album_name):
                return False
            return bool(_LIVE_ALBUM_RE.search(album_name))

        # Remove by track title OR live album
        mask_title = df['track_name'].fillna('').apply(lambda t: not _is_variant(str(t)))
        mask_album = df['album_name'].fillna('').apply(lambda a: not _is_live_album(str(a)))
        df = df[mask_title & mask_album]
    except Exception as e:
        print(f"  ⚠️ Variant filter error: {e}")
    removed = before - len(df)
    msg = f"[Filter 6d] Non-original versions removed: {removed:,} → {len(df):,}"
    print(f"  {msg}")
    report_lines.append(msg)

    # ── 6e. Foreign artist pattern filter ────────────────────────────────
    # Remove tracks from Brazilian MC/DJ and other foreign artists
    before = len(df)
    try:
        from tools.collect_data import VietnameseDetector
        keep_mask = []
        for _, row in df.iterrows():
            artist = str(row.get("primary_artist", "")).strip()
            artists_str = str(row.get("artists", artist))
            artist_list = [a.strip() for a in artists_str.split(",")]
            is_foreign = VietnameseDetector.is_foreign_blocked(artist_list)
            keep_mask.append(not is_foreign)
        df = df[keep_mask]
    except ImportError:
        print("  ⚠️ Could not import VietnameseDetector — skipping foreign filter")
    removed = before - len(df)
    msg = f"[Filter 6e] Foreign artists: removed {removed:,} → {len(df):,}"
    print(f"  {msg}")
    report_lines.append(msg)

    # ── 7. Foreign-language dominant tracks ───────────────────────────────
    # Tracks where foreign characters (CJK/Korean/Thai) OUTNUMBER VN chars.
    # e.g. "あいうえお Việt Remix" has 5 foreign vs 1 VN → reject.
    before = len(df)
    try:
        from tools.collect_data import Config
        keep_mask = []
        for _, row in df.iterrows():
            combined = f"{row.get('track_name', '')} {row.get('primary_artist', '')} {row.get('album_name', '')}"
            foreign_count = 0
            vn_count = 0
            for ch in combined:
                cp = ord(ch)
                for rng_start, rng_end in Config.FOREIGN_CHAR_RANGES:
                    if rng_start <= cp <= rng_end:
                        foreign_count += 1
                        break
                if ch in Config.VIETNAMESE_UNIQUE_CHARS:
                    vn_count += 1
            # Reject if has ≥3 foreign chars AND foreign > VN
            if foreign_count >= 3 and foreign_count > vn_count:
                keep_mask.append(False)
            else:
                keep_mask.append(True)
        df = df[keep_mask]
    except ImportError:
        pass
    removed = before - len(df)
    msg = f"[Filter 7] Foreign-dominant tracks: removed {removed:,} → {len(df):,}"
    print(f"  {msg}")
    report_lines.append(msg)

    # ── 8. Low-quality / obscure artist filter ───────────────────────────
    # Two-layer approach:
    # A) Blocklist of known non-mainstream/spam/entertainment artists (ALWAYS runs)
    # B) Artist-level quality: max track popularity < 15 → remove (only when pop column exists)
    before = len(df)

    # A) Specific artist blocklist (from manual review of data quality)
    _ARTIST_BLOCKLIST = {
            # Entertainment/comedy — not music artists
            'bác sĩ mập hồng', 'chó phú quốc', 'rắn cạp đuôi', 'hoàng lụt',
            # Instrumental ensembles — hard to match on ytmusicapi
            'jaigon orchestra',
            # Very obscure / local / non-mainstream
            'lộc kim vân', 'thảo phạm', 'hòa t. trần', 'đức kaishi',
            'duy phúc', 'bích liên singer', 'myhoa', 'n ly', 'dewar',
            'vũ thắng lợi', 'hưng cacao', 'mai diệu ly', 'phan ann',
            'minh quan', 'nguyễn duyên quỳnh', 'cần vinh', 'mona evie',
            'hoàng quyền', 'qz', 'annhvu',
            # Underground with too many remixes — low match rate on ytmusic
            'hữu stream', 'don raemo', 'doff',
            # User-flagged: obscure/old/not-mainstream-enough
            'thuỳ dung', 'jombie', 'đồng lan', 'ngọc mai', 'ken quach',
            'nam tiến', 'quách beem', 'lều phương anh', 'panny', 'betekar',
            'milly', 'sĩ thanh', 'ái phương', 'tấn phạm',
            # ── v14.2 — Non-artist / compilation / TV show entries ──
            'nhiều ca sĩ', 'nhieu ca si',
            'chị đẹp đạp gió rẽ sóng', 'chi dep dap gio re song',
            'liên quân mobile', 'vina bất diệt', 'tốp nam',
            'nhóm la thăng', 'nhóm lạc việt', 'cam philharmonic',
            'openshare', 'magazine', 'ian rees', 'feliks alvin',
            # ── v14.3 — Non-music / comedians / TV hosts ──
            'mc 12', 'trấn thành', 'trường giang', 'bb trần',
            'huỳnh lập', 'tiến luật', 'tự long', 'thành trung',
            'nsưt thoại mỹ', 'nsnd bạch tuyết',
            'nsưt kim tiểu long',
            'gia đình lâm vỹ dạ - hứa minh đạt',
            'cát phượng', 'lâm vỹ dạ', 'chí tài', 'khả như',
            'kiều oanh',
            # ── v14.3 — Foreign artists that slipped through ──
            'south park mexican', 'juan gotti', 'chriss vogt',
            'gasca zurli', 'antoneus maximus', 'ted park',
            'two maloka', 'sonaone', 'herbalife',
            'teodora', 'nik makino', 'ralphie reese',
            'megashock', 'raditori', 'mimetals', 'lemese',
            'orkestrated', 'mal delayz', 'almighty hova',
            'kevin krissen', 'various artist',
            # ── v14.4 — User-flagged: not matching criteria ──
            # Obscure / non-mainstream / wrong channel
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
            # Old-genre artists user confirmed to block
            'nguyễn phi hùng', 'vy oanh',
            'phạm quỳnh anh', 'vương anh tú', 'thanh long',
            'cao duy', 'charmy pham',
            'v.music', 'oplus', 'vân anh',
            'hà nhi', 'blacka', 'myan', 'p.shi',
            'jackt', 'robber', 'công hoà', 'chỉ hoa',
            'nah', 'thanh duy', 'jang nguyễn',
            'f47', 'vo ha tram',
            'võ hạ trâm',
            # More user-flagged
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
            # ── Old-genre / trữ tình — confirmed not needed ──
            'hiền thục', 'vicky nhung', 'nguyễn đình vũ',
            'la thăng', 'thái hoàng', 'phạm hoàng khoa',
            'khổng tú quỳnh', 's.t sơn thạch',
            'phan duy anh', 'phát huy t4', 'phát hồ',
            'bùi anh tuấn', 'brother a tuấn anh',
            'ssay huỳnh', 'trần trác phong', 'hoàng hải đăng',
            'châu dương', 'doãn hiếu', 'hà chương',
            'đinh hương',
            # User-requested removals
            'phạm trưởng', 'hồ ngọc hà',
            # --- Comprehensive cleanup (old/trữ tình/bolero/folk/wrong identity) ---
            'tiến nguyễn', 'hồng dương', 'tường vy', 'myra trần', 'hồ hoài anh',
            'thanh hoa', 'vân quỳnh', 'mỹ dung', 'gigi hương giang',
            'ngọc lễ', 'khánh hà', 'nsut xuân hinh', 'nhóm mây trắng',
            'thế vũ', 'vy thúy vân', 'nguyên chấn phong', 'hoàng thanh',
            'thành an', 'nguyễn đan', 'quốc phú', 'huỳnh lợi',
            'trương lệ vân', 'lê chí trung', 'hoàng bách', 'châu khải phong',
            'tiêu minh phụng', 'đức minh', 'trọng bắc', 'lâm bảo ngọc',
            'hoài anh kiệt', 'hương giang', 'đặng dinh', 'hkt',
            'trạm cảm xúc', 'đinh tiến đạt', 'phung ngoc huy',
            'nguyễn thùy linh', 'tuấn nghĩa', 'hồng sơn',
            'mỹ anh',  # old trữ tình singer (not Mỹ Linh's daughter)
            'emily',   # French artist (not Vietnamese Emily)
            'dick & dee dee', 'the beach', 'conego',  # non-Vietnamese
            'grab', 'bdmedia', 'doctor nature',  # not real artists
            'chúc hỷ', 'xuân định k.y', 'hanoi blues note',
            # Additional old/revolutionary/folk artists
            'tuyết thanh', 'thúy lan', 'cảnh thiên', 'quốc dũng',
            'kim phúc', 'phan muôn', 'thanh thúy', 'huy hùng',
            'lê dung', 'minh',  # old singer covering Trịnh Công Sơn classics
            'hoàng kim', 'hoàng dung', 'thanh huyền',  # old folk/nhạc đỏ singers
            'kha thi',  # bolero singer
            'sỹ ben', 'sy ben',  # old trữ tình
            'như hảo', 'nhu hao',  # old folk/nhạc đỏ
            # ── v15.0 — comprehensive old/cải lương/bolero/nhạc đỏ/thánh ca cleanup ──
            # Choirs / groups old
            'tốp nữ', 'tốp nam nữ', 'tam ca 3a', 'tam ca thế hệ mới',
            'tứ ca ngẫu nhiên', 'nhóm mtv', '5 dòng kẻ', 'năm dòng kẻ',
            'nhóm ac & m', 'ac&m', 'nhom gmc', 'little v cẩm vân',
            # Nhạc sĩ / pre-1975
            'anh bằng',
            # Cải lương / tân cổ
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
            # Bolero / nhạc vàng / hải ngoại / old
            'anh dũng', 'hoàng việt trang', 'trịnh nam sơn',
            'dạ hương', 'tuấn cường', 'quách tấn du',
            'vân trường', 'y phụng', 'đoàn phi',
            'cam thơ', 'tấn đạt', 'khắc dũng',
            'thúy đạt', 'kiều diễm', 'thanh phương',
            'ngọc yến', 'kim cương', 'thọ hùng',
            'thiên sơn', 'dương minh kiệt', 'ngọc vũ',
            'mai trung tín', 'đỗ quang', 'hoàng tâm',
            'ngọc xuân', 'chí hướng', 'tuấn phương',
            'kim anh', 'thành nhân', 'cảnh hàn',
            'việt hà', 'văn tuấn', 'quang cường',
            'hồ phong an', 'kim thoa', 'quý tráng',
            'khắc tư', 'triệu ánh xuân', 'cát tuyền',
            'lâm thúy vân', 'thục trinh', 'julie',
            'lucia kim chi', 'huỳnh tiểu nhi',
            'minh hà', 'ngọc hiền', 'ánh minh',
            'lysa đoàn', 'thuý miền', 'thụy anh', 'hồng phúc',
            'trịnh nam gia', 'ngọc thy', 'nguyễn cửu dũng',
            'phương hồng thủy', 'giáng tiên', 'tấn beo',
            'mộng tuyền', 'ns thanh hằng', 'phụng quốc giang',
            'thái châu', 'phương quang', 'hà thanh xuân',
            'siu black', 'y jang tuyn', 'ba tráng',
            'quỳnh gai', 'lisa thùy lâm', 'connie kim',
            'cẩm vân phạm', 'le minh hieu', 'linh huệ',
            'liêu duy linh', 'sang sang', 'thành nguyên',
            'hoàng phong quân', 'bảo thiên',
            'nguyễn quang trọng', 'tuấn phong', 'hoàng thái',
            'nini', 'phan hoàng oanh', 'trần tâm',
            'ngọc quỳnh', 'hữu nội', 'hamlet trương radio',
            'kiều nương', 'quỳnh hương',
            # Nhạc đỏ / dân ca / quê hương
            'quang hào', 'tiến thành', 'duy thường',
            'tố hà', 'huyền trang sao mai', 'thuý cải',
            'phi thúy hạnh', 'quang đại',
            # Thánh ca / nhạc đạo
            'thụy long', 'mai thảo',
            # Nhạc thiếu nhi / not singer
            'uyển my', 'ngô thanh vân', 'be bao ngu',
            # Old groups
            'tik tik tak', 'bạn có tài mà',
            # Small-count old
            'mạnh giàu', 'lâm dũng', 'ngọc anh vi',
            'duy long', 'ngân quỳnh', 'phượng hằng',
            'trường thống', 'việt hoà', 'khánh dũng',
            'quý bình', 'mỹ trâm', 'lê minh hảo', 'bích ngọc',
            'thu hà', 'thanh sơn',
            # ── v16.0 — user-specified + comprehensive audit cleanup ──
            # User-flagged removals
            'vu van', 'tuyết mai', 'quỳnh như', 'lâm hùng',
            'phạm hiền', 'vũ trà', 'tấn sang', 'phạm kỳ',
            'ba trọng', 'khanh dan',
            'lương hồng quế', 'trịnh ngọc huyền', 'lương hồng huệ',
            'kim thúy', 'hà bửu tân', 'sơn trung',
            'nguyễn đình tuấn dũng', 'vũ minh đức', 'đinh huy',
            'như hiền', 'đức việt', 'lương tuấn',
            'như mai', 'vy vân', 'candy hoàng hoa',
            # Audit: nhạc đỏ / dân ca / quê hương / old
            'thanh hiếu', 'tú linh', 'thu giang', 'cao minh',
            'hoàng vinh', 'minh thành', 'bảo trâm',
            'trung anh', 'duy sang', 'thế dân',
            'thái bảo', 'thanh cường', 'a páo',
            'trần thụy kim anh', 'lan anh', 'đại vệ',
            'nguyễn hữu chiến thắng', 'nha ngoc',
            # Audit: thánh ca / ca đoàn
            'ca đoàn ngàn khơi', 'vương dzung', 'reddy',
            'lâm nhật tiến & ca đoàn ngàn khơi',
            'mai thanh sơn & lê anh quân & ca đoàn ngàn khơi',
            # Audit: cải lương / vọng cổ / xẩm
            'thái khiết linh', 'thế phương vbk',
            # Audit: old / unclear
            'techno', 'ngọc quỳnh', 'yuniboo',
            'gia huy', 'khánh du', 'khánh đăng',
            'release', 'thành phú',
            'duy khoa', 'phan hoàng tâm',
            # ── v16.1 — final cleanup ──
            'bảo thơ',  # nhạc trữ tình cũ
            'hoàng thơ - đào đức',  # old folk
            'ngọc điệp',  # dân ca ("Lý Cây Khế")
            'bùi phi long',  # dân ca ("Thương Con Sáo Sang Sông")
            'châu tuấn - yến khoa',  # old
            'tam ca 3 a',  # spacing variant of "tam ca 3a"
            'volodymyr bielik',  # foreign artist
            # ── v17.0 — strict modern-only filter: remove ALL old-gen (pre-2013 fame) ──
            # 90s-2000s pop idols / divas / ballad singers
            'đan trường', 'lam trường', 'ưng hoàng phúc',
            'mỹ tâm', 'hồ quỳnh hương', 'quang vinh',
            'cao thái sơn', 'thu minh', 'đăng khôi',
            'thủy tiên', 'bảo thy', 'lê hiếu',
            'yanbi', 'lưu hương giang', 'quỳnh nga',
            'wanbi tuấn anh', 'nathan lee', 'minh hằng',
            'ông cao thắng', 'hà trần', 'lil knight',
            "lil' knight", '365daband', 'the men',
            'hoài lâm', 'quốc thiên', 'isaac',
            'cường seven', 'hari won', 'nhật thủy',
            'ngô kiến huy', 'akira phan', 'khởi my',
            'đông nhi',
            'tóc tiên', 'miu lê', 'trịnh thăng bình',
            'trung quân', 'trung quân idol',
            'văn mai hương', 'uyên linh', 'hương tràm',
            'đinh mạnh ninh', 'phương mỹ chi', 'thái trinh',
            'song luân', 'khắc việt', 'hồ quang hiếu',
            'maya', 'nguyên hà', 'phạm toàn thắng',
            'jun phạm', 'dương hoàng yến', 'gil lê',
            'lê cát trọng lý', 'thanh bùi', 'minh vương m4u',
            'hà myo', 'tuấn hưng', 'lưu hưng', 'hồ phong an',
            'nguyễn hải phong', 'nukan trần tùng anh',
            # Nhạc trẻ sến / bolero-adjacent / old nhạc trẻ
            'vũ duy khánh', 'lê bảo bình',
            'gin tuấn kiệt', 'tuấn đạt', 'huy vạc',
            'dương hiếu nghĩa', 'vina uyển my', 'datkaa',
            'bảo kun', 'đinh tùng huy', 'đình phong',
            'tuấn khoa', 'aki ngọc duy', 'only c',
            'đông thiên đức', 'hoàng tôn', 'jaykii',
            'huyr', 'khải đăng', 'kuun đức nam',
            'nguyễn phước hoàn', 'lynk lee', 'lê thiện hiếu',
            'phạm anh duy', 'vũ thảo my', 'huỳnh james',
            'trang pháp',
            'lê hoàng (tm1981)', 'mỹ mỹ',
            'trịnh tuấn vỹ', 'nukan trần tùng anh',
            'khaly nguyễn', 'ut nhị', 'thế phương vbk',
            # ── v17.1 — final mop-up ──
            'mạnh quân',  # nhạc trẻ/actor
            'will', 'will 365',  # 365DaBand member
            'duy khánh 周周', 'duy khánh',  # nhạc trẻ variant
            'hakoota', 'hakoota dũng hà',  # old indie
            'kaisoul',  # old nhạc trẻ rapper
            'nicky st.319',  # old group
            'mia',  # old pop (MiA)
            'ngọc trinh',  # model, not singer
            'nguyễn trần trung quân',  # full name variant of trung quân
            # ── v18.0 — thorough cleanup: obscure / non-famous / old-era combos ──
            # High-track obscure artists (manual audit)
            'đức thịnh', 'hải sâm', 'haisam', 'tiến minh', 'hoàng hải dương',
            'hạnh sino', 'big daddy ft hạnh sino',
            'minh tiến', 'chuột sấm sét', 'bảo yến rosie',
            'huỳnh tú', 'minh tốc & lam',
            'wowy ft karik ft nhật cường',  # old SouthGangz era
            # Medium-track obscure
            'the fillin', 'anh thư phan', 'tuấn việt',
            'mike', 'mess.', 'kidsai', 'gung0cay',
            'j.key', '$a milo', 'willistic', 'dlblack',
            'yến tatoo', 'phankeo', 'emma nhất khanh',
            'dickson', 'nvm', 'jay bach', 'hazard clique',
            'rocky cde', 'wokeup', 'lv king', 'nimbia',
            'fous', 'thien hi', 'alex lam', 'sean',
            # Small-count obscure (user-flagged)
            'vĩnh hoàng', 'đĩa than hồng', 'swan nguyễn',
            "a 'namese", 'nam duong', 'neko land',
            'pixel neko', '(s)trong', 'blak ray',
            'vy jacko', 'mylina', 'mopius', 'mcee blue',
            'chiulinh', 'vcc left hand', 'superc',
            'v.o.x', 'maiquinn', 'tyt', 'p$mall', 'lizay',
            'limitlxss', 'cashmel', 'pain a.k.a dai ca p',
            'trungng', 'tgsn', 'bigp', 'khánh jayz',
            'tùng maru',
            # Obscure featured/primary flagged by user
            'aitai', 'bảo hân helia', 'hằng ssi',
            'quyết tiến maz', 'gia bảo', 'đạt max',
            'chút bình yên', 'hồng đào', 'phùng tiến minh',
            'vũ phương anh', 'trungg i.u', 'pialinh',
            'rica', 'minh cà ri', 'tịnh quyên', 'hai bang',
            'bảo phúc', 'tân hy khánh', 'đinh quang đạt',
            'juan phi', 'guen', 'viam', 'niz', 'cangcang',
            'nhóm g-shine', 'phương hoa', 'trịnh bảo bàng',
            'beta music', 'blackbi',
            # v18.1 — user-flagged
            'mèow lạc', 'hồng lụa', 'lil shady',
            'phạm hoàng anh', 'a.c xuân tài',
            'mingji', 'miky đóng tune',
            'addy trần',
        }

        # Build diacritics-stripped version of blocklist for fuzzy matching
    import unicodedata as _ud8

    def _norm_f8(text: str) -> str:
        text = text.replace('Đ', 'D').replace('đ', 'd')
        nfd = _ud8.normalize('NFD', text)
        return ''.join(c for c in nfd if _ud8.category(c) != 'Mn').lower().strip()

    _BLOCKLIST_STRIPPED = {_norm_f8(a) for a in _ARTIST_BLOCKLIST}

    # B) Compute artist-level max popularity (only when pop column exists)
    pop_col = "track_popularity" if "track_popularity" in df.columns else "popularity"
    has_pop = pop_col in df.columns
    if has_pop:
        df[pop_col] = pd.to_numeric(df[pop_col], errors='coerce')
        all_null = df[pop_col].isna().all()
        df[pop_col] = df[pop_col].fillna(0)
        artist_max_pop = df.groupby(
            df['primary_artist'].astype(str).str.strip().str.lower()
        )[pop_col].max()

    keep_mask = []
    for _, row in df.iterrows():
        art_lower = str(row.get('primary_artist', '')).strip().lower()
        art_stripped = _norm_f8(art_lower)

        # A) Blocklist check (exact + diacritics-stripped) — ALWAYS runs
        if art_lower in _ARTIST_BLOCKLIST or art_stripped in _BLOCKLIST_STRIPPED:
            keep_mask.append(False)
            continue

        # B) Artist max popularity check — if their BEST track < 15, likely obscure
        #    Only runs when popularity column exists
        if has_pop and not all_null:
            max_pop = artist_max_pop.get(art_lower, 0)
            if max_pop < 15:
                keep_mask.append(False)
            else:
                keep_mask.append(True)
        else:
            keep_mask.append(True)

    df = df[keep_mask]
    removed = before - len(df)
    msg = f"[Filter 8] Low-quality/obscure artists (blocklist + max_pop<15): removed {removed:,} → {len(df):,}"
    print(f"  {msg}")
    report_lines.append(msg)

    # ── 8b. Clean "Artist | Title" pipe format → strip artist prefix ─────
    # YTMusic playlist compilations often name tracks "Artist | Song Title".
    # Clean by replacing with just the song title, then dedup again.
    import re as _re8b
    _PIPE_RE = _re8b.compile(r'^(.+?)\s*\|\s*(.+)$')
    pipe_cleaned = 0
    new_names = []
    for _, row in df.iterrows():
        tn = str(row['track_name'])
        m = _PIPE_RE.match(tn)
        if m:
            prefix = m.group(1).strip().lower()
            artist = str(row.get('primary_artist', '')).strip().lower()
            # Only strip if the prefix matches the artist name
            if prefix == artist or artist.startswith(prefix) or prefix.startswith(artist):
                new_names.append(m.group(2).strip())
                pipe_cleaned += 1
            else:
                new_names.append(tn)
        else:
            new_names.append(tn)
    df['track_name'] = new_names
    if pipe_cleaned:
        # Dedup again after cleaning
        before = len(df)
        df['_dedup_key'] = (
            df['track_name'].astype(str).str.strip().str.lower() + '|||' +
            df['primary_artist'].astype(str).str.strip().str.lower()
        )
        df = df.drop_duplicates(subset='_dedup_key', keep='first')
        df = df.drop(columns=['_dedup_key'])
        dup_removed = before - len(df)
        msg = f"[Filter 8b] Pipe-format cleanup: {pipe_cleaned:,} cleaned, {dup_removed:,} new duplicates removed → {len(df):,}"
        print(f"  {msg}")
        report_lines.append(msg)

    # ── 8c. Per-artist track cap ────────────────────────────────────────
    # DISABLED: no per-artist cap — keep all tracks per artist.
    # MAX_TRACKS_PER_ARTIST = 50

    # ── 9. Remove tracks without audio features (post-Phase 5) ───────────
    # Only applied if phase5 columns exist (i.e. running after Phase 5).
    essential = ["valence", "energy", "danceability"]
    available_essential = [c for c in essential if c in df.columns]
    if len(available_essential) >= 2:
        before = len(df)
        # Require at least 2 of the 3 essential features to be non-null
        null_counts = df[available_essential].isnull().sum(axis=1)
        df = df[null_counts <= 1]
        removed = before - len(df)
        if removed > 0:
            msg = f"[Filter 9] Missing audio features (≥2/3 null): removed {removed:,} → {len(df):,}"
            print(f"  {msg}")
            report_lines.append(msg)

    # ── Reset index ──────────────────────────────────────────────────────
    df = df.reset_index(drop=True)

    # ── 10. Drop always-null columns (YTMusic mode) ──────────────────────
    _YTMUSIC_NULL_COLS = ['spotify_track_id', 'preview_url', 'release_date']
    dropped_cols = []
    for col in _YTMUSIC_NULL_COLS:
        if col in df.columns and df[col].isna().all():
            df = df.drop(columns=[col])
            dropped_cols.append(col)
    # Also drop track_popularity if all zero/null (useless in YTMusic mode)
    if 'track_popularity' in df.columns:
        pop_vals = pd.to_numeric(df['track_popularity'], errors='coerce')
        if pop_vals.isna().all() or (pop_vals.fillna(0) == 0).all():
            df = df.drop(columns=['track_popularity'])
            dropped_cols.append('track_popularity')
    if dropped_cols:
        msg = f"[Cleanup] Dropped always-null columns: {', '.join(dropped_cols)}"
        print(f"  {msg}")
        report_lines.append(msg)

    # ── Summary ──────────────────────────────────────────────────────────
    total_removed = initial - len(df)
    pct = total_removed / initial * 100 if initial else 0
    summary = (
        f"\n## Summary\n"
        f"- Input: {initial:,}\n"
        f"- Output: {len(df):,}\n"
        f"- Removed: {total_removed:,} ({pct:.1f}%)"
    )
    report_lines.append(summary)
    print(f"\n  ✅ Filtering complete: {initial:,} → {len(df):,} tracks ({total_removed:,} removed, {pct:.1f}%)")

    # ── Write outputs ────────────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(str(output_path), index=False, encoding="utf-8-sig")
    print(f"  ✅ Output: {output_path}")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"  ✅ Report: {report_path}")

    return df


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Brightify Phase 2 – Data Filtering")
    parser.add_argument("--input", "-i", default=str(DEFAULT_INPUT), help="Input CSV")
    parser.add_argument("--output", "-o", default=str(DEFAULT_OUTPUT), help="Output CSV")
    parser.add_argument("--report", default=str(REPORT_PATH), help="Report path")
    args = parser.parse_args()
    run_filter(Path(args.input), Path(args.output), Path(args.report))


if __name__ == "__main__":
    main()
