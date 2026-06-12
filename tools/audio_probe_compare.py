"""Phase 2 — compare audio→V-A probes on DEAM (nested-CV R²): current MERT vs per-layer
MERT vs MuQ (SOTA-2025) vs MuQ+MERT ensemble. Pick the best per axis. Catalog MuQ
embeddings already exist (data/muq_embeddings.npy) so a winner is directly deployable.
Frozen embeddings + Ridge linear probe only (no fine-tune). DEAM human V-A = target.

Run: python -m tools.audio_probe_compare
"""
from __future__ import annotations
import glob, json, os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg

DEAM = "data/external/deam"


def _deam_labels():
    fs = glob.glob(f"{DEAM}/**/song_level/static_annotations_averaged_songs_*.csv", recursive=True)
    df = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True)
    df.columns = [c.strip() for c in df.columns]
    return {int(r.song_id): ((r.valence_mean - 1) / 8, (r.arousal_mean - 1) / 8) for r in df.itertuples()}


def _nested_cv_r2(X, y, seed=42):
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import KFold, cross_val_score
    outer = KFold(5, shuffle=True, random_state=seed)
    r2s = []
    for tr, te in outer.split(X):
        best_a, best = 1.0, -9
        for a in [1, 10, 100, 300, 1000]:
            s = cross_val_score(Ridge(alpha=a), X[tr], y[tr], cv=3, scoring="r2").mean()
            if s > best: best, best_a = s, a
        m = Ridge(alpha=best_a).fit(X[tr], y[tr])
        pred = m.predict(X[te])
        ss_res = ((y[te] - pred) ** 2).sum(); ss_tot = ((y[te] - y[te].mean()) ** 2).sum()
        r2s.append(1 - ss_res / ss_tot)
    return float(np.mean(r2s)), float(np.std(r2s))


def main() -> int:
    ids = json.load(open(f"{DEAM}/deam_ids.json"))
    lab = _deam_labels()
    keep = [i for i, s in enumerate(ids) if s in lab]
    yv = np.array([lab[ids[i]][0] for i in keep]); ya = np.array([lab[ids[i]][1] for i in keep])
    mert_all = np.load(f"{DEAM}/deam_mert_all_layers.npy")[keep]   # (n,12,768)
    muq = np.load(f"{DEAM}/deam_muq.npy")[keep]                    # (n,1024)
    mvalid = ~np.isnan(muq).any(1)
    print(f"DEAM: n={len(keep)} (muq valid {mvalid.sum()})")

    mert_mean = mert_all.mean(1)   # current production (mean 12 layers)
    configs = {
        "MERT mean-12 (current)": mert_mean,
        "MuQ": muq,
        "MuQ+MERT (concat)": np.hstack([muq, mert_mean]),
    }
    for axis, y in [("AROUSAL", ya), ("VALENCE", yv)]:
        print(f"\n=== {axis} — DEAM nested-CV R² ===")
        for nm, X in configs.items():
            m = mvalid if "MuQ" in nm else np.ones(len(keep), bool)
            r2, sd = _nested_cv_r2(X[m], y[m])
            print(f"  {nm:24} R²={r2:+.3f} ± {sd:.3f}")
        # best single MERT layer
        best_layer, best_r2 = None, -9
        for L in range(mert_all.shape[1]):
            r2, _ = _nested_cv_r2(mert_all[:, L, :], y)
            if r2 > best_r2: best_r2, best_layer = r2, L
        print(f"  MERT best single layer = L{best_layer}  R²={best_r2:+.3f}  (vs mean-12 above)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
