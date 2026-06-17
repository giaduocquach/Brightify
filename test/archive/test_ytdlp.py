"""
Test yt-dlp: download chất lượng, tốc độ, format support
Sử dụng bài nhạc Việt đã biết trên YouTube
"""
import time
import os
import sys
import json
import tempfile
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Sample Vietnamese tracks to test (Spotify ID → YouTube search query)
TEST_TRACKS = [
    {"name": "Có Chắc Yêu Là Đây", "artist": "Sơn Tùng M-TP", "spotify_id": "5cn5oHiXJTLiuthgbgfkMh"},
    {"name": "Đừng Làm Trái Tim Anh Đau", "artist": "Sơn Tùng M-TP", "spotify_id": "4Fqqd9zumXOR8nlwWC8rnb"},
    {"name": "Nơi Này Có Anh", "artist": "Sơn Tùng M-TP", "spotify_id": "2QHkpDKkOPmgwZZYgN19dh"},
]


def test_search_and_info():
    """Test yt-dlp search + metadata extraction (no download)"""
    print("=" * 70)
    print("TEST 1: yt-dlp search & metadata extraction")
    print("=" * 70)

    import yt_dlp

    results = []
    for track in TEST_TRACKS:
        query = f"{track['artist']} - {track['name']}"
        print(f"\n  Searching: {query}")

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "default_search": "ytsearch3",
            "noplaylist": True,
        }

        t0 = time.time()
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch:{query}", download=False)
                elapsed = time.time() - t0

                if info and info.get("entries"):
                    entry = info["entries"][0]
                    result = {
                        "query": query,
                        "found": True,
                        "title": entry.get("title"),
                        "duration": entry.get("duration"),
                        "youtube_id": entry.get("id"),
                        "uploader": entry.get("uploader"),
                        "view_count": entry.get("view_count"),
                        "search_time_s": round(elapsed, 2),
                        "formats_count": len(entry.get("formats", [])),
                        "has_audio": any(f.get("acodec") != "none" for f in entry.get("formats", [])),
                    }
                    print(f"    ✅ Found: {result['title']} ({result['duration']}s)")
                    print(f"       YouTube ID: {result['youtube_id']}, Views: {result['view_count']}")
                    print(f"       Search time: {result['search_time_s']}s, Formats: {result['formats_count']}")
                else:
                    result = {"query": query, "found": False, "search_time_s": round(elapsed, 2)}
                    print(f"    ❌ Not found ({elapsed:.2f}s)")
        except Exception as e:
            result = {"query": query, "found": False, "error": str(e)}
            print(f"    ❌ Error: {e}")

        results.append(result)

    return results


def test_download_quality():
    """Test yt-dlp download with different quality settings"""
    print("\n" + "=" * 70)
    print("TEST 2: yt-dlp download quality comparison")
    print("=" * 70)

    import yt_dlp

    track = TEST_TRACKS[0]
    query = f"{track['artist']} - {track['name']}"

    quality_configs = [
        {"name": "mp3_128k", "opts": {"format": "bestaudio", "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "128"}]}},
        {"name": "mp3_192k", "opts": {"format": "bestaudio", "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]}},
        {"name": "mp3_320k", "opts": {"format": "bestaudio", "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"}]}},
    ]

    results = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for config in quality_configs:
            outpath = os.path.join(tmpdir, f"test_{config['name']}")

            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "default_search": "ytsearch",
                "noplaylist": True,
                "outtmpl": outpath + ".%(ext)s",
                **config["opts"],
            }

            print(f"\n  Downloading [{config['name']}]: {query}")
            t0 = time.time()
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([f"ytsearch:{query}"])
                elapsed = time.time() - t0

                # Find the output file
                out_files = [f for f in os.listdir(tmpdir) if f.startswith(f"test_{config['name']}")]
                if out_files:
                    filepath = os.path.join(tmpdir, out_files[0])
                    size_mb = os.path.getsize(filepath) / (1024 * 1024)
                    result = {
                        "quality": config["name"],
                        "success": True,
                        "file_size_mb": round(size_mb, 2),
                        "download_time_s": round(elapsed, 2),
                        "filename": out_files[0],
                    }
                    print(f"    ✅ {size_mb:.2f} MB in {elapsed:.2f}s")
                else:
                    result = {"quality": config["name"], "success": False, "error": "no output file"}
                    print(f"    ❌ No output file")
            except Exception as e:
                result = {"quality": config["name"], "success": False, "error": str(e)}
                print(f"    ❌ Error: {e}")

            results.append(result)

    return results


def test_existing_files():
    """Test analysis of existing music files in music_files/"""
    print("\n" + "=" * 70)
    print("TEST 3: Analyze existing music files")
    print("=" * 70)

    music_dir = PROJECT_ROOT / "music_files"
    mp3_files = sorted(music_dir.glob("*.mp3"))[:5]

    results = []
    for mp3 in mp3_files:
        size_mb = mp3.stat().st_size / (1024 * 1024)
        result = {
            "file": mp3.name,
            "size_mb": round(size_mb, 2),
        }

        # Try to get duration using ffprobe
        try:
            out = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(mp3)],
                capture_output=True, text=True, timeout=10,
            )
            if out.returncode == 0:
                info = json.loads(out.stdout)
                fmt = info.get("format", {})
                result["duration_s"] = round(float(fmt.get("duration", 0)), 1)
                result["bitrate_kbps"] = round(int(fmt.get("bit_rate", 0)) / 1000)
                result["format"] = fmt.get("format_name")
        except Exception:
            pass

        results.append(result)
        print(f"  {mp3.name}: {result.get('size_mb')}MB, {result.get('duration_s', '?')}s, {result.get('bitrate_kbps', '?')}kbps")

    return results


def main():
    print("🔧 yt-dlp Test Suite")
    print(f"   Version check:")
    os.system("yt-dlp --version 2>/dev/null")
    print()

    all_results = {}
    all_results["search_metadata"] = test_search_and_info()
    all_results["download_quality"] = test_download_quality()
    all_results["existing_files"] = test_existing_files()

    # Save results
    out_path = PROJECT_ROOT / "test" / "results_ytdlp.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\n📁 Results saved to {out_path}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY: yt-dlp")
    print("=" * 70)
    search_ok = sum(1 for r in all_results["search_metadata"] if r.get("found"))
    print(f"  Search:   {search_ok}/{len(all_results['search_metadata'])} tracks found")
    dl_ok = sum(1 for r in all_results["download_quality"] if r.get("success"))
    print(f"  Download: {dl_ok}/{len(all_results['download_quality'])} quality levels OK")
    avg_time = sum(r.get("search_time_s", 0) for r in all_results["search_metadata"]) / max(len(all_results["search_metadata"]), 1)
    print(f"  Avg search time: {avg_time:.2f}s")


if __name__ == "__main__":
    main()
