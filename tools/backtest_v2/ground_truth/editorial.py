"""PRIMARY ground truth — crawl VN editorial playlists via ytmusicapi, fuzzy-match to catalog.

§7.1 — Phase 2.

Protocol:
  1. Search each query with filter="playlists", take up to 5 results.
  2. Fetch full playlist with get_playlist(limit=None).
  3. Fuzzy-match each track (name + artist) against the catalog via
     normalised diacritics + token overlap (Jaccard ≥ threshold).
  4. Filter: drop playlists with < MIN_HITS matches.
  5. Filter: drop playlists with > MAX_COVERAGE_RATIO * catalog_size matches
     (too generic, not discriminative).
  6. Save {intent, playlist_id, title, matched: [{catalog_idx, track_name, artist}]}.

Only the mapping is saved — no audio, no full lyrics (ToS).
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# ---------------------------------------------------------------------------
# Constants (from §7.1)
# ---------------------------------------------------------------------------

PLAYLIST_QUERIES = [
    "nhạc buồn tâm trạng",
    "nhạc chill việt nam",
    "nhạc tập trung học bài",
    "nhạc tan làm thư giãn",
    "nhạc đôi lứa couple",
    "nhạc tết vui",
    "nhạc gym tập thể dục",
    "nhạc indie việt",
    "v-pop ballad hay nhất",
    "nhạc acoustic việt nam",
    "nhạc rap việt",
    "nhạc trữ tình",
    "nhạc vàng bolero",
    "top nhạc việt 2024",
    "nhạc pop việt hay nhất",
    "nhạc nhẹ việt nam",
    "nhạc tình cảm việt",
    "nhạc lofi việt nam",
]

MIN_HITS = 10          # §7.1: bỏ playlist < 10 hit
MAX_COVERAGE_RATIO = 0.70  # §7.1: bỏ playlist > 70% catalog coverage
YTMUSIC_DELAY = 0.15   # s between requests (from collect_data.py pattern)
SEARCH_RESULTS_PER_QUERY = 5
FUZZY_THRESHOLD = 0.50  # Jaccard token overlap threshold (normalised)


# ---------------------------------------------------------------------------
# Text normalisation helpers
# ---------------------------------------------------------------------------

def _normalise(text: str) -> str:
    """Lowercase, strip diacritics, remove punctuation."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _tokens(text: str) -> set:
    return set(_normalise(text).split())


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _match_score(track_name: str, artist: str, cat_name: str, cat_artist: str) -> float:
    """Combined score: 0.7 * track Jaccard + 0.3 * artist Jaccard."""
    t_score = _jaccard(_tokens(track_name), _tokens(cat_name))
    a_score = _jaccard(_tokens(artist), _tokens(cat_artist))
    return 0.7 * t_score + 0.3 * a_score


# ---------------------------------------------------------------------------
# Catalog preparation
# ---------------------------------------------------------------------------

def _build_catalog_index(catalog_df: pd.DataFrame) -> List[Tuple[int, str, str, set, set]]:
    """Pre-compute normalised token sets for fast matching.

    Returns list of (catalog_idx, track_name, artist, name_tokens, artist_tokens).
    """
    rows = []
    # Determine artist column
    artist_col = None
    for col in ("primary_artist", "artists", "artist_name"):
        if col in catalog_df.columns:
            artist_col = col
            break

    for idx, row in catalog_df.iterrows():
        name = str(row.get("track_name", "") or "")
        artist = str(row.get(artist_col, "") or "") if artist_col else ""
        rows.append((int(idx), name, artist, _tokens(name), _tokens(artist)))
    return rows


