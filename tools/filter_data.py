"""
Brightify – Phase 2: Data Filtering & Deduplication

Reads Phase 1 output (phase1_spotify.csv) and produces a clean, deduplicated
dataset with only Vietnamese tracks that have essential metadata.

Filters applied (in order):
  1.  Remove rows missing track_id or track_name
  2.  Remove duplicate track_ids (keep highest popularity)
  2b. Normalize artist names (ASCII ↔ diacritics)
  3.  Remove duplicate name+artist combinations (diacritics-normalized)
  4.  Remove tracks shorter than 2m30s or longer than 360s (6 minutes),
      except editorially approved short tracks
  5.  Verify Vietnamese (re-run VietnameseDetector v2 as safety net)
  6.  Remove children's music (nhạc thiếu nhi)
  6b. Remove non-artist channels (remix/compilation/TV show channels)
  6c. Remove old-genre artists (bolero/nhạc vàng/cải lương)
  6d. Remove non-original versions (remix/live/cover/acoustic/lofi…)
  6e. Remove foreign artist patterns (Brazilian MC/DJ…)
  6f. Remove seasonal music (Tết/Xuân + Giáng Sinh/Noel) [NEW]
  6g. Remove tracks released before 2013 (target 9x/GenZ) [NEW]
  6h. Remove profanity in track titles
  6i. Remove profanity-heavy lyrics (when lyrics are present)
  7.  Remove foreign-language dominant tracks (CJK/Korean/Thai > VN chars)
  7c. Remove foreign-language lyrics with no Vietnamese evidence
  8.  Remove low-quality/obscure artists (blocklist + max popularity < 15)
  8b. Clean "Artist | Title" pipe format → strip artist prefix
  8c. Remove tracks with very low per-track popularity (< 20) [NEW]
  9.  Remove tracks missing essential audio features (post-Phase 5)

Output: checkpoints/phase2_filtered.csv

Usage:
    python -m tools.filter_data                          # default
    python -m tools.filter_data --input path/to/csv      # custom input
    python -m tools.filter_data --report                 # print report only
"""

import argparse
from difflib import SequenceMatcher
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

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
MIN_DURATION_MS = 150_000   # 2 minutes 30 seconds
MAX_DURATION_MS = 360_000   # 6 minutes

# Release year filter — target 9x/GenZ audience
RELEASE_YEAR_MIN = 2013     # soft filter: only drops tracks with KNOWN year < this

# Per-track popularity floor (Spotify 0-100 scale)
TRACK_POP_MIN = 20          # soft filter: only drops when popularity IS known and < this
VIEW_COUNT_MIN = 100_000    # post-download floor when Spotify popularity is unavailable
RECENT_VIEW_COUNT_MIN = 50_000
RECENT_RELEASE_YEAR_MIN = 2022


_VN_TOKEN_CHARS = r"A-Za-zÀ-ỹ0-9"
_PROFANITY_HARD_RE = re.compile(
    rf'(?<![{_VN_TOKEN_CHARS}])(?:địt|đụ(?!ng)|cặc|lồn|buồi)(?![{_VN_TOKEN_CHARS}])'
    rf'|(?<![{_VN_TOKEN_CHARS}])(?:đầu buồi|con buồi|bú c|liếm c)(?![{_VN_TOKEN_CHARS}])',
    re.IGNORECASE,
)
_PROFANITY_MILD_RE = re.compile(
    rf'(?<![{_VN_TOKEN_CHARS}])(?:đéo|vãi l|vãi đ|đ\.m|đmm|đmcs|vcl|cứt|mẹ mày|mẹ kiếp)(?![{_VN_TOKEN_CHARS}])',
    re.IGNORECASE,
)
_TITLE_PROFANITY_RE = re.compile(
    rf'(?<![{_VN_TOKEN_CHARS}])(?:địt|đụ(?!ng)|cặc|lồn|buồi|đéo|vcl|đ\.m|đmm|cứt)(?![{_VN_TOKEN_CHARS}])',
    re.IGNORECASE,
)

