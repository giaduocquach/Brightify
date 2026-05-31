"""E-RELABEL (2026-05-31) — re-derive song emotion labels from lyrics-valence +
audio-arousal, replacing the biased CLAP audio zero-shot labels.

WHY (see memory project_clap_label_bias): CLAP labels 74% of the catalog happy/excited,
yet Essentia arousal is identical (~0.33) across ALL CLAP labels → CLAP labels do not
track arousal at all, and 89% of CLAP-"happy" songs are actually low-energy. Songs titled
buồn/khóc/chia tay are labelled "happy" 3× more than "sad". The skew is a labelling
artifact, not the data.

NEW LABELLING (evidence-grounded):
  Valence ← lyrics  (Vietnamese emotion lexicon; arXiv:2302.13321 "valence needs lyrics")
                    blended with Essentia audio valence as a backstop.
  Arousal ← audio   (Essentia energy/arousal; reliable cross-culturally, r≈0.81).
                    RANK-normalised within the catalog — Essentia's absolute arousal
                    scale is uncalibrated (median 0.34), but a song's RANK ("more or less
                    energetic than typical") is meaningful and avoids the degenerate
                    "everything is low-arousal" cut. Valence is kept NATURAL (semantic
                    0.5 = neutral) because positive/negative is absolute, not relative.
  Label = quadrant via MultimodalEmotionFusion.get_emotion_label(valence, arousal).

EVALUATION is NON-CIRCULAR — three signals NOT used to derive the labels:
  1. Title-keyword accuracy: sad-titled songs should get sad/melancholic labels.
  2. Arousal consistency: Spearman(label's canonical arousal, Essentia arousal).
  3. Valence consistency: do "negative" labels have lower lyric sentiment than "positive"?

Output: data/emotion_labels_v2.json  {track_id: {label, valence, arousal}}
Usage:  python -m tools.relabel_emotions            # build + backtest
        python -m tools.relabel_emotions --report   # backtest existing file only
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg

OUT_FILE = "data/emotion_labels_v2.json"

# Canonical Russell V-A centroids for the 8 labels (for consistency scoring).
CANON_VA = {
    'happy': (0.88, 0.70), 'excited': (0.72, 0.92), 'peaceful': (0.72, 0.15),
    'calm': (0.62, 0.22), 'melancholic': (0.28, 0.32), 'sad': (0.15, 0.18),
    'tense': (0.30, 0.78), 'angry': (0.12, 0.92),
}

# Independent title keywords (NOT used to build labels) for semantic validation.
SAD_KW = r'buồn|khóc|nước mắt|chia tay|cô đơn|đau|tan vỡ|lỡ|tiếc|quên|xa'
HAPPY_KW = r'vui|yêu|hạnh phúc|nắng|cười|tươi|mừng|tình yêu|ngọt'


def _norm(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    lo, hi = np.nanmin(x), np.nanmax(x)
    return np.clip((x - lo) / (hi - lo + 1e-9), 0, 1)


def _rank_norm(x: np.ndarray) -> np.ndarray:
    """Rank-normalise to [0,1] with median→0.5 (catalog-relative)."""
    x = np.asarray(x, dtype=float)
    order = np.argsort(np.argsort(x))
    return order / (len(x) - 1 + 1e-9)


def build_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Return df with new columns: v2_valence, v2_arousal, v2_label."""
    from core.emotion_analysis import get_emotion_analyzer
    lexicon, classifier, fusion = get_emotion_analyzer()

    # --- lyrics valence/arousal from the Vietnamese lexicon ---
    lyr_col = 'lyrics_cleaned' if 'lyrics_cleaned' in df.columns else 'plain_lyrics'
    lyr_v = np.full(len(df), 0.5)
    lyr_cov = np.zeros(len(df))  # lexicon coverage (confidence)
    for i, txt in enumerate(df[lyr_col].fillna('').values):
        scores = lexicon.analyze_lyrics(txt)
        if scores and sum(scores.values()) > 0:
            v, _a = classifier.emotions_to_valence_arousal(scores)
            lyr_v[i] = v
            lyr_cov[i] = min(1.0, sum(abs(s) for s in scores.values()))

    # --- audio valence / arousal (Essentia) ---
    aud_v = df['valence'].fillna(0.5).to_numpy(float)
    energy = df['energy'].fillna(0.5).to_numpy(float)
    ess_aro = df['arousal'].fillna(0.5).to_numpy(float)
    audio_arousal = 0.6 * energy + 0.4 * ess_aro

    # --- fuse ---
    # Valence: lyrics-led (research) weighted by lexicon coverage; audio backstop.
    w_lyr = 0.35 + 0.30 * lyr_cov          # 0.35–0.65 depending on lexicon hits
    valence_raw = w_lyr * lyr_v + (1 - w_lyr) * aud_v
    # Both lyric- and audio-valence centre ~0.45 (scale offset, not true neutral),
    # so a hard 0.5 cut over-rotates to negative. Blend the natural scale (keeps
    # absolute direction — sad stays sad) with a rank-normalised version (median→0.5,
    # removes the offset, balances the split). 0.45 natural / 0.55 rank.
    valence = 0.45 * valence_raw + 0.55 * _rank_norm(valence_raw)

    # Arousal: audio, RANK-normalised (Essentia absolute scale uncalibrated).
    arousal = _rank_norm(audio_arousal)

    labels = [fusion.get_emotion_label(float(v), float(a))
              for v, a in zip(valence, arousal)]

    df = df.copy()
    df['v2_valence'] = np.clip(valence, 0, 1)
    df['v2_arousal'] = arousal
    df['v2_label'] = labels
    return df


