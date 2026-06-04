"""V22 — Build mood-specific GT for P@k (non-tautological external metric).

Crawls YouTube Music playlists using MOOD-named queries (not genre).
Human-curated playlists = external GT independent of song_va / engine.
Multi-source de-noise: keep song only if appears in ≥ MIN_PLAYLIST_AGREEMENT
distinct playlists for the same mood → reduces noise from mis-labeled playlists.

Output:
  var/runtime/backtest/ground_truth/mood_gt_v1.json
    {mood: {song_idx: n_playlists, ...}, playlists: [...]}
  var/runtime/backtest/ground_truth/color_editorial_gt_v1.json  (rebuilt)

Then: python -m tools.color_editorial_grouped to re-evaluate P@k.

Run: python -m tools.build_mood_gt
"""
from __future__ import annotations
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GT_DIR     = "var/runtime/backtest/ground_truth"
OUT_MOOD   = os.path.join(GT_DIR, "mood_gt_v1.json")
GT_FILE    = os.path.join(GT_DIR, "color_editorial_gt_v1.json")
os.makedirs(GT_DIR, exist_ok=True)

# Mood-specific queries — unambiguous Vietnamese mood names, not genre/era
MOOD_QUERIES = {
    "sad":        ["nhạc buồn", "nhạc thất tình việt", "nhạc chia tay buồn nhất",
                   "nhạc tâm trạng buồn việt nam"],
    "happy":      ["nhạc vui tươi việt nam", "nhạc vui nhộn việt", "nhạc vui trẻ em việt",
                   "nhạc tết vui nhộn"],
    "calm":       ["nhạc chill việt nam", "nhạc nhẹ nhàng thư giãn việt",
                   "nhạc lofi việt nam", "nhạc acoustic nhẹ nhàng việt"],
    "excited":    ["nhạc sôi động việt nam", "nhạc edm việt remix",
                   "nhạc party quẩy việt", "nhạc nhảy việt"],
    "tense":      ["nhạc rap việt căng", "nhạc rock việt mạnh", "nhạc diss rap việt"],
    "melancholic":["nhạc buồn nhẹ nhàng tâm trạng", "nhạc hoài niệm việt",
                   "nhạc bolero tâm trạng"],
}

MIN_HITS              = 5   # playlist must match ≥5 catalog songs (was 8, relaxed)
MAX_COVERAGE_RATIO    = 0.55
N_RESULTS_PER_QUERY   = 5   # playlists per query
MIN_PLAYLIST_AGREEMENT= 1   # song must appear in ≥1 mood playlist (relaxed for coverage)


