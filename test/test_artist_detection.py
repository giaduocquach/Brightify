"""
Test: VietnameseDetector fixes for artist normalization, discovered artists,
and mixed VN+English song handling.

Tests:
1. KNOWN_ARTISTS normalization: "Low G" matches despite spaces
2. Discovered artist support in is_vietnamese()
3. Mixed VN+English songs by known/discovered artists pass
4. All previously working cases still work
5. Full-English songs by non-VN artists still get filtered
"""
import sys
import json
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from tools.collect_data import VietnameseDetector

RESULTS_FILE = Path(__file__).parent / "results_artist_detection.json"

def test_known_artist_normalization():
    """Test that KNOWN_ARTISTS matching works with various formats."""
    results = []
    
    test_cases = [
        # (artist_names, expected, description)
        (["Low G"], True, "Low G with space"),
        (["low g"], True, "low g lowercase with space"),
        (["lowg"], True, "lowg no space"),
        (["LOWG"], True, "LOWG uppercase no space"),
        (["LOW G"], True, "LOW G uppercase with space"),
        (["Sơn Tùng MTP"], True, "Sơn Tùng MTP exact"),
        (["sơn tùng m-tp"], True, "sơn tùng m-tp with hyphen"),
        (["K-ICM"], True, "K-ICM with hyphen"),
        (["kicm"], True, "kicm no hyphen"),
        (["MONO"], True, "MONO uppercase"),
        (["mono"], True, "mono lowercase"),
        (["Grey D"], True, "Grey D with space"),
        (["greyd"], True, "greyd no space"),
        (["Da LAB"], True, "Da LAB"),
        (["B Ray"], True, "B Ray with space"),
        (["Đen Vâu"], True, "Đen Vâu"),
        (["Only C"], True, "Only C with space"),
        (["onlyc"], True, "onlyc no space"),
        (["Mr Siro"], True, "Mr Siro with space"),
        (["Andree Right Hand"], True, "Andree Right Hand"),
        (["RPT MCK"], True, "RPT MCK"),
        (["MYLINA"], True, "MYLINA recent artist"),
        (["Saabirose"], True, "Saabirose recent rapper"),
        (["A1J"], True, "A1J recent singer"),
        (["OLEW"], True, "OLEW recent singer-songwriter"),
        (["Sơn.K"], True, "Sơn.K recent singer"),
        (["Captain Boy"], True, "ATSH Captain Boy"),
        (["CONGB"], True, "ATSH CONGB"),
        (["Cody Nam Võ"], True, "ATSH Cody Nam Võ"),
        (["7dnight"], True, "Rap Việt finalist"),
        (["Blacka"], True, "Rap Việt finalist"),
        (["Khắc Việt"], True, "active 9x-era singer"),
        (["Hồ Quang Hiếu"], True, "active 9x-era singer"),
        (["Haisam"], True, "Hải Sâm ASCII alias"),
        # Non-VN artists should NOT match
        (["Taylor Swift"], False, "Taylor Swift (foreign)"),
        (["BTS"], False, "BTS (foreign)"),
        (["Ed Sheeran"], False, "Ed Sheeran (foreign)"),
        (["Adele"], False, "Adele (foreign)"),
    ]
    
    print("=" * 70)
    print("TEST 1: KNOWN_ARTISTS Normalization")
    print("=" * 70)
    
    passed = 0
    failed = 0
    for artist_names, expected, desc in test_cases:
        result = VietnameseDetector.is_known_artist(artist_names)
        status = "✅" if result == expected else "❌"
        if result != expected:
            failed += 1
            print(f"  {status} {desc}: expected={expected}, got={result}")
        else:
            passed += 1
            print(f"  {status} {desc}")
        results.append({
            "test": "normalization",
            "input": artist_names,
            "expected": expected,
            "actual": result,
            "pass": result == expected,
            "description": desc
        })
    
    print(f"\n  Result: {passed}/{passed+failed} passed")
    return results, failed == 0