_SEASONAL_TET_STRONG_RE = re.compile(
    r'\b(?:tet|tet nguyen dan|mung xuan|chuc tet|chuc xuan|nam moi|'
    r'du xuan|don xuan|hoi xuan|giao thua|li xi|hai loc|'
    r'banh chung|banh tet|ong do|cau doi|hoa dao|hoa mai|'
    r'phao hoa|anh cho em mua xuan|giai dieu mua xuan|'
    r'goi (?:em la|ten) mua xuan|hay mang den nhung mua xuan|'
    r'hom nay mua xuan|mua xuan (?:oi|goi)|ngay xuan|nang xuan|'
    r'nhu hoa mua xuan|nhung ngay xuan|thi tham mua xuan|'
    r'xuan ca|xuan son|'
    r'xuan \d{2,4}|xuan se|xuan dang|xuan da|xuan ben|xuan ve|'
    r'xuan sang|doan xuan|giai dieu xuan|giai dieu mua xuan|'
    r'diep khuc mua xuan|hanh phuc xuan|dam cuoi dau xuan|lk xuan)\b',
    re.IGNORECASE,
)
_SEASONAL_NOEL_STRONG_RE = re.compile(
    r'\b(?:giang sinh|noel|christmas|xmas|merry christmas|'
    r'jingle bells?|silent night|hang be lem|dem thanh vo cung|'
    r'rudolph|santa claus)\b',
    re.IGNORECASE,
)
_SEASONAL_ALBUM_STRONG_RE = re.compile(
    r'\b(?:nhac tet|tet nguyen dan|mung xuan|chuc tet|chuc xuan|'
    r'nam moi|du xuan|don xuan|hoi xuan|giao thua|li xi|'
    r'banh chung|banh tet|hoa dao|hoa mai|giai dieu mua xuan|'
    r've nha don tet|xuan phat tai|giang sinh|noel|'
    r'christmas|xmas|merry christmas)\b',
    re.IGNORECASE,
)
_SEASONAL_LYRICS_STRONG_RE = re.compile(
    r'\b(?:chuc tet|chuc xuan|mung xuan|nam moi|tet nguyen dan|'
    r'giao thua|li xi|hai loc|du xuan|don xuan|hoi xuan|'
    r'hoa dao|hoa mai|banh chung|banh tet|ong do|cau doi|'
    r'giang sinh|noel|christmas|xmas|merry christmas|'
    r'jingle bells?|silent night|hang be lem|dem thanh vo cung)\b',
    re.IGNORECASE,
)
_SEASONAL_LYRICS_MARKER_RE = re.compile(
    r'\b(?:tet|tet nguyen dan|chuc tet|chuc xuan|mung xuan|nam moi|'
    r'giao thua|li xi|hai loc|du xuan|don xuan|hoi xuan|nang xuan|'
    r'phao hoa|hoa dao|hoa mai|banh chung|banh tet|ong do|cau doi|'
    r'giang sinh|noel|christmas|xmas|merry christmas|jingle bells?)\b',
    re.IGNORECASE,
)
_SEASONAL_LYRICS_CONTEXT_RE = re.compile(
    r'\b(?:com doan vien|doan vien|cuoi nam|nam qua da lam gi|'
    r'chuyen nha minh|ve nha|ve chua con|con hua se ve|nha minh co nhau|'
    r'bao gio lay chong|ra gieng|thang gieng|mung tuoi|van su nhu y|'
    r'lay via|cau duyen|them duoc ve nha|em oi anh nho nha|vi nha|'
    r'noella|noend|december)\b',
    re.IGNORECASE,
)
_SEASONAL_HINT_RE = re.compile(
    r'\b(?:tet|nam moi|giang sinh|noel|christmas|xmas|'
    r'giao thua|li xi|sum vay|hoa dao|hoa mai|banh chung|'
    r'ong do|cau doi|phao hoa|hang be lem|dem thanh vo cung)\b',
    re.IGNORECASE,
)
_SEASONAL_XUAN_RE = re.compile(r"\bxuan\b", re.IGNORECASE)
_SEASONAL_XUAN_TITLE_CONTEXT_RE = re.compile(
    r'\b(?:lung la lung luyen xuan|nang tien mua xuan|con buom xuan|'
    r'khuc hat mua xuan|khuc giao mua)\b',
    re.IGNORECASE,
)
_FOREIGN_LANGUAGE_ARTIST_BLOCKLIST = {
    "antransax",
    "cloud 5",
    "hoaprox",
    "tanny ng",
}
_KNOWN_WRONG_CONTENT_TRACK_IDS = {
    "-Rbf9Kls7qI",
    "48vT3-a45uc",
    "78lcZX49yf8",
    "9ThLlYM5fyg",
    "9W8xO_aUtgE",
    "DZ0oir_DLao",
    "__Hz1Ed2Peo",
    "FVN2srj9OIk",  # Khúc Hát Chim Trời: short re-release of an old song
    "tRVsdGZthiQ",  # Khúc Hát Chim Trời: complete re-release of an old song
    "4tYuIU7pLmI",  # Ngôi Sao Cô Đơn: MP3 source has a long extra segment
    "J-ghINjFgMQ",  # old song / mismatched re-release
    "LxNzRN8EMcw",  # Bo Xì Bo: MP3 source has a long extra segment
    "MZhSVJ4daNU",  # old low-value re-release
    "ZptHLeuexEs",  # ten-minute medley under a five-minute track entry
    "_8OsrVyr30M",  # Rời: no clean matching source found
    "gJHSDZfJrRY",  # See Tình: MP3 source has a long extra segment
    "kvcVGyzg-OI",  # mismatched source; replacement is extremely low-value
    "mA-UxOle3YQ",  # Xóa Tên Anh Đi: MP3 source has a long extra segment
    "bmURTXWSVRQ",  # Đò Sang Ngang: source is incorrectly attributed to Da LAB
    "prCggo8jWV0",  # Sao Đổi Ngôi: source is incorrectly attributed to Bảo Anh
    "wRai9bzoFts",  # NGÂY NGÔ: source is over seven minutes
    "yvK94mAuXrI",  # Đồ Gây Mê: drug/profanity-heavy lyrics, low catalog fit
    "4AFzkqtFqSg",  # Take It Off: drug/profanity-heavy lyrics, low catalog fit
    "2Atly_saklA",  # Touman: drug/profanity-heavy lyrics, low catalog fit
    "89bwEKawtSc",  # Đơn Côi: drug/profanity-heavy lyrics, low catalog fit
    "2A31yXddLig",  # To the Moon: drug/profanity-heavy lyrics, low catalog fit
    "raOHouwNuzY",  # Apeshit: drug/profanity-heavy lyrics, low catalog fit
    "9D2bBo_kGDQ",  # Crazy Love Song: Korean Orange artist collision
    "Ety-Zn2nPfs",  # On My Own: short English track
}
_SHORT_TRACK_ALLOWLIST_IDS = {
    "TpO5ZVEB3Ek",  # Hạt Giống Số 1
}
_SHORT_TRACK_ALLOWLIST_TITLES = {
    "hat giong so 1",
}
_LEGACY_IDENTITY_ARTIST_IDS = {
    "UCgzabA9k1QZhveKNQpQReOQ",  # Đức Huy: old catalog identity
    "UCxXheGOMHn5GFJW_A-3n51g",  # Tuấn Dũng: old/traditional identity
}
_SCORE_COMPOSER_ARTIST_IDS = {
    "UCNctzUfSQywEVfR-L8fUXFw",  # Khuất Duy Minh soundtrack score catalog
}
_LEGACY_RELEASE_ALBUMS_BY_ARTIST_ID = {
    # Old Bích Phượng identity mixed into the modern Bích Phương catalog.
    "UC6cABeghgrm1dV5bYnPNw6A": {
        "anh tuyet tam ca ao trang ngoi tua man thuyen",
        "ca dao dong song",
        "dan sao hau giang",
        "mo ve da lat",
        "nhiem mau tinh chua",
        "nhung dieu ly que huong",
        "tieng chuong thuc tinh",
        "tieng goi thanh nien",
        "tieng hat bich phuong",
        "tu do em buon",
        "neu anh la em",
    },
    # Old Anh Tú identity mixed into the current singer's catalog.
    "UCQmJpTarZMikea8T8Pkd2qw": {
        "bang nhac nhac tre 7",
        "ben quanh hiu",
        "buon vuong mat em",
        "caraoke",
        "chia tay chieu dong top hits 67",
        "da vu muon mau",
        "hai au 200",
        "hai au 202",
        "lang nghe thoi gian",
        "mo ve em",
        "mot thoang viet nam 1",
        "nguoi di qua doi toi",
        "nua trai tim yeu nguoi",
        "saigon saigon",
        "tinh nhu canh chim",
        "tinh suong khoi",
        "tieng mua roi",
        "van yeu mot nguoi",
    },
}
_PROGRAM_AUDIO_RE = re.compile(
    r"\b(?:san dau ca (?:tu|tư)|sàn đấu ca (?:từ|tư)|"
    r"san chien giong hat|sàn chiến giọng hát|"
    r"in the moonlight show|a colors show|gameshow|talkshow|podcast)\b",
    re.IGNORECASE,
)
_FRAGMENT_AUDIO_RE = re.compile(
    r"\b(?:audio cut|short version|snippet|teaser|intro|interlude|outro|"
    r"prologue|epilogue|opening|ending|skit)\b|"
    r"(?:^|\s)[#\[]\s*\d+\s*[\]]?\s*$",
    re.IGNORECASE,
)
_KNOWN_ARTIST_COLLISION_ALBUMS = {
    "best of latin hip hop",
    "durchstromungen 2 klangkrafte",
    "flaming star other twangin movie instrumentals associated with the king",
    "give em the boot iv",
    "give em the boot v",
    "kobolt",
    "musique bluegrass",
    "party animals vol 3",
    "peter torsens ungdomssynder",
    "project outbreak",
    "rock chicks vol 7",
    "rock chicks vol 8",
    "static waves 4",
    "vip lounge",
}
_OLD_GENRE_TEXT_RE = re.compile(
    r'\b(?:bolero|nhac vang|tru tinh|cai luong|vong co|tan co|ca co|'
    r'dan ca|nhac que huong|nhac linh|nhac xua|hai ngoai|'
    r'thanh ca|quan ho|chau van|trinh cong son|em va trinh)\b',
    re.IGNORECASE,
)
_NON_ORIGINAL_STRONG_KEYWORDS = (
    r'remix|remxi|remixes|lofi|lo-fi|lo fi|acoustic|acapella|a cappella|'
    r'lk|lien\s*khuc|liên\s*khúc|'
    r'live session|live at|live|'
    r'in the moonlight show|a colors show|'
    r'minishow|moodshow|liveshow|live show|in concert|concert|'
    r'session|sessions|deep cuts|speed up|speedup|sped up|slowed|reverb|'
    r'mashup|rapcoustic|cover collection|cover|'
    r'version|ver\.?|'
    r'extended|instrumental|karaoke|stripped|unplugged|'
    r'orchestral|orchestra|symphony|remaster|demo|radio mix|radio edit|'
    r'rework|flip|bootleg|vip mix|dj mix|dance mix|vocal mix|'
    r'nightcore|8d|bass boosted|rmx|'
    r'remake|bonus track|reprise|reprised|teaser|open verse|'
    r'interlude|intro|outro|outtro|prologue|'
    r'film version|short version|short \d+'
)
_NON_ORIGINAL_CONTEXT_KEYWORDS = (
    r'piano|solo violin|vocals|inst\.?|'
    r'performance(?:\s+with\s+band)?|harmony|romance|rumba|'
    r'(?:v|vrt|orange|real|lylicia|al\d+|tan thieu gia)\s*mix|mix|'
    r'music box|flute|instrument|doc tau sao|độc tấu sáo|'
    r'alternative|re-imagined|raw|'
    r'lam lai|làm lại|phien ban|phiên bản|ban thu|bản thu|'
    r'ban dau tien|bản đầu tiên|song ca|duet|'
    r'the recap|recap|fashion show|the heroes|'
    r'dongvui harmony|động tag show|lan song xanh|làn sóng xanh|'
    r'huong mua he|hương mùa hè|ugc only|buonhonmotchut|'
    r'chi dep dap gio re song|chị đẹp đạp gió rẽ sóng|'
    r'v2|2\.0|speed(?:\s*\d+(?:\.\d+)?)?|slow down|'
    r'drill|house|vinahouse|edm|ballad|chill|beat|trap|future bass|'
    r'tropical|deep house|progressive|hardstyle|techno|phonk|uk garage|'
    r'rock version|tiktok|tour(?:\s+\d{4})?'
)
_NON_ORIGINAL_STRONG_RE = re.compile(
    rf'\b(?:{_NON_ORIGINAL_STRONG_KEYWORDS})\b',
    re.IGNORECASE,
)
_NON_ORIGINAL_CONTEXT_RE = re.compile(
    rf'(?:'
    rf'[\(\[][^\)\]]*\b(?:{_NON_ORIGINAL_CONTEXT_KEYWORDS})\b[^\)\]]*[\)\]]'
    rf'|\s+-\s+[^|]*\b(?:{_NON_ORIGINAL_CONTEXT_KEYWORDS})\b'
    rf'|\b(?:piano|solo violin|vocals|inst\.?)\s*$'
    rf')',
    re.IGNORECASE,
)
_NON_ORIGINAL_WHITELIST_RE = re.compile(
    r'\bALIVE\b|\bTouliver\b|\bProd\.?\b',
    re.IGNORECASE,
)
_SOUNDTRACK_RE = re.compile(
    r'\b(?:original\s+(?:motion picture|television|movie)\s+soundtrack|'
    r'original soundtrack|soundtrack|ost)\b',
    re.IGNORECASE,
)
_VN_UNIQUE_CHARS = set(
    "àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩ"
    "òóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ"
    "ÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨ"
    "ÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ"
)
_VN_HINT_WORDS = {
    "của", "tôi", "bạn", "anh", "em", "và", "là", "có", "yêu", "thương",
    "nhớ", "buồn", "vui", "mình", "người", "thôi", "đâu", "đây", "sao",
    "như", "khi", "một", "được", "không", "rồi", "nào", "hết", "lòng",
    "đời", "ngày", "đêm", "mưa", "nắng", "bao", "mãi", "chờ", "còn",
}


