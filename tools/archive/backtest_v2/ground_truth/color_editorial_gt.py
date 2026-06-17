"""L2a ground truth — editorial MOOD playlists -> per-colour relevant set (EXTERNAL).

The existing editorial_playlists_v1.json is genre/era-heavy (indie, v-pop ballad, rap),
so it barely covers moods. Here we crawl YouTube Music with explicitly MOOD-named queries,
grouped by the engine's 8 emotion labels, and assign each catalog song the mood(s) of the
playlist(s) it appears in (human curation — independent of song_va / hsl_to_va).

A colour's relevant set = songs whose editorial mood-set contains the colour's HUMAN
target_mood (from color_norms.py). This is the most defensible GT (real human curation),
but coverage is sparse (only songs that surface in crawled playlists are labelled).

Reuses the fuzzy-matching + filtering machinery in editorial.py.

Usage: python -m tools.backtest_v2.ground_truth.color_editorial_gt
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Dict, List

import pandas as pd

GT_DIR = "var/runtime/backtest/ground_truth"
GT_FILE = os.path.join(GT_DIR, "color_editorial_gt_v1.json")

# Mood label -> VN playlist search queries (curated to be unambiguous mood names).
MOOD_QUERIES: Dict[str, List[str]] = {
    "happy":       ["nhạc vui tươi việt", "nhạc trẻ vui nhộn", "nhạc tết vui"],
    "excited":     ["nhạc sôi động việt", "nhạc edm việt remix", "nhạc gym tập thể dục",
                    "nhạc party quẩy việt"],
    "calm":        ["nhạc chill việt nam", "nhạc nhẹ thư giãn", "nhạc lofi việt nam"],
    "peaceful":    ["nhạc acoustic nhẹ nhàng việt", "nhạc không lời thư giãn việt"],
    "melancholic": ["nhạc tâm trạng hoài niệm", "nhạc buồn nhẹ nhàng tâm trạng"],
    "sad":         ["nhạc buồn", "nhạc thất tình", "nhạc chia tay buồn nhất"],
    "tense":       ["nhạc rock việt", "nhạc rap việt căng"],
    "angry":       ["nhạc rock mạnh việt", "nhạc rap diss việt"],
}

MIN_HITS = 8
MAX_COVERAGE_RATIO = 0.60
N_RESULTS_PER_QUERY = 4


def crawl_mood_playlists(catalog_df: pd.DataFrame, verbose: bool = True) -> dict:
    """Crawl mood playlists; return {mood: {song_idx: n_playlists_seen}} + raw list."""
    from ytmusicapi import YTMusic
    from tools.backtest_v2.ground_truth import editorial as ed

    yt = YTMusic()
    cat_index = ed._build_catalog_index(catalog_df)
    cat_size = len(catalog_df)
    seen_pl: set = set()
    mood_songs: Dict[str, Dict[int, int]] = {m: {} for m in MOOD_QUERIES}
    raw: List[dict] = []

    for mood, queries in MOOD_QUERIES.items():
        for query in queries:
            if verbose:
                print(f"[color-ed] {mood:11s} <- {query!r}")
            try:
                results = yt.search(query, filter="playlists", limit=N_RESULTS_PER_QUERY)
            except Exception as exc:
                print(f"[color-ed]   search error: {exc}"); time.sleep(1.0); continue
            time.sleep(ed.YTMUSIC_DELAY)

            for r in results:
                pl_id = r.get("playlistId") or r.get("browseId")
                if not pl_id or pl_id in seen_pl:
                    continue
                seen_pl.add(pl_id)
                try:
                    pl = yt.get_playlist(pl_id, limit=None)
                except Exception as exc:
                    print(f"[color-ed]   get_playlist error: {exc}"); time.sleep(1.0); continue
                time.sleep(ed.YTMUSIC_DELAY)

                tracks = pl.get("tracks") or []
                matched: set = set()
                for tr in tracks:
                    nm = tr.get("title") or ""
                    al = tr.get("artists") or []
                    ar = ", ".join(a.get("name", "") for a in al) if al else ""
                    idx = ed._fuzzy_match(nm, ar, cat_index)
                    if idx is not None:
                        matched.add(idx)

                n = len(matched)
                cov = n / cat_size if cat_size else 0
                if n < MIN_HITS or cov > MAX_COVERAGE_RATIO:
                    if verbose:
                        print(f"[color-ed]   DROP '{pl.get('title','')[:40]}' ({n} hits, {cov:.0%})")
                    continue
                for idx in matched:
                    mood_songs[mood][idx] = mood_songs[mood].get(idx, 0) + 1
                raw.append({"mood": mood, "query": query, "playlist_id": pl_id,
                            "title": pl.get("title", ""), "n_matched": n})
                if verbose:
                    print(f"[color-ed]   keep '{pl.get('title','')[:40]}' ({n} hits)")
    return {"mood_songs": mood_songs, "playlists": raw}


def build_color_editorial_gt(verbose: bool = True) -> dict:
    from tools.backtest_v2.catalog import Catalog
    from tools.backtest_v2.ground_truth.color_norms import query_colors

    cat = Catalog.load()
    crawl = crawl_mood_playlists(cat.df, verbose=verbose)
    mood_songs = crawl["mood_songs"]

    gt = {}
    for q in query_colors():
        mood = q["target_mood"]
        relevant = sorted(int(i) for i in mood_songs.get(mood, {}))
        gt[q["hex"]] = {"term": q["term"], "target_mood": mood,
                        "relevant": relevant, "n_relevant": len(relevant)}

    out = {"colors": gt,
           "mood_coverage": {m: len(s) for m, s in mood_songs.items()},
           "n_playlists_kept": len(crawl["playlists"]),
           "validity": "external"}
    os.makedirs(GT_DIR, exist_ok=True)
    json.dump(out, open(GT_FILE, "w"), ensure_ascii=False, indent=1)
    if verbose:
        print(f"\n[color-ed] mood coverage: {out['mood_coverage']}")
        print(f"[color-ed] saved -> {GT_FILE}")
        for h, e in gt.items():
            print(f"  {e['term']:9s} ({e['target_mood']:11s}): {e['n_relevant']} relevant")
    return out


def load_color_editorial_gt(path: str = GT_FILE) -> dict:
    return json.load(open(path))


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    build_color_editorial_gt()
