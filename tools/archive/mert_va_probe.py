"""MERT → (valence, arousal) 2D probe — Phase 2 cross-modal signal.

Trains a small probe on FROZEN MERT-95M embeddings using DEAM static annotations.
Output: data/mert_va.npy  shape=(n_songs, 2)  columns=[valence, arousal]
Rows are aligned with data/mert_embeddings.npy (= catalog CSV row order).

Arousal transfer: established R²≈0.58 (linear) on our catalog via existing
mert_arousal_probe.py.  Valence is harder cross-corpus — MERT captures tonal
cues (major/minor tonality, chord valence, spectral brightness) that are NOT
captured by text/label-based valence. Even R²≈0.2-0.3 adds an independent
audio-based valence dimension for the image→music cross-modal signal.

Both Ridge (linear) and MLP (non-linear) are evaluated; best CV model is used.

Usage:
    python -m tools.mert_va_probe train
"""
from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg

DEAM_DIR  = "data/external/deam"
DEAM_MERT = f"{DEAM_DIR}/deam_mert.npy"
DEAM_IDS  = f"{DEAM_DIR}/deam_ids.json"
OUT_VA    = "data/mert_va.npy"


# ---------------------------------------------------------------------------
# DEAM label loader
# ---------------------------------------------------------------------------

def _deam_va() -> dict:
    """Return {song_id: (valence_norm, arousal_norm)} from DEAM static annotations.

    DEAM labels are on a 1-9 scale.  Normalised to [0, 1] via (x - 1) / 8.
    """
    import pandas as pd
    fs = glob.glob(
        f"{DEAM_DIR}/**/song_level/static_annotations_averaged_songs_*.csv",
        recursive=True,
    )
    df = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True)
    df.columns = [c.strip() for c in df.columns]
    out = {}
    for _, row in df.iterrows():
        sid = int(row["song_id"])
        v   = (float(row["valence_mean"]) - 1.0) / 8.0
        a   = (float(row["arousal_mean"]) - 1.0) / 8.0
        out[sid] = (float(np.clip(v, 0, 1)), float(np.clip(a, 0, 1)))
    return out


# ---------------------------------------------------------------------------
# Train
# ---------------------------------------------------------------------------