def test_current_artists_not_old_genre_blocked():
    """Current artists restored from stale blocklist entries must remain eligible."""
    for artist in [
        "Phương Mỹ Chi", "Mỹ Anh", "Khắc Việt", "Hồ Quang Hiếu",
        "Lê Bảo Bình", "Đình Dũng", "Đinh Tùng Huy", "Huy Vạc",
        "Isaac", "Quốc Thiên", "Song Luân", "Jun Phạm",
        "Ngô Kiến Huy", "Cường Seven", "Phạm Anh Duy",
    ]:
        assert not VietnameseDetector.is_old_genre_blocked([artist]), artist
    assert VietnameseDetector.is_old_genre_blocked(["Chế Linh"])


def test_current_artists_override_stale_non_artist_entries():
    """Show artists previously confused with channels must remain eligible."""
    for artist in ["Captain Boy", "Đỗ Phú Quí", "Blacka", "Nhâm Phương Nam"]:
        assert not VietnameseDetector.is_non_artist_channel(artist), artist


def test_discovered_artists():
    """Test that discovered_artists parameter works in is_vietnamese()."""
    results = []
    
    # Simulate a discovered_artists set (artists with ≥3 VN-char tracks in dataset)
    discovered = {"low g", "16 typh", "wren evans"}
    
    test_cases = [
        # (track, artists, album, discovered, expected_vn, expected_reason_contains, desc)
        ("Love Game", ["Low G"], "", discovered, True, "known_artist", 
         "Low G - Love Game (now matches via fixed KNOWN_ARTISTS)"),
        ("In Love", ["Low G"], "", discovered, True, "known_artist",
         "Low G - In Love (English title, VN artist)"),
        ("Some English Song", ["16 Typh"], "", discovered, True, "discovered_artist",
         "16 Typh - discovered artist (not in static list)"),
        ("Random Track", ["Wren Evans"], "", discovered, True, "discovered_artist",
         "Wren Evans - discovered artist"),
        ("Waiting For You", ["MONO"], "", discovered, True, "known_artist",
         "MONO - Waiting For You (known artist)"),
        ("Bước Qua Đời Nhau", ["Lê Bảo Bình"], "", discovered, True, "vietnamese_chars",
         "Lê Bảo Bình - VN chars in title + artist"),
        # VN chars in track name — always passes regardless of artist
        ("Đại Minh Tinh", ["Low G"], "", None, True, "vietnamese_chars",
         "VN chars in title always passes"),
        # Unknown non-VN artist, English title, no discovered set → should fail
        ("Love Game", ["Some Random Artist"], "", None, False, "not_vietnamese",
         "Unknown artist, English title → correctly rejected"),
    ]
    
    print("\n" + "=" * 70)
    print("TEST 2: Discovered Artists + is_vietnamese()")
    print("=" * 70)
    
    passed = 0
    failed = 0
    for track, artists, album, disc, expected_vn, expected_reason, desc in test_cases:
        is_vn, reason = VietnameseDetector.is_vietnamese(track, artists, album,
                                                          discovered_artists=disc)
        ok = is_vn == expected_vn
        status = "✅" if ok else "❌"
        if not ok:
            failed += 1
            print(f"  {status} {desc}")
            print(f"       expected vn={expected_vn}, got vn={is_vn} reason={reason}")
        else:
            passed += 1
            print(f"  {status} {desc} → {reason}")
        results.append({
            "test": "discovered_artists",
            "track": track,
            "artists": artists,
            "expected_vn": expected_vn,
            "actual_vn": is_vn,
            "reason": reason,
            "pass": ok,
            "description": desc
        })
    
    print(f"\n  Result: {passed}/{passed+failed} passed")
    return results, failed == 0


