"""
Test improved Vietnamese filter:
1. Stronger VietnameseDetector (fix common_words, better langdetect)
2. Children's music filter
3. Compare old vs new filter on actual dataset

KHÔNG chỉnh sửa hệ thống — chỉ test offline trên phase2_filtered.csv / phase3_lyrics.csv
"""
import re
import sys
import json
import time
from pathlib import Path
from collections import Counter

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

CHECKPOINT_DIR = PROJECT_ROOT / "checkpoints"

# ══════════════════════════════════════════════════════════════════════════════
# IMPROVED VIETNAMESE DETECTOR  (proposed v2)
# ══════════════════════════════════════════════════════════════════════════════

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
    (0xAC00, 0xD7AF), (0x1100, 0x11FF),
    (0x3040, 0x309F), (0x30A0, 0x30FF),
    (0x4E00, 0x9FFF), (0x0E00, 0x0E7F),
]

# ── OLD common words (v1) — too loose, catches non-VN ────────────────────
COMMON_VN_WORDS_V1 = re.compile(
    r'\b(?:'
    r'anh|em|yêu|thương|nhớ|buồn|vui|tình|đời|người|'
    r'trái tim|hạnh phúc|cô đơn|chia tay|quên|mưa|nắng|'
    r'giấc mơ|sài gòn|hà nội|việt nam|bạn|mẹ|đường|'
    r'lòng|tay|môi|mắt|đêm|ngày|trăng|sao|biển|'
    r'xin|cho|của|với|không|còn|một|những|và|là|'
    r'nơi|đây|hãy|như|sẽ|được|đến|đã|rồi|thôi'
    r')\b',
    re.IGNORECASE | re.UNICODE
)

