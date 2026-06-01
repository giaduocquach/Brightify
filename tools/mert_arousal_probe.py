"""MERT→arousal probe (E-AROUSAL, 2026-06-01).

Restores the AUDIO half of the audio+lyrics mood fusion. Essentia audio features are
degenerate (see memory project_arousal_miscalibration); MERT is the clean audio
representation we already have (data/mert_embeddings.npy). A small LINEAR PROBE maps
FROZEN MERT embeddings → arousal — MERT is NOT fine-tuned. Trained on DEAM (1802
Western songs with V-A labels); arousal transfers cross-corpus reasonably (Eerola 2026
R²≈0.81 in-domain). Valence is NOT done here (cross-corpus valence transfer fails;
valence stays LLM-from-lyrics).

  extract-deam : MERTEncoder on DEAM audio → deam_mert.npy + deam_ids.json
  train        : Ridge probe (5-fold CV R²) → apply to our MERT → data/mert_arousal.json
                 + non-circular backtest (CV R², vs tempo, vs LLM-arousal, distribution)

Usage: python -m tools.mert_arousal_probe extract-deam
       python -m tools.mert_arousal_probe train
"""
from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg

DEAM_DIR = "data/external/deam"
DEAM_MERT = f"{DEAM_DIR}/deam_mert.npy"
DEAM_IDS = f"{DEAM_DIR}/deam_ids.json"
OUT_AROUSAL = "data/mert_arousal.json"


def _deam_arousal() -> dict:
    """song_id -> arousal_mean (1..9) from DEAM static annotations."""
    import pandas as pd
    fs = glob.glob(f"{DEAM_DIR}/**/song_level/static_annotations_averaged_songs_*.csv",
                   recursive=True)
    df = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True)
    df.columns = [c.strip() for c in df.columns]
    return dict(zip(df["song_id"].astype(int), df["arousal_mean"].astype(float)))


def extract_deam() -> None:
    from core.mert_encoder import MERTEncoder
    labels = _deam_arousal()
    mp3s = {}
    for p in glob.glob(f"{DEAM_DIR}/**/*.mp3", recursive=True):
        base = os.path.splitext(os.path.basename(p))[0]
        try:
            mp3s[int(base)] = p
        except ValueError:
            continue
    ids = [s for s in labels if s in mp3s]
    print(f"[extract-deam] {len(ids)} songs with both label+audio (of {len(labels)} labels)")
    enc = MERTEncoder(); enc._load()
    embs, kept = [], []
    for i, sid in enumerate(ids, 1):
        e = enc.extract(mp3s[sid])
        if e is not None:
            embs.append(e); kept.append(sid)
        if i % 100 == 0:
            print(f"  {i}/{len(ids)}")
    np.save(DEAM_MERT, np.asarray(embs, dtype=np.float32))
    json.dump(kept, open(DEAM_IDS, "w"))
    print(f"[extract-deam] saved {len(kept)} embeddings → {DEAM_MERT}")


def train() -> None:
    import pandas as pd
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import KFold, cross_val_score
    from scipy.stats import spearmanr

    X = np.load(DEAM_MERT)
    ids = json.load(open(DEAM_IDS))
    labels = _deam_arousal()
    y = np.array([(labels[s] - 1.0) / 8.0 for s in ids])   # 1..9 → 0..1
    print(f"[train] DEAM probe set: X={X.shape}, arousal mean={y.mean():.2f} std={y.std():.2f}")

    print("\n=== Probe validity — 5-fold CV R² (held-out DEAM) ===")
    cv = KFold(5, shuffle=True, random_state=cfg.RANDOM_SEED)
    best_a, best_r2 = 1.0, -9
    for alpha in [1.0, 10.0, 100.0, 300.0]:
        r2 = cross_val_score(Ridge(alpha=alpha), X, y, cv=cv, scoring="r2")
        print(f"  Ridge α={alpha:5}: R²={r2.mean():+.3f} ± {r2.std():.3f}")
        if r2.mean() > best_r2:
            best_a, best_r2 = alpha, r2.mean()
    print(f"  → best α={best_a} (CV R²={best_r2:.3f})")

    model = Ridge(alpha=best_a).fit(X, y)

    # Apply to OUR catalog
    ours = np.load(cfg.MERT_EMBEDDINGS_FILE)
    pred = np.clip(model.predict(ours), 0, 1)
    cat = pd.read_csv(cfg.PROCESSED_FILE)
    tids = cat["track_id"].astype(str).tolist()
    json.dump({t: round(float(p), 4) for t, p in zip(tids, pred)},
              open(OUT_AROUSAL, "w"))
    print(f"\n[train] applied to {len(pred)} songs → {OUT_AROUSAL}")

    print("\n=== Backtest on OUR catalog (non-circular sanity) ===")
    tempo = cat["tempo"].fillna(cat["tempo"].median()).values
    energy = cat["energy"].fillna(0.5).values
    print(f"  MERT-arousal vs tempo  ρ = {spearmanr(pred, tempo).correlation:+.3f}  "
          f"(real BPM — legit arousal proxy; broken DEAM-arousal had +0.03)")
    print(f"  MERT-arousal vs energy ρ = {spearmanr(pred, energy).correlation:+.3f}")
    v3 = json.load(open(cfg.RELABELED_EMOTIONS_FILE))
    llm_a = np.array([v3.get(t, {}).get("arousal", 0.5) for t in tids])
    print(f"  MERT-arousal vs LLM-arousal ρ = {spearmanr(pred, llm_a).correlation:+.3f}  "
          f"(two independent arousal estimates: audio vs lyrics)")
    print(f"  distribution: mean={pred.mean():.2f} std={pred.std():.2f} "
          f">=0.5: {(pred>=0.5).mean()*100:.0f}%  (broken DEAM-arousal: std 0.06, 1.8%)")