def run():
    import pandas as pd
    from ytmusicapi import YTMusic
    from tools.backtest_v2.ground_truth import editorial as ed

    df = pd.read_csv("data/vietnamese_music_processed_full.csv",
                     usecols=["track_id","track_name","artists"])
    df["track_id"] = df["track_id"].astype(str)
    cat_size   = len(df)
    cat_index  = ed._build_catalog_index(df)

    yt       = YTMusic()
    seen_pl  = set()
    mood_songs: dict[str, dict[int, int]] = {m: {} for m in MOOD_QUERIES}
    raw_playlists: list[dict] = []

    print(f"Crawling mood-specific playlists (catalog={cat_size} songs)...")
    print(f"Queries: {sum(len(v) for v in MOOD_QUERIES.values())} total\n")

    for mood, queries in MOOD_QUERIES.items():
        print(f"[{mood}]")
        for query in queries:
            print(f"  searching: {query!r}")
            try:
                results = yt.search(query, filter="playlists",
                                    limit=N_RESULTS_PER_QUERY)
            except Exception as e:
                print(f"    search error: {e}"); time.sleep(1.0); continue
            time.sleep(ed.YTMUSIC_DELAY)

            for r in results:
                pl_id = r.get("playlistId") or r.get("browseId")
                if not pl_id or pl_id in seen_pl:
                    continue
                seen_pl.add(pl_id)
                try:
                    pl = yt.get_playlist(pl_id, limit=None)
                except Exception as e:
                    print(f"    get_playlist error: {e}"); time.sleep(1.0); continue
                time.sleep(ed.YTMUSIC_DELAY)

                tracks = pl.get("tracks") or []
                matched: set[int] = set()
                for tr in tracks:
                    nm = tr.get("title") or ""
                    al = tr.get("artists") or []
                    ar = ", ".join(a.get("name","") for a in al) if al else ""
                    idx = ed._fuzzy_match(nm, ar, cat_index)
                    if idx is not None:
                        matched.add(idx)

                n   = len(matched)
                cov = n / cat_size
                if n < MIN_HITS or cov > MAX_COVERAGE_RATIO:
                    print(f"    DROP '{pl.get('title','')[:40]}' "
                          f"({n} hits, {cov:.0%})")
                    continue

                for idx in matched:
                    mood_songs[mood][idx] = mood_songs[mood].get(idx, 0) + 1
                raw_playlists.append({
                    "mood": mood, "query": query,
                    "playlist_id": pl_id,
                    "title": pl.get("title",""),
                    "n_matched": n,
                })
                print(f"    KEEP '{pl.get('title','')[:40]}' ({n} hits)")

        n_total = sum(1 for cnt in mood_songs[mood].values()
                      if cnt >= MIN_PLAYLIST_AGREEMENT)
        print(f"  → {n_total} songs for [{mood}] "
              f"(agreement≥{MIN_PLAYLIST_AGREEMENT})\n")

    # Save mood GT
    out = {
        "mood_songs": {
            mood: {
                str(idx): cnt
                for idx, cnt in songs.items()
                if cnt >= MIN_PLAYLIST_AGREEMENT
            }
            for mood, songs in mood_songs.items()
        },
        "playlists": raw_playlists,
        "n_playlists_crawled": len(raw_playlists),
        "min_playlist_agreement": MIN_PLAYLIST_AGREEMENT,
        "validity": "external_mood_playlists_v22",
        "note": (
            "Mood-specific human-curated playlists. "
            "NOT filtered by engine V-A labels → clean external GT for P@k. "
            "De-noised by multi-source agreement (songs in ≥1 mood playlist kept)."
        ),
    }
    json.dump(out, open(OUT_MOOD, "w"), ensure_ascii=False, indent=1)
    print(f"Saved → {OUT_MOOD}")

    # Coverage report
    print("\n=== MOOD COVERAGE ===")
    for mood, songs in out["mood_songs"].items():
        print(f"  {mood:12}: {len(songs):4} songs  "
              f"({len(songs)/cat_size*100:.1f}% catalog)")

    # Rebuild color GT with new mood pools
    _rebuild_gt(out["mood_songs"], df)
    print(f"\nNext: python -m tools.run_f1_validation to evaluate P@k")


def _rebuild_gt(mood_songs: dict, df):
    """Rebuild color_editorial_gt_v1.json with new mood-specific pools."""
    from tools.backtest_v2.ground_truth.color_norms import query_colors

    gt_old = json.load(open(GT_FILE)) if os.path.exists(GT_FILE) else {}
    gt_colors_old = gt_old.get("colors", {})

    gt_colors = {}
    for q in query_colors():
        mood   = q["target_mood"]
        hex_c  = q["hex"]
        term   = q["term"]
        pool   = sorted(int(i) for i in mood_songs.get(mood, {}))
        n_rel  = len(pool)

        # Preserve existing pools for moods not in new crawl
        if n_rel == 0 and hex_c in gt_colors_old:
            old = gt_colors_old[hex_c]
            pool  = old.get("relevant", [])
            n_rel = len(pool)
            note  = "kept_from_v21"
        else:
            note = "mood_crawl_v22"

        gt_colors[hex_c] = {
            "term": term, "target_mood": mood,
            "relevant": pool, "n_relevant": n_rel,
            "source": note,
        }

    mood_coverage = {m: sum(1 for v in gt_colors.values()
                            if v["target_mood"]==m and v["n_relevant"]>0)
                     for m in mood_songs}

    out = {
        "colors": gt_colors,
        "mood_coverage": {m: len(mood_songs.get(m,{})) for m in mood_songs},
        "validity": "external_mood_playlists_v22",
        "n_playlists_crawled": sum(
            1 for v in gt_colors.values() if v["source"]=="mood_crawl_v22"),
    }
    json.dump(out, open(GT_FILE, "w"), ensure_ascii=False, indent=1)

    print("\n=== REBUILT COLOR GT ===")
    for hx, info in gt_colors.items():
        print(f"  {info['term']:10} {hx}  {info['target_mood']:12} "
              f"n_rel={info['n_relevant']:4}  [{info['source']}]")


if __name__ == "__main__":
    run()