def _fuzzy_match(
    track_name: str,
    artist: str,
    catalog_index: List[Tuple[int, str, str, set, set]],
    threshold: float = FUZZY_THRESHOLD,
) -> Optional[int]:
    """Return catalog_idx of best match if score >= threshold, else None."""
    t_tok = _tokens(track_name)
    a_tok = _tokens(artist)
    best_idx = None
    best_score = -1.0
    for cat_idx, _cn, _ca, cn_tok, ca_tok in catalog_index:
        t_score = _jaccard(t_tok, cn_tok)
        if t_score < 0.4:  # early reject on track name
            continue
        a_score = _jaccard(a_tok, ca_tok)
        score = 0.7 * t_score + 0.3 * a_score
        if score > best_score:
            best_score = score
            best_idx = cat_idx
    if best_score >= threshold:
        return best_idx
    return None


# ---------------------------------------------------------------------------
# Crawl + match
# ---------------------------------------------------------------------------

def crawl_editorial_playlists(
    catalog_df: pd.DataFrame,
    n_results_per_query: int = SEARCH_RESULTS_PER_QUERY,
    verbose: bool = True,
) -> List[Dict[str, Any]]:
    """Crawl VN playlists from YouTube Music and fuzzy-match to catalog.

    Returns list of playlist dicts that pass the filters.
    Each dict:
        intent        — search query used
        playlist_id   — YouTube Music playlist ID
        title         — playlist title
        n_tracks_raw  — total tracks in playlist
        matched       — [{catalog_idx, track_name, artist}]
    """
    from ytmusicapi import YTMusic

    yt = YTMusic()
    catalog_index = _build_catalog_index(catalog_df)
    catalog_size = len(catalog_df)

    seen_playlist_ids: set = set()
    raw_playlists: List[Dict[str, Any]] = []

    for query in PLAYLIST_QUERIES:
        if verbose:
            print(f"[editorial] Searching: {query!r}")
        try:
            results = yt.search(query, filter="playlists", limit=n_results_per_query)
        except Exception as exc:
            print(f"[editorial]   search error: {exc}")
            time.sleep(1.0)
            continue
        time.sleep(YTMUSIC_DELAY)

        for r in results:
            pl_id = r.get("playlistId") or r.get("browseId")
            if not pl_id or pl_id in seen_playlist_ids:
                continue
            seen_playlist_ids.add(pl_id)
            pl_title = r.get("title", "")

            try:
                pl = yt.get_playlist(pl_id, limit=None)
            except Exception as exc:
                print(f"[editorial]   get_playlist {pl_id} error: {exc}")
                time.sleep(1.0)
                continue
            time.sleep(YTMUSIC_DELAY)

            tracks = pl.get("tracks") or []
            if verbose:
                print(f"[editorial]   playlist '{pl_title}' — {len(tracks)} tracks")

            # Fuzzy-match each track
            matched: List[Dict[str, Any]] = []
            seen_catalog_idx: set = set()
            for tr in tracks:
                tr_name = tr.get("title") or ""
                # artists field is a list of {name, id}
                artists_list = tr.get("artists") or []
                tr_artist = ", ".join(a.get("name", "") for a in artists_list) if artists_list else ""

                cat_idx = _fuzzy_match(tr_name, tr_artist, catalog_index)
                if cat_idx is not None and cat_idx not in seen_catalog_idx:
                    seen_catalog_idx.add(cat_idx)
                    matched.append({
                        "catalog_idx": cat_idx,
                        "track_name": tr_name,
                        "artist": tr_artist,
                    })

            raw_playlists.append({
                "intent": query,
                "playlist_id": pl_id,
                "title": pl_title,
                "n_tracks_raw": len(tracks),
                "matched": matched,
            })

    # Apply filters
    filtered = []
    for pl in raw_playlists:
        n_hits = len(pl["matched"])
        coverage = n_hits / catalog_size if catalog_size > 0 else 0
        if n_hits < MIN_HITS:
            if verbose:
                print(f"[editorial] DROP '{pl['title']}': {n_hits} hits < {MIN_HITS}")
            continue
        if coverage > MAX_COVERAGE_RATIO:
            if verbose:
                print(f"[editorial] DROP '{pl['title']}': coverage {coverage:.1%} > {MAX_COVERAGE_RATIO:.0%}")
            continue
        filtered.append(pl)

    if verbose:
        total_matched = sum(len(pl["matched"]) for pl in filtered)
        print(f"\n[editorial] Playlists passing filter: {len(filtered)}")
        print(f"[editorial] Total track matches: {total_matched}")

    return filtered


