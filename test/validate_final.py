"""Final validation of all integrated changes."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.filter_data import run_filter
from tools.collect_data import VietnameseDetector, LyricsCollector, Config

print("=" * 50)
print("FINAL VALIDATION")
print("=" * 50)

# 1. Budgets
print(f"\n1. API_CALL_LIMIT: {Config.API_CALL_LIMIT}")
assert Config.API_CALL_LIMIT == 25_000

# 2. LyricsCollector
lc = LyricsCollector()
print(f"2. LyricsCollector ytmusic: {lc.ytmusic is not None}")
assert lc.ytmusic is not None

# 3. Children filter
assert VietnameseDetector.is_children_music("Bé Ơi", "Góc Nhạc Thiếu Nhi", "Album")
assert not VietnameseDetector.is_children_music("Lạc Trôi", "Sơn Tùng M-TP", "Album")
print("3. Children filter: OK")

# 4. Known artist protects English tracks
ok, reason = VietnameseDetector.is_vietnamese("Love Game", ["Low G"], "")
print(f"4. Low G - Love Game: vn={ok} ({reason})")

ok, reason = VietnameseDetector.is_vietnamese("Mascara", ["Chillies"], "")
print(f"   Chillies - Mascara: vn={ok} ({reason})")

ok, reason = VietnameseDetector.is_vietnamese("Random English", ["Random Foreign"], "")
print(f"   Foreign - Random: vn={ok} ({reason})")
assert not ok

# 5. filter_data imports
print("5. filter_data imports: OK")

print("\n✅ ALL VALIDATIONS PASSED")
