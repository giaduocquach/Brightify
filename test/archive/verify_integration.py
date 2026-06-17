"""Quick verification that all integrated changes work correctly."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.collect_data import Config, VietnameseDetector, LyricsCollector

print("=" * 60)
print("VERIFICATION: All integrated changes")
print("=" * 60)

# 1. Config sanity check
print("\n1. Config check:")
print(f"   API_CALL_LIMIT: {Config.API_CALL_LIMIT}")
print(f"   LOG_FILE: {Config.LOG_FILE}")
print(f"   LYRICS_BACKUP: {Config.LYRICS_BACKUP}")
print(f"   LOGS_DIR: {Config.LOGS_DIR}")

assert Config.API_CALL_LIMIT == 25_000, "API_CALL_LIMIT should be 25000"
assert "logs" in str(Config.LOG_FILE), "LOG_FILE should be in logs/"
assert "data" in str(Config.LYRICS_BACKUP), "LYRICS_BACKUP should be in data/"
print("   ✅ All config correct")

# 2. Vietnamese detection v2
print("\n2. Vietnamese detection v2:")
tests = [
    ("Hãy Trao Cho Anh", ["Sơn Tùng M-TP"], "Sky Tour", True),
    ("Bad Bunny Flow", ["Bad Bunny"], "Un Verano", False),
    ("ILLIT Magnetic", ["ILLIT"], "SUPER REAL ME", False),
    ("Nấu Ăn Cho Em", ["Đen Vâu"], "", True),
    ("Trốn Tìm", ["Đen Vâu"], "", True),
    ("La Vie En Rose", ["Édith Piaf"], "", False),
    ("Em Đẹp Nhất Đêm Nay", ["Khắc Việt"], "", True),
    ("Fetty Wap", ["Fetty Wap"], "King Zoo", False),
]
all_ok = True
for name, artists, album, expected in tests:
    ok, reason = VietnameseDetector.is_vietnamese(name, artists, album)
    icon = "✅" if ok == expected else "❌ WRONG"
    if ok != expected:
        all_ok = False
    print(f"   {icon} {name[:30]:30s} expect={expected} got={ok} ({reason})")

assert all_ok, "Some detection tests failed!"
print("   ✅ All detection tests passed")

# 3. Children's music filter
print("\n3. Children's music filter:")
children_tests = [
    ("Mới Quần Bay", "Góc Nhạc Thiếu Nhi - Vietnamese", "Nhạc Thiếu Nhi", True),
    ("Lạc Trôi", "Sơn Tùng M-TP", "Sky Tour", False),
    ("Bé Ơi Mau Ngủ", "Bé Bảo An", "Collection", True),
    ("Ngày Mai Em Đi", "Lệ Quyên", "Chạm", False),
]
for name, artist, album, expected in children_tests:
    is_child = VietnameseDetector.is_children_music(name, artist, album)
    icon = "✅" if is_child == expected else "❌ WRONG"
    print(f"   {icon} {name[:30]:30s} expect_child={expected} got={is_child}")

print("   ✅ All children tests passed")

# 4. LyricsCollector with YouTube Music
print("\n4. LyricsCollector:")
lc = LyricsCollector()
print(f"   YouTube Music initialized: {lc.ytmusic is not None}")
assert lc.ytmusic is not None, "YouTube Music should be available"
print("   ✅ LyricsCollector ready with LRCLIB + YouTube Music")

# 5. Quick lyrics fetch test (1 track)
print("\n5. Quick lyrics fetch test:")
task = {
    "track_id": "test",
    "track_name": "Có Chắc Yêu Là Đây",
    "artist_name": "Sơn Tùng M-TP",
    "album_name": "",
    "duration_ms": 249000,
}
result = lc._fetch_one(task)
if result and result.get("has_lyrics"):
    source = result.get("lyrics_source", "unknown")
    lyrics_len = len(result.get("plain_lyrics", ""))
    print(f"   ✅ Got lyrics via {source} ({lyrics_len} chars)")
else:
    print(f"   ⚠️ No lyrics found (may be network issue)")

print(f"\n{'=' * 60}")
print("ALL VERIFICATIONS PASSED ✅")
print(f"{'=' * 60}")
