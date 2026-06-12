"""Phase 3 — EWE (Evaluator Weighted Estimator) weights for the V-A signal blends.

De-circularizes the valence weighting: instead of NNLS-fit to GPT (an LLM target),
weight each signal by its RELIABILITY = correlation with the consensus of the others
(Grimm & Kroschel 2005; the affect-recognition standard for combining noisy raters
WITHOUT ground truth). Iterative: consensus → re-weight by corr-to-consensus (≥0) → repeat.
No external target → no LLM in the weighting. Reports weight + reliability + bootstrap CI.

Run: python -m tools.va_ewe_weights
"""
from __future__ import annotations
import json, os, sys
import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg

OUT = "var/runtime/backtest/reports/va_ewe_weights.json"


def _rank(a):
    a = np.asarray(a, float); o = np.full(len(a), np.nan); m = ~np.isnan(a)
    if m.sum() > 1: o[m] = (rankdata(a[m]) - 1) / (m.sum() - 1)
    return o


def _jv(path, field, tids):
    if not os.path.exists(path): return None
    d = json.load(open(path))
    def g(t):
        x = d.get(t); return (x.get(field) if isinstance(x, dict) else x) if x is not None else np.nan
    return np.array([g(t) if g(t) is not None else np.nan for t in tids], float)


def ewe(M, iters=10):
    """M: (n, k) rank matrix (rows complete). Returns (weights, reliabilities)."""
    k = M.shape[1]
    w = np.ones(k) / k
    for _ in range(iters):
        cons = M @ w
        r = np.array([max(0.0, spearmanr(M[:, i], cons).correlation) for i in range(k)])
        if r.sum() == 0: break
        w_new = r / r.sum()
        if np.allclose(w_new, w, atol=1e-4): w = w_new; break
        w = w_new
    cons = M @ w
    rel = np.array([float(spearmanr(M[:, i], cons).correlation) for i in range(k)])
    return w, rel


def _boot(M, names, n=2000, seed=1):
    rng = np.random.default_rng(seed); N = len(M); W = []
    for _ in range(n):
        idx = rng.integers(0, N, N); w, _ = ewe(M[idx]); W.append(w)
    W = np.array(W)
    return {names[i]: [round(float(np.percentile(W[:, i], 2.5)), 3), round(float(np.percentile(W[:, i], 97.5)), 3)] for i in range(len(names))}


def _block(name, sigs, refs):
    names = list(sigs)
    M = np.column_stack([_rank(sigs[k]) for k in names])
    keep = ~np.isnan(M).any(1)
    M = M[keep]
    w, rel = ewe(M)
    ci = _boot(M, names)
    print(f"\n=== {name} EWE (n={keep.sum()}) ===")
    for i, k in enumerate(names):
        print(f"  {k:9} weight={w[i]:.3f}  reliability(ρ vs consensus)={rel[i]:+.3f}  CI95={ci[k]}")
    cons = M @ w
    out = {"weights": {names[i]: round(float(w[i]), 3) for i in range(len(names))},
           "reliability": {names[i]: round(float(rel[i]), 3) for i in range(len(names))},
           "weight_ci95": ci, "n": int(keep.sum())}
    # sanity: consensus agreement with independent refs (NOT used for weighting)
    for rn, rv in refs.items():
        rv2 = rv[keep]; m = ~np.isnan(rv2)
        out.setdefault("consensus_vs_ref", {})[rn] = round(float(spearmanr(cons[m], rv2[m]).correlation), 3)
        print(f"  consensus ρ vs {rn} (independent check) = {out['consensus_vs_ref'][rn]}")
    return out


def main() -> int:
    df = pd.read_csv(cfg.PROCESSED_FILE); tids = df["track_id"].astype(str).tolist()
    gpt = _jv("data/va_reference_gpt.json", "valence", tids)
    gem = _jv("data/emotion_labels_v5d.json", "valence", tids)
    vsig = {"vn_lex": _jv("data/emotion_labels_v6c.json", "valence_vnlex", tids),
            "vn_sent": _jv(cfg.VN_SENTIMENT_VALENCE_FILE, None, tids),
            "emobank": _jv("data/emobank_valence.json", None, tids),
            "mert": _jv("data/mert_valence.json", None, tids)}
    rep = {"valence": _block("VALENCE", vsig, {"GPT": gpt, "Gemini": gem})}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(rep, open(OUT, "w"), indent=2)
    print(f"\nsaved → {OUT}  (weights from reliability, NOT from any LLM target)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
