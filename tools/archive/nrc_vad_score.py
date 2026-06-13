"""Shared NRC-VAD lexicon loader — valence AND arousal.

Extracts the pattern from color_r2_valence_panel.py:_load_nrc_vad() and extends
it to load both valence (col 2) and arousal (col 3). Used by build_v6a_labels.py,
color_r2_valence_panel.py, and any future probe that needs lyrics-based V-A.

Lexicon format (tab-separated):
  Word  Valence  Arousal  Dominance
Values already normalised to [0,1] in NRC-VAD v2.1.

Run: python -m tools.nrc_vad_score [--lyrics "song lyrics here"]
"""
from __future__ import annotations

import json
import os
import sys
from typing import Optional

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

NRC_VAD_PATH = "var/data/nrc_vad_lexicon.txt"


def load_nrc_vad(path: str = NRC_VAD_PATH) -> dict[str, tuple[float, float]]:
    """Load NRC-VAD lexicon → {word: (valence, arousal)}.

    Returns empty dict if file not found. Values in [0,1].
    """
    lexicon: dict[str, tuple[float, float]] = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("Word"):
                    continue
                parts = line.split("\t")
                if len(parts) < 3:
                    continue
                word = parts[0].lower().strip()
                try:
                    valence = float(parts[1])
                    arousal = float(parts[2])
                    lexicon[word] = (valence, arousal)
                except ValueError:
                    pass
    except FileNotFoundError:
        pass
    return lexicon


def score_lyrics(lyrics: str, lexicon: dict[str, tuple[float, float]],
                 dim: str = "valence") -> float:
    """Mean NRC-VAD score for dim ('valence' or 'arousal') over matched words.

    Returns NaN if no words match (caller should decide fallback).
    """
    if not lexicon or not isinstance(lyrics, str):
        return float("nan")
    idx = 0 if dim == "valence" else 1
    tokens = lyrics.lower().split()
    scores = [lexicon[t][idx] for t in tokens if t in lexicon]
    return float(np.mean(scores)) if scores else float("nan")


def score_lyrics_va(lyrics: str, lexicon: dict[str, tuple[float, float]]
                    ) -> tuple[float, float]:
    """Return (valence, arousal) tuple. Either/both may be NaN."""
    return score_lyrics(lyrics, lexicon, "valence"), score_lyrics(lyrics, lexicon, "arousal")


def build_catalog_scores(df, lexicon: dict[str, tuple[float, float]],
                         out_path: Optional[str] = None) -> dict[str, dict]:
    """Score full catalog DataFrame. Returns {track_id: {valence, arousal, n_matched}}.

    Requires df to have a track_id column and at least one lyrics column.
    """
    lyrics_col = next(
        (c for c in ["lyrics", "lyrics_cleaned", "lyrics_clean", "lyric", "plain_lyrics"]
         if c in df.columns),
        None,
    )
    id_col = next(
        (c for c in ["track_id", "id", "song_id", "ID"] if c in df.columns), None
    )
    if lyrics_col is None or id_col is None:
        raise ValueError(f"Need track_id+lyrics columns. Found: {list(df.columns)}")

    results: dict[str, dict] = {}
    for _, row in df.iterrows():
        tid = str(row[id_col])
        lyr = str(row[lyrics_col]) if row[lyrics_col] == row[lyrics_col] else ""
        v, a = score_lyrics_va(lyr, lexicon)
        tokens = lyr.lower().split()
        n_matched = sum(1 for t in tokens if t in lexicon)
        results[tid] = {
            "valence":   None if np.isnan(v) else round(float(v), 4),
            "arousal":   None if np.isnan(a) else round(float(a), 4),
            "n_matched": n_matched,
        }

    if out_path:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        json.dump(results, open(out_path, "w"), ensure_ascii=False)
        valid_v = sum(1 for r in results.values() if r["valence"] is not None)
        valid_a = sum(1 for r in results.values() if r["arousal"] is not None)
        print(f"[nrc_vad_score] {len(results)} songs, "
              f"valence matched={valid_v}, arousal matched={valid_a} → {out_path}")

    return results


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--lyrics", help="Score a single lyrics string")
    ap.add_argument("--build-catalog", action="store_true",
                    help="Score full catalog → data/nrc_vad_scores.json")
    ap.add_argument("--lexicon", default=NRC_VAD_PATH)
    args = ap.parse_args()

    lexicon = load_nrc_vad(args.lexicon)
    if not lexicon:
        print(f"[ERROR] Lexicon not found: {args.lexicon}")
        print("  Download from: saifmohammad.com/WebPages/NRC-Emotion-Lexicon.htm")
        return 1

    print(f"[nrc_vad_score] Loaded {len(lexicon)} entries from {args.lexicon}")

    if args.lyrics:
        v, a = score_lyrics_va(args.lyrics, lexicon)
        print(f"  valence={v:.4f}  arousal={a:.4f}")

    if args.build_catalog:
        import config as cfg
        import pandas as pd
        df = pd.read_csv(cfg.PROCESSED_FILE)
        build_catalog_scores(df, lexicon, out_path="data/nrc_vad_scores.json")

    return 0


if __name__ == "__main__":
    sys.exit(main())
