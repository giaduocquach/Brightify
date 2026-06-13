"""Build a BLIND Vietnamese Valence-Arousal gold-set template (audit V17, P0 #2).

Why: every V-A number in the system (MERT arousal R²=0.58, LLM lyric-valence) is measured
on Western data (DEAM) or unvalidated. This builds the in-domain evaluation artifact that
unblocks validating/calibrating the arousal probe, the LLM valence, AND any encoder swap.

Sampling is STRATIFIED by the song's content emotion so rare moods (excited/angry/peaceful,
1–2% of the catalog) are covered — a uniform random sample would be ~47% sad and useless for
validating bright-mood colours. Rows are shuffled and carry NO labels, so annotators rate blind.

Output: var/goldset/color_va_goldset_template.csv
Each annotator copies it to var/goldset/ratings/<name>.csv and fills:
  rater_valence  (0 = rất tiêu cực/buồn   … 1 = rất tích cực/vui)
  rater_arousal  (0 = rất nhẹ/tĩnh lặng   … 1 = rất mạnh/sôi động)
Then run: python -m tools.eval_color_goldset

Usage: python -m tools.build_color_goldset [n_per_emotion]
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

SEED = 42


def main() -> int:
    n_per = int(sys.argv[1]) if len(sys.argv) > 1 else 26   # ~26×8 ≈ 200
    from core.recommendation_engine import get_recommender
    rec = get_recommender()
    df = rec.df.reset_index(drop=True)
    rng = np.random.default_rng(SEED)

    fe = df['fused_emotion'].fillna('').str.lower().values
    lyr_col = 'lyrics_cleaned' if 'lyrics_cleaned' in df.columns else 'plain_lyrics'
    art_col = 'primary_artist' if 'primary_artist' in df.columns else (
        'artists' if 'artists' in df.columns else None)

    rows, coverage = [], {}
    for emo in sorted(set(e for e in fe if e)):
        idx = np.where(fe == emo)[0]
        if len(idx) == 0:
            continue
        take = idx if len(idx) <= n_per else rng.choice(idx, n_per, replace=False)
        coverage[emo] = len(take)
        for i in take:
            r = df.iloc[int(i)]
            lyr = str(r.get(lyr_col) or '')
            rows.append({
                'track_id': r.get('track_id'),
                'track_name': r.get('track_name'),
                'artist': (r.get(art_col) if art_col else '') or '',
                'lyric_preview': ' '.join(lyr.split())[:240],
                'rater_valence': '',
                'rater_arousal': '',
            })

    out = pd.DataFrame(rows).sample(frac=1, random_state=SEED).reset_index(drop=True)
    os.makedirs('var/goldset/ratings', exist_ok=True)
    path = 'var/goldset/color_va_goldset_template.csv'
    out.to_csv(path, index=False)
    print(f"wrote {len(out)} songs -> {path}")
    print("stratified coverage by source emotion (HIDDEN from annotators in the file):")
    for e, n in sorted(coverage.items(), key=lambda x: -x[1]):
        print(f"   {e:<12} {n}")
    print("\nNext: each annotator fills a copy in var/goldset/ratings/<name>.csv,")
    print("then run  python -m tools.eval_color_goldset")
    return 0


if __name__ == "__main__":
    sys.exit(main())