# ---------------------------------------------------------------------------
# Save / load
# ---------------------------------------------------------------------------

GT_DIR = "var/runtime/backtest/ground_truth"
GT_FILE = os.path.join(GT_DIR, "editorial_playlists_v1.json")


def save_editorial_gt(playlists: List[Dict[str, Any]], path: str = GT_FILE) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(playlists, fh, ensure_ascii=False, indent=2)
    print(f"[editorial] Saved to {path}")


def build_cross_artist_gt_mapping(
    playlists: List[Dict[str, Any]],
) -> Dict[int, List[int]]:
    """Like build_query_gt_mapping but only keeps seed→relevant pairs from DIFFERENT artists.

    Motivation: KG embeddings are built from artist co-occurrence, which may correlate
    with editorial playlist co-occurrence (same artist appears in many playlists → easy
    same-artist pairs inflate KG gain). This GT tests whether KG helps on cross-artist
    retrieval, ruling out the circular-reasoning concern.
    """
    mapping: Dict[int, List[int]] = {}
    for pl in playlists:
        tracks = pl["matched"]
        if len(tracks) < 2:
            continue
        for t_seed in tracks:
            seed_idx    = t_seed["catalog_idx"]
            seed_artist = t_seed.get("artist", "")
            relevant = [
                t["catalog_idx"] for t in tracks
                if t["catalog_idx"] != seed_idx and t.get("artist", "") != seed_artist
            ]
            if not relevant:
                continue
            if seed_idx not in mapping:
                mapping[seed_idx] = []
            existing = set(mapping[seed_idx])
            mapping[seed_idx].extend(i for i in relevant if i not in existing)
    return {k: v for k, v in mapping.items() if v}


def load_editorial_gt(path: str = GT_FILE) -> List[Dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def build_query_gt_mapping(playlists: List[Dict[str, Any]]) -> Dict[int, List[int]]:
    """Convert playlist list into {seed_catalog_idx: [relevant_catalog_idx, ...]} mapping.

    For each playlist, each matched track is treated as a query seed, and
    all other matched tracks in the same playlist are the relevant set.
    This is standard "playlist continuation" evaluation.
    """
    mapping: Dict[int, List[int]] = {}
    for pl in playlists:
        indices = [m["catalog_idx"] for m in pl["matched"]]
        if len(indices) < 2:
            continue
        for seed in indices:
            relevant = [i for i in indices if i != seed]
            if seed not in mapping:
                mapping[seed] = []
            # Union across playlists — a track can appear in multiple playlists
            existing = set(mapping[seed])
            mapping[seed].extend(i for i in relevant if i not in existing)
    return mapping


def build_cluster_seeds(playlists: List[Dict[str, Any]]) -> List[List[int]]:
    """Return [[seed_idx, ...], ...] — one inner list per playlist.

    Used with cluster_paired_bootstrap to correct pseudo-replication:
    queries from the same playlist share a relevant set and are not independent.
    """
    return [
        [m["catalog_idx"] for m in pl["matched"]]
        for pl in playlists
        if len(pl["matched"]) >= 2
    ]


# ---------------------------------------------------------------------------
# Main entry point (used by CLI)
# ---------------------------------------------------------------------------

def build_editorial_gt(
    catalog_df: pd.DataFrame,
    save: bool = True,
    verbose: bool = True,
) -> Tuple[List[Dict[str, Any]], Dict[int, List[int]]]:
    """Crawl, match, filter, optionally save, return (playlists, gt_mapping)."""
    playlists = crawl_editorial_playlists(catalog_df, verbose=verbose)
    if save and playlists:
        save_editorial_gt(playlists)
    mapping = build_query_gt_mapping(playlists)
    return playlists, mapping
