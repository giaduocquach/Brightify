"""V22 — Patch editorial GT: quadrant-mismatch fix, NO Gemini-quadrant filter.

V21 audit + negative control (2026-06-04) revealed:
  Old patch_editorial_gt.py used `pool ∩ Q3/Q4(v5-Gemini)` to build GT
  for grey/black/turquoise/white → circular (Kriegeskorte 2009 double-dipping).
  Shuffle-test: Macro Qprec barely changes with random song_va → tautological.

V22 fix:
  - grey/black: raw playlist membership from "v-pop ballad + tình cảm + bolero"
    WITHOUT any Gemini/V-A filter. These playlists are human-curated for sad/
    melancholic mood by human editors. Raw membership = truly external GT.
  - turquoise/white: NO reliable external GT exists without Gemini filter
    (indie playlists are genre, not mood-specific). Set n_rel=0 → skip.
    Honest > noisy circular pool.
  - purple: keep existing tense pool (from rock/rap mood crawl in
    color_editorial_gt.py — not v5-filtered, genuinely external).
  - All other colours (red/orange/yellow/pink/green/blue/brown): unchanged
    (came from color_editorial_gt.py mood-crawl, always external).

Metric note (V22):
  Qprec = retrieval-quadrant precision = TAUTOLOGICAL for V-A-based retrieval
  (proven by shuffle-test). Qprec becomes "internal consistency diagnostic" only.
  P@k (fraction of top-k in raw playlist GT) is the honest external metric.

Chạy: python -m tools.patch_editorial_gt
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GT_FILE       = "var/runtime/backtest/ground_truth/color_editorial_gt_v1.json"
PLAYLIST_FILE = "var/runtime/backtest/ground_truth/editorial_playlists_v1.json"
CSV_FILE      = "data/vietnamese_music_processed_full.csv"


def run():
    import pandas as pd

    playlists = json.load(open(PLAYLIST_FILE))
    gt        = json.load(open(GT_FILE))
    df        = pd.read_csv(CSV_FILE, usecols=["track_id", "track_name"])
    df["track_id"] = df["track_id"].astype(str)

    def pool_raw(intents, min_playlists=1):
        """Raw playlist membership — NO V-A/Gemini filter.
        Optionally require song to appear in ≥ min_playlists for de-noising.
        This is the only valid external GT: human editorial curation.
        """
        song_pl_count: dict[int, int] = {}
        for p in playlists:
            if p["intent"] in intents:
                for m in p.get("matched", []):
                    idx = m["catalog_idx"]
                    song_pl_count[idx] = song_pl_count.get(idx, 0) + 1
        return sorted(idx for idx, cnt in song_pl_count.items() if cnt >= min_playlists)

    # SAD/MELANCHOLIC: ballad + tình cảm + bolero — human-curated sad music.
    # Raw membership, no Gemini filter. De-noise: require ≥1 playlist (lenient,
    # since these intents are already mood-specific not genre-general).
    sad_pool_raw = pool_raw(
        ["v-pop ballad hay nhất", "nhạc tình cảm việt", "nhạc vàng bolero"],
        min_playlists=1)

    # TENSE: take from existing GT (came from color_editorial_gt.py crawl
    # of "nhạc rock việt" / "nhạc rap việt căng" — external, not v5-filtered).
    tense_pool = set()
    for info in gt["colors"].values():
        if info.get("target_mood") == "tense":
            tense_pool.update(info.get("relevant", []))
    tense_pool = sorted(tense_pool)

    # Patches to apply — only colours that were previously circular or wrong
    patches = {
        "#808080": ("sad",   sad_pool_raw),  # grey   → raw ballad pool, no Gemini filter
        "#000000": ("sad",   sad_pool_raw),  # black  → raw ballad pool, no Gemini filter
        "#800080": ("tense", tense_pool),    # purple → centroid Q2, external tense crawl (OK)
        "#40E0D0": ("calm",  []),            # turquoise → n_rel=0 (no external GT without circular filter)
        "#FFFFFF": ("calm",  []),            # white     → n_rel=0 (same reason)
    }

    print("V22 — Patching editorial GT (NO Gemini-quadrant filter):")
    for hex_c, (new_mood, new_rel) in patches.items():
        old_mood   = gt["colors"][hex_c].get("target_mood", "?")
        old_n      = len(gt["colors"][hex_c].get("relevant", []))
        gt["colors"][hex_c]["target_mood"] = new_mood
        gt["colors"][hex_c]["relevant"]    = new_rel
        gt["colors"][hex_c]["n_relevant"]  = len(new_rel)
        term = gt["colors"][hex_c].get("term", "?")
        note = "(RAW, no Gemini filter)" if new_rel else "(n_rel=0: no clean external GT)"
        print(f"  {hex_c} ({term:10}): {old_mood:12}→{new_mood:8} n_rel {old_n:3}→{len(new_rel):4}  {note}")

    gt["validity"] = "external_raw_playlist_v22"
    gt["v22_note"] = (
        "grey/black use raw human-curated playlist membership (ballad+tình_cảm+bolero), "
        "NO Gemini-quadrant filter. turquoise/white have n_rel=0 (no clean external GT). "
        "Qprec is tautological for V-A retrieval (proven by shuffle-test). "
        "P@k against raw playlist GT is the honest external metric."
    )
    json.dump(gt, open(GT_FILE, "w"), ensure_ascii=False, indent=1)
    print(f"\nSaved → {GT_FILE}")
    print(f"  grey/black pool: {len(sad_pool_raw)} songs (raw, no Gemini filter)")
    print(f"  turquoise/white: n_rel=0 (honest: no external GT)")
    print("Run `python -m tools.run_f1_validation` to verify.")


if __name__ == "__main__":
    run()
