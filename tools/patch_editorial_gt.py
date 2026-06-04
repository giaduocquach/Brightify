"""Bước B — Patch editorial GT: sửa quadrant-mismatch + lấp grey/black coverage gap.

Root cause: GT gốc (color_editorial_gt_v1.json) dùng old-hex V-A để gán target_mood,
nhưng engine chuyển sang centroid-hex (ISCC-NBS) từ V16. Kết quả:
  - purple  #800080 old-hex: V=0.558 A=0.840 → Q1 (excited)
  - purple  #9C4F96 centroid: V=0.265 A=0.554 → Q2 (tense)  ← thực tế engine dùng
  - grey/black: target_mood='melancholic' nhưng pool=0 vì query crawl không tìm được

Fix:
  - grey/black: target_mood='sad', pool từ v-pop ballad+tình cảm+bolero playlists ∩ Q3(v5)
  - purple: target_mood='tense', dùng existing tense pool (124 songs)
  - turquoise/white: target_mood='calm', pool từ indie việt ∩ Q4(v5)

Chạy: python -m tools.patch_editorial_gt
Cần: var/runtime/backtest/ground_truth/editorial_playlists_v1.json
      var/runtime/backtest/ground_truth/color_editorial_gt_v1.json
      data/emotion_labels_v5.json (Gemini-relabeled)
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GT_FILE       = "var/runtime/backtest/ground_truth/color_editorial_gt_v1.json"
PLAYLIST_FILE = "var/runtime/backtest/ground_truth/editorial_playlists_v1.json"
V5_FILE       = "data/emotion_labels_v5.json"
CSV_FILE      = "data/vietnamese_music_processed_full.csv"


def _quadrant(v, a):
    if v >= 0.5 and a >= 0.5: return "Q1"
    if v <  0.5 and a >= 0.5: return "Q2"
    if v <  0.5 and a <  0.5: return "Q3"
    return "Q4"


def run():
    import pandas as pd

    playlists = json.load(open(PLAYLIST_FILE))
    v5        = json.load(open(V5_FILE))
    gt        = json.load(open(GT_FILE))
    df        = pd.read_csv(CSV_FILE, usecols=["track_id", "track_name"])
    df["track_id"] = df["track_id"].astype(str)

    idx_to_tid = {i: str(df.iloc[i]["track_id"]) for i in range(len(df))}

    def get_va(idx):
        tid = idx_to_tid.get(idx, "")
        e = v5.get(tid, {})
        return float(e.get("valence", 0.5)), float(e.get("arousal", 0.5))

    def pool_from_playlists(intents, target_q):
        """Songs appearing in named playlists AND in target quadrant per v5."""
        raw = set()
        for p in playlists:
            if p["intent"] in intents:
                for m in p.get("matched", []):
                    raw.add(m["catalog_idx"])
        return sorted(idx for idx in raw if _quadrant(*get_va(idx)) == target_q)

    # Build corrected pools
    q3_pool = pool_from_playlists(
        ["v-pop ballad hay nhất", "nhạc tình cảm việt", "nhạc vàng bolero"], "Q3")
    q4_pool = pool_from_playlists(["nhạc indie việt"], "Q4")

    # Tense pool: already good quality (crawled from rock/rap mood playlists)
    tense_pool = set()
    for info in gt["colors"].values():
        if info.get("target_mood") == "tense":
            tense_pool.update(info.get("relevant", []))
    tense_pool = sorted(tense_pool)

    # Apply patches
    # Keys are old-hex (as stored in GT file)
    patches = {
        "#808080": ("sad",   q3_pool),    # grey   V=0.41/A=0.32 → Q3
        "#000000": ("sad",   q3_pool),    # black  V=0.25/A=0.45 → Q3
        "#800080": ("tense", tense_pool), # purple V=0.27/A=0.55 → Q2 (centroid)
        "#40E0D0": ("calm",  q4_pool),    # turquoise V=0.51/A=0.33 → Q4 (centroid)
        "#FFFFFF": ("calm",  q4_pool),    # white  V=0.59/A=0.17 → Q4
    }

    print("Patching editorial GT (centroid-hex quadrant correction):")
    for hex_c, (new_mood, new_rel) in patches.items():
        old_mood = gt["colors"][hex_c].get("target_mood", "?")
        gt["colors"][hex_c]["target_mood"] = new_mood
        gt["colors"][hex_c]["relevant"]    = new_rel
        gt["colors"][hex_c]["n_relevant"]  = len(new_rel)
        term = gt["colors"][hex_c].get("term", "?")
        print(f"  {hex_c} ({term:10}): {old_mood} → {new_mood}  n_rel={len(new_rel)}")

    gt["validity"] = "external_denoised_v5quadrant_patchB"
    json.dump(gt, open(GT_FILE, "w"), ensure_ascii=False, indent=1)
    print(f"\nSaved → {GT_FILE}")
    print("Run `python -m tools.run_f1_validation` to verify.")


if __name__ == "__main__":
    run()