def _strip_vn_diacritics(text: str) -> str:
    text = str(text or "").replace("Đ", "D").replace("đ", "d")
    nfd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def _normalize_match_text(text: str) -> str:
    stripped = _strip_vn_diacritics(text).lower()
    return re.sub(r"[^a-z0-9]+", " ", stripped).strip()


_VN_HINT_WORDS_ASCII = {_normalize_match_text(word) for word in _VN_HINT_WORDS}


def _clean_artist_name(name: str) -> str:
    cleaned = str(name or "").strip()
    cleaned = re.sub(r"\s*-\s*Topic$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" .-_")


def _split_artist_field(artists_value, fallback: str = "") -> list[str]:
    raw = str(artists_value if pd.notna(artists_value) else fallback)
    return [_clean_artist_name(a) for a in raw.split(",") if _clean_artist_name(a)]


def canonical_track_title(track_name: str) -> str:
    """Normalize a title while removing credit-only feat/prod annotations."""
    title = str(track_name or "")
    title = re.sub(
        r"[\(\[][^\(\)\[\]]*?\b(?:feat(?:uring)?|ft\.?|prod\.?|w/)"
        r"[^\(\)\[\]]*[\)\]]",
        " ",
        title,
        flags=re.IGNORECASE,
    )
    title = re.sub(
        r"\s*(?:[-–—|]\s*)?(?:feat(?:uring)?|ft\.?|prod\.?|w/)\s+.*$",
        " ",
        title,
        flags=re.IGNORECASE,
    )
    return _normalize_match_text(title)


def _artist_identity_sets(row: pd.Series) -> tuple[set[str], set[str]]:
    names = {
        _normalize_match_text(name)
        for name in _split_artist_field(
            row.get("artists", row.get("primary_artist", "")),
            fallback=str(row.get("primary_artist", "")),
        )
        if _normalize_match_text(name)
    }
    ids = {
        value.strip()
        for value in str(row.get("artist_ids", "")).split(",")
        if value.strip() and value.strip().lower() not in {"nan", "none"}
    }
    primary_id = str(row.get("primary_artist_id", "")).strip()
    if primary_id and primary_id.lower() not in {"nan", "none"}:
        ids.add(primary_id)
    return names, ids


def _normalized_lyrics(row: pd.Series) -> str:
    for column in ("plain_lyrics", "synced_lyrics", "lyrics"):
        value = row.get(column)
        if isinstance(value, str) and value.strip():
            normalized = _normalize_match_text(value)
            if len(normalized) >= 100:
                return normalized
    return ""


def _base_track_title(track_name: str) -> str:
    title = re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", str(track_name or ""))
    title = re.sub(r"^\s*\d{1,2}\s*[.\-:_]?\s+", "", title)
    return canonical_track_title(title)


def _title_match_evidence(left_name: str, right_name: str) -> tuple[bool, float]:
    left_title = canonical_track_title(left_name)
    right_title = canonical_track_title(right_name)
    if not left_title or not right_title:
        return False, 0.0
    if left_title == right_title:
        return True, 1.0

    left_base = _base_track_title(left_name)
    right_base = _base_track_title(right_name)
    if left_base and left_base == right_base and len(left_base) >= 4:
        return True, 1.0

    ratio = SequenceMatcher(
        None,
        left_title,
        right_title,
        autojunk=False,
    ).ratio()
    left_tokens = set(left_title.split())
    right_tokens = set(right_title.split())
    union = left_tokens | right_tokens
    token_overlap = len(left_tokens & right_tokens) / len(union) if union else 0.0
    return ratio >= 0.88 or token_overlap >= 0.80, max(ratio, token_overlap)


def are_duplicate_song_rows(
    left: pd.Series,
    right: pd.Series,
    audio_similarity: float | None = None,
) -> bool:
    """Return True only when title plus metadata identify the same recording."""
    title_compatible, title_similarity = _title_match_evidence(
        left.get("track_name", ""),
        right.get("track_name", ""),
    )

    left_names, left_ids = _artist_identity_sets(left)
    right_names, right_ids = _artist_identity_sets(right)
    artists_related = bool(left_names & right_names or left_ids & right_ids)

    left_lrclib = str(left.get("lrclib_id", "")).strip()
    right_lrclib = str(right.get("lrclib_id", "")).strip()
    same_lrclib = (
        left_lrclib == right_lrclib
        and left_lrclib.lower() not in {"", "nan", "none"}
    )

    left_duration = pd.to_numeric(
        pd.Series([left.get("track_duration_ms")]), errors="coerce"
    ).iloc[0]
    right_duration = pd.to_numeric(
        pd.Series([right.get("track_duration_ms")]), errors="coerce"
    ).iloc[0]
    duration_delta = (
        abs(float(left_duration) - float(right_duration))
        if pd.notna(left_duration) and pd.notna(right_duration)
        else None
    )
    duration_close = duration_delta is not None and duration_delta <= 4_000
    duration_cross_artist_close = duration_delta is not None and duration_delta <= 10_000

    left_lyrics = _normalized_lyrics(left)
    right_lyrics = _normalized_lyrics(right)
    exact_lyrics = bool(left_lyrics and left_lyrics == right_lyrics)
    fuzzy_lyrics = False
    if left_lyrics and right_lyrics and not exact_lyrics:
        length_ratio = min(len(left_lyrics), len(right_lyrics)) / max(
            len(left_lyrics), len(right_lyrics)
        )
        if length_ratio >= 0.85:
            fuzzy_lyrics = (
                SequenceMatcher(None, left_lyrics, right_lyrics, autojunk=False).ratio()
                >= 0.96
            )

    audio_match = audio_similarity is not None and audio_similarity >= 0.985
    high_audio_match = audio_similarity is not None and audio_similarity >= 0.995
    alias_match = (
        artists_related
        and high_audio_match
        and duration_delta is not None
        and duration_delta <= 4_000
        and (exact_lyrics or fuzzy_lyrics)
    )
    if not title_compatible:
        return alias_match

    if artists_related:
        return (
            same_lrclib
            or exact_lyrics
            or fuzzy_lyrics
            or (
                duration_close
                and audio_match
                and title_similarity >= 0.75
            )
        )
    return same_lrclib or (
        duration_cross_artist_close
        and high_audio_match
        and (
            (title_similarity >= 0.82 and (exact_lyrics or fuzzy_lyrics))
            or title_similarity >= 0.97
        )
    )


def _row_quality_rank(row: pd.Series) -> tuple:
    artists = _split_artist_field(
        row.get("artists", row.get("primary_artist", "")),
        fallback=str(row.get("primary_artist", "")),
    )
    view_count = pd.to_numeric(
        pd.Series([row.get("view_count")]), errors="coerce"
    ).iloc[0]
    metadata_columns = (
        "synced_lyrics",
        "plain_lyrics",
        "lrclib_id",
        "album_id",
        "track_duration_ms",
        "youtube_id",
    )
    metadata_count = sum(
        pd.notna(row.get(column)) and str(row.get(column)).strip().lower() not in {"", "nan"}
        for column in metadata_columns
    )
    title = str(row.get("track_name", ""))
    album = str(row.get("album_name", ""))
    title_key = canonical_track_title(title)
    album_key = canonical_track_title(album)
    single_title_penalty = int(not album_key or album_key != title_key)
    compilation_penalty = int(
        bool(
            re.search(
                r"\b(?:best|collection|tuyen tap|gala|playlist|tap \d+|vol\.?\s*\d+)\b",
                _normalize_match_text(album),
                re.IGNORECASE,
            )
        )
    )
    duration = pd.to_numeric(
        pd.Series([row.get("track_duration_ms")]), errors="coerce"
    ).iloc[0]
    short_penalty = int(pd.notna(duration) and duration < 120_000)
    annotation_penalty = int(
        bool(re.search(r"\b(?:feat(?:uring)?|ft\.?|prod\.?|w/)\b", title, re.I))
    )
    return (
        int(is_non_original_version(title, row.get("album_name", ""))),
        -int(pd.notna(view_count)),
        -float(view_count) if pd.notna(view_count) else 0.0,
        single_title_penalty,
        compilation_penalty,
        short_penalty,
        -len(artists),
        -metadata_count,
        annotation_penalty,
        -float(duration) if pd.notna(duration) else 0.0,
        len(title),
    )


def _merge_artist_credits(winner: pd.Series, members: list[pd.Series]) -> pd.Series:
    merged = winner.copy()
    ordered_pairs: list[tuple[str, str]] = []
    seen_names: set[str] = set()
    for row in [winner, *members]:
        names = _split_artist_field(
            row.get("artists", row.get("primary_artist", "")),
            fallback=str(row.get("primary_artist", "")),
        )
        ids = [
            value.strip()
            for value in str(row.get("artist_ids", "")).split(",")
        ]
        for index, name in enumerate(names):
            normalized = _normalize_match_text(name)
            if not normalized or normalized in seen_names:
                continue
            artist_id = ids[index] if index < len(ids) else ""
            if artist_id.lower() in {"nan", "none"}:
                artist_id = ""
            ordered_pairs.append((name, artist_id))
            seen_names.add(normalized)
    if ordered_pairs:
        merged["artists"] = ", ".join(name for name, _ in ordered_pairs)
        if "artist_ids" in winner.index:
            merged["artist_ids"] = ",".join(artist_id for _, artist_id in ordered_pairs)
    clean_titles = [
        str(row.get("track_name", ""))
        for row in [winner, *members]
        if not re.search(
            r"\b(?:feat(?:uring)?|ft\.?|prod\.?|w/)\b",
            str(row.get("track_name", "")),
            re.IGNORECASE,
        )
    ]
    if clean_titles:
        merged["track_name"] = min(clean_titles, key=len)
    return merged


def _audio_similarity(
    left_track_id,
    right_track_id,
    audio_embeddings: dict[str, list[float]] | None,
) -> float | None:
    if not audio_embeddings:
        return None
    left = audio_embeddings.get(str(left_track_id))
    right = audio_embeddings.get(str(right_track_id))
    if left is None or right is None:
        return None
    left_vector = np.asarray(left, dtype=np.float32)
    right_vector = np.asarray(right, dtype=np.float32)
    denominator = float(np.linalg.norm(left_vector) * np.linalg.norm(right_vector))
    if denominator == 0:
        return None
    return float(np.dot(left_vector, right_vector) / denominator)


def _audio_neighbor_pairs(
    df: pd.DataFrame,
    audio_embeddings: dict[str, list[float]] | None,
    neighbors: int = 6,
    min_similarity: float = 0.995,
) -> list[tuple[int, int, float]]:
    if not audio_embeddings or len(df) < 2:
        return []
    indexes = [
        index
        for index, track_id in df["track_id"].items()
        if str(track_id) in audio_embeddings
    ]
    if len(indexes) < 2:
        return []

    matrix = np.asarray(
        [audio_embeddings[str(df.at[index, "track_id"])] for index in indexes],
        dtype=np.float32,
    )
    neighbor_count = min(neighbors + 1, len(indexes))
    from sklearn.neighbors import NearestNeighbors

    model = NearestNeighbors(
        n_neighbors=neighbor_count,
        metric="cosine",
        algorithm="brute",
        n_jobs=-1,
    )
    model.fit(matrix)
    distances, neighbor_positions = model.kneighbors(matrix)
    pair_scores: dict[tuple[int, int], float] = {}
    for source_position, (row_distances, row_neighbors) in enumerate(
        zip(distances, neighbor_positions)
    ):
        for distance, candidate_position in zip(row_distances, row_neighbors):
            if candidate_position == source_position:
                continue
            similarity = 1.0 - float(distance)
            if similarity < min_similarity:
                continue
            left_index = indexes[source_position]
            right_index = indexes[candidate_position]
            pair = tuple(sorted((left_index, right_index)))
            pair_scores[pair] = max(pair_scores.get(pair, -1.0), similarity)
    return [
        (left_index, right_index, similarity)
        for (left_index, right_index), similarity in pair_scores.items()
    ]


def deduplicate_song_entities(
    df: pd.DataFrame,
    audio_embeddings: dict[str, list[float]] | None = None,
) -> tuple[pd.DataFrame, int]:
    """Collapse duplicate recordings across swapped primary artists/credits."""
    if df.empty or "track_name" not in df.columns:
        return df.copy(), 0

    working = df.copy().reset_index(drop=True)
    working["_entity_title"] = working["track_name"].apply(canonical_track_title)
    indexes = list(working.index)
    parent = {index: index for index in indexes}

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left_index, right_index):
        left_root, right_root = find(left_index), find(right_index)
        if left_root != right_root:
            parent[right_root] = left_root

    for title, group in working.groupby("_entity_title", sort=False, dropna=False):
        if not title or len(group) < 2:
            continue
        group_indexes = list(group.index)
        for position, left_index in enumerate(group_indexes):
            for right_index in group_indexes[position + 1:]:
                similarity = _audio_similarity(
                    working.loc[left_index].get("track_id"),
                    working.loc[right_index].get("track_id"),
                    audio_embeddings,
                )
                if are_duplicate_song_rows(
                    working.loc[left_index],
                    working.loc[right_index],
                    audio_similarity=similarity,
                ):
                    union(left_index, right_index)

    for left_index, right_index, similarity in _audio_neighbor_pairs(
        working,
        audio_embeddings,
    ):
        if find(left_index) == find(right_index):
            continue
        if are_duplicate_song_rows(
            working.loc[left_index],
            working.loc[right_index],
            audio_similarity=similarity,
        ):
            union(left_index, right_index)

    components: dict[int, list[int]] = {}
    for index in indexes:
        components.setdefault(find(index), []).append(index)

    kept_rows: list[pd.Series] = []
    removed = 0
    for component_indexes in components.values():
        component = [
            working.loc[index].drop(labels=["_entity_title"])
            for index in component_indexes
        ]
        if len(component) == 1:
            kept_rows.append(component[0])
            continue
        winner = min(component, key=_row_quality_rank)
        members = [
            row for row in component
            if str(row.get("track_id")) != str(winner.get("track_id"))
        ]
        kept_rows.append(_merge_artist_credits(winner, members))
        removed += len(component) - 1

    result = pd.DataFrame(kept_rows, columns=df.columns)
    return result.reset_index(drop=True), removed


