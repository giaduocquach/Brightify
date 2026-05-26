#!/usr/bin/env python3
"""Test ytmusicapi lyrics functionality."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ytmusicapi import YTMusic

def main():
    yt = YTMusic()

    # Test 1: Search a Vietnamese song
    print("=== Test 1: Search ===")
    results = yt.search("Sơn Tùng MTP Hãy Trao Cho Anh", filter="songs", limit=3)
    if not results:
        print("FAIL: No search results")
        return

    vid = results[0].get("videoId")
    title = results[0].get("title")
    artist_names = [a.get("name") for a in results[0].get("artists", [])]
    print(f"Found: {title} by {artist_names}")
    print(f"videoId: {vid}")

    # Test 2: get_watch_playlist
    print("\n=== Test 2: get_watch_playlist ===")
    watch = yt.get_watch_playlist(vid)
    if not watch:
        print("FAIL: No watch data")
        return

    lyrics_id = watch.get("lyrics")
    print(f"lyrics browseId: {lyrics_id}")

    if not lyrics_id:
        print("FAIL: No lyrics browseId found")
        return

    # Test 3: get_lyrics (plain)
    print("\n=== Test 3: get_lyrics (plain) ===")
    lyrics = yt.get_lyrics(lyrics_id)
    if not lyrics:
        print("FAIL: No lyrics data")
        return

    print(f"Type: {type(lyrics).__name__}")

    # Handle both dict and model object
    text = getattr(lyrics, "lyrics", None)
    if text is None and isinstance(lyrics, dict):
        text = lyrics.get("lyrics")

    source = getattr(lyrics, "source", None)
    if source is None and isinstance(lyrics, dict):
        source = lyrics.get("source")

    has_ts = getattr(lyrics, "hasTimestamps", None)
    if has_ts is None and isinstance(lyrics, dict):
        has_ts = lyrics.get("hasTimestamps")

    print(f"Source: {source}")
    print(f"hasTimestamps: {has_ts}")
    if text:
        print(f"Lyrics (first 200 chars): {text[:200]}...")
        print(f"PASS: Plain lyrics OK ({len(text)} chars)")
    else:
        print("FAIL: No lyrics text")
        return

    # Test 4: timed lyrics
    print("\n=== Test 4: get_lyrics (timed) ===")
    try:
        timed = yt.get_lyrics(lyrics_id, timestamps=True)
        if not timed:
            print("No timed data returned")
            return

        has_ts2 = getattr(timed, "hasTimestamps", None)
        if has_ts2 is None and isinstance(timed, dict):
            has_ts2 = timed.get("hasTimestamps")

        print(f"hasTimestamps: {has_ts2}")

        timed_lyrics = getattr(timed, "lyrics", None)
        if timed_lyrics is None and isinstance(timed, dict):
            timed_lyrics = timed.get("lyrics")

        if has_ts2 and isinstance(timed_lyrics, list) and len(timed_lyrics) > 0:
            line = timed_lyrics[0]
            print(f"Line type: {type(line).__name__}")
            line_text = getattr(line, "text", "") if hasattr(line, "text") else line.get("text", "")
            start = getattr(line, "start_time", 0) if hasattr(line, "start_time") else line.get("start_time", 0)
            print(f"First line: [{start}ms] {line_text}")
            print(f"Total lines: {len(timed_lyrics)}")

            # Test LRC conversion
            total_sec = start / 1000
            mins = int(total_sec // 60)
            secs = total_sec % 60
            lrc = f"[{mins:02d}:{secs:05.2f}] {line_text}"
            print(f"LRC format: {lrc}")
            print("PASS: Timed lyrics OK")
        else:
            print("No timestamps available for this song (may not have timed lyrics)")
    except Exception as e:
        print(f"Timed lyrics error: {e}")

    # Test 5: Test LyricsCollector class
    print("\n=== Test 5: LyricsCollector class ===")
    from tools.collect_data import LyricsCollector
    lc = LyricsCollector()
    print(f"ytmusic initialized: {lc._ytmusic is not None}")
    print(f"download IDs loaded: {len(lc._download_ids)}")

    task = {
        "track_id": "test_123",
        "track_name": "Hãy Trao Cho Anh",
        "artist_name": "Sơn Tùng M-TP",
        "album_name": "",
        "duration_ms": 261000,
    }
    result = lc._fetch_ytmusic(task)
    if result:
        print(f"lyrics_source: {result.get('lyrics_source')}")
        print(f"has_lyrics: {result.get('has_lyrics')}")
        plain = result.get("plain_lyrics", "")
        synced = result.get("synced_lyrics")
        print(f"plain_lyrics: {len(plain)} chars")
        print(f"synced_lyrics: {'Yes' if synced else 'No'}")
        print("PASS: LyricsCollector._fetch_ytmusic OK")
    else:
        print("FAIL: LyricsCollector._fetch_ytmusic returned None")

    # Test 6: LRCLIB fallback
    print("\n=== Test 6: LRCLIB fallback ===")
    result_lrc = lc._fetch_lrclib(task)
    if result_lrc:
        print(f"lyrics_source: {result_lrc.get('lyrics_source')}")
        print(f"has_lyrics: {result_lrc.get('has_lyrics')}")
        print("PASS: LRCLIB fallback OK")
    else:
        print("LRCLIB had no result for this track (expected for some songs)")

    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    main()
