"""Build emotion_labels_v6i.json — v6h valence + MuQ-AROUSAL probe (re-test for consistency).

v6h/v6f arousal uses a MERT-arousal probe; the audio backbone is now MuQ (V40). This re-tests
whether arousal can ALSO go MuQ (one fully-consistent backbone). MuQ-arousal beat MERT on
DEAM-human-CV earlier (0.775 vs 0.647) but regressed VN colour-TE in the v6f-era context. Now
the context changed (v6h labels, V38 colour arousal, MuQ backbone, α=0.55) → re-gate.

AROUSAL = NNLS fit on DEAM-human of [MuQ-arousal OOF, clean-BPM, loudness] (tempo floored 0.15),
applied to catalog. VALENCE = inherited from v6h. Adopt only if colour-TE ≤ v6h AND tempo-track holds.
Run: python -m tools.build_v6i_labels  (then gate vs v6h)
"""
from __future__ import annotations
import json, os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr
from scipy.optimize import nnls
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg
from tools.build_v6g_labels import _jv, _rank, _deam_arousal, DEAM

V6H = "data/emotion_labels_v6h.json"
OUT = "data/emotion_labels_v6i.json"


def main() -> int:
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import KFold
    df = pd.read_csv(cfg.PROCESSED_FILE); tids = df["track_id"].astype(str).tolist()
    v6h = json.load(open(V6H))

    # ---- MuQ-arousal blend fit on DEAM-human ----
    ids = json.load(open(f"{DEAM}/deam_ids.json")); arou = _deam_arousal()
    aco = json.load(open(f"{DEAM}/deam_acoustic.json")); muq_d = np.load(f"{DEAM}/deam_muq.npy")
    keep = [i for i, s in enumerate(ids) if s in arou and str(s) in aco and not np.isnan(muq_d[i]).any()]
    yA = np.array([arou[ids[i]] for i in keep])
    Xm = muq_d[keep]; oof = np.zeros(len(yA))
    for tr, te in KFold(5, shuffle=True, random_state=42).split(Xm):
        oof[te] = Ridge(alpha=100).fit(Xm[tr], yA[tr]).predict(Xm[te])
    tempo_d = np.array([aco[str(ids[i])]["tempo"] for i in keep])
    loud_d = np.array([aco[str(ids[i])]["rms_db"] for i in keep])
    F = np.column_stack([_rank(oof), _rank(tempo_d), _rank(loud_d)]); yr = _rank(yA)
    # tempo weight TUNED for MuQ = 0.35 (MuQ doesn't encode tempo, needs more than MERT's 0.15).
    # Sweep (tools/tune_muq_arousal.py): 0.35 → DEAM-CV 0.692 (>MERT 0.647) AND ρ(A,BPM) 0.466
    # (clears the 0.20 target both prior versions failed), colour-TE 0.0246 ≈ v6h. NNLS fallback off.
    wt = float(os.environ.get("BRIGHTIFY_MUQ_TEMPO_W", "0.35"))
    rest = 1 - wt; r = 0.76 / 0.86
    wa = np.array([rest * r, wt, rest * (1 - r)])
    print(f"[v6i arousal] MuQ/tempo/loud weights = {np.round(wa,3).tolist()}")
    # NOTE: this CV measures per-fold NNLS-refit weights, NOT the deployed hand-set `wa` above.
    # It is an UPPER-bound sanity check on the feature set, not validation of `wa`. The deployed
    # blend (wa, tempo-w=0.35) is validated separately in tools/tune_muq_arousal.py (fixed-weight
    # DEAM-CV 0.692 > MERT 0.647). Reported here only to confirm the 3 features carry arousal signal.
    cvr = []
    for tr, te in KFold(5, shuffle=True, random_state=1).split(F):
        wnn, _ = nnls(F[tr], yr[tr]); wnn = wnn / (wnn.sum() + 1e-12)
        cvr.append(spearmanr(F[te] @ wnn, yA[te]).correlation)
    print(f"[v6i arousal] feature-set NNLS-refit CV ρ = {np.nanmean(cvr):.3f}  "
          f"(upper bound; deployed wa validated in tune_muq_arousal.py = 0.692 vs MERT 0.647)")

    # ---- apply to catalog ----
    cf = json.load(open("data/crossfade_features.json"))
    muq_a = _jv("data/muq_arousal.json", None, tids); bpm = _jv("data/clean_bpm.json", None, tids)
    loud = np.array([cf.get(t, {}).get("loudness_lufs", np.nan) for t in tids], float)
    Fv = np.column_stack([_rank(muq_a), _rank(bpm), _rank(loud)])
    araw = np.full(len(tids), np.nan)
    for i in range(len(tids)):
        row = Fv[i]; av = ~np.isnan(row)
        if av.any(): araw[i] = float(row[av] @ wa[av] / (wa[av].sum() + 1e-12))
    araw[np.isnan(araw)] = 0.5
    ar = _rank(araw); arousal = np.clip(0.471 + (ar - ar.mean()) / (ar.std() + 1e-9) * 0.133, 0, 1)

    out = {}
    for i, t in enumerate(tids):
        e = v6h.get(t, {})
        out[t] = {"valence": e.get("valence", 0.5), "arousal": round(float(arousal[i]), 4),
                  "label": e.get("label"), "src": "v6i_v6h-valence_muq-arousal"}
    json.dump(out, open(OUT, "w"), ensure_ascii=False)

    # gate: tempo tracking + vs v6h arousal
    v6h_ar = np.array([float(v6h.get(t, {}).get("arousal", np.nan)) for t in tids])
    def rho(a, b): m = ~np.isnan(a) & ~np.isnan(b); return spearmanr(a[m], b[m]).correlation
    print(f"\n=== v6i GATE ===")
    print(f"  ρ(arousal, clean_BPM)={rho(arousal,bpm):+.3f}  (v6h/v6f MERT was 0.18; >0.20 target)")
    print(f"  ρ(arousal, loudness)={rho(arousal,loud):+.3f}")
    print(f"  ρ vs v6h arousal={rho(arousal,v6h_ar):+.3f}  → {OUT}")
    print(f"  Next: python -m tools.color_eval_rigor --emotions-file {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