# ── NEW common words (v2) — tighter, removed ambiguous words ─────────────
# Removed: anh, em, cho, la, sao, con, là, và, như, một, với, còn
# These are too common in Portuguese/French/Spanish/Tagalog/etc.
# Kept: words with VN diacritics are inherently safe, plus multi-character VN-only words
COMMON_VN_WORDS_V2 = re.compile(
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

# Require at least 2 matches to confirm via common words (v2 strict mode)
COMMON_VN_WORDS_V2_ALL = re.compile(
    r'\b(?:'
    r'yêu|thương|nhớ|buồn|vui|tình|đời|người|'
    r'trái tim|hạnh phúc|cô đơn|chia tay|quên|mưa|nắng|'
    r'giấc mơ|sài gòn|hà nội|việt nam|bạn|mẹ|đường|'
    r'lòng|mắt|đêm|ngày|trăng|biển|'
    r'xin|không|những|được|đến|đã|rồi|thôi|'
    r'nơi|đây|hãy|phải|cùng|lắm|thật|nữa|mình|'
    r'cũng|vẫn|chưa|bao giờ|luôn|từng|khóc|xinh|đẹp'
    r')\b',
    re.IGNORECASE | re.UNICODE
)

# ── Known artists — expanded from collect_data.py ──────────────────────
# (imported at runtime from collect_data.py to stay in sync)

# ── Children's music patterns ────────────────────────────────────────────
CHILDREN_ARTIST_PATTERNS = re.compile(
    r'(?:'
    r'Thiếu Nhi|Nhi Đồng|Nhạc Thiếu Nhi|'
    r'Góc Nhạc Thiếu Nhi|'
    r'Bé [A-ZÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬĐÊẾỀỂỄỆÔỐỒỔỖỘƠỚỜỞỠỢƯỨỪỬỮỰ][a-zàáảãạăắằẳẵặâấầẩẫậđêếềểễệôốồổỗộơớờởỡợưứừửữự]+'
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
    r'Bé Ơi|Bé Yêu Ơi'
    r')',
    re.IGNORECASE | re.UNICODE
)


def has_foreign_chars(text: str) -> bool:
    count = 0
    for ch in text:
        cp = ord(ch)
        for rng_start, rng_end in FOREIGN_CHAR_RANGES:
            if rng_start <= cp <= rng_end:
                count += 1
                if count >= 2:
                    return True
                break
    return False


def has_vn_unique_chars(text: str) -> bool:
    return bool(VIETNAMESE_UNIQUE_CHARS & set(text))


def has_vn_diacritics(text: str) -> bool:
    return bool(VIETNAMESE_ALL_DIACRITICS & set(text))


def is_children_music(track_name: str, artist: str, album: str) -> bool:
    """Detect children's music (nhạc thiếu nhi)"""
    if CHILDREN_ARTIST_PATTERNS.search(artist):
        return True
    if CHILDREN_ALBUM_PATTERNS.search(album):
        # Double check: album has children keyword, but artist might be a normal artist
        # who has ONE song on a children compilation
        if CHILDREN_TRACK_PATTERNS.search(track_name):
            return True
        # If artist also looks like children's artist, definitely children
        if CHILDREN_ARTIST_PATTERNS.search(artist):
            return True
        # Album keyword alone catches compilations — flag it
        return True
    if CHILDREN_TRACK_PATTERNS.search(track_name):
        return True
    return False


def is_vietnamese_v2(track_name: str, artist_names: list, album_name: str = "") -> tuple:
    """
    Improved Vietnamese detection v2:
    - Tightened common_words (removed ambiguous words)
    - langdetect on combined_text (not just track_name)
    - Require ≥2 method passes for borderline cases
    """
    combined_text = f"{track_name} {' '.join(artist_names)} {album_name}"

    # 0. Reject foreign chars (Korean/Japanese/Chinese/Thai)
    if has_foreign_chars(combined_text):
        if not has_vn_unique_chars(combined_text):
            return False, "foreign_chars"

    # 1. Vietnamese unique chars (strongest signal)
    if has_vn_unique_chars(combined_text):
        return True, "vietnamese_chars"

    # 2. Known artist (import from collect_data)
    try:
        from tools.collect_data import VietnameseDetector
        if VietnameseDetector.is_known_artist(artist_names):
            return True, "known_artist"
    except ImportError:
        pass

    # 3. Multiple VN diacritics (≥3 for higher confidence)
    vn_diac_count = sum(1 for c in combined_text if c in VIETNAMESE_ALL_DIACRITICS)
    if vn_diac_count >= 3:
        return True, "diacritics_multiple"

    # 4. Common VN words (tightened v2) — require match in track_name
    has_common = bool(COMMON_VN_WORDS_V2.search(track_name.lower()))
    if has_common:
        # Additional signal check: also need ≥1 VN diacritic OR ≥2 word matches
        matches = COMMON_VN_WORDS_V2_ALL.findall(combined_text.lower())
        if len(matches) >= 2 or vn_diac_count >= 1:
            return True, "common_words_confirmed"

    # 5. langdetect on combined_text (expanded from just track_name)
    try:
        from langdetect import detect
        if len(combined_text.strip()) >= 8:
            lang = detect(combined_text)
            if lang == "vi":
                return True, "langdetect"
    except Exception:
        pass

    # 6. langdetect on track_name alone (fallback)
    try:
        from langdetect import detect
        if len(track_name.strip()) >= 10:
            lang = detect(track_name)
            if lang == "vi":
                # Need secondary confirmation for track_name-only langdetect
                if has_common or vn_diac_count >= 1:
                    return True, "langdetect_confirmed"
    except Exception:
        pass

    return False, "not_vietnamese"


# ══════════════════════════════════════════════════════════════════════════════
# TESTS
# ══════════════════════════════════════════════════════════════════════════════

def test_children_filter():
    """Test 1: Children's music detection on actual dataset"""
    print("=" * 70)
    print("TEST 1: Children's Music Filter")
    print("=" * 70)

    csv_path = CHECKPOINT_DIR / "phase4_lyrics.csv"
    if not csv_path.exists():
        csv_path = CHECKPOINT_DIR / "phase2_filtered.csv"
    if not csv_path.exists():
        print("  ⚠️ No checkpoint CSV found, skipping")
        return None
    df = pd.read_csv(csv_path)
    print(f"  Dataset: {len(df):,} tracks")

    children = []
    for _, row in df.iterrows():
        name = str(row.get("track_name", ""))
        artist = str(row.get("primary_artist", ""))
        album = str(row.get("album_name", ""))
        if is_children_music(name, artist, album):
            children.append({"name": name, "artist": artist, "album": album})

    df_children = pd.DataFrame(children)
    print(f"  Children's music detected: {len(children):,} ({100*len(children)/len(df):.1f}%)")
    if len(df_children) > 0:
        print(f"\n  Top artists:")
        for a, c in Counter(df_children["artist"]).most_common(15):
            print(f"    {a}: {c}")
        print(f"\n  Sample tracks:")
        for _, r in df_children.head(10).iterrows():
            print(f"    {r['name'][:40]:40s} | {r['artist'][:25]:25s} | {r['album'][:25]}")

    return {"count": len(children), "pct": round(100*len(children)/len(df), 2)}


def test_filter_comparison():
    """Test 2: Old vs New Vietnamese detector on actual dataset"""
    print("\n" + "=" * 70)
    print("TEST 2: Old vs New Vietnamese Detector")
    print("=" * 70)

    csv_path = CHECKPOINT_DIR / "phase4_lyrics.csv"
    if not csv_path.exists():
        csv_path = CHECKPOINT_DIR / "phase2_filtered.csv"
    if not csv_path.exists():
        print("  ⚠️ No checkpoint CSV found, skipping")
        return None
    df = pd.read_csv(csv_path)
    print(f"  Dataset: {len(df):,} tracks")

    try:
        from tools.collect_data import VietnameseDetector
    except ImportError:
        print("  ⚠️ Cannot import VietnameseDetector")
        return None

    old_pass = 0
    old_fail = 0
    new_pass = 0
    new_fail = 0
    disagreements = []

    t0 = time.time()
    for i, (_, row) in enumerate(df.iterrows()):
        name = str(row.get("track_name", ""))
        artist_str = str(row.get("artists", row.get("primary_artist", "")))
        artist_names = [a.strip() for a in artist_str.split(",")]
        album = str(row.get("album_name", ""))

        old_vn, old_reason = VietnameseDetector.is_vietnamese(name, artist_names, album)
        new_vn, new_reason = is_vietnamese_v2(name, artist_names, album)

        if old_vn:
            old_pass += 1
        else:
            old_fail += 1
        if new_vn:
            new_pass += 1
        else:
            new_fail += 1

        if old_vn != new_vn:
            disagreements.append({
                "name": name,
                "artist": artist_str,
                "album": album,
                "old": f"{'PASS' if old_vn else 'FAIL'}({old_reason})",
                "new": f"{'PASS' if new_vn else 'FAIL'}({new_reason})",
            })

        if (i + 1) % 5000 == 0:
            print(f"  ... processed {i+1:,} tracks")

    elapsed = time.time() - t0
    print(f"  Processing time: {elapsed:.1f}s")
    print(f"\n  Old detector: {old_pass:,} pass, {old_fail:,} fail")
    print(f"  New detector: {new_pass:,} pass, {new_fail:,} fail")
    print(f"  Disagreements: {len(disagreements):,}")

    newly_rejected = [d for d in disagreements if "PASS" in d["old"] and "FAIL" in d["new"]]
    newly_accepted = [d for d in disagreements if "FAIL" in d["old"] and "PASS" in d["new"]]

    print(f"\n  Newly REJECTED by v2 (old=PASS, new=FAIL): {len(newly_rejected)}")
    for d in newly_rejected[:20]:
        print(f"    ❌ {d['name'][:35]:35s} | {d['artist'][:25]:25s} | old={d['old']}, new={d['new']}")

    print(f"\n  Newly ACCEPTED by v2 (old=FAIL, new=PASS): {len(newly_accepted)}")
    for d in newly_accepted[:10]:
        print(f"    ✅ {d['name'][:35]:35s} | {d['artist'][:25]:25s} | old={d['old']}, new={d['new']}")

    return {
        "old_pass": old_pass, "old_fail": old_fail,
        "new_pass": new_pass, "new_fail": new_fail,
        "disagreements": len(disagreements),
        "newly_rejected": len(newly_rejected),
        "newly_accepted": len(newly_accepted),
        "sample_rejected": newly_rejected[:30],
    }


def test_known_false_positives():
    """Test 3: Known foreign songs that should be rejected"""
    print("\n" + "=" * 70)
    print("TEST 3: Known False Positives — foreign songs that should be rejected")
    print("=" * 70)

    known_foreign = [
        {"name": "Trap Queen", "artists": ["Fetty Wap"], "album": "Fetty Wap"},
        {"name": "Ojos Tristes", "artists": ["Selena Gomez"], "album": "I Said I Love You First"},
        {"name": "Rastro de Pó", "artists": ["Tagua Tagua"], "album": "Rastro de Pó"},
        {"name": "Conga Mongo", "artists": ["AMÉMÉ"], "album": "Power"},
        {"name": "L'île au trésor", "artists": ["Les Enfoirés"], "album": "2026"},
        {"name": "Preludio: Altiplano", "artists": ["Ricardo Montaner"], "album": "Una Mañana"},
        {"name": "Shape of You", "artists": ["Ed Sheeran"], "album": "Divide"},
        {"name": "Despacito", "artists": ["Luis Fonsi"], "album": "Vida"},
        {"name": "Con Calma", "artists": ["Daddy Yankee"], "album": "Con Calma"},
        {"name": "La Bamba", "artists": ["Ritchie Valens"], "album": "La Bamba"},
    ]

    known_vietnamese = [
        {"name": "TET VIET NAM", "artists": ["VAMP"], "album": "TET VIET NAM"},
        {"name": "Dau Tinh Sau", "artists": ["Thanh Hà"], "album": "Uoc Hen"},
        {"name": "Canh Buom Do Tham", "artists": ["Do Bao"], "album": "Canh Cung"},
        {"name": "Khong Yeu Xin Dung Noi", "artists": ["Droppy"], "album": ""},
        {"name": "Nho Em Thoi", "artists": ["Tony Funkhouse"], "album": "Nho Em Thoi"},
        {"name": "Anh Oi O Lai", "artists": ["Chi Pu"], "album": "Anh Oi O Lai"},
        {"name": "Phuong Hong", "artists": ["Than-Tuong"], "album": "Ban Nhac"},
        {"name": "Waiting For You", "artists": ["MONO"], "album": "22"},
        {"name": "FEVER", "artists": ["Coldzy"], "album": "MEDICINE"},
    ]

    try:
        from tools.collect_data import VietnameseDetector
    except ImportError:
        print("  ⚠️ Cannot import VietnameseDetector")
        return None

    print("\n  Foreign songs (should be REJECTED):")
    old_correct_foreign = 0
    new_correct_foreign = 0
    for track in known_foreign:
        old_vn, old_r = VietnameseDetector.is_vietnamese(track["name"], track["artists"], track.get("album", ""))
        new_vn, new_r = is_vietnamese_v2(track["name"], track["artists"], track.get("album", ""))
        old_ok = "✅" if not old_vn else "❌"
        new_ok = "✅" if not new_vn else "❌"
        if not old_vn:
            old_correct_foreign += 1
        if not new_vn:
            new_correct_foreign += 1
        print(f"    Old:{old_ok}({old_r:20s}) New:{new_ok}({new_r:25s}) | {track['name'][:30]} - {track['artists'][0]}")

    print(f"\n  Vietnamese songs (should be ACCEPTED):")
    old_correct_vn = 0
    new_correct_vn = 0
    for track in known_vietnamese:
        old_vn, old_r = VietnameseDetector.is_vietnamese(track["name"], track["artists"], track.get("album", ""))
        new_vn, new_r = is_vietnamese_v2(track["name"], track["artists"], track.get("album", ""))
        old_ok = "✅" if old_vn else "❌"
        new_ok = "✅" if new_vn else "❌"
        if old_vn:
            old_correct_vn += 1
        if new_vn:
            new_correct_vn += 1
        print(f"    Old:{old_ok}({old_r:20s}) New:{new_ok}({new_r:25s}) | {track['name'][:30]} - {track['artists'][0]}")

    total_tests = len(known_foreign) + len(known_vietnamese)
    old_total = old_correct_foreign + old_correct_vn
    new_total = new_correct_foreign + new_correct_vn
    print(f"\n  📊 Accuracy:")
    print(f"     Old detector: {old_total}/{total_tests} ({100*old_total/total_tests:.1f}%)")
    print(f"     New detector: {new_total}/{total_tests} ({100*new_total/total_tests:.1f}%)")

    return {"old_accuracy": old_total, "new_accuracy": new_total, "total": total_tests}


if __name__ == "__main__":
    all_results = {}

    r1 = test_children_filter()
    all_results["children_filter"] = r1

    r2 = test_filter_comparison()
    all_results["filter_comparison"] = r2

    r3 = test_known_false_positives()
    all_results["false_positives"] = r3

    output_path = Path(__file__).parent / "results_filter_v2.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n✅ Results saved: {output_path}")
