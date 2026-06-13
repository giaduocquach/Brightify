"""Re-test MuQ-arousal with TEMPO-WEIGHT optimization (the lever the user flagged).

v6i's MuQ-arousal tracked tempo poorly (ρ(A,BPM)=0.147 < target 0.20) because the blend
floored tempo at 0.15 — a value inherited from MERT, which already partially encodes tempo.
MuQ does NOT encode tempo (ρ≈0 vs BPM), so it needs a HIGHER explicit tempo weight. Sweep the
tempo weight and find where tempo-tracking clears 0.20 while DEAM-CV holds; then gate colour-TE
on the best candidate. If a setting makes MuQ-arousal both consistent AND no-regression → adopt.

Run: python -m tools.tune_muq_arousal
"""
from __future__ import annotations
import json, os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg
from tools.build_v6g_labels import _jv, _rank, _deam_arousal, DEAM


def main() -> int:
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import KFold
    df = pd.read_csv(cfg.PROCESSED_FILE); tids = df["track_id"].astype(str).tolist()

    # DEAM OOF MuQ-arousal + tempo/loud ranks
    ids = json.load(open(f"{DEAM}/deam_ids.json")); arou = _deam_arousal()
    aco = json.load(open(f"{DEAM}/deam_acoustic.json")); muq_d = np.load(f"{DEAM}/deam_muq.npy")
    keep = [i for i, s in enumerate(ids) if s in arou and str(s) in aco and not np.isnan(muq_d[i]).any()]
    yA = np.array([arou[ids[i]] for i in keep]); yr = _rank(yA)
    Xm = muq_d[keep]; oof = np.zeros(len(yA))
    for tr, te in KFold(5, shuffle=True, random_state=42).split(Xm):
        oof[te] = Ridge(alpha=100).fit(Xm[tr], yA[tr]).predict(Xm[te])
    Fd = np.column_stack([_rank(oof), _rank([aco[str(ids[i])]["tempo"] for i in keep]),
                          _rank([aco[str(ids[i])]["rms_db"] for i in keep])])

    # catalog ranks
    cf = json.load(open("data/crossfade_features.json"))
    muq_a = _rank(_jv("data/muq_arousal.json", None, tids))
    bpm_raw = _jv("data/clean_bpm.json", None, tids); bpm = _rank(bpm_raw)
    loud = _rank(np.array([cf.get(t, {}).get("loudness_lufs", np.nan) for t in tids], float))

    def blend(F, w):
        out = np.full(F.shape[0], np.nan)
        for i in range(F.shape[0]):
            row = F[i]; av = ~np.isnan(row)
            if av.any(): out[i] = row[av] @ w[av] / (w[av].sum() + 1e-12)
        return out

    print(f"{'w_tempo':>8}{'w_muq':>7}{'w_loud':>7} | {'DEAM-CV ρ':>10} {'ρ(A,BPM)cat':>12}")
    print("-" * 50)
    # MuQ:loud ratio ~ NNLS (0.76:0.10); allocate (1−w_tempo) to them
    base_muq, base_loud = 0.76, 0.10; r = base_muq / (base_muq + base_loud)
    results = []
    for wt in (0.15, 0.25, 0.35, 0.45, 0.55):
        rest = 1 - wt; w = np.array([rest * r, wt, rest * (1 - r)])
        cv = spearmanr(Fd @ w, yA).correlation
        cat = blend(np.column_stack([muq_a, bpm, loud]), w)
        rho_bpm = spearmanr(cat[~np.isnan(cat)], bpm_raw[~np.isnan(cat)]).correlation
        results.append((wt, w, cv, rho_bpm))
        print(f"{wt:>8.2f}{w[0]:>7.2f}{w[2]:>7.2f} | {cv:>10.3f} {rho_bpm:>12.3f}")
    print("\n  Target: ρ(A,BPM) ≥ 0.20 (v6h MERT=0.18) while DEAM-CV ≥ 0.647 (v6h).")
    print("  v6f/MERT ref: ρ(A,BPM)=0.18, DEAM-CV=0.647.  Pick smallest w_tempo clearing 0.20,")
    print("  then build that label + gate colour-TE (target ≤ v6h 0.0248).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
