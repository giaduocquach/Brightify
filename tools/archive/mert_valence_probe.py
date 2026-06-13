"""MERT→valence probe (A1.3, V27).

Experimental: cross-corpus valence transfer is harder than arousal (see mert_arousal_probe.py
comment). Gate: held-out CV R² ≥ 0.15 on DEAM + catalog Spearman ρ ≥ 0.40 vs Gemini valence.
If gate fails → document negative result, valence stays Gemini-from-lyrics.

Uses the SAME frozen DEAM MERT embeddings as the arousal probe (deam_mert.npy / deam_ids.json).
Does NOT re-extract unless --layers is given.

  train          : all-layers probe → data/mert_valence.json
  train --layers 9,11,12 : layer ablation (CV R² only, re-extracts DEAM if needed)

Usage:
  python -m tools.mert_valence_probe train
  python -m tools.mert_valence_probe train --layers 9
  python -m tools.mert_valence_probe train --layers 9,10,11,12
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
DEAM_AUDIO = f"{DEAM_DIR}/MEMD_audio"
DEAM_IDS = f"{DEAM_DIR}/deam_ids.json"
DEAM_ALL_LAYERS = f"{DEAM_DIR}/deam_mert_all_layers.npy"
OUT_VALENCE = "data/mert_valence.json"

# Gate thresholds (conservative — valence harder than arousal cross-corpus)
GATE_CV_R2 = 0.15
GATE_CATALOG_RHO = 0.40


def _deam_valence() -> dict:
    """song_id -> valence_mean (1..9) from DEAM static annotations."""
    import pandas as pd
    fs = glob.glob(f"{DEAM_DIR}/**/song_level/static_annotations_averaged_songs_*.csv",
                   recursive=True)
    df = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True)
    df.columns = [c.strip() for c in df.columns]
    return dict(zip(df["song_id"].astype(int), df["valence_mean"].astype(float)))


def _layers_key(layers) -> str:
    """Canonical string key for a layer config: e.g. [9] → 'l9', [9,11,12] → 'l9-11-12'."""
    if isinstance(layers, int):
        return f"l{layers}"
    return "l" + "-".join(str(l) for l in sorted(layers))


def _load_ablation_X(layers) -> np.ndarray | None:
    """Slice specific layers from pre-extracted all-layers file (fast path, no re-extract)."""
    if not os.path.exists(DEAM_ALL_LAYERS):
        return None
    all_layers = np.load(DEAM_ALL_LAYERS)  # (N, 12, 768)
    layer_list = [layers] if isinstance(layers, int) else list(layers)
    idxs = [l - 1 for l in layer_list]  # 1-indexed → 0-indexed
    return all_layers[:, idxs, :].mean(axis=1)  # (N, 768)


def _extract_deam_for_layers(layers) -> np.ndarray:
    """Fallback: re-extract DEAM with specific layers if all-layers file missing."""
    from core.mert_encoder import MERTEncoder
    key = _layers_key(layers)
    out_path = f"{DEAM_DIR}/deam_mert_{key}.npy"
    ids = json.load(open(DEAM_IDS))

    if os.path.exists(out_path):
        print(f"  [extract] Loading cached {out_path}")
        return np.load(out_path)

    if not os.path.isdir(DEAM_AUDIO):
        print(f"ERROR: DEAM audio not found at {DEAM_AUDIO}. Cannot re-extract.")
        return None

    print(f"  [extract] Extracting DEAM with layers={layers} ({len(ids)} songs) …")
    enc = MERTEncoder(layers=layers)
    embs = []
    for sid in ids:
        mp3 = os.path.join(DEAM_AUDIO, f"{sid}.mp3")
        if not os.path.exists(mp3):
            embs.append(np.zeros(768, dtype=np.float32))
        else:
            embs.append(enc.extract(mp3).astype(np.float32))
    X = np.stack(embs)
    np.save(out_path, X)
    print(f"  [extract] Saved {X.shape} → {out_path}")
    return X


def train(layers=None) -> None:
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import KFold, cross_val_score
    from scipy.stats import spearmanr
    import pandas as pd

    ablation = layers is not None
    if ablation:
        X = _load_ablation_X(layers)
        if X is not None:
            ids = json.load(open(DEAM_IDS))
            print(f"\n[ABLATION] layers={layers} key={_layers_key(layers)} (sliced from all-layers file)")
        else:
            X = _extract_deam_for_layers(layers)
            if X is None:
                return
            ids = json.load(open(DEAM_IDS))
            print(f"\n[ABLATION] layers={layers} key={_layers_key(layers)}")
    else:
        if not os.path.exists(DEAM_MERT):
            print(f"ERROR: {DEAM_MERT} not found. Run mert_arousal_probe extract-deam first.")
            return
        X = np.load(DEAM_MERT)
        ids = json.load(open(DEAM_IDS))
    labels = _deam_valence()

    # Filter to songs that have both MERT embedding and valence label
    keep = [(i, sid) for i, sid in enumerate(ids) if sid in labels]
    if not keep:
        print("ERROR: no DEAM songs with both MERT+valence label.")
        return
    idx, sids = zip(*keep)
    X = X[list(idx)]
    y = np.array([(labels[s] - 1.0) / 8.0 for s in sids])   # 1..9 → 0..1
    print(f"[train] DEAM probe set: X={X.shape}  valence mean={y.mean():.2f} std={y.std():.2f}")

    print("\n=== Probe validity — 5-fold CV R² (held-out DEAM) ===")
    cv = KFold(5, shuffle=True, random_state=cfg.RANDOM_SEED)
    best_a, best_r2 = 1.0, -9.0
    for alpha in [1.0, 10.0, 100.0, 300.0, 1000.0]:
        r2 = cross_val_score(Ridge(alpha=alpha), X, y, cv=cv, scoring="r2")
        print(f"  Ridge α={alpha:6}: R²={r2.mean():+.3f} ± {r2.std():.3f}")
        if r2.mean() > best_r2:
            best_a, best_r2 = alpha, r2.mean()
    print(f"  → best α={best_a} (CV R²={best_r2:.3f})")

    gate_cv = best_r2 >= GATE_CV_R2
    print(f"\n  Gate CV R²≥{GATE_CV_R2}: {'PASS ✓' if gate_cv else 'FAIL ✗'}")

    if not gate_cv:
        print("\nNEGATIVE RESULT: cross-corpus valence transfer insufficient.")
        print(f"  CV R²={best_r2:.3f} < {GATE_CV_R2}  Valence stays Gemini-from-lyrics.")
        if not ablation:
            print("  This confirms the note in mert_arousal_probe.py.")
        return

    model = Ridge(alpha=best_a).fit(X, y)

    if ablation:
        # Ablation mode: only report CV R², skip catalog (needs separate re-extraction)
        key = _layers_key(layers)
        print(f"\n[ABLATION RESULT] layers={layers} CV R²={best_r2:.3f}")
        print(f"  Compare vs all-layers baseline (CV R²=0.487).")
        print(f"  If better: re-extract catalog with layers={layers} and rerun `train`.")
        return

    # Apply to OUR catalog
    ours = np.load(cfg.MERT_EMBEDDINGS_FILE)
    pred = np.clip(model.predict(ours), 0, 1)
    cat = pd.read_csv(cfg.PROCESSED_FILE)
    tids = cat["track_id"].astype(str).tolist()

    # Catalog gate: ρ vs Gemini valence
    gemini_v = np.array([float(cat.loc[cat["track_id"].astype(str) == t, "valence"].iloc[0])
                         if (cat["track_id"].astype(str) == t).any() else 0.5
                         for t in tids])
    # Simpler: assume catalog rows align with tids
    if "valence" in cat.columns:
        gemini_v = cat["valence"].fillna(0.5).values.astype(float)
    rho = spearmanr(pred, gemini_v).correlation
    gate_rho = rho >= GATE_CATALOG_RHO
    print(f"\n=== Catalog validation ===")
    print(f"  MERT-valence vs Gemini-valence ρ = {rho:+.3f}")
    print(f"  Gate catalog ρ≥{GATE_CATALOG_RHO}: {'PASS ✓' if gate_rho else 'FAIL ✗'}")

    print(f"\n  distribution: mean={pred.mean():.2f} std={pred.std():.2f} "
          f"≥0.5: {(pred>=0.5).mean()*100:.0f}%")

    if not gate_rho:
        print("\nNEGATIVE RESULT: catalog ρ too low for safe label update.")
        print(f"  ρ={rho:.3f} < {GATE_CATALOG_RHO}  Valence stays Gemini-from-lyrics.")
        return

    json.dump({t: round(float(p), 4) for t, p in zip(tids, pred)}, open(OUT_VALENCE, "w"))
    print(f"\n[train] GATE PASSED — saved {len(pred)} predictions → {OUT_VALENCE}")
    print("  Next: blend MERT-valence with Gemini-valence (e.g. 0.3·MERT + 0.7·Gemini)")
    print("        then re-run color_eval_rigor.py to confirm TE does not regress.")


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    cmd = argv[0] if argv else ""
    if cmd == "train":
        layers = None
        if "--layers" in argv:
            idx = argv.index("--layers")
            raw = argv[idx + 1]
            parts = [int(x) for x in raw.split(",")]
            layers = parts[0] if len(parts) == 1 else parts
        train(layers=layers)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