def test_low_g_full_catalog():
    """Test all Low G tracks from Phase 1 dataset — all should pass detection."""
    results = []
    
    csv_path = PROJECT_ROOT / "checkpoints" / "phase1_spotify.csv"
    if not csv_path.exists():
        print("\n⚠️ Skipping Low G catalog test — phase1_spotify.csv not found")
        return results, True
    
    df = pd.read_csv(str(csv_path))
    low_g = df[df['primary_artist'].str.contains('Low G', case=False, na=False)]
    
    print("\n" + "=" * 70)
    print(f"TEST 3: Low G Full Catalog ({len(low_g)} tracks)")
    print("=" * 70)
    
    # Build discovered artists from dataset (as Phase 2 would)
    artist_vn_count = Counter()
    for _, row in df.iterrows():
        track_name = str(row.get("track_name", ""))
        artist = str(row.get("primary_artist", "")).strip().lower()
        if artist and artist != "nan" and VietnameseDetector.has_vietnamese_chars(track_name):
            artist_vn_count[artist] += 1
    discovered_vn_artists = {a for a, c in artist_vn_count.items() if c >= 3}
    
    print(f"  Discovered VN artists in dataset: {len(discovered_vn_artists)}")
    print(f"  'low g' in discovered: {'low g' in discovered_vn_artists}")
    
    passed = 0
    failed = 0
    for _, row in low_g.iterrows():
        track = str(row['track_name'])
        artists = str(row.get('artists', row['primary_artist'])).split(', ')
        album = str(row.get('album_name', ''))
        
        is_vn, reason = VietnameseDetector.is_vietnamese(
            track, artists, album, discovered_artists=discovered_vn_artists
        )
        
        status = "✅" if is_vn else "❌"
        if not is_vn:
            failed += 1
            print(f"  {status} {track} | {artists} → {reason} (SHOULD BE VN)")
        else:
            passed += 1
            print(f"  {status} {track[:40]:40s} → {reason}")
        
        results.append({
            "test": "low_g_catalog",
            "track": track,
            "artists": artists,
            "is_vn": is_vn,
            "reason": reason,
            "pass": is_vn
        })
    
    print(f"\n  Result: {passed}/{passed+failed} passed (all Low G tracks should be VN)")
    return results, failed == 0


def test_regression_known_cases():
    """Regression test: ensure previously correct detections still work."""
    results = []
    
    test_cases = [
        # VN songs that should always pass
        ("Có Chắc Yêu Là Đây", ["Sơn Tùng M-TP"], True, "VN chars"),
        ("Nơi Này Có Anh", ["Sơn Tùng M-TP"], True, "VN chars"),
        ("Hãy Trao Cho Anh", ["Sơn Tùng M-TP"], True, "VN chars"),
        ("Chạy Ngay Đi", ["Sơn Tùng M-TP"], True, "VN chars"),
        ("Bạc Phận", ["Jack"], True, "VN chars"),
        ("Đưa Em Về Nhà", ["Grey D"], True, "VN chars"),
        ("Bước Qua Đời Nhau", ["Lê Bảo Bình"], True, "VN chars in title"),
        # English-titled songs by VN known artists → should pass
        ("There's No One At All", ["Sơn Tùng M-TP"], True, "known_artist"),
        ("Waiting For You", ["MONO"], True, "known_artist"),
        # Non-VN songs that should fail
        ("Dynamite", ["BTS"], False, "foreign/English"),
        ("Shape of You", ["Ed Sheeran"], False, "English"),
        ("Hello", ["Adele"], False, "English"),
    ]
    
    print("\n" + "=" * 70)
    print("TEST 4: Regression – Known Cases")
    print("=" * 70)
    
    passed = 0
    failed = 0
    for track, artists, expected, desc in test_cases:
        is_vn, reason = VietnameseDetector.is_vietnamese(track, artists)
        ok = is_vn == expected
        status = "✅" if ok else "❌"
        if not ok:
            failed += 1
            print(f"  {status} {artists[0]} - {track}: expected={expected}, got={is_vn} ({reason})")
        else:
            passed += 1
            print(f"  {status} {artists[0]:20s} - {track[:35]:35s} → {reason}")
        results.append({
            "test": "regression",
            "track": track,
            "artists": artists,
            "expected": expected,
            "actual": is_vn,
            "reason": reason,
            "pass": ok
        })
    
    print(f"\n  Result: {passed}/{passed+failed} passed")
    return results, failed == 0