def train() -> None:
    from sklearn.linear_model import Ridge
    from sklearn.neural_network import MLPRegressor
    from sklearn.model_selection import KFold, cross_val_score
    from sklearn.multioutput import MultiOutputRegressor
    from scipy.stats import spearmanr

    X   = np.load(DEAM_MERT)
    ids = json.load(open(DEAM_IDS))
    va  = _deam_va()

    # Align ids → labels
    aligned = [(i, va[s]) for i, s in enumerate(ids) if s in va]
    row_idx  = np.array([a[0] for a in aligned])
    Y        = np.array([a[1] for a in aligned])          # (N, 2): [valence, arousal]
    X_train  = X[row_idx]

    print(f"[mert_va] DEAM train set: X={X_train.shape}  "
          f"V mean={Y[:,0].mean():.3f} std={Y[:,0].std():.3f}  "
          f"A mean={Y[:,1].mean():.3f} std={Y[:,1].std():.3f}")

    cv = KFold(5, shuffle=True, random_state=cfg.RANDOM_SEED)

    # ---- Ridge (linear) ----
    print("\n=== Ridge probe — 5-fold CV R² ===")
    best_ridge_a, best_ridge_r2_v, best_ridge_r2_a = 100.0, -9.0, -9.0
    for alpha in [1.0, 10.0, 100.0, 300.0]:
        r2_v = cross_val_score(Ridge(alpha=alpha), X_train, Y[:, 0], cv=cv, scoring="r2")
        r2_a = cross_val_score(Ridge(alpha=alpha), X_train, Y[:, 1], cv=cv, scoring="r2")
        print(f"  α={alpha:5.0f}  valence R²={r2_v.mean():+.3f}±{r2_v.std():.3f}  "
              f"arousal R²={r2_a.mean():+.3f}±{r2_a.std():.3f}")
        if r2_v.mean() > best_ridge_r2_v:
            best_ridge_a, best_ridge_r2_v, best_ridge_r2_a = alpha, r2_v.mean(), r2_a.mean()

    # ---- MLP (non-linear) ----
    print("\n=== MLP probe — 5-fold CV R² ===")
    mlp_cfg = dict(hidden_layer_sizes=(512, 256), activation="relu",
                   max_iter=300, random_state=cfg.RANDOM_SEED, early_stopping=True,
                   validation_fraction=0.1, n_iter_no_change=15)
    mlp_v = MLPRegressor(**mlp_cfg)
    mlp_a = MLPRegressor(**mlp_cfg)
    r2_mlp_v = cross_val_score(mlp_v, X_train, Y[:, 0], cv=cv, scoring="r2")
    r2_mlp_a = cross_val_score(mlp_a, X_train, Y[:, 1], cv=cv, scoring="r2")
    print(f"  MLP(512,256)  valence R²={r2_mlp_v.mean():+.3f}±{r2_mlp_v.std():.3f}  "
          f"arousal R²={r2_mlp_a.mean():+.3f}±{r2_mlp_a.std():.3f}")

    # ---- Choose best per dimension ----
    use_mlp_v = r2_mlp_v.mean() > best_ridge_r2_v
    use_mlp_a = r2_mlp_a.mean() > best_ridge_r2_a
    print(f"\n  → valence model:  {'MLP' if use_mlp_v else f'Ridge α={best_ridge_a}'}"
          f"  (CV R²={r2_mlp_v.mean():.3f} vs {best_ridge_r2_v:.3f})")
    print(f"  → arousal model:  {'MLP' if use_mlp_a else f'Ridge α={best_ridge_a}'}"
          f"  (CV R²={r2_mlp_a.mean():.3f} vs {best_ridge_r2_a:.3f})")

    # ---- Train final models ----
    if use_mlp_v:
        model_v = MLPRegressor(**mlp_cfg).fit(X_train, Y[:, 0])
    else:
        model_v = Ridge(alpha=best_ridge_a).fit(X_train, Y[:, 0])

    if use_mlp_a:
        model_a = MLPRegressor(**mlp_cfg).fit(X_train, Y[:, 1])
    else:
        model_a = Ridge(alpha=best_ridge_a).fit(X_train, Y[:, 1])

    # ---- Apply to catalog ----
    ours = np.load(cfg.MERT_EMBEDDINGS_FILE)   # (n_songs, 768)
    val_pred = np.clip(model_v.predict(ours), 0.0, 1.0)
    aro_pred = np.clip(model_a.predict(ours), 0.0, 1.0)
    mert_va  = np.column_stack([val_pred, aro_pred]).astype(np.float32)
    np.save(OUT_VA, mert_va)
    print(f"\n[mert_va] Saved {mert_va.shape} → {OUT_VA}")
    print(f"  valence: mean={val_pred.mean():.3f}  std={val_pred.std():.3f}  "
          f"≥0.5: {(val_pred>=0.5).mean()*100:.0f}%")
    print(f"  arousal: mean={aro_pred.mean():.3f}  std={aro_pred.std():.3f}  "
          f"≥0.5: {(aro_pred>=0.5).mean()*100:.0f}%")

    # ---- Sanity: compare with existing signals ----
    import pandas as pd
    from scipy.stats import spearmanr
    cat = pd.read_csv(cfg.PROCESSED_FILE)
    if "tempo" in cat.columns:
        print(f"\n=== Sanity checks on catalog ===")
        tempo  = cat["tempo"].fillna(cat["tempo"].median()).values
        energy = cat["energy"].fillna(0.5).values if "energy" in cat.columns else None
        print(f"  MERT-arousal vs tempo  ρ={spearmanr(aro_pred,  tempo).correlation:+.3f}  (expected +)")
        if energy is not None:
            print(f"  MERT-arousal vs energy ρ={spearmanr(aro_pred,  energy).correlation:+.3f}  (expected +)")
            print(f"  MERT-valence vs energy ρ={spearmanr(val_pred,  energy).correlation:+.3f}  (expected ~0)")
        if os.path.exists(cfg.RELABELED_EMOTIONS_FILE):
            v5 = json.load(open(cfg.RELABELED_EMOTIONS_FILE))
            tids   = cat["track_id"].astype(str).tolist()
            llm_v  = np.array([v5.get(t, {}).get("valence",  0.5) for t in tids])
            llm_a  = np.array([v5.get(t, {}).get("arousal",  0.5) for t in tids])
            print(f"  MERT-valence vs LLM-valence ρ={spearmanr(val_pred, llm_v).correlation:+.3f}")
            print(f"  MERT-arousal vs LLM-arousal ρ={spearmanr(aro_pred, llm_a).correlation:+.3f}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    if not argv or argv[0] != "train":
        print(__doc__)
        return 1
    train()
    return 0


if __name__ == "__main__":
    sys.exit(main())
