"""
Test ytmusicapi: search accuracy, metadata richness, Vietnamese music coverage
"""
import time
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Test queries
TEST_QUERIES = [
    {"name": "Có Chắc Yêu Là Đây", "artist": "Sơn Tùng M-TP"},
    {"name": "Đừng Làm Trái Tim Anh Đau", "artist": "Sơn Tùng M-TP"},
    {"name": "Nơi Này Có Anh", "artist": "Sơn Tùng M-TP"},
    {"name": "Hãy Trao Cho Anh", "artist": "Sơn Tùng M-TP"},
    {"name": "Chạy Ngay Đi", "artist": "Sơn Tùng M-TP"},
    {"name": "Anh Đã OK", "artist": "Binz"},
    {"name": "Chiều Hôm Ấy", "artist": "JaykiiA"},
    {"name": "Tình Đơn Phương", "artist": "Mỹ Tâm"},
    {"name": "Waiting For You", "artist": "Mono"},
    {"name": "Lạc Trôi", "artist": "Sơn Tùng M-TP"},
]


def test_search_accuracy():
    """Test ytmusicapi search accuracy for Vietnamese songs"""
    print("=" * 70)
    print("TEST 1: ytmusicapi search accuracy")
    print("=" * 70)

    from ytmusicapi import YTMusic
    ytm = YTMusic()

    results = []
    for track in TEST_QUERIES:
        query = f"{track['artist']} {track['name']}"
        print(f"\n  Searching: {query}")

        t0 = time.time()
        try:
            search_results = ytm.search(query, filter="songs", limit=5)
            elapsed = time.time() - t0

            if search_results:
                top = search_results[0]
                # Check if top result matches
                top_title = top.get("title", "").lower()
                top_artists = " ".join(a.get("name", "") for a in top.get("artists", [])).lower()
                expected_name = track["name"].lower()

                name_match = expected_name in top_title or top_title in expected_name
                result = {
                    "query": query,
                    "found": True,
                    "exact_match": name_match,
                    "top_title": top.get("title"),
                    "top_artists": [a.get("name") for a in top.get("artists", [])],
                    "top_video_id": top.get("videoId"),
                    "top_duration": top.get("duration"),
                    "top_album": top.get("album", {}).get("name") if top.get("album") else None,
                    "total_results": len(search_results),
                    "search_time_s": round(elapsed, 2),
                }
                match_str = "✅ MATCH" if name_match else "⚠️ CLOSE"
                print(f"    {match_str}: {result['top_title']} by {result['top_artists']}")
                print(f"       VideoID: {result['top_video_id']}, Duration: {result['top_duration']}")
                print(f"       Album: {result['top_album']}, Results: {result['total_results']}")
            else:
                result = {"query": query, "found": False, "search_time_s": round(elapsed, 2)}
                print(f"    ❌ No results")
        except Exception as e:
            result = {"query": query, "found": False, "error": str(e)}
            print(f"    ❌ Error: {e}")

        results.append(result)
        time.sleep(0.5)  # Rate limit

    return results


def test_metadata_richness():
    """Test what metadata ytmusicapi provides"""
    print("\n" + "=" * 70)
    print("TEST 2: ytmusicapi metadata richness")
    print("=" * 70)

    from ytmusicapi import YTMusic
    ytm = YTMusic()

    track = TEST_QUERIES[0]
    query = f"{track['artist']} {track['name']}"

    results = {}
    try:
        # Song search
        songs = ytm.search(query, filter="songs", limit=1)
        if songs:
            song = songs[0]
            results["song_fields"] = list(song.keys())
            results["song_sample"] = {k: str(v)[:100] for k, v in song.items()}
            print(f"  Song fields: {results['song_fields']}")

            # Get song details if videoId available
            vid = song.get("videoId")
            if vid:
                try:
                    details = ytm.get_song(vid)
                    if details:
                        vd = details.get("videoDetails", {})
                        results["song_detail_fields"] = list(vd.keys()) if vd else []
                        results["song_detail_sample"] = {k: str(v)[:100] for k, v in vd.items()} if vd else {}
                        print(f"  Song detail fields: {results['song_detail_fields']}")
                except Exception as e:
                    results["song_detail_error"] = str(e)

        # Album search
        albums = ytm.search(query, filter="albums", limit=1)
        if albums:
            results["album_fields"] = list(albums[0].keys())
            print(f"  Album fields: {results['album_fields']}")

        # Artist search
        artists = ytm.search(track["artist"], filter="artists", limit=1)
        if artists:
            results["artist_fields"] = list(artists[0].keys())
            print(f"  Artist fields: {results['artist_fields']}")

    except Exception as e:
        results["error"] = str(e)
        print(f"  ❌ Error: {e}")

    return results


def test_vietnamese_browsing():
    """Test browsing Vietnamese music charts/playlists"""
    print("\n" + "=" * 70)
    print("TEST 3: ytmusicapi Vietnamese browsing")
    print("=" * 70)

    from ytmusicapi import YTMusic
    ytm = YTMusic()

    results = {}
    try:
        # Search for Vietnamese playlists
        vn_queries = ["nhạc việt hot", "v-pop 2025", "nhạc trẻ hay nhất"]
        for q in vn_queries:
            playlists = ytm.search(q, filter="playlists", limit=3)
            plist_info = []
            for pl in playlists:
                plist_info.append({
                    "title": pl.get("title"),
                    "author": pl.get("author"),
                    "itemCount": pl.get("itemCount"),
                })
            results[q] = plist_info
            print(f"\n  '{q}': {len(playlists)} playlists")
            for p in plist_info:
                print(f"    - {p['title']} by {p['author']} ({p['itemCount']} items)")

    except Exception as e:
        results["error"] = str(e)
        print(f"  ❌ Error: {e}")

    return results


def main():
    print("🔧 ytmusicapi Test Suite")
    try:
        from ytmusicapi import YTMusic
        print(f"   Version: {__import__('ytmusicapi').__version__}")
    except ImportError:
        print("   ❌ ytmusicapi not installed!")
        return

    all_results = {}
    all_results["search_accuracy"] = test_search_accuracy()
    all_results["metadata_richness"] = test_metadata_richness()
    all_results["vietnamese_browsing"] = test_vietnamese_browsing()

    # Save results
    out_path = PROJECT_ROOT / "test" / "results_ytmusicapi.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\n📁 Results saved to {out_path}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY: ytmusicapi")
    print("=" * 70)
    search = all_results["search_accuracy"]
    found = sum(1 for r in search if r.get("found"))
    matched = sum(1 for r in search if r.get("exact_match"))
    print(f"  Found:        {found}/{len(search)} tracks")
    print(f"  Exact match:  {matched}/{len(search)} tracks")
    avg_time = sum(r.get("search_time_s", 0) for r in search) / max(len(search), 1)
    print(f"  Avg search:   {avg_time:.2f}s")
    print(f"  Metadata fields: {len(all_results.get('metadata_richness', {}).get('song_fields', []))}")


if __name__ == "__main__":
    main()