def _apply_keep_mask(df: pd.DataFrame, keep_mask) -> pd.DataFrame:
    if isinstance(keep_mask, pd.Series):
        mask = keep_mask.astype(bool)
    else:
        mask = pd.Series(list(keep_mask), index=df.index, dtype=bool)
    return df.loc[mask].copy()


def has_vn_evidence(text: str) -> bool:
    if not text or not isinstance(text, str):
        return False
    if _VN_UNIQUE_CHARS & set(text):
        return True
    tokens = set(text.lower().split())
    if _VN_HINT_WORDS & tokens:
        return True
    return bool(_VN_HINT_WORDS_ASCII & set(_normalize_match_text(text).split()))


def profanity_stats(text: str) -> tuple[int, int, int]:
    if not text or not isinstance(text, str):
        return 0, 0, 0
    hard_hits = len(_PROFANITY_HARD_RE.findall(text))
    mild_hits = len(_PROFANITY_MILD_RE.findall(text))
    score = hard_hits * 4 + mild_hits
    return hard_hits, mild_hits, score


def is_profane_lyrics(text: str) -> bool:
    hard_hits, mild_hits, score = profanity_stats(text)
    if hard_hits >= 3:
        return True
    if mild_hits >= 10:
        return True
    return score >= 15


def is_profane_title(text: str) -> bool:
    if not text or not isinstance(text, str):
        return False
    return bool(_TITLE_PROFANITY_RE.search(text))


