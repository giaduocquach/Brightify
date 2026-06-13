"""Phase 2 — MuQ→V-A probes (train on DEAM-human, apply to catalog).
MuQ beat MERT on DEAM nested-CV (arousal 0.66 vs 0.56; valence 0.55 vs 0.49 — see
audio_probe_compare). Frozen MuQ + Ridge linear probe (no fine-tune). Outputs:
  data/muq_arousal.json, data/muq_valence.json  ({track_id: [0,1]})

Run: python -m tools.muq_probe
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


def _catalog_muq(tids):
    """Align catalog MuQ embeddings to tids via metadata track_ids (handles reorder)."""
    X = np.load("data/muq_embeddings.npy")
    meta_p = "data/muq_metadata.json"
    if os.path.exists(meta_p):
        meta = json.load(open(meta_p))
        order = meta.get("done_track_ids") or meta.get("track_ids")
        if order and len(order) == len(X):
            idx = {str(t): i for i, t in enumerate(order)}
            return np.array([X[idx[t]] if t in idx else np.full(X.shape[1], np.nan) for t in tids])
    return X  # assume row-aligned


def main() -> int:
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import KFold, cross_val_score
    ids = json.load(open(f"{DEAM}/deam_ids.json"))
    lab = _deam_labels()
    muq = np.load(f"{DEAM}/deam_muq.npy")
    keep = [i for i, s in enumerate(ids) if s in lab and not np.isnan(muq[i]).any()]
    X = muq[keep]
    yv = np.array([lab[ids[i]][0] for i in keep]); ya = np.array([lab[ids[i]][1] for i in keep])

    df = pd.read_csv(cfg.PROCESSED_FILE); tids = df["track_id"].astype(str).tolist()
    Xc = _catalog_muq(tids)
    print(f"DEAM train n={len(keep)}  catalog n={len(tids)}  (muq valid {int((~np.isnan(Xc)).any(1).sum())})")

    for axis, y, out in [("arousal", ya, "data/muq_arousal.json"), ("valence", yv, "data/muq_valence.json")]:
        best_a, best = 1.0, -9
        for a in [1, 10, 100, 300, 1000]:
            s = cross_val_score(Ridge(alpha=a), X, y, cv=5, scoring="r2").mean()
            if s > best: best, best_a = s, a
        model = Ridge(alpha=best_a).fit(X, y)
        valid = ~np.isnan(Xc).any(1)
        pred = np.full(len(tids), np.nan)
        pred[valid] = np.clip(model.predict(Xc[valid]), 0, 1)
        d = {tids[i]: round(float(pred[i]), 4) for i in range(len(tids)) if not np.isnan(pred[i])}
        json.dump(d, open(out, "w"))
        print(f"  {axis}: α={best_a} CV-R²={best:.3f}  → {out}  ({len(d)} songs, mean={np.nanmean(pred):.3f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