def _title_accuracy(df: pd.DataFrame, label_col: str) -> dict:
    """Fraction of sad/happy-titled songs whose label matches the title sentiment."""
    titles = df['track_name'].fillna('')
    pos_labels = {'happy', 'excited', 'peaceful', 'calm'}
    neg_labels = {'sad', 'melancholic', 'tense', 'angry'}

    sad = df[titles.str.contains(SAD_KW, case=False, regex=True)]
    hap = df[titles.str.contains(HAPPY_KW, case=False, regex=True)
             & ~titles.str.contains(SAD_KW, case=False, regex=True)]

    sad_ok = sad[label_col].isin(neg_labels).mean() if len(sad) else float('nan')
    hap_ok = hap[label_col].isin(pos_labels).mean() if len(hap) else float('nan')
    return {'sad_title_correct': sad_ok, 'happy_title_correct': hap_ok,
            'n_sad': len(sad), 'n_happy': len(hap)}


def _consistency(df: pd.DataFrame, label_col: str) -> dict:
    """Spearman between each label's canonical V-A and independent signals."""
    canon_v = df[label_col].map(lambda e: CANON_VA.get(e, (0.5, 0.5))[0])
    canon_a = df[label_col].map(lambda e: CANON_VA.get(e, (0.5, 0.5))[1])

    # arousal: vs Essentia audio arousal (independent of label derivation for CLAP;
    # weakly circular for v2 since v2 arousal derives from audio — noted in report)
    ess_arousal = 0.6 * df['energy'].fillna(0.5) + 0.4 * df['arousal'].fillna(0.5)
    a_rho = spearmanr(canon_a, ess_arousal).correlation
    # valence: vs lyric sentiment_compound (independent for BOTH label sets)
    sent = df['sentiment_compound'].fillna(0)
    v_rho = spearmanr(canon_v, sent).correlation
    return {'arousal_consistency': a_rho, 'valence_consistency': v_rho}


def backtest(df: pd.DataFrame, clap: dict) -> None:
    df = df.copy()
    df['clap_label'] = df['track_id'].astype(str).map(clap)

    print("\n" + "=" * 62)
    print("E-RELABEL BACKTEST — CLAP (old)  vs  lyrics+audio (v2, new)")
    print("=" * 62)

    print("\n--- Distribution ---")
    comp = pd.DataFrame({
        'CLAP': df['clap_label'].value_counts(),
        'v2': df['v2_label'].value_counts(),
    }).fillna(0).astype(int)
    print(comp.to_string())

    print("\n--- (1) Title-keyword accuracy [INDEPENDENT] (higher = better) ---")
    for name, col in [('CLAP', 'clap_label'), ('v2', 'v2_label')]:
        t = _title_accuracy(df, col)
        print(f"  {name:4}  sad-titled→negative: {t['sad_title_correct']*100:5.1f}%  "
              f"(n={t['n_sad']})   happy-titled→positive: {t['happy_title_correct']*100:5.1f}%  "
              f"(n={t['n_happy']})")

    print("\n--- (2,3) Consistency: Spearman(label canonical V-A, independent signal) ---")
    print("    arousal vs Essentia audio | valence vs lyric sentiment_compound")
    for name, col in [('CLAP', 'clap_label'), ('v2', 'v2_label')]:
        c = _consistency(df, col)
        print(f"  {name:4}  arousal ρ={c['arousal_consistency']:+.3f}   "
              f"valence ρ={c['valence_consistency']:+.3f}")
    print("\n  NOTE: v2 arousal ρ is partly circular (v2 derives arousal from audio);")
    print("  the title accuracy (1) and valence ρ vs lyric-sentiment are fully")
    print("  independent of the v2 derivation and are the decisive metrics.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--report', action='store_true', help='backtest existing v2 file only')
    args = ap.parse_args()

    df = pd.read_csv(cfg.PROCESSED_FILE)
    if 'track_id' not in df.columns:
        df['track_id'] = range(len(df))
    with open(cfg.CLAP_EMOTIONS_FILE) as f:
        clap = json.load(f)

    if args.report and os.path.exists(OUT_FILE):
        with open(OUT_FILE) as f:
            v2 = json.load(f)
        df['v2_label'] = df['track_id'].astype(str).map(lambda t: v2.get(t, {}).get('label'))
        df['v2_valence'] = df['track_id'].astype(str).map(lambda t: v2.get(t, {}).get('valence', 0.5))
        df['v2_arousal'] = df['track_id'].astype(str).map(lambda t: v2.get(t, {}).get('arousal', 0.5))
    else:
        print("[E-RELABEL] Building labels from lyrics + audio ...")
        df = build_labels(df)
        out = {str(r.track_id): {'label': r.v2_label,
                                 'valence': round(float(r.v2_valence), 4),
                                 'arousal': round(float(r.v2_arousal), 4)}
               for r in df.itertuples()}
        os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
        with open(OUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False)
        print(f"[E-RELABEL] Saved {len(out)} labels → {OUT_FILE}")

    backtest(df, clap)
    return 0


if __name__ == '__main__':
    sys.exit(main())