def is_seasonal_track(track_name: str, album_name: str = "", lyrics_text: str = "") -> bool:
    tn_norm = _normalize_match_text(track_name)
    an_norm = _normalize_match_text(album_name)
    lyrics_norm = _normalize_match_text(lyrics_text)

    if re.search(r"\bdau truong\b.*\bmua xuan\b", tn_norm):
        return False

    if (
        _SEASONAL_TET_STRONG_RE.search(tn_norm)
        or _SEASONAL_XUAN_TITLE_CONTEXT_RE.search(tn_norm)
        or _SEASONAL_NOEL_STRONG_RE.search(tn_norm)
        or _SEASONAL_ALBUM_STRONG_RE.search(an_norm)
        or (
            len(_SEASONAL_LYRICS_MARKER_RE.findall(lyrics_norm)) >= 2
            and _SEASONAL_LYRICS_CONTEXT_RE.search(f"{tn_norm} {an_norm}")
        )
    ):
        return True

    return bool(
        _SEASONAL_XUAN_RE.search(tn_norm)
        and (
            _SEASONAL_HINT_RE.search(an_norm)
            or _SEASONAL_LYRICS_STRONG_RE.search(lyrics_norm)
        )
    )


def is_old_genre_track(track_name: str, album_name: str = "", genres_value="") -> bool:
    """Detect explicit old-genre evidence at track/album/genre level."""
    searchable = " ".join(
        _normalize_match_text(value)
        for value in (track_name, album_name, genres_value)
        if value is not None and not pd.isna(value)
    )
    return bool(_OLD_GENRE_TEXT_RE.search(searchable))


def foreign_lyrics_language(text: str) -> str | None:
    """Return a high-confidence non-Vietnamese lyrics language, if any."""
    if not text or not isinstance(text, str):
        return None
    cleaned = re.sub(r"\[[^\]]+\]|♪", " ", text).strip()
    if len(cleaned) < 120:
        return None
    try:
        from langdetect import DetectorFactory, LangDetectException, detect_langs

        DetectorFactory.seed = 0
        languages = detect_langs(cleaned[:6000])
    except Exception:
        return None
    if not languages:
        return None
    top = languages[0]
    vi_probability = next(
        (language.prob for language in languages if language.lang == "vi"),
        0.0,
    )
    if top.lang != "vi" and top.prob >= 0.85 and vi_probability < 0.10:
        return top.lang
    return None


def is_known_foreign_identity_release(
    primary_artist: str,
    album_name: str,
) -> bool:
    artist = _clean_artist_name(primary_artist).lower()
    album = _normalize_match_text(album_name)
    if artist in _FOREIGN_LANGUAGE_ARTIST_BLOCKLIST:
        return True
    return artist == "orange" and album in _KNOWN_ARTIST_COLLISION_ALBUMS


def catalog_quality_rejection_reason(row, audio_record: dict | None = None) -> str | None:
    """Return a high-confidence catalog/audio rejection reason."""
    track_id = str(row.get("track_id", ""))
    artist_id = str(row.get("primary_artist_id", "")).strip()
    title = str(row.get("track_name", ""))
    album = str(row.get("album_name", ""))
    context = f"{title} {album}"
    duration_ms = pd.to_numeric(
        pd.Series([row.get("track_duration_ms")]), errors="coerce"
    ).iloc[0]
    duration_s = float(duration_ms) / 1000 if pd.notna(duration_ms) else None

    if track_id in _KNOWN_WRONG_CONTENT_TRACK_IDS:
        return "verified_wrong_content"
    if artist_id in _LEGACY_IDENTITY_ARTIST_IDS:
        return "legacy_artist_identity"
    if artist_id in _SCORE_COMPOSER_ARTIST_IDS:
        return "soundtrack_score_catalog"
    if _normalize_match_text(album) in _LEGACY_RELEASE_ALBUMS_BY_ARTIST_ID.get(
        artist_id, set()
    ):
        return "legacy_release"
    if _PROGRAM_AUDIO_RE.search(context):
        return "fragment_or_program_excerpt"
    if _FRAGMENT_AUDIO_RE.search(context) and (
        duration_s is None or duration_s < 180
    ):
        return "fragment_or_program_excerpt"

    values = dict(audio_record or {})
    for key in (
        "actual_duration_s",
        "instrumental_probability",
        "voice_probability",
        "yamnet_speech_mean",
        "yamnet_singing_mean",
        "yamnet_music_mean",
        "speech_dominant_fraction",
        "low_music_fraction",
    ):
        if key not in values and key in row:
            values[key] = row.get(key)

    def number(key: str) -> float | None:
        value = pd.to_numeric(pd.Series([values.get(key)]), errors="coerce").iloc[0]
        return float(value) if pd.notna(value) else None

    instrumental = number("instrumental_probability")
    voice = number("voice_probability")
    singing = number("yamnet_singing_mean")
    speech = number("yamnet_speech_mean")
    speech_fraction = number("speech_dominant_fraction")
    music = number("yamnet_music_mean")
    low_music = number("low_music_fraction")
    actual_duration = number("actual_duration_s")
    if actual_duration is not None and actual_duration > MAX_DURATION_MS / 1000:
        return "actual_duration_out_of_range"

    if instrumental is not None and (
        instrumental >= 0.82
        or (
            instrumental >= 0.70
            and singing is not None
            and singing < 0.018
        )
    ):
        return "instrumental_audio"
    if (
        speech_fraction is not None
        and speech_fraction >= 0.30
        and (singing is None or singing < 0.04)
    ) or (
        speech is not None
        and speech >= 0.18
        and (music is None or speech > music * 0.30)
    ):
        return "spoken_audio"
    if (
        low_music is not None
        and low_music >= 0.55
        and (voice is None or voice < 0.65)
    ):
        return "non_music_audio"
    return None


def is_allowed_short_track(row) -> bool:
    """Keep only explicit editorial exceptions below MIN_DURATION_MS."""
    track_id = str(row.get("track_id", "")).strip()
    if track_id in _SHORT_TRACK_ALLOWLIST_IDS:
        return True
    return _normalize_match_text(row.get("track_name", "")) in _SHORT_TRACK_ALLOWLIST_TITLES


def is_non_original_version(track_name: str, album_name: str = "") -> bool:
    """Detect live/remix/cover/lofi/acoustic variants in title or album."""
    title = str(track_name or "")
    album = str(album_name or "")
    title_match = bool(
        _NON_ORIGINAL_STRONG_RE.search(title)
        or _NON_ORIGINAL_CONTEXT_RE.search(title)
    )
    album_match = bool(
        _NON_ORIGINAL_STRONG_RE.search(album)
        or _NON_ORIGINAL_CONTEXT_RE.search(album)
        or re.search(r"\btour(?:\s+\d{4})?\b", album, re.IGNORECASE)
    )
    if album_match and _NON_ORIGINAL_WHITELIST_RE.search(album):
        album_match = False
    return title_match or album_match