def _rank01(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, float)
    return np.argsort(np.argsort(x)) / (len(x) - 1 + 1e-9)


def fuse(w_mert: float = 0.6) -> None:
    """Produce the true audio+lyrics labels (v4): valence ← LLM-lyrics,
    arousal ← w_mert·MERT-audio (rank-normalised, catalog-relative) + (1-w)·LLM-lyrics.
    label = quadrant(valence, arousal). Everything (song_va, fused_emotion, mood_quadrant)
    then derives from ONE consistent audio+lyrics V-A.
    """
    import pandas as pd
    from collections import Counter
    from core.emotion_analysis import get_emotion_analyzer
    _, _, fusion = get_emotion_analyzer()

    v3 = json.load(open("data/emotion_labels_v3.json"))
    ma = json.load(open(OUT_AROUSAL))
    tids = list(v3.keys())
    mert_a = np.array([ma.get(t, 0.5) for t in tids])
    # Use MERT's NATURAL prediction (the honest audio arousal), only de-compress its
    # spread to ~std 0.16 around its own mean — preserves ordering AND the real
    # high/low fraction (NOT rank-norm, which forces 50/50 and re-creates fake-angry).
    mu, sd = mert_a.mean(), mert_a.std() + 1e-9
    mert_s = np.clip(mu + (mert_a - mu) / sd * 0.16, 0, 1)

    out = {}
    for i, t in enumerate(tids):
        lv = float(v3[t].get("valence", 0.5))
        la = float(v3[t].get("arousal", 0.5))
        a = float(np.clip(w_mert * mert_s[i] + (1 - w_mert) * la, 0, 1))
        out[t] = {"valence": round(lv, 4), "arousal": round(a, 4),
                  "label": fusion.get_emotion_label(lv, a),
                  "arousal_mert": round(float(mert_a[i]), 4),
                  "arousal_llm": round(la, 4), "src": "fused_v4"}
    json.dump(out, open("data/emotion_labels_v4.json", "w"), ensure_ascii=False)
    dist = Counter(v["label"] for v in out.values())
    tot = sum(dist.values())
    print(f"[fuse] arousal = {w_mert}·MERT(audio,rank) + {1-w_mert:.1f}·LLM(lyrics) → "
          f"data/emotion_labels_v4.json")
    for k in ['happy', 'excited', 'peaceful', 'calm', 'melancholic', 'sad', 'tense', 'angry']:
        print(f"  {k:12} {dist.get(k,0):5} ({dist.get(k,0)*100//tot}%)")
    Q = {'Q1': dist['happy']+dist['excited'], 'Q2': dist['angry']+dist['tense'],
         'Q3': dist['sad']+dist['melancholic'], 'Q4': dist['peaceful']+dist['calm']}
    print('  Quadrants:', {k: f'{v}({v*100//tot}%)' for k, v in Q.items()})


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    cmd = argv[0] if argv else ""
    if cmd == "extract-deam":
        extract_deam()
    elif cmd == "train":
        train()
    elif cmd == "fuse":
        fuse(float(argv[1]) if len(argv) > 1 else 0.6)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
