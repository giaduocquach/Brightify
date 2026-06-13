"""Build emotion_labels_v6f.json — AROUSAL completed with the tempo facet it was missing.

Diagnosis (V32): v6e/MERT-arousal tracks loudness/energy (ρ≈0.33–0.43) but NOT tempo
(ρ≈0.005 vs a CLEAN librosa BPM), and in this catalog tempo ⟂ loudness (ρ≈−0.02). So
arousal captured only the energy facet and missed the orthogonal TEMPO facet (Eerola:
arousal = tempo + loudness + spectral energy). Fix: add tempo.

Grounding (DEAM human labels, scale-free): fit a rank-space NNLS of
[MERT-arousal(OOF on DEAM), tempo, loudness] → DEAM human arousal, report CV R²
(human-grounded), then apply the SAME rank features on the VN catalog
[mert_arousal.json, clean_bpm.json, loudness_lufs]. Rank features make the linear
model unit/scale-invariant so DEAM(Western)→VN transfer is honest. Valence = v6e UNCHANGED.

Gate: ρ(v6f-arousal, clean_bpm) > 0.20 (tracks tempo) AND retains loudness tracking
AND color TE(v6f) ≤ v6e (0.0232). Adopt only if all pass.

Run: python -m tools.build_v6f_labels
"""
from __future__ import annotations
import glob, json, os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr
from scipy.optimize import nnls
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg

DEAM_DIR = "data/external/deam"
V6E = "data/emotion_labels_v6e.json"
OUT = "data/emotion_labels_v6f.json"


def _rank(a):
    a = np.asarray(a, float)
    out = np.full(len(a), np.nan)
    m = ~np.isnan(a)
    if m.sum() > 1:
        out[m] = (rankdata(a[m]) - 1) / (m.sum() - 1)
    return out


def _deam_arousal():
    fs = glob.glob(f"{DEAM_DIR}/**/song_level/static_annotations_averaged_songs_*.csv", recursive=True)
    df = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True)
    df.columns = [c.strip() for c in df.columns]
    return dict(zip(df["song_id"].astype(int), df["arousal_mean"].astype(float)))


def main() -> int:
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import KFold

    # ---- DEAM: features [MERT-arousal OOF, tempo, loudness] vs human arousal ----
    Xm = np.load(f"{DEAM_DIR}/deam_mert.npy")
    ids = json.load(open(f"{DEAM_DIR}/deam_ids.json"))
    arou = _deam_arousal()
    aco = json.load(open(f"{DEAM_DIR}/deam_acoustic.json"))
    keep = [i for i, s in enumerate(ids)
            if s in arou and str(s) in aco]
    Xm = Xm[keep]
    y = np.array([(arou[ids[i]] - 1.0) / 8.0 for i in keep])
    tempo = np.array([aco[str(ids[i])]["tempo"] for i in keep])
    loud = np.array([aco[str(ids[i])]["rms_db"] for i in keep])
    print(f"[v6f] DEAM grounding set: {len(keep)} songs")

    # OOF MERT-arousal on DEAM (no leakage)
    oof = np.zeros(len(y))
    kf = KFold(5, shuffle=True, random_state=cfg.RANDOM_SEED)
    for tr, te in kf.split(Xm):
        oof[te] = Ridge(alpha=100.0).fit(Xm[tr], y[tr]).predict(Xm[te])

    # rank features, NNLS → rank(human arousal)
    F = np.column_stack([_rank(oof), _rank(tempo), _rank(loud)])
    yr = _rank(y)
    w, _ = nnls(F, yr)
    w = w / (w.sum() + 1e-12)
    names = ["mert_arousal", "tempo", "loudness"]
    print(f"[v6f] DEAM-grounded weights: {dict(zip(names, np.round(w,3)))}")
    # human-grounded CV R² of the blend
    from sklearn.metrics import r2_score
    cvr2 = []
    for tr, te in kf.split(F):
        wt, _ = nnls(F[tr], yr[tr]); wt = wt/(wt.sum()+1e-12)
        cvr2.append(spearmanr(F[te] @ wt, y[te]).correlation)
    print(f"[v6f] DEAM CV ρ(blend, human arousal) = {np.nanmean(cvr2):.3f}  "
          f"(MERT-only OOF ρ = {spearmanr(oof, y).correlation:.3f})")

    # ---- apply to VN catalog with the SAME rank features ----
    cat = pd.read_csv(cfg.PROCESSED_FILE)
    tids = cat["track_id"].astype(str).values
    mert = json.load(open("data/mert_arousal.json"))
    bpm = json.load(open("data/clean_bpm.json"))
    cf = json.load(open("data/crossfade_features.json"))
    vn_mert = np.array([mert.get(t, np.nan) for t in tids])
    vn_tempo = np.array([bpm.get(t, np.nan) for t in tids])
    vn_loud = np.array([cf.get(t, {}).get("loudness_lufs", np.nan) for t in tids])
    Fv = np.column_stack([_rank(vn_mert), _rank(vn_tempo), _rank(vn_loud)])
    # per-song weighted avg over available features (renormalised)
    arousal_raw = np.full(len(tids), np.nan)
    for i in range(len(tids)):
        row = Fv[i]; av = ~np.isnan(row)
        if av.any():
            ww = w[av]
            arousal_raw[i] = float(row[av] @ ww / (ww.sum() + 1e-12)) if ww.sum() > 0 else float(np.nanmean(row[av]))
    arousal_raw[np.isnan(arousal_raw)] = 0.5
    # preserve v6a-like scale (mean≈0.47, std≈0.13)
    ar = _rank(arousal_raw)
    arousal = np.clip(0.471 + (ar - ar.mean()) / (ar.std() + 1e-9) * 0.133, 0, 1)

    # ---- build v6f: valence UNCHANGED from v6e, arousal replaced ----
    v6e = json.load(open(V6E))
    out = {}
    for i, t in enumerate(tids):
        e = v6e.get(t, {})
        out[t] = {**e, "arousal": round(float(arousal[i]), 4),
                  "src": (e.get("src", "v6e") + "+v6f_arousal")}
    json.dump(out, open(OUT, "w"), ensure_ascii=False)

    # ---- validation: does v6f arousal now track tempo + loudness? ----
    def r(a, b):
        m = ~np.isnan(a) & ~np.isnan(b); return spearmanr(a[m], b[m]).correlation
    print(f"\n=== v6f AROUSAL VALIDATION (VN catalog) ===")
    print(f"  ρ(v6f-arousal, clean_bpm) = {r(arousal, vn_tempo):+.3f}  (v6e was +0.005; target >0.20)")
    print(f"  ρ(v6f-arousal, loudness)  = {r(arousal, vn_loud):+.3f}  (v6e was +0.33; should retain)")
    print(f"  ρ(v6f-arousal, energy)    = {r(arousal, cat['energy'].values.astype(float)):+.3f}")
    print(f"  arousal mean={arousal.mean():.3f} std={arousal.std():.3f}")
    print(f"  → {OUT}\n  Next gate: python -m tools.color_eval_rigor --emotions-file {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