def is_low_value_soundtrack_release(
    track_name: str,
    album_name: str,
    artist_names: list[str],
    known_artists: set[str],
    view_count=None,
    hot_source=None,
) -> bool:
    """Reject soundtrack score/deep cuts while preserving verified vocal artists."""
    context = f"{track_name or ''} {album_name or ''}"
    if not _SOUNDTRACK_RE.search(context):
        return False
    normalized_artists = {_clean_artist_name(name).lower() for name in artist_names}
    if normalized_artists & known_artists:
        return False
    views = pd.to_numeric(pd.Series([view_count]), errors="coerce").iloc[0]
    if pd.notna(views) and views >= VIEW_COUNT_MIN:
        return False
    if pd.notna(hot_source) and str(hot_source).strip():
        return False
    return True


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
            # Diacritics can distinguish different people even when stripping
            # produces the same ASCII text (Bích Phương vs Bích Phượng).
            # Only unify this group when an actual ASCII spelling is present.
            if all(_has_vn_diacritics(name) for name, _ in variants):
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
                stripped_names = {_strip_vn(name) for name, _ in variants}
                if len(stripped_names) == 1 and all(
                    _has_vn_diacritics(name) for name, _ in variants
                ):
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
        # Prefer the studio/original row when duplicate title+artist entries
        # include live/remix/acoustic/OST variants.
        df["_variant_rank"] = df.apply(
            lambda row: int(
                is_non_original_version(
                    row.get("track_name", ""),
                    row.get("album_name", ""),
                )
            ),
            axis=1,
        )
        df["_pop_rank"] = (
            pd.to_numeric(df[pop_col], errors="coerce").fillna(-1)
            if pop_col in df.columns
            else -1
        )
        df["_view_rank"] = (
            pd.to_numeric(df["view_count"], errors="coerce").fillna(-1)
            if "view_count" in df.columns
            else -1
        )
        df = df.sort_values(
            ["_variant_rank", "_pop_rank", "_view_rank"],
            ascending=[True, False, False],
            kind="stable",
        )
        df = df.drop_duplicates(subset=["_n", "_a"], keep="first")
        df = df.drop(
            columns=["_n", "_a", "_variant_rank", "_pop_rank", "_view_rank"]
        )
    removed = before - len(df)
    msg = f"[Filter 3] Duplicate name+artist (diacritics-normalized): removed {removed:,} → {len(df):,}"
    print(f"  {msg}")
    report_lines.append(msg)

    # ── 3b. Dedup the same recording across credit/uploader variants ────
    before = len(df)
    audio_embeddings = None
    audio_embeddings_path = PROJECT_ROOT / "data" / "audio_embeddings.json"
    if audio_embeddings_path.exists():
        try:
            with audio_embeddings_path.open(encoding="utf-8") as handle:
                all_audio_embeddings = json.load(handle)
            input_ids = set(df["track_id"].astype(str))
            audio_embeddings = {
                track_id: vector
                for track_id, vector in all_audio_embeddings.items()
                if track_id in input_ids
            }
        except Exception as e:
            print(f"  ⚠️ Audio embeddings unavailable for cross-artist dedup: {e}")
    df, removed = deduplicate_song_entities(df, audio_embeddings=audio_embeddings)
    msg = (
        f"[Filter 3b] Duplicate song entities (feat/credit/primary variants): "
        f"removed {removed:,} → {len(df):,}"
    )
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
        allowed_short = df.apply(is_allowed_short_track, axis=1)
        df = df[~has_dur | in_range | (allowed_short & df[dur_col].lt(MIN_DURATION_MS))]
        removed = before - len(df)
        msg = f"[Filter 4] Duration out of range (<2m30s except allowlist, or >6m): removed {removed:,} → {len(df):,}"
        print(f"  {msg}")
        report_lines.append(msg)

    # ── 5. Vietnamese re-verification (with discovered-artist protection) ─
    before = len(df)
    _discovered_vn_artists: set = set()  # hoisted so Filter 7b can access it
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
        _discovered_vn_artists = discovered_vn_artists  # hoist to outer scope
        print(f"    (discovered {len(discovered_vn_artists):,} VN artists with ≥3 VN-char tracks)")

        keep_mask = []
        recovered = 0
        for _, row in df.iterrows():
            artist_names = _split_artist_field(
                row.get("artists", row.get("primary_artist", "")),
                fallback=str(row.get("primary_artist", "")),
            )
            album_name = str(row.get("album_name", ""))
            # Direct Vietnamese evidence is stronger than the discovered-artist
            # threshold and keeps this stage stable after deduplication.
            if (
                has_vn_evidence(str(row.get("track_name", "")))
                or has_vn_evidence(album_name)
                or any(has_vn_evidence(artist) for artist in artist_names)
            ):
                keep_mask.append(True)
                continue
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
        df = _apply_keep_mask(df, keep_mask)
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
            artist_names = _split_artist_field(
                row.get("artists", row.get("primary_artist", "")),
                fallback=str(row.get("primary_artist", "")),
            )
            artist = ", ".join(artist_names)
            album = str(row.get("album_name", ""))
            is_child = VietnameseDetector.is_children_music(track_name, artist, album)
            keep_mask.append(not is_child)
        df = _apply_keep_mask(df, keep_mask)
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
            primary_artist = _clean_artist_name(str(row.get("primary_artist", "")))
            artist_names = _split_artist_field(
                row.get("artists", primary_artist),
                fallback=primary_artist,
            )
            # Channel detection is only reliable on the primary artist field.
            # Featured artists often include collectives / aliases / uploader-style
            # names and should not remove an otherwise valid track.
            if primary_artist:
                is_channel = VietnameseDetector.is_non_artist_channel(primary_artist)
            else:
                is_channel = any(VietnameseDetector.is_non_artist_channel(a) for a in artist_names)
            keep_mask.append(not is_channel)
        df = _apply_keep_mask(df, keep_mask)
    except ImportError:
        print("  ⚠️ Could not import VietnameseDetector — skipping channel filter")
    removed = before - len(df)
    msg = f"[Filter 6b] Non-artist channels: removed {removed:,} → {len(df):,}"
    print(f"  {msg}")
    report_lines.append(msg)

    # ── 6c. Old-genre artist filter ──────────────────────────────────────
    # Remove old-genre artists and explicit bolero/nhạc vàng/cải lương
    # releases, including releases by otherwise current artists.
    before = len(df)
    try:
        from tools.collect_data import VietnameseDetector
        keep_mask = []
        for _, row in df.iterrows():
            artist_names = _split_artist_field(
                row.get("artists", row.get("primary_artist", "")),
                fallback=str(row.get("primary_artist", "")),
            )
            genre_value = next(
                (
                    row.get(col)
                    for col in ("artist_genres", "spotify_genres", "genres")
                    if col in df.columns and pd.notna(row.get(col))
                ),
                "",
            )
            is_old = (
                VietnameseDetector.is_old_genre_blocked(artist_names)
                or is_old_genre_track(
                    row.get("track_name", ""),
                    row.get("album_name", ""),
                    genre_value,
                )
            )
            keep_mask.append(not is_old)
        df = _apply_keep_mask(df, keep_mask)
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
        keep_original = [
            not is_non_original_version(
                row.get("track_name", ""),
                row.get("album_name", ""),
            )
            for _, row in df.iterrows()
        ]
        df = _apply_keep_mask(df, keep_original)
    except Exception as e:
        print(f"  ⚠️ Variant filter error: {e}")
    removed = before - len(df)
    msg = f"[Filter 6d] Non-original versions removed: {removed:,} → {len(df):,}"
    print(f"  {msg}")
    report_lines.append(msg)

    # ── 6d2. Remove low-value soundtrack scores/deep cuts ──────────────
    # "Original Soundtrack" alone does not make a vocal song a variant.
    # Keep verified artists and hot releases, but reject obscure score rows.
    before = len(df)
    try:
        from tools.collect_data import VietnameseDetector

        known_artists_6d2 = {name.lower() for name in VietnameseDetector.KNOWN_ARTISTS}
        keep_mask_6d2 = []
        for _, row in df.iterrows():
            artist_names = _split_artist_field(
                row.get("artists", row.get("primary_artist", "")),
                fallback=str(row.get("primary_artist", "")),
            )
            is_low_value_score = is_low_value_soundtrack_release(
                row.get("track_name", ""),
                row.get("album_name", ""),
                artist_names,
                known_artists_6d2,
                row.get("view_count"),
                row.get("hot_source"),
            )
            keep_mask_6d2.append(not is_low_value_score)
        df = _apply_keep_mask(df, keep_mask_6d2)
    except Exception as e:
        print(f"  ⚠️ Soundtrack score filter error: {e}")
    removed = before - len(df)
    msg = f"[Filter 6d2] Low-value soundtrack scores removed: {removed:,} → {len(df):,}"
    print(f"  {msg}")
    report_lines.append(msg)

    # ── 6d3. Verified catalog/audio quality gate ─────────────────────────
    # Duration alone is not a rejection signal. Combine identity/release
    # evidence with the offline audio audit for instrumental, speech, and
    # non-music files.
    before = len(df)
    audio_audit_by_id: dict[str, dict] = {}
    audio_audit_path = PROJECT_ROOT / "data" / "catalog_audio_quality_audit.csv"
    if audio_audit_path.exists():
        try:
            audio_audit = pd.read_csv(audio_audit_path)
            audio_audit_by_id = {
                str(row["track_id"]): row.to_dict()
                for _, row in audio_audit.iterrows()
            }
        except Exception as e:
            print(f"  ⚠️ Audio quality audit unavailable: {e}")
    quality_reasons = [
        catalog_quality_rejection_reason(
            row,
            audio_audit_by_id.get(str(row.get("track_id", ""))),
        )
        for _, row in df.iterrows()
    ]
    df = _apply_keep_mask(df, [reason is None for reason in quality_reasons])
    removed = before - len(df)
    msg = f"[Filter 6d3] Verified bad/legacy/audio content: removed {removed:,} → {len(df):,}"
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
            artist_list = _split_artist_field(row.get("artists", artist), fallback=artist)
            is_foreign = VietnameseDetector.is_foreign_blocked(artist_list)
            keep_mask.append(not is_foreign)
        df = _apply_keep_mask(df, keep_mask)
    except ImportError:
        print("  ⚠️ Could not import VietnameseDetector — skipping foreign filter")
    removed = before - len(df)
    msg = f"[Filter 6e] Foreign artists: removed {removed:,} → {len(df):,}"
    print(f"  {msg}")
    report_lines.append(msg)

    # ── 6f. Seasonal music filter (Tết + Giáng Sinh/Noel) ────────────────
    # Removes holiday-specific songs that don't fit everyday listening.
    # Uses stronger title/album patterns plus lyric evidence when available.
    before = len(df)
    try:
        lyrics_col_6f = next(
            (c for c in ["plain_lyrics", "synced_lyrics", "lyrics"] if c in df.columns),
            None,
        )
        mask_seasonal = [
            not is_seasonal_track(
                row.get("track_name", ""),
                row.get("album_name", ""),
                row.get(lyrics_col_6f, "") if lyrics_col_6f else "",
            )
            for _, row in df.iterrows()
        ]
        df = _apply_keep_mask(df, mask_seasonal)
    except Exception as e:
        print(f"  ⚠️ Seasonal filter error: {e}")
    removed = before - len(df)
    msg = f"[Filter 6f] Seasonal music (Tết + Giáng Sinh/Noel): removed {removed:,} → {len(df):,}"
    print(f"  {msg}")
    report_lines.append(msg)

    # ── 6g. Release year filter (≥ 2013, target 9x/GenZ) ────────────────
    # Soft filter: tracks with KNOWN release year < 2013 are dropped.
    # Tracks without a year are KEPT (year will be resolved later via
    # yt-dlp upload_date in Phase 3). Uses 'year' column first, falls back
    # to first 4 chars of 'release_date'.
    before = len(df)
    # Priority: release year metadata, then the source upload date resolved
    # after MP3 download.
    album_year_path = PROJECT_ROOT / "data" / "album_release_year_audit.csv"
    if "album_id" in df.columns and album_year_path.exists():
        try:
            album_years = pd.read_csv(
                album_year_path,
                usecols=["album_id", "resolved_year"],
            ).drop_duplicates("album_id", keep="last")
            year_lookup = dict(
                zip(
                    album_years["album_id"].astype(str),
                    pd.to_numeric(album_years["resolved_year"], errors="coerce"),
                )
            )
            df["album_release_year"] = df["album_id"].astype(str).map(year_lookup)
        except Exception as e:
            print(f"  ⚠️ Album release-year audit unavailable: {e}")
    _year_columns = [
        'year', 'release_date', 'album_release_year', 'upload_year', 'upload_date'
    ]
    _year_col = next((c for c in _year_columns if c in df.columns), None)
    if _year_col:
        def _extract_year(val) -> int | None:
            if pd.isna(val):
                return None
            s = str(val).strip()
            if not s or s in ('nan', 'None', '0', '<NA>'):
                return None
            try:
                return int(s[:4])
            except (ValueError, TypeError):
                return None

        _years = df[_year_col].apply(_extract_year)
        # If a secondary column can fill in NaN years, merge them
        for _fallback in _year_columns:
            if _fallback != _year_col and _fallback in df.columns:
                _fill = df[_fallback].apply(_extract_year)
                _years = _years.where(_years.notna(), _fill)
        _known_old = _years.notna() & (_years < RELEASE_YEAR_MIN)
        _n_unknown = int(_years.isna().sum())
        df = df[~_known_old]
        removed = before - len(df)
        _src = '+'.join(c for c in _year_columns if c in df.columns)
        msg = (
            f"[Filter 6g] Release year < {RELEASE_YEAR_MIN} (cols: {_src}): removed {removed:,} "
            f"({_n_unknown:,} with unknown year kept) → {len(df):,}"
        )
    else:
        removed = 0
        msg = f"[Filter 6g] Release year: no year/release_date/upload_year column — skipped → {len(df):,}"
    print(f"  {msg}")
    report_lines.append(msg)

    # ── 6h. Profanity / vulgar track title filter ────────────────────────
    # Chỉ loại tên bài có từ tục rõ ràng.
    before = len(df)
    try:
        keep_mask_6h = []
        for _, row in df.iterrows():
            tn = str(row.get("track_name", ""))
            keep_mask_6h.append(not is_profane_title(tn))
        df = _apply_keep_mask(df, keep_mask_6h)
    except Exception as e:
        print(f"  ⚠️ Profanity filter error: {e}")
    removed = before - len(df)
    msg = f"[Filter 6h] Profanity in track title: removed {removed:,} → {len(df):,}"
    print(f"  {msg}")
    report_lines.append(msg)

    # ── 6i. Profanity-heavy lyrics filter ────────────────────────────────
    # When lyrics are present, remove tracks with either any hard profanity
    # or very frequent mild slang. This is stricter than title-only checks
    # but still avoids dropping tracks for one casual "vcl"/"đéo".
    lyrics_col_6i = next(
        (c for c in ["plain_lyrics", "synced_lyrics", "lyrics"] if c in df.columns),
        None,
    )
    if lyrics_col_6i:
        before = len(df)
        mask_clean_lyrics = df[lyrics_col_6i].apply(lambda text: not is_profane_lyrics(text))
        df = _apply_keep_mask(df, mask_clean_lyrics)
        removed = before - len(df)
        msg = f"[Filter 6i] Profanity-heavy lyrics: removed {removed:,} → {len(df):,}"
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
        df = _apply_keep_mask(df, keep_mask)
    except ImportError:
        pass
    removed = before - len(df)
    msg = f"[Filter 7] Foreign-dominant tracks: removed {removed:,} → {len(df):,}"
    print(f"  {msg}")
    report_lines.append(msg)

    # ── 7b. Pure-ASCII foreign track filter ──────────────────────────────
    # Catches foreign (Western/Latin) tracks that have NO Vietnamese markers
    # in either track name OR artist name, and whose artist is not a known
    # or discovered Vietnamese artist.
    # Example caught: "Shape of You" by Ed Sheeran (zero VN chars, not known VN artist)
    # Example kept:   "Run Now" by Binz (Binz in KNOWN_ARTISTS → kept)
    before = len(df)
    try:
        from tools.collect_data import VietnameseDetector

        _known_lower_7b = {k.lower() for k in VietnameseDetector.KNOWN_ARTISTS}

        keep_mask_7b = []
        for _, row in df.iterrows():
            tn  = str(row.get('track_name',     ''))
            art = str(row.get('primary_artist', ''))
            # Fast pass: any VN evidence in title or any artist field → keep
            if has_vn_evidence(tn) or has_vn_evidence(art):
                keep_mask_7b.append(True)
                continue
            # Check ALL artists in the comma-separated artists column
            # (catches feat. artists that are known VN artists even if primary isn't)
            all_artists = [
                a.lower()
                for a in _split_artist_field(row.get("artists", art), fallback=art)
            ]
            if any(has_vn_evidence(a) for a in all_artists):
                keep_mask_7b.append(True)
                continue
            if any(a in _discovered_vn_artists or a in _known_lower_7b for a in all_artists):
                keep_mask_7b.append(True)
                continue
            # Pure ASCII + no known/discovered VN artist anywhere → likely foreign
            keep_mask_7b.append(False)
        df = _apply_keep_mask(df, keep_mask_7b)
    except Exception as e:
        print(f"  ⚠️ Pure-ASCII foreign filter error: {e}")
    removed = before - len(df)
    msg = f"[Filter 7b] Pure-ASCII foreign tracks: removed {removed:,} → {len(df):,}"
    print(f"  {msg}")
    report_lines.append(msg)

    # ── 7c. Foreign-language lyrics filter ───────────────────────────────
    # Catches English/foreign songs that slip through because the artist is
    # Vietnamese or mixed-VN collab, but the lyrics themselves show no
    # Vietnamese evidence.
    lyrics_col_7c = next(
        (c for c in ["plain_lyrics", "synced_lyrics", "lyrics"] if c in df.columns),
        None,
    )
    if lyrics_col_7c:
        before = len(df)
        from tools.collect_data import VietnameseDetector

        _known_lower_7c = {k.lower() for k in VietnameseDetector.KNOWN_ARTISTS}

        keep_mask_7c = []
        for _, row in df.iterrows():
            lyrics_text = row.get(lyrics_col_7c, "")
            primary_artist = _clean_artist_name(str(row.get("primary_artist", ""))).lower()
            instrumental = bool(row.get("instrumental", False))
            primary_is_vn = (
                primary_artist in _discovered_vn_artists
                or primary_artist in _known_lower_7c
                or has_vn_evidence(primary_artist)
            )
            foreign_language = foreign_lyrics_language(lyrics_text)
            known_foreign_release = is_known_foreign_identity_release(
                primary_artist,
                row.get("album_name", ""),
            )
            keep_mask_7c.append(
                instrumental
                or foreign_language is None
                or (primary_is_vn and not known_foreign_release)
            )
        df = _apply_keep_mask(df, keep_mask_7c)

        removed = before - len(df)
        msg = f"[Filter 7c] Foreign-language lyrics: removed {removed:,} → {len(df):,}"
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
            'ngọc phước', 'billy100',
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
            'đinh mạnh ninh', 'thái trinh',
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
            'vy jacko', 'mopius', 'mcee blue',
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
    _views_f8 = (
        pd.to_numeric(df["view_count"], errors="coerce")
        if "view_count" in df.columns
        else pd.Series(float("nan"), index=df.index)
    )
    _hot_source_f8 = (
        df["hot_source"].notna()
        if "hot_source" in df.columns
        else pd.Series(False, index=df.index)
    )
    if has_pop:
        df[pop_col] = pd.to_numeric(df[pop_col], errors='coerce')
        all_null = df[pop_col].isna().all()
        df[pop_col] = df[pop_col].fillna(0)
        artist_max_pop = df.groupby(
            df['primary_artist'].astype(str).str.strip().str.lower()
        )[pop_col].max()
    else:
        all_null = True

    _artist_keys_f8 = df["primary_artist"].astype(str).str.strip().str.lower()
    _row_hot_f8 = _hot_source_f8 | (_views_f8 >= VIEW_COUNT_MIN)
    if has_pop:
        _row_hot_f8 |= df[pop_col] >= TRACK_POP_MIN
    artist_has_hot_signal = _row_hot_f8.groupby(_artist_keys_f8).any()

    keep_mask = []
    for _, row in df.iterrows():
        art_lower = str(row.get('primary_artist', '')).strip().lower()
        art_stripped = _norm_f8(art_lower)

        # A) Blocklist check (exact + diacritics-stripped) — ALWAYS runs
        # Current artists only bypass stale manual names; they still face
        # artist- and track-level popularity checks.
        is_current = VietnameseDetector.is_current_artist([art_lower])
        if (
            not is_current
            and (art_lower in _ARTIST_BLOCKLIST or art_stripped in _BLOCKLIST_STRIPPED)
        ):
            keep_mask.append(False)
            continue

        # B) Artist max popularity check — if their BEST track < 15, likely obscure
        #    A hot track on YouTube/chart overrides a low Spotify score.
        if has_pop and not all_null:
            max_pop = artist_max_pop.get(art_lower, 0)
            has_hot_track = bool(artist_has_hot_signal.get(art_lower, False))
            if max_pop < 15 and not has_hot_track:
                keep_mask.append(False)
            else:
                keep_mask.append(True)
        else:
            keep_mask.append(True)

    df = _apply_keep_mask(df, keep_mask)
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

    # ── 8c. Per-track popularity threshold ──────────────────────────────
    # Drops individual tracks with very low Spotify popularity (< TRACK_POP_MIN).
    # Separate from artist-level filter 8B: an artist can pass artist-level
    # quality check but still have many obscure deep-cuts we don't want.
    # Soft filter: only fires when popularity data IS present and non-zero.
    # Tracks from ZingMP3 chart (hot_source flag) are exempt.
    _pop_col_8c = "track_popularity" if "track_popularity" in df.columns else "popularity"
    if _pop_col_8c in df.columns:
        _pop_8c = pd.to_numeric(df[_pop_col_8c], errors='coerce')
        _has_pop_data = _pop_8c.notna().any() and (_pop_8c.fillna(0) > 0).any()
        if _has_pop_data:
            before = len(df)
            _known_low_pop = _pop_8c.notna() & (_pop_8c < TRACK_POP_MIN)
            # A song can be a genuine YouTube hit before Spotify catches up.
            if "view_count" in df.columns:
                _views_for_pop = pd.to_numeric(df["view_count"], errors="coerce")
                _known_low_pop &= ~(_views_for_pop >= VIEW_COUNT_MIN)
            # Exempt tracks flagged as coming from hot chart sources
            if 'hot_source' in df.columns:
                _known_low_pop = _known_low_pop & df['hot_source'].isna()
            df = df[~_known_low_pop]
            removed = before - len(df)
            msg = f"[Filter 8c] Low per-track popularity (< {TRACK_POP_MIN}): removed {removed:,} → {len(df):,}"
            print(f"  {msg}")
            report_lines.append(msg)

    # ── 8d. YouTube view threshold after MP3 download ───────────────────
    # Phase 1 YTMusic rows often lack Spotify popularity. Phase 3 enriches
    # view_count via yt-dlp, so a second filter pass can reject obscure songs.
    if "view_count" in df.columns:
        _views_8d = pd.to_numeric(df["view_count"], errors="coerce")
        _pop_for_views = (
            pd.to_numeric(df[_pop_col_8c], errors="coerce")
            if _pop_col_8c in df.columns
            else pd.Series(float("nan"), index=df.index)
        )
        if _views_8d.notna().any():
            before = len(df)
            _known_low_views = _views_8d.notna() & (_views_8d < VIEW_COUNT_MIN)
            _release_year_8d = pd.Series(float("nan"), index=df.index)
            for column in ("year", "upload_year", "upload_date", "release_date"):
                if column not in df.columns:
                    continue
                parsed_year = df[column].apply(
                    lambda value: (
                            int(match.group(0))
                        if (
                            pd.notna(value)
                            and (match := re.search(r"\b(19|20)\d{2}\b", str(value)))
                        )
                        else None
                    )
                )
                _release_year_8d = _release_year_8d.where(
                    _release_year_8d.notna(),
                    parsed_year,
                )
            _recent_with_momentum = (
                (_release_year_8d >= RECENT_RELEASE_YEAR_MIN)
                & (_views_8d >= RECENT_VIEW_COUNT_MIN)
            )
            _remove_for_views = _known_low_views & ~_recent_with_momentum
            _remove_for_views &= ~(_pop_for_views >= TRACK_POP_MIN)
            if "hot_source" in df.columns:
                _remove_for_views &= df["hot_source"].isna()
            df = df[~_remove_for_views]
            removed = before - len(df)
            msg = (
                f"[Filter 8d] Low YouTube views (< {VIEW_COUNT_MIN:,}, no popularity override): "
                f"removed {removed:,}; releases from {RECENT_RELEASE_YEAR_MIN} keep at "
                f"{RECENT_VIEW_COUNT_MIN:,}+ → {len(df):,}"
            )
            print(f"  {msg}")
            report_lines.append(msg)

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
