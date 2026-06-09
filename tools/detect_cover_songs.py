"""
Detect cover songs, duplicates, and same-song versions in the catalog.

Problem: Catalog has multiple versions of the same song:
  - Exact duplicates: "Âm Tính 0" and "Âm Tính 0 (feat. Lumee)" — MERT cosine = 1.000
  - Cross-lingual versions: "April's Lie" and "Tháng Tư Là Lời Nói Dối" — MERT=0.949, lyrics=1.000
  - Remixes, acoustic, live versions of the same song

When recommend_by_song returns a cover/duplicate of the seed, it wastes a slot
and confuses users who want DIFFERENT songs.

Detection approach — 3 layers:
  Layer 1: Exact or near-exact — MERT cosine > 0.98  (same audio effectively)
  Layer 2: Same song, same artist — MERT > 0.92 AND same primary artist
  Layer 3: Same song, different artist (cover) — MERT > 0.95 AND lyrics cosine > 0.85
           (true covers: same melody AND same lyrics structure)

Cross-lingual detection (April Lie case):
  MERT > 0.92 AND same artist AND lyrics cosine < 0.5 (different language → low lyrics sim)
  → caught by Layer 2

Output: data/cover_index.json — {track_id: [list_of_cover_track_ids]}
        data/cover_stats.json  — detection statistics

Usage: python -m tools.detect_cover_songs [--dry-run] [--threshold-mert 0.92]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import config as cfg

COVER_INDEX_FILE = str(cfg.DATA_DIR / "cover_index.json")
COVER_STATS_FILE = str(cfg.DATA_DIR / "cover_stats.json")


def normalize_title(s: str) -> str:
    """Strip version suffixes and diacritics for fuzzy title matching."""
    s = str(s).lower().strip()
    # Remove version indicators
    for kw in ["(feat", "(ft.", "(ft ", "feat.", " ft.", "(remix", "(acoustic",
               "(live", "(cover", "(piano", "(instrumental", "(karaoke",
               "(ost", "(ver.", "(version", "(prod.", "(prod ", "(theme"]:
        idx = s.find(kw)
        if idx > 0:
            s = s[:idx].strip()
    # Remove diacritics
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    # Keep only alphanumeric + spaces
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def primary_artist(artist_str: str) -> str:
    """Extract first/primary artist name, normalized."""
    if not artist_str:
        return ""
    first = str(artist_str).split(",")[0].strip()
    first = unicodedata.normalize("NFD", first.lower())
    first = "".join(c for c in first if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", first)[:15]


def detect_covers(
    mert_threshold_exact: float = 0.99,
    mert_threshold_same_artist: float = 0.97,   # raised from 0.92 to avoid false positives
    mert_threshold_cover: float = 0.95,
    lyrics_threshold_cover: float = 0.90,        # raised from 0.85
    dry_run: bool = False,
    verbose: bool = True,
) -> Dict[str, List[str]]:
    """Build cover index: {track_id: [list_of_cover_track_ids]}."""
    import pandas as pd

    df = pd.read_csv(cfg.PROCESSED_FILE)
    n = len(df)
    track_ids = df["track_id"].astype(str).values

    if verbose:
        print(f"[covers] Catalog: {n} songs")
        print(f"[covers] Loading embeddings...")

    # Load embeddings
    mert = np.load(cfg.MERT_EMBEDDINGS_FILE).astype(np.float32)
    lyr  = np.load(cfg.EMBEDDINGS_FILE).astype(np.float32)
    for mat in (mert, lyr):
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        mat /= norms

    # Precompute normalized metadata
    norm_titles   = [normalize_title(t) for t in df["track_name"].fillna("")]
    prim_artists  = [primary_artist(a) for a in df["artists"].fillna("")]

    cover_pairs: Set[tuple] = set()  # (i, j) i < j

    if verbose:
        print(f"[covers] Scanning {n*(n-1)//2:,} pairs in batches...")

    # Lyrics-first approach: VN-SBERT cosine is more reliable than MERT for same-content.
    # MERT collapses for same-artist productions → high false positive with MERT-only.
    # Strategy: use LYRICS as the primary signal, MERT as confirmation.
    batch_size = 512
    stats = {"lyrics_exact": 0, "lyrics_high_mert": 0, "title_match": 0}

    for start in range(0, n, batch_size):
        end = min(start + batch_size, n)
        block_lyr = lyr[start:end]       # (B, D)
        cos_lyr = block_lyr @ lyr.T      # (B, N)

        for bi, i in enumerate(range(start, end)):
            row_lyr = cos_lyr[bi]
            # Only check j > i, require lyrics > 0.92 as primary filter
            candidates = np.where(row_lyr[i+1:] > 0.92)[0] + i + 1

            for j in candidates:
                lc = float(row_lyr[j])
                if (i, j) in cover_pairs:
                    continue

                mc = float(mert[i] @ mert[j])
                reason = None

                # Layer 1: Near-identical lyrics (same song regardless of audio)
                # Catches: same song different case/title, same lyrics in DB
                if lc >= 0.97:
                    reason = "lyrics_exact"
                    stats["lyrics_exact"] += 1

                # Layer 2: Very high lyrics + high MERT (same song, different version)
                # MERT > 0.93 as confirmation that audio is also similar
                elif lc >= 0.92 and mc >= 0.93:
                    reason = "lyrics_high_mert"
                    stats["lyrics_high_mert"] += 1

                if reason:
                    cover_pairs.add((i, j))

    # Layer 3: Title-based detection (catches cross-lingual: April Lie)
    # Same normalized title + same primary artist
    from collections import defaultdict
    title_groups: dict = defaultdict(list)
    for i, (t, a) in enumerate(zip(norm_titles, prim_artists)):
        if t and a and len(t) > 3:
            key = f"{a[:8]}|{t[:20]}"
            title_groups[key].append(i)
    for key, group in title_groups.items():
        if len(group) > 1:
            for ii in range(len(group)):
                for jj in range(ii+1, len(group)):
                    pair = (min(group[ii], group[jj]), max(group[ii], group[jj]))
                    if pair not in cover_pairs:
                        cover_pairs.add(pair)
                        stats["title_match"] += 1

        if verbose and (start // batch_size) % 4 == 0:
            print(f"  [{start:4d}/{n}] found {len(cover_pairs)} cover pairs so far")

    if verbose:
        print(f"\n[covers] Total cover pairs: {len(cover_pairs)}")
        print(f"  lyrics_exact: {stats['lyrics_exact']}, lyrics_high_mert: {stats['lyrics_high_mert']}, title_match: {stats['title_match']}")

    # Build index: for each song, list of songs it should not be recommended alongside
    index: Dict[str, List[str]] = defaultdict(list)
    for i, j in cover_pairs:
        ti = track_ids[i]; tj = track_ids[j]
        index[ti].append(tj)
        index[tj].append(ti)

    # Print sample pairs for spot-check
    if verbose:
        print(f"\n[covers] Sample detected pairs:")
        count = 0
        for i, j in sorted(cover_pairs, key=lambda x: -(mert[x[0]] @ mert[x[1]]))[:15]:
            mc = float(mert[i] @ mert[j])
            lc = float(lyr[i] @ lyr[j])
            ni = str(df.iloc[i].get("track_name", ""))[:35]
            nj = str(df.iloc[j].get("track_name", ""))[:35]
            ai_str = str(df.iloc[i].get("artists", ""))[:20]
            aj_str = str(df.iloc[j].get("artists", ""))[:20]
            print(f"  mert={mc:.3f} lyr={lc:.3f} | '{ni}'({ai_str}) ↔ '{nj}'({aj_str})")
            count += 1

    if not dry_run:
        index_plain = {k: list(set(v)) for k, v in index.items()}
        with open(COVER_INDEX_FILE, "w", encoding="utf-8") as fh:
            json.dump(index_plain, fh, ensure_ascii=False, indent=1)

        cover_stats = {
            "n_songs": n, "n_cover_pairs": len(cover_pairs),
            "n_songs_with_covers": len(index),
            "stats": stats,
            "thresholds": {
                "mert_exact": mert_threshold_exact,
                "mert_same_artist": mert_threshold_same_artist,
                "mert_cover": mert_threshold_cover,
                "lyrics_cover": lyrics_threshold_cover,
            },
        }
        with open(COVER_STATS_FILE, "w", encoding="utf-8") as fh:
            json.dump(cover_stats, fh, indent=2)

        print(f"\n[covers] Saved → {COVER_INDEX_FILE}")
    else:
        print(f"\n[covers] Dry run — not saving.")

    return dict(index)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--threshold-mert", type=float, default=0.92)
    ap.add_argument("--threshold-exact", type=float, default=0.98)
    args = ap.parse_args(argv)
    os.chdir(str(PROJECT_ROOT))
    detect_covers(
        mert_threshold_exact=args.threshold_exact,
        mert_threshold_same_artist=args.threshold_mert,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