def test_dataset_impact():
    """Measure how many tracks in Phase 1 are affected by the fix."""
    csv_path = PROJECT_ROOT / "checkpoints" / "phase1_spotify.csv"
    if not csv_path.exists():
        print("\n⚠️ Skipping dataset impact test — phase1_spotify.csv not found")
        return [], True
    
    df = pd.read_csv(str(csv_path))
    
    print("\n" + "=" * 70)
    print(f"TEST 5: Dataset Impact Analysis ({len(df):,} tracks)")
    print("=" * 70)
    
    # Build discovered artists
    artist_vn_count = Counter()
    for _, row in df.iterrows():
        track_name = str(row.get("track_name", ""))
        artist = str(row.get("primary_artist", "")).strip().lower()
        if artist and artist != "nan" and VietnameseDetector.has_vietnamese_chars(track_name):
            artist_vn_count[artist] += 1
    discovered_vn_artists = {a for a, c in artist_vn_count.items() if c >= 3}
    
    # Compare old vs new detection
    changes = {"newly_accepted": 0, "newly_rejected": 0, "unchanged_accept": 0, "unchanged_reject": 0}
    newly_accepted_tracks = []
    
    for _, row in df.iterrows():
        track = str(row.get("track_name", ""))
        artists = str(row.get("artists", row.get("primary_artist", ""))).split(", ")
        album = str(row.get("album_name", ""))
        
        # Old detection (without discovered artists, old normalization is gone but
        # we can test with vs without discovered_artists)
        is_vn_base, _ = VietnameseDetector.is_vietnamese(track, artists, album)
        is_vn_new, reason = VietnameseDetector.is_vietnamese(
            track, artists, album, discovered_artists=discovered_vn_artists
        )
        
        if not is_vn_base and is_vn_new:
            changes["newly_accepted"] += 1
            if len(newly_accepted_tracks) < 30:
                newly_accepted_tracks.append({
                    "track": track,
                    "artist": str(row.get("primary_artist", "")),
                    "reason": reason
                })
        elif is_vn_base and not is_vn_new:
            changes["newly_rejected"] += 1
        elif is_vn_base:
            changes["unchanged_accept"] += 1
        else:
            changes["unchanged_reject"] += 1
    
    print(f"  Unchanged accepted:  {changes['unchanged_accept']:,}")
    print(f"  Unchanged rejected:  {changes['unchanged_reject']:,}")
    print(f"  Newly accepted:      {changes['newly_accepted']:,}")
    print(f"  Newly rejected:      {changes['newly_rejected']:,}")
    
    if newly_accepted_tracks:
        print(f"\n  Sample newly accepted tracks (by discovered-artist):")
        for t in newly_accepted_tracks[:15]:
            print(f"    {t['artist']:20s} - {t['track'][:35]:35s} → {t['reason']}")
    
    return [changes], True  # langdetect is non-deterministic, small fluctuations expected


def main():
    all_results = []
    all_passed = True
    
    r, ok = test_known_artist_normalization()
    all_results.extend(r)
    all_passed &= ok
    
    r, ok = test_discovered_artists()
    all_results.extend(r)
    all_passed &= ok
    
    r, ok = test_low_g_full_catalog()
    all_results.extend(r)
    all_passed &= ok
    
    r, ok = test_regression_known_cases()
    all_results.extend(r)
    all_passed &= ok
    
    r, ok = test_dataset_impact()
    all_results.extend(r)
    all_passed &= ok
    
    # Save results
    with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nResults saved: {RESULTS_FILE}")
    
    print("\n" + "=" * 70)
    if all_passed:
        print("  ✅ ALL TESTS PASSED")
    else:
        print("  ❌ SOME TESTS FAILED")
    print("=" * 70)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
